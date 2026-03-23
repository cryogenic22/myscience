"""Tests for temporal evidence scoring — SPEC-004 R9.

TDD: Evidence scored by recency so recent data ranks higher than old data.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest


class TestRecencyScore:
    """Verify recency scoring function."""

    def test_recent_scores_high(self):
        from services.search import recency_score
        now = datetime.now(timezone.utc)
        score = recency_score(now - timedelta(days=5))
        assert score >= 0.9

    def test_month_old_scores_medium(self):
        from services.search import recency_score
        now = datetime.now(timezone.utc)
        score = recency_score(now - timedelta(days=60))
        assert 0.3 <= score <= 0.8

    def test_year_old_scores_low(self):
        from services.search import recency_score
        now = datetime.now(timezone.utc)
        score = recency_score(now - timedelta(days=400))
        assert score <= 0.3

    def test_none_date_returns_default(self):
        from services.search import recency_score
        score = recency_score(None)
        assert score == 0.5  # neutral default

    def test_future_date_clamps_to_1(self):
        from services.search import recency_score
        future = datetime.now(timezone.utc) + timedelta(days=10)
        score = recency_score(future)
        assert score == 1.0


class TestTemporalRanking:
    """Verify evidence sorted by relevance × recency."""

    def test_recent_evidence_ranked_higher(self):
        from services.search import rank_by_recency
        now = datetime.now(timezone.utc)
        evidence = [
            {"content": "old", "similarity": 0.9, "retrieved_at": (now - timedelta(days=365)).isoformat()},
            {"content": "new", "similarity": 0.9, "retrieved_at": (now - timedelta(days=1)).isoformat()},
        ]
        ranked = rank_by_recency(evidence)
        assert ranked[0]["content"] == "new"

    def test_high_relevance_still_wins_over_recency(self):
        from services.search import rank_by_recency
        now = datetime.now(timezone.utc)
        evidence = [
            {"content": "old_relevant", "similarity": 0.99, "retrieved_at": (now - timedelta(days=200)).isoformat()},
            {"content": "new_irrelevant", "similarity": 0.3, "retrieved_at": (now - timedelta(days=1)).isoformat()},
        ]
        ranked = rank_by_recency(evidence)
        assert ranked[0]["content"] == "old_relevant"

    def test_empty_list(self):
        from services.search import rank_by_recency
        assert rank_by_recency([]) == []

    def test_missing_date_gets_neutral_score(self):
        from services.search import rank_by_recency
        evidence = [
            {"content": "no_date", "similarity": 0.8},
            {"content": "has_date", "similarity": 0.8, "retrieved_at": datetime.now(timezone.utc).isoformat()},
        ]
        ranked = rank_by_recency(evidence)
        # has_date should rank higher (recency 1.0 vs 0.5)
        assert ranked[0]["content"] == "has_date"
