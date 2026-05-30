"""Backfill fact_class on existing facts rows (Z1).

Idempotent — safe to re-run. Walks the facts table, derives fact_class
from the predicate via the same map fact_ingest uses, and UPDATEs in place.
Existing rows default to 'corporate' from the migration; this refines.

Usage:
    python scripts/backfill_fact_class.py
    python scripts/backfill_fact_class.py --limit 500
    python scripts/backfill_fact_class.py --predicate safety_signal
"""

from __future__ import annotations

import argparse
import logging
from collections import Counter

from config import config
from db import Database
from services.fact_ingest import classify_predicate

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


_UPDATE_SQL = """
    UPDATE facts SET fact_class = %s
     WHERE id = %s AND fact_class IS DISTINCT FROM %s
"""

_FETCH_SQL = """
    SELECT id, predicate, fact_class
      FROM facts
     {where}
     ORDER BY created_at
     {limit}
"""


def main() -> None:
    ap = argparse.ArgumentParser(description="Backfill fact_class from predicate")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--predicate", type=str, default=None,
                    help="restrict to facts matching this predicate")
    args = ap.parse_args()

    db = Database(config.db.dsn)
    clauses: list[str] = []
    params: list = []
    if args.predicate:
        clauses.append("predicate = %s")
        params.append(args.predicate)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    limit_sql = ""
    if args.limit is not None:
        limit_sql = f"LIMIT {int(args.limit)}"
    sql = _FETCH_SQL.format(where=where, limit=limit_sql)

    rows = db.fetch_all(sql, params)
    counts: Counter = Counter()
    for r in rows:
        desired = classify_predicate(r.get("predicate"))
        if r.get("fact_class") != desired:
            db.execute(_UPDATE_SQL, [desired, r["id"], desired])
            counts[desired] += 1
        else:
            counts["unchanged"] += 1

    print(f"scanned={len(rows)} "
          + " ".join(f"{k}={v}" for k, v in sorted(counts.items())))


if __name__ == "__main__":
    main()
