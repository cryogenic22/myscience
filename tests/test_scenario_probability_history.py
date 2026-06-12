"""Loop 2 (Helix temporal) — scenario probability HISTORY / OQ2 gate.

The Helix Output-Quality Benchmark OQ2: *every scenario probability change has an
audit row* (prev -> new -> delta -> triggering signals -> method -> note). The
calibration loop previously kept only the latest note, so "why did this move
0.38 -> 0.12?" was unanswerable. This pins: a genuine change appends a history
row; an idempotent no-op run appends nothing; the helpers compute/return cleanly.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from services.scenario_calibration import (
    calibrate_engagement_scenarios,
    _record_prob_history,
)


def _sig(conf="confirmed", direction=None, sid="sig-1",
         headline="readout", created_at="2026-05-10T00:00:00Z"):
    return {"id": sid, "confidence_tier": conf, "impact_tier": "high",
            "headline": headline, "direction": direction, "created_at": created_at}


def _db(scenarios, signals_by_entity, asset="drug:semaglutide"):
    db = MagicMock()
    db.executed = []

    def fetch_one(sql, params=None):
        return {"asset": asset} if "from engagements" in (sql or "").lower() else None

    def fetch_all(sql, params=None):
        s = (sql or "").lower()
        if "from scenarios" in s:
            return scenarios
        if "from signals" in s:
            ent = params[1] if params and len(params) > 1 else None
            return signals_by_entity.get(ent, [])
        return []

    def execute(sql, params=None):
        db.executed.append((sql, params))

    db.fetch_one = MagicMock(side_effect=fetch_one)
    db.fetch_all = MagicMock(side_effect=fetch_all)
    db.execute = MagicMock(side_effect=execute)
    return db


def _history_writes(db):
    return [(s, p) for (s, p) in db.executed
            if "scenario_probability_history" in (s or "").lower()]


class TestProbabilityHistory:
    def test_change_appends_history_row(self, monkeypatch):
        import services.scenario_calibration as sc
        monkeypatch.setattr(sc, "resolve_asset_to_subject", lambda db, a: ("drug", "focal-1"))
        db = _db(
            scenarios=[{"id": "scn-1", "name": "Signal: label expands",
                        "prior_prob": 0.3, "current_prob": None,
                        "created_at": "2026-05-01T00:00:00Z"}],
            signals_by_entity={"focal-1": [_sig(sid="11111111-1111-1111-1111-111111111111")]},
        )
        calibrate_engagement_scenarios(db, "eng-1")
        writes = _history_writes(db)
        assert len(writes) == 1, "a probability change must append exactly one history row"
        _, params = writes[0]
        assert params[1] is None          # prev_prob (first calibration)
        assert isinstance(params[2], float) and params[2] > 0.3   # new_prob
        assert params[4] == ["11111111-1111-1111-1111-111111111111"]  # triggering signals

    def test_no_change_appends_nothing(self, monkeypatch):
        import services.scenario_calibration as sc
        monkeypatch.setattr(sc, "resolve_asset_to_subject", lambda db, a: ("drug", "focal-1"))
        # current_prob already equals what this evidence yields → idempotent no-op.
        # prior 0.3 + one confirmed signal = 0.3 + 1.0*0.30*(0.95-0.3) = 0.495.
        db = _db(
            scenarios=[{"id": "scn-1", "name": "Signal: x", "prior_prob": 0.3,
                        "current_prob": 0.495, "created_at": "2026-05-01T00:00:00Z"}],
            signals_by_entity={"focal-1": [_sig()]},
        )
        calibrate_engagement_scenarios(db, "eng-1")
        assert _history_writes(db) == [], "an unchanged probability must not append history"

    def test_clear_to_uncalibrated_is_recorded(self, monkeypatch):
        import services.scenario_calibration as sc
        monkeypatch.setattr(sc, "resolve_asset_to_subject", lambda db, a: ("drug", "focal-1"))
        db = _db(
            scenarios=[{"id": "scn-1", "name": "Signal: x", "prior_prob": 0.3,
                        "current_prob": 0.5, "created_at": "2026-05-01T00:00:00Z"}],
            signals_by_entity={},   # no evidence now → clears to NULL
        )
        calibrate_engagement_scenarios(db, "eng-1")
        writes = _history_writes(db)
        assert len(writes) == 1
        _, params = writes[0]
        assert params[1] == 0.5 and params[2] is None   # prev -> NULL

    def test_record_helper_computes_delta(self):
        db = MagicMock()
        db.execute = MagicMock()
        _record_prob_history(db, "scn-1", 0.3, 0.45, ["s1"], "ewma_calibration", "n")
        params = db.execute.call_args[0][1]
        assert params[3] == 0.15   # delta = new - prev

    def test_record_helper_never_raises_on_db_error(self):
        db = MagicMock()
        db.execute = MagicMock(side_effect=RuntimeError("no such table"))
        # must swallow-and-log, never break calibration
        _record_prob_history(db, "scn-1", 0.3, 0.45, [], "m", "n")
