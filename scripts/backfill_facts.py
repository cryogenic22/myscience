"""Backfill facts from existing market_events (A1, spine convergence).

Idempotent — safe to re-run. Reads DATABASE_URL (or config DSN).

Usage:
    python scripts/backfill_facts.py                 # all events
    python scripts/backfill_facts.py --limit 200
    python scripts/backfill_facts.py --since-days 30 --event-types approval pricing
"""

from __future__ import annotations

import argparse
import logging

from config import config
from db import Database
from services.fact_ingest import backfill_facts_from_events

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


def main() -> None:
    ap = argparse.ArgumentParser(description="Backfill facts from market_events")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--since-days", type=int, default=None)
    ap.add_argument("--event-types", nargs="*", default=None)
    args = ap.parse_args()

    db = Database(config.db.dsn)
    stats = backfill_facts_from_events(
        db,
        limit=args.limit,
        since_days=args.since_days,
        event_types=args.event_types,
    )
    print(
        f"scanned={stats.scanned} asserted={stats.asserted} "
        f"skipped_existing={stats.skipped_existing} "
        f"skipped_no_subject={stats.skipped_no_subject}"
    )


if __name__ == "__main__":
    main()
