"""SPEC-021 D2 — autonomous outcome detection scheduler.

Periodically scans open/in_progress decisions, runs the outcome matcher
against the live signals table, and appends `outcome_proposals` rows
for high-confidence matches. Does NOT auto-capture — the human still
confirms via UI (D2 stays "AI-informed → confirmed by human"). Full
autonomy comes in D Phase 3 (raise threshold + auto-write decisions).

Reuses the matcher in `services.outcome_detector` (no duplication).
Designed to be called from the existing `DataPipelineScheduler` job
registry — see `register_outcome_scheduler`.

Each tick:
  1. SELECT open/in_progress decisions where outcome_auto_checked_at
     is NULL or stale (> 6 hours old)
  2. For each, look up war_room.primary_entity_id and run the matcher
  3. For top-N candidates above AUTO_PROPOSE_THRESHOLD, INSERT into
     outcome_proposals (UNIQUE on decision_id+signal_id prevents dupes)
  4. UPDATE the decision's outcome_auto_checked_at timestamp
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

from services.outcome_detector import (
    DETECTOR_RULE_VERSION,
    match_signals_to_decision,
)

logger = logging.getLogger(__name__)


# Higher threshold than the manual matcher (0.4) — autonomous proposals
# should be confident enough that the human will usually accept.
AUTO_PROPOSE_THRESHOLD = 0.75

# How many decisions to process per tick (cap to avoid runaway batches)
MAX_DECISIONS_PER_TICK = 50

# Re-scan a decision after this interval, even if previously checked
RECHECK_AFTER_HOURS = 6


def _is_disabled() -> bool:
    return os.environ.get("MZ_OUTCOME_SCHEDULER_DISABLED", "").lower() in ("1", "true", "yes")


def _due_decisions(db, limit: int = MAX_DECISIONS_PER_TICK) -> list[dict]:
    """Open/in_progress decisions due for an outcome auto-check."""
    try:
        return db.fetch_all(
            f"""SELECT id, war_room_round_id, war_room_id, source_signal_id,
                       move_type, target_value, deadline, confidence_at_commit,
                       created_at, outcome_auto_checked_at
                FROM decisions
                WHERE status IN ('open', 'in_progress')
                  AND (outcome_auto_checked_at IS NULL
                       OR outcome_auto_checked_at < NOW() - INTERVAL '{RECHECK_AFTER_HOURS} hours')
                ORDER BY outcome_auto_checked_at NULLS FIRST, created_at ASC
                LIMIT %s""",
            [limit],
        ) or []
    except Exception:
        logger.exception("outcome_scheduler: due-decisions query failed")
        return []


def _entity_id_for_decision(db, decision: dict) -> Optional[str]:
    war_room_id = decision.get("war_room_id")
    if not war_room_id:
        return None
    try:
        row = db.fetch_one(
            "SELECT primary_entity_id FROM war_rooms WHERE id::text = %s",
            [str(war_room_id)],
        )
    except Exception:
        return None
    return row.get("primary_entity_id") if row else None


def _propose(db, *, decision_id: str, candidate: dict) -> bool:
    """Insert one outcome_proposals row. Returns True if inserted, False
    if a duplicate was silently ignored (UNIQUE constraint catch).

    Uses ON CONFLICT DO NOTHING so re-running the scheduler doesn't
    fail; we just skip already-proposed (decision, signal) pairs.
    """
    try:
        db.execute(
            """INSERT INTO outcome_proposals
                   (decision_id, matched_signal_id, match_score, match_components)
               VALUES (%s::uuid, %s::uuid, %s, %s::jsonb)
               ON CONFLICT (decision_id, matched_signal_id) DO NOTHING""",
            [
                decision_id,
                candidate["signal_id"],
                float(candidate["match_score"]),
                json.dumps(candidate.get("match_components") or {}),
            ],
        )
        return True
    except Exception as exc:
        logger.warning(
            "outcome_proposal insert failed (decision=%s signal=%s): %s",
            decision_id, candidate.get("signal_id"), exc,
        )
        return False


def _mark_checked(db, decision_id: str) -> None:
    try:
        db.execute(
            "UPDATE decisions SET outcome_auto_checked_at = NOW() WHERE id::text = %s",
            [decision_id],
        )
    except Exception:
        logger.exception("outcome_scheduler: mark-checked failed for %s", decision_id)


def tick(db) -> dict:
    """Run one detection pass. Returns summary stats for logging."""
    if _is_disabled():
        return {"disabled": True, "decisions_scanned": 0, "proposals_created": 0}

    decisions = _due_decisions(db)
    if not decisions:
        return {"decisions_scanned": 0, "proposals_created": 0}

    proposals_created = 0
    for d in decisions:
        decision_id = str(d["id"])
        entity_id = _entity_id_for_decision(db, d)
        try:
            candidates = match_signals_to_decision(
                db, decision=d, entity_id_for_matching=entity_id,
            )
        except Exception:
            logger.exception("outcome_scheduler: matcher raised for %s", decision_id)
            _mark_checked(db, decision_id)
            continue

        for c in candidates:
            if c.get("match_score", 0.0) >= AUTO_PROPOSE_THRESHOLD:
                if _propose(db, decision_id=decision_id, candidate=c):
                    proposals_created += 1

        _mark_checked(db, decision_id)

    summary = {
        "rule_version_id": DETECTOR_RULE_VERSION,
        "decisions_scanned": len(decisions),
        "proposals_created": proposals_created,
    }
    logger.info("outcome_scheduler tick: %s", summary)
    return summary


def register_outcome_scheduler(scheduler, db_factory, interval_hours: int = 1) -> None:
    """Register the outcome detection job with an APScheduler instance.

    `db_factory` is a callable that returns a Database instance — we
    don't reuse a single connection across ticks because the scheduler
    runs in a background thread and connections are not thread-safe.
    """
    if _is_disabled():
        logger.info("outcome_scheduler disabled via MZ_OUTCOME_SCHEDULER_DISABLED")
        return

    from apscheduler.triggers.interval import IntervalTrigger

    def _job():
        try:
            db = db_factory()
            tick(db)
        except Exception:
            logger.exception("outcome_scheduler: job crashed")

    scheduler.add_job(
        _job,
        trigger=IntervalTrigger(hours=interval_hours),
        id="outcome_detection",
        name="SPEC-021 D2 outcome detection",
        replace_existing=True,
    )
    logger.info(
        "outcome_scheduler registered (every %dh, threshold=%.2f)",
        interval_hours, AUTO_PROPOSE_THRESHOLD,
    )
