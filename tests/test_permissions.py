"""Tests for services/agent/permissions.py — trust tier permission engine.

TDD: Verify tier-based access control, approval flow, audit trail.
"""

from __future__ import annotations

import logging

import pytest

from services.agent.permissions import (
    PermissionDenied,
    PermissionEngine,
    SessionMode,
    TrustTier,
)


class TestPermissionEngine:
    """Verify permission decisions across trust tiers and session modes."""

    def test_public_always_allowed(self):
        """Public tier is allowed in all session modes."""
        engine = PermissionEngine()
        for mode in SessionMode:
            decision = engine.check("rag_search", TrustTier.PUBLIC.value, mode)
            assert decision.allowed is True
            assert decision.trust_tier == "public"

    def test_standard_always_allowed(self):
        """Standard tier is allowed in all session modes."""
        engine = PermissionEngine()
        for mode in SessionMode:
            decision = engine.check("sql_query", TrustTier.STANDARD.value, mode)
            assert decision.allowed is True
            assert decision.trust_tier == "standard"

    def test_elevated_allowed_in_standard(self):
        """Elevated tier is allowed when session mode is standard."""
        engine = PermissionEngine()
        decision = engine.check("run_steward", TrustTier.ELEVATED.value, SessionMode.STANDARD)
        assert decision.allowed is True
        assert "user-initiated" in decision.reason

    def test_elevated_allowed_in_autonomous_but_logged(self, caplog):
        """Elevated tier is allowed in autonomous mode but emits a warning log."""
        engine = PermissionEngine()
        with caplog.at_level(logging.WARNING):
            decision = engine.check("run_steward", TrustTier.ELEVATED.value, SessionMode.AUTONOMOUS)
        assert decision.allowed is True
        assert "logged" in decision.reason.lower()
        assert any("ELEVATED" in r.message for r in caplog.records)

    def test_system_denied_without_approval(self):
        """System tier is denied by default (no explicit approval)."""
        engine = PermissionEngine()
        decision = engine.check("drop_table", TrustTier.SYSTEM.value, SessionMode.STANDARD)
        assert decision.allowed is False
        assert decision.requires_approval is True
        assert "explicit approval" in decision.reason.lower()

    def test_system_allowed_with_approval(self):
        """System tier is allowed after grant_approval() is called."""
        engine = PermissionEngine()
        engine.grant_approval("drop_table")
        decision = engine.check("drop_table", TrustTier.SYSTEM.value, SessionMode.STANDARD)
        assert decision.allowed is True
        assert "approval granted" in decision.reason.lower()

    def test_enforce_raises_on_denied(self):
        """enforce() raises PermissionDenied when check returns denied."""
        engine = PermissionEngine()
        with pytest.raises(PermissionDenied) as exc_info:
            engine.enforce("drop_table", TrustTier.SYSTEM.value)
        assert exc_info.value.tool_name == "drop_table"
        assert exc_info.value.tier == "system"

    def test_enforce_passes_on_allowed(self):
        """enforce() returns None when the tool is allowed."""
        engine = PermissionEngine()
        result = engine.enforce("rag_search", TrustTier.PUBLIC.value)
        assert result is None

    def test_decisions_recorded(self):
        """check() records every decision in the audit trail."""
        engine = PermissionEngine()
        engine.check("tool_a", TrustTier.PUBLIC.value)
        engine.check("tool_b", TrustTier.STANDARD.value)
        engine.check("tool_c", TrustTier.SYSTEM.value)
        decisions = engine.get_decisions()
        assert len(decisions) == 3
        assert decisions[0].tool_name == "tool_a"
        assert decisions[2].tool_name == "tool_c"

    def test_revoke_approval(self):
        """Revoking approval causes subsequent system-tier checks to deny."""
        engine = PermissionEngine()
        engine.grant_approval("dangerous_tool")
        # First check — allowed
        assert engine.check("dangerous_tool", TrustTier.SYSTEM.value).allowed is True
        # Revoke
        engine.revoke_approval("dangerous_tool")
        # Second check — denied
        assert engine.check("dangerous_tool", TrustTier.SYSTEM.value).allowed is False

    def test_denied_count(self):
        """get_denied_count() accurately counts denied decisions."""
        engine = PermissionEngine()
        engine.check("ok_tool", TrustTier.PUBLIC.value)       # allowed
        engine.check("sys_a", TrustTier.SYSTEM.value)         # denied
        engine.check("sys_b", TrustTier.SYSTEM.value)         # denied
        engine.check("std_tool", TrustTier.STANDARD.value)    # allowed
        assert engine.get_denied_count() == 2
