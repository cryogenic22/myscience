#!/usr/bin/env python
"""Backfill drug_id on adverse_events / drug_labels rows orphaned before the
combo-component resolver fallback existed (Loop 2: resolve-at-ingest hardening).

Resolution-at-ingest already populates drug_id for new rows; this recovers the
legacy NULL-drug_id rows (concentrated on combination drugs like Entresto whose
mono component name "sacubitril" could not be trigram-matched to the combo row).

For each NULL-drug_id row it runs EntityResolver.resolve_drug_mention (DB-only:
alias -> fuzzy -> combo-component) and, on a hit, sets
    drug_id = COALESCE(<resolved>, drug_id)
so no existing link is ever overwritten. Idempotent (only touches NULL rows) and
conservation-safe (a row that still does not resolve is left NULL and COUNTED,
never dropped).

Usage:
    DATABASE_URL=... python scripts/backfill_orphan_drug_links.py [--apply]

Default is a DRY RUN (reports what would change). Pass --apply to write.
Read-only by default; safe to inspect against prod first.
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import Counter

import psycopg2
import psycopg2.extras

from config import config
from connectors.base import SourceType
from db import Database
from integration.entity_resolver import EntityResolver

# (table, source_type for alias lookups)
TARGETS = [
    ("adverse_events", SourceType.OPENFDA_FAERS),
    ("drug_labels", SourceType.OPENFDA_LABELS),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    ap.add_argument("url", nargs="?", help="postgres url (else DATABASE_URL)")
    args = ap.parse_args()

    url = args.url or os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("Set DATABASE_URL or pass a postgres url as argv[1].")

    db = Database(url)
    db.connect()
    # DB-only cascade: no OpenAI client (embedding/LLM strategies skipped).
    resolver = EntityResolver(db=db, config=config, openai_client=None)

    grand = Counter()
    for table, source_type in TARGETS:
        rows = db.fetch_all(
            f"""
            SELECT id, drug_name
            FROM {table}
            WHERE drug_id IS NULL
              AND drug_name IS NOT NULL
              AND (record_status IS NULL OR record_status = 'active')
            """
        )
        resolved = 0
        unresolved_names: Counter = Counter()
        for row in rows:
            name = (row.get("drug_name") or "").strip()
            link = resolver.resolve_drug_mention(name, source_type) if name else None
            if link:
                resolved += 1
                if args.apply:
                    db.execute(
                        f"UPDATE {table} SET drug_id = COALESCE(%s, drug_id), "
                        f"updated_at = NOW() WHERE id = %s AND drug_id IS NULL",
                        [link.entity_id, str(row["id"])],
                    )
            else:
                unresolved_names[name.lower()] += 1

        grand["orphans"] += len(rows)
        grand["resolved"] += resolved
        grand["still_null"] += len(rows) - resolved
        print(f"\n=== {table} ===")
        print(f"  orphans (NULL drug_id): {len(rows)}")
        print(f"  resolved:               {resolved}")
        print(f"  still unresolved:       {len(rows) - resolved}")
        if unresolved_names:
            print("  unresolved drug_name breakdown:")
            for nm, n in unresolved_names.most_common(10):
                print(f"    {n:>4}  {nm}")

    mode = "APPLIED" if args.apply else "DRY RUN (no writes; pass --apply)"
    print(f"\n[{mode}] totals: {dict(grand)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
