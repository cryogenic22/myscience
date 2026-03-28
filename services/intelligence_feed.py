"""Intelligence Feed Service — market events + impact assessments for the frontend feed.

Queries market_events (extended by migration 026) and impact_assessments,
classifies severity, and provides feed retrieval, summary, detail, dismissal,
and chat context injection.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


# ── Severity derivation ──


def derive_severity(trust_score: float, max_impact_magnitude: float) -> str:
    """Classify event severity from trust score and max impact magnitude."""
    if trust_score >= 0.8 and max_impact_magnitude >= 0.7:
        return "critical"
    if trust_score >= 0.6 and max_impact_magnitude >= 0.4:
        return "high"
    if trust_score >= 0.4:
        return "medium"
    return "low"


# ── Data classes ──


@dataclass
class FeedItem:
    event_id: str
    event_type: str
    event_date: Optional[str]
    description: str
    source_url: Optional[str]
    source_tier: str
    trust_score: float
    primary_entity_name: Optional[str]
    primary_entity_type: Optional[str]
    severity: str
    impact_count: int
    max_impact_magnitude: float
    status: str
    created_at: str


@dataclass
class FeedSummary:
    total_unread: int
    critical_count: int
    high_count: int
    since_hours: int


# ── Service ──


class IntelligenceFeedService:
    """Query market events and impact assessments for the intelligence feed."""

    def __init__(self, db):
        self.db = db

    def get_feed(
        self,
        limit: int = 30,
        offset: int = 0,
        severity: Optional[str] = None,
        entity_type: Optional[str] = None,
        since_hours: int = 168,
    ) -> list[FeedItem]:
        """Return feed items sorted by trust_score DESC, created_at DESC."""
        try:
            conditions = ["me.status != 'dismissed'"]
            params: list = []

            if entity_type:
                conditions.append("me.primary_entity_type = %s")
                params.append(entity_type)

            conditions.append(
                "me.created_at > NOW() - make_interval(hours := %s)"
            )
            params.append(since_hours)

            where = " AND ".join(conditions)

            rows = self.db.fetch_all(
                f"""
                SELECT
                    me.id::text AS event_id,
                    me.event_type,
                    me.event_date::text AS event_date,
                    me.description,
                    me.source_url,
                    COALESCE(me.source_tier, 'tier_3') AS source_tier,
                    COALESCE(me.trust_score, 0.5) AS trust_score,
                    me.primary_entity_name,
                    me.primary_entity_type,
                    COALESCE(ic.impact_count, 0) AS impact_count,
                    COALESCE(ic.max_impact, 0) AS max_impact_magnitude,
                    COALESCE(me.status, 'new') AS status,
                    me.created_at::text AS created_at
                FROM market_events me
                LEFT JOIN LATERAL (
                    SELECT
                        COUNT(*) AS impact_count,
                        MAX(ia.impact_magnitude) AS max_impact
                    FROM impact_assessments ia
                    WHERE ia.event_id = me.id
                ) ic ON true
                WHERE {where}
                ORDER BY me.trust_score DESC NULLS LAST, me.created_at DESC
                LIMIT %s OFFSET %s
                """,
                params + [limit, offset],
            )
        except Exception:
            logger.exception("Failed to fetch intelligence feed")
            rows = []

        items = [self._row_to_feed_item(row) for row in rows]

        if severity:
            items = [item for item in items if item.severity == severity]

        return items

    def get_feed_summary(self, since_hours: int = 24) -> FeedSummary:
        """Count unread events and break down by severity."""
        try:
            rows = self.db.fetch_all(
                """
                SELECT
                    COALESCE(me.trust_score, 0.5) AS trust_score,
                    COALESCE(ic.max_impact, 0) AS max_impact_magnitude
                FROM market_events me
                LEFT JOIN LATERAL (
                    SELECT MAX(ia.impact_magnitude) AS max_impact
                    FROM impact_assessments ia
                    WHERE ia.event_id = me.id
                ) ic ON true
                WHERE COALESCE(me.status, 'new') != 'dismissed'
                  AND me.created_at > NOW() - make_interval(hours := %s)
                """,
                [since_hours],
            )
        except Exception:
            logger.exception("Failed to fetch feed summary")
            rows = []

        total_unread = len(rows)
        critical_count = 0
        high_count = 0

        for row in rows:
            trust = float(row.get("trust_score", 0))
            impact = float(row.get("max_impact_magnitude", 0))
            sev = derive_severity(trust, impact)
            if sev == "critical":
                critical_count += 1
            elif sev == "high":
                high_count += 1

        return FeedSummary(
            total_unread=total_unread,
            critical_count=critical_count,
            high_count=high_count,
            since_hours=since_hours,
        )

    def get_event_detail(self, event_id: str) -> Optional[dict]:
        """Return a single event with its impact assessments."""
        try:
            row = self.db.fetch_one(
                """
                SELECT
                    me.id::text AS event_id,
                    me.event_type,
                    me.event_date::text AS event_date,
                    me.description,
                    me.source_url,
                    COALESCE(me.source_tier, 'tier_3') AS source_tier,
                    COALESCE(me.trust_score, 0.5) AS trust_score,
                    me.primary_entity_name,
                    me.primary_entity_type,
                    COALESCE(me.status, 'new') AS status,
                    me.created_at::text AS created_at
                FROM market_events me
                WHERE me.id::text = %s
                LIMIT 1
                """,
                [event_id],
            )
        except Exception:
            logger.exception("Failed to fetch event detail")
            return None

        if not row:
            return None

        try:
            assessments = self.db.fetch_all(
                """
                SELECT
                    ia.id::text AS assessment_id,
                    ia.event_id::text AS event_id,
                    ia.affected_entity_id,
                    ia.affected_entity_type,
                    ia.affected_entity_name,
                    ia.assessment_type,
                    ia.impact_magnitude,
                    ia.impact_direction,
                    ia.narrative,
                    ia.scenario_result
                FROM impact_assessments ia
                WHERE ia.event_id::text = %s
                ORDER BY ia.impact_magnitude DESC NULLS LAST
                """,
                [event_id],
            )
        except Exception:
            logger.exception("Failed to fetch impact assessments")
            assessments = []

        result = dict(row)
        result["assessments"] = list(assessments)
        return result

    def dismiss_event(self, event_id: str) -> None:
        """Mark an event as dismissed."""
        self.db.execute(
            "UPDATE market_events SET status = 'dismissed' WHERE id::text = %s",
            [event_id],
        )

    def get_chat_context_events(
        self,
        entity_names: list[str],
        since_hours: int = 72,
    ) -> list[dict]:
        """Return recent events relevant to given entity names for chat context."""
        if not entity_names:
            return []

        try:
            placeholders = ", ".join(["%s"] * len(entity_names))
            rows = self.db.fetch_all(
                f"""
                SELECT
                    me.id::text AS event_id,
                    me.event_type,
                    me.description,
                    COALESCE(me.trust_score, 0.5) AS trust_score,
                    me.primary_entity_name,
                    me.primary_entity_type,
                    me.created_at::text AS created_at
                FROM market_events me
                WHERE me.primary_entity_name IN ({placeholders})
                  AND COALESCE(me.status, 'new') != 'dismissed'
                  AND me.created_at > NOW() - make_interval(hours := %s)
                ORDER BY me.trust_score DESC NULLS LAST, me.created_at DESC
                LIMIT 10
                """,
                entity_names + [since_hours],
            )
        except Exception:
            logger.exception("Failed to fetch chat context events")
            rows = []

        return [dict(r) for r in rows]

    # ── Helpers ──

    @staticmethod
    def _row_to_feed_item(row: dict) -> FeedItem:
        trust = float(row.get("trust_score", 0))
        impact = float(row.get("max_impact_magnitude", 0))
        return FeedItem(
            event_id=str(row.get("event_id", "")),
            event_type=str(row.get("event_type", "")),
            event_date=row.get("event_date"),
            description=str(row.get("description", "")),
            source_url=row.get("source_url"),
            source_tier=str(row.get("source_tier", "")),
            trust_score=trust,
            primary_entity_name=row.get("primary_entity_name"),
            primary_entity_type=row.get("primary_entity_type"),
            severity=derive_severity(trust, impact),
            impact_count=int(row.get("impact_count", 0)),
            max_impact_magnitude=impact,
            status=str(row.get("status", "new")),
            created_at=str(row.get("created_at", "")),
        )
