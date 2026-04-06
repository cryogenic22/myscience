"""Tests for materialized view fallback — SPEC-004 R4.

TDD: Tests written FIRST, then realtime_competitive_landscape/pipeline implementation.
When MVs return sparse results, fall back to real-time SQL against base tables.

Also tests MV fallback telemetry (Task #131):
- log_mv_fallback writes events
- get_mv_health computes health summary
- /metrics/mv-health endpoint
- Alert flags when fallback_pct > 20%
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch, call


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



class TestLandscapeTriesBothTopics:
    """Verify competitive_landscape tries both expanded and original topic."""

    def test_landscape_tries_both_expanded_and_original(self):
        """When MV is sparse and expanded topic returns nothing, try original short form."""
        from services.metrics import PharmaMetrics

        db = MagicMock()
        config = MagicMock()
        metrics = PharmaMetrics(db, config)

        # MV query returns sparse results (1 row)
        mv_sparse = [
            {"mechanism_name": "GLP-1 RA", "therapeutic_area": "Diabetes",
             "drug_count": 1, "trial_count": 2, "active_trial_count": 1,
             "total_pipeline_score": 5.0, "market_share_pct": 100.0},
        ]

        # Realtime for expanded "Glucagon-Like Peptide-1" returns nothing
        rt_expanded_empty = []

        # Realtime for original "GLP-1" returns good results
        rt_original_good = [
            {"mechanism_name": "GLP-1 Receptor Agonists", "therapeutic_area": "Diabetes",
             "drug_count": 5, "trial_count": 20, "active_trial_count": 8,
             "total_pipeline_score": 42.5},
            {"mechanism_name": "GLP-1 Receptor Agonists", "therapeutic_area": "Obesity",
             "drug_count": 3, "trial_count": 10, "active_trial_count": 4,
             "total_pipeline_score": 22.0},
        ]

        # db.fetch_all call sequence: MV query, then realtime(expanded), then realtime(original)
        db.fetch_all.side_effect = [mv_sparse, rt_expanded_empty, rt_original_good]

        result = metrics.competitive_landscape(
            topic="Glucagon-Like Peptide-1",
            original_topic="GLP-1",
            limit=30,
        )

        # Should have fallen through to the original topic and returned those results
        assert len(result) >= 2
        assert result[0]["mechanism_name"] == "GLP-1 Receptor Agonists"
        # Should have made 3 db calls: MV + expanded realtime + original realtime
        assert db.fetch_all.call_count == 3

    def test_landscape_skips_original_when_expanded_works(self):
        """When expanded topic returns good results, don't try original."""
        from services.metrics import PharmaMetrics

        db = MagicMock()
        config = MagicMock()
        metrics = PharmaMetrics(db, config)

        # MV query returns sparse
        mv_sparse = [
            {"mechanism_name": "GLP-1 RA", "therapeutic_area": "Diabetes",
             "drug_count": 1, "trial_count": 2, "active_trial_count": 1,
             "total_pipeline_score": 5.0, "market_share_pct": 100.0},
        ]

        # Realtime for expanded returns good results
        rt_expanded_good = [
            {"mechanism_name": "GLP-1 Receptor Agonists", "therapeutic_area": "Diabetes",
             "drug_count": 5, "trial_count": 20, "active_trial_count": 8,
             "total_pipeline_score": 42.5},
            {"mechanism_name": "GLP-1 Receptor Agonists", "therapeutic_area": "Obesity",
             "drug_count": 3, "trial_count": 10, "active_trial_count": 4,
             "total_pipeline_score": 22.0},
            {"mechanism_name": "GLP-1 Receptor Agonists", "therapeutic_area": "Heart Failure",
             "drug_count": 2, "trial_count": 5, "active_trial_count": 2,
             "total_pipeline_score": 10.0},
        ]

        db.fetch_all.side_effect = [mv_sparse, rt_expanded_good]

        result = metrics.competitive_landscape(
            topic="Glucagon-Like Peptide-1",
            original_topic="GLP-1",
            limit=30,
        )

        # Should use expanded results and not try original
        assert len(result) == 3
        # Only 2 db calls: MV + expanded realtime (no original needed)
        assert db.fetch_all.call_count == 2

    def test_landscape_no_original_when_same_as_topic(self):
        """When original_topic == topic, don't double-query."""
        from services.metrics import PharmaMetrics

        db = MagicMock()
        config = MagicMock()
        metrics = PharmaMetrics(db, config)

        mv_sparse = [{"mechanism_name": "X", "therapeutic_area": "Y",
                       "drug_count": 1, "trial_count": 1, "active_trial_count": 0,
                       "total_pipeline_score": 1.0, "market_share_pct": 100.0}]
        rt_empty = []

        db.fetch_all.side_effect = [mv_sparse, rt_empty]

        result = metrics.competitive_landscape(
            topic="diabetes",
            original_topic="diabetes",
            limit=30,
        )

        # original_topic == topic (case-insensitive), so no third query
        assert db.fetch_all.call_count == 2


# ── MV Fallback Telemetry Tests (Task #131) ────────────────────────


