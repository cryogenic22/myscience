"""User feedback API routes.

Captures bug reports, feature requests, and data quality issues.
Data feedback (data_quality, data_request) feeds the Data Steward signal collector.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from api.deps import get_db
from db import Database

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/feedback", tags=["feedback"])

VALID_CATEGORIES = {"bug", "issue", "enhancement", "feature", "data_quality", "data_request"}
VALID_PRIORITIES = {"low", "medium", "high", "critical"}
VALID_STATUSES = {"new", "triaged", "in_progress", "resolved", "rejected"}


class FeedbackCreateRequest(BaseModel):
    category: str
    title: str
    description: Optional[str] = None
    priority: str = "medium"
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    page_url: Optional[str] = None
    entity_context: Optional[dict] = None
    diagnostic_context: Optional[dict] = None


class FeedbackUpdateRequest(BaseModel):
    status: Optional[str] = None
    priority: Optional[str] = None
    resolution: Optional[str] = None
    resolved_by: Optional[str] = None


@router.post("")
def create_feedback(body: FeedbackCreateRequest, db: Database = Depends(get_db)):
    """Create a feedback entry."""
    if body.category not in VALID_CATEGORIES:
        raise HTTPException(400, f"Invalid category: {body.category}. Must be one of {VALID_CATEGORIES}")
    if body.priority not in VALID_PRIORITIES:
        raise HTTPException(400, f"Invalid priority: {body.priority}")

    import json
    row = db.fetch_one(
        """
        INSERT INTO feedback_entries
            (user_id, session_id, page_url, category, title, description,
             priority, entity_context, diagnostic_context)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id, category, title, status, priority, created_at
        """,
        [
            body.user_id, body.session_id, body.page_url,
            body.category, body.title, body.description,
            body.priority,
            json.dumps(body.entity_context) if body.entity_context else None,
            json.dumps(body.diagnostic_context) if body.diagnostic_context else None,
        ],
    )
    logger.info("Feedback created: %s (%s) — %s", row["id"], body.category, body.title)
    return {"feedback": row}


@router.get("")
def list_feedback(
    status: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Database = Depends(get_db),
):
    """List feedback entries with optional filters."""
    conditions = []
    params = []

    if status:
        conditions.append("status = %s")
        params.append(status)
    if category:
        conditions.append("category = %s")
        params.append(category)

    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    total_row = db.fetch_one(
        f"SELECT COUNT(*) AS cnt FROM feedback_entries {where}", params
    )
    total = total_row["cnt"] if total_row else 0

    rows = db.fetch_all(
        f"""SELECT id, user_id, page_url, category, title, priority,
                   status, resolved_by, created_at, updated_at
            FROM feedback_entries {where}
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s""",
        params + [limit, offset],
    )
    return {"items": rows, "total": total, "limit": limit, "offset": offset}


@router.patch("/{feedback_id}")
def update_feedback(
    feedback_id: str,
    body: FeedbackUpdateRequest,
    db: Database = Depends(get_db),
):
    """Update feedback status, priority, or resolution."""
    updates = []
    params = []

    if body.status:
        if body.status not in VALID_STATUSES:
            raise HTTPException(400, f"Invalid status: {body.status}")
        updates.append("status = %s")
        params.append(body.status)
    if body.priority:
        if body.priority not in VALID_PRIORITIES:
            raise HTTPException(400, f"Invalid priority: {body.priority}")
        updates.append("priority = %s")
        params.append(body.priority)
    if body.resolution is not None:
        updates.append("resolution = %s")
        params.append(body.resolution)
    if body.resolved_by is not None:
        updates.append("resolved_by = %s")
        params.append(body.resolved_by)

    if not updates:
        raise HTTPException(400, "No fields to update")

    updates.append("updated_at = %s")
    params.append(datetime.now(timezone.utc))
    params.append(feedback_id)

    row = db.fetch_one(
        f"""UPDATE feedback_entries
            SET {', '.join(updates)}
            WHERE id = %s
            RETURNING id, status, priority, resolution, resolved_by, updated_at""",
        params,
    )
    if not row:
        raise HTTPException(404, f"Feedback {feedback_id} not found")
    return {"feedback": row}


@router.get("/stats")
def feedback_stats(db: Database = Depends(get_db)):
    """Aggregate counts by category, status, and resolved_by."""
    by_category = db.fetch_all(
        "SELECT category, COUNT(*) AS cnt FROM feedback_entries GROUP BY category ORDER BY cnt DESC"
    )
    by_status = db.fetch_all(
        "SELECT status, COUNT(*) AS cnt FROM feedback_entries GROUP BY status ORDER BY cnt DESC"
    )
    auto_resolved = db.fetch_one(
        "SELECT COUNT(*) AS cnt FROM feedback_entries WHERE resolved_by = 'steward'"
    )
    total = db.fetch_one("SELECT COUNT(*) AS cnt FROM feedback_entries")

    return {
        "total": total["cnt"] if total else 0,
        "by_category": {r["category"]: r["cnt"] for r in by_category},
        "by_status": {r["status"]: r["cnt"] for r in by_status},
        "auto_resolved_by_steward": auto_resolved["cnt"] if auto_resolved else 0,
    }
