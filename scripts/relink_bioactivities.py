#!/usr/bin/env python
"""Pure-DB relink of bioactivities → the drug spine, then re-run BioactivityEmitter.

Context. The ChEMBL connector + ``_store_bioactivity`` link ``drug_id`` at ingest
(D3) via the entity resolver, so NEW activity rows attach to the spine. But rows
ingested before that fix carry ``drug_id = NULL`` and could only be repaired by
re-hitting the ChEMBL API — the table never persisted the *molecule* identifier
(only ``chembl_activity_id``, the assay-row id). Migration 089 adds
``bioactivities.molecule_chembl_id``; with it, the compound → drug mapping is a
pure-DB join:

    bioactivities.molecule_chembl_id  ->  drugs.chembl_id  ->  drug_id

``drugs.chembl_id`` is uniquely indexed (migration 038) and we exclude
merged/superseded dup rows so the link lands on the canonical drug (the same
ranking the resolver uses).

Conservation #2 (no silent loss). The backfill is ADDITIVE — it only fills NULL
``drug_id`` and never overwrites an existing link. A molecule that is not in our
drug spine (an off-target assay compound) is COUNTED as ``unresolved`` and left
untouched (``drug_id`` stays NULL); it is never dropped or coerced. The pasted
``{candidates, matched, unresolved}`` is the drop-manifest.

Usage:
    DATABASE_URL=... python -m scripts.relink_bioactivities [--limit N] [--dry-run]
    DATABASE_URL=... python -m scripts.relink_bioactivities --emit   # also run emitter
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# Canonical drug rows only — match the resolver / DR-emitters, which exclude
# consolidated-away dups so a relink lands on the rich canonical row.
_DRUG_SPINE_SQL = """
    SELECT id AS drug_id, chembl_id
      FROM drugs
     WHERE chembl_id IS NOT NULL
       AND COALESCE(record_status, '') NOT IN ('merged', 'superseded', 'excluded')
"""

_NULL_ROWS_SQL = """
    SELECT id, molecule_chembl_id
      FROM bioactivities
     WHERE drug_id IS NULL
       AND molecule_chembl_id IS NOT NULL
     {limit_clause}
"""

# Additive: WHERE drug_id IS NULL guard makes a re-run a no-op (idempotent) and
# guarantees we never clobber an already-resolved link.
_UPDATE_SQL = """
    UPDATE bioactivities
       SET drug_id = %s
     WHERE id = %s
       AND drug_id IS NULL
"""


def _build_chembl_index(spine_rows: list[dict]) -> dict[str, str]:
    """lower(chembl_id) -> drug_id. drugs.chembl_id is uniquely indexed so a
    collision is not expected; if one occurs we keep the first deterministically."""
    index: dict[str, str] = {}
    for r in spine_rows:
        cid = (r.get("chembl_id") or "").strip().lower()
        if cid and cid not in index:
            index[cid] = str(r["drug_id"])
    return index


def relink(db, limit: int | None = None, dry_run: bool = False) -> dict:
    """Fill NULL bioactivities.drug_id from molecule_chembl_id → drugs.chembl_id.

    Returns {candidates, matched, unresolved, dry_run}. ``unresolved`` = rows
    whose molecule is not in our drug spine (counted, not dropped)."""
    index = _build_chembl_index(db.fetch_all(_DRUG_SPINE_SQL))
    limit_sql = f"LIMIT {int(limit)}" if limit else ""
    rows = db.fetch_all(_NULL_ROWS_SQL.format(limit_clause=limit_sql))

    matched = 0
    unresolved = 0
    for row in rows:
        mol = (row.get("molecule_chembl_id") or "").strip().lower()
        drug_id = index.get(mol)
        if not drug_id:
            unresolved += 1
            continue
        matched += 1
        if not dry_run:
            db.execute(_UPDATE_SQL, [drug_id, row["id"]])
    return {
        "candidates": len(rows),
        "matched": matched,
        "unresolved": unresolved,
        "dry_run": dry_run,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--emit", action="store_true",
                    help="after relinking, run BioactivityEmitter over the spine")
    ap.add_argument("db_url", nargs="?", default=os.environ.get("DATABASE_URL"))
    args = ap.parse_args()
    if not args.db_url:
        sys.exit("Pass a DB url or set DATABASE_URL.")

    from db import Database

    db = Database(args.db_url)
    db.connect()
    try:
        result = relink(db, limit=args.limit, dry_run=args.dry_run)
        print("relink:", result)
        if args.emit and not args.dry_run:
            from services.fact_emitters.base import run_emitter
            from services.fact_emitters.mechanisms import BioactivityEmitter

            stats = run_emitter(db, BioactivityEmitter())
            print("emit:", {
                "scanned": stats.scanned,
                "asserted": stats.asserted,
                "skipped_existing": stats.skipped_existing,
                "evidence_written": stats.evidence_written,
            })
    finally:
        db.close()


if __name__ == "__main__":
    main()
