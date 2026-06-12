"""Consolidate duplicate drug records into canonical entities.

Merges multiple records for the same drug (e.g., 7 "sitagliptin" variants)
into one canonical record, keeping the best-quality data and re-pointing
entity_links to the surviving record.

Usage:
    python -m scripts.consolidate_drugs [--dry-run]
"""

from __future__ import annotations

import argparse
import logging
import re
from datetime import datetime, timezone

from config import config
from db import Database

logger = logging.getLogger(__name__)


def _normalize_drug_name(name: str) -> str:
    """Normalize a drug name for grouping duplicates.

    Strips salt forms, dosage info, brand mentions, and common noise
    to find the canonical drug name for dedup grouping.
    """
    n = name.strip()
    # Lowercase
    n = n.lower()
    # Remove parenthetical brand names: "sitagliptin (Januvia)" → "sitagliptin"
    n = re.sub(r"\s*\([^)]*\)", "", n)
    # Remove salt forms: "phosphate", "hydrochloride", "monohydrate", "anhydrous"
    n = re.sub(
        r"\b(?:phosphate|hydrochloride|hcl|monohydrate|anhydrous|mesylate|"
        r"maleate|fumarate|succinate|tartrate|besylate|calcium|sodium|"
        r"potassium|acetate|citrate|sulfate|nitrate|bromide|chloride|"
        r"disodium|dipotassium|hemifumarate|tromethamine)\b",
        "", n,
    )
    # Remove dosage forms: "oral", "tablet", "injection", "formulation"
    n = re.sub(
        r"\b(?:oral|tablet|injection|capsule|solution|suspension|formulation|"
        r"extended.release|immediate.release|film.coated|ir|er|sr|xr|xl)\b",
        "", n,
    )
    # Remove "DPP4i", "- DPP4i", "DPP-4 inhibitor" suffixes
    n = re.sub(r"\s*[-–]\s*(?:DPP-?4i?|SGLT2i?|GLP-1|ARB|ACEi)\b", "", n, flags=re.IGNORECASE)
    # Remove "MK0431" style identifiers
    n = re.sub(r"\b[A-Z]{1,4}\d{3,6}\b", "", n, flags=re.IGNORECASE)
    # Remove "/ duration of treatment: 21 weeks" style tails
    n = re.sub(r"\s*/\s*duration.*$", "", n)
    # Collapse whitespace
    n = re.sub(r"\s+", " ", n).strip()
    # Remove trailing punctuation
    n = n.rstrip(".,;:-/ ")
    return n


def combo_safe_normalize(name: str) -> str:
    """Normalize for dedup grouping, but NEVER collapse an additive combo into
    its mono. `_normalize_drug_name` strips parentheticals, so
    "losartan potassium (+ hydrochlorothiazide)" would otherwise normalize to
    "losartan" and be merged into the monotherapy — a wrong merge. When an
    additive-combo marker is present ("(+", " + "), fall back to the exact
    lowercased raw name so the row only groups with identical strings."""
    if not name:
        return ""
    if "(+" in name or " + " in name:
        return name.strip().lower()
    return _normalize_drug_name(name)


def _pick_canonical(records: list[dict]) -> dict:
    """Pick the best record to keep as canonical.

    Priority: FDA source > backfill with most links > alphabetically first.
    """
    fda_records = [r for r in records if r["source_api"] in ("fda_orange_book", "fda_labels")]
    ct_records = [r for r in records if r["source_api"] == "clinical_trials_gov"]
    backfill_records = [r for r in records if r["source_api"] == "backfill"]

    # Prefer FDA, then CT.gov, then backfill
    candidates = fda_records or ct_records or backfill_records or records

    # Among candidates, prefer ones with company_id and mechanism_id set
    scored = []
    for r in candidates:
        score = 0
        if r.get("company_id"):
            score += 10
        if r.get("mechanism_id"):
            score += 5
        if r.get("brand_name") and r["brand_name"] != r.get("generic_name"):
            score += 3
        if r.get("therapeutic_area_id"):
            score += 2
        score += r.get("link_count", 0) / 100  # tie-break by links
        scored.append((score, r))

    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1]


def _log_change(db: Database, entity_type: str, entity_id: str,
                change_type: str, fields: list[str]) -> None:
    db.execute(
        """
        INSERT INTO data_change_log
            (entity_type, entity_id, change_type, changed_fields, changed_at)
        VALUES (%s, %s, %s, %s, %s)
        """,
        [entity_type, entity_id, change_type, fields, datetime.now(timezone.utc)],
    )


def consolidate_drugs(db: Database, dry_run: bool = False) -> dict:
    """Find and merge duplicate drug records.

    Delegates to the hardened ``EntityConsolidator`` (richness-ranked,
    combo-safe) instead of the historical in-module merge. That older path was
    a conservation landmine and actively corrupted prod: it (a) grouped without
    excluding ``record_status='superseded'`` rows, so it re-processed rows that
    a prior pass had already soft-deleted; (b) chose the canonical by *source
    authority* (``_pick_canonical``) rather than data richness — the opposite of
    what the chat/dossier resolvers use; and (c) only moved ``entity_links``
    (DELETE-ing the rest) while leaving the loser's facts / clinical_trials /
    signals stranded. Run via the scheduler's ``auto_curate`` post-task, it
    demoted the rich ``tirzepatide`` canonical (269 facts / 112 trials) to
    ``record_status='merged'`` and scattered its links — so ``resolve_entity``
    fell through to a junk look-alike row and "compare semaglutide vs
    tirzepatide" reported 1 trial instead of 184.

    ``EntityConsolidator(rank_by_richness=True, …)`` instead: excludes
    merged+superseded, keeps the evidence-owning (richest) row as canonical so
    it is never demoted, and conflict-safe repoints EVERY reference — FK tables,
    text-keyed ``facts.subject_entity_id``, and ``signals`` — never DELETE-ing
    them. ``combo_safe_normalize`` keeps additive combos (Hyzaar) out of the
    mono's group. See tests/test_consolidate_drugs_richness_canonical.py.
    """
    from integration.entity_consolidator import EntityConsolidator

    consolidator = EntityConsolidator(
        db,
        dry_run=dry_run,
        rank_by_richness=True,
        drug_name_normalizer=combo_safe_normalize,
    )
    res = consolidator.consolidate_drugs()
    # Preserve the historical return shape that callers (scripts.auto_curate)
    # read/annotate.
    return {
        "groups_found": res.get("groups_found", 0),
        "records_merged": res.get("records_merged", 0),
        "aliases_created": res.get("records_merged", 0),
        "skipped": res.get("skipped", 0),
        "plan": res.get("plan", []),
    }


def run(dry_run: bool = False) -> dict:
    """Run drug consolidation."""
    db = Database(config.db.dsn)
    db.connect()
    try:
        return consolidate_drugs(db, dry_run)
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Consolidate duplicate drug records")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    results = run(dry_run=args.dry_run)
    print("\n=== Drug Consolidation Results ===")
    for k, v in results.items():
        print(f"  {k}: {v}")
    if args.dry_run:
        print("  (dry run — no changes written)")


if __name__ == "__main__":
    main()
