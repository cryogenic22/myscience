"""PB-H19 — backfill entity refs on orphaned high-value market_events.

Resolves the drug/company named in each orphaned event's description against
the existing entity spine and sets primary_entity_* (+ drug_id) so the
events→facts backfill (scripts/backfill_facts.py) then lifts them into the
ledger. Idempotent — only touches still-orphaned rows.

Reads DATABASE_URL. Deterministic name-matching (no LLM); events whose entity
is absent from the spine stay orphaned (a supervised auto-create/NER pass is
the follow-up). Typical pairing:

    python -m scripts.backfill_event_entities --limit 2000
    python -m scripts.backfill_facts --event-types approval trial_readout ma_deal \
        regulatory_setback supply_disruption pricing safety_signal patent_ip
"""
from __future__ import annotations

import argparse
import logging

from config import config
from db import Database
from services.event_entity_resolver import (
    HIGH_VALUE_EVENT_TYPES,
    backfill_orphaned_events,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


def main() -> None:
    ap = argparse.ArgumentParser(description="Backfill entity refs on orphaned events")
    ap.add_argument("--limit", type=int, default=2000)
    ap.add_argument("--event-types", nargs="*", default=list(HIGH_VALUE_EVENT_TYPES))
    args = ap.parse_args()

    db = Database(config.db.dsn)
    stats = backfill_orphaned_events(
        db, event_types=tuple(args.event_types), limit=args.limit
    )
    logging.info(
        "event-entity backfill: scanned=%s resolved=%s by_type=%s",
        stats["scanned"], stats["resolved"], stats["by_type"],
    )
    print(stats)


if __name__ == "__main__":
    main()
