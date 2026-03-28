"""Intelligence Feed Service — assessed events + impact assessments for the frontend feed panel.

Queries assessed_events and impact_assessments tables, classifies severity,
and provides feed retrieval, summary, detail, dismissal, and chat context.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


# ── Severity derivation ──


def derive_severity(trust_score: float, max_impact_magnitude: float) -> str:
    """Classify event severity from trust score and max impact magnitude.

    Thresholds:
    - critical: trust >= 0.8 AND max_impact >= 0.7
    - high:     trust >= 0.6 AND max_impact >= 0.4
    - medium:   trust >= 0.4
    - low:      everything else
    """
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
    """Query assessed events and impact assessments for the intelligence feed."""

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
        """Return feed items sorted by trust_score DESC, created_at DESC.

        Applies optional severity and entity_type post-filters (severity is
        derived, not stored, so we filter in Python after retrieval).
        """
        try:
            conditions = ["ae.status != 'dismissed'"]
            params: list = []

            if entity_type:
                conditions.append("ae.primary_entity_type = %s")
                params.append(entity_type)

            conditions.append(
                "ae.created_at > NOW() - make_interval(hours := %s)"
            )
            params.append(since_hours)

            where = " AND ".join(conditions)

            rows = self.db.fetch_all(
                f"""
                SELECT
                    ae.event_id::text AS event_id,
                    ae.event_type,
                    ae.event_date::text AS event_date,
                    ae.description,
                    ae.source_url,
                    ae.source_tier,
                    ae.trust_score,
                    ae.primary_entity_name,
                    ae.primary_entity_type,
                    COALESCE(ic.impact_count, 0) AS impact_count,
                    COALESCE(ic.max_impact_magnitude, 0) AS max_impact_magnitude,
                    ae.status,
                    ae.created_at::text AS created_at
                FROM assessed_events ae
                LEFT JOIN LATERAL (
                    SELECT
                        COUNT(*) AS impact_count,
                        MAX(magnitude) AS max_impact_magnitude
                    FROM impact_assessments ia
                    WHERE ia.event_id = ae.event_id
                ) ic ON true
                WHERE {where}
                ORDER BY ae.trust_score DESC, ae.created_at DESC
                LIMIT %s OFFSET %s
                """,
                params + [limit, offset],
            )
        except Exception:
            logger.exception("Failed to fetch intelligence feed")
            rows = []

        items = [self._row_to_feed_item(row) for row in rows]

        # Post-filter by severity (derived field, not in DB)
        if severity:
            items = [item for item in items if item.severity == severity]

        return items

    def get_feed_summary(self, since_hours: int = 24) -> FeedSummary:
        """Count unread events and break down by severity."""
        try:
            rows = self.db.fetch_all(
                """
                SELECT
                    ae.trust_score,
                    COALESCE(ic.max_impact_magnitude, 0) AS max_impact_magnitude,
                    ae.status
                FROM assessed_events ae
                LEFT JOIN LATERAL (
                    SELECT MAX(magnitude) AS max_impact_magnitude
                    FROM impact_assessments ia
                    WHERE ia.event_id = ae.event_id
                ) ic ON true
                WHERE ae.status != 'dismissed'
                  AND ae.created_at > NOW() - make_interval(hours := %s)
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
                    ae.event_id::text AS event_id,
                    ae.event_type,
                    ae.event_date::text AS event_date,
                    ae.description,
                    ae.source_url,
                    ae.source_tier,
                    ae.trust_score,
                    ae.primary_entity_name,
                    ae.primary_entity_type,
                    ae.status,
                    ae.created_at::text AS created_at
                FROM assessed_events ae
                WHERE ae.event_id::text = %s
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
                    ia.assessment_id::text AS assessment_id,
                    ia.event_id::text AS event_id,
                    ia.entity_id::text AS entity_id,
                    ia.entity_type,
                    ia.entity_name,
                    ia.impact_type,
                    ia.magnitude,
                    ia.direction,
                    ia.reasoning,
                    ia.confidence
                FROM impact_assessments ia
                WHERE ia.event_id::text = %s
                ORDER BY ia.magnitude DESC
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
            """
            UPDATE assessed_events
            SET status = 'dismissed',
                updated_at = NOW()
            WHERE event_id::text = %s
            """,
            [event_id],
        )

    def get_chat_context_events(
        self,
        entity_names: list[str],
        since_hours: int = 72,
    ) -> list[dict]:
        """Return recent events relevant to the given entity names for chat context.

        Used by the chat handler to inject intelligence signals into LLM context.
        """
        if not entity_names:
            return []

        try:
            # Build parameterized IN clause
            placeholders = ", ".join(["%s"] * len(entity_names))
            rows = self.db.fetch_all(
                f"""
                SELECT
                    ae.event_id::text AS event_id,
                    ae.event_type,
                    ae.description,
                    ae.trust_score,
                    ae.primary_entity_name,
                    ae.primary_entity_type,
                    ae.created_at::text AS created_at
                FROM assessed_events ae
                WHERE ae.entity_name IN ({placeholders})
                  AND ae.status != 'dismissed'
                  AND ae.created_at > NOW() - make_interval(hours := %s)
                ORDER BY ae.trust_score DESC, ae.created_at DESC
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
