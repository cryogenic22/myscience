"""SPEC-021 Phase D MVP — outcome detector.

Given a decision (with `move_type`, `primary_entity_id`, `created_at`,
`deadline`, `confidence_at_commit`), find candidate outcome signals from
the `signals` table and score the match. After the human picks one,
compute a calibration_score and emit a learning-ledger row.

Engine signature mirrors the war-game pattern:
    (db, **structured_inputs) -> structured_output

so a future harness can wrap autonomous batch detection without
changing the service API. (See SPEC-021 §"LLM/tools/harness".)

Pure-functional internals are split out so they can be unit-tested
without a DB.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any, Optional

logger = logging.getLogger(__name__)


# Match scoring weight caps (must sum to 1.0)
_W_ENTITY = 0.5
_W_KBQ = 0.3
_W_TEMPORAL = 0.2

MATCH_THRESHOLD = 0.4
MAX_CANDIDATES = 5

DETECTOR_RULE_VERSION = "outcome-v1.0.0"


# Move-type → expected KBQ tags. Maps a war-game move to the kinds of
# signals likely to indicate its outcome firing in the real world.
MOVE_TO_KBQS: dict[str, set[str]] = {
    "trial_readout":      {"clinical"},
    "new_indication":     {"clinical", "regulatory"},
    "label_expansion":    {"regulatory"},
    "price_cut":          {"pricing_access"},
    "acquisition":        {"m_and_a", "strategic"},
    "formulation_switch": {"product"},
    "geo_expansion":      {"strategic"},
    "segment_pivot":      {"strategic", "product"},
}


# ────────────────────────────────────────────────────────────────────
# Pure scoring functions (DB-free)
# ────────────────────────────────────────────────────────────────────

def _kbq_for_move(move_type: str) -> set[str]:
    return MOVE_TO_KBQS.get(move_type, set())


def _score_entity(decision_entity_id: Optional[str],
                  signal_entity_id: Optional[str],
                  signal_related_entity_ids: Optional[list[str]] = None) -> float:
    """0.0–_W_ENTITY based on entity overlap.

    Full credit if primary_entity matches; half credit if the decision's
    entity appears in the signal's related_entity_ids.
    """
    if not decision_entity_id or not signal_entity_id:
        return 0.0
    if str(decision_entity_id) == str(signal_entity_id):
        return _W_ENTITY
    if signal_related_entity_ids and decision_entity_id in [str(x) for x in signal_related_entity_ids]:
        return _W_ENTITY * 0.5
    return 0.0


def _score_kbq(decision_move_type: str, signal_kbq_tags: Optional[list[str]]) -> float:
    """0.0–_W_KBQ based on KBQ overlap."""
    expected = _kbq_for_move(decision_move_type)
    if not expected or not signal_kbq_tags:
        return 0.0
    actual = set(str(t) for t in signal_kbq_tags)
    overlap = expected & actual
    if not overlap:
        return 0.0
    return _W_KBQ * (len(overlap) / len(expected))


def _score_temporal(decision_created_at: Optional[datetime | date],
                    decision_deadline: Optional[date],
                    signal_created_at: Optional[datetime | date]) -> float:
    """0.0–_W_TEMPORAL based on whether the signal landed in the
    decision's plausible-outcome window.

    Window: [decision.created_at, decision.deadline + 30 days].
    Within window → full credit.
    Within 60 days outside the window → half credit.
    Else → zero.
    """
    if signal_created_at is None or decision_created_at is None:
        return 0.0

    sd = signal_created_at.date() if hasattr(signal_created_at, "date") else signal_created_at
    cd = decision_created_at.date() if hasattr(decision_created_at, "date") else decision_created_at

    # Signal must arrive AT OR AFTER the decision was committed
    if sd < cd:
        return 0.0

    if decision_deadline is None:
        # No deadline — accept any signal in the next 180 days
        days_after = (sd - cd).days
        if days_after <= 180:
            return _W_TEMPORAL
        if days_after <= 240:
            return _W_TEMPORAL * 0.5
        return 0.0

    upper = decision_deadline + timedelta(days=30)
    if sd <= upper:
        return _W_TEMPORAL
    days_late = (sd - upper).days
    if days_late <= 60:
        return _W_TEMPORAL * 0.5
    return 0.0


def _compose_match(entity: float, kbq: float, temporal: float) -> tuple[float, dict]:
    total = entity + kbq + temporal
    return total, {
        "entity_overlap": round(entity, 3),
        "kbq_overlap": round(kbq, 3),
        "temporal_proximity": round(temporal, 3),
    }


# ────────────────────────────────────────────────────────────────────
# Calibration scoring
# ────────────────────────────────────────────────────────────────────

def compute_calibration_score(*, verdict: str, confidence_at_commit: Optional[float]) -> float:
    """Crude MVP calibration score in [0, 1].

    Quadrants:
      - verified + high conf  → confidence_at_commit (we were right and confident)
      - verified + low conf   → 1 - confidence_at_commit (right but hedged — partial credit)
      - missed   + high conf  → 1 - confidence_at_commit (wrong AND confident — heavy penalty inverted)
      - missed   + low conf   → confidence_at_commit (wrong but hedged — light penalty)

    A score near 1.0 = well-calibrated. A score near 0.0 = poorly
    calibrated (overconfident in the wrong direction).
    """
    if confidence_at_commit is None:
        return 0.5  # neutral when we have no prior

    c = max(0.0, min(1.0, confidence_at_commit))

    if verdict == "verified":
        if c >= 0.5:
            return c
        return 1.0 - c
    if verdict == "missed":
        if c >= 0.5:
            return 1.0 - c
        return c
    # cancelled / unknown verdict: neutral
    return 0.5


def suggest_weight_delta(*, calibration_score: float, verdict: str) -> float:
    """Magnitude derived from |calibration - 0.5|; sign from verdict.

    `verified` outcomes nudge weights up; `missed` outcomes nudge them
    down. Cancelled returns 0 (no learning signal).
    """
    if verdict == "cancelled":
        return 0.0
    magnitude = abs(calibration_score - 0.5) * 0.2  # scale to ±0.1 max
    return magnitude if verdict == "verified" else -magnitude


# ────────────────────────────────────────────────────────────────────
# DB-bound matching
# ────────────────────────────────────────────────────────────────────

def match_signals_to_decision(db, *, decision: dict,
                              entity_id_for_matching: Optional[str] = None,
                              limit: int = MAX_CANDIDATES) -> list[dict]:
    """Pull recent signals and score them against the decision.

    `decision` must have: id, move_type, source_signal_id (optional),
    created_at, deadline, primary_entity_id may live on the war_room.

    `entity_id_for_matching` lets the caller pass the war_room's
    primary_entity_id (which is the conceptually-correct entity for a
    decision; decisions don't carry a primary_entity_id of their own).
    """
    move_type = decision.get("move_type") or ""
    source_signal_id = decision.get("source_signal_id")
    created_at = decision.get("created_at")
    deadline = decision.get("deadline")

    if isinstance(created_at, str):
        try:
            created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except Exception:
            created_at = None
    if isinstance(deadline, str):
        try:
            deadline = datetime.fromisoformat(deadline).date()
        except Exception:
            deadline = None

    expected_kbqs = _kbq_for_move(move_type)

    # Pull recent signals — coarse filter at SQL level (recency +
    # status), refine with scoring in Python. Cap row count to a sane
    # limit to keep this cheap.
    try:
        rows = db.fetch_all(
            """SELECT id, headline, summary, kbq_tags, primary_entity_id,
                      primary_entity_name, related_entity_ids, created_at,
                      confidence_tier, trust_score, impact_tier, rule_version_id
               FROM signals
               WHERE status IN ('candidate', 'reviewed', 'shipped')
                 AND created_at >= NOW() - INTERVAL '270 days'
               ORDER BY created_at DESC
               LIMIT 200""",
            None,
        ) or []
    except Exception:
        logger.exception("signal pull failed in outcome_detector")
        return []

    candidates: list[dict] = []
    for row in rows:
        sid = str(row.get("id"))
        # Exclude the decision's source signal — that's the seed, not the outcome
        if source_signal_id and str(source_signal_id) == sid:
            continue

        ent = _score_entity(
            entity_id_for_matching,
            row.get("primary_entity_id"),
            row.get("related_entity_ids"),
        )
        kbq = _score_kbq(move_type, row.get("kbq_tags"))
        temp = _score_temporal(created_at, deadline, row.get("created_at"))
        score, components = _compose_match(ent, kbq, temp)

        if score < MATCH_THRESHOLD:
            continue

        candidates.append({
            "signal_id": sid,
            "headline": row.get("headline"),
            "summary": row.get("summary"),
            "kbq_tags": list(row.get("kbq_tags") or []),
            "created_at": row.get("created_at").isoformat() if hasattr(row.get("created_at"), "isoformat") else str(row.get("created_at") or ""),
            "primary_entity_name": row.get("primary_entity_name"),
            "primary_entity_id": row.get("primary_entity_id"),
            "rule_version_id": row.get("rule_version_id"),
            "confidence_tier": row.get("confidence_tier"),
            "trust_score": row.get("trust_score"),
            "impact_tier": row.get("impact_tier"),
            "match_score": round(score, 3),
            "match_components": components,
        })

    candidates.sort(key=lambda c: c["match_score"], reverse=True)
    return candidates[:limit]
