"""BE-3 — agent name field on /agent/events tests."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest


# ════════════════════════════════════════════════════════════════════
# _normalize_agent_name
# ════════════════════════════════════════════════════════════════════

class TestNormaliseAgentName:
    @pytest.mark.parametrize("raw,expected", [
        ("research_agent", "strategist"),
        ("researcher", "strategist"),
        ("strategist", "strategist"),
        ("data_steward", "curator"),
        ("steward", "curator"),
        ("curator", "curator"),
        ("feedback_loops", "curator"),
        ("conversation_memory", "sentinel"),
        ("memory", "sentinel"),
        ("sentinel", "sentinel"),
    ])
    def test_known_slugs(self, raw, expected):
        from api.routes.agent import _normalize_agent_name
        assert _normalize_agent_name(raw) == expected

    def test_unknown_falls_back_to_sentinel(self):
        from api.routes.agent import _normalize_agent_name
        assert _normalize_agent_name("totally-new-agent-2026") == "sentinel"

    def test_none_falls_back_to_sentinel(self):
        from api.routes.agent import _normalize_agent_name
        assert _normalize_agent_name(None) == "sentinel"
        assert _normalize_agent_name("") == "sentinel"

    def test_substring_match(self):
        from api.routes.agent import _normalize_agent_name
        # Codenames evolve; substring fallback catches research_agent_v2 etc.
        assert _normalize_agent_name("research_agent_v2") == "strategist"
        assert _normalize_agent_name("data_steward_v3") == "curator"


# ════════════════════════════════════════════════════════════════════
# /agent/events response shape
# ════════════════════════════════════════════════════════════════════

def _client(rows):
    from fastapi.testclient import TestClient
    from api.app import create_app
    from api.deps import get_db

    db = MagicMock()
    db.fetch_all.return_value = rows

    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def _row(agent_type="research_agent", event_type="tool_invoked"):
    return {
        "id": "evt-1",
        "session_id": "sess-1",
        "event_type": event_type,
        "agent_type": agent_type,
        "tool_name": "search",
        "trust_tier": "viewer",
        "args_hash": "abc",
        "result_status": "ok",
        "metadata": {},
        "created_at": datetime.now(timezone.utc),
    }


class TestEventsEndpointAgentField:
    def test_every_event_has_agent_field(self):
        client = _client([
            _row(agent_type="research_agent"),
            _row(agent_type="data_steward"),
            _row(agent_type="conversation_memory"),
            _row(agent_type=None),
        ])
        r = client.get("/agent/events")
        assert r.status_code == 200, r.text
        events = r.json()["events"]
        assert len(events) == 4
        assert all(e.get("agent") in ("sentinel", "strategist", "curator")
                   for e in events), (
            "BE-3 acceptance: every event must carry a non-null agent field"
        )

    def test_legacy_agent_type_still_present(self):
        """Back-compat — existing clients reading agent_type keep working."""
        client = _client([_row(agent_type="research_agent")])
        r = client.get("/agent/events")
        ev = r.json()["events"][0]
        assert ev.get("agent_type") == "research_agent"
        assert ev.get("agent") == "strategist"

    def test_filter_by_public_agent_name(self):
        client = _client([
            _row(agent_type="research_agent"),
            _row(agent_type="data_steward"),
            _row(agent_type="conversation_memory"),
        ])
        r = client.get("/agent/events?agent=curator")
        events = r.json()["events"]
        assert len(events) == 1
        assert events[0]["agent"] == "curator"

    def test_filter_by_invalid_agent_returns_empty_with_error(self):
        client = _client([_row()])
        r = client.get("/agent/events?agent=bogus")
        body = r.json()
        assert body["events"] == []
        assert "agent must be" in body.get("error", "")
