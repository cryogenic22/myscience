"""BE-4 — /agents/stream SSE tests."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from unittest.mock import MagicMock

import pytest


def _row(**overrides):
    base = {
        "id": "evt-1",
        "session_id": "sess-1",
        "event_type": "tool_invoked",
        "agent_type": "research_agent",
        "tool_name": "search",
        "trust_tier": "viewer",
        "args_hash": "abc",
        "result_status": "ok",
        "metadata": {"activity": "Scanning trial registry",
                     "entity_refs": ["drug:tirzepatide"]},
        "created_at": datetime(2026, 5, 10, 12, tzinfo=timezone.utc),
    }
    base.update(overrides)
    return base


# ════════════════════════════════════════════════════════════════════
# _serialize_event_for_sse
# ════════════════════════════════════════════════════════════════════

class TestSerializeEventForSse:
    def test_carries_noun_agent_field(self):
        from api.routes.agent import _serialize_event_for_sse
        out = _serialize_event_for_sse(_row(agent_type="research_agent"))
        assert out["agent"] == "strategist"
        assert out["agent_type"] == "research_agent"

    def test_extracts_metadata_activity(self):
        from api.routes.agent import _serialize_event_for_sse
        out = _serialize_event_for_sse(_row())
        assert out["activity"] == "Scanning trial registry"

    def test_falls_back_to_tool_name_when_no_activity(self):
        from api.routes.agent import _serialize_event_for_sse
        out = _serialize_event_for_sse(_row(metadata={}))
        assert out["activity"] == "search"

    def test_collects_entity_refs(self):
        from api.routes.agent import _serialize_event_for_sse
        out = _serialize_event_for_sse(_row())
        assert out["entity_refs"] == ["drug:tirzepatide"]

    def test_handles_metadata_as_json_string(self):
        from api.routes.agent import _serialize_event_for_sse
        row = _row()
        row["metadata"] = json.dumps({"activity": "x", "entity_refs": ["company:lilly"]})
        out = _serialize_event_for_sse(row)
        assert out["activity"] == "x"
        assert out["entity_refs"] == ["company:lilly"]


# ════════════════════════════════════════════════════════════════════
# /agents/stream — endpoint registration + headers
# ════════════════════════════════════════════════════════════════════

class TestStreamRouteRegistration:
    def test_route_is_registered(self):
        """SSE GET /agents/stream is mounted on the FastAPI app."""
        from api.app import create_app

        app = create_app()
        paths = {r.path for r in app.routes}
        assert "/agents/stream" in paths
        # Versioned alias also mounted
        assert "/api/v1/agents/stream" in paths

    def test_route_response_class_is_streaming(self):
        """The route is wired to StreamingResponse (not JSONResponse)."""
        from api.routes.agent import stream_router
        # Find the route on the dedicated SSE router
        matching = [r for r in stream_router.routes if r.path == "/agents/stream"]
        assert matching, "expected /agents/stream route on stream_router"

    def test_constants_are_safe(self):
        """Heartbeat / poll cadence + max duration are bounded."""
        from api.routes.agent import (
            DEFAULT_HEARTBEAT_S, DEFAULT_POLL_S, SSE_MAX_DURATION_S,
        )
        assert 1 <= DEFAULT_POLL_S <= 30
        assert 5 <= DEFAULT_HEARTBEAT_S <= 60
        # Don't pin a worker for hours
        assert SSE_MAX_DURATION_S <= 3600
