"""Durable session persistence for agent runs.

Tracks agent sessions (steward, research, pipeline) through their lifecycle:
start -> checkpoint -> complete/fail. Supports crash recovery via checkpoints.

Works in two modes:
- With DB: persists to agent_sessions table (migration 029)
- Without DB: in-memory only (for tests and local dev)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

logger = logging.getLogger(__name__)


@dataclass
class AgentSession:
    """Represents a single agent run with checkpoint support."""

    id: str
    agent_type: str
    goal: str = ""
    status: str = "running"
    current_step: int = 0
    total_steps: Optional[int] = None
    checkpoint_data: dict = field(default_factory=dict)
    started_at: Optional[datetime] = None
    last_checkpoint: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None


class SessionStore:
    """Durable session persistence for agent runs."""

    def __init__(self, db=None):
        self.db = db
        self._sessions: dict[str, AgentSession] = {}  # in-memory fallback

    def start(self, agent_type: str, goal: str = "", total_steps: Optional[int] = None) -> AgentSession:
        """Start a new agent session."""
        session = AgentSession(
            id=str(uuid4()),
            agent_type=agent_type,
            goal=goal,
            total_steps=total_steps,
            started_at=datetime.now(timezone.utc),
        )
        if self.db:
            try:
                self.db.execute(
                    """INSERT INTO agent_sessions (id, agent_type, goal, status, total_steps, started_at)
                       VALUES (%s, %s, %s, %s, %s, %s)""",
                    [session.id, agent_type, goal, "running", total_steps, session.started_at],
                )
            except Exception as e:
                logger.warning("Failed to persist session start: %s", e)
        self._sessions[session.id] = session
        return session

    def checkpoint(self, session_id: str, step: int, data: Optional[dict] = None) -> None:
        """Record a checkpoint -- can resume from here after crash."""
        now = datetime.now(timezone.utc)
        session = self._sessions.get(session_id)
        if session:
            session.current_step = step
            session.last_checkpoint = now
            if data:
                session.checkpoint_data.update(data)
        if self.db:
            try:
                self.db.execute(
                    """UPDATE agent_sessions
                       SET current_step = %s, last_checkpoint = %s,
                           checkpoint_data = COALESCE(checkpoint_data, '{}'::jsonb) || %s
                       WHERE id = %s""",
                    [step, now, json.dumps(data or {}), session_id],
                )
            except Exception as e:
                logger.warning("Failed to persist checkpoint: %s", e)

    def complete(self, session_id: str) -> None:
        """Mark session as completed."""
        now = datetime.now(timezone.utc)
        session = self._sessions.get(session_id)
        if session:
            session.status = "completed"
            session.completed_at = now
        if self.db:
            try:
                self.db.execute(
                    "UPDATE agent_sessions SET status = 'completed', completed_at = %s WHERE id = %s",
                    [now, session_id],
                )
            except Exception as e:
                logger.warning("Failed to persist completion: %s", e)

    def fail(self, session_id: str, error: str) -> None:
        """Mark session as failed."""
        now = datetime.now(timezone.utc)
        session = self._sessions.get(session_id)
        if session:
            session.status = "failed"
            session.error_message = error
            session.completed_at = now
        if self.db:
            try:
                self.db.execute(
                    "UPDATE agent_sessions SET status = 'failed', error_message = %s, completed_at = %s WHERE id = %s",
                    [error[:500], now, session_id],
                )
            except Exception as e:
                logger.warning("Failed to persist failure: %s", e)

    def get(self, session_id: str) -> Optional[AgentSession]:
        """Get session by ID."""
        if session_id in self._sessions:
            return self._sessions[session_id]
        if self.db:
            try:
                row = self.db.fetch_one("SELECT * FROM agent_sessions WHERE id = %s", [session_id])
                if row:
                    return AgentSession(
                        id=str(row["id"]),
                        agent_type=row["agent_type"],
                        goal=row.get("goal", ""),
                        status=row["status"],
                        current_step=row.get("current_step", 0),
                        total_steps=row.get("total_steps"),
                        checkpoint_data=row.get("checkpoint_data") or {},
                        started_at=row.get("started_at"),
                        last_checkpoint=row.get("last_checkpoint"),
                        completed_at=row.get("completed_at"),
                        error_message=row.get("error_message"),
                    )
            except Exception:
                pass
        return None

    def get_recent(self, agent_type: Optional[str] = None, limit: int = 10) -> list[AgentSession]:
        """Get recent sessions, optionally filtered by agent_type."""
        if self.db:
            try:
                if agent_type:
                    rows = self.db.fetch_all(
                        "SELECT * FROM agent_sessions WHERE agent_type = %s ORDER BY started_at DESC LIMIT %s",
                        [agent_type, limit],
                    )
                else:
                    rows = self.db.fetch_all(
                        "SELECT * FROM agent_sessions ORDER BY started_at DESC LIMIT %s",
                        [limit],
                    )
                return [AgentSession(
                    id=str(r["id"]), agent_type=r["agent_type"],
                    goal=r.get("goal", ""),
                    status=r["status"], current_step=r.get("current_step", 0),
                    total_steps=r.get("total_steps"),
                    started_at=r.get("started_at"), completed_at=r.get("completed_at"),
                ) for r in rows]
            except Exception:
                pass
        # In-memory fallback
        sessions = list(self._sessions.values())
        if agent_type:
            sessions = [s for s in sessions if s.agent_type == agent_type]
        return sessions[-limit:]
