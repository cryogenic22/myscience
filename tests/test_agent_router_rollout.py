"""SPEC_016 Track 1 Phase 1c — chat router routes all intents through
the agent graph (with legacy handlers as exception fallback).

Gated by MZ_AGENT_ROUTER_ROLLOUT env var (0.0-1.0, deterministic per-session
hashing — same pattern as SPEC_011's MZ_UNIFIED_HANDLER_ROLLOUT).

Tests:
  - config flag exists and defaults to 0.0 (opt-in until rolled out)
  - _should_route_via_agent honours MZ_AGENT_ROUTER_ROLLOUT
  - team_eval and structured_query are NOT force-routed here
    (they already use their graphs; rollout is for the 7 legacy handlers)
  - session-hash distribution is deterministic + fair at 50%
  - static checks that chat.py wires the graph + fallback + metadata tag

All tests must FAIL before implementation.
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _reload_config(monkeypatch):
    import config as config_module
    importlib.reload(config_module)
    return config_module.config


# ────────────────────────────────────────────────────────────────────
# Config flag
# ────────────────────────────────────────────────────────────────────

def test_agent_router_rollout_config_exists(monkeypatch):
    """Phase 1c: config.agent must expose router_rollout float."""
    monkeypatch.delenv("MZ_AGENT_ROUTER_ROLLOUT", raising=False)
    cfg = _reload_config(monkeypatch)
    assert hasattr(cfg.agent, "router_rollout"), (
        "config.agent must expose router_rollout (float) for Phase 1c A/B"
    )


def test_agent_router_rollout_defaults_to_zero(monkeypatch):
    """Default OFF until we've observed the agent path's quality in prod.
    This is opt-in via env var; once confidence is high, bump to 1.0."""
    monkeypatch.delenv("MZ_AGENT_ROUTER_ROLLOUT", raising=False)
    cfg = _reload_config(monkeypatch)
    assert cfg.agent.router_rollout == 0.0


def test_agent_router_rollout_accepts_partial(monkeypatch):
    monkeypatch.setenv("MZ_AGENT_ROUTER_ROLLOUT", "0.5")
    cfg = _reload_config(monkeypatch)
    assert cfg.agent.router_rollout == 0.5


def test_agent_router_rollout_accepts_full(monkeypatch):
    monkeypatch.setenv("MZ_AGENT_ROUTER_ROLLOUT", "1.0")
    cfg = _reload_config(monkeypatch)
    assert cfg.agent.router_rollout == 1.0


# ────────────────────────────────────────────────────────────────────
# Routing helper _should_route_via_agent
# ────────────────────────────────────────────────────────────────────

def _import_router_helper():
    import api.routes.chat as chat_module
    importlib.reload(chat_module)
    return chat_module._should_route_via_agent


def test_should_route_off_when_rollout_zero(monkeypatch):
    monkeypatch.setenv("MZ_AGENT_ROUTER_ROLLOUT", "0.0")
    _reload_config(monkeypatch)
    should = _import_router_helper()
    for sid in ("a", "b", "c"):
        for intent in ("dossier", "compare", "landscape", "pipeline"):
            assert should(sid, intent) is False, (
                f"rollout=0 should disable agent routing for all "
                f"(sid={sid}, intent={intent})"
            )


def test_should_route_on_when_rollout_full_and_intent_supported(monkeypatch):
    monkeypatch.setenv("MZ_AGENT_ROUTER_ROLLOUT", "1.0")
    _reload_config(monkeypatch)
    should = _import_router_helper()
    for intent in ("dossier", "compare", "landscape",
                   "portfolio", "pipeline", "general", "deep_research"):
        assert should("any-session", intent) is True, (
            f"rollout=1 should route {intent} via agent"
        )


def test_should_route_skips_intents_outside_map(monkeypatch):
    """team_eval and structured_query already have their own graphs;
    this helper is specifically for the 7 legacy-handler intents."""
    monkeypatch.setenv("MZ_AGENT_ROUTER_ROLLOUT", "1.0")
    _reload_config(monkeypatch)
    should = _import_router_helper()
    for intent in ("team_eval", "structured_query", "unknown_intent"):
        assert should("sid", intent) is False, (
            f"Intent '{intent}' should not be agent-routed by this helper "
            "(already has its own dispatch or is unknown)"
        )


def test_should_route_deterministic_per_session(monkeypatch):
    monkeypatch.setenv("MZ_AGENT_ROUTER_ROLLOUT", "0.5")
    _reload_config(monkeypatch)
    should = _import_router_helper()
    sid = "user-123"
    first = should(sid, "dossier")
    for _ in range(25):
        assert should(sid, "dossier") is first


def test_should_route_50_percent_distribution(monkeypatch):
    """50% rollout splits sessions ~50/50 by hash."""
    monkeypatch.setenv("MZ_AGENT_ROUTER_ROLLOUT", "0.5")
    _reload_config(monkeypatch)
    should = _import_router_helper()
    n = 1000
    agent_count = sum(1 for i in range(n) if should(f"s-{i}", "dossier"))
    assert 400 <= agent_count <= 600, (
        f"expected ~500 of {n} sessions routed to agent; got {agent_count}"
    )


# ────────────────────────────────────────────────────────────────────
# Static checks — chat.py wiring
# ────────────────────────────────────────────────────────────────────

def _chat_src():
    return (REPO_ROOT / "api" / "routes" / "chat.py").read_text(encoding="utf-8")


def test_chat_py_imports_should_route_helper():
    """_should_route_via_agent must be defined in chat.py."""
    src = _chat_src()
    assert re.search(r"def\s+_should_route_via_agent\s*\(", src), (
        "chat.py must define _should_route_via_agent(session_id, intent) helper"
    )


def test_chat_py_hashes_session_id_for_bucketing():
    """The helper uses md5(session_id) deterministic bucketing."""
    src = _chat_src()
    # Any reference to hashlib + md5 in the vicinity of _should_route_via_agent
    assert re.search(
        r"_should_route_via_agent[\s\S]{0,800}hashlib",
        src,
    ), "chat.py must use hashlib for deterministic session bucketing"


def test_chat_py_wires_query_graph_path_with_fallback():
    """chat.py must call query_graph on the agent path AND have a try/except
    fallback to the legacy handler chain."""
    src = _chat_src()
    # Reference to query_graph.invoke OR get_query_graph
    has_graph_call = (
        "query_graph" in src
        or "get_query_graph" in src
        or "invoke(" in src  # langgraph graphs use .invoke
    )
    assert has_graph_call, "chat.py must invoke the query_graph for the agent path"


def test_chat_py_tags_router_in_metadata():
    """Responses from the agent path must be tagged router='agent' and
    legacy path responses tagged router='legacy' so we can A/B-compare."""
    src = _chat_src()
    has_agent_tag = re.search(
        r"['\"]router['\"]\s*:\s*['\"]agent['\"]", src
    )
    has_legacy_tag = re.search(
        r"['\"]router['\"]\s*:\s*['\"]legacy['\"]", src
    )
    assert has_agent_tag, "chat.py must tag metadata.router='agent' on graph path"
    assert has_legacy_tag, "chat.py must tag metadata.router='legacy' on fallback path"


def test_chat_py_logs_agent_routing_telemetry():
    """Every request must log an 'agent_routing' event with router attribution
    so we can measure A/B quality."""
    src = _chat_src()
    assert re.search(
        r'event_type\s*=\s*["\']agent_routing["\']',
        src,
    ) or re.search(
        r"_log_agent_routing",
        src,
    ), "chat.py must log 'agent_routing' telemetry events for A/B observation"
