"""BE-5 — agent nudge tests."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest


# ════════════════════════════════════════════════════════════════════
# nudge_intents service
# ════════════════════════════════════════════════════════════════════

class TestRegistry:
    def test_list_all(self):
        from services.agent.nudge_intents import list_intents
        out = list_intents()
        assert set(out.keys()) == {"sentinel", "strategist", "curator"}

    def test_list_for_agent(self):
        from services.agent.nudge_intents import list_intents
        out = list_intents("sentinel")
        assert "watch_entity" in out
        assert "boost_source" in out

    def test_list_unknown_agent_returns_empty(self):
        from services.agent.nudge_intents import list_intents
        assert list_intents("bogus") == {}


class TestValidate:
    def test_unknown_agent_raises(self):
        from services.agent.nudge_intents import validate
        with pytest.raises(ValueError, match="unknown agent"):
            validate("bogus", "watch_entity", {})

    def test_unknown_intent_for_agent_raises(self):
        from services.agent.nudge_intents import validate
        with pytest.raises(ValueError, match="not valid"):
            validate("sentinel", "rerun_simulation", {})

    def test_missing_required_payload_raises(self):
        from services.agent.nudge_intents import validate
        with pytest.raises(ValueError, match="missing required"):
            validate("sentinel", "watch_entity", {})

    def test_well_formed_passes(self):
        from services.agent.nudge_intents import validate
        validate("sentinel", "watch_entity",
                 {"entity_type": "drug", "entity_id": "drug-1"})
        validate("strategist", "rerun_simulation", {"war_room_id": "wr-1"})
        validate("curator", "explain_score", {"signal_id": "sig-1"})


# ════════════════════════════════════════════════════════════════════
# Dispatcher
# ════════════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def _clear_idempotency():
    """Reset the per-process cache between tests so each one starts fresh."""
    from services.agent import nudge_intents as svc
    svc._IDEMPOTENCY_CACHE.clear()
    yield
    svc._IDEMPOTENCY_CACHE.clear()


class TestDispatch:
    def test_logs_event_and_returns_event_id(self):
        from services.agent.nudge_intents import dispatch
        db = MagicMock()
        db.fetch_one.return_value = {"id": "evt-123"}

        out = dispatch(db, agent="sentinel", intent="watch_entity",
                       payload={"entity_type": "drug", "entity_id": "drug-1"},
                       actor="user-1")
        assert out.accepted is True
        assert out.event_id == "evt-123"
        assert out.deduped is False

        # Inspect the INSERT
        sql, params = db.fetch_one.call_args.args
        assert "insert into agent_events" in sql.lower()
        # tool_name slot holds the intent (per agent_events schema)
        assert "watch_entity" in params

    def test_idempotent_within_window(self):
        from services.agent.nudge_intents import dispatch
        db = MagicMock()
        db.fetch_one.return_value = {"id": "evt-A"}
        out1 = dispatch(db, agent="sentinel", intent="boost_source",
                        payload={"source_id": "fda"}, actor="u")
        out2 = dispatch(db, agent="sentinel", intent="boost_source",
                        payload={"source_id": "fda"}, actor="u")
        assert out1.deduped is False
        assert out2.deduped is True
        # Only ONE INSERT should have fired
        inserts = [c for c in db.fetch_one.call_args_list
                   if c.args and "insert into agent_events" in str(c.args[0]).lower()]
        assert len(inserts) == 1

    def test_idempotency_expires_after_window(self):
        from services.agent.nudge_intents import dispatch, IDEMPOTENCY_WINDOW_S
        db = MagicMock()
        db.fetch_one.return_value = {"id": "evt-A"}

        t0 = 1000.0
        t1 = t0 + IDEMPOTENCY_WINDOW_S + 1  # past the window
        out1 = dispatch(db, agent="sentinel", intent="boost_source",
                        payload={"source_id": "fda"}, actor="u", now=t0)
        out2 = dispatch(db, agent="sentinel", intent="boost_source",
                        payload={"source_id": "fda"}, actor="u", now=t1)
        assert out1.deduped is False
        assert out2.deduped is False
        inserts = [c for c in db.fetch_one.call_args_list
                   if c.args and "insert into agent_events" in str(c.args[0]).lower()]
        assert len(inserts) == 2

    def test_different_payload_is_not_dedup(self):
        from services.agent.nudge_intents import dispatch
        db = MagicMock()
        db.fetch_one.return_value = {"id": "evt-X"}
        dispatch(db, agent="sentinel", intent="watch_entity",
                 payload={"entity_type": "drug", "entity_id": "a"}, actor="u")
        out = dispatch(db, agent="sentinel", intent="watch_entity",
                       payload={"entity_type": "drug", "entity_id": "b"}, actor="u")
        assert out.deduped is False

    def test_db_failure_is_non_fatal(self):
        from services.agent.nudge_intents import dispatch
        db = MagicMock()
        db.fetch_one.side_effect = RuntimeError("agent_events missing")
        # Must NOT raise — nudge UX isn't worth a 500
        out = dispatch(db, agent="sentinel", intent="boost_source",
                       payload={"source_id": "fda"}, actor="u")
        assert out.accepted is True
        assert out.event_id is None


# ════════════════════════════════════════════════════════════════════
# Endpoint shape
# ════════════════════════════════════════════════════════════════════

class TestEndpointShape:
    def test_intents_route_registered(self):
        from api.app import create_app
        app = create_app()
        paths = {r.path for r in app.routes}
        assert "/agents/intents" in paths
        assert "/agents/{agent}/nudge" in paths
        # Versioned alias
        assert "/api/v1/agents/{agent}/nudge" in paths
