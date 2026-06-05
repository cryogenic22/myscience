"""C4/C5 — scheduler wiring for the dormant learning loops.

Verifies the post-ingestion tasks run LearningService (C4) and
ConceptWeightAdjuster (C5), format their results, and always close the
own connection. Pure unit tests (services are monkeypatched).
"""

from __future__ import annotations


class _DB:
    def __init__(self, closed):
        self._closed = closed

    def connect(self):
        pass

    def close(self):
        self._closed["v"] = True


# ── C4: learning service ──

def test_run_learning_service_runs_and_closes(monkeypatch):
    from scheduler import runner as r
    closed = {"v": False}
    monkeypatch.setattr(r, "Database", lambda dsn: _DB(closed))

    import services.learning_service as ls

    class _Result:
        run_id = "run-1"; status = "complete"
        decisions_processed = 4; sources_updated = 2; prompts_flagged = 1

    class _Svc:
        def __init__(self, *a, **k): pass
        def run(self, db, *, started_by_user_id=None): return _Result()

    monkeypatch.setattr(ls, "LearningService", _Svc)

    sched = r.DataPipelineScheduler.__new__(r.DataPipelineScheduler)
    out = sched._run_learning_service()
    assert "status=complete" in out
    assert "4 decisions" in out
    assert closed["v"] is True


def test_run_learning_service_closes_on_error(monkeypatch):
    from scheduler import runner as r
    closed = {"v": False}
    monkeypatch.setattr(r, "Database", lambda dsn: _DB(closed))

    import services.learning_service as ls

    class _Svc:
        def __init__(self, *a, **k): pass
        def run(self, db, **k): raise RuntimeError("boom")

    monkeypatch.setattr(ls, "LearningService", _Svc)

    sched = r.DataPipelineScheduler.__new__(r.DataPipelineScheduler)
    try:
        sched._run_learning_service()
    except RuntimeError:
        pass
    assert closed["v"] is True  # connection released even on failure


# ── C5: concept-weight adjuster ──

def test_run_concept_weight_adjuster_runs_and_closes(monkeypatch):
    from scheduler import runner as r
    closed = {"v": False}
    monkeypatch.setattr(r, "Database", lambda dsn: _DB(closed))

    import services.concept_registry as cr
    import services.concept_weight_adjuster as cwa

    class _Registry:
        def __init__(self, *a, **k): pass

    class _Report:
        analyzed_queries = 42; concepts_adjusted = 3

    class _Adj:
        def __init__(self, *a, **k): pass
        def analyze_and_adjust(self, lookback_days=7): return _Report()

    monkeypatch.setattr(cr, "ConceptRegistry", _Registry)
    monkeypatch.setattr(cwa, "ConceptWeightAdjuster", _Adj)

    sched = r.DataPipelineScheduler.__new__(r.DataPipelineScheduler)
    out = sched._run_concept_weight_adjuster()
    assert "analyzed 42 queries" in out
    assert "3 concepts adjusted" in out
    assert closed["v"] is True
