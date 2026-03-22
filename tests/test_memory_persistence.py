"""Tests for ConversationMemory persistence to PostgreSQL.

Verifies that get_conversation_memory() restores from DB and
save_conversation_memory() writes snapshots via db.execute().

Run with: pytest tests/test_memory_persistence.py -v
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch, call

import pytest

from services.conversation_memory import ConversationMemory


# ── Helpers ──


def _make_mock_db(stored_snapshot=None):
    """Create a mock Database that optionally returns a stored snapshot."""
    db = MagicMock()
    if stored_snapshot is not None:
        db.fetch_one.return_value = {"snapshot": stored_snapshot}
    else:
        db.fetch_one.return_value = None
    return db


def _build_memory_with_exchanges() -> ConversationMemory:
    """Create a ConversationMemory with two exchanges for testing."""
    mem = ConversationMemory(token_budget=4000)
    mem.add_exchange(
        question="Tell me about semaglutide",
        response="Semaglutide is a GLP-1 agonist.",
        entities=["semaglutide"],
    )
    mem.add_exchange(
        question="Who makes it?",
        response="Novo Nordisk manufactures it.",
        entities=["Novo Nordisk"],
    )
    return mem


# ── 1. TestSaveConversationMemory ──


class TestSaveConversationMemory:
    """save_conversation_memory() writes snapshots to the DB."""

    def test_save_calls_execute(self):
        """save_conversation_memory issues an INSERT...ON CONFLICT query."""
        from api.deps import save_conversation_memory

        db = _make_mock_db()
        mem = _build_memory_with_exchanges()

        save_conversation_memory("sess-1", mem, db)

        db.execute.assert_called_once()
        args = db.execute.call_args
        sql = args[0][0]
        params = args[0][1]
        assert "INSERT INTO conversation_snapshots" in sql
        assert "ON CONFLICT" in sql
        assert params[0] == "sess-1"

    def test_save_snapshot_is_valid_json(self):
        """The snapshot parameter passed to execute is valid JSON."""
        from api.deps import save_conversation_memory

        db = _make_mock_db()
        mem = _build_memory_with_exchanges()

        save_conversation_memory("sess-2", mem, db)

        params = db.execute.call_args[0][1]
        snapshot_str = params[1]
        parsed = json.loads(snapshot_str)
        # snapshot() returns a JSON string; save wraps it in json.dumps
        inner = json.loads(parsed) if isinstance(parsed, str) else parsed
        assert "exchanges" in inner
        assert "entity_counts" in inner

    def test_save_does_not_raise_on_db_error(self):
        """DB failures are logged, not raised."""
        from api.deps import save_conversation_memory

        db = _make_mock_db()
        db.execute.side_effect = Exception("connection lost")
        mem = _build_memory_with_exchanges()

        # Should not raise
        save_conversation_memory("sess-3", mem, db)

    def test_save_with_empty_memory(self):
        """Saving a fresh (empty) memory works without error."""
        from api.deps import save_conversation_memory

        db = _make_mock_db()
        mem = ConversationMemory(token_budget=4000)

        save_conversation_memory("sess-empty", mem, db)

        db.execute.assert_called_once()


# ── 2. TestGetConversationMemoryRestore ──


class TestGetConversationMemoryRestore:
    """get_conversation_memory() restores state from DB on first access."""

    def test_restore_from_db_snapshot(self):
        """When DB has a snapshot, entities are restored."""
        from api import deps

        # Build a snapshot to store
        mem = _build_memory_with_exchanges()
        snapshot_dict = json.loads(mem.snapshot())

        mock_db = _make_mock_db(stored_snapshot=snapshot_dict)

        # Clear the in-memory cache
        original_store = deps._memory_store.copy()
        deps._memory_store.clear()

        try:
            with patch.object(deps, "get_db", return_value=mock_db):
                restored = deps.get_conversation_memory("test-restore")

            entities = restored.get_entities_discussed()
            assert "semaglutide" in entities
            assert "Novo Nordisk" in entities
        finally:
            deps._memory_store.clear()
            deps._memory_store.update(original_store)

    def test_restore_with_json_string_snapshot(self):
        """When DB returns snapshot as a JSON string (not dict), it still restores."""
        from api import deps

        mem = _build_memory_with_exchanges()
        snapshot_str = mem.snapshot()  # This is already a JSON string

        mock_db = _make_mock_db(stored_snapshot=snapshot_str)

        original_store = deps._memory_store.copy()
        deps._memory_store.clear()

        try:
            with patch.object(deps, "get_db", return_value=mock_db):
                restored = deps.get_conversation_memory("test-str-restore")

            entities = restored.get_entities_discussed()
            assert "semaglutide" in entities
        finally:
            deps._memory_store.clear()
            deps._memory_store.update(original_store)

    def test_fresh_memory_when_no_db_row(self):
        """When DB has no row for this session, a fresh memory is returned."""
        from api import deps

        mock_db = _make_mock_db(stored_snapshot=None)

        original_store = deps._memory_store.copy()
        deps._memory_store.clear()

        try:
            with patch.object(deps, "get_db", return_value=mock_db):
                mem = deps.get_conversation_memory("test-fresh")

            assert mem.get_context() == ""
            assert mem.get_entities_discussed() == []
        finally:
            deps._memory_store.clear()
            deps._memory_store.update(original_store)

    def test_fresh_memory_when_db_errors(self):
        """When DB raises, a fresh memory is returned (no crash)."""
        from api import deps

        mock_db = MagicMock()
        mock_db.fetch_one.side_effect = Exception("no such table")

        original_store = deps._memory_store.copy()
        deps._memory_store.clear()

        try:
            with patch.object(deps, "get_db", return_value=mock_db):
                mem = deps.get_conversation_memory("test-err")

            assert mem is not None
            assert mem.get_context() == ""
        finally:
            deps._memory_store.clear()
            deps._memory_store.update(original_store)

    def test_cached_on_second_access(self):
        """Second call returns the cached instance, not a new DB lookup."""
        from api import deps

        mock_db = _make_mock_db(stored_snapshot=None)

        original_store = deps._memory_store.copy()
        deps._memory_store.clear()

        try:
            with patch.object(deps, "get_db", return_value=mock_db):
                mem1 = deps.get_conversation_memory("test-cache")
                mem2 = deps.get_conversation_memory("test-cache")

            assert mem1 is mem2
            # fetch_one should only be called once (first access)
            assert mock_db.fetch_one.call_count == 1
        finally:
            deps._memory_store.clear()
            deps._memory_store.update(original_store)


# ── 3. TestRoundTrip ──


class TestRoundTrip:
    """Full save + restore cycle through the persistence functions."""

    def test_save_then_restore_preserves_state(self):
        """Snapshot saved via save_conversation_memory can be restored via get_conversation_memory."""
        from api import deps
        from api.deps import save_conversation_memory

        mem = _build_memory_with_exchanges()

        # Capture what save_conversation_memory would write
        captured_params = {}
        mock_db = MagicMock()

        def capture_execute(sql, params):
            captured_params["sql"] = sql
            captured_params["params"] = params

        mock_db.execute.side_effect = capture_execute

        save_conversation_memory("rt-session", mem, mock_db)

        # Now simulate restoring: make fetch_one return the saved snapshot
        saved_snapshot = json.loads(captured_params["params"][1])
        # saved_snapshot is a JSON string of the snapshot dict
        inner = json.loads(saved_snapshot) if isinstance(saved_snapshot, str) else saved_snapshot

        mock_db2 = _make_mock_db(stored_snapshot=inner)

        original_store = deps._memory_store.copy()
        deps._memory_store.clear()

        try:
            with patch.object(deps, "get_db", return_value=mock_db2):
                restored = deps.get_conversation_memory("rt-session")

            # Verify restored state matches original
            assert set(restored.get_entities_discussed()) == set(mem.get_entities_discussed())
            assert restored.get_context() == mem.get_context()
        finally:
            deps._memory_store.clear()
            deps._memory_store.update(original_store)
