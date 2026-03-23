"""Tests for materialized view fallback — SPEC-004 R4.

TDD: Tests written FIRST, then realtime_competitive_landscape/pipeline implementation.
When MVs return sparse results, fall back to real-time SQL against base tables.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock


class TestRealtimeLandscape:
    """Verify real-time competitive landscape from base tables."""

    def test_returns_segments_from_base_tables(self):
        from services.metrics import realtime_competitive_landscape
        db = MagicMock()
        db.fetch_all.return_value = [
            {"mechanism_name": "GLP-1 RA", "therapeutic_area": "Diabetes",
             "drug_count": 5, "trial_count": 20, "active_trial_count": 8,
             "total_pipeline_score": 42.5},
        ]
        segments = realtime_competitive_landscape(db, "GLP-1")
        assert len(segments) >= 1
        assert segments[0]["mechanism_name"] == "GLP-1 RA"
        assert segments[0]["drug_count"] == 5

    def test_groups_by_mechanism_and_ta(self):
        from services.metrics import realtime_competitive_landscape
        db = MagicMock()
        db.fetch_all.return_value = [
            {"mechanism_name": "GLP-1 RA", "therapeutic_area": "Diabetes",
             "drug_count": 5, "trial_count": 20, "active_trial_count": 8,
             "total_pipeline_score": 42.5},
            {"mechanism_name": "SGLT2i", "therapeutic_area": "Diabetes",
             "drug_count": 4, "trial_count": 15, "active_trial_count": 5,
             "total_pipeline_score": 30.0},
        ]
        segments = realtime_competitive_landscape(db, "diabetes")
        assert len(segments) == 2

    def test_empty_when_no_matches(self):
        from services.metrics import realtime_competitive_landscape
        db = MagicMock()
        db.fetch_all.return_value = []
        segments = realtime_competitive_landscape(db, "nonexistent_topic")
        assert segments == []

    def test_includes_drug_and_trial_counts(self):
        from services.metrics import realtime_competitive_landscape
        db = MagicMock()
        db.fetch_all.return_value = [
            {"mechanism_name": "GLP-1 RA", "therapeutic_area": "Diabetes",
             "drug_count": 5, "trial_count": 20, "active_trial_count": 8,
             "total_pipeline_score": 42.5},
        ]
        segments = realtime_competitive_landscape(db, "GLP-1")
        seg = segments[0]
        assert "drug_count" in seg
        assert "trial_count" in seg
        assert "total_pipeline_score" in seg


class TestRealtimePipeline:
    """Verify real-time pipeline strength from base tables."""

    def test_returns_drugs_with_phase_counts(self):
        from services.metrics import realtime_pipeline_strength
        db = MagicMock()
        db.fetch_all.return_value = [
            {"drug_name": "semaglutide", "drug_id": "d1",
             "total_trials": 47, "active_trials": 12,
             "p1_count": 0, "p2_count": 2, "p3_count": 5, "p4_count": 40,
             "pipeline_score": 42.5},
        ]
        drugs = realtime_pipeline_strength(db, "Diabetes")
        assert len(drugs) >= 1
        assert drugs[0]["drug_name"] == "semaglutide"
        assert "p3_count" in drugs[0]

    def test_filters_by_therapeutic_area(self):
        from services.metrics import realtime_pipeline_strength
        db = MagicMock()
        db.fetch_all.return_value = []
        drugs = realtime_pipeline_strength(db, "Nonexistent TA")
        assert drugs == []
        # Verify the SQL includes TA filter
        sql = db.fetch_all.call_args[0][0]
        assert "therapeutic_area" in sql.lower() or "ta" in sql.lower()

    def test_empty_when_no_drugs(self):
        from services.metrics import realtime_pipeline_strength
        db = MagicMock()
        db.fetch_all.return_value = []
        drugs = realtime_pipeline_strength(db, "Unknown")
        assert drugs == []


class TestMVFallback:
    """Verify fallback logic: MV first, realtime if sparse."""

    def test_uses_mv_when_sufficient(self):
        """MV returns 5+ rows → no fallback needed."""
        from services.metrics import competitive_landscape_with_fallback
        db = MagicMock()
        mv_results = [{"mechanism_name": f"mech_{i}", "drug_count": i + 1} for i in range(5)]
        segments = competitive_landscape_with_fallback(db, "topic", mv_results=mv_results)
        assert len(segments) == 5
        # Should not call db.fetch_all (no realtime query)
        db.fetch_all.assert_not_called()

    def test_falls_back_when_mv_sparse(self):
        """MV returns ≤2 rows → calls realtime."""
        from services.metrics import competitive_landscape_with_fallback
        db = MagicMock()
        db.fetch_all.return_value = [
            {"mechanism_name": "GLP-1 RA", "therapeutic_area": "Diabetes",
             "drug_count": 5, "trial_count": 20, "active_trial_count": 8,
             "total_pipeline_score": 42.5},
        ]
        mv_results = [{"mechanism_name": "mech_1", "drug_count": 1}]
        segments = competitive_landscape_with_fallback(db, "GLP-1", mv_results=mv_results)
        # Should have called realtime
        assert db.fetch_all.call_count >= 1
