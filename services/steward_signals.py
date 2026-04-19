"""Steward Signal Collector — aggregates data gap signals for the Data Steward.

Collects from three sources:
1. query_telemetry — low-confidence answers, missing entities
2. feedback_entries — data_quality and data_request user reports
3. quality metrics — stale sources, low completeness

Ranks signals via objective function:
    score = query_frequency × gap_severity × feasibility × freshness_decay
"""

from __future__ import annotations

import math
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from db import Database

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────

GAP_SEVERITY = {
    "missing_entity": 1.0,
    "data_quality": 0.9,
    "data_request": 0.8,
    "low_confidence": 0.7,
    "low_evidence": 0.5,
    "low_completeness": 0.6,
    "stale_data": 0.4,
}

FEASIBILITY = {
    "deterministic": 1.0,   # existing script can fix it
    "ai_enrichment": 0.5,   # needs LLM
    "web_research": 0.3,    # external lookup
    "manual": 0.1,          # needs human
}

# Gap types that map to deterministic fixes
DETERMINISTIC_GAPS = {"low_completeness", "stale_data", "data_quality"}


# ── Dataclass ──────────────────────────────────────────────────────

@dataclass
class StewardSignal:
    """A single signal indicating a data gap the steward should address."""
    source: str             # 'query_telemetry' | 'feedback' | 'quality_scorecard'
    source_id: str          # row ID from source table
    entity_type: str | None
    entity_id: str | None
    entity_name: str | None
    gap_type: str           # 'missing_entity', 'low_evidence', etc.
    priority_score: float
    details: dict
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ── Collector ──────────────────────────────────────────────────────

