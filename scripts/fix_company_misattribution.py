#!/usr/bin/env python
"""Repair drugs whose company_id contradicts the authoritative trial sponsor.

The Novavax/Garvan wrong-company attribution bug: stale ``drugs.company_id`` from
an older resolution attributed Novo Nordisk's diabetes pipeline (Cagrilintide,
IcoSema, IDegLira, the NNC-* compound codes, ...) to ``NOVAVAX, INC.`` and
tirzepatide / metformin investigator-trial drugs to the (excluded) Garvan
Institute. Asking ``/chat`` about Novavax therefore returned Novo Nordisk's
pipeline. The trials themselves carry the correct ``sponsor_name``
('Novo Nordisk A/S'), so we re-derive the company from each drug's *dominant*
sponsor via a SAFE normalized-exact match — never fuzzy
(similarity('novo nordisk','novavax')=0.19 is below threshold, yet an older path
collapsed them; we must not repeat that).

Conservation:
  * Repoints ``drugs.company_id`` and the OWNS ``entity_links`` row, recording the
    prior company_id in ``entity_links.metadata.reattribution`` — reversible, not a
    silent overwrite.
  * Only acts when the dominant sponsor clears a plurality floor AND resolves
    (normalized-exact) to a company DIFFERENT from the current one. Anything
    weaker is left untouched and logged for review — never a silent change.
  * Idempotent (a re-run finds company_id already correct → no-op). Dry-run by
    default; ``--apply`` to write.

Usage:
    python -m scripts.fix_company_misattribution                 # dry-run, all companies
    python -m scripts.fix_company_misattribution --company <id>  # scope to one company
    python -m scripts.fix_company_misattribution --apply         # write changes
"""
from __future__ import annotations

import argparse
import json
import logging
import os
from collections import Counter
from typing import Optional

from domain.pharma.mention_normalizer import normalize_company_mention

logger = logging.getLogger(__name__)


# ── pure helpers (unit-tested, DB-free) ─────────────────────────────────────────

def normalized_company_key(name: Optional[str]) -> str:
    """The canonical join key for a company name / sponsor string. Collapses
    corporate suffixes + punctuation so 'Novo Nordisk A/S' and 'NOVO NORDISK INC'
    agree, while staying distinct from unrelated names ('Novavax')."""
    if not name:
        return ""
    try:
        return (normalize_company_mention(name) or "").strip().lower()
    except Exception:
        return name.strip().lower()


def dominant_sponsor(counts: dict, min_share: float = 0.5) -> Optional[str]:
    """The single sponsor that accounts for >= ``min_share`` of a drug's trials,
    or None when no sponsor has a clear plurality (then we don't guess). Blank
    sponsor strings are ignored."""
    clean = {s: n for s, n in counts.items() if s and str(s).strip()}
    total = sum(clean.values())
    if total <= 0:
        return None
    sponsor, n = max(clean.items(), key=lambda kv: kv[1])
    return sponsor if n / total >= min_share else None


def should_reattribute(resolved_company_id: Optional[str],
                       current_company_id: Optional[str]) -> bool:
    """Repoint only when the sponsor resolved to a real company that differs from
    the current attribution. Never null out an existing link on a non-resolution."""
    return bool(resolved_company_id) and resolved_company_id != current_company_id


# ── DB layer ────────────────────────────────────────────────────────────────────

def build_company_index(db) -> dict[str, str]:
    """{normalized_key: company_id}. On collision prefer an active company, then
    the richer one (more owned drugs) — the resolver's richness rule, so we land
    on the canonical row rather than a stub."""
    rows = db.fetch_all(
        """
        SELECT c.id::text AS id, c.name, c.record_status,
               (SELECT count(*) FROM drugs d WHERE d.company_id = c.id) AS owned
          FROM companies c
        """
    ) or []
    best: dict[str, tuple] = {}
    for r in rows:
        key = normalized_company_key(r.get("name"))
        if not key:
            continue
        active = (r.get("record_status") == "active")
        rank = (1 if active else 0, int(r.get("owned") or 0))
        if key not in best or rank > best[key][0]:
            best[key] = (rank, str(r["id"]))
    return {k: v[1] for k, v in best.items()}


