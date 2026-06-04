"""PB-203 / L13 — agent nudges: intent registry, validation, persistence, route."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from services.agent.nudge_intents import (
    AGENT_INTENTS,
    NudgeError,
    VALID_AGENTS,
    get_intent,
    list_intents,
    record_nudge,
    validate_nudge,
)


# ── registry ─────────────────────────────────────────────────────────────────

def test_three_agents_each_have_intents():
    assert set(VALID_AGENTS) == {"sentinel", "strategist", "curator"}
    for agent in VALID_AGENTS:
        assert list_intents(agent), f"{agent} has no intents"


def test_intents_match_spec():
    keys = {a: {i.key for i in list_intents(a)} for a in VALID_AGENTS}
    assert keys["sentinel"] == {"watch", "ignore", "boost_source"}
    assert keys["strategist"] == {"rerun_sim", "draft_counter"}
    assert keys["curator"] == {"explain_score", "mark_outcome_verified"}


def test_list_intents_unknown_agent_is_empty():
    assert list_intents("nobody") == []


def test_get_intent_is_case_insensitive():
    assert get_intent("Sentinel", "WATCH").key == "watch"


# ── validation ───────────────────────────────────────────────────────────────

def test_validate_ok_returns_intent():
    it = validate_nudge("strategist", "rerun_sim", target={"scenario_id": "s1"})
    assert it.key == "rerun_sim"


def test_validate_rejects_unknown_agent():
    with pytest.raises(NudgeError, match="unknown agent"):
        validate_nudge("oracle", "watch", target={"x": 1})


def test_validate_rejects_intent_not_on_agent():
    # rerun_sim belongs to strategist, not sentinel
    with pytest.raises(NudgeError, match="no intent"):
        validate_nudge("sentinel", "rerun_sim", target={"x": 1})


def test_validate_requires_target_when_intent_demands_one():
    with pytest.raises(NudgeError, match="requires a target"):
        validate_nudge("sentinel", "watch", target=None)


# ── persistence ──────────────────────────────────────────────────────────────

def _db_returning(row):
    db = MagicMock()
    db.fetch_one = MagicMock(return_value=row)
    return db


def test_record_nudge_validates_then_inserts():
    row = {"id": "n1", "agent": "curator", "intent": "explain_score",
           "target": {"signal_id": "sig1"}, "note": None, "status": "queued",
           "created_by": "u1", "created_at": "2026-06-04T00:00:00Z"}
    db = _db_returning(row)
    out = record_nudge(db, agent="curator", intent_key="explain_score",
                       target={"signal_id": "sig1"}, created_by="u1")
    assert out["status"] == "queued"
    assert out["intent"] == "explain_score"
    assert db.fetch_one.called


def test_record_nudge_rejects_invalid_before_touching_db():
    db = _db_returning(None)
    with pytest.raises(NudgeError):
        record_nudge(db, agent="strategist", intent_key="explain_score",
                     target={"x": 1}, created_by="u1")
    db.fetch_one.assert_not_called()


# ── route (the wire) ─────────────────────────────────────────────────────────

def _client(db, user=None):
    from fastapi.testclient import TestClient
    from api.app import create_app
    from api.deps import get_db, get_current_user
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = (lambda: user)
    return TestClient(app)


def test_route_is_registered():
    from api.app import create_app
    app = create_app()
    routes = [(getattr(r, "path", ""), getattr(r, "methods", set()) or set())
              for r in app.routes]
    assert any(p == "/agents/{agent}/nudge" and "POST" in m for p, m in routes)
    assert any(p == "/agents/{agent}/intents" and "GET" in m for p, m in routes)


def test_get_intents_is_anonymous_and_lists_intents():
    client = _client(MagicMock(), user=None)
    r = client.get("/agents/strategist/intents")
    assert r.status_code == 200
    keys = {i["key"] for i in r.json()["intents"]}
    assert keys == {"rerun_sim", "draft_counter"}


def test_get_intents_unknown_agent_404():
    client = _client(MagicMock(), user=None)
    assert client.get("/agents/oracle/intents").status_code == 404


def test_post_nudge_requires_auth():
    client = _client(MagicMock(), user=None)
    r = client.post("/agents/sentinel/nudge", json={"intent": "watch",
                                                    "target": {"entity_id": "e1"}})
    assert r.status_code == 401


def test_post_nudge_happy_path():
    row = {"id": "n1", "agent": "sentinel", "intent": "watch",
           "target": {"entity_id": "e1"}, "note": None, "status": "queued",
           "created_by": "u1", "created_at": "2026-06-04T00:00:00Z"}
    db = MagicMock()
    db.fetch_one = MagicMock(return_value=row)
    client = _client(db, user={"id": "u1", "role": "uploader"})
    r = client.post("/agents/sentinel/nudge",
                    json={"intent": "watch", "target": {"entity_id": "e1"}})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["nudge"]["status"] == "queued"
    assert body["nudge"]["intent"] == "watch"


def test_post_nudge_invalid_intent_400():
    db = MagicMock()
    client = _client(db, user={"id": "u1", "role": "uploader"})
    r = client.post("/agents/sentinel/nudge",
                    json={"intent": "rerun_sim", "target": {"x": 1}})
    assert r.status_code == 400
