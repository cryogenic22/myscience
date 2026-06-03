"""PB-H14 — scenario calibration loop tests.

A scenario is derived with a structural PRIOR. As signals about the engagement's
focal asset arrive AFTER derivation, they corroborate (or weakly contest) the
scenario, re-weighting prior_prob → current_prob via EWMA and recording a
calibration_note that cites the latest signal. Calibration only measures
evidence ACCUMULATION (honest: it never claims to know a scenario reversed),
so confirmed signals lift current_prob, weak/disputed ones pull toward neutral.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from services.scenario_calibration import (
    calibrate_scenario_prob,
    OBSERVATION_BY_CONFIDENCE,
    calibrate_engagement_scenarios,
)


def _sig(conf="confirmed", headline="Phase 3 win", created_at="2026-05-20T00:00:00Z"):
    return {
        "id": f"sig-{conf}",
        "confidence_tier": conf,
        "impact_tier": "high",
        "headline": headline,
        "created_at": created_at,
    }


class TestPureCalibration:
    def test_no_signals_leaves_uncalibrated(self):
        current, note = calibrate_scenario_prob(prior=0.3, signals=[], entity_label="semaglutide")
        assert current is None
        assert note is None

    def test_confirmed_signal_lifts_above_prior(self):
        current, note = calibrate_scenario_prob(
            prior=0.3, signals=[_sig("confirmed")], entity_label="semaglutide",
        )
        assert current is not None
        assert current > 0.3  # corroboration raises probability
        assert current <= 0.95

    def test_more_confirmed_signals_lift_further(self):
        one, _ = calibrate_scenario_prob(prior=0.3, signals=[_sig("confirmed")], entity_label="x")
        many, _ = calibrate_scenario_prob(
            prior=0.3, signals=[_sig("confirmed", headline=f"win {i}") for i in range(5)],
            entity_label="x",
        )
        assert many > one  # evidence accumulates

    def test_note_cites_count_entity_and_latest_signal(self):
        current, note = calibrate_scenario_prob(
            prior=0.3,
            signals=[_sig("confirmed", headline="FDA approval")],
            entity_label="semaglutide",
        )
        assert "semaglutide" in note
        assert "FDA approval" in note
        assert "0.3" in note  # prior shown
        assert str(round(current, 2)) in note

    def test_disputed_signal_does_not_overshoot(self):
        # A disputed signal corroborates weakly — should stay below a confirmed one.
        disputed, _ = calibrate_scenario_prob(prior=0.3, signals=[_sig("disputed")], entity_label="x")
        confirmed, _ = calibrate_scenario_prob(prior=0.3, signals=[_sig("confirmed")], entity_label="x")
        assert disputed < confirmed

    def test_observation_map_ordered(self):
        assert (
            OBSERVATION_BY_CONFIDENCE["confirmed"]
            > OBSERVATION_BY_CONFIDENCE["reported"]
            > OBSERVATION_BY_CONFIDENCE["inferred"]
            >= OBSERVATION_BY_CONFIDENCE["disputed"]
        )

    def test_bounded_unit_interval(self):
        current, _ = calibrate_scenario_prob(
            prior=0.7, signals=[_sig("confirmed") for _ in range(50)], entity_label="x",
        )
        assert 0.0 <= current <= 0.95


class TestEngagementCalibration:
    def _db(self, *, asset_row, scenarios, signals):
        db = MagicMock()

        def fetch_one(sql, params=None):
            if "from engagements" in (sql or "").lower():
                return asset_row
            return None

        def fetch_all(sql, params=None):
            s = (sql or "").lower()
            if "from scenarios" in s:
                return scenarios
            if "from signals" in s:
                return signals
            return []

        db.fetch_one = MagicMock(side_effect=fetch_one)
        db.fetch_all = MagicMock(side_effect=fetch_all)
        db.execute = MagicMock()
        return db

    def test_updates_scenario_with_corroborating_signal(self, monkeypatch):
        import services.scenario_calibration as sc
        # focal entity resolves to a drug id; one live scenario; one newer signal.
        monkeypatch.setattr(sc, "resolve_asset_to_subject", lambda db, asset: ("drug", "drug-1"))
        db = self._db(
            asset_row={"asset": "drug:semaglutide"},
            scenarios=[{
                "id": "scn-1", "name": "Competitive pressure: tirzepatide",
                "prior_prob": 0.3, "current_prob": None,
                "created_at": "2026-05-01T00:00:00Z",
            }],
            signals=[_sig("confirmed", headline="Readout positive", created_at="2026-05-10T00:00:00Z")],
        )
        n = calibrate_engagement_scenarios(db, "eng-1")
        assert n == 1
        # an UPDATE was issued carrying a current_prob + note
        assert db.execute.called
        update_sql = db.execute.call_args[0][0].lower()
        assert "update scenarios" in update_sql
        params = db.execute.call_args[0][1]
        assert any(isinstance(p, float) and 0.3 < p <= 0.95 for p in params)

    def test_no_signals_makes_no_update(self, monkeypatch):
        import services.scenario_calibration as sc
        monkeypatch.setattr(sc, "resolve_asset_to_subject", lambda db, asset: ("drug", "drug-1"))
        db = self._db(
            asset_row={"asset": "drug:semaglutide"},
            scenarios=[{
                "id": "scn-1", "name": "x", "prior_prob": 0.3,
                "current_prob": None, "created_at": "2026-05-01T00:00:00Z",
            }],
            signals=[],
        )
        n = calibrate_engagement_scenarios(db, "eng-1")
        assert n == 0
        db.execute.assert_not_called()
