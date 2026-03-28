"""Intelligence Feed API routes.

Expose assessed events and impact assessments as a REST feed for the
frontend intelligence panel.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query

from api.deps import get_db
from db import Database

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/intelligence", tags=["intelligence"])


def _get_feed_service(db: Database = Depends(get_db)):
    from services.intelligence_feed import IntelligenceFeedService
    return IntelligenceFeedService(db)


@router.get("/feed")
def get_feed(
    limit: int = Query(30, ge=1, le=200),
    offset: int = Query(0, ge=0),
    severity: str | None = Query(None),
    entity_type: str | None = Query(None),
    since_hours: int = Query(168, ge=1, le=8760),
    db: Database = Depends(get_db),
):
    """Return the intelligence feed — assessed events sorted by trust then recency."""
    try:
        from services.intelligence_feed import IntelligenceFeedService
        svc = IntelligenceFeedService(db)
        items = svc.get_feed(
            limit=limit,
            offset=offset,
            severity=severity,
            entity_type=entity_type,
            since_hours=since_hours,
        )
        return {
            "items": [
                {
                    "event_id": item.event_id,
                    "event_type": item.event_type,
                    "event_date": item.event_date,
                    "description": item.description,
                    "source_url": item.source_url,
                    "source_tier": item.source_tier,
                    "trust_score": round(item.trust_score, 3),
                    "primary_entity_name": item.primary_entity_name,
                    "primary_entity_type": item.primary_entity_type,
                    "severity": item.severity,
                    "impact_count": item.impact_count,
                    "max_impact_magnitude": round(item.max_impact_magnitude, 3),
                    "status": item.status,
                    "created_at": item.created_at,
                }
                for item in items
            ],
            "count": len(items),
            "limit": limit,
            "offset": offset,
        }
    except Exception:
        logger.exception("Failed to fetch intelligence feed")
        return {"items": [], "count": 0, "limit": limit, "offset": offset}


@router.get("/feed/summary")
def feed_summary(
    since_hours: int = Query(24, ge=1, le=8760),
    db: Database = Depends(get_db),
):
    """Return unread event counts broken down by severity."""
    try:
        from services.intelligence_feed import IntelligenceFeedService
        svc = IntelligenceFeedService(db)
        summary = svc.get_feed_summary(since_hours=since_hours)
        return {
            "total_unread": summary.total_unread,
            "critical_count": summary.critical_count,
            "high_count": summary.high_count,
            "since_hours": summary.since_hours,
        }
    except Exception:
        logger.exception("Failed to fetch feed summary")
        return {"total_unread": 0, "critical_count": 0, "high_count": 0, "since_hours": since_hours}


@router.get("/feed/{event_id}")
def event_detail(
    event_id: str,
    db: Database = Depends(get_db),
):
    """Return a single event with its impact assessments."""
    try:
        from services.intelligence_feed import IntelligenceFeedService
        svc = IntelligenceFeedService(db)
        result = svc.get_event_detail(event_id)
        if result is None:
            return {"error": "not_found", "event_id": event_id}
        return result
    except Exception:
        logger.exception("Failed to fetch event detail")
        return {"error": "internal_error", "event_id": event_id}


@router.post("/feed/{event_id}/dismiss")
def dismiss_event(
    event_id: str,
    db: Database = Depends(get_db),
):
    """Mark an event as dismissed."""
    try:
        from services.intelligence_feed import IntelligenceFeedService
        svc = IntelligenceFeedService(db)
        svc.dismiss_event(event_id)
        return {"status": "dismissed", "event_id": event_id}
    except Exception:
        logger.exception("Failed to dismiss event")
        return {"error": "internal_error", "event_id": event_id}


@router.get("/chat-context")
def chat_context(
    entities: str = Query(..., description="Comma-separated entity names"),
    since_hours: int = Query(72, ge=1, le=720),
    db: Database = Depends(get_db),
):
    """Return recent intelligence events relevant to the given entities for chat context."""
    try:
        from services.intelligence_feed import IntelligenceFeedService
        entity_names = [e.strip() for e in entities.split(",") if e.strip()]
        if not entity_names:
            return {"events": [], "count": 0}
        svc = IntelligenceFeedService(db)
        events = svc.get_chat_context_events(entity_names, since_hours=since_hours)
        return {"events": events, "count": len(events)}
    except Exception:
        logger.exception("Failed to fetch chat context events")
        return {"events": [], "count": 0}
