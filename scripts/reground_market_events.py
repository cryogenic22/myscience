"""D2 — reground orphaned market_events to the entity spine (additive).

Two passes, both idempotent (only touch still-NULL-primary rows):

  1. derive_primary_from_drug_id — events that already carry a drug_id (the
     ingest resolver linked the drug but the old writer never stamped the
     primary_entity_* spine column). Set-based; grounds the bulk in one
     statement. Gated on evidence, not the (mislabelled) record_status.
  2. backfill_orphaned_events — high-value events with NO drug_id whose entity
     is named only in the free-text description (approvals, trial readouts,
     M&A…). Deterministic longest-whole-word match against the drugs/companies/
     alias vocabulary. Events whose entity is absent from the spine stay
     orphaned and are logged (the resolvable ceiling — many news items are
     genuinely entity-less macro/sector pieces, a supervised NER/auto-create
     pass is the follow-up).

Reads DATABASE_URL (config.db.dsn). Additive: never deletes, never repoints a
live link. Pair with scripts/backfill_facts.py to lift the newly-grounded
events into the ledger.

    python -m scripts.reground_market_events                 # both passes, all rows
    python -m scripts.reground_market_events --text-limit 5000
"""
from __future__ import annotations

import argparse
import logging

from config import config
from db import Database
from services.event_entity_resolver import (
    HIGH_VALUE_EVENT_TYPES,
    backfill_orphaned_events,
    derive_primary_from_drug_id,
    load_vocabulary,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("reground_market_events")


def _null_primary_count(db) -> int:
    row = db.fetch_one(
        "SELECT count(*) AS c FROM market_events WHERE primary_entity_id IS NULL"
    )
    return int(row["c"]) if row else -1


def reground(db, *, derive_limit=None, text_limit: int = 5000,
             text_pass: bool = True) -> dict:
    """Run both reground passes; return a stats dict with before/after counts."""
    before = _null_primary_count(db)
    logger.info("NULL primary_entity_id before: %d", before)

    derived = derive_primary_from_drug_id(db, limit=derive_limit)
    logger.info("pass 1 (drug_id derive): grounded=%d", derived["grounded"])

    text_stats = {"scanned": 0, "resolved": 0, "by_type": {}}
    if text_pass:
        vocab = load_vocabulary(db)
        text_stats = backfill_orphaned_events(db, limit=text_limit, vocab=vocab)
        logger.info(
            "pass 2 (free-text): scanned=%d resolved=%d by_type=%s",
            text_stats["scanned"], text_stats["resolved"], text_stats["by_type"],
        )

    after = _null_primary_count(db)
    logger.info("NULL primary_entity_id after: %d (Δ %d)", after, before - after)
    return {
        "null_primary_before": before,
        "null_primary_after": after,
        "derived_from_drug_id": derived["grounded"],
        "resolved_from_text": text_stats["resolved"],
        "text_scanned": text_stats["scanned"],
        "text_by_type": text_stats["by_type"],
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Reground orphaned market_events (D2)")
    ap.add_argument("--derive-limit", type=int, default=None,
                    help="bound the drug_id-derive pass (default: all)")
    ap.add_argument("--text-limit", type=int, default=5000,
                    help="bound the free-text pass (default: 5000)")
    ap.add_argument("--no-text", action="store_true",
                    help="skip the free-text pass (drug_id derive only)")
    ap.add_argument("--event-types", nargs="*", default=list(HIGH_VALUE_EVENT_TYPES))
    args = ap.parse_args()

    db = Database(config.db.dsn)
    db.connect()
    try:
        stats = reground(
            db, derive_limit=args.derive_limit, text_limit=args.text_limit,
            text_pass=not args.no_text,
        )
    finally:
        db.close()
    print(stats)


if __name__ == "__main__":
    main()
