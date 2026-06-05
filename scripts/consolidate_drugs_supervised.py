"""D2 (drug-side) — supervised, reversible drug-duplicate consolidation.

Reuses ``EntityConsolidator(rank_by_richness=True,
drug_name_normalizer=combo_safe_normalize)`` (the A6 precedent): canonical =
richest row (matches the dossier resolver), soft-delete duplicates
(record_status='superseded'), and complete repoint of the text-keyed spine refs
the generic FK loop misses — facts.subject_entity_id, signals.primary_entity_id,
entity_links (set-based) — plus the FK tables (now incl. bioactivities).

After the merge, repoint the NULL-primary recall events onto their (now
canonical) drug's primary_entity_id, then VERIFY zero orphans across every spine
table: nothing points at a superseded drug row.

Usage:
    python scripts/consolidate_drugs_supervised.py "<db url>" --dry-run
    python scripts/consolidate_drugs_supervised.py "<db url>"
    python scripts/consolidate_drugs_supervised.py "<db url>" --verify
"""

from __future__ import annotations

import argparse
import logging
import sys

from integration.entity_consolidator import EntityConsolidator
from scripts.consolidate_drugs import combo_safe_normalize

logger = logging.getLogger(__name__)


def drug_orphans(db) -> dict[str, int]:
    """Spine refs pointing at a superseded DRUG row — must be 0 after a merge."""
    out: dict[str, int] = {}
    out["facts.subject_entity_id"] = (db.fetch_one(
        "SELECT count(*) c FROM facts f JOIN drugs d ON d.id::text = f.subject_entity_id "
        "WHERE f.subject_entity_type = 'drug' AND f.superseded_by IS NULL "
        "  AND d.record_status = 'superseded'"
    ) or {}).get("c", 0)
    out["signals.primary_entity_id"] = (db.fetch_one(
        "SELECT count(*) c FROM signals s JOIN drugs d ON d.id::text = s.primary_entity_id "
        "WHERE s.primary_entity_type = 'drug' AND d.record_status = 'superseded'"
    ) or {}).get("c", 0)
    out["entity_links.drug"] = (db.fetch_one(
        "SELECT count(*) c FROM entity_links el JOIN drugs d "
        "  ON d.id::text IN (el.source_entity_id, el.target_entity_id) "
        "WHERE d.record_status = 'superseded'"
    ) or {}).get("c", 0)
    # FK tables: any drug_id still pointing at a superseded drug
    for table in ("clinical_trials", "market_events", "pubmed_articles",
                  "adverse_events", "drug_labels", "regulatory_milestones",
                  "bioactivities", "pmc_articles"):
        try:
            out[f"{table}.drug_id"] = (db.fetch_one(
                f"SELECT count(*) c FROM {table} t JOIN drugs d ON d.id = t.drug_id "
                f"WHERE d.record_status = 'superseded'"
            ) or {}).get("c", 0)
        except Exception:
            db_rollback(db)
    return out


def db_rollback(db) -> None:
    try:
        db.conn.rollback()
    except Exception:
        pass


def reground_null_primary_events(db) -> int:
    """Set primary_entity_id on NULL-primary market_events that carry a drug_id
    (now pointing at a canonical, post-merge drug). Additive, idempotent."""
    db.execute(
        "UPDATE market_events me SET primary_entity_id = me.drug_id::text, "
        "       primary_entity_type = 'drug' "
        "WHERE me.primary_entity_id IS NULL AND me.drug_id IS NOT NULL "
        "  AND me.record_status IS DISTINCT FROM 'superseded'"
    )
    return (db.fetch_one(
        "SELECT count(*) c FROM market_events "
        "WHERE primary_entity_id IS NOT NULL AND drug_id IS NOT NULL "
        "  AND record_status IS DISTINCT FROM 'superseded'"
    ) or {}).get("c", 0)


def _connect(url: str):
    from db import Database
    db = Database(url)
    db.connect()
    return db


def main() -> None:
    ap = argparse.ArgumentParser(description="Supervised drug consolidation (D2)")
    ap.add_argument("db_url", nargs="?")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--no-reground", action="store_true",
                    help="skip the NULL-primary recall-event reground step")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    import os
    url = args.db_url or os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("Pass a postgres url or set DATABASE_URL")
    db = _connect(url)
    try:
        if args.verify:
            print("drug orphans:", drug_orphans(db))
            return
        c = EntityConsolidator(
            db, rank_by_richness=True,
            drug_name_normalizer=combo_safe_normalize, dry_run=args.dry_run,
        )
        res = c.consolidate_drugs()
        print("=== drug consolidation ===")
        print(f"  groups_found: {res['groups_found']}")
        print(f"  records_merged: {res['records_merged']}")
        print(f"  skipped: {res['skipped']}")
        if args.dry_run:
            for p in res.get("plan", [])[:25]:
                print(f"    {p['name']} -> {p['canonical_name']} "
                      f"({len(p['merge'])} dups)")
            print("  (dry run — no writes)")
            return
        if not args.no_reground:
            grounded = reground_null_primary_events(db)
            print(f"  market_events grounded (primary_entity_id set): {grounded}")
        print("drug orphans after:", drug_orphans(db))
    finally:
        db.close()


if __name__ == "__main__":
    main()
