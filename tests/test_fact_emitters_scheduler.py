"""DR-8 — scheduler fact-emitter wiring (entity tables → facts ledger).

Verifies the post-ingestion task reuses run_all_emitters with the bounded limit,
formats the result, and always closes its connection.
"""
from __future__ import annotations

from services.fact_emitters.base import EmitStats


def test_run_fact_emitters_calls_run_all_and_closes_conn(monkeypatch):
    from scheduler import runner as r

    closed = {"v": False}

    class _DB:
        def connect(self):
            pass

        def close(self):
            closed["v"] = True

    monkeypatch.setattr(r, "Database", lambda dsn: _DB())

    captured: dict = {}
    import services.fact_emitters.base as fe

    def _fake_run_all(db, *, limit=None, **kw):
        captured["limit"] = limit
        return {
            "clinical_trials": EmitStats(emitter="clinical_trials", asserted=3,
                                         skipped_existing=7),
            "adverse_events": EmitStats(emitter="adverse_events", asserted=1,
                                        skipped_existing=2),
        }

    monkeypatch.setattr(fe, "run_all_emitters", _fake_run_all)

    sched = r.DataPipelineScheduler.__new__(r.DataPipelineScheduler)
    out = sched._run_fact_emitters(limit=200)

    assert captured["limit"] == 200            # bounded, not a full sweep
    assert "clinical_trials=3a/7e" in out
    assert closed["v"] is True                 # connection always released


def test_run_fact_emitters_closes_conn_on_error(monkeypatch):
    from scheduler import runner as r

    closed = {"v": False}

    class _DB:
        def connect(self):
            pass

        def close(self):
            closed["v"] = True

    monkeypatch.setattr(r, "Database", lambda dsn: _DB())

    import services.fact_emitters.base as fe

    def _boom(db, **kw):
        raise RuntimeError("emitters down")

    monkeypatch.setattr(fe, "run_all_emitters", _boom)

    sched = r.DataPipelineScheduler.__new__(r.DataPipelineScheduler)
    try:
        sched._run_fact_emitters()
    except RuntimeError:
        pass
    assert closed["v"] is True
