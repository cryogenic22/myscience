"""Tests for compound intent detection and execution.

Validates that multi-part questions are split into 1-2 intents,
executed by the correct handlers, and merged properly.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from services.chat_handlers.intent import Intent, detect_compound_intent
from services.chat_handlers.handlers import handle_compound, _merge_data_contexts


# ── TestCompoundIntentDetection ──


class TestCompoundIntentDetection:
    """Validate splitting compound questions into multiple intents."""

    def test_detects_portfolio_plus_compare(self):
        """'portfolio and compare' -> [portfolio, compare]"""
        result = detect_compound_intent(
            "Show me Pfizer's portfolio and compare their top 3 drugs"
        )
        intents = [r[0] for r in result]
        assert len(intents) == 2
        assert Intent.PORTFOLIO in intents
        assert Intent.COMPARE in intents

    def test_detects_dossier_plus_landscape(self):
        """'tell me about X and its competitive landscape' -> [dossier, landscape]"""
        result = detect_compound_intent(
            "Tell me about semaglutide and also show the competitive landscape"
        )
        intents = [r[0] for r in result]
        assert len(intents) == 2
        assert Intent.DOSSIER in intents
        assert Intent.LANDSCAPE in intents

    def test_single_intent_unchanged(self):
        """Single-intent questions return exactly one result."""
        result = detect_compound_intent("Tell me about semaglutide")
        assert len(result) == 1
        assert result[0][0] == Intent.DOSSIER

    def test_three_intents_capped_at_two(self):
        """Max 2 intents per compound query, even if 3+ clauses."""
        result = detect_compound_intent(
            "Pfizer portfolio and compare semaglutide vs tirzepatide plus show the obesity pipeline"
        )
        assert len(result) <= 2


# ── TestCompoundIntentExecution ──


class TestCompoundIntentExecution:
    """Validate handle_compound merges handler results correctly."""

    def _make_handler_result(self, intent: str, narrative: str, confidence: float = 0.8) -> dict:
        return {
            "narrative": narrative,
            "intent": intent,
            "confidence": confidence,
            "data": {
                "evidence": [{"source": "test", "content": f"Evidence for {intent}"}],
                "graph_context": {
                    "nodes": [{"id": "n1", "label": f"Node from {intent}"}],
                    "edges": [],
                    "node_count": 1,
                    "edge_count": 0,
                },
                "entity_focus": [{"entity_id": "e1", "label": f"Entity from {intent}"}],
                "metrics_context": {f"{intent}_metric": {"score": 0.9}},
                "provenance_summary": {
                    "total_evidence_items": 1,
                    "by_source": {"test_source": 1},
                },
            },
        }

    @patch("services.chat_handlers.handlers._INTENT_DISPATCH")
    def test_executes_both_intents(self, mock_dispatch):
        """Both handlers are called and produce results."""
        mock_portfolio = MagicMock(return_value=self._make_handler_result("portfolio", "Portfolio analysis."))
        mock_compare = MagicMock(return_value=self._make_handler_result("compare", "Comparison results."))
        mock_dispatch.get = lambda intent, *a: {
            Intent.PORTFOLIO: mock_portfolio,
            Intent.COMPARE: mock_compare,
        }.get(intent)

        intents = [(Intent.PORTFOLIO, {"company_name": "Pfizer"}), (Intent.COMPARE, {"entities": ["A", "B"]})]
        result = handle_compound(intents, db=MagicMock(), engine=MagicMock(), llm=MagicMock(), metrics_svc=MagicMock())

        mock_portfolio.assert_called_once()
        mock_compare.assert_called_once()
        assert result["narrative"]  # non-empty
        assert result["data"] is not None

    @patch("services.chat_handlers.handlers._INTENT_DISPATCH")
    def test_merges_narratives(self, mock_dispatch):
        """Combined narrative contains text from both handlers separated by ---."""
        mock_portfolio = MagicMock(return_value=self._make_handler_result("portfolio", "Portfolio analysis."))
        mock_landscape = MagicMock(return_value=self._make_handler_result("landscape", "Landscape overview."))
        mock_dispatch.get = lambda intent, *a: {
            Intent.PORTFOLIO: mock_portfolio,
            Intent.LANDSCAPE: mock_landscape,
        }.get(intent)

        intents = [(Intent.PORTFOLIO, {}), (Intent.LANDSCAPE, {})]
        result = handle_compound(intents, db=MagicMock(), engine=MagicMock(), llm=MagicMock(), metrics_svc=MagicMock())

        assert "Portfolio analysis." in result["narrative"]
        assert "Landscape overview." in result["narrative"]
        assert "---" in result["narrative"]

    @patch("services.chat_handlers.handlers._INTENT_DISPATCH")
    def test_merges_data_contexts(self, mock_dispatch):
        """Evidence + graph from both handlers are merged."""
        result_a = self._make_handler_result("portfolio", "A")
        result_b = self._make_handler_result("compare", "B")
        mock_dispatch.get = lambda intent, *a: {
            Intent.PORTFOLIO: MagicMock(return_value=result_a),
            Intent.COMPARE: MagicMock(return_value=result_b),
        }.get(intent)

        intents = [(Intent.PORTFOLIO, {}), (Intent.COMPARE, {})]
        result = handle_compound(intents, db=MagicMock(), engine=MagicMock(), llm=MagicMock(), metrics_svc=MagicMock())

        data = result["data"]
        assert len(data["evidence"]) == 2
        assert data["graph_context"]["node_count"] == 2
        assert len(data["entity_focus"]) == 2

    @patch("services.chat_handlers.handlers._INTENT_DISPATCH")
    def test_confidence_is_min_of_both(self, mock_dispatch):
        """Compound confidence is the minimum of individual confidences."""
        result_a = self._make_handler_result("portfolio", "A", confidence=0.9)
        result_b = self._make_handler_result("landscape", "B", confidence=0.6)
        mock_dispatch.get = lambda intent, *a: {
            Intent.PORTFOLIO: MagicMock(return_value=result_a),
            Intent.LANDSCAPE: MagicMock(return_value=result_b),
        }.get(intent)

        intents = [(Intent.PORTFOLIO, {}), (Intent.LANDSCAPE, {})]
        result = handle_compound(intents, db=MagicMock(), engine=MagicMock(), llm=MagicMock(), metrics_svc=MagicMock())

        assert result["confidence"] == 0.6
