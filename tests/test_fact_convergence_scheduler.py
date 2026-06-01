"""PB-H17 — scheduler fact convergence (market_events → facts) wiring.

The new post-ingestion task reuses the proven, idempotent
backfill_facts_from_events. This verifies the wiring: it's called with the
bounded since_days, the result is formatted, and the connection is always
closed (the long-sweep-on-shared-connection footgun the method guards against).
"""
from __future__ import annotations

from services.fact_ingest import BackfillStats


def test_run_fact_convergence_calls_backfill_and_closes_conn(monkeypatch):
    from scheduler import runner as r

    closed = {"v": False}

    class _DB:
        def connect(self):
            pass

        def close(self):
            closed["v"] = True

    monkeypatch.setattr(r, "Database", lambda dsn: _DB())

    captured: dict = {}
    import services.fact_ingest as fi

    def _fake_backfill(db, *, since_days=None, **kw):
        captured["since_days"] = since_days
        return BackfillStats(scanned=10, asserted=4, skipped_existing=6, skipped_no_subject=0)

    monkeypatch.setattr(fi, "backfill_facts_from_events", _fake_backfill)

    # __new__ skips __init__ (which would build a real scheduler) — we only
    # exercise the convergence method.
    sched = r.DataPipelineScheduler.__new__(r.DataPipelineScheduler)
    out = sched._run_fact_convergence(since_days=7)

    assert captured["since_days"] == 7        # bounded sweep, not full scan
    assert "4 asserted" in out
    assert "6 existing" in out
    assert closed["v"] is True                # connection always released


def test_run_fact_convergence_closes_conn_on_error(monkeypatch):
    from scheduler import runner as r

    closed = {"v": False}

    class _DB:
        def connect(self):
            pass

        def close(self):
            closed["v"] = True

    monkeypatch.setattr(r, "Database", lambda dsn: _DB())

    import services.fact_ingest as fi

    def _boom(db, **kw):
        raise RuntimeError("ledger down")

    monkeypatch.setattr(fi, "backfill_facts_from_events", _boom)

    sched = r.DataPipelineScheduler.__new__(r.DataPipelineScheduler)
    try:
        sched._run_fact_convergence()
    except RuntimeError:
        pass
    assert closed["v"] is True                # finally: closed even on error
