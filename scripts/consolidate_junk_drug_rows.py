"""Consolidate junk / duplicate drug-spine rows (Loop 3, data-quality push).

The drugs spine accumulates entity-extraction garbage alongside real drugs:

  * **fragments / dose-arms** — "initiation of tirzepatide", "Tirzepatide Dose 1",
    "Tirzepatide as an adjunct to lifestyle intervention". These unambiguously
    refer to ONE real drug; their facts/trials belong on the canonical row.
  * **ambiguous disjunctions** — "semaglutide or tirzepatide". Mention two drugs;
    their evidence cannot be safely attributed to either.
  * **incompletely-merged dups** — rows already ``record_status='merged'`` that
    STILL own clinical_trials / signals / entity_links (the merge repointed
    facts but missed FK tables, or predates the conflict-safe consolidator).
    Those refs are orphaned onto a soft-deleted row — invisible to the dossier,
    which resolves to the canonical id.

This is the write-time complement to ``services/dossier_kb._is_junk_competitor_name``
(read-time competitor filter). Decision per row:

  * **ABSORB** (attributable: exactly one embedded real drug, not an additive
    combo) → repoint every reference to the canonical and supersede the row.
    Reuses the hardened, conflict-safe ``EntityConsolidator._merge_drug`` so no
    FK table, signal, or text-keyed fact reference is left behind. *Conserves*
    the evidence onto the canonical (conservation-before-correctness).
  * **EXCLUDE** (ambiguous / unattributable) → reversible
    ``record_status='excluded'`` + a drop-manifest entry. No evidence is
    repointed (mis-attribution would be worse than a quarantined row).
  * **SKIP** — the canonical itself, a real additive combo, or a distinct drug.

Everything is reversible (soft-delete only) and idempotent (a second run finds
nothing to do). Dry-run is the default; a manifest is always written.

Usage:
    python -m scripts.consolidate_junk_drug_rows --name-like tirzepatide   # dry-run
    python -m scripts.consolidate_junk_drug_rows --name-like tirzepatide --apply
    python -m scripts.consolidate_junk_drug_rows --apply                   # whole spine
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# Reuse the single source of junk-name truth + the duplicate normalizer.
from scripts.clean_drug_names import _should_exclude
from scripts.consolidate_drugs import _normalize_drug_name

MANIFEST_PATH = "benchmark/reports/junk_drug_consolidation_manifest.json"

# Additive combination markers — a real multi-drug product ("X + Y", "X and Y",
# "X plus Y"). Never absorbed into a mono and never excluded: it is its own
# distinct entity (combo-safe, mirrors scripts.consolidate_drugs.combo_safe_normalize).
_ADDITIVE_COMBO_RE = re.compile(r"\(\+|\s\+\s|\bplus\b|\band\b", re.IGNORECASE)
# Disjunction — "semaglutide or tirzepatide": an ambiguous extraction naming two
# drugs, not a real entity. Quarantined, not merged.
_DISJUNCTION_RE = re.compile(r"\bor\b", re.IGNORECASE)


def _norm(name: str) -> str:
    """Normalized drug name for duplicate grouping (salt/brand/dose stripped)."""
    return _normalize_drug_name(name or "")


# Generic trial/clinical terms that exist as their own (often heavily-linked)
# 'active' drug rows but are NOT real drugs — e.g. a row literally named
# 'intervention' carrying 98 trial links (verified on prod). These must never
# count as an embedded real drug or they create phantom 'two-drug' ambiguity.
_NON_DRUG_TOKENS = {
    "intervention", "treatment", "control", "placebo", "comparator", "therapy",
    "management", "care", "standard", "usual", "lifestyle", "exercise", "diet",
    "dietary", "surgery", "surgical", "education", "counseling", "counselling",
    "monitoring", "observation", "medication", "medications", "drug", "drugs",
    "dose", "doses", "arm", "cohort", "group", "study", "supplement",
    "supplementation", "prehabilitation", "rehabilitation", "sham", "vehicle",
    "saline", "water", "routine", "clinical", "obesity",
}


def _ngrams(name: str, max_n: int = 4) -> set[str]:
    toks = re.findall(r"[a-z0-9-]+", (name or "").lower())
    grams: set[str] = set()
    for n in range(1, max_n + 1):
        for i in range(len(toks) - n + 1):
            grams.add(" ".join(toks[i : i + n]))
    return grams


def real_name_hits(name: str, real_names: set[str],
                   self_name: Optional[str] = None) -> list[str]:
    """Distinct real drug names (len >= 4) embedded as whole-word spans in name.

    n-gram lookup against the set of canonical drug names — fast and matches
    multi-word names exactly on word boundaries (no substring false-positives).
    Drops the row's OWN name (an un-excluded junk row is in ``real_names`` and
    would otherwise match itself) and any single-token generic trial term that
    is not a real drug (``_NON_DRUG_TOKENS``)."""
    self_low = (self_name or "").lower().strip()
    grams = _ngrams(name)
    out = []
    for g in grams:
        if len(g) < 4 or g not in real_names:
            continue
        if g == self_low:
            continue
        if " " not in g and g in _NON_DRUG_TOKENS:
            continue
        out.append(g)
    return sorted(set(out))


@dataclass
class Verdict:
    action: str  # "skip" | "absorb" | "exclude"
    parent_name: Optional[str] = None  # absorb: the embedded/normalized canonical name
    reason: str = ""


def classify(
    name: str,
    real_names: set[str],
    norm_name: str,
    canonical_norm_to_id: dict[str, str],
    this_id: str,
) -> Verdict:
    """Pure decision for one drug row. ``canonical_norm_to_id`` maps a normalized
    name to the id of its richest active row (the canonical survivor).

    Order matters: the additive-combo guard and the ambiguity/junk verdicts run
    BEFORE the canonical self-check, because an un-excluded ambiguous row
    ("semaglutide or tirzepatide") is registered as its own canonical and would
    otherwise short-circuit to skip."""
    # Protect real additive combos first — never absorbed or excluded.
    if _ADDITIVE_COMBO_RE.search(name or ""):
        return Verdict("skip", reason="additive_combo")

    hits = real_name_hits(name, real_names, self_name=name)

    if _should_exclude(name):
        if len(hits) == 1:
            return Verdict("absorb", parent_name=hits[0], reason="junk_fragment")
        return Verdict("exclude", reason="junk_unattributable")

    # An ambiguous "drugA or drugB" names two real drugs — quarantine, never merge.
    if len(hits) >= 2 and _DISJUNCTION_RE.search(name or ""):
        return Verdict("exclude", reason="ambiguous_disjunction")

    # The richest active row for its norm is the canonical — never touched.
    if canonical_norm_to_id.get(norm_name) == this_id:
        return Verdict("skip", reason="canonical")

    # A plain duplicate (same normalized name as the canonical) — includes the
    # incompletely-merged rows; re-merging completes their reference repointing.
    parent_id = canonical_norm_to_id.get(norm_name)
    if parent_id and parent_id != this_id:
        return Verdict("absorb", parent_name=norm_name, reason="true_dup")

    return Verdict("skip", reason="keep")


# ──────────────────────────────────────────────────────────────────────────
# DB orchestration
# ──────────────────────────────────────────────────────────────────────────

@dataclass
class RunStats:
    absorbed: int = 0
    excluded: int = 0
    skipped: int = 0
    plan: list = field(default_factory=list)


# Tables whose remaining rows mean a soft-deleted drug is NOT yet fully absorbed.
_REF_TABLES = ("clinical_trials", "market_events", "adverse_events",
               "drug_labels", "pubmed_articles", "pmc_articles")


def _owns_refs(db, drug_id: str) -> bool:
    """True if the row still owns evidence references — facts, signals,
    entity_links, or any FK table. Used to make absorb idempotent: a cleanly
    absorbed (superseded, zero-ref) row is a no-op on re-run."""
    q = [("SELECT count(*) c FROM facts WHERE subject_entity_type='drug' "
          "AND subject_entity_id=%s AND superseded_by IS NULL", [drug_id]),
         ("SELECT count(*) c FROM signals WHERE primary_entity_type='drug' "
          "AND primary_entity_id=%s", [drug_id]),
         ("SELECT count(*) c FROM entity_links "
          "WHERE source_entity_id=%s OR target_entity_id=%s", [drug_id, drug_id])]
    for sql, p in q:
        if (db.fetch_one(sql, p) or {}).get("c"):
            return True
    for t in _REF_TABLES:
        try:
            if (db.fetch_one(f"SELECT count(*) c FROM {t} WHERE drug_id=%s",
                             [drug_id]) or {}).get("c"):
                return True
        except Exception:
            continue
    return False


def _build_real_names(db) -> set[str]:
    """Lowercased generic_names of active, non-junk drug rows (the canonical
    vocabulary used for embedded-drug detection)."""
    rows = db.fetch_all(
        "SELECT generic_name FROM drugs "
        "WHERE record_status IS DISTINCT FROM 'superseded' "
        "  AND record_status IS DISTINCT FROM 'merged' "
        "  AND record_status IS DISTINCT FROM 'excluded' "
        "  AND generic_name IS NOT NULL AND generic_name <> ''"
    )
    out: set[str] = set()
    for r in rows:
        nm = r["generic_name"]
        if not _should_exclude(nm):
            out.add(nm.lower())
    return out


def run(db, name_like: Optional[str] = None, dry_run: bool = True) -> RunStats:
    from integration.entity_consolidator import EntityConsolidator

    stats = RunStats()
    consolidator = EntityConsolidator(db, dry_run=dry_run, rank_by_richness=True)
    real_names = _build_real_names(db)

    # Candidate rows: any status (so we also complete already-'merged' rows that
    # still own references), optionally scoped by name.
    sql = ("SELECT id, generic_name, brand_name, record_status "
           "FROM drugs WHERE generic_name IS NOT NULL AND generic_name <> ''")
    params: list = []
    if name_like:
        sql += " AND LOWER(generic_name) LIKE %s"
        params.append(f"%{name_like.lower()}%")
    candidates = db.fetch_all(sql, params)

    # Canonical (richest active non-junk row) per normalized name, restricted to
    # the norms present in the candidate set.
    canonical_norm_to_id: dict[str, str] = {}
    by_norm: dict[str, list[dict]] = {}
    for c in candidates:
        nm = c["generic_name"]
        status = c.get("record_status")
        is_active = status not in ("superseded", "merged", "excluded")
        if is_active and not _should_exclude(nm):
            by_norm.setdefault(_norm(nm), []).append(c)
    for norm, rows in by_norm.items():
        if not norm:
            continue
        richest = max(rows, key=lambda r: consolidator._drug_richness(str(r["id"])))
        canonical_norm_to_id[norm] = str(richest["id"])

    manifest: list[dict] = []
    for c in candidates:
        cid = str(c["id"])
        name = c["generic_name"]
        v = classify(name, real_names, _norm(name), canonical_norm_to_id, cid)

        if v.action == "skip":
            stats.skipped += 1
            continue

        if v.action == "absorb":
            parent_id = canonical_norm_to_id.get(_norm(v.parent_name))
            if not parent_id or parent_id == cid:
                stats.skipped += 1
                continue
            # Idempotency: a row already soft-deleted with no remaining refs has
            # been fully absorbed on a prior run — nothing left to repoint.
            if c.get("record_status") in ("superseded", "merged") and not _owns_refs(db, cid):
                stats.skipped += 1
                continue
            entry = {"id": cid, "name": name, "action": "absorb",
                     "into": parent_id, "reason": v.reason,
                     "prev_status": c.get("record_status")}
            stats.plan.append(entry)
            manifest.append(entry)
            stats.absorbed += 1
            if not dry_run:
                canonical = db.fetch_one("SELECT * FROM drugs WHERE id = %s", [parent_id])
                dup = db.fetch_one("SELECT * FROM drugs WHERE id = %s", [cid])
                consolidator._merge_drug(canonical, dup)
            logger.info("ABSORB %s %r -> %s (%s)", cid[:8], name, parent_id[:8], v.reason)
            continue

        if v.action == "exclude":
            # Idempotency: already quarantined on a prior run.
            if c.get("record_status") == "excluded":
                stats.skipped += 1
                continue
            entry = {"id": cid, "name": name, "action": "exclude",
                     "reason": v.reason, "prev_status": c.get("record_status")}
            stats.plan.append(entry)
            manifest.append(entry)
            stats.excluded += 1
            if not dry_run:
                _exclude_row(db, cid, name, v.reason)
            logger.info("EXCLUDE %s %r (%s)", cid[:8], name, v.reason)

    _write_manifest(manifest, name_like, dry_run, stats)
    return stats


def _exclude_row(db, drug_id: str, name: str, reason: str) -> None:
    """Reversible quarantine: mark excluded + audit. No evidence is repointed."""
    with db.transaction():
        db.execute(
            "UPDATE drugs SET record_status = 'excluded' WHERE id = %s", [drug_id]
        )
        try:
            db.execute(
                "INSERT INTO data_change_log "
                "(entity_type, entity_id, change_type, changed_fields, changed_at) "
                "VALUES ('drug', %s, 'exclude_junk_row', %s, %s)",
                [drug_id, ["record_status", f"reason:{reason}", f"name:{name}"],
                 datetime.now(timezone.utc)],
            )
        except Exception:
            logger.debug("data_change_log insert skipped", exc_info=True)


def _write_manifest(manifest: list[dict], name_like, dry_run: bool,
                    stats: RunStats) -> None:
    try:
        os.makedirs(os.path.dirname(MANIFEST_PATH), exist_ok=True)
        with open(MANIFEST_PATH, "w", encoding="utf-8") as fh:
            json.dump({
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "name_like": name_like,
                "dry_run": dry_run,
                "absorbed": stats.absorbed,
                "excluded": stats.excluded,
                "skipped": stats.skipped,
                "entries": manifest,
            }, fh, indent=2)
        logger.info("manifest -> %s", MANIFEST_PATH)
    except Exception:
        logger.warning("could not write manifest", exc_info=True)


def main():
    parser = argparse.ArgumentParser(description="Consolidate junk/dup drug-spine rows")
    parser.add_argument("--name-like", help="restrict to drugs whose generic_name LIKE %%this%%")
    parser.add_argument("--apply", action="store_true", help="write changes (default: dry-run)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    from db import Database
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        from config import config
        dsn = config.db.dsn
    db = Database(dsn)
    db.connect()
    try:
        stats = run(db, name_like=args.name_like, dry_run=not args.apply)
    finally:
        db.close()

    print("\n=== Junk/Dup Drug Consolidation ===")
    print(f"  absorbed: {stats.absorbed}")
    print(f"  excluded: {stats.excluded}")
    print(f"  skipped:  {stats.skipped}")
    for e in stats.plan:
        if e["action"] == "absorb":
            print(f"   ABSORB  {e['id'][:8]} {e['name']!r} -> {e['into'][:8]} ({e['reason']})")
        else:
            print(f"   EXCLUDE {e['id'][:8]} {e['name']!r} ({e['reason']})")
    if not args.apply:
        print("  (dry run — no changes written)")


if __name__ == "__main__":
    main()
