"""Tests for services/agent/event_stream.py -- agent event bus.

TDD: Verify event creation, emission, filtering, memory cap, and DB persistence.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from services.agent.event_stream import AgentEvent, AgentEventType, EventStream


# ── AgentEvent dataclass tests ──


class TestAgentEvent:
    """Verify AgentEvent defaults and field assignment."""

    def test_default_timestamp(self):
        event = AgentEvent(event_type=AgentEventType.TOOL_INVOKED)
        assert event.timestamp is not None
        assert event.timestamp.tzinfo is not None  # timezone-aware

    def test_custom_values(self):
        ts = datetime(2026, 4, 5, 12, 0, 0, tzinfo=timezone.utc)
        event = AgentEvent(
            event_type=AgentEventType.TOOL_COMPLETED,
            session_id="sess-1",
            agent_type="steward",
            tool_name="entity_merge",
            trust_tier="elevated",
            args_hash="abc123",
            result_status="ok",
            metadata={"rows": 5},
            timestamp=ts,
            id="evt-42",
        )
        assert event.event_type == AgentEventType.TOOL_COMPLETED
        assert event.session_id == "sess-1"
        assert event.agent_type == "steward"
        assert event.tool_name == "entity_merge"
        assert event.trust_tier == "elevated"
        assert event.args_hash == "abc123"
        assert event.result_status == "ok"
        assert event.metadata == {"rows": 5}
        assert event.timestamp == ts
        assert event.id == "evt-42"


# ── EventStream tests ──


class TestEventStream:
    """Verify EventStream emit, convenience methods, filtering, and cap."""

    def test_emit_stores_in_memory(self):
        stream = EventStream()
        event = AgentEvent(event_type=AgentEventType.TURN_START, session_id="s1")
        stream.emit(event)
        assert len(stream._events) == 1
        assert stream._events[0] is event

    def test_emit_tool_invoked(self):
        stream = EventStream()
        event = stream.emit_tool_invoked(
            session_id="s1",
            agent_type="steward",
            tool_name="graph_search",
            trust_tier="public",
            args={"query": "tirzepatide"},
        )
        assert event.event_type == AgentEventType.TOOL_INVOKED
        assert event.session_id == "s1"
        assert event.agent_type == "steward"
        assert event.tool_name == "graph_search"
        assert event.trust_tier == "public"
        assert event.args_hash is not None
        assert len(event.args_hash) == 16
        assert len(stream._events) == 1

    def test_emit_tool_completed(self):
        stream = EventStream()
        event = stream.emit_tool_completed(
            session_id="s2",
            agent_type="research",
            tool_name="rag_search",
            result_status="ok",
            metadata={"hits": 10},
        )
        assert event.event_type == AgentEventType.TOOL_COMPLETED
        assert event.result_status == "ok"
        assert event.metadata == {"hits": 10}

    def test_emit_tool_failed(self):
        stream = EventStream()
        event = stream.emit_tool_failed(
            session_id="s3",
            agent_type="pipeline",
            tool_name="sql_query",
            error="Connection timeout after 5000ms",
        )
        assert event.event_type == AgentEventType.TOOL_FAILED
        assert event.result_status == "error"
        assert event.metadata["error"] == "Connection timeout after 5000ms"

    def test_get_recent_with_limit(self):
        stream = EventStream()
        for i in range(10):
            stream.emit(AgentEvent(
                event_type=AgentEventType.STEP_COMPLETED,
                session_id=f"s-{i}",
            ))
        recent = stream.get_recent(limit=3)
        assert len(recent) == 3
        # Should be the last 3
        assert recent[0].session_id == "s-7"
        assert recent[2].session_id == "s-9"

    def test_get_recent_filter_by_type(self):
        stream = EventStream()
        stream.emit(AgentEvent(event_type=AgentEventType.TOOL_INVOKED, tool_name="a"))
        stream.emit(AgentEvent(event_type=AgentEventType.TOOL_COMPLETED, tool_name="a"))
        stream.emit(AgentEvent(event_type=AgentEventType.TOOL_INVOKED, tool_name="b"))

        invoked = stream.get_recent(event_type="tool_invoked")
        assert len(invoked) == 2
        completed = stream.get_recent(event_type="tool_completed")
        assert len(completed) == 1

    def test_get_recent_filter_by_agent(self):
        stream = EventStream()
        stream.emit(AgentEvent(event_type=AgentEventType.TURN_START, agent_type="steward"))
        stream.emit(AgentEvent(event_type=AgentEventType.TURN_START, agent_type="research"))
        stream.emit(AgentEvent(event_type=AgentEventType.TURN_START, agent_type="steward"))

        steward_events = stream.get_recent(agent_type="steward")
        assert len(steward_events) == 2
        research_events = stream.get_recent(agent_type="research")
        assert len(research_events) == 1

    def test_count_by_type(self):
        stream = EventStream()
        stream.emit(AgentEvent(event_type=AgentEventType.TOOL_INVOKED))
        stream.emit(AgentEvent(event_type=AgentEventType.TOOL_INVOKED))
        stream.emit(AgentEvent(event_type=AgentEventType.TOOL_COMPLETED))
        stream.emit(AgentEvent(event_type=AgentEventType.TOOL_FAILED))

        counts = stream.count_by_type()
        assert counts["tool_invoked"] == 2
        assert counts["tool_completed"] == 1
        assert counts["tool_failed"] == 1

    def test_memory_cap(self):
        stream = EventStream()
        stream._max_memory = 10  # lower cap for test
        for i in range(25):
            stream.emit(AgentEvent(
                event_type=AgentEventType.STEP_COMPLETED,
                session_id=f"s-{i}",
            ))
        assert len(stream._events) == 10
        # Oldest should be trimmed, newest kept
        assert stream._events[0].session_id == "s-15"
        assert stream._events[-1].session_id == "s-24"

    def test_emit_persists_to_db(self):
        db = MagicMock()
        stream = EventStream(db=db)
        event = AgentEvent(
            event_type=AgentEventType.TOOL_INVOKED,
            session_id="s1",
            agent_type="steward",
            tool_name="graph_search",
        )
        stream.emit(event)
        assert db.execute.call_count == 1
        call_args = db.execute.call_args
        sql = call_args[0][0]
        assert "INSERT INTO agent_events" in sql

    def test_emit_handles_db_failure_gracefully(self):
        db = MagicMock()
        db.execute.side_effect = Exception("DB is down")
        stream = EventStream(db=db)
        event = AgentEvent(event_type=AgentEventType.TURN_START)
        # Should not raise
        stream.emit(event)
        # Event still in memory
        assert len(stream._events) == 1

    def test_args_hash_deterministic(self):
        stream = EventStream()
        e1 = stream.emit_tool_invoked("s1", "a", "tool", "public", {"x": 1, "y": 2})
        e2 = stream.emit_tool_invoked("s1", "a", "tool", "public", {"y": 2, "x": 1})
        assert e1.args_hash == e2.args_hash  # sort_keys=True ensures this

    def test_error_truncation(self):
        stream = EventStream()
        long_error = "x" * 1000
        event = stream.emit_tool_failed("s1", "a", "tool", long_error)
        assert len(event.metadata["error"]) == 500
