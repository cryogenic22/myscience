"""CTX telemetry — lightweight persistence for context-building metrics.

Telemetry is fire-and-forget: failures are silently swallowed so they
never break the main request path.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def log_ctx_event(
    db,
    question: str,
    intent: str,
    ctx_tokens: Optional[int] = None,
    legacy_tokens: Optional[int] = None,
    compression_ratio: Optional[float] = None,
    build_time_ms: Optional[float] = None,
    mode: Optional[str] = None,
    evidence_raw_tokens: Optional[int] = None,
    evidence_compressed_tokens: Optional[int] = None,
    answer_quality_proxy: Optional[float] = None,
    query_complexity: Optional[int] = None,
    entity_count: Optional[int] = None,
    hop_depth: Optional[int] = None,
) -> None:
    """Persist a single CTX telemetry row. Never raises."""
    try:
        q_hash = hashlib.sha256(question.encode()).hexdigest()[:16]
        db.execute(
            """INSERT INTO ctx_telemetry
               (question_hash, intent, ctx_tokens, legacy_tokens,
                compression_ratio, build_time_ms, mode,
                evidence_raw_tokens, evidence_compressed_tokens,
                answer_quality_proxy, query_complexity, entity_count, hop_depth)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            [
                q_hash, intent, ctx_tokens, legacy_tokens,
                compression_ratio, build_time_ms, mode,
                evidence_raw_tokens, evidence_compressed_tokens,
                answer_quality_proxy, query_complexity, entity_count, hop_depth,
            ],
        )
    except Exception:
        logger.debug("ctx_telemetry insert failed (table may not exist yet)", exc_info=True)
