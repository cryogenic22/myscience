"""Reaper for orphaned RUNNING etl_runs (connector sync verification).

A killed process (Railway restart / proxy drop) leaves an etl_runs row stuck
in RUNNING forever, because the pipeline only sets a terminal status inside its
own try/except. Live prod had 48 such orphans across 8 sources, making healthy
connectors look perpetually stuck in the scorecard. reap_stuck_runs() marks
them FAILED. These tests pin: it targets only old RUNNING rows, is idempotent,
and returns the reaped count — without a live DB (fake db captures SQL).
"""

from __future__ import annotations

from scheduler.runner import DataPipelineScheduler


class _FakeDB:
    """Captures fetch_all calls and replays a queued result."""

    def __init__(self, returning):
        self._returning = returning
        self.queries: list[tuple[str, list]] = []

    def fetch_all(self, query, params=None):
        self.queries.append((query, params or []))
        return self._returning


def test_reap_returns_count_and_commits_terminal_status():
    sched = DataPipelineScheduler.__new__(DataPipelineScheduler)  # no APScheduler
    db = _FakeDB(returning=[{"id": "a"}, {"id": "b"}, {"id": "c"}])
    n = sched.reap_stuck_runs(db, hours=12)
    assert n == 3
    sql, params = db.queries[0]
    # only RUNNING rows, only past the threshold, set to a terminal status
    assert "status = 'RUNNING'" in sql
    assert "started_at <" in sql
    assert "FAILED" in sql
    assert 12 in params


def test_reap_is_idempotent_noop_when_none_stuck():
    sched = DataPipelineScheduler.__new__(DataPipelineScheduler)
    db = _FakeDB(returning=[])
    assert sched.reap_stuck_runs(db, hours=12) == 0


def test_reap_uses_default_threshold_when_unspecified():
    sched = DataPipelineScheduler.__new__(DataPipelineScheduler)
    db = _FakeDB(returning=[])
    sched.reap_stuck_runs(db)
    _, params = db.queries[0]
    assert DataPipelineScheduler.STUCK_RUNNING_HOURS in params


def test_reap_swallows_db_errors_safely():
    class _BoomDB:
        def fetch_all(self, *a, **k):
            raise RuntimeError("connection dropped")

    sched = DataPipelineScheduler.__new__(DataPipelineScheduler)
    assert sched.reap_stuck_runs(_BoomDB(), hours=12) == 0
