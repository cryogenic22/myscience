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
    CORROBORATION_WEIGHT,
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
        assert "corroborating" in note
        assert "0.3" in note  # prior shown
        assert str(round(current, 2)) in note

    def test_disputed_only_is_uncalibrated(self):
        # A disputed signal must NOT inflate probability — it contributes no
        # corroboration, so a disputed-only window leaves the scenario uncalibrated.
        current, note = calibrate_scenario_prob(prior=0.3, signals=[_sig("disputed")], entity_label="x")
        assert current is None and note is None

    def test_never_drops_below_prior(self):
        # Honesty: this loop measures corroboration only, never refutation.
        current, _ = calibrate_scenario_prob(prior=0.6, signals=[_sig("inferred")], entity_label="x")
        assert current >= 0.6

    def test_weak_signal_lifts_less_than_confirmed(self):
        weak, _ = calibrate_scenario_prob(prior=0.3, signals=[_sig("inferred")], entity_label="x")
        strong, _ = calibrate_scenario_prob(prior=0.3, signals=[_sig("confirmed")], entity_label="x")
        assert weak < strong

    def test_weight_map_ordered_disputed_zero(self):
        assert (
            CORROBORATION_WEIGHT["confirmed"]
            > CORROBORATION_WEIGHT["reported"]
            > CORROBORATION_WEIGHT["inferred"]
            > CORROBORATION_WEIGHT["disputed"]
        )
        assert CORROBORATION_WEIGHT["disputed"] == 0.0

    def test_bounded_unit_interval(self):
        current, _ = calibrate_scenario_prob(
            prior=0.7, signals=[_sig("confirmed") for _ in range(50)], entity_label="x",
        )
        assert 0.0 <= current <= 0.95


class TestEngagementCalibration:
    def _db(self, *, asset_row, scenarios, signals_by_entity):
        """signals_by_entity: maps the entity_id used in the signals query →
        the signal rows to return, so a test can assert which entity was queried."""
        db = MagicMock()
        db.signal_entity_ids = []

        def fetch_one(sql, params=None):
            if "from engagements" in (sql or "").lower():
                return asset_row
            return None

        def fetch_all(sql, params=None):
            s = (sql or "").lower()
            if "from scenarios" in s:
                return scenarios
            if "from signals" in s:
                entity_id = params[1] if params and len(params) > 1 else None
                db.signal_entity_ids.append(entity_id)
                return signals_by_entity.get(entity_id, [])
            return []

        db.fetch_one = MagicMock(side_effect=fetch_one)
        db.fetch_all = MagicMock(side_effect=fetch_all)
        db.execute = MagicMock()
        return db

    def test_updates_scenario_with_corroborating_signal(self, monkeypatch):
        import services.scenario_calibration as sc
        monkeypatch.setattr(sc, "resolve_asset_to_subject", lambda db, asset: ("drug", "focal-1"))
        db = self._db(
            asset_row={"asset": "drug:semaglutide"},
            scenarios=[{
                "id": "scn-1", "name": "Signal: FDA expands label",
                "prior_prob": 0.3, "current_prob": None,
                "created_at": "2026-05-01T00:00:00Z",
            }],
            signals_by_entity={"focal-1": [
                _sig("confirmed", headline="Readout positive", created_at="2026-05-10T00:00:00Z"),
            ]},
        )
        n = calibrate_engagement_scenarios(db, "eng-1")
        assert n == 1
        update_sql = db.execute.call_args[0][0].lower()
        assert "update scenarios" in update_sql
        params = db.execute.call_args[0][1]
        assert any(isinstance(p, float) and 0.3 < p <= 0.95 for p in params)

    def test_competitive_scenario_targets_the_rival_not_focal(self, monkeypatch):
        """The key correctness fix: a 'Competitive pressure: tirzepatide' scenario
        must be calibrated by TIRZEPATIDE's signals, not the focal asset's."""
        import services.scenario_calibration as sc

        def resolve(db, asset):
            mapping = {"drug:semaglutide": ("drug", "focal-1"), "tirzepatide": ("drug", "rival-1")}
            return mapping.get(asset, ("drug", asset))
        monkeypatch.setattr(sc, "resolve_asset_to_subject", resolve)

        db = self._db(
            asset_row={"asset": "drug:semaglutide"},
            scenarios=[{
                "id": "scn-1", "name": "Competitive pressure: tirzepatide",
                "prior_prob": 0.3, "current_prob": None,
                "created_at": "2026-05-01T00:00:00Z",
            }],
            signals_by_entity={
                "rival-1": [_sig("confirmed", headline="Tirzepatide wins indication")],
                "focal-1": [],
            },
        )
        n = calibrate_engagement_scenarios(db, "eng-1")
        assert n == 1
        assert "rival-1" in db.signal_entity_ids   # queried the rival
        note = db.execute.call_args[0][1][1]
        assert "tirzepatide" in note               # note cites the rival entity

    def test_no_signals_makes_no_update(self, monkeypatch):
        import services.scenario_calibration as sc
        monkeypatch.setattr(sc, "resolve_asset_to_subject", lambda db, asset: ("drug", "focal-1"))
        db = self._db(
            asset_row={"asset": "drug:semaglutide"},
            scenarios=[{
                "id": "scn-1", "name": "Signal: x", "prior_prob": 0.3,
                "current_prob": None, "created_at": "2026-05-01T00:00:00Z",
            }],
            signals_by_entity={},
        )
        n = calibrate_engagement_scenarios(db, "eng-1")
        assert n == 0
        db.execute.assert_not_called()

    def test_stale_current_prob_cleared_when_no_corroboration(self, monkeypatch):
        """Idempotency: a scenario carrying a current_prob from a prior run, but
        with no corroborating evidence now, is reset to NULL (not left stale)."""
        import services.scenario_calibration as sc
        monkeypatch.setattr(sc, "resolve_asset_to_subject", lambda db, asset: ("drug", "focal-1"))
        db = self._db(
            asset_row={"asset": "drug:semaglutide"},
            scenarios=[{
                "id": "scn-1", "name": "Signal: x", "prior_prob": 0.3,
                "current_prob": 0.64,  # stale value from a previous run
                "created_at": "2026-05-01T00:00:00Z",
            }],
            signals_by_entity={},  # no signals now
        )
        n = calibrate_engagement_scenarios(db, "eng-1")
        assert n == 1
        params = db.execute.call_args[0][1]
        assert params[0] is None and params[1] is None  # cleared to uncalibrated

    def test_disputed_only_window_makes_no_update(self, monkeypatch):
        import services.scenario_calibration as sc
        monkeypatch.setattr(sc, "resolve_asset_to_subject", lambda db, asset: ("drug", "focal-1"))
        db = self._db(
            asset_row={"asset": "drug:semaglutide"},
            scenarios=[{
                "id": "scn-1", "name": "Signal: contested", "prior_prob": 0.3,
                "current_prob": None, "created_at": "2026-05-01T00:00:00Z",
            }],
            signals_by_entity={"focal-1": [_sig("disputed", headline="Unconfirmed rumor")]},
        )
        n = calibrate_engagement_scenarios(db, "eng-1")
        assert n == 0
        db.execute.assert_not_called()
