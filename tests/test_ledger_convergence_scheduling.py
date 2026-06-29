"""Ledger-convergence scheduling — the events/entities → FACTS conversion must run
on a cadence, not only on-demand.

27-Jun prod probe: the facts + evidence ledgers froze for 12 days (0 new rows)
while every ingest connector stayed fresh — because ``fact_convergence`` +
``fact_emitters`` were reachable only through ``run_now()``'s post-task block,
which the live app never calls (it drives ``_register_jobs``, not ``run_now``).
This is the identical defect class the 15-Jun fix closed for sensing promotion.

These deterministic, DB-free tests (Lane 1) pin two things so the freeze cannot
silently recur:
  1. the converters run as one scheduled job registered in ``_register_jobs``;
  2. the ledger-freshness SLA exists and the verdict logic reads a 12-day-old
     ledger as unhealthy (the deterministic half of the gate that would have
     caught the freeze). Wiring this SLA into the LIVE Lane-2 script
     (connector_health) is a follow-up — see LEDGER_FRESHNESS_SLA_DAYS's note."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch


def _scheduler():
    from scheduler.runner import DataPipelineScheduler
    return DataPipelineScheduler()


class TestRunLedgerConvergence:
    def test_runs_convergence_and_emitters(self):
        sched = _scheduler()
        with patch.object(type(sched), "_run_fact_convergence",
                          return_value="OK: 9 asserted, 1 existing, 0 no-subject") as c, \
             patch.object(type(sched), "_run_fact_emitters",
                          return_value="OK: clinical_trials=4a/2e") as e, \
             patch.object(type(sched), "_run_evidence_backfill",
                          return_value="OK: 9 linked, 0 sourceless, 0 failed") as ev:
            out = sched._run_ledger_convergence()
        assert c.called, "_run_fact_convergence not called"
        assert e.called, "_run_fact_emitters not called"
        # CONSERVATION: event-facts assert with source_doc_id NULL — the evidence
        # backfill that links them MUST run in the same job or the ≥0.98 evidence
        # floor degrades every cycle (proven on prod 99.99%→97.04%).
        assert ev.called, "_run_evidence_backfill not called — facts would lack provenance"
        assert "9 asserted" in out["fact_convergence"]
        assert out["fact_emitters"].startswith("OK")
        assert "linked" in out["evidence_backfill"]

    def test_evidence_backfill_runs_even_if_emission_fails(self):
        # both emission steps failing must NOT skip the evidence link — any
        # previously-NULL facts still get grounded (conservation: no silent abort).
        sched = _scheduler()
        with patch.object(type(sched), "_run_fact_convergence",
                          side_effect=RuntimeError("boom")), \
             patch.object(type(sched), "_run_fact_emitters",
                          side_effect=RuntimeError("boom2")), \
             patch.object(type(sched), "_run_evidence_backfill",
                          return_value="OK: 3 linked, 0 sourceless, 0 failed") as ev:
            out = sched._run_ledger_convergence()
        assert out["fact_convergence"].startswith("ERROR")
        assert out["fact_emitters"].startswith("ERROR")
        assert ev.called, "evidence backfill must still run after emission failures"
        assert out["evidence_backfill"].startswith("OK")

    def test_writes_into_shared_results_dict(self):
        # run_now threads its own results dict through; keys must land there
        # (and existing keys preserved) so run_now output is unchanged.
        sched = _scheduler()
        results = {"existing": "keep"}
        with patch.object(type(sched), "_run_fact_convergence",
                          return_value="OK: 0 asserted, 0 existing, 0 no-subject"), \
             patch.object(type(sched), "_run_fact_emitters", return_value="OK: none"), \
             patch.object(type(sched), "_run_evidence_backfill", return_value="OK: 0 linked"):
            sched._run_ledger_convergence(results)
        assert results["existing"] == "keep"
        assert all(k in results for k in ("fact_convergence", "fact_emitters", "evidence_backfill"))


class TestRegisterJobs:
    def test_ledger_convergence_job_is_registered(self):
        sched = _scheduler()
        sched._register_jobs()
        ids = {j.id for j in sched._scheduler.get_jobs()}
        assert "ledger_convergence" in ids, \
            f"ledger_convergence not registered; got {sorted(ids)}"

    def test_sensing_promotion_still_registered(self):
        # regression: adding ledger convergence must not drop the sensing job
        sched = _scheduler()
        sched._register_jobs()
        ids = {j.id for j in sched._scheduler.get_jobs()}
        assert "sensing_promotion" in ids


class TestLedgerFreshnessGate:
    """The Lane-2 invariant that makes a frozen ledger fail closed. Reuses the
    existing pure ``evaluate_source_health`` verdict so a stale ledger reads
    unhealthy exactly the way a stale source does."""

    def test_facts_and_evidence_have_an_sla(self):
        from scheduler.config import LEDGER_FRESHNESS_SLA_DAYS
        tables = {v[0] for v in LEDGER_FRESHNESS_SLA_DAYS.values()}
        assert "facts" in tables, "facts ledger has no freshness SLA"
        assert "evidence_records" in tables, "evidence ledger has no freshness SLA"

    def test_stale_ledger_is_unhealthy(self):
        # a 12-day-old facts ledger (the 27-Jun freeze) must read unhealthy
        from scheduler.config import LEDGER_FRESHNESS_SLA_DAYS
        from scripts.connector_health import evaluate_source_health
        sla = LEDGER_FRESHNESS_SLA_DAYS["facts_ledger"][2]
        now = datetime(2026, 6, 27, tzinfo=timezone.utc)
        stale = now - timedelta(days=12)
        h = evaluate_source_health("facts_ledger", "facts", sla, 15051, stale,
                                   None, None, None, now=now)
        assert not h.healthy and h.over_sla

    def test_fresh_ledger_is_healthy(self):
        from scripts.connector_health import evaluate_source_health
        now = datetime(2026, 6, 27, tzinfo=timezone.utc)
        fresh = now - timedelta(hours=6)
        h = evaluate_source_health("facts_ledger", "facts", 3, 15051, fresh,
                                   None, None, None, now=now)
        assert h.healthy and not h.over_sla

    def test_empty_ledger_is_unhealthy(self):
        from scripts.connector_health import evaluate_source_health
        now = datetime(2026, 6, 27, tzinfo=timezone.utc)
        h = evaluate_source_health("facts_ledger", "facts", 3, 0, None,
                                   None, None, None, now=now)
        assert not h.healthy
