"""Tests for services/steward_signals.py — signal collection and priority ranking.

TDD: Verify objective function, collection from each source, deduplication.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone, timedelta

import pytest
from unittest.mock import MagicMock


# ── Objective Function (pure logic) ──


class TestComputePriority:
    """Verify the priority scoring objective function."""

    def test_missing_entity_highest_severity(self):
        from services.steward_signals import compute_priority
        score_missing = compute_priority("missing_entity", query_frequency=1)
        score_stale = compute_priority("stale_data", query_frequency=1)
        assert score_missing > score_stale

    def test_query_frequency_multiplier(self):
        from services.steward_signals import compute_priority
        score_1 = compute_priority("missing_entity", query_frequency=1)
        score_5 = compute_priority("missing_entity", query_frequency=5)
        assert score_5 == pytest.approx(score_1 * 5, rel=0.01)

    def test_freshness_decay(self):
        from services.steward_signals import compute_priority
        now = datetime.now(timezone.utc)
        recent = compute_priority("missing_entity", created_at=now)
        old = compute_priority("missing_entity", created_at=now - timedelta(days=60))
        assert recent > old

    def test_freshness_decay_formula(self):
        from services.steward_signals import compute_priority
        now = datetime.now(timezone.utc)
        score_30d = compute_priority("missing_entity", query_frequency=1,
                                      created_at=now - timedelta(days=30))
        # At 30 days, decay = exp(-1) ≈ 0.368
        score_0d = compute_priority("missing_entity", query_frequency=1, created_at=now)
        ratio = score_30d / score_0d
        assert ratio == pytest.approx(math.exp(-1), abs=0.05)

    def test_deterministic_gap_higher_feasibility(self):
        from services.steward_signals import compute_priority
        # low_completeness is deterministic, missing_entity is AI
        score_det = compute_priority("low_completeness", query_frequency=1)
        score_ai = compute_priority("low_confidence", query_frequency=1)
        # deterministic has feasibility 1.0, AI has 0.5
        # but severity matters too — low_completeness=0.6, low_confidence=0.7
        # det: 1 * 0.6 * 1.0 = 0.6, ai: 1 * 0.7 * 0.5 = 0.35
        assert score_det > score_ai

    def test_zero_frequency_returns_zero(self):
        from services.steward_signals import compute_priority
        score = compute_priority("missing_entity", query_frequency=0)
        assert score == 0.0

    def test_unknown_gap_type_uses_default(self):
        from services.steward_signals import compute_priority
        score = compute_priority("unknown_type", query_frequency=1)
        assert score > 0  # uses default severity 0.5


# ── Signal Collection ──


class TestCollectQueryGaps:
    """Verify query_telemetry signal collection."""

    def test_collects_from_telemetry(self):
        from services.steward_signals import StewardSignalCollector
        db = MagicMock()
        now = datetime.now(timezone.utc)
        db.fetch_all.return_value = [
            {"gap_type": "missing_entity", "gap_details": '{"missing": ["tirzepatide"]}',
             "frequency": 5, "first_seen": now},
        ]

        collector = StewardSignalCollector(db)
        signals = collector._collect_query_gaps(since_days=7)
        assert len(signals) == 1
        assert signals[0].gap_type == "missing_entity"
        assert signals[0].entity_name == "tirzepatide"
        assert signals[0].details["frequency"] == 5

    def test_handles_db_error_gracefully(self):
        from services.steward_signals import StewardSignalCollector
        db = MagicMock()
        db.fetch_all.side_effect = RuntimeError("connection pool exhausted")

        collector = StewardSignalCollector(db)
        signals = collector._collect_query_gaps(since_days=7)
        assert signals == []


class TestCollectFeedbackSignals:
    """Verify feedback signal collection."""

    def test_collects_data_quality_feedback(self):
        from services.steward_signals import StewardSignalCollector
        db = MagicMock()
        now = datetime.now(timezone.utc)
        db.fetch_all.return_value = [
            {"id": "fb-1", "category": "data_quality", "title": "Missing mechanism",
             "description": "Semaglutide has no mechanism_id",
             "entity_context": '{"entity_type": "drug", "entity_id": "d001", "entity_name": "semaglutide"}',
             "priority": "high", "created_at": now},
        ]

        collector = StewardSignalCollector(db)
        signals = collector._collect_feedback_signals(since_days=7)
        assert len(signals) == 1
        assert signals[0].source == "feedback"
        assert signals[0].entity_name == "semaglutide"
        assert signals[0].gap_type == "data_quality"

    def test_critical_priority_boost(self):
        from services.steward_signals import StewardSignalCollector
        db = MagicMock()
        now = datetime.now(timezone.utc)
        db.fetch_all.return_value = [
            {"id": "fb-1", "category": "data_quality", "title": "Critical issue",
             "description": None, "entity_context": None,
             "priority": "critical", "created_at": now},
            {"id": "fb-2", "category": "data_quality", "title": "Low issue",
             "description": None, "entity_context": None,
             "priority": "low", "created_at": now},
        ]

        collector = StewardSignalCollector(db)
        signals = collector._collect_feedback_signals(since_days=7)
        assert len(signals) == 2
        critical = [s for s in signals if s.details["feedback_priority"] == "critical"][0]
        low = [s for s in signals if s.details["feedback_priority"] == "low"][0]
        assert critical.priority_score > low.priority_score


class TestCollectSignals:
    """Verify full signal collection and deduplication."""

    def test_deduplicates_by_entity_and_gap(self):
        from services.steward_signals import StewardSignalCollector
        db = MagicMock()
        now = datetime.now(timezone.utc)

        # query_telemetry returns one signal, feedback returns another for same entity
        db.fetch_all.side_effect = [
            # query gaps
            [{"gap_type": "missing_entity", "gap_details": '{"missing": ["semaglutide"]}',
              "frequency": 2, "first_seen": now}],
            # feedback signals
            [{"id": "fb-1", "category": "data_quality", "title": "Missing data",
              "description": None, "entity_context": None,
              "priority": "medium", "created_at": now}],
            # quality signals (empty)
            [],
        ]

        collector = StewardSignalCollector(db)
        signals = collector.collect_signals(limit=50, since_days=7)
        # Both have entity_id=None, but different gap_types, so both kept
        assert len(signals) >= 1

    def test_respects_limit(self):
        from services.steward_signals import StewardSignalCollector
        db = MagicMock()
        now = datetime.now(timezone.utc)

        db.fetch_all.side_effect = [
            [{"gap_type": f"missing_entity", "gap_details": f'{{"missing": ["drug{i}"]}}',
              "frequency": 1, "first_seen": now} for i in range(10)],
            [],  # no feedback
            [],  # no quality
        ]

        collector = StewardSignalCollector(db)
        signals = collector.collect_signals(limit=3, since_days=7)
        assert len(signals) <= 3

    def test_sorts_by_priority_desc(self):
        from services.steward_signals import StewardSignalCollector
        db = MagicMock()
        now = datetime.now(timezone.utc)

        db.fetch_all.side_effect = [
            [
                {"gap_type": "low_evidence", "gap_details": '{"evidence_count": 0}',
                 "frequency": 1, "first_seen": now},
                {"gap_type": "missing_entity", "gap_details": '{"missing": ["drug1"]}',
                 "frequency": 10, "first_seen": now},
            ],
            [],  # no feedback
            [],  # no quality
        ]

        collector = StewardSignalCollector(db)
        signals = collector.collect_signals(limit=50, since_days=7)
        assert len(signals) >= 2
        # Higher priority first
        assert signals[0].priority_score >= signals[1].priority_score

    def test_empty_when_no_gaps(self):
        from services.steward_signals import StewardSignalCollector
        db = MagicMock()
        db.fetch_all.return_value = []

        collector = StewardSignalCollector(db)
        signals = collector.collect_signals()
        assert signals == []
