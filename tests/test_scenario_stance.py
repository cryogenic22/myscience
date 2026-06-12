"""Helix gap #3 — scenario-relative signal stance + downward calibration.

A negative signal about a RIVAL must be able to REFUTE a competitive-pressure
scenario (pull its probability toward the floor), not only corroborate it. Every
other case stays SUPPORTS, so there is no regression vs the pre-stance loop.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from services.scenario_calibration import (
    CONTRADICTS,
    SUPPORTS,
    calibrate_engagement_scenarios,
    calibrate_scenario_prob,
    signal_stance,
)


def _sig(conf="confirmed", *, direction=None, stance=None,
         headline="Phase 3 readout", created_at="2026-05-20T00:00:00Z"):
    s = {
        "id": f"sig-{conf}-{direction}",
        "confidence_tier": conf,
        "impact_tier": "high",
        "direction": direction,
        "headline": headline,
        "created_at": created_at,
    }
    if stance is not None:
        s["stance"] = stance
    return s


# ── pure stance classifier ─────────────────────────────────────────────────

class TestSignalStance:
    def test_negative_rival_signal_contradicts_competitive_scenario(self):
        assert signal_stance("negative", scenario_is_competitive=True) == CONTRADICTS

    def test_positive_rival_signal_supports(self):
        assert signal_stance("positive", scenario_is_competitive=True) == SUPPORTS

    def test_neutral_or_unknown_rival_signal_supports(self):
        assert signal_stance("neutral", scenario_is_competitive=True) == SUPPORTS
        assert signal_stance(None, scenario_is_competitive=True) == SUPPORTS

    def test_negative_signal_on_focal_scenario_still_supports(self):
        # no polarity model for focal-asset scenarios → no wrong-direction refute
        assert signal_stance("negative", scenario_is_competitive=False) == SUPPORTS


# ── stance-aware math ───────────────────────────────────────────────────────

class TestStanceCalibration:
    def test_contradicting_signal_lowers_below_prior(self):
        cur, note = calibrate_scenario_prob(
            prior=0.5, signals=[_sig("confirmed", stance=CONTRADICTS)],
            entity_label="tirzepatide")
        assert cur is not None and cur < 0.5
        assert "contradicting" in note and "lowered" in note

    def test_supporting_signal_still_raises(self):
        cur, _ = calibrate_scenario_prob(
            prior=0.5, signals=[_sig("confirmed", stance=SUPPORTS)],
            entity_label="tirzepatide")
        assert cur > 0.5

    def test_missing_stance_defaults_to_supports(self):
        # backward-compat: a caller that never sets stance gets the old behaviour
        cur, _ = calibrate_scenario_prob(
            prior=0.5, signals=[_sig("confirmed")], entity_label="x")
        assert cur > 0.5

    def test_mixed_stances_net_out(self):
        sup_only, _ = calibrate_scenario_prob(
            prior=0.5, signals=[_sig("confirmed", stance=SUPPORTS)], entity_label="x")
        mixed, _ = calibrate_scenario_prob(
            prior=0.5,
            signals=[_sig("confirmed", stance=SUPPORTS),
                     _sig("confirmed", stance=CONTRADICTS)],
            entity_label="x")
        assert mixed < sup_only  # the contradiction pulls the net back down

    def test_contradiction_bounded_at_floor(self):
        cur, _ = calibrate_scenario_prob(
            prior=0.2,
            signals=[_sig("confirmed", stance=CONTRADICTS) for _ in range(40)],
            entity_label="x")
        assert cur >= 0.05

    def test_disputed_contradiction_has_no_weight(self):
        cur, note = calibrate_scenario_prob(
            prior=0.4, signals=[_sig("disputed", stance=CONTRADICTS)], entity_label="x")
        assert cur is None and note is None  # zero-weight → not a mover


# ── engagement-level: a negative rival signal refutes the pressure scenario ──

class TestEngagementRefutation:
    def _db(self, *, asset_row, scenarios, signals_by_entity):
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
                eid = params[1] if params and len(params) > 1 else None
                return signals_by_entity.get(eid, [])
            return []

        db.fetch_one = MagicMock(side_effect=fetch_one)
        db.fetch_all = MagicMock(side_effect=fetch_all)
        db.execute = MagicMock()
        return db

    def test_negative_rival_signal_lowers_competitive_scenario(self, monkeypatch):
        import services.scenario_calibration as sc

        def fake_resolve(db, asset):
            if "tirzepatide" in asset:
                return ("drug", "rival-1")
            return ("drug", "focal-1")
        monkeypatch.setattr(sc, "resolve_asset_to_subject", fake_resolve)

        db = self._db(
            asset_row={"asset": "drug:semaglutide"},
            scenarios=[{
                "id": "scn-1", "name": "Competitive pressure: tirzepatide",
                "prior_prob": 0.5, "current_prob": None,
                "created_at": "2026-05-01T00:00:00Z",
            }],
            signals_by_entity={"rival-1": [
                _sig("confirmed", direction="negative",
                     headline="SURMOUNT readout misses primary endpoint"),
            ]},
        )
        n = calibrate_engagement_scenarios(db, "eng-1")
        assert n == 1
        new_prob = db.execute.call_args[0][1][0]
        assert new_prob < 0.5  # the rival weakened → pressure scenario refuted
