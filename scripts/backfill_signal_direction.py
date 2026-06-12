"""Backfill signals.direction (polarity) from each signal's source-fact predicate.

`direction` (positive|negative|neutral) is a general sensing enrichment — it
lets calibration treat a rival's setback as evidence AGAINST a competitive-
pressure scenario (Loop 1 / OQ3), and is available to chat / the intelligence
feed / future launch use-cases. New signals get it at mint time
(`fact_signals.build_signal_row`); this backfills the existing rows.

Derivation reuses the single source of truth `fact_signals.signal_direction`,
joining signals → signal_facts → facts to recover the predicate + object_value.
Reversible (only writes where direction IS NULL; re-runnable), dry-run default.

Usage:
    python -m scripts.backfill_signal_direction            # dry-run
    python -m scripts.backfill_signal_direction --apply
"""

from __future__ import annotations

import argparse
import json
import logging
import os

from db import Database
from services.fact_signals import signal_direction

logger = logging.getLogger(__name__)

_SQL = """
    SELECT s.id AS signal_id, f.predicate, f.object_value
      FROM signals s
      JOIN signal_facts sf ON sf.signal_id = s.id
      JOIN facts f ON f.id = sf.fact_id
     WHERE s.direction IS NULL
"""


def run(db, *, apply: bool = False) -> dict:
    rows = db.fetch_all(_SQL) or []
    counts: dict[str, int] = {}
    updated = 0
    for r in rows:
        obj = r.get("object_value") or {}
        if isinstance(obj, str):
            try:
                obj = json.loads(obj)
            except (ValueError, TypeError):
                obj = {}
        d = signal_direction(r.get("predicate"), obj)
        counts[d] = counts.get(d, 0) + 1
        if apply:
            db.execute("UPDATE signals SET direction = %s WHERE id = %s AND direction IS NULL",
                       [d, r["signal_id"]])
            updated += 1
    return {"candidates": len(rows), "updated": updated if apply else 0,
            "by_direction": counts, "applied": apply}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        from config import config
        dsn = config.db.dsn
    db = Database(dsn)
    db.connect()
    try:
        stats = run(db, apply=args.apply)
    finally:
        db.close()
    print("=== signal direction backfill ===")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    if not args.apply:
        print("  (dry run — no writes)")


if __name__ == "__main__":
    main()
