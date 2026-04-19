"""SPEC-011: CTX ContextGuard as Default + A/B Rollout — TDD test contract.

These tests verify that:
1. MZ_UNIFIED_HANDLER defaults to true (was false)
2. MZ_UNIFIED_HANDLER_ROLLOUT (new) controls A/B traffic split
3. Routing helper _should_use_unified_handler() works as designed
4. Per-session determinism (same session → same handler)
5. CTX guard suppresses hallucinated citation markers
6. Fallback to legacy on UnifiedChatHandler exception
7. chat_routing telemetry captures handler attribution

Run BEFORE implementing fixes to confirm they all FAIL (TDD discipline).
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


# ────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────

def _reload_config(monkeypatch):
    """Force config module to re-read env vars."""
    import config as config_module
    importlib.reload(config_module)
    return config_module.config


# ────────────────────────────────────────────────────────────────────
# Category 1: Config defaults
# ────────────────────────────────────────────────────────────────────

def test_unified_handler_default_is_true(monkeypatch):
    """SPEC-011: MZ_UNIFIED_HANDLER must default to true (was false)."""
    monkeypatch.delenv("MZ_UNIFIED_HANDLER", raising=False)
    cfg = _reload_config(monkeypatch)
    assert cfg.agent.use_unified_handler is True


def test_unified_handler_rollout_default_is_full(monkeypatch):
    """SPEC-011: MZ_UNIFIED_HANDLER_ROLLOUT must default to 1.0 (full rollout)."""
    monkeypatch.delenv("MZ_UNIFIED_HANDLER_ROLLOUT", raising=False)
    cfg = _reload_config(monkeypatch)
    assert cfg.agent.unified_handler_rollout == 1.0


def test_unified_handler_can_be_disabled(monkeypatch):
    """Hard kill switch: MZ_UNIFIED_HANDLER=false disables regardless of rollout."""
    monkeypatch.setenv("MZ_UNIFIED_HANDLER", "false")
    cfg = _reload_config(monkeypatch)
    assert cfg.agent.use_unified_handler is False


def test_rollout_accepts_partial(monkeypatch):
    monkeypatch.setenv("MZ_UNIFIED_HANDLER_ROLLOUT", "0.5")
    cfg = _reload_config(monkeypatch)
    assert cfg.agent.unified_handler_rollout == 0.5


def test_rollout_zero(monkeypatch):
    monkeypatch.setenv("MZ_UNIFIED_HANDLER_ROLLOUT", "0.0")
    cfg = _reload_config(monkeypatch)
    assert cfg.agent.unified_handler_rollout == 0.0


# ────────────────────────────────────────────────────────────────────
# Category 2: Routing helper
# ────────────────────────────────────────────────────────────────────

def _import_router():
    """Import the routing helper after config reload. Module may need reload too."""
    import api.routes.chat as chat_module
    importlib.reload(chat_module)
    return chat_module._should_use_unified_handler


def test_routing_hard_off_when_handler_disabled(monkeypatch):
    """If MZ_UNIFIED_HANDLER=false, no session is routed to unified."""
    monkeypatch.setenv("MZ_UNIFIED_HANDLER", "false")
    monkeypatch.setenv("MZ_UNIFIED_HANDLER_ROLLOUT", "1.0")
    _reload_config(monkeypatch)
    should_use = _import_router()
    for sid in ("a", "b", "c", "d"):
        assert should_use(sid) is False


def test_routing_full_rollout_routes_all(monkeypatch):
    monkeypatch.setenv("MZ_UNIFIED_HANDLER", "true")
    monkeypatch.setenv("MZ_UNIFIED_HANDLER_ROLLOUT", "1.0")
    _reload_config(monkeypatch)
    should_use = _import_router()
    for sid in ("a", "b", "c", "d"):
        assert should_use(sid) is True


def test_routing_zero_rollout_routes_none(monkeypatch):
    monkeypatch.setenv("MZ_UNIFIED_HANDLER", "true")
    monkeypatch.setenv("MZ_UNIFIED_HANDLER_ROLLOUT", "0.0")
    _reload_config(monkeypatch)
    should_use = _import_router()
    for sid in ("a", "b", "c", "d"):
        assert should_use(sid) is False


def test_routing_50_percent_distribution(monkeypatch):
    """50% rollout should split traffic ~50/50 across many sessions."""
    monkeypatch.setenv("MZ_UNIFIED_HANDLER", "true")
    monkeypatch.setenv("MZ_UNIFIED_HANDLER_ROLLOUT", "0.5")
    _reload_config(monkeypatch)
    should_use = _import_router()
    routed_unified = sum(
        1 for i in range(1000)
        if should_use(f"session-{i}")
    )
    # md5 distribution is uniform — allow ±5% variance
    assert 450 <= routed_unified <= 550, (
        f"Expected ~500 of 1000 routed to unified, got {routed_unified}"
    )


def test_routing_25_percent_distribution(monkeypatch):
    """25% rollout should route ~250 of 1000."""
    monkeypatch.setenv("MZ_UNIFIED_HANDLER", "true")
    monkeypatch.setenv("MZ_UNIFIED_HANDLER_ROLLOUT", "0.25")
    _reload_config(monkeypatch)
    should_use = _import_router()
    routed_unified = sum(
        1 for i in range(1000)
        if should_use(f"session-{i}")
    )
    assert 200 <= routed_unified <= 300, (
        f"Expected ~250 of 1000, got {routed_unified}"
    )


def test_routing_is_deterministic_per_session(monkeypatch):
    """Same session_id must always route the same way (no flapping)."""
    monkeypatch.setenv("MZ_UNIFIED_HANDLER", "true")
    monkeypatch.setenv("MZ_UNIFIED_HANDLER_ROLLOUT", "0.5")
    _reload_config(monkeypatch)
    should_use = _import_router()
    sid = "user-abc-123"
    first = should_use(sid)
    for _ in range(50):
        assert should_use(sid) is first


def test_routing_handles_default_session(monkeypatch):
    """The literal 'default' session_id used for unauthenticated callers
    must route deterministically and not crash."""
    monkeypatch.setenv("MZ_UNIFIED_HANDLER", "true")
    monkeypatch.setenv("MZ_UNIFIED_HANDLER_ROLLOUT", "0.5")
    _reload_config(monkeypatch)
    should_use = _import_router()
    # Just confirms it returns a bool deterministically
    a = should_use("default")
    b = should_use("default")
    assert a is b
    assert isinstance(a, bool)


# ────────────────────────────────────────────────────────────────────
# Category 3: Response handler tagging
# ────────────────────────────────────────────────────────────────────

def test_chat_route_tags_unified_handler_in_payload_metadata():
    """STATIC: chat.py must set metadata.handler='unified' on the unified-path payload."""
    src = (REPO_ROOT / "api" / "routes" / "chat.py").read_text(encoding="utf-8")
    # Look for "handler": "unified" near payload["metadata"] assignment (within ~200 chars)
    has_tag = re.search(
        r"payload\[['\"]metadata['\"]\][\s\S]{0,200}['\"]handler['\"]:\s*['\"]unified['\"]",
        src,
    )
    assert has_tag, (
        "chat.py must tag the unified-path payload with metadata.handler='unified'"
    )


def test_chat_route_tags_legacy_handler_in_payload_metadata():
    """STATIC: chat.py must set metadata.handler='legacy' on the legacy-path payload."""
    src = (REPO_ROOT / "api" / "routes" / "chat.py").read_text(encoding="utf-8")
    has_tag = re.search(
        r"payload\[['\"]metadata['\"]\][\s\S]{0,200}['\"]handler['\"]:\s*['\"]legacy['\"]",
        src,
    )
    assert has_tag, (
        "chat.py must tag the legacy-path payload with metadata.handler='legacy'"
    )


def test_chat_route_calls_log_chat_routing():
    """STATIC: chat.py must call _log_chat_routing for both unified and legacy paths."""
    src = (REPO_ROOT / "api" / "routes" / "chat.py").read_text(encoding="utf-8")
    unified_call = re.search(r'_log_chat_routing\s*\(\s*["\']unified["\']', src)
    legacy_call = re.search(r'_log_chat_routing\s*\(\s*["\']legacy["\']', src)
    assert unified_call, "chat.py must call _log_chat_routing('unified', ...)"
    assert legacy_call, "chat.py must call _log_chat_routing('legacy', ...)"


def test_chat_route_logs_fallback_when_unified_handler_errors():
    """STATIC: when UnifiedChatHandler raises, must log fallback=True telemetry."""
    src = (REPO_ROOT / "api" / "routes" / "chat.py").read_text(encoding="utf-8")
    # Permissive: any _log_chat_routing call somewhere with fallback=True
    has_fallback_log = re.search(
        r"_log_chat_routing[\s\S]{0,400}fallback\s*=\s*True",
        src,
    )
    assert has_fallback_log, (
        "chat.py must call _log_chat_routing(..., fallback=True, ...) "
        "in the UnifiedChatHandler except block"
    )


# ────────────────────────────────────────────────────────────────────
# Category 4: CTX guard suppression
# ────────────────────────────────────────────────────────────────────

def test_ctx_guard_check_response_exists():
    """SPEC-011: CTXQueryPipeline.check_response must exist for guard functionality."""
    from services.ctx_pipeline import CTXQueryPipeline
    assert hasattr(CTXQueryPipeline, "check_response")


def test_ctx_guard_detects_unknown_entity_in_response():
    """The guard must detect hallucinated entity-like tokens not in the corpus."""
    from ctxpack.modules.guard import ContextGuard
    guard = ContextGuard(known_entity_names={"DRUG-Semaglutide", "DRUG-Tirzepatide"})
    # Hallucinated unknown entity ID in the response
    response = "Per source DRUG-Madeupzepamide, the dose is 0.5mg [DOC-99]."
    result = guard.check(response)
    assert result.low_confidence is True, (
        "guard must flag low_confidence when unknown entity ID is mentioned"
    )
    assert result.unknown_entities, (
        "guard must list the unknown entity DRUG-Madeupzepamide"
    )


def test_ctx_guard_passes_grounded_response():
    """Grounded text with no fishy entity IDs returns low_confidence=False."""
    from ctxpack.modules.guard import ContextGuard
    guard = ContextGuard(known_entity_names={"DRUG-Semaglutide"})
    response = "Semaglutide showed weight loss in clinical trials."
    result = guard.check(response)
    assert result.low_confidence is False, (
        f"grounded response should pass; got signals={result.signals_detected}, "
        f"unknown={result.unknown_entities}"
    )


# ────────────────────────────────────────────────────────────────────
# Category 5: Telemetry contract
# ────────────────────────────────────────────────────────────────────

def test_log_chat_routing_helper_exists():
    """STATIC: chat.py must define a _log_chat_routing helper that emits
    a 'chat_routing' telemetry event."""
    src = (REPO_ROOT / "api" / "routes" / "chat.py").read_text(encoding="utf-8")
    assert re.search(r"def\s+_log_chat_routing\s*\(", src), (
        "chat.py must define _log_chat_routing helper"
    )
    assert re.search(r'event_type\s*=\s*["\']chat_routing["\']', src), (
        "chat.py must log telemetry with event_type='chat_routing'"
    )


def test_log_chat_routing_includes_handler_in_metadata():
    """STATIC: telemetry helper must populate metadata.handler from arg."""
    src = (REPO_ROOT / "api" / "routes" / "chat.py").read_text(encoding="utf-8")
    # The helper signature should accept handler as first positional, and place it in metadata
    assert re.search(
        r'metadata\s*=\s*\{[^}]*["\']handler["\']:\s*handler',
        src, re.DOTALL,
    ), "_log_chat_routing must put handler arg into metadata.handler"
