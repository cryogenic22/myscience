"""Backfill fact governance — compute trust metadata for existing ledger facts.

Migration 090 adds the governance columns; NEW facts get them at write time via
``services.facts_ledger.assert_fact``. This script fills the dimensions for facts
that predate 090 (``trust_score IS NULL``).

Properties:
  * BOUNDED + idempotent — only scores facts whose ``trust_score IS NULL``, in
    batches; safe to re-run / resume.
  * API-free — no LLM, no network beyond the DB. Pure ``score_fact`` per row.
  * resolver_confidence comes from ``resolution_audit`` (the highest-confidence
    accepted resolution for the subject) when available, else ``score_fact``'s
    default.
  * NEVER overwrites a ``human_approved`` review_status — a human's judgement is
    authoritative. The numeric dimensions are still refreshed for those rows, but
    review_status is preserved via SQL COALESCE-on-human.

Usage:
    DATABASE_URL=... python -m scripts.backfill_fact_governance [--limit N] [--dry-run]
"""
from __future__ import annotations

import argparse
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from services.fact_governance import score_fact

logger = logging.getLogger(__name__)

# Un-scored facts only (idempotent). Bounded by LIMIT in the runner.
_UNSCORED_SQL = """
    SELECT id, fact_class, created_by, confidence,
           subject_entity_type, subject_entity_id,
           valid_from, created_at, object_value, review_status
      FROM facts
     WHERE trust_score IS NULL
     ORDER BY created_at ASC NULLS LAST
     LIMIT %s
"""

# Highest-confidence accepted resolution for a subject (best estimate that the
# (type, id) the fact is keyed by is the right entity).
_RESOLVER_CONF_SQL = """
    SELECT confidence
      FROM resolution_audit
     WHERE resolved_entity_id = %s
       AND accepted = TRUE
     ORDER BY confidence DESC NULLS LAST
     LIMIT 1
"""

# Preserve human_approved; otherwise apply the computed review_status. The CASE
# makes the no-overwrite rule structural (not just application discipline).
_UPDATE_SQL = """
    UPDATE facts
       SET source_reliability    = %(source_reliability)s,
           extraction_confidence = %(extraction_confidence)s,
           resolver_confidence   = %(resolver_confidence)s,
           freshness_at          = %(freshness_at)s,
           schema_version        = %(schema_version)s,
           trust_score           = %(trust_score)s,
           review_status         = CASE WHEN review_status = 'human_approved'
                                        THEN 'human_approved'
                                        ELSE %(review_status)s END
     WHERE id = %(id)s
"""


def resolver_conf_for_subject(db, subject_entity_type: str,
                              subject_entity_id: str) -> Optional[float]:
    """Best-known resolution confidence for the subject, or None if no
    resolution_audit row exists (caller lets score_fact apply its default)."""
    try:
        row = db.fetch_one(_RESOLVER_CONF_SQL, [subject_entity_id])
    except Exception:
        logger.exception("resolver-conf lookup failed for %s", subject_entity_id)
        return None
    if row and row.get("confidence") is not None:
        try:
            return float(row["confidence"])
        except (TypeError, ValueError):
            return None
    return None


def backfill_governance(db, *, batch: int = 1000, max_rows: Optional[int] = None,
                        now: Optional[datetime] = None,
                        dry_run: bool = False) -> dict:
    """Score every un-scored fact. Bounded, idempotent. Returns count stats."""
    now = now or datetime.now(timezone.utc)
    stats = {"scanned": 0, "scored": 0, "preserved_human": 0,
             "resolver_from_audit": 0}

    remaining = max_rows
    while True:
        limit = batch if remaining is None else min(batch, remaining)
        if limit <= 0:
            break
        rows = db.fetch_all(_UNSCORED_SQL, [limit])
        if not rows:
            break
        for fact in rows:
            stats["scanned"] += 1
            rc = resolver_conf_for_subject(
                db, fact.get("subject_entity_type"), fact.get("subject_entity_id"))
            if rc is not None:
                stats["resolver_from_audit"] += 1
            g = score_fact(fact, resolver_conf=rc, now=now)
            if (fact.get("review_status") or "") == "human_approved":
                stats["preserved_human"] += 1
            params = {
                "id": fact["id"],
                "source_reliability": g.source_reliability,
                "extraction_confidence": g.extraction_confidence,
                "resolver_confidence": g.resolver_confidence,
                "freshness_at": g.freshness_at,
                "schema_version": g.schema_version,
                "trust_score": g.trust_score,
                "review_status": g.review_status,
            }
            if not dry_run:
                db.execute(_UPDATE_SQL, params)
            stats["scored"] += 1
        if remaining is not None:
            remaining -= len(rows)
        # MockDB returns the same un-scored rows every call once dry_run skips the
        # UPDATE; in dry-run we only do one pass to avoid looping.
        if dry_run or len(rows) < limit:
            break
    logger.info("fact-governance backfill: %s", stats)
    return stats


def _dsn() -> str:
    return os.environ.get("DATABASE_URL") or __import__("config").config.db.dsn


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Backfill fact governance / trust model.")
    ap.add_argument("--limit", type=int, default=None,
                    help="Max facts to score (default: all un-scored).")
    ap.add_argument("--batch", type=int, default=1000)
    ap.add_argument("--dry-run", action="store_true",
                    help="Compute + report; do not write.")
    args = ap.parse_args()

    from db import Database

    db = Database(_dsn())
    db.connect()
    try:
        stats = backfill_governance(
            db, batch=args.batch, max_rows=args.limit, dry_run=args.dry_run)
    finally:
        try:
            db.close()
        except Exception:
            pass
    print("Fact-governance backfill complete:")
    for k, v in stats.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