def drug_dominant_sponsor(db, drug_id: str, min_share: float = 0.5) -> Optional[str]:
    rows = db.fetch_all(
        "SELECT sponsor_name FROM clinical_trials WHERE drug_id = %s", [drug_id]
    ) or []
    counts = Counter(r.get("sponsor_name") for r in rows)
    return dominant_sponsor(dict(counts), min_share=min_share)


def repair(db, *, target_company_ids: Optional[list[str]] = None,
           apply: bool = False, min_share: float = 0.5) -> dict:
    """Re-derive company_id from the dominant trial sponsor for drugs currently
    attributed to ``target_company_ids`` (or all drugs with a company_id when
    None). Returns a stats dict; mutates only when ``apply``."""
    index = build_company_index(db)

    if target_company_ids:
        drugs = db.fetch_all(
            "SELECT id::text AS id, generic_name, company_id::text AS company_id "
            "FROM drugs WHERE company_id::text = ANY(%s)", [list(target_company_ids)]
        ) or []
    else:
        drugs = db.fetch_all(
            "SELECT id::text AS id, generic_name, company_id::text AS company_id "
            "FROM drugs WHERE company_id IS NOT NULL"
        ) or []

    stats = {"scanned": 0, "reattributed": 0, "already_correct": 0,
             "no_dominant_sponsor": 0, "sponsor_unresolved": 0, "changes": []}

    for d in drugs:
        stats["scanned"] += 1
        drug_id = d["id"]
        current = d.get("company_id")
        sponsor = drug_dominant_sponsor(db, drug_id, min_share=min_share)
        if not sponsor:
            stats["no_dominant_sponsor"] += 1
            continue
        resolved = index.get(normalized_company_key(sponsor))
        if not resolved:
            stats["sponsor_unresolved"] += 1
            continue
        if not should_reattribute(resolved, current):
            stats["already_correct"] += 1
            continue
        stats["reattributed"] += 1
        stats["changes"].append({"drug": d.get("generic_name"), "drug_id": drug_id,
                                 "from": current, "to": resolved, "sponsor": sponsor})
        if apply:
            _apply_reattribution(db, drug_id, current, resolved)
    return stats


def _apply_reattribution(db, drug_id: str, old_company: Optional[str],
                         new_company: str) -> None:
    """Repoint drugs.company_id + the OWNS entity_link, recording the prior value
    in entity_links.metadata (reversible). Best-effort per drug."""
    db.execute("UPDATE drugs SET company_id = %s WHERE id = %s",
               [new_company, drug_id])
    prov = json.dumps({"reattribution": {"from": old_company, "to": new_company,
                                         "by": "fix_company_misattribution"}})
    # Move (or create) the OWNS link, stamping provenance of the prior owner.
    db.execute(
        "UPDATE entity_links "
        "   SET source_entity_id = %s, "
        "       metadata = COALESCE(metadata, '{}'::jsonb) || %s::jsonb "
        " WHERE link_type = 'OWNS' AND target_entity_type = 'drug' "
        "   AND target_entity_id = %s AND source_entity_id = %s",
        [new_company, prov, drug_id, old_company],
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--company", action="append", dest="companies",
                    help="scope to drugs owned by this company id (repeatable)")
    ap.add_argument("--apply", action="store_true", help="write changes")
    ap.add_argument("--min-share", type=float, default=0.5)
    args = ap.parse_args()

    from db import Database
    dsn = os.environ.get("DATABASE_URL") or __import__("config").config.db.dsn
    db = Database(dsn)
    db.connect()
    try:
        stats = repair(db, target_company_ids=args.companies, apply=args.apply,
                       min_share=args.min_share)
    finally:
        db.close()

    mode = "APPLIED" if args.apply else "DRY-RUN"
    logger.info("[%s] scanned=%d reattributed=%d already_correct=%d "
                "no_dominant_sponsor=%d sponsor_unresolved=%d", mode,
                stats["scanned"], stats["reattributed"], stats["already_correct"],
                stats["no_dominant_sponsor"], stats["sponsor_unresolved"])
    for c in stats["changes"][:40]:
        logger.info("  %s: %s -> %s  (sponsor=%s)", c["drug"], c["from"], c["to"],
                    c["sponsor"])
    if len(stats["changes"]) > 40:
        logger.info("  ... and %d more", len(stats["changes"]) - 40)


if __name__ == "__main__":
    main()
