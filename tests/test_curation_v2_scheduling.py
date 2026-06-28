"""auto_curate_v2 scheduling + the ``self.db`` crash fix.

auto_curate_v2's five deterministic curation passes (SEC EDGAR enrichment,
orphan-company linking, resolution sweep, HITL auto-resolve, FAIR score) never
ran automatically on prod:

  * the scheduler post-task (``run_now`` step 6b) called
    ``run_all_curation(self.db)``, but ``DataPipelineScheduler`` never sets
    ``self.db`` → ``AttributeError`` every cycle, so v2 silently no-op'd
    everywhere ``run_now`` is reached (CLI, /catalog, /steward);
  * it was registered on no cron, so even once fixed it would only run on a
    manual ``/enrichment`` POST.

Same defect class as the 15-Jun sensing freeze and the 27-Jun ledger freeze: a
built converter reachable only on-demand. These DB-free Lane-1 tests pin the fix
(own short-lived connection) and the schedule (a registered cron job) so neither
can silently regress."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def _scheduler():
    from scheduler.runner import DataPipelineScheduler
    return DataPipelineScheduler()


class TestSelfDbRootCause:
    def test_scheduler_has_no_db_attribute(self):
        # The bug: step 6b passed ``self.db``; the scheduler never sets it. Pin
        # the absence so the fix stays "own short-lived connection" and nobody
        # re-introduces a stashed ``self.db`` that would go stale across the
        # daemon's whole lifetime (every other post-task opens its own conn).
        sched = _scheduler()
        assert not hasattr(sched, "db")


class TestRunAutoCurateV2:
    def test_opens_and_closes_its_own_connection(self):
        sched = _scheduler()
        fake_db = MagicMock()
        with patch("scheduler.runner.Database", return_value=fake_db) as DB, \
             patch("scripts.auto_curate_v2.run_all_curation",
                   return_value=[{"enriched": 3}, {"linked": 2}]) as rac:
            out = sched._run_auto_curate_v2()
        DB.assert_called_once()               # own connection, NOT self.db
        fake_db.connect.assert_called_once()
        fake_db.close.assert_called_once()    # and released
        rac.assert_called_once_with(fake_db)  # passed the real conn, not self.db
        assert out.startswith("OK")

    def test_totals_items_across_passes(self):
        # mirrors the prior inline accounting: enriched|resolved|linked per pass.
        sched = _scheduler()
        with patch("scheduler.runner.Database", return_value=MagicMock()), \
             patch("scripts.auto_curate_v2.run_all_curation",
                   return_value=[{"enriched": 5}, {"linked": 2}, {"resolved": 4},
                                 {}, {"overall": 0.9}]):
            out = sched._run_auto_curate_v2()
        assert "11 items" in out  # 5 + 2 + 4 + 0(no key) + 0(fair has no count)

    def test_summary_flags_partial_when_a_pass_errored(self):
        # run_all_curation isolates a failing pass into an {"error": ...} result
        # rather than raising; the scheduler summary must then read PARTIAL with a
        # failed-count, not a clean "OK" (conservation #3: job-ran ≠ healthy).
        sched = _scheduler()
        with patch("scheduler.runner.Database", return_value=MagicMock()), \
             patch("scripts.auto_curate_v2.run_all_curation",
                   return_value=[{"enriched": 4},
                                 {"pass": "resolution_sweep", "error": "boom"},
                                 {"resolved": 2}]):
            out = sched._run_auto_curate_v2()
        assert out.startswith("PARTIAL"), out
        assert "1/3 passes failed" in out
        assert "6 items" in out  # 4 + 0(errored) + 2

    def test_connection_released_even_when_a_pass_raises(self):
        # conservation: a failing pass must still release the DB connection
        # (no leaked handle that would exhaust the Railway pool over time).
        sched = _scheduler()
        fake_db = MagicMock()
        with patch("scheduler.runner.Database", return_value=fake_db), \
             patch("scripts.auto_curate_v2.run_all_curation",
                   side_effect=RuntimeError("boom")):
            try:
                sched._run_auto_curate_v2()
            except RuntimeError:
                pass
        fake_db.close.assert_called_once()


class TestRegisterJobs:
    def test_auto_curate_v2_job_is_registered(self):
        sched = _scheduler()
        sched._register_jobs()
        ids = {j.id for j in sched._scheduler.get_jobs()}
        assert "auto_curate_v2" in ids, \
            f"auto_curate_v2 not registered; got {sorted(ids)}"

    def test_existing_jobs_still_registered(self):
        # regression: adding v2 must not drop the sensing or ledger jobs the
        # 15-Jun / 27-Jun fixes added (the same _register_jobs surface).
        sched = _scheduler()
        sched._register_jobs()
        ids = {j.id for j in sched._scheduler.get_jobs()}
        assert {"sensing_promotion", "ledger_convergence"} <= ids, \
            f"lost a scheduled job: {sorted(ids)}"
