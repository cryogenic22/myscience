"""Tests for SessionStore — durable session persistence for agent runs.

TDD: These tests are written BEFORE the implementation.
Run with: pytest tests/test_session_store.py -v
"""

from __future__ import annotations

import pytest

from services.agent.session_store import AgentSession, SessionStore


# ── 1. TestAgentSession ──


class TestAgentSession:
    """AgentSession dataclass defaults and custom values."""

    def test_default_values(self):
        """AgentSession has sensible defaults for status, step, checkpoint_data."""
        session = AgentSession(id="abc-123", agent_type="steward")
        assert session.id == "abc-123"
        assert session.agent_type == "steward"
        assert session.goal == ""
        assert session.status == "running"
        assert session.current_step == 0
        assert session.total_steps is None
        assert session.checkpoint_data == {}
        assert session.started_at is None
        assert session.last_checkpoint is None
        assert session.completed_at is None
        assert session.error_message is None

    def test_custom_values(self):
        """AgentSession accepts all custom values."""
        session = AgentSession(
            id="xyz-789",
            agent_type="research",
            goal="Fill knowledge gaps for semaglutide",
            status="completed",
            current_step=5,
            total_steps=10,
            checkpoint_data={"last_entity": "semaglutide"},
        )
        assert session.agent_type == "research"
        assert session.goal == "Fill knowledge gaps for semaglutide"
        assert session.status == "completed"
        assert session.current_step == 5
        assert session.total_steps == 10
        assert session.checkpoint_data == {"last_entity": "semaglutide"}


# ── 2. TestSessionStore ──


class TestSessionStore:
    """SessionStore lifecycle: start, checkpoint, complete, fail, get."""

    def test_start_creates_session(self):
        """start() returns a session with running status and a UUID id."""
        store = SessionStore()
        session = store.start("steward", goal="Curate drug data")
        assert session.status == "running"
        assert session.agent_type == "steward"
        assert session.goal == "Curate drug data"
        assert session.started_at is not None
        assert len(session.id) == 36  # UUID format

    def test_checkpoint_updates_step(self):
        """checkpoint() advances current_step and sets last_checkpoint."""
        store = SessionStore()
        session = store.start("steward")
        store.checkpoint(session.id, step=3, data={"processed": 42})
        updated = store.get(session.id)
        assert updated.current_step == 3
        assert updated.last_checkpoint is not None
        assert updated.checkpoint_data["processed"] == 42

    def test_complete_sets_status(self):
        """complete() changes status to completed and sets completed_at."""
        store = SessionStore()
        session = store.start("research")
        store.complete(session.id)
        updated = store.get(session.id)
        assert updated.status == "completed"
        assert updated.completed_at is not None

    def test_fail_sets_error(self):
        """fail() sets status to failed and records error_message."""
        store = SessionStore()
        session = store.start("steward")
        store.fail(session.id, "Connection refused")
        updated = store.get(session.id)
        assert updated.status == "failed"
        assert updated.error_message == "Connection refused"
        assert updated.completed_at is not None

    def test_get_returns_session(self):
        """get() after start returns the same session."""
        store = SessionStore()
        session = store.start("research", goal="Test goal")
        fetched = store.get(session.id)
        assert fetched is not None
        assert fetched.id == session.id
        assert fetched.agent_type == "research"
        assert fetched.goal == "Test goal"

    def test_get_returns_none_for_unknown(self):
        """get() with a non-existent ID returns None."""
        store = SessionStore()
        assert store.get("nonexistent-id") is None

    def test_get_recent(self):
        """get_recent() returns sessions ordered by creation time."""
        store = SessionStore()
        s1 = store.start("steward", goal="First")
        s2 = store.start("research", goal="Second")
        s3 = store.start("steward", goal="Third")
        recent = store.get_recent(limit=10)
        assert len(recent) == 3
        # Most recent sessions should be last in the in-memory list
        ids = [s.id for s in recent]
        assert s1.id in ids
        assert s2.id in ids
        assert s3.id in ids

    def test_get_recent_filters_by_agent_type(self):
        """get_recent(agent_type=...) filters to matching sessions only."""
        store = SessionStore()
        store.start("steward", goal="Steward task")
        store.start("research", goal="Research task")
        store.start("steward", goal="Another steward task")
        recent = store.get_recent(agent_type="steward", limit=10)
        assert len(recent) == 2
        assert all(s.agent_type == "steward" for s in recent)

    def test_db_fallback(self):
        """SessionStore works in-memory when db=None (no database dependency)."""
        store = SessionStore(db=None)
        session = store.start("steward")
        store.checkpoint(session.id, step=1)
        store.complete(session.id)
        result = store.get(session.id)
        assert result.status == "completed"
        assert result.current_step == 1

    def test_checkpoint_merges_data(self):
        """Multiple checkpoints merge their data dicts."""
        store = SessionStore()
        session = store.start("research")
        store.checkpoint(session.id, step=1, data={"entities": 10})
        store.checkpoint(session.id, step=2, data={"links": 5})
        updated = store.get(session.id)
        assert updated.current_step == 2
        assert updated.checkpoint_data["entities"] == 10
        assert updated.checkpoint_data["links"] == 5

    def test_start_with_total_steps(self):
        """start() can accept a total_steps parameter for progress tracking."""
        store = SessionStore()
        session = store.start("steward", goal="Batch curation", total_steps=50)
        assert session.total_steps == 50