class StewardSignalCollector:
    """Aggregates signals from telemetry, feedback, and quality metrics."""

    def __init__(self, db: Database):
        self.db = db

    def collect_signals(
        self, limit: int = 50, since_days: int = 7
    ) -> list[StewardSignal]:
        """Collect and rank signals from all sources.

        Returns signals sorted by priority_score descending.
        """
        signals: list[StewardSignal] = []
        signals.extend(self._collect_query_gaps(since_days))
        signals.extend(self._collect_feedback_signals(since_days))
        signals.extend(self._collect_quality_signals())

        # Deduplicate by (entity_id, gap_type) — keep highest priority
        seen: dict[tuple, StewardSignal] = {}
        for s in signals:
            key = (s.entity_id, s.gap_type)
            if key not in seen or s.priority_score > seen[key].priority_score:
                seen[key] = s
        deduped = sorted(seen.values(), key=lambda s: s.priority_score, reverse=True)

        return deduped[:limit]

    def _collect_query_gaps(self, since_days: int) -> list[StewardSignal]:
        """Extract gap signals from query_telemetry."""
        signals = []
        try:
            rows = self.db.fetch_all(
                """
                SELECT gap_type, gap_details,
                       COUNT(*) AS frequency,
                       MIN(created_at) AS first_seen
                FROM query_telemetry
                WHERE gap_type IS NOT NULL
                  AND created_at > NOW() - make_interval(days := %s)
                GROUP BY gap_type, gap_details
                ORDER BY frequency DESC
                LIMIT 50
                """,
                [since_days],
            )
            for row in rows:
                details = row.get("gap_details") or {}
                if isinstance(details, str):
                    import json
                    details = json.loads(details)

                # Extract entity info from gap details
                missing = details.get("missing", [])
                entity_name = missing[0] if missing else None

                score = compute_priority(
                    gap_type=row["gap_type"],
                    query_frequency=row["frequency"],
                    created_at=row.get("first_seen"),
                )
                signals.append(StewardSignal(
                    source="query_telemetry",
                    source_id=f"qt-{row['gap_type']}-{row['frequency']}",
                    entity_type=None,
                    entity_id=None,
                    entity_name=entity_name,
                    gap_type=row["gap_type"],
                    priority_score=score,
                    details={"frequency": row["frequency"], **details},
                    created_at=row.get("first_seen", datetime.now(timezone.utc)),
                ))
        except Exception:
            logger.debug("Failed to collect query gap signals", exc_info=True)

        return signals

    def _collect_feedback_signals(self, since_days: int) -> list[StewardSignal]:
        """Extract data feedback as steward signals."""
        signals = []
        try:
            rows = self.db.fetch_all(
                """
                SELECT id, category, title, description, entity_context,
                       priority, created_at
                FROM feedback_entries
                WHERE category IN ('data_quality', 'data_request')
                  AND status IN ('new', 'triaged')
                  AND created_at > NOW() - make_interval(days := %s)
                ORDER BY
                    CASE priority
                        WHEN 'critical' THEN 4 WHEN 'high' THEN 3
                        WHEN 'medium' THEN 2 WHEN 'low' THEN 1
                    END DESC,
                    created_at ASC
                LIMIT 50
                """,
                [since_days],
            )
            for row in rows:
                ec = row.get("entity_context") or {}
                if isinstance(ec, str):
                    import json
                    ec = json.loads(ec)

                priority_boost = {"critical": 2.0, "high": 1.5, "medium": 1.0, "low": 0.5}
                boost = priority_boost.get(row.get("priority", "medium"), 1.0)

                score = compute_priority(
                    gap_type=row["category"],
                    query_frequency=1,
                    created_at=row.get("created_at"),
                ) * boost

                signals.append(StewardSignal(
                    source="feedback",
                    source_id=str(row["id"]),
                    entity_type=ec.get("entity_type"),
                    entity_id=ec.get("entity_id"),
                    entity_name=ec.get("entity_name"),
                    gap_type=row["category"],
                    priority_score=score,
                    details={
                        "title": row["title"],
                        "description": row.get("description"),
                        "feedback_priority": row.get("priority"),
                    },
                    created_at=row.get("created_at", datetime.now(timezone.utc)),
                ))
        except Exception:
            logger.debug("Failed to collect feedback signals", exc_info=True)

        return signals

    def _collect_quality_signals(self) -> list[StewardSignal]:
        """Extract signals from stale sources and low completeness."""
        signals = []
        try:
            # Stale sources: last ETL run > 14 days ago
            rows = self.db.fetch_all(
                """
                SELECT source_name, MAX(finished_at) AS last_run
                FROM etl_runs
                WHERE status = 'completed'
                GROUP BY source_name
                HAVING MAX(finished_at) < NOW() - INTERVAL '14 days'
                """
            )
            for row in rows:
                score = compute_priority(
                    gap_type="stale_data",
                    query_frequency=1,
                    created_at=row.get("last_run"),
                )
                signals.append(StewardSignal(
                    source="quality_scorecard",
                    source_id=f"stale-{row['source_name']}",
                    entity_type=None,
                    entity_id=None,
                    entity_name=None,
                    gap_type="stale_data",
                    priority_score=score,
                    details={"source_name": row["source_name"], "last_run": str(row["last_run"])},
                ))
        except Exception:
            logger.debug("Failed to collect quality signals", exc_info=True)

        return signals

    def get_signal_stats(self) -> dict:
        """Return aggregate statistics about current signals."""
        signals = self.collect_signals(limit=200, since_days=30)
        by_source: dict[str, int] = {}
        by_gap: dict[str, int] = {}
        entity_counts: dict[str, int] = {}

        for s in signals:
            by_source[s.source] = by_source.get(s.source, 0) + 1
            by_gap[s.gap_type] = by_gap.get(s.gap_type, 0) + 1
            if s.entity_name:
                entity_counts[s.entity_name] = entity_counts.get(s.entity_name, 0) + 1

        top_entities = sorted(entity_counts.items(), key=lambda x: x[1], reverse=True)[:10]

        return {
            "total_signals": len(signals),
            "by_source": by_source,
            "by_gap_type": by_gap,
            "top_entities": [{"name": n, "signal_count": c} for n, c in top_entities],
        }


# ── Objective Function ─────────────────────────────────────────────

def compute_priority(
    gap_type: str,
    query_frequency: int = 1,
    created_at: datetime | None = None,
) -> float:
    """Compute priority score for a signal.

    score = query_frequency × gap_severity × feasibility × freshness_decay

    freshness_decay = exp(-age_days / 30)  — recent signals weighted higher
    """
    severity = GAP_SEVERITY.get(gap_type, 0.5)
    feasibility = FEASIBILITY["deterministic"] if gap_type in DETERMINISTIC_GAPS else FEASIBILITY["ai_enrichment"]

    # Freshness decay
    if created_at:
        now = datetime.now(timezone.utc)
        if hasattr(created_at, 'tzinfo') and created_at.tzinfo is None:
            age_days = (now.replace(tzinfo=None) - created_at).days
        else:
            age_days = (now - created_at).days
        freshness = math.exp(-age_days / 30)
    else:
        freshness = 1.0

    return query_frequency * severity * feasibility * freshness
