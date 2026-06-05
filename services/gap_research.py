"""C3 (learning loops) — close the query → quality → research loop.

Diagnosis: "The query→quality→research loop is open: we log questions but
don't detect 'answered badly' → don't trigger the dormant research agent to
fill the gap."

This module is the trigger. When a chat answer is low-confidence / low-evidence
/ missing-entity (the gaps already computed by services.telemetry.detect_query_gap),
we spawn a research job to fill the gap. The job is the same
`deep_research_jobs` artifact the manual research path uses, so it flows
through the existing background runner (handle_deep_research) — i.e. the
dormant research path now has an automatic trigger.

Idempotent + bounded: we skip if an open (queued/running) gap-research job for
the same question already exists, so a user re-asking a weak query doesn't
spawn duplicates.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Gaps that justify auto-research. missing_entity and low_confidence are the
# strong "answered badly" signals; low_evidence is the thin-coverage signal.
GAP_TRIGGERS = {"missing_entity", "low_confidence", "low_evidence"}


def _has_open_gap_job(db, scope_key: str, question: str) -> bool:
    """True if a queued/running gap-research job already exists for this
    question (dedup so re-asking doesn't spawn duplicates)."""
    try:
        row = db.fetch_one(
            """
            SELECT 1
              FROM deep_research_jobs
             WHERE scope_key = %s
               AND question = %s
               AND status IN ('queued', 'running')
               AND (options->>'auto_gap_research') = 'true'
             LIMIT 1
            """,
            [scope_key, question],
        )
        return bool(row)
    except Exception:
        logger.debug("gap-job dedup check failed", exc_info=True)
        return False


def maybe_trigger_gap_research(
    db,
    *,
    question: str,
    gap_type: Optional[str],
    gap_details: Optional[dict] = None,
    scope_key: str = "default",
    session_id: Optional[str] = None,
) -> Optional[dict]:
    """Create a gap-fill research job if the answer was weak.

    Returns the created job dict, or None if no trigger fired (no gap, or a
    job already exists). Never raises — telemetry/triggers must not break chat.
    """
    if not question or not question.strip():
        return None
    if gap_type not in GAP_TRIGGERS:
        return None

    try:
        if _has_open_gap_job(db, scope_key, question):
            logger.info("gap-research already queued for %r — skipping", question[:80])
            return None

        # Lazy import to avoid a hard dependency cycle at module load.
        from services.workspace import ChatWorkspaceService

        workspace = ChatWorkspaceService(db)
        options = {
            "include_graph": True,
            "include_metrics": True,
            "source_strict": True,
            "include_web": True,
            # Markers so the job is attributable + dedupable.
            "auto_gap_research": True,
            "trigger_gap_type": gap_type,
            "trigger_gap_details": gap_details or {},
            "trigger_session_id": session_id,
        }
        job = workspace.create_research_job(
            scope_key=scope_key, question=question, options=options,
        )
        logger.info(
            "Auto-spawned gap-research job %s (gap=%s) for %r",
            job.get("id"), gap_type, question[:80],
        )
        return job
    except Exception:
        logger.warning("maybe_trigger_gap_research failed", exc_info=True)
        return None
