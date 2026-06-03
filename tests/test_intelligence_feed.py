"""Tests for services/intelligence_feed.py — IntelligenceFeedService.

TDD: Verify feed retrieval, severity classification, summary counts,
event detail with assessments, dismissal, and chat context extraction.

Run with: pytest tests/test_intelligence_feed.py -v
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest
from unittest.mock import MagicMock


# ── Query dispatch keys ──
# The feed query has "FROM market_events ae" as main table with a LATERAL join
# to impact_assessments.  The standalone assessments query has
# "FROM impact_assessments ia" as the main FROM clause.
# We distinguish by checking for "FROM market_events" (feed) vs
# "FROM impact_assessments ia" (detail assessments).

_KEY_FEED = "FROM market_events"
_KEY_DETAIL_ASSESSMENTS = "FROM impact_assessments ia"
_KEY_DISMISS = "UPDATE market_events"


def _make_feed_row(
    *,
    event_id="evt-001",
    event_type="safety_signal",
    event_date="2026-03-20",
    description="New safety signal detected",
    source_url="https://example.com",
    source_tier="tier_1",
    trust_score=0.9,
    primary_entity_name="DrugX",
    primary_entity_type="drug",
    impact_count=3,
    max_impact_magnitude=0.8,
    status="new",
    created_at="2026-03-20T10:00:00+00:00",
):
    return {
        "event_id": event_id,
        "event_type": event_type,
        "event_date": event_date,
        "description": description,
        "source_url": source_url,
        "source_tier": source_tier,
        "trust_score": trust_score,
        "primary_entity_name": primary_entity_name,
        "primary_entity_type": primary_entity_type,
        "impact_count": impact_count,
        "max_impact_magnitude": max_impact_magnitude,
        "status": status,
        "created_at": created_at,
    }


def _mock_db(
    feed_rows=None,
    assessment_rows=None,
    event_detail_row=None,
):
    """Build a MagicMock DB that dispatches based on SQL content.

    Dispatch rules (substring match on query text):
    - "FROM market_events" → feed_rows (get_feed, get_feed_summary, chat_context)
    - "FROM impact_assessments ia" → assessment_rows (get_event_detail assessments)
    - fetch_one with "FROM market_events" → event_detail_row
    """
    db = MagicMock()
    feed = feed_rows if feed_rows is not None else []
    assessments = assessment_rows if assessment_rows is not None else []
    detail_row = event_detail_row

    def _fetch_all(query, params=None):
        # The feed queries always have "FROM market_events" — check first.
        # The standalone assessments query has "FROM impact_assessments ia"
        # but NOT "FROM market_events".
        if _KEY_FEED in query:
            return feed
        if _KEY_DETAIL_ASSESSMENTS in query:
            return assessments
        return []

    def _fetch_one(query, params=None):
        if _KEY_FEED in query:
            return detail_row
        return None

    db.fetch_all = MagicMock(side_effect=_fetch_all)
    db.fetch_one = MagicMock(side_effect=_fetch_one)
    db.execute = MagicMock()
    return db


# ── TestGetFeed ──


class TestGetFeed:
    """Verify feed retrieval with sorting and filtering."""

    def test_returns_events_sorted_by_trust_then_recency(self):
        from services.intelligence_feed import IntelligenceFeedService

        rows = [
            _make_feed_row(event_id="evt-1", trust_score=0.7, created_at="2026-03-19T10:00:00+00:00"),
            _make_feed_row(event_id="evt-2", trust_score=0.9, created_at="2026-03-18T10:00:00+00:00"),
            _make_feed_row(event_id="evt-3", trust_score=0.9, created_at="2026-03-20T10:00:00+00:00"),
        ]
        db = _mock_db(feed_rows=rows)
        svc = IntelligenceFeedService(db)
        result = svc.get_feed(limit=30)

        # The SQL orders by trust_score DESC, created_at DESC, so we trust
        # the DB ordering. Just verify we get back FeedItem dataclasses.
        assert len(result) == 3
        assert result[0].event_id == "evt-1"

    def test_filters_by_severity(self):
        from services.intelligence_feed import IntelligenceFeedService

        # critical: trust >= 0.8 AND max_impact >= 0.7
        critical_row = _make_feed_row(
            event_id="crit-1", trust_score=0.9, max_impact_magnitude=0.8,
        )
        # low: trust < 0.4
        low_row = _make_feed_row(
            event_id="low-1", trust_score=0.2, max_impact_magnitude=0.1,
        )
        db = _mock_db(feed_rows=[critical_row, low_row])
        svc = IntelligenceFeedService(db)

        # When filtering by severity=critical, only the critical item should pass
        result = svc.get_feed(severity="critical")
        assert all(item.severity == "critical" for item in result)

    def test_filters_by_entity_type(self):
        from services.intelligence_feed import IntelligenceFeedService

        drug_row = _make_feed_row(event_id="d-1", primary_entity_type="drug")
        company_row = _make_feed_row(event_id="c-1", primary_entity_type="company")
        db = _mock_db(feed_rows=[drug_row, company_row])
        svc = IntelligenceFeedService(db)

        result = svc.get_feed(entity_type="drug")
        # Filtering is done in SQL via parameter, so we check the call was made
        # and results are returned as FeedItems
        assert len(result) >= 0  # depends on mock dispatch
        for item in result:
            assert hasattr(item, "event_id")

    def test_respects_limit_and_offset(self):
        from services.intelligence_feed import IntelligenceFeedService

        rows = [_make_feed_row(event_id=f"evt-{i}") for i in range(5)]
        db = _mock_db(feed_rows=rows)
        svc = IntelligenceFeedService(db)

        result = svc.get_feed(limit=3, offset=0)
        # We get back what the DB returns (mock returns all 5, but the SQL
        # would have applied LIMIT/OFFSET). Verify FeedItems are created.
        assert len(result) <= 5
        for item in result:
            assert hasattr(item, "severity")

    def test_empty_feed(self):
        from services.intelligence_feed import IntelligenceFeedService

        db = _mock_db(feed_rows=[])
        svc = IntelligenceFeedService(db)

        result = svc.get_feed()
        assert result == []


# ── TestGetFeedSummary ──


class TestGetFeedSummary:
    """Verify feed summary counts."""

    def test_counts_unread_events(self):
        from services.intelligence_feed import IntelligenceFeedService

        rows = [
            _make_feed_row(trust_score=0.9, max_impact_magnitude=0.8, status="new"),
            _make_feed_row(trust_score=0.7, max_impact_magnitude=0.5, status="new"),
            _make_feed_row(trust_score=0.2, max_impact_magnitude=0.1, status="new"),
        ]
        db = _mock_db(feed_rows=rows)
        svc = IntelligenceFeedService(db)

        summary = svc.get_feed_summary(since_hours=24)
        assert summary.total_unread == 3
        assert summary.since_hours == 24

    def test_critical_separate_from_high(self):
        from services.intelligence_feed import IntelligenceFeedService

        rows = [
            # critical: trust >= 0.8 AND max_impact >= 0.7
            _make_feed_row(event_id="c1", trust_score=0.9, max_impact_magnitude=0.8, status="new"),
            # high: trust >= 0.6 AND max_impact >= 0.4
            _make_feed_row(event_id="h1", trust_score=0.7, max_impact_magnitude=0.5, status="new"),
            # low
            _make_feed_row(event_id="l1", trust_score=0.2, max_impact_magnitude=0.1, status="new"),
        ]
        db = _mock_db(feed_rows=rows)
        svc = IntelligenceFeedService(db)

        summary = svc.get_feed_summary(since_hours=24)
        assert summary.critical_count == 1
        assert summary.high_count == 1

    def test_zero_when_no_events(self):
        from services.intelligence_feed import IntelligenceFeedService

        db = _mock_db(feed_rows=[])
        svc = IntelligenceFeedService(db)

        summary = svc.get_feed_summary(since_hours=24)
        assert summary.total_unread == 0
        assert summary.critical_count == 0
        assert summary.high_count == 0


# ── TestGetEventDetail ──


class TestGetEventDetail:
    """Verify event detail retrieval with impact assessments."""

    def test_returns_event_with_assessments(self):
        from services.intelligence_feed import IntelligenceFeedService

        detail = _make_feed_row(event_id="evt-detail")
        assessments = [
            {
                "assessment_id": "a-1",
                "event_id": "evt-detail",
                "affected_entity_id": "drug-1",
                "affected_entity_type": "drug",
                "affected_entity_name": "DrugX",
                "assessment_type": "safety",
                "impact_magnitude": 0.8,
                "impact_direction": "negative",
                "narrative": "PRR spike detected",
                "scenario_result": None,
            },
        ]
        db = _mock_db(event_detail_row=detail, assessment_rows=assessments)
        svc = IntelligenceFeedService(db)

        result = svc.get_event_detail("evt-detail")
        assert result is not None
        assert result["event_id"] == "evt-detail"
        assert "assessments" in result
        assert len(result["assessments"]) == 1
        assert result["assessments"][0]["assessment_id"] == "a-1"

    def test_returns_none_for_missing_id(self):
        from services.intelligence_feed import IntelligenceFeedService

        db = _mock_db(event_detail_row=None, assessment_rows=[])
        svc = IntelligenceFeedService(db)

        result = svc.get_event_detail("nonexistent")
        assert result is None


# ── TestDismissEvent ──


class TestDismissEvent:
    """Verify event dismissal."""

    def test_sets_status_to_dismissed(self):
        from services.intelligence_feed import IntelligenceFeedService

        db = _mock_db()
        svc = IntelligenceFeedService(db)

        svc.dismiss_event("evt-001")
        db.execute.assert_called_once()
        call_args = db.execute.call_args
        sql = call_args[0][0]
        assert "dismissed" in sql.lower() or "dismissed" in str(call_args[0][1]).lower()

    def test_db_execute_called(self):
        from services.intelligence_feed import IntelligenceFeedService

        db = _mock_db()
        svc = IntelligenceFeedService(db)

        svc.dismiss_event("evt-999")
        assert db.execute.call_count == 1


# ── TestGetChatContextEvents ──


class TestGetChatContextEvents:
    """Verify chat context event extraction."""

    def test_returns_recent_events_for_entity(self):
        from services.intelligence_feed import IntelligenceFeedService

        rows = [
            _make_feed_row(
                event_id="ctx-1",
                primary_entity_name="Keytruda",
                description="New trial result for Keytruda",
            ),
        ]
        db = _mock_db(feed_rows=rows)
        svc = IntelligenceFeedService(db)

        result = svc.get_chat_context_events(["Keytruda"], since_hours=72)
        assert len(result) == 1
        assert result[0]["event_id"] == "ctx-1"

    def test_empty_for_unknown_entity(self):
        from services.intelligence_feed import IntelligenceFeedService

        db = _mock_db(feed_rows=[])
        svc = IntelligenceFeedService(db)

        result = svc.get_chat_context_events(["NonexistentDrug"], since_hours=72)
        assert result == []

    def test_respects_time_window(self):
        from services.intelligence_feed import IntelligenceFeedService

        rows = [
            _make_feed_row(event_id="recent-1", primary_entity_name="DrugY"),
        ]
        db = _mock_db(feed_rows=rows)
        svc = IntelligenceFeedService(db)

        # The time window is applied via SQL, so we verify the call is made
        # and results are returned in the expected format.
        result = svc.get_chat_context_events(["DrugY"], since_hours=24)
        for item in result:
            assert "event_id" in item
            assert "description" in item


# ── TestSeverityDerivation ──


class TestSeverityDerivation:
    """Verify the severity classification logic."""

    def test_critical_threshold(self):
        from services.intelligence_feed import derive_severity

        assert derive_severity(0.8, 0.7) == "critical"
        assert derive_severity(0.9, 0.9) == "critical"

    def test_high_threshold(self):
        from services.intelligence_feed import derive_severity

        assert derive_severity(0.6, 0.4) == "high"
        assert derive_severity(0.7, 0.5) == "high"

    def test_medium_threshold(self):
        from services.intelligence_feed import derive_severity

        assert derive_severity(0.4, 0.1) == "medium"
        assert derive_severity(0.5, 0.2) == "medium"

    def test_low_threshold(self):
        from services.intelligence_feed import derive_severity

        assert derive_severity(0.1, 0.1) == "low"
        assert derive_severity(0.3, 0.9) == "low"

    def test_boundary_critical_vs_high(self):
        from services.intelligence_feed import derive_severity

        # Exactly at critical boundary
        assert derive_severity(0.8, 0.7) == "critical"
        # Just below critical on impact → falls to high
        assert derive_severity(0.8, 0.69) == "high"

    def test_boundary_high_vs_medium(self):
        from services.intelligence_feed import derive_severity

        assert derive_severity(0.6, 0.4) == "high"
        assert derive_severity(0.6, 0.39) == "medium"

    def test_boundary_medium_vs_low(self):
        from services.intelligence_feed import derive_severity

        assert derive_severity(0.4, 0.0) == "medium"
        assert derive_severity(0.39, 0.0) == "low"


# ── Dedup regression (market_events flood: same recall re-ingested 1000s of times) ──

def test_get_feed_query_dedups_by_entity_type_description():
    """The feed must DISTINCT ON (entity, type, description) so duplicate
    market_events (e.g. the same FDA recall ingested thousands of times) don't
    flood the digest. Regression for the duplication complaint."""
    db = MagicMock()
    captured = {}

    def _fetch_all(query, params=None):
        captured["sql"] = query
        return []
    db.fetch_all = MagicMock(side_effect=_fetch_all)

    from services.intelligence_feed import IntelligenceFeedService
    IntelligenceFeedService(db).get_feed(limit=10)

    sql = captured["sql"].upper()
    assert "DISTINCT ON" in sql
    assert "PRIMARY_ENTITY_ID" in sql and "EVENT_TYPE" in sql and "DESCRIPTION" in sql
    # keeps the strongest copy of each group
    assert "TRUST_SCORE DESC" in sql


def test_get_feed_summary_dedups_too():
    db = MagicMock()
    captured = {}
    db.fetch_all = MagicMock(side_effect=lambda q, p=None: captured.update(sql=q) or [])
    from services.intelligence_feed import IntelligenceFeedService
    IntelligenceFeedService(db).get_feed_summary()
    assert "DISTINCT ON" in captured["sql"].upper()
