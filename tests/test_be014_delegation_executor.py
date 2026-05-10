"""BE-14 — delegation executor tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest


# ════════════════════════════════════════════════════════════════════
# Migration shape
# ════════════════════════════════════════════════════════════════════

class TestMigration073:
    def test_creates_delegated_runs(self):
        path = Path(__file__).parent.parent / "schema" / "migrations" / "073_delegated_runs.sql"
        sql = path.read_text(encoding="utf-8").lower()
        assert "create table" in sql and "delegated_runs" in sql
        for col in ("run_id", "requested_by", "scenario_kind",
                    "parameters", "wake_at", "status", "result"):
            assert col in sql, f"missing column {col}"
        assert "skip locked" not in sql, (
            "FOR UPDATE SKIP LOCKED lives in the executor SQL, "
            "not the table definition"
        )


# ════════════════════════════════════════════════════════════════════
# Service
# ════════════════════════════════════════════════════════════════════

class TestQueue:
    def test_inserts_and_returns_row(self):
        from services.agent.delegation_executor import queue

        db = MagicMock()
        wake = datetime.now(timezone.utc) + timedelta(hours=8)
        db.fetch_one.return_value = {
            "run_id": "r-1", "requested_by": "u-1",
            "war_room_id": None, "scenario_kind": "morning_pulse",
            "parameters": {}, "wake_at": wake,
            "status": "queued", "created_at": datetime.now(timezone.utc),
        }
        out = queue(
            db,
            requested_by="u-1", scenario_kind="morning_pulse",
            parameters={"horizon": "24h"},
            wake_at=wake,
        )
        assert out["run_id"] == "r-1"


class TestExecuteDue:
    @pytest.fixture(autouse=True)
    def _reset_handlers(self):
        from services.agent import delegation_executor as mod
        mod._HANDLERS.clear()
        yield
        mod._HANDLERS.clear()

    def test_runs_handler_and_completes(self):
        from services.agent.delegation_executor import register_handler, execute_due

        seen = {}

        def my_handler(db, params):
            seen.update(params)
            return {"verdict": "hold", "delta_pct": 1.4}

        register_handler("morning_pulse", my_handler)

        db = MagicMock()
        # _claim_one returns a row; second call returns None to stop.
        db.fetch_one.side_effect = [
            {"run_id": "r-1", "requested_by": "u",
             "war_room_id": None, "scenario_kind": "morning_pulse",
             "parameters": {"k": "v"}},
            None,
        ]
        out = execute_due(db, max_runs=5)
        assert out == {"completed": 1, "failed": 0, "skipped": 0}
        assert seen == {"k": "v"}

    def test_unknown_kind_marks_failed_skipped(self):
        from services.agent.delegation_executor import execute_due

        db = MagicMock()
        db.fetch_one.side_effect = [
            {"run_id": "r-2", "requested_by": "u",
             "war_room_id": None, "scenario_kind": "something_else",
             "parameters": {}},
            None,
        ]
        out = execute_due(db)
        assert out == {"completed": 0, "failed": 0, "skipped": 1}

    def test_handler_exception_marks_failed(self):
        from services.agent.delegation_executor import register_handler, execute_due

        def boom(db, params):
            raise RuntimeError("kaboom")

        register_handler("explody", boom)

        db = MagicMock()
        db.fetch_one.side_effect = [
            {"run_id": "r-3", "requested_by": "u",
             "war_room_id": None, "scenario_kind": "explody",
             "parameters": {}},
            None,
        ]
        out = execute_due(db)
        assert out == {"completed": 0, "failed": 1, "skipped": 0}

    def test_claim_uses_skip_locked(self):
        """The claim SQL must use FOR UPDATE SKIP LOCKED so concurrent
        workers don't fight over rows."""
        from services.agent.delegation_executor import _claim_one
        db = MagicMock()
        db.fetch_one.return_value = None
        _claim_one(db)
        sql = str(db.fetch_one.call_args.args[0]).lower()
        assert "for update skip locked" in sql

    def test_no_due_returns_zeros(self):
        from services.agent.delegation_executor import execute_due
        db = MagicMock()
        db.fetch_one.return_value = None
        out = execute_due(db)
        assert out == {"completed": 0, "failed": 0, "skipped": 0}


class TestListForUser:
    def test_returns_iso_timestamps(self):
        from services.agent.delegation_executor import list_for_user

        db = MagicMock()
        db.fetch_all.return_value = [
            {
                "run_id": "r-1", "war_room_id": None,
                "scenario_kind": "morning_pulse",
                "status": "complete",
                "wake_at": datetime.now(timezone.utc),
                "created_at": datetime.now(timezone.utc),
                "started_at": datetime.now(timezone.utc),
                "completed_at": datetime.now(timezone.utc),
                "error_message": None,
            }
        ]
        rows = list_for_user(db, user_id="u-1")
        assert len(rows) == 1
        assert isinstance(rows[0]["wake_at"], str)
        assert "T" in rows[0]["wake_at"]  # ISO 8601
