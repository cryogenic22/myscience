"""Tests for CI benchmark integration — offline eval + regression detection.

Validates that the CI eval runner can score pre-captured responses,
detect regressions, enforce thresholds, and generate JSON reports.
"""

from __future__ import annotations

import json
import os
import tempfile
import pytest

from benchmark.ci_eval import run_ci_eval, DEFAULT_REGRESSION_LIMIT


def _golden_subset():
    """Minimal golden queries for CI tests (3 queries covering 3 intents)."""
    return [
        {
            "id": "CI01",
            "intent": "dossier",
            "question": "Tell me about semaglutide",
            "expected": {
                "entities": ["semaglutide"],
                "must_mention": ["GLP-1"],
                "must_not_mention": [],
                "min_evidence": 1,
                "min_citations": 1,
            },
        },
        {
            "id": "CI02",
            "intent": "landscape",
            "question": "GLP-1 competitive landscape",
            "expected": {
                "entities": [],
                "must_mention": ["GLP-1"],
                "must_not_mention": [],
                "min_evidence": 0,
                "min_citations": 0,
            },
        },
        {
            "id": "CI03",
            "intent": "portfolio",
            "question": "Novo Nordisk portfolio",
            "expected": {
                "entities": ["Novo Nordisk"],
                "must_mention": [],
                "must_not_mention": [],
                "min_evidence": 0,
                "min_citations": 0,
            },
        },
    ]


def _captured_responses_good():
    """Captured responses that score well."""
    return [
        {
            "query_id": "CI01",
            "response": {
                "intent": "dossier",
                "narrative": "**Semaglutide** is a GLP-1 receptor agonist developed by Novo Nordisk [1].",
                "data": {
                    "evidence": [
                        {"source": "clinical_trials_gov", "content": "Semaglutide Phase 3 trial data"},
                        {"source": "pubmed", "content": "GLP-1 receptor agonist review"},
                    ],
                    "entity_focus": [{"label": "semaglutide", "entity_type": "drug", "id": "x"}],
                    "graph_context": {"nodes": [], "edges": [], "node_count": 0, "edge_count": 0},
                    "metrics_context": {},
                    "provenance_summary": {"by_source": {"pubmed": 1, "clinical_trials_gov": 1}},
                },
            },
        },
        {
            "query_id": "CI02",
            "response": {
                "intent": "landscape",
                "narrative": "The GLP-1 receptor agonist landscape is dominated by semaglutide and tirzepatide.",
                "data": {
                    "evidence": [],
                    "entity_focus": [],
                    "graph_context": {"nodes": [], "edges": [], "node_count": 0, "edge_count": 0},
                    "metrics_context": {},
                    "provenance_summary": {},
                },
            },
        },
        {
            "query_id": "CI03",
            "response": {
                "intent": "portfolio",
                "narrative": "**Novo Nordisk** has a strong portfolio in diabetes and obesity.",
                "data": {
                    "evidence": [],
                    "entity_focus": [{"label": "Novo Nordisk", "entity_type": "company", "id": "y"}],
                    "graph_context": {"nodes": [], "edges": [], "node_count": 0, "edge_count": 0},
                    "metrics_context": {},
                    "provenance_summary": {},
                },
            },
        },
    ]


def _captured_responses_bad():
    """Captured responses that score poorly (wrong intents, no entities)."""
    return [
        {
            "query_id": "CI01",
            "response": {
                "intent": "general",  # wrong intent
                "narrative": "No data available.",
                "data": {
                    "evidence": [],
                    "entity_focus": [],
                    "graph_context": {"nodes": [], "edges": [], "node_count": 0, "edge_count": 0},
                    "metrics_context": {},
                    "provenance_summary": {},
                },
            },
        },
        {
            "query_id": "CI02",
            "response": {
                "intent": "general",  # wrong intent
                "narrative": "I don't know.",
                "data": {
                    "evidence": [],
                    "entity_focus": [],
                    "graph_context": {"nodes": [], "edges": [], "node_count": 0, "edge_count": 0},
                    "metrics_context": {},
                    "provenance_summary": {},
                },
            },
        },
        {
            "query_id": "CI03",
            "response": {
                "intent": "general",  # wrong intent
                "narrative": "Sorry, no information.",
                "data": {
                    "evidence": [],
                    "entity_focus": [],
                    "graph_context": {"nodes": [], "edges": [], "node_count": 0, "edge_count": 0},
                    "metrics_context": {},
                    "provenance_summary": {},
                },
            },
        },
    ]


