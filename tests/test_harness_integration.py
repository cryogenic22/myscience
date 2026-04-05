"""Tests for Agent Harness integration — wiring into production.

Covers:
- get_harness() DI registration (Task 1A)
- Tool executor registration (Task 1B)
- DataSteward-through-harness (Task 1C)
- Query/team-eval-through-harness (Task 1D)
- Event emission and session lifecycle
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from dataclasses import dataclass

from services.agent.harness import (
    MarketZeroHarness,
    HarnessConfig,
    HarnessResult,
    StepResult,
)
from services.agent.event_stream import AgentEventType
from services.agent.permissions import SessionMode


# ── Fixtures ──


@pytest.fixture
def mock_db():
    """Minimal mock DB that satisfies harness + executor dependencies."""
    db = MagicMock()
    db.fetch_one.return_value = None
    db.fetch_all.return_value = []
    db.execute.return_value = None
    return db


@pytest.fixture
def harness(mock_db):
    """Create a harness instance with no DB persistence."""
    return MarketZeroHarness(db=None, config=HarnessConfig())


# ── Task 1A: get_harness() DI registration ──


class TestGetHarness:
    """Test that get_harness() returns a properly configured harness."""

    @patch("api.deps.get_db")
    def test_get_harness_returns_harness_instance(self, mock_get_db):
        mock_get_db.return_value = MagicMock()
        from api.deps import get_harness

        # Clear any cached instance
        get_harness.cache_clear()
        h = get_harness()
        assert isinstance(h, MarketZeroHarness)

    @patch("api.deps.get_db")
    def test_get_harness_has_registry(self, mock_get_db):
        mock_get_db.return_value = MagicMock()
        from api.deps import get_harness

        get_harness.cache_clear()
        h = get_harness()
        assert h.registry is not None
        assert h.registry.count() > 0

    @patch("api.deps.get_db")
    def test_get_harness_has_registered_executors(self, mock_get_db):
        mock_get_db.return_value = MagicMock()
        from api.deps import get_harness

        get_harness.cache_clear()
        h = get_harness()
        # At minimum the core tools should have executors
        assert len(h._tool_executors) > 0
        # Check key tool names are registered
        assert "steward_curate" in h._tool_executors
        assert "mv_refresh" in h._tool_executors
        assert "fair_score" in h._tool_executors
        assert "entity_influence" in h._tool_executors
        assert "competitive_clusters" in h._tool_executors
        assert "entity_exclude" in h._tool_executors

    @patch("api.deps.get_db")
    def test_get_harness_is_singleton(self, mock_get_db):
        mock_get_db.return_value = MagicMock()
        from api.deps import get_harness

        get_harness.cache_clear()
        h1 = get_harness()
        h2 = get_harness()
        assert h1 is h2


# ── Task 1B: Executor registration + delegation ──


class TestToolExecutors:
    """Test that tool executors delegate to existing services."""

    def test_steward_curate_executor(self, harness):
        """steward_curate executor creates a DataSteward and calls run_loop."""
        from api.deps import _make_steward_curate_executor

        mock_db = MagicMock()
        executor = _make_steward_curate_executor(mock_db)

        with patch("services.steward_signals.StewardSignalCollector") as MockCollector, \
             patch("services.data_steward.DataSteward") as MockSteward:
            mock_summary = MagicMock()
            mock_summary.completed = 5
            mock_summary.failed = 0
            mock_summary.iterations = 5
            mock_summary.feedback_resolved = 2
            mock_summary.total_elapsed_s = 1.0
            MockSteward.return_value.run_loop.return_value = mock_summary

            result = executor({"max_iterations": 10, "skip_ai": True})
            assert result["completed"] == 5
            assert result["failed"] == 0
            MockSteward.return_value.run_loop.assert_called_once()

    def test_mv_refresh_executor(self, harness):
        """mv_refresh executor calls db.execute with refresh SQL."""
        from api.deps import _make_mv_refresh_executor

        mock_db = MagicMock()
        mock_db.fetch_all.return_value = [{"viewname": "mv_test"}]
        executor = _make_mv_refresh_executor(mock_db)

        result = executor({})
        assert result["refreshed"] is True

    def test_fair_score_executor(self, harness):
        """fair_score executor delegates to FAIRScorer.compute."""
        from api.deps import _make_fair_score_executor

        mock_db = MagicMock()
        executor = _make_fair_score_executor(mock_db)

        with patch("services.fair_scorer.FAIRScorer") as MockFAIR:
            mock_result = MagicMock()
            mock_result.overall = 0.75
            MockFAIR.return_value.compute.return_value = mock_result

            result = executor({})
            assert result["overall"] == 0.75
            MockFAIR.return_value.compute.assert_called_once()

    def test_entity_influence_executor(self, harness):
        """entity_influence executor delegates to GraphAnalytics."""
        from api.deps import _make_entity_influence_executor

        mock_db = MagicMock()
        executor = _make_entity_influence_executor(mock_db)

        with patch("services.graph_analytics.GraphAnalytics") as MockGA:
            MockGA.return_value.entity_influence.return_value = {
                "entity_id": "123", "score": 0.9
            }
            result = executor({"entity_id": "123"})
            assert result["entity_id"] == "123"
            assert result["score"] == 0.9

    def test_competitive_clusters_executor(self, harness):
        """competitive_clusters executor delegates to GraphAnalytics."""
        from api.deps import _make_competitive_clusters_executor

        mock_db = MagicMock()
        executor = _make_competitive_clusters_executor(mock_db)

        with patch("services.graph_analytics.GraphAnalytics") as MockGA:
            MockGA.return_value.competitive_clusters.return_value = [
                {"cluster": "oncology", "size": 10}
            ]
            result = executor({"therapeutic_area": "oncology"})
            assert result["clusters"][0]["cluster"] == "oncology"

    def test_entity_exclude_executor(self, harness):
        """entity_exclude executor marks entity as excluded via SQL."""
        from api.deps import _make_entity_exclude_executor

        mock_db = MagicMock()
        executor = _make_entity_exclude_executor(mock_db)

        result = executor({"entity_id": "123", "entity_type": "drug"})
        assert result["excluded"] is True
        mock_db.execute.assert_called_once()


# ── Task 1B: Harness run lifecycle ──


class TestHarnessRunLifecycle:
    """Test that harness.run() creates sessions and emits events."""

    def test_run_creates_session(self, harness):
        """Harness.run() creates an AgentSession record."""
        result = harness.run(
            agent_type="test_agent",
            goal="Test goal",
            steps=[],
        )
        assert result.session_id
        assert result.agent_type == "test_agent"
        assert result.status == "completed"

        # Verify session was stored
        session = harness.session_store.get(result.session_id)
        assert session is not None
        assert session.agent_type == "test_agent"

    def test_run_emits_turn_start_and_completed(self, harness):
        """Harness.run() emits TURN_START and SESSION_COMPLETED events."""
        result = harness.run(
            agent_type="test_agent",
            goal="Test",
            steps=[],
        )
        events = harness.event_stream.get_recent(limit=10)
        event_types = [e.event_type for e in events]
        assert AgentEventType.TURN_START in event_types
        assert AgentEventType.SESSION_COMPLETED in event_types

    def test_run_with_step_emits_tool_events(self, harness):
        """Harness.run() emits TOOL_INVOKED + TOOL_COMPLETED per step."""
        harness.register_executor("steward_curate", lambda args: {"ok": True})

        result = harness.run(
            agent_type="data_steward",
            goal="Test curation",
            steps=[("steward_curate", {"max_iterations": 5})],
        )
        assert result.steps_completed == 1
        assert result.steps_failed == 0

        events = harness.event_stream.get_recent(limit=20)
        event_types = [e.event_type for e in events]
        assert AgentEventType.TOOL_INVOKED in event_types
        assert AgentEventType.TOOL_COMPLETED in event_types

    def test_run_with_failing_step(self, harness):
        """A step that raises is captured as failed, not crashed."""
        def failing_executor(args):
            raise RuntimeError("DB connection lost")

        harness.register_executor("steward_curate", failing_executor)

        result = harness.run(
            agent_type="data_steward",
            goal="Test failure",
            steps=[("steward_curate", {})],
        )
        # Harness should still complete (individual step fails, not the run)
        assert result.status == "completed"
        assert result.steps_failed == 1
        assert result.step_results[0].status == "error"
        assert "DB connection lost" in result.step_results[0].error

    def test_run_with_unknown_tool_skips(self, harness):
        """Running an unregistered tool returns error step result."""
        result = harness.run(
            agent_type="test",
            goal="Test unknown",
            steps=[("nonexistent_tool", {})],
        )
        assert result.steps_failed == 1
        assert result.step_results[0].status == "error"
        assert "Unknown tool" in result.step_results[0].error

    def test_run_with_executor_override(self, harness):
        """The executor= param overrides registered executors."""
        harness.register_executor("steward_curate", lambda args: {"from": "registered"})

        result = harness.run(
            agent_type="data_steward",
            goal="Override test",
            steps=[("steward_curate", {})],
            executor=lambda args: {"from": "override"},
        )
        assert result.step_results[0].output == {"from": "override"}


# ── Task 1C: DataSteward through harness ──


class TestStewardThroughHarness:
    """Test DataSteward routed through the harness wrapper."""

    def test_steward_harness_produces_session(self, harness):
        """Running steward through harness creates a session with agent_type=data_steward."""
        mock_summary = MagicMock()
        mock_summary.completed = 3
        mock_summary.failed = 0
        mock_summary.iterations = 3
        mock_summary.feedback_resolved = 1
        mock_summary.total_elapsed_s = 2.0

        def steward_executor(args):
            return {
                "completed": mock_summary.completed,
                "failed": mock_summary.failed,
                "feedback_resolved": mock_summary.feedback_resolved,
            }

        harness.register_executor("steward_curate", steward_executor)

        result = harness.run(
            agent_type="data_steward",
            goal="Periodic curation cycle",
            steps=[
                ("steward_curate", {"max_iterations": 20, "skip_ai": True}),
            ],
        )
        assert result.agent_type == "data_steward"
        assert result.status == "completed"
        assert result.steps_completed == 1

        session = harness.session_store.get(result.session_id)
        assert session.agent_type == "data_steward"

    def test_steward_multi_step(self, harness):
        """Steward can have multiple steps (curate + FAIR + MV refresh)."""
        harness.register_executor("steward_curate", lambda args: {"completed": 5})
        harness.register_executor("fair_score", lambda args: {"overall": 0.8})
        harness.register_executor("mv_refresh", lambda args: {"refreshed": True})

        result = harness.run(
            agent_type="data_steward",
            goal="Full curation cycle",
            steps=[
                ("steward_curate", {"max_iterations": 20}),
                ("fair_score", {}),
                ("mv_refresh", {}),
            ],
        )
        assert result.steps_completed == 3
        assert result.steps_failed == 0


# ── Task 1D: Query/team-eval through harness ──


class TestQueryThroughHarness:
    """Test LangGraph agents routed through the harness wrapper."""

    def test_query_harness_produces_session(self, harness):
        """Running a query through harness creates a session with agent_type=query."""
        def query_executor(args):
            return {
                "narrative": "Analysis of pipeline data",
                "table_data": [{"drug": "test", "phase": "3"}],
            }

        harness.register_executor("sql_query", query_executor)

        result = harness.run(
            agent_type="query",
            goal="Answer: What drugs are in phase 3?",
            steps=[("sql_query", {"question": "What drugs are in phase 3?"})],
        )
        assert result.agent_type == "query"
        assert result.status == "completed"
        assert result.steps_completed == 1

    def test_team_eval_harness_produces_session(self, harness):
        """Running team eval through harness creates a session with agent_type=team_eval."""
        result = harness.run(
            agent_type="team_eval",
            goal="Evaluate: Tirzepatide market potential",
            steps=[("rag_search", {"query": "tirzepatide"})],
            executor=lambda args: {"results": [{"entity": "tirzepatide"}]},
        )
        assert result.agent_type == "team_eval"
        assert result.status == "completed"

    def test_query_graph_passthrough_executor(self, harness):
        """The executor= param can wrap a LangGraph invoke call."""
        mock_graph_result = {
            "narrative": "Test narrative",
            "table_data": None,
            "visualizations": [],
        }

        result = harness.run(
            agent_type="query",
            goal="Answer: test question",
            steps=[("sql_query", {"question": "test"})],
            executor=lambda args: mock_graph_result,
        )
        assert result.steps_completed == 1
        assert result.step_results[0].output == mock_graph_result


# ── Task 1D: Handler integration ──


class TestHandlerIntegration:
    """Test that handle_structured_query and handle_team_eval use harness when available."""

    @patch("services.chat_handlers.handlers.get_harness")
    @patch("services.chat_handlers.handlers.get_query_graph")
    def test_handle_structured_query_uses_harness(self, mock_get_graph, mock_get_harness):
        """handle_structured_query routes through harness when available."""
        graph_output = {
            "narrative": "Test",
            "table_data": None,
            "visualizations": [],
            "presentation": {"title": "Test"},
            "error": None,
        }
        mock_graph = MagicMock()
        mock_graph.invoke.return_value = graph_output
        mock_get_graph.return_value = mock_graph

        mock_harness = MagicMock()
        mock_step = MagicMock()
        mock_step.output = graph_output
        mock_harness_result = MagicMock()
        mock_harness_result.status = "completed"
        mock_harness_result.step_results = [mock_step]
        mock_harness.run.return_value = mock_harness_result
        mock_get_harness.return_value = mock_harness

        from services.chat_handlers.handlers import handle_structured_query

        engine = MagicMock()
        db = MagicMock()
        llm = MagicMock()

        handle_structured_query("test question", engine, db, llm)

        # The harness should have been invoked
        mock_harness.run.assert_called_once()
        call_kwargs = mock_harness.run.call_args
        assert call_kwargs.kwargs.get("agent_type") == "query"

    @patch("services.chat_handlers.handlers.get_harness")
    @patch("services.chat_handlers.handlers.get_query_graph")
    def test_handle_structured_query_falls_back_without_harness(self, mock_get_graph, mock_get_harness):
        """handle_structured_query still works when harness is unavailable."""
        graph_output = {
            "narrative": "Test",
            "table_data": None,
            "visualizations": [],
            "presentation": {"title": "Test"},
            "error": None,
        }
        mock_graph = MagicMock()
        mock_graph.invoke.return_value = graph_output
        mock_get_graph.return_value = mock_graph

        # Harness unavailable
        mock_get_harness.side_effect = Exception("harness not available")

        from services.chat_handlers.handlers import handle_structured_query

        engine = MagicMock()
        db = MagicMock()
        llm = MagicMock()

        result = handle_structured_query("test question", engine, db, llm)
        # Should still succeed via direct graph.invoke
        mock_graph.invoke.assert_called_once()

    @patch("services.chat_handlers.handlers.get_harness")
    @patch("services.chat_handlers.handlers.get_team_eval_graph")
    def test_handle_team_eval_uses_harness(self, mock_get_graph, mock_get_harness):
        """handle_team_eval routes through harness when available."""
        graph_output = {
            "combined_narrative": "Test analysis",
            "persona_analyses": [],
            "confidence_assessment": {},
            "presentation": {},
            "table_data": None,
            "visualizations": [],
        }
        mock_graph = MagicMock()
        mock_graph.invoke.return_value = graph_output
        mock_get_graph.return_value = mock_graph

        mock_harness = MagicMock()
        mock_step = MagicMock()
        mock_step.output = graph_output
        mock_harness_result = MagicMock()
        mock_harness_result.status = "completed"
        mock_harness_result.step_results = [mock_step]
        mock_harness.run.return_value = mock_harness_result
        mock_get_harness.return_value = mock_harness

        from services.chat_handlers.handlers import handle_team_eval

        engine = MagicMock()
        db = MagicMock()
        llm = MagicMock()

        handle_team_eval("evaluate tirzepatide", engine, db, llm)

        mock_harness.run.assert_called_once()
        call_kwargs = mock_harness.run.call_args
        assert call_kwargs.kwargs.get("agent_type") == "team_eval"
