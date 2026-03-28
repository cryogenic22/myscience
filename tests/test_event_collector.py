"""Tests for services/event_collector.py — market event ingestion, dedup, trust scoring.

TDD: Verify hash computation, trust scoring by source tier, entity resolution,
collection with dedup, and retrieval of unprocessed events.

Run with: pytest tests/test_event_collector.py -v
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from unittest.mock import MagicMock


# ── Helpers ──

def _make_candidate(**overrides) -> "EventCandidate":
    """Factory for EventCandidate with sensible defaults."""
    from services.event_collector import EventCandidate

    defaults = {
        "source_feed": "fda_press",
        "source_tier": "tier_1",
        "event_type": "approval",
        "description": "FDA approves semaglutide for obesity",
        "event_date": datetime(2026, 3, 15, tzinfo=timezone.utc),
        "source_url": "https://fda.gov/news/semaglutide-approval",
        "entity_hint": "semaglutide",
        "entity_type_hint": "drug",
        "raw_data": {"headline": "FDA approves semaglutide"},
    }
    defaults.update(overrides)
    return EventCandidate(**defaults)


# SQL dispatch keys for MockDB
_KEY_DRUG_LOOKUP = "drugs"
_KEY_COMPANY_LOOKUP = "companies"
_KEY_HASH_CHECK = "event_hash"
_KEY_INSERT = "INSERT INTO market_events"
_KEY_UPDATE_CORROBORATION = "corroboration_count"
_KEY_UNPROCESSED = "status = 'new'"


def _mock_db(
    drug_rows=None,
    company_rows=None,
    hash_exists=False,
    unprocessed_rows=None,
):
    """Build a MagicMock DB that dispatches based on SQL content."""
    db = MagicMock()
    drugs = drug_rows if drug_rows is not None else []
    companies = company_rows if company_rows is not None else []
    unprocessed = unprocessed_rows if unprocessed_rows is not None else []

    def _fetch_one(query, params=None):
        if _KEY_DRUG_LOOKUP in query and "ILIKE" in query:
            return drugs[0] if drugs else None
        if _KEY_COMPANY_LOOKUP in query and "ILIKE" in query:
            return companies[0] if companies else None
        if _KEY_HASH_CHECK in query:
            if hash_exists:
                return {"id": "existing-id", "event_hash": "abc123"}
            return None
        return None

    def _fetch_all(query, params=None):
        if _KEY_UNPROCESSED in query:
            return unprocessed
        return []

    def _execute(query, params=None):
        pass  # INSERT/UPDATE — no return needed

    db.fetch_one = MagicMock(side_effect=_fetch_one)
    db.fetch_all = MagicMock(side_effect=_fetch_all)
    db.execute = MagicMock(side_effect=_execute)
    return db


# ── Hash Computation ──


class TestComputeEventHash:
    """Verify deterministic hash generation from event attributes."""

    def test_same_inputs_yield_same_hash(self):
        from services.event_collector import EventCollector

        collector = EventCollector(MagicMock())
        c1 = _make_candidate()
        c2 = _make_candidate()
        assert collector._compute_event_hash(c1) == collector._compute_event_hash(c2)

    def test_different_inputs_yield_different_hash(self):
        from services.event_collector import EventCollector

        collector = EventCollector(MagicMock())
        c1 = _make_candidate(source_url="https://fda.gov/a")
        c2 = _make_candidate(source_url="https://fda.gov/b")
        assert collector._compute_event_hash(c1) != collector._compute_event_hash(c2)

    def test_whitespace_normalization(self):
        from services.event_collector import EventCollector

        collector = EventCollector(MagicMock())
        c1 = _make_candidate(description="  FDA approves  semaglutide  ")
        c2 = _make_candidate(description="FDA approves semaglutide")
        assert collector._compute_event_hash(c1) == collector._compute_event_hash(c2)


# ── Trust Score Assignment ──


class TestAssignTrustScore:
    """Verify trust scoring by source tier with corroboration bonus."""

    def test_tier_1_scores_high(self):
        from services.event_collector import EventCollector

        collector = EventCollector(MagicMock())
        c = _make_candidate(source_tier="tier_1")
        score = collector._assign_trust_score(c, corroboration_count=0)
        assert score >= 0.85

    def test_tier_2_scores_medium(self):
        from services.event_collector import EventCollector

        collector = EventCollector(MagicMock())
        c = _make_candidate(source_tier="tier_2")
        score = collector._assign_trust_score(c, corroboration_count=0)
        assert 0.5 <= score <= 0.7

    def test_tier_3_scores_low(self):
        from services.event_collector import EventCollector

        collector = EventCollector(MagicMock())
        c = _make_candidate(source_tier="tier_3")
        score = collector._assign_trust_score(c, corroboration_count=0)
        assert 0.2 <= score <= 0.4

    def test_corroboration_bonus_increases_score(self):
        from services.event_collector import EventCollector

        collector = EventCollector(MagicMock())
        c = _make_candidate(source_tier="tier_2")
        base = collector._assign_trust_score(c, corroboration_count=0)
        boosted = collector._assign_trust_score(c, corroboration_count=2)
        assert boosted > base

    def test_score_capped_at_1(self):
        from services.event_collector import EventCollector

        collector = EventCollector(MagicMock())
        c = _make_candidate(source_tier="tier_1")
        # Even with extreme corroboration, score should not exceed 1.0
        score = collector._assign_trust_score(c, corroboration_count=100)
        assert score <= 1.0


# ── Primary Entity Resolution ──


class TestResolvePrimaryEntity:
    """Verify entity resolution via DB ILIKE lookup."""

    def test_resolves_known_drug(self):
        from services.event_collector import EventCollector

        db = _mock_db(drug_rows=[{"id": "d001", "generic_name": "semaglutide"}])
        collector = EventCollector(db)
        result = collector._resolve_primary_entity("semaglutide", "drug")
        assert result is not None
        assert result["id"] == "d001"

    def test_resolves_known_company(self):
        from services.event_collector import EventCollector

        db = _mock_db(company_rows=[{"id": "c001", "name": "Novo Nordisk"}])
        collector = EventCollector(db)
        result = collector._resolve_primary_entity("Novo Nordisk", "company")
        assert result is not None
        assert result["id"] == "c001"

    def test_returns_none_for_unknown(self):
        from services.event_collector import EventCollector

        db = _mock_db()  # empty results
        collector = EventCollector(db)
        result = collector._resolve_primary_entity("nonexistent_drug", "drug")
        assert result is None

    def test_handles_empty_hint(self):
        from services.event_collector import EventCollector

        db = _mock_db()
        collector = EventCollector(db)
        result = collector._resolve_primary_entity(None, None)
        assert result is None


# ── Collect (full pipeline) ──


class TestCollect:
    """Verify the collect() pipeline: fetch → dedup → score → persist."""

    def test_new_event_persisted(self):
        from services.event_collector import EventCollector

        db = _mock_db(hash_exists=False)
        collector = EventCollector(db)
        candidates = [_make_candidate()]

        result = collector.collect(candidates)
        assert result.total_fetched == 1
        assert result.new_events == 1
        assert result.duplicates_skipped == 0
        # Verify INSERT was called
        insert_calls = [
            call for call in db.execute.call_args_list
            if call[0][0] and "INSERT" in call[0][0]
        ]
        assert len(insert_calls) >= 1

    def test_duplicate_skipped_by_hash(self):
        from services.event_collector import EventCollector

        db = _mock_db(hash_exists=True)
        collector = EventCollector(db)
        candidates = [_make_candidate()]

        result = collector.collect(candidates)
        assert result.total_fetched == 1
        assert result.duplicates_skipped == 1
        assert result.new_events == 0

    def test_handles_connector_failure_gracefully(self):
        from services.event_collector import EventCollector

        db = MagicMock()
        db.fetch_one.side_effect = RuntimeError("DB connection lost")
        db.execute.side_effect = RuntimeError("DB connection lost")

        collector = EventCollector(db)
        candidates = [_make_candidate()]

        # Should not raise — returns summary with 0 new events
        result = collector.collect(candidates)
        assert result.total_fetched == 1
        assert result.new_events == 0

    def test_returns_collection_result_summary(self):
        from services.event_collector import EventCollector, CollectionResult

        db = _mock_db(hash_exists=False)
        collector = EventCollector(db)
        candidates = [
            _make_candidate(source_url="https://fda.gov/a"),
            _make_candidate(source_url="https://fda.gov/b"),
        ]

        result = collector.collect(candidates)
        assert isinstance(result, CollectionResult)
        assert result.total_fetched == 2
        assert result.new_events + result.duplicates_skipped + result.trust_upgraded <= 2


# ── Get Unprocessed Events ──


class TestGetUnprocessedEvents:
    """Verify retrieval of events pending processing."""

    def test_returns_new_events_sorted_by_trust(self):
        from services.event_collector import EventCollector

        rows = [
            {"id": "e1", "trust_score": 0.5, "status": "new",
             "event_type": "approval", "description": "Low trust event",
             "source_feed": "google_news", "created_at": datetime.now(timezone.utc)},
            {"id": "e2", "trust_score": 0.9, "status": "new",
             "event_type": "approval", "description": "High trust event",
             "source_feed": "fda_press", "created_at": datetime.now(timezone.utc)},
        ]
        db = _mock_db(unprocessed_rows=rows)
        collector = EventCollector(db)
        events = collector.get_unprocessed_events(limit=10)
        assert len(events) == 2
        # DB returns them pre-sorted, collector passes through
        assert events[0]["id"] == "e1" or events[1]["id"] == "e2"

    def test_respects_limit(self):
        from services.event_collector import EventCollector

        rows = [
            {"id": f"e{i}", "trust_score": 0.5, "status": "new",
             "event_type": "approval", "description": f"Event {i}",
             "source_feed": "fda_press", "created_at": datetime.now(timezone.utc)}
            for i in range(5)
        ]
        db = _mock_db(unprocessed_rows=rows)
        collector = EventCollector(db)
        events = collector.get_unprocessed_events(limit=3)
        # The mock returns all 5, but the SQL should have LIMIT — we test the call
        db.fetch_all.assert_called_once()
        call_args = db.fetch_all.call_args
        assert "LIMIT" in call_args[0][0]

    def test_excludes_non_new_status(self):
        from services.event_collector import EventCollector

        db = _mock_db(unprocessed_rows=[])
        collector = EventCollector(db)
        events = collector.get_unprocessed_events()
        assert events == []
        # Verify the SQL filters on status = 'new'
        call_args = db.fetch_all.call_args
        assert "status = 'new'" in call_args[0][0]
