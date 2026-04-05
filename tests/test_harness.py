"""Tests for MarketZeroHarness — unified agent execution wrapper.

Run with: pytest tests/test_harness.py -v
"""

from __future__ import annotations

import pytest

from services.agent.harness import (
    HarnessConfig,
    HarnessResult,
    MarketZeroHarness,
    StepResult,
)
from services.agent.permissions import SessionMode
from services.agent.registry import ToolDefinition, ToolRegistry
from services.agent.event_stream import AgentEventType


# ── Helpers ──


def _make_registry(*tools: ToolDefinition) -> ToolRegistry:
    """Build a minimal registry with the given tools."""
    reg = ToolRegistry()
    for t in tools:
        reg.register(t)
    return reg


def _public_tool(name: str = "graph_search") -> ToolDefinition:
    return ToolDefinition(name=name, trust_tier="public", side_effects="read")


def _standard_tool(name: str = "steward_curate") -> ToolDefinition:
    return ToolDefinition(name=name, trust_tier="standard", side_effects="write")


def _system_tool(name: str = "db_drop") -> ToolDefinition:
    return ToolDefinition(name=name, trust_tier="system", side_effects="write")


def _ok_executor(args: dict) -> dict:
    return {"ok": True, **args}


def _failing_executor(args: dict) -> dict:
    raise RuntimeError("executor boom")


# ── 1. TestHarnessConfig ──


class TestHarnessConfig:
    """HarnessConfig defaults."""

    def test_default_values(self):
        """Verify defaults: max_steps=50, checkpoint_every=1, session_mode=STANDARD."""
        cfg = HarnessConfig()
        assert cfg.max_steps == 50
        assert cfg.checkpoint_every == 1
        assert cfg.session_mode == SessionMode.STANDARD


# ── 2. TestMarketZeroHarness ──


