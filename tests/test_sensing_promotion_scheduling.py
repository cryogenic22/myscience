"""Sensing-promotion scheduling — the events+facts→signals conversion runs on a
cadence, not only on-demand (15-Jun gap analysis: signals stalled 11d because the
promotion step was reachable only via run_now / upload / CLI). DB-free."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def _scheduler():
    from scheduler.runner import DataPipelineScheduler
    return DataPipelineScheduler()


class TestRunSensingPromotion:
    def test_calls_promote_mint_and_relink(self):
        sched = _scheduler()
        promo = MagicMock(promoted=5, skipped_existing=1, skipped_no_entity=2)
        mint = MagicMock(minted=7, scanned=10)
        with patch("scheduler.runner.Database"), \
             patch("services.signal_promoter.promote_events", return_value=promo) as p, \
             patch("services.fact_signals.mint_signals_from_facts", return_value=mint) as m, \
             patch("services.signal_promoter.relink_market_signals", return_value={"relinked": 3}) as r:
            out = sched._run_sensing_promotion()
        assert p.called, "promote_events not called"
        assert m.called, "mint_signals_from_facts not called"
        assert r.called, "relink_market_signals not called"
        # must filter to high-significance events, not the 96% RECALL_CLASS_I flood
        evt = p.call_args.kwargs.get("event_types") or []
        assert "approval" in evt and "trial_readout" in evt, \
            f"promote_events must pass HIGH_SIGNIFICANCE event_types; got {evt}"
        assert "general" not in evt  # recall/general noise excluded
        assert "5 promoted" in out["signal_promotion"]
        assert "7 minted" in out["fact_signal_mint"]
        assert out["signal_relink"].startswith("OK")

    def test_one_failing_step_does_not_abort_the_others(self):
        # each step is independently try/except'd — a promote failure must not
        # block mint/relink (conservation: no silent total abort).
        sched = _scheduler()
        mint = MagicMock(minted=1, scanned=1)
        with patch("scheduler.runner.Database"), \
             patch("services.signal_promoter.promote_events", side_effect=RuntimeError("boom")), \
             patch("services.fact_signals.mint_signals_from_facts", return_value=mint) as m, \
             patch("services.signal_promoter.relink_market_signals", return_value={}) as r:
            out = sched._run_sensing_promotion()
        assert out["signal_promotion"].startswith("ERROR")
        assert m.called and r.called  # downstream steps still ran
        assert out["fact_signal_mint"].startswith("OK")


class TestRegisterJobs:
    def test_sensing_promotion_job_is_registered(self):
        sched = _scheduler()
        sched._register_jobs()
        ids = {j.id for j in sched._scheduler.get_jobs()}
        assert "sensing_promotion" in ids, f"sensing_promotion not registered; got {sorted(ids)}"
