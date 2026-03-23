"""Tests for graph truncation transparency — SPEC-004 R8.

TDD: traverse() signals when it hits the node cap.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock


class TestGraphTruncation:
    """Verify truncation detection in graph traversal results."""

    def test_not_truncated_below_cap(self):
        from services.graph import detect_truncation
        result = detect_truncation(node_count=50, max_nodes=100)
        assert result["truncated"] is False

    def test_truncated_at_cap(self):
        from services.graph import detect_truncation
        result = detect_truncation(node_count=100, max_nodes=100)
        assert result["truncated"] is True

    def test_truncated_metadata(self):
        from services.graph import detect_truncation
        result = detect_truncation(node_count=100, max_nodes=100)
        assert result["max_nodes"] == 100
        assert "truncated" in result

    def test_zero_nodes_not_truncated(self):
        from services.graph import detect_truncation
        result = detect_truncation(node_count=0, max_nodes=100)
        assert result["truncated"] is False

    def test_confidence_applies_truncation_penalty(self):
        """Confidence scoring should penalize truncated graphs."""
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
