"""Tests for response confidence scoring — SPEC-004 R1.

TDD: Tests written FIRST, then compute_response_confidence() implementation.
"""

from __future__ import annotations

import pytest


class TestComputeConfidence:
    """Verify confidence scoring from data quality signals."""

    def test_full_data_high_confidence(self):
        """All signals present → ≥0.8."""
        from services.chat_handlers.formatting import compute_response_confidence
        score = compute_response_confidence(
            entity_resolved=True, entity_match_score=1.0,
            evidence_count=12, graph_node_count=25,
            metrics_available=True,
        )
        assert score >= 0.8

    def test_no_evidence_low_confidence(self):
        """Zero evidence → ≤0.3."""
        from services.chat_handlers.formatting import compute_response_confidence
        score = compute_response_confidence(
            entity_resolved=True, entity_match_score=0.9,
            evidence_count=0, graph_node_count=0,
            metrics_available=False,
        )
        assert score <= 0.3

    def test_no_graph_medium_confidence(self):
        """Evidence but no graph → moderate score."""
        from services.chat_handlers.formatting import compute_response_confidence
        score = compute_response_confidence(
            entity_resolved=True, entity_match_score=0.9,
            evidence_count=8, graph_node_count=0,
            metrics_available=True,
        )
        assert 0.4 <= score <= 0.7

    def test_no_metrics_deduction(self):
        """No metrics → missing 0.2 from score."""
        from services.chat_handlers.formatting import compute_response_confidence
        with_metrics = compute_response_confidence(
            entity_resolved=True, entity_match_score=1.0,
            evidence_count=10, graph_node_count=20,
            metrics_available=True,
        )
        without_metrics = compute_response_confidence(
            entity_resolved=True, entity_match_score=1.0,
            evidence_count=10, graph_node_count=20,
            metrics_available=False,
        )
        assert with_metrics - without_metrics == pytest.approx(0.2, abs=0.01)

    def test_graph_truncated_penalty(self):
        """Truncated graph → small penalty."""
        from services.chat_handlers.formatting import compute_response_confidence
        normal = compute_response_confidence(
            entity_resolved=True, entity_match_score=1.0,
            evidence_count=10, graph_node_count=100,
            metrics_available=True, graph_truncated=False,
        )
        truncated = compute_response_confidence(
            entity_resolved=True, entity_match_score=1.0,
            evidence_count=10, graph_node_count=100,
            metrics_available=True, graph_truncated=True,
        )
        assert truncated < normal
        assert normal - truncated == pytest.approx(0.05, abs=0.01)

    def test_entity_not_resolved(self):
        """Entity not resolved → 0 from resolution component."""
        from services.chat_handlers.formatting import compute_response_confidence
        resolved = compute_response_confidence(
            entity_resolved=True, entity_match_score=1.0,
            evidence_count=5, graph_node_count=5,
            metrics_available=True,
        )
        not_resolved = compute_response_confidence(
            entity_resolved=False, entity_match_score=None,
            evidence_count=5, graph_node_count=5,
            metrics_available=True,
        )
        assert resolved > not_resolved
        assert resolved - not_resolved == pytest.approx(0.3, abs=0.01)

    def test_entity_low_match_score(self):
        """Low match score → reduced resolution weight."""
        from services.chat_handlers.formatting import compute_response_confidence
        high_match = compute_response_confidence(
            entity_resolved=True, entity_match_score=1.0,
            evidence_count=5, graph_node_count=5,
            metrics_available=True,
        )
        low_match = compute_response_confidence(
            entity_resolved=True, entity_match_score=0.5,
            evidence_count=5, graph_node_count=5,
            metrics_available=True,
        )
        assert high_match > low_match

    def test_clamps_to_0_1(self):
        """Score never below 0 or above 1."""
        from services.chat_handlers.formatting import compute_response_confidence
        score = compute_response_confidence(
            entity_resolved=True, entity_match_score=1.0,
            evidence_count=100, graph_node_count=200,
            metrics_available=True,
        )
        assert 0.0 <= score <= 1.0

    def test_all_zeros(self):
        """No data at all → 0.0."""
        from services.chat_handlers.formatting import compute_response_confidence
        score = compute_response_confidence(
            entity_resolved=False, entity_match_score=None,
            evidence_count=0, graph_node_count=0,
            metrics_available=False,
        )
        assert score == 0.0

    def test_landscape_metrics_only(self):
        """Metrics but no graph/evidence (landscape pattern) → ~0.4."""
        from services.chat_handlers.formatting import compute_response_confidence
        score = compute_response_confidence(
            entity_resolved=False, entity_match_score=None,
            evidence_count=0, graph_node_count=0,
            metrics_available=True,
        )
        assert 0.15 <= score <= 0.3
