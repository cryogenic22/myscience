"""One-shot backfill: promote market_events → candidate signals.

Usage:
    python -m scripts.promote_signals            # promote all unsignalled events
    python -m scripts.promote_signals --limit 100
    python -m scripts.promote_signals --since-days 30
    python -m scripts.promote_signals --dry-run   # count only, no inserts

Idempotent — safe to re-run; already-signalled events are skipped.
"""

from __future__ import annotations

import argparse
import logging

from config import config
from db import Database
from services.signal_promoter import (
    promote_events,
    build_signal_row,
    HIGH_SIGNIFICANCE_EVENT_TYPES,
)

logger = logging.getLogger(__name__)


def run(
    *,
    limit: int = 100000,
    since_days: int | None = None,
    event_types: list[str] | None = None,
    dry_run: bool = False,
) -> dict:
    db = Database(config.db.dsn)
    db.connect()
    try:
        if dry_run:
            existing_rows = db.fetch_all("SELECT event_id FROM signals", [])
            existing = {str(r["event_id"]) for r in existing_rows if r.get("event_id")}
            where = "WHERE event_type = ANY(%s)" if event_types else ""
            params: list = [list(event_types)] if event_types else []
            params.append(limit)
            events = db.fetch_all(
                f"""SELECT id, event_type, description, source_tier, trust_score,
                           primary_entity_type, primary_entity_id, primary_entity_name,
                           drug_id, event_date
                      FROM market_events {where}
                     ORDER BY event_date DESC
                     LIMIT %s""",
                params,
            )
            would_promote = would_ship = would_skip_existing = would_skip_no_entity = 0
            for e in events:
                if str(e["id"]) in existing:
                    would_skip_existing += 1
                    continue
                row = build_signal_row(e)
                if row is None:
                    would_skip_no_entity += 1
                else:
                    would_promote += 1
                    if row["status"] == "shipped":
                        would_ship += 1
            summary = {
                "dry_run": True,
                "scanned": len(events),
                "would_promote": would_promote,
                "would_ship": would_ship,
                "would_skip_existing": would_skip_existing,
                "would_skip_no_entity": would_skip_no_entity,
            }
        else:
            res = promote_events(db, limit=limit, since_days=since_days, event_types=event_types)
            summary = {
                "scanned": res.scanned,
                "promoted": res.promoted,
                "skipped_existing": res.skipped_existing,
                "skipped_no_entity": res.skipped_no_entity,
            }
        print(summary)
        return summary
    finally:
        db.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Promote market_events into signals.")
    ap.add_argument("--limit", type=int, default=100000)
    ap.add_argument("--since-days", type=int, default=None)
    ap.add_argument("--event-types", type=str, default=None,
                    help="comma-separated event types to target")
    ap.add_argument("--high-significance", action="store_true",
                    help="target high-significance event types (approval, trial_readout, ma_deal, ...)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    event_types = None
    if args.high_significance:
        event_types = list(HIGH_SIGNIFICANCE_EVENT_TYPES)
    elif args.event_types:
        event_types = [t.strip() for t in args.event_types.split(",") if t.strip()]
    run(limit=args.limit, since_days=args.since_days, event_types=event_types, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