class TestLogMvFallback:
    """Verify log_mv_fallback writes to the mv_fallback_events table."""

    def test_inserts_event_row(self):
        from services.telemetry import log_mv_fallback
        db = MagicMock()
        log_mv_fallback(
            db,
            method_name="competitive_landscape",
            mv_name="mv_competitive_landscape",
            reason="insufficient_data",
            row_count=1,
        )
        db.execute.assert_called_once()
        sql = db.execute.call_args[0][0]
        assert "mv_fallback_events" in sql
        params = db.execute.call_args[0][1]
        assert params[0] == "competitive_landscape"
        assert params[1] == "mv_competitive_landscape"
        assert params[2] == "insufficient_data"
        assert params[3] == 1

    def test_default_reason_is_insufficient_data(self):
        from services.telemetry import log_mv_fallback
        db = MagicMock()
        log_mv_fallback(db, method_name="test", mv_name="mv_test")
        params = db.execute.call_args[0][1]
        assert params[2] == "insufficient_data"
        assert params[3] == 0

    def test_never_raises_on_db_error(self):
        from services.telemetry import log_mv_fallback
        db = MagicMock()
        db.execute.side_effect = RuntimeError("table does not exist")
        # Should not raise
        log_mv_fallback(db, method_name="test", mv_name="mv_test")

    def test_logs_mv_error_reason(self):
        from services.telemetry import log_mv_fallback
        db = MagicMock()
        log_mv_fallback(
            db,
            method_name="company_portfolio",
            mv_name="mv_company_portfolio",
            reason="mv_error",
            row_count=0,
        )
        params = db.execute.call_args[0][1]
        assert params[2] == "mv_error"


class TestGetMvHealth:
    """Verify get_mv_health computes health summary correctly."""

    def test_returns_empty_when_no_events(self):
        from services.telemetry import get_mv_health
        db = MagicMock()
        db.fetch_all.return_value = []
        db.fetch_one.return_value = {"total": 0}

        result = get_mv_health(db, hours=24)
        assert result["views"] == {}
        assert result["alerts"] == []
        assert result["period_hours"] == 24

    def test_computes_fallback_counts(self):
        from services.telemetry import get_mv_health
        db = MagicMock()
        db.fetch_all.return_value = [
            {"mv_name": "mv_competitive_landscape", "fallback_count": 5,
             "last_fallback": "2026-04-05T10:00:00", "methods_affected": 1},
        ]
        db.fetch_one.return_value = {"total": 100}

        result = get_mv_health(db, hours=24)
        assert "mv_competitive_landscape" in result["views"]
        view = result["views"]["mv_competitive_landscape"]
        assert view["fallback_count"] == 5
        assert view["total_queries"] == 100
        assert view["fallback_pct"] == 5.0

    def test_alert_when_fallback_pct_above_20(self):
        from services.telemetry import get_mv_health
        db = MagicMock()
        db.fetch_all.return_value = [
            {"mv_name": "mv_competitive_landscape", "fallback_count": 30,
             "last_fallback": "2026-04-05T10:00:00", "methods_affected": 1},
        ]
        db.fetch_one.return_value = {"total": 100}

        result = get_mv_health(db, hours=24)
        assert len(result["alerts"]) == 1
        alert = result["alerts"][0]
        assert alert["mv_name"] == "mv_competitive_landscape"
        assert alert["fallback_pct"] == 30.0
        assert alert["severity"] == "medium"

    def test_high_severity_above_50_pct(self):
        from services.telemetry import get_mv_health
        db = MagicMock()
        db.fetch_all.return_value = [
            {"mv_name": "mv_company_portfolio", "fallback_count": 60,
             "last_fallback": "2026-04-05T10:00:00", "methods_affected": 1},
        ]
        db.fetch_one.return_value = {"total": 100}

        result = get_mv_health(db, hours=24)
        assert len(result["alerts"]) == 1
        assert result["alerts"][0]["severity"] == "high"
        assert result["alerts"][0]["fallback_pct"] == 60.0

    def test_no_alert_when_pct_below_threshold(self):
        from services.telemetry import get_mv_health
        db = MagicMock()
        db.fetch_all.return_value = [
            {"mv_name": "mv_competitive_landscape", "fallback_count": 2,
             "last_fallback": "2026-04-05T10:00:00", "methods_affected": 1},
        ]
        db.fetch_one.return_value = {"total": 100}

        result = get_mv_health(db, hours=24)
        assert len(result["alerts"]) == 0
        assert result["views"]["mv_competitive_landscape"]["fallback_pct"] == 2.0

    def test_graceful_when_table_missing(self):
        from services.telemetry import get_mv_health
        db = MagicMock()
        db.fetch_all.side_effect = RuntimeError("relation does not exist")

        result = get_mv_health(db, hours=24)
        assert result["views"] == {}
        assert result["alerts"] == []

    def test_multiple_views_with_mixed_health(self):
        from services.telemetry import get_mv_health
        db = MagicMock()
        db.fetch_all.return_value = [
            {"mv_name": "mv_competitive_landscape", "fallback_count": 25,
             "last_fallback": "2026-04-05T10:00:00", "methods_affected": 1},
            {"mv_name": "mv_drug_pipeline_strength", "fallback_count": 3,
             "last_fallback": "2026-04-05T09:00:00", "methods_affected": 1},
        ]
        db.fetch_one.return_value = {"total": 100}

        result = get_mv_health(db, hours=24)
        assert len(result["views"]) == 2
        # Only the landscape one should alert (25%)
        assert len(result["alerts"]) == 1
        assert result["alerts"][0]["mv_name"] == "mv_competitive_landscape"


