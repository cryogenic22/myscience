"""Unified event bus for all agent activity.

Tracks tool invocations, completions, failures, and session lifecycle
events. Persists to agent_events table (migration 029) and keeps a
capped in-memory buffer for fast recent-event queries.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4

logger = logging.getLogger(__name__)


class AgentEventType(Enum):
    TURN_START = "turn_start"
    TOOL_INVOKED = "tool_invoked"
    TOOL_COMPLETED = "tool_completed"
    TOOL_FAILED = "tool_failed"
    STEP_COMPLETED = "step_completed"
    BUDGET_WARNING = "budget_warning"
    APPROVAL_REQUESTED = "approval_requested"
    SESSION_CHECKPOINT = "session_checkpoint"
    SESSION_COMPLETED = "session_completed"
    SESSION_FAILED = "session_failed"
    PERMISSION_DENIED = "permission_denied"


@dataclass
class AgentEvent:
    event_type: AgentEventType
    session_id: str = ""
    agent_type: str = ""
    tool_name: Optional[str] = None
    trust_tier: Optional[str] = None
    args_hash: Optional[str] = None
    result_status: str = "ok"
    metadata: dict = field(default_factory=dict)
    timestamp: Optional[datetime] = None
    id: str = field(default_factory=lambda: str(uuid4()))

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc)


class EventStream:
    """Unified event bus for all agent activity."""

    def __init__(self, db=None):
        self.db = db
        self._events: list[AgentEvent] = []
        self._max_memory = 500  # cap in-memory events

    def emit(self, event: AgentEvent) -> None:
        """Emit an agent event -- persists to DB and keeps in memory."""
        self._events.append(event)
        if len(self._events) > self._max_memory:
            self._events = self._events[-self._max_memory:]

        if self.db:
            try:
                self.db.execute(
                    """INSERT INTO agent_events
                       (id, session_id, event_type, agent_type, tool_name,
                        trust_tier, args_hash, result_status, metadata, created_at)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    [event.id, event.session_id, event.event_type.value,
                     event.agent_type, event.tool_name, event.trust_tier,
                     event.args_hash, event.result_status,
                     json.dumps(event.metadata), event.timestamp],
                )
            except Exception as e:
                logger.warning("Failed to persist event: %s", e)

        logger.debug("Event: %s tool=%s session=%s",
                      event.event_type.value, event.tool_name, event.session_id)

    def emit_tool_invoked(self, session_id: str, agent_type: str,
                          tool_name: str, trust_tier: str, args: dict = None) -> AgentEvent:
        """Convenience: emit a tool_invoked event with args hash."""
        args_hash = hashlib.sha256(json.dumps(args or {}, sort_keys=True).encode()).hexdigest()[:16]
        event = AgentEvent(
            event_type=AgentEventType.TOOL_INVOKED,
            session_id=session_id,
            agent_type=agent_type,
            tool_name=tool_name,
            trust_tier=trust_tier,
            args_hash=args_hash,
        )
        self.emit(event)
        return event

    def emit_tool_completed(self, session_id: str, agent_type: str,
                            tool_name: str, result_status: str = "ok",
                            metadata: dict = None) -> AgentEvent:
        """Convenience: emit a tool_completed event."""
        event = AgentEvent(
            event_type=AgentEventType.TOOL_COMPLETED,
            session_id=session_id,
            agent_type=agent_type,
            tool_name=tool_name,
            result_status=result_status,
            metadata=metadata or {},
        )
        self.emit(event)
        return event

    def emit_tool_failed(self, session_id: str, agent_type: str,
                         tool_name: str, error: str) -> AgentEvent:
        """Convenience: emit a tool_failed event with error truncated to 500 chars."""
        event = AgentEvent(
            event_type=AgentEventType.TOOL_FAILED,
            session_id=session_id,
            agent_type=agent_type,
            tool_name=tool_name,
            result_status="error",
            metadata={"error": error[:500]},
        )
        self.emit(event)
        return event

    def get_recent(self, limit: int = 50, event_type: str = None,
                   agent_type: str = None) -> list[AgentEvent]:
        """Get recent events, optionally filtered."""
        events = self._events
        if event_type:
            events = [e for e in events if e.event_type.value == event_type]
        if agent_type:
            events = [e for e in events if e.agent_type == agent_type]
        return events[-limit:]

    def count_by_type(self) -> dict[str, int]:
        """Count events by type."""
        counts: dict[str, int] = {}
        for e in self._events:
            key = e.event_type.value
            counts[key] = counts.get(key, 0) + 1
        return counts
