"""Permission engine for the agent harness.

Enforces trust-tier access control at the tool execution boundary.
Four tiers: public (read-only), standard (write-safe), elevated (write-risky),
system (destructive — requires explicit approval).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class TrustTier(Enum):
    PUBLIC = "public"
    STANDARD = "standard"
    ELEVATED = "elevated"
    SYSTEM = "system"


class SessionMode(Enum):
    AUTONOMOUS = "autonomous"    # background agents, no human present
    STANDARD = "standard"        # API request, user initiated
    SUPERVISED = "supervised"    # human reviewing every action


class PermissionDenied(Exception):
    """Raised when a tool invocation is denied by the permission engine."""

    def __init__(self, tool_name: str, tier: str, mode: str, reason: str = ""):
        self.tool_name = tool_name
        self.tier = tier
        self.mode = mode
        self.reason = reason
        super().__init__(
            f"Permission denied: {tool_name} (tier={tier}) in {mode} mode. {reason}"
        )


@dataclass
class PermissionDecision:
    allowed: bool
    tool_name: str
    trust_tier: str
    session_mode: str
    reason: str
    timestamp: datetime
    requires_approval: bool = False


_TIER_ORDER = {"public": 0, "standard": 1, "elevated": 2, "system": 3}


class PermissionEngine:
    """Enforces trust tier permissions at the tool execution boundary."""

    def __init__(self, default_mode: SessionMode = SessionMode.STANDARD):
        self.default_mode = default_mode
        self._decisions: list[PermissionDecision] = []
        self._approvals: set[str] = set()  # tool names with explicit approval

    def check(
        self,
        tool_name: str,
        trust_tier: str,
        mode: Optional[SessionMode] = None,
    ) -> PermissionDecision:
        """Check if a tool invocation is permitted."""
        effective_mode = mode or self.default_mode
        tier_level = _TIER_ORDER.get(trust_tier, 1)
        now = datetime.now(timezone.utc)

        # Public and standard tiers: always allowed
        if tier_level <= 1:
            decision = PermissionDecision(
                allowed=True,
                tool_name=tool_name,
                trust_tier=trust_tier,
                session_mode=effective_mode.value,
                reason="Tier within standard range",
                timestamp=now,
            )
            self._decisions.append(decision)
            return decision

        # Elevated tier: allowed in all modes, but logged in autonomous
        if tier_level == 2:
            if effective_mode == SessionMode.AUTONOMOUS:
                logger.warning(
                    "ELEVATED tool %s invoked in autonomous mode — logging action",
                    tool_name,
                )
            decision = PermissionDecision(
                allowed=True,
                tool_name=tool_name,
                trust_tier=trust_tier,
                session_mode=effective_mode.value,
                reason=(
                    "Elevated tier — action logged"
                    if effective_mode == SessionMode.AUTONOMOUS
                    else "Elevated tier — user-initiated"
                ),
                timestamp=now,
            )
            self._decisions.append(decision)
            return decision

        # System tier: requires explicit approval
        if tier_level >= 3:
            if tool_name in self._approvals:
                decision = PermissionDecision(
                    allowed=True,
                    tool_name=tool_name,
                    trust_tier=trust_tier,
                    session_mode=effective_mode.value,
                    reason="System tier — explicit approval granted",
                    timestamp=now,
                )
                self._decisions.append(decision)
                return decision
            else:
                decision = PermissionDecision(
                    allowed=False,
                    tool_name=tool_name,
                    trust_tier=trust_tier,
                    session_mode=effective_mode.value,
                    reason="System tier requires explicit approval",
                    timestamp=now,
                    requires_approval=True,
                )
                self._decisions.append(decision)
                return decision

        # Default deny (unreachable with valid tiers, but defensive)
        decision = PermissionDecision(
            allowed=False,
            tool_name=tool_name,
            trust_tier=trust_tier,
            session_mode=effective_mode.value,
            reason="Unknown tier",
            timestamp=now,
        )
        self._decisions.append(decision)
        return decision

    def enforce(
        self,
        tool_name: str,
        trust_tier: str,
        mode: Optional[SessionMode] = None,
    ) -> None:
        """Check and raise PermissionDenied if not allowed."""
        decision = self.check(tool_name, trust_tier, mode)
        if not decision.allowed:
            raise PermissionDenied(
                tool_name, trust_tier, decision.session_mode, decision.reason
            )

    def grant_approval(self, tool_name: str) -> None:
        """Grant explicit approval for a system-tier tool."""
        self._approvals.add(tool_name)
        logger.info("Approval granted for system-tier tool: %s", tool_name)

    def revoke_approval(self, tool_name: str) -> None:
        """Revoke approval for a system-tier tool."""
        self._approvals.discard(tool_name)

    def get_decisions(self, limit: int = 50) -> list[PermissionDecision]:
        """Get recent permission decisions."""
        return self._decisions[-limit:]

    def get_denied_count(self) -> int:
        """Count denied decisions."""
        return sum(1 for d in self._decisions if not d.allowed)