class TestMarketZeroHarness:
    """MarketZeroHarness run lifecycle, step execution, event emission."""

    def test_run_empty_steps(self):
        """run() with no steps returns completed with 0 steps."""
        harness = MarketZeroHarness()
        result = harness.run(agent_type="steward", goal="No-op")
        assert result.status == "completed"
        assert result.steps_completed == 0
        assert result.steps_failed == 0
        assert result.steps_denied == 0
        assert result.step_results == []
        assert result.session_id  # UUID assigned

    def test_run_single_step(self):
        """Register an executor, run one step, completes with output."""
        tool = _public_tool("graph_search")
        reg = _make_registry(tool)
        harness = MarketZeroHarness(registry=reg)
        harness.register_executor("graph_search", _ok_executor)

        result = harness.run(
            agent_type="research",
            goal="Search graph",
            steps=[("graph_search", {"query": "semaglutide"})],
        )

        assert result.status == "completed"
        assert result.steps_completed == 1
        assert len(result.step_results) == 1
        step = result.step_results[0]
        assert step.status == "ok"
        assert step.tool_name == "graph_search"
        assert step.output["ok"] is True
        assert step.output["query"] == "semaglutide"
        assert step.duration_ms > 0

    def test_run_multiple_steps(self):
        """Three steps, all complete successfully."""
        t1 = _public_tool("graph_search")
        t2 = _public_tool("rag_search")
        t3 = _public_tool("metrics_query")
        reg = _make_registry(t1, t2, t3)
        harness = MarketZeroHarness(registry=reg)
        harness.register_executor("graph_search", _ok_executor)
        harness.register_executor("rag_search", _ok_executor)
        harness.register_executor("metrics_query", _ok_executor)

        result = harness.run(
            agent_type="research",
            goal="Multi-step",
            steps=[
                ("graph_search", {"q": "a"}),
                ("rag_search", {"q": "b"}),
                ("metrics_query", {"q": "c"}),
            ],
        )

        assert result.status == "completed"
        assert result.steps_completed == 3
        assert result.steps_failed == 0
        assert len(result.step_results) == 3
        assert all(s.status == "ok" for s in result.step_results)

    def test_step_permission_denied(self):
        """System-tier tool denied in standard mode records denial."""
        tool = _system_tool("db_drop")
        reg = _make_registry(tool)
        harness = MarketZeroHarness(registry=reg)
        harness.register_executor("db_drop", _ok_executor)

        result = harness.run(
            agent_type="steward",
            goal="Dangerous op",
            steps=[("db_drop", {})],
        )

        assert result.status == "completed"
        assert result.steps_denied == 1
        assert result.steps_completed == 0
        step = result.step_results[0]
        assert step.status == "denied"
        assert "Permission denied" in step.error

    def test_step_unknown_tool(self):
        """Returns error for a tool not in the registry."""
        reg = _make_registry()  # empty registry
        harness = MarketZeroHarness(registry=reg)

        result = harness.run(
            agent_type="steward",
            goal="Bad tool",
            steps=[("nonexistent_tool", {})],
        )

        assert result.status == "completed"
        assert result.steps_failed == 1
        step = result.step_results[0]
        assert step.status == "error"
        assert "Unknown tool" in step.error

    def test_step_executor_error(self):
        """Executor raises an exception, step marked as failed."""
        tool = _public_tool("graph_search")
        reg = _make_registry(tool)
        harness = MarketZeroHarness(registry=reg)
        harness.register_executor("graph_search", _failing_executor)

        result = harness.run(
            agent_type="research",
            goal="Exploding tool",
            steps=[("graph_search", {})],
        )

        assert result.status == "completed"
        assert result.steps_failed == 1
        step = result.step_results[0]
        assert step.status == "error"
        assert "executor boom" in step.error

    def test_session_created(self):
        """Session store has the session after run."""
        harness = MarketZeroHarness()
        result = harness.run(agent_type="steward", goal="Check session")
        session = harness.session_store.get(result.session_id)
        assert session is not None
        assert session.agent_type == "steward"
        assert session.goal == "Check session"
        assert session.status == "completed"

    def test_events_emitted(self):
        """Event stream has turn_start + tool events + session_completed."""
        tool = _public_tool("graph_search")
        reg = _make_registry(tool)
        harness = MarketZeroHarness(registry=reg)
        harness.register_executor("graph_search", _ok_executor)

        result = harness.run(
            agent_type="research",
            goal="Event test",
            steps=[("graph_search", {"q": "test"})],
        )

        events = harness.event_stream.get_recent(limit=50)
        event_types = [e.event_type for e in events]

        assert AgentEventType.TURN_START in event_types
        assert AgentEventType.TOOL_INVOKED in event_types
        assert AgentEventType.TOOL_COMPLETED in event_types
        assert AgentEventType.SESSION_COMPLETED in event_types

        # All events reference the same session
        session_events = [e for e in events if e.session_id == result.session_id]
        assert len(session_events) >= 4  # turn_start + invoked + completed + checkpoint + session_completed

    def test_checkpoint_recorded(self):
        """Session store has checkpoint after step."""
        tool = _public_tool("graph_search")
        reg = _make_registry(tool)
        harness = MarketZeroHarness(registry=reg)
        harness.register_executor("graph_search", _ok_executor)

        result = harness.run(
            agent_type="steward",
            goal="Checkpoint test",
            steps=[("graph_search", {})],
        )

        session = harness.session_store.get(result.session_id)
        assert session.current_step == 1
        assert session.last_checkpoint is not None
        assert session.checkpoint_data.get("last_tool") == "graph_search"

    def test_result_counts(self):
        """steps_completed + steps_failed + steps_denied correct across mixed results."""
        pub = _public_tool("graph_search")
        sys = _system_tool("db_drop")
        reg = _make_registry(pub, sys)
        harness = MarketZeroHarness(registry=reg)
        harness.register_executor("graph_search", _ok_executor)
        harness.register_executor("db_drop", _ok_executor)

        result = harness.run(
            agent_type="steward",
            goal="Mixed results",
            steps=[
                ("graph_search", {}),       # ok
                ("db_drop", {}),            # denied (system tier)
                ("nonexistent_tool", {}),   # error (unknown)
            ],
        )

        assert result.steps_completed == 1
        assert result.steps_denied == 1
        assert result.steps_failed == 1
        assert len(result.step_results) == 3

    def test_custom_executor(self):
        """Single executor passed to run() used for all steps."""
        t1 = _public_tool("graph_search")
        t2 = _public_tool("rag_search")
        reg = _make_registry(t1, t2)
        harness = MarketZeroHarness(registry=reg)

        call_log = []

        def custom_exec(args: dict) -> dict:
            call_log.append(args)
            return {"custom": True}

        result = harness.run(
            agent_type="research",
            goal="Custom executor",
            steps=[("graph_search", {"a": 1}), ("rag_search", {"b": 2})],
            executor=custom_exec,
        )

        assert result.status == "completed"
        assert result.steps_completed == 2
        assert len(call_log) == 2
        assert call_log[0] == {"a": 1}
        assert call_log[1] == {"b": 2}
        assert result.step_results[0].output == {"custom": True}

    def test_max_steps_enforced(self):
        """Stops at max_steps even if more steps provided."""
        tool = _public_tool("graph_search")
        reg = _make_registry(tool)
        cfg = HarnessConfig(max_steps=2)
        harness = MarketZeroHarness(registry=reg, config=cfg)
        harness.register_executor("graph_search", _ok_executor)

        # Provide 5 steps but max_steps=2
        steps = [("graph_search", {"i": i}) for i in range(5)]
        result = harness.run(agent_type="research", goal="Max steps", steps=steps)

        assert result.status == "completed"
        assert result.steps_completed == 2
        assert len(result.step_results) == 2

    def test_no_executor_skips(self):
        """Tool with no registered executor returns skipped output."""
        tool = _public_tool("graph_search")
        reg = _make_registry(tool)
        harness = MarketZeroHarness(registry=reg)
        # No executor registered

        result = harness.run(
            agent_type="research",
            goal="No executor",
            steps=[("graph_search", {})],
        )

        assert result.status == "completed"
        assert result.steps_completed == 1
        step = result.step_results[0]
        assert step.status == "ok"
        assert step.output["skipped"] is True

    def test_total_duration_recorded(self):
        """HarnessResult records total_duration_ms."""
        harness = MarketZeroHarness()
        result = harness.run(agent_type="steward", goal="Timing")
        assert result.total_duration_ms >= 0