def _write_temp_json(data) -> str:
    """Write data to a temp JSON file and return its path."""
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return path


class TestCIBenchmark:
    """CI benchmark integration tests."""

    def test_offline_eval_from_captured_responses(self):
        """Scores pre-captured JSON responses against golden queries."""
        golden_path = _write_temp_json(_golden_subset())
        responses_path = _write_temp_json(_captured_responses_good())
        baseline = {
            "overall_score": 0.5,
            "by_dimension": {"intent": 0.5, "grounding": 0.5, "factual": 0.5, "completeness": 0.5, "citation": 0.5},
        }
        baseline_path = _write_temp_json(baseline)

        try:
            result = run_ci_eval(
                baseline_path=baseline_path,
                responses_path=responses_path,
                golden_path=golden_path,
            )
            assert "overall" in result
            assert result["overall"] > 0.0
            assert result["total_queries"] == 3
        finally:
            os.unlink(golden_path)
            os.unlink(responses_path)
            os.unlink(baseline_path)

    def test_exits_0_when_above_threshold(self):
        """CI exits 0 when composite score is above the threshold."""
        golden_path = _write_temp_json(_golden_subset())
        responses_path = _write_temp_json(_captured_responses_good())

        try:
            result = run_ci_eval(
                responses_path=responses_path,
                golden_path=golden_path,
                threshold=30.0,  # low threshold, good responses should pass
                offline=True,
            )
            assert result["passed"] is True
            assert result["overall"] * 100 >= 30.0
            assert len(result.get("fail_reasons", [])) == 0
        finally:
            os.unlink(golden_path)
            os.unlink(responses_path)

    def test_exits_1_when_below_threshold(self):
        """CI exits 1 when composite score drops below threshold."""
        golden_path = _write_temp_json(_golden_subset())
        responses_path = _write_temp_json(_captured_responses_bad())

        try:
            result = run_ci_eval(
                responses_path=responses_path,
                golden_path=golden_path,
                threshold=90.0,  # high threshold, bad responses will fail
                offline=True,
            )
            assert result["passed"] is False
            reasons = result.get("fail_reasons", [])
            assert any("below threshold" in r for r in reasons)
        finally:
            os.unlink(golden_path)
            os.unlink(responses_path)

    def test_regression_detection_overall(self):
        """Detects if overall score drops more than regression limit from baseline."""
        golden_path = _write_temp_json(_golden_subset())
        responses_path = _write_temp_json(_captured_responses_good())

        # Create a baseline with an artificially high score (forcing a regression)
        baseline = {
            "overall_score": 0.999,  # very high -> current will be lower
            "by_dimension": {"intent": 0.5, "grounding": 0.5, "factual": 0.5, "completeness": 0.5, "citation": 0.5},
        }
        baseline_path = _write_temp_json(baseline)

        try:
            result = run_ci_eval(
                baseline_path=baseline_path,
                responses_path=responses_path,
                golden_path=golden_path,
            )
            assert result["passed"] is False
            assert len(result["regressions"]) > 0
            # Should have an "overall" regression
            dims = [r["dimension"] for r in result["regressions"]]
            assert "overall" in dims
        finally:
            os.unlink(golden_path)
            os.unlink(responses_path)
            os.unlink(baseline_path)

    def test_per_dimension_regression(self):
        """Any single dimension drops >regression_limit -> alert."""
        golden_path = _write_temp_json(_golden_subset())
        responses_path = _write_temp_json(_captured_responses_good())

        # Baseline with factual dimension much higher than actual.
        baseline = {
            "overall_score": 0.5,
            "by_dimension": {
                "intent": 0.5,
                "grounding": 0.5,
                "factual": 0.999,  # artificially high — actual is ~0.5
                "completeness": 0.5,
                "citation": 0.5,
            },
        }
        baseline_path = _write_temp_json(baseline)

        try:
            result = run_ci_eval(
                baseline_path=baseline_path,
                responses_path=responses_path,
                golden_path=golden_path,
            )
            # Should detect a regression in factual dimension
            dims = [r["dimension"] for r in result["regressions"]]
            assert "factual" in dims
        finally:
            os.unlink(golden_path)
            os.unlink(responses_path)
            os.unlink(baseline_path)

    def test_custom_regression_limit(self):
        """Custom regression-limit flag controls sensitivity.

        Good responses score factual=0.5 (no verifiable numbers in some
        narratives).  Setting baseline factual to 0.6 creates a 10pp drop
        which is within default 10pp limit but outside a tight 1pp limit.
        """
        golden_path = _write_temp_json(_golden_subset())
        responses_path = _write_temp_json(_captured_responses_good())

        baseline = {
            "overall_score": 0.5,
            "by_dimension": {
                "intent": 1.0,
                "grounding": 1.0,
                "factual": 0.6,  # actual is 0.5 -> 10pp drop
                "completeness": 1.0,
                "citation": 1.0,
            },
        }
        baseline_path = _write_temp_json(baseline)

        try:
            # With 1pp limit, the factual 10pp drop should trigger
            result_tight = run_ci_eval(
                baseline_path=baseline_path,
                responses_path=responses_path,
                golden_path=golden_path,
                regression_limit=1.0,  # very tight — 1pp
            )
            dims = [r["dimension"] for r in result_tight["regressions"]]
            assert "factual" in dims, f"Expected factual regression with 1pp limit, got {dims}"

            # With loose limit (50pp), same data should pass
            result_loose = run_ci_eval(
                baseline_path=baseline_path,
                responses_path=responses_path,
                golden_path=golden_path,
                regression_limit=50.0,  # very loose
            )
            assert result_loose["passed"] is True
        finally:
            os.unlink(golden_path)
            os.unlink(responses_path)
            os.unlink(baseline_path)

    def test_offline_without_responses_uses_synthetic(self):
        """Offline mode without --responses generates synthetic responses."""
        golden_path = _write_temp_json(_golden_subset())

        try:
            result = run_ci_eval(
                golden_path=golden_path,
                offline=True,
            )
            assert result["total_queries"] == 3
            assert result["overall"] > 0.0
        finally:
            os.unlink(golden_path)

    def test_generates_json_report(self):
        """Report saved as JSON with required fields."""
        golden_path = _write_temp_json(_golden_subset())
        responses_path = _write_temp_json(_captured_responses_good())
        baseline = {
            "overall_score": 0.5,
            "by_dimension": {"intent": 0.5, "grounding": 0.5, "factual": 0.5, "completeness": 0.5, "citation": 0.5},
        }
        baseline_path = _write_temp_json(baseline)

        try:
            result = run_ci_eval(
                baseline_path=baseline_path,
                responses_path=responses_path,
                golden_path=golden_path,
            )
            report_path = result["report_path"]
            assert os.path.exists(report_path)

            with open(report_path, "r", encoding="utf-8") as f:
                report_data = json.load(f)

            # Verify required fields
            assert "passed" in report_data
            assert "overall" in report_data
            assert "regressions" in report_data
            assert "by_dimension" in report_data
            assert "total_queries" in report_data
        finally:
            os.unlink(golden_path)
            os.unlink(responses_path)
            os.unlink(baseline_path)

    def test_no_baseline_skips_regression_check(self):
        """When no baseline is provided, regression checking is skipped."""
        golden_path = _write_temp_json(_golden_subset())
        responses_path = _write_temp_json(_captured_responses_good())

        try:
            result = run_ci_eval(
                responses_path=responses_path,
                golden_path=golden_path,
                threshold=30.0,
                offline=True,
            )
            assert result["baseline"] is None
            assert result["regressions"] == []
            assert result["passed"] is True
        finally:
            os.unlink(golden_path)
            os.unlink(responses_path)

    def test_threshold_and_regression_both_checked(self):
        """Both threshold and regression failures are reported together."""
        golden_path = _write_temp_json(_golden_subset())
        responses_path = _write_temp_json(_captured_responses_bad())

        baseline = {
            "overall_score": 0.999,
            "by_dimension": {
                "intent": 0.999,
                "grounding": 0.999,
                "factual": 0.999,
                "completeness": 0.999,
                "citation": 0.999,
            },
        }
        baseline_path = _write_temp_json(baseline)

        try:
            result = run_ci_eval(
                baseline_path=baseline_path,
                responses_path=responses_path,
                golden_path=golden_path,
                threshold=95.0,  # impossibly high
            )
            assert result["passed"] is False
            reasons = result.get("fail_reasons", [])
            # Should have both threshold failure and regression failure
            has_threshold = any("below threshold" in r for r in reasons)
            has_regression = any("Regression" in r for r in reasons)
            assert has_threshold, f"Expected threshold failure in {reasons}"
            assert has_regression, f"Expected regression failure in {reasons}"
        finally:
            os.unlink(golden_path)
            os.unlink(responses_path)
            os.unlink(baseline_path)
