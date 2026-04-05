"""Tests for api/routes/agent.py -- agent harness API endpoints.

TDD: Verify events, sessions, and registry endpoints with mock DB.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


# ── Events endpoint tests ──


class TestAgentEventsEndpoint:
    """Verify GET /agent/events logic."""

    def test_returns_empty_when_no_events(self):
        from api.routes.agent import get_agent_events
        db = MagicMock()
        db.fetch_all.side_effect = Exception("table does not exist")

        result = get_agent_events(event_type=None, agent_type=None, limit=50, db=db)
        assert result["events"] == []
        assert result["total"] == 0

    def test_returns_events_from_db(self):
        from api.routes.agent import get_agent_events
        db = MagicMock()
        db.fetch_all.return_value = [
            {
                "id": "evt-1", "session_id": "s1", "event_type": "tool_invoked",
                "agent_type": "steward", "tool_name": "graph_search",
                "trust_tier": "public", "args_hash": "abc123",
                "result_status": "ok", "metadata": {}, "created_at": "2026-04-05T00:00:00Z",
            },
            {
                "id": "evt-2", "session_id": "s1", "event_type": "tool_completed",
                "agent_type": "steward", "tool_name": "graph_search",
                "trust_tier": "public", "args_hash": "abc123",
                "result_status": "ok", "metadata": {"hits": 5}, "created_at": "2026-04-05T00:00:01Z",
            },
        ]

        result = get_agent_events(event_type=None, agent_type=None, limit=50, db=db)
        assert result["total"] == 2
        assert len(result["events"]) == 2
        assert result["events"][0]["id"] == "evt-1"

    def test_filters_by_event_type(self):
        from api.routes.agent import get_agent_events
        db = MagicMock()
        db.fetch_all.return_value = [
            {
                "id": "evt-1", "session_id": "s1", "event_type": "tool_invoked",
                "agent_type": "steward", "tool_name": "sql_query",
                "trust_tier": "standard", "args_hash": "def456",
                "result_status": "ok", "metadata": {}, "created_at": "2026-04-05",
            },
        ]

        result = get_agent_events(event_type="tool_invoked", agent_type=None, limit=50, db=db)
        assert result["total"] == 1
        # Verify the WHERE clause was built
        sql = db.fetch_all.call_args[0][0]
        assert "event_type = %s" in sql

    def test_filters_by_agent_type(self):
        from api.routes.agent import get_agent_events
        db = MagicMock()
        db.fetch_all.return_value = []

        get_agent_events(event_type=None, agent_type="research", limit=10, db=db)
        sql = db.fetch_all.call_args[0][0]
        assert "agent_type = %s" in sql
        params = db.fetch_all.call_args[0][1]
        assert "research" in params


# ── Sessions endpoint tests ──


class TestAgentSessionsEndpoint:
    """Verify GET /agent/sessions logic."""

    def test_returns_empty_when_no_sessions(self):
        from api.routes.agent import get_agent_sessions
        db = MagicMock()
        db.fetch_all.side_effect = Exception("table does not exist")

        result = get_agent_sessions(agent_type=None, status=None, limit=20, db=db)
        assert result["sessions"] == []
        assert result["total"] == 0

    def test_returns_sessions_from_db(self):
        from api.routes.agent import get_agent_sessions
        db = MagicMock()
        db.fetch_all.return_value = [
            {
                "id": "sess-1", "agent_type": "steward", "goal": "Curate drugs",
                "status": "completed", "current_step": 5, "total_steps": 5,
                "started_at": "2026-04-05T00:00:00Z", "last_checkpoint": "2026-04-05T00:05:00Z",
                "completed_at": "2026-04-05T00:10:00Z", "error_message": None,
            },
        ]

        result = get_agent_sessions(agent_type=None, status=None, limit=20, db=db)
        assert result["total"] == 1
        assert result["sessions"][0]["id"] == "sess-1"
        assert result["sessions"][0]["status"] == "completed"

    def test_filters_by_status(self):
        from api.routes.agent import get_agent_sessions
        db = MagicMock()
        db.fetch_all.return_value = []

        get_agent_sessions(agent_type=None, status="running", limit=20, db=db)
        sql = db.fetch_all.call_args[0][0]
        assert "status = %s" in sql
        params = db.fetch_all.call_args[0][1]
        assert "running" in params

    def test_filters_by_agent_type(self):
        from api.routes.agent import get_agent_sessions
        db = MagicMock()
        db.fetch_all.return_value = []

        get_agent_sessions(agent_type="research", status=None, limit=20, db=db)
        sql = db.fetch_all.call_args[0][0]
        assert "agent_type = %s" in sql


# ── Tool Registry endpoint tests ──


class TestToolRegistryEndpoint:
    """Verify GET /agent/registry logic."""

    def test_returns_all_tools(self):
        from api.routes.agent import get_tool_registry
        result = get_tool_registry()
        assert result["total"] >= 13
        assert len(result["tools"]) == result["total"]

    def test_tools_have_required_fields(self):
        from api.routes.agent import get_tool_registry
        result = get_tool_registry()
        for tool in result["tools"]:
            assert "name" in tool
            assert "trust_tier" in tool
            assert "side_effects" in tool
            assert "description" in tool
            assert "tags" in tool
            assert tool["name"]  # not empty
            assert tool["trust_tier"] in ("public", "standard", "elevated", "system")
            assert tool["side_effects"] in ("none", "read", "write", "external")

    def test_known_tools_present(self):
        from api.routes.agent import get_tool_registry
        result = get_tool_registry()
        tool_names = {t["name"] for t in result["tools"]}
        assert "graph_search" in tool_names
        assert "sql_query" in tool_names
        assert "rag_search" in tool_names
        assert "fair_score" in tool_names
        assert "pipeline_run" in tool_names
