"""Tests for QualityMonitorHook and scripts/quality_scorecard.py.

TDD: Verify quality snapshot computation, delta alerting, and scorecard generation.
"""

from __future__ import annotations

import json
import re

import pytest


class MockDB:
    """Mock database for quality monitor tests."""

    def __init__(self):
        self._results: dict[str, list[dict]] = {}
        self.executed: list[tuple[str, list]] = []

    def set_results(self, key: str, results: list[dict]):
        self._results[key] = results

    def fetch_all(self, sql: str, params=None) -> list[dict]:
        sql_lower = sql.lower()
        from_match = re.search(r'\bfrom\s+(\w+)', sql_lower)
        if from_match:
            primary = from_match.group(1)
            if primary in self._results:
                return self._results[primary]
        for key, results in self._results.items():
            if key in sql_lower:
                return results
        return []

    def fetch_one(self, sql: str, params=None) -> dict | None:
        sql_lower = sql.lower()
        if "information_schema" in sql_lower:
            return {"exists_": False}
        if "count(*)" in sql_lower:
            return {"cnt": 10, "total": 10}
        results = self.fetch_all(sql, params)
        return results[0] if results else None

    def execute(self, sql: str, params=None) -> None:
        self.executed.append((sql, params or []))


# ── QualityMonitorHook tests ──

class TestQualityMonitorHook:
    def test_computes_quality_snapshot(self):
        db = MockDB()
        db.set_results("data_quality_results", [
            {"entity_type": "drug", "avg_score": 0.75},
            {"entity_type": "company", "avg_score": 0.60},
        ])

        from integration.pipeline_hooks import QualityMonitorHook
        hook = QualityMonitorHook(db)
        snapshot = hook._compute_quality_snapshot()
        assert "drug" in snapshot
        assert snapshot["drug"] == 0.75

    def test_returns_empty_snapshot_without_table(self):
        db = MockDB()
        # No results set → fetch_all returns []

        from integration.pipeline_hooks import QualityMonitorHook
        hook = QualityMonitorHook(db)
        snapshot = hook._compute_quality_snapshot()
        assert snapshot == {}

    def test_detects_quality_drop(self):
        db = MockDB()
        db.set_results("data_quality_results", [
            {"entity_type": "drug", "avg_score": 0.50},
        ])
        # Previous snapshot had 0.80 → drop of 0.30
        db.set_results("pipeline_quality_history", [
            {"quality_scores": json.dumps({"drug": 0.80})},
        ])

        from integration.pipeline_hooks import QualityMonitorHook, HookContext
        hook = QualityMonitorHook(db, quality_drop_threshold=0.05)

        ctx = HookContext(
            hook_point="ON_RUN_COMPLETE",
            source_type="clinical_trials_gov",
            etl_run_id="run-001",
            metadata={"records_inserted": 10},
        )
        result = hook.execute(ctx)
        assert "alerts" in result.data
        assert len(result.data["alerts"]) >= 1
        assert "dropped" in result.data["alerts"][0].lower()

    def test_no_alert_when_stable(self):
        db = MockDB()
        db.set_results("data_quality_results", [
            {"entity_type": "drug", "avg_score": 0.75},
        ])
        db.set_results("pipeline_quality_history", [
            {"quality_scores": json.dumps({"drug": 0.74})},
        ])

        from integration.pipeline_hooks import QualityMonitorHook, HookContext
        hook = QualityMonitorHook(db, quality_drop_threshold=0.05)

        ctx = HookContext(
            hook_point="ON_RUN_COMPLETE",
            source_type="pubmed",
            etl_run_id="run-002",
            metadata={"records_inserted": 5},
        )
        result = hook.execute(ctx)
        assert result.action == "continue"
        assert "Quality stable" in result.message

    def test_alerts_on_large_entity_batch(self):
        db = MockDB()
        db.set_results("data_quality_results", [
            {"entity_type": "drug", "avg_score": 0.75},
        ])

        from integration.pipeline_hooks import QualityMonitorHook, HookContext
        hook = QualityMonitorHook(db, new_entity_threshold=50)

        ctx = HookContext(
            hook_point="ON_RUN_COMPLETE",
            source_type="clinical_trials_gov",
            etl_run_id="run-003",
            metadata={"records_inserted": 200},
        )
        result = hook.execute(ctx)
        entity_alerts = [a for a in result.data.get("alerts", []) if "entities" in a.lower()]
        assert len(entity_alerts) >= 1


# ── quality_scorecard tests ──

class TestQualityScorecard:
    def test_compute_completeness(self):
        db = MockDB()

        call_count = [0]

        def mock_fetch_one(sql, params=None):
            sql_lower = sql.lower()
            if "count(*) as cnt" in sql_lower:
                return {"cnt": 100}
            # field completeness queries use COUNT(*) AS filled
            if "as filled" in sql_lower:
                return {"filled": 80}
            return None

        db.fetch_one = mock_fetch_one

        from scripts.quality_scorecard import compute_completeness
        result = compute_completeness(db)
        assert "drug" in result
        assert result["drug"]["total"] == 100
        # 80/100 = 0.8 per field, overall should be 0.8
        assert result["drug"]["overall"] > 0

    def test_compute_overall_score(self):
        from scripts.quality_scorecard import compute_overall_score

        completeness = {
            "drug": {"total": 100, "fields": {"name": 1.0}, "overall": 0.8},
        }
        links = {
            "drug": {"total": 100, "linked": 80, "density": 0.8, "avg_links": 3.0},
        }
        quality = {
            "drug": {"assessed": 100, "avg_score": 0.7, "passed": 70, "failed": 30},
        }

        score = compute_overall_score(completeness, links, quality)
        assert 0.0 < score <= 1.0
        # With all components at 0.7-0.8, score should be in that range
        assert score >= 0.6

    def test_compute_overall_score_empty(self):
        from scripts.quality_scorecard import compute_overall_score
        score = compute_overall_score({}, {}, {})
        assert score == 0.0

    def test_generate_report_produces_markdown(self):
        db = MockDB()

        def mock_fetch_one(sql, params=None):
            sql_lower = sql.lower()
            if "information_schema" in sql_lower:
                return {"exists_": False}
            if "count(*) as cnt" in sql_lower:
                return {"cnt": 0}  # zero records → skip complex link queries
            if "as filled" in sql_lower:
                return {"filled": 0}
            if "avg_links" in sql_lower:
                return {"avg_links": 0}
            return None

        db.fetch_one = mock_fetch_one
        db.set_results("therapeutic_areas", [
            {"name": "Diabetes Mellitus", "linked_entities": 10},
        ])

        from scripts.quality_scorecard import generate_report
        report = generate_report(db)

        assert "# Market Zero Quality Scorecard" in report
        assert "## Overall Score" in report
        assert "## Completeness" in report
