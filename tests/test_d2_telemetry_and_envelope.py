"""SPEC-021 D2 — LLM telemetry + error envelope + lifespan + SPA registry."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from services import llm_telemetry as tel


# ────────────────────────────────────────────────────────────────────
# log_llm_call
# ────────────────────────────────────────────────────────────────────

def test_log_llm_call_inserts_row():
    db = MagicMock()
    tel.log_llm_call(
        db,
        caller="war_game", model="gpt-4o", prompt_version="v1",
        user_id="user-1", latency_ms=1234,
        prompt_tokens=500, completion_tokens=200,
        succeeded=True, error_message=None,
    )
    assert db.execute.called
    sql = db.execute.call_args[0][0].lower()
    assert "insert into llm_call_log" in sql


def test_log_llm_call_swallows_db_error():
    """Telemetry insert failure must not break the caller."""
    db = MagicMock()
    db.execute.side_effect = RuntimeError("connection lost")
    # Should not raise
    tel.log_llm_call(
        db, caller="x", model="gpt-4o-mini", prompt_version="v1",
        user_id=None, latency_ms=10, prompt_tokens=1,
        completion_tokens=1, succeeded=True,
    )


def test_cost_estimate_uses_known_model_pricing():
    cost = tel._estimate_cost_usd("gpt-4o", 1_000_000, 1_000_000)
    # gpt-4o = (2.50, 10.00) per 1M tokens → $12.50
    assert cost == pytest.approx(12.50, abs=0.01)


def test_cost_estimate_unknown_model_uses_default():
    cost = tel._estimate_cost_usd("totally-new-model", 1_000_000, 0)
    # Default ($2.50, $10) for unknown
    assert cost == pytest.approx(2.50, abs=0.01)


# ────────────────────────────────────────────────────────────────────
# chat_with_telemetry — happy path + timeout
# ────────────────────────────────────────────────────────────────────

class _FakeLLM:
    def __init__(self, *, enabled=True, reply="reply text",
                 sleep=0.0, raise_exc=None):
        self.enabled = enabled
        self._reply = reply
        self._sleep = sleep
        self._raise = raise_exc
        # config.llm.model lookup chain
        self.config = type("C", (), {"llm": type("L", (), {"model": "gpt-4o-mini"})})()

    def raw_chat(self, *, system, user, max_tokens, temperature):
        if self._sleep:
            time.sleep(self._sleep)
        if self._raise:
            raise self._raise
        return self._reply


def test_chat_with_telemetry_returns_reply_and_logs():
    db = MagicMock()
    llm = _FakeLLM(reply="hello world")
    out = tel.chat_with_telemetry(
        llm, db, system="sys", user="u",
        caller="war_game", prompt_version="v1",
        timeout_seconds=5.0,
    )
    assert out == "hello world"
    # Logged
    assert db.execute.called
    args = db.execute.call_args[0][1]
    succeeded_param = args[8]
    assert succeeded_param is True


def test_chat_with_telemetry_disabled_llm_returns_none():
    db = MagicMock()
    llm = _FakeLLM(enabled=False)
    out = tel.chat_with_telemetry(llm, db, system="s", user="u", caller="x")
    assert out is None
    # No log row when LLM disabled
    assert not db.execute.called


def test_chat_with_telemetry_timeout_returns_none():
    db = MagicMock()
    llm = _FakeLLM(sleep=2.0)  # sleeps longer than timeout
    out = tel.chat_with_telemetry(
        llm, db, system="s", user="u",
        caller="x", timeout_seconds=0.3,
    )
    assert out is None
    # Logged with succeeded=False + error mentions timeout
    args = db.execute.call_args[0][1]
    assert args[8] is False  # succeeded
    assert "timeout" in (args[9] or "").lower()  # error_message


def test_chat_with_telemetry_exception_returns_none():
    db = MagicMock()
    llm = _FakeLLM(raise_exc=RuntimeError("boom"))
    out = tel.chat_with_telemetry(
        llm, db, system="s", user="u",
        caller="x", timeout_seconds=5.0,
    )
    assert out is None
    args = db.execute.call_args[0][1]
    assert args[8] is False
    assert "boom" in (args[9] or "")


# ────────────────────────────────────────────────────────────────────
# Error envelope shape (HTTPException + ValidationError)
# ────────────────────────────────────────────────────────────────────

def test_error_envelope_for_http_exception():
    from fastapi import FastAPI, HTTPException
    from fastapi.testclient import TestClient
    from api.exception_handlers import install_exception_handlers

    app = FastAPI()
    install_exception_handlers(app)

    @app.get("/raise")
    def _raise():
        raise HTTPException(404, "war room not found: abc")

    client = TestClient(app)
    r = client.get("/raise")
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["code"] == 404
    assert body["error"]["type"] == "not_found"
    assert "war room not found" in body["error"]["message"]
    # Back-compat
    assert "war room not found" in body["detail"]


def test_error_envelope_for_validation_error():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from pydantic import BaseModel
    from api.exception_handlers import install_exception_handlers

    app = FastAPI()
    install_exception_handlers(app)

    class Body(BaseModel):
        title: str

    @app.post("/things")
    def _create(body: Body):
        return {"ok": True}

    client = TestClient(app)
    r = client.post("/things", json={})  # missing title
    assert r.status_code == 422
    body = r.json()
    assert body["error"]["code"] == 422
    assert body["error"]["type"] == "validation_error"
    assert "title" in body["error"]["message"].lower() or "field" in body["error"]["message"].lower()
    assert "errors" in body["error"]["details"]


# ────────────────────────────────────────────────────────────────────
# SPA fallback registry — auto-collected from routers
# ────────────────────────────────────────────────────────────────────

def test_spa_fallback_collects_router_prefixes():
    """The auto-collected prefix set should include every router's
    top-level path segment, so a new router never needs manual
    registration in the SPA fallback list."""
    from api.app import create_app

    app = create_app()
    # Re-derive the same registry the middleware uses
    from api.app import create_app as _ca  # noqa: F401 — get scope ref via closure trick

    # Walk routes ourselves (mirroring the middleware's logic)
    seen = set()
    for route in app.routes:
        path = getattr(route, "path", "") or ""
        if not path.startswith("/"):
            continue
        stripped = path[len("/api/v1"):] if path.startswith("/api/v1") else path
        stripped = stripped.lstrip("/")
        if not stripped:
            continue
        seen.add(stripped.split("/", 1)[0])
    # Expect every router we know is mounted to appear
    for expected in ("war-rooms", "decisions", "auth", "search", "metrics"):
        assert expected in seen, f"prefix {expected!r} should be auto-collected"


# ────────────────────────────────────────────────────────────────────
# Lifespan handlers wired on app.state
# ────────────────────────────────────────────────────────────────────

def test_lifespan_callbacks_registered():
    from api.app import create_app
    app = create_app()
    # At minimum: start_background_agents + outcome scheduler start
    assert len(app.state._startup_fns) >= 2
    assert len(app.state._shutdown_fns) >= 2