class TestMetricsFallbackInstrumentation:
    """Verify that PharmaMetrics methods call log_mv_fallback at fallback points."""

    @patch("services.metrics.log_mv_fallback")
    def test_pipeline_strength_logs_fallback_on_sparse(self, mock_log):
        from services.metrics import PharmaMetrics
        db = MagicMock()
        config = MagicMock()
        metrics = PharmaMetrics(db, config)

        # MV returns 1 row (sparse) for TA query
        db.fetch_all.side_effect = [
            [{"drug_id": "d1", "drug_name": "test", "brand_name": None,
              "therapeutic_area": "TA", "mechanism": "M",
              "p1_count": 0, "p2_count": 0, "p3_count": 1, "p4_count": 0,
              "total_trials": 1, "active_trials": 1,
              "pipeline_score": 4.0, "active_pipeline_score": 4.0,
              "last_trial_start": None}],
            [],  # realtime returns empty
        ]

        metrics.drug_pipeline_strength(therapeutic_area="Test TA")

        mock_log.assert_called_once_with(
            db,
            method_name="drug_pipeline_strength",
            mv_name="mv_drug_pipeline_strength",
            reason="insufficient_data",
            row_count=1,
        )

    @patch("services.metrics.log_mv_fallback")
    def test_competitive_landscape_logs_on_sparse(self, mock_log):
        from services.metrics import PharmaMetrics
        db = MagicMock()
        config = MagicMock()
        metrics = PharmaMetrics(db, config)

        mv_sparse = [
            {"mechanism_name": "X", "therapeutic_area": "Y",
             "drug_count": 1, "trial_count": 2, "active_trial_count": 1,
             "total_pipeline_score": 5.0, "market_share_pct": 100.0,
             "mechanism_id": None, "therapeutic_area_id": None, "top_drug": None},
        ]
        rt_good = [
            {"mechanism_name": "X", "therapeutic_area": "Y",
             "drug_count": 5, "trial_count": 20, "active_trial_count": 8,
             "total_pipeline_score": 42.5},
            {"mechanism_name": "Z", "therapeutic_area": "Y",
             "drug_count": 3, "trial_count": 10, "active_trial_count": 4,
             "total_pipeline_score": 22.0},
        ]
        db.fetch_all.side_effect = [mv_sparse, rt_good]

        metrics.competitive_landscape(topic="test")

        mock_log.assert_called_once_with(
            db,
            method_name="competitive_landscape",
            mv_name="mv_competitive_landscape",
            reason="insufficient_data",
            row_count=1,
        )

    @patch("services.metrics.log_mv_fallback")
    def test_competitive_landscape_logs_on_error(self, mock_log):
        from services.metrics import PharmaMetrics
        db = MagicMock()
        config = MagicMock()
        metrics = PharmaMetrics(db, config)

        db.fetch_all.side_effect = [
            RuntimeError("relation does not exist"),
            [],  # realtime fallback
        ]

        result = metrics.competitive_landscape(topic="test")

        mock_log.assert_called_once_with(
            db,
            method_name="competitive_landscape",
            mv_name="mv_competitive_landscape",
            reason="mv_error",
            row_count=0,
        )

    @patch("services.metrics.log_mv_fallback")
    def test_company_portfolio_logs_on_error(self, mock_log):
        from services.metrics import PharmaMetrics
        db = MagicMock()
        config = MagicMock()
        metrics = PharmaMetrics(db, config)

        db.fetch_all.side_effect = RuntimeError("MV does not exist")

        result = metrics.company_portfolio()
        assert result == []

        mock_log.assert_called_once_with(
            db,
            method_name="company_portfolio",
            mv_name="mv_company_portfolio",
            reason="mv_error",
            row_count=0,
        )

    @patch("services.metrics.log_mv_fallback")
    def test_no_fallback_logged_when_mv_has_enough_rows(self, mock_log):
        from services.metrics import PharmaMetrics
        db = MagicMock()
        config = MagicMock()
        metrics = PharmaMetrics(db, config)

        # MV returns 5 rows — no fallback needed
        db.fetch_all.return_value = [
            {"drug_id": f"d{i}", "drug_name": f"drug_{i}", "brand_name": None,
             "therapeutic_area": "TA", "mechanism": "M",
             "p1_count": 0, "p2_count": 0, "p3_count": 1, "p4_count": 0,
             "total_trials": 1, "active_trials": 1,
             "pipeline_score": float(i), "active_pipeline_score": float(i),
             "last_trial_start": None}
            for i in range(5)
        ]

        metrics.drug_pipeline_strength(therapeutic_area="Test TA")
        mock_log.assert_not_called()
