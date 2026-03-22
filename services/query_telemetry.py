"""Query telemetry — per-query signal capture for data gap detection.

Telemetry is fire-and-forget: failures are silently swallowed so they
never break the main request path. Feeds the Data Steward's signal collector.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Optional

logger = logging.getLogger(__name__)


# ── Gap Detection (pure function) ──────────────────────────────────

def detect_query_gap(
    entities_requested: list[str],
    entities_found: list[str],
    evidence_count: int,
    confidence: float | None,
) -> tuple[str | None, dict | None]:
    """Determine gap type from response signals.

    Returns (gap_type, gap_details) or (None, None) if no gap detected.

    Gap types:
    - 'missing_entity': entity requested but not found in response
    - 'low_evidence': fewer than 2 evidence items
    - 'low_confidence': confidence < 0.4 (UnifiedHandler only)
    """
    # Missing entity: requested but not in response
    requested_set = set(e.lower().strip() for e in (entities_requested or []) if e)
    found_set = set(e.lower().strip() for e in (entities_found or []) if e)
    missing = requested_set - found_set
    if missing:
        return "missing_entity", {"missing": sorted(missing)}

    # Low confidence (only available with UnifiedHandler)
    if confidence is not None and confidence < 0.4:
        return "low_confidence", {"confidence": confidence}

    # Low evidence
    if evidence_count < 2:
        return "low_evidence", {"evidence_count": evidence_count}

    return None, None


# ── Telemetry Persistence (fire-and-forget) ────────────────────────

def log_query_event(
    db,
    session_id: str | None = None,
    question: str = "",
    intent: str = "",
    entities_requested: list[str] | None = None,
    entities_found: list[str] | None = None,
    confidence: float | None = None,
    evidence_count: int = 0,
    sources_used: list[str] | None = None,
    response_latency_ms: float | None = None,
    gap_type: str | None = None,
    gap_details: dict | None = None,
) -> None:
    """Persist a single query telemetry row. Never raises."""
    try:
        import json
        q_hash = hashlib.sha256(question.encode()).hexdigest()[:16]
        db.execute(
            """INSERT INTO query_telemetry
               (session_id, question_hash, question_text, intent,
                entities_requested, entities_found,
                confidence, evidence_count, sources_used,
                response_latency_ms, gap_type, gap_details)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            [
                session_id, q_hash, question, intent,
                entities_requested, entities_found,
                confidence, evidence_count, sources_used,
                response_latency_ms, gap_type,
                json.dumps(gap_details) if gap_details else None,
            ],
        )
    except Exception:
        logger.debug("query_telemetry insert failed (table may not exist yet)", exc_info=True)
