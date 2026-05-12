"""Loop #21 — backend tests for GET /agents/activity."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest


def _make_db(*, signal=None, war_room=None, weights=None):
    """Mock DB that returns the prepared row for each SELECT pattern."""

    def fake_fetch_one(sql, params=None):
        s = (sql or "").lower()
        if "from signals" in s:
            return signal
        if "from war_room_sessions" in s:
            return war_room
        if "from materiality_weight_config" in s:
            return weights
        return None

    db = MagicMock()
    db.fetch_one = MagicMock(side_effect=fake_fetch_one)
    return db


def _client(db):
    from fastapi.testclient import TestClient
    from api.app import create_app
    from api.deps import get_db

    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


class TestAgentActivity:
    def test_endpoint_returns_one_per_agent(self):
        client = _client(_make_db())
        r = client.get("/agents/activity")
        assert r.status_code == 200, r.text
        body = r.json()
        ids = {a["agent_id"] for a in body["activities"]}
        assert ids == {"sentinel", "strategist", "curator"}

    def test_each_activity_has_required_fields(self):
        client = _client(_make_db())
        body = client.get("/agents/activity").json()
        for a in body["activities"]:
            assert "agent_id" in a
            assert "kind" in a and a["kind"] in {
                "started",
                "progress",
                "completed",
                "failed",
            }
            assert a["text"]
            assert a["timestamp"]

    def test_poll_after_seconds_is_returned(self):
        client = _client(_make_db())
        body = client.get("/agents/activity").json()
        assert body.get("poll_after_seconds", 0) > 0

    def test_sentinel_uses_latest_signal_headline_when_available(self):
        signal = {
            "headline": "FDA approves new oral GLP-1",
            "impact_tier": "high",
            "impact_score": 9.4,
            "kbq_tags": ["regulatory"],
            "ts": datetime(2026, 5, 12, 18, 0, tzinfo=timezone.utc),
        }
        client = _client(_make_db(signal=signal))
        body = client.get("/agents/activity").json()
        sentinel = next(a for a in body["activities"] if a["agent_id"] == "sentinel")
        assert "FDA approves new oral GLP-1" in sentinel["text"]
        assert sentinel["kind"] == "completed"

    def test_strategist_uses_latest_war_room_when_available(self):
        war_room = {
            "title": "Pricing posture under accelerated launch",
            "scenario_question": "What if Lilly launches Q1?",
            "created_at": datetime(2026, 5, 12, 18, 30, tzinfo=timezone.utc),
        }
        client = _client(_make_db(war_room=war_room))
        body = client.get("/agents/activity").json()
        strategist = next(
            a for a in body["activities"] if a["agent_id"] == "strategist"
        )
        assert "Pricing posture" in strategist["text"]

    def test_curator_uses_latest_weight_config_when_available(self):
        weights = {
            "created_at": datetime(2026, 5, 12, 17, 0, tzinfo=timezone.utc),
            "weights_jsonb": {"source_tier": 0.3, "entity_criticality": 0.3, "claim_type": 0.25, "recency": 0.15},
        }
        client = _client(_make_db(weights=weights))
        body = client.get("/agents/activity").json()
        curator = next(a for a in body["activities"] if a["agent_id"] == "curator")
        assert "re-calibrated" in curator["text"].lower() or "recalibrated" in curator["text"].lower()
        assert curator["kind"] == "completed"

    def test_falls_back_to_idle_when_db_empty(self):
        client = _client(_make_db())  # all None
        body = client.get("/agents/activity").json()
        kinds = {a["agent_id"]: a["kind"] for a in body["activities"]}
        # Empty DB → started/listening lines for each agent
        assert kinds["sentinel"] == "started"
        assert kinds["strategist"] == "started"
        assert kinds["curator"] == "started"
