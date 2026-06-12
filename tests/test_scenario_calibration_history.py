"""FS-1 / OQ2 — scenario_calibration_history append tape.

Every ACTUAL probability move writes exactly one append-only audit row
(prev→new→delta + stance mix + triggering signal); an idempotent recompute that
doesn't change the value writes none. A contradicting competitor signal writes a
row with delta < 0 and n_contradicting > 0 (the OQ2 + OQ3 structural gate).
"""
from __future__ import annotations

from unittest.mock import MagicMock

from services.scenario_calibration import (
    calibrate_engagement_scenarios,
    move_stats,
)


def _sig(conf="confirmed", *, direction=None, sid="sig-1",
         created_at="2026-05-20T00:00:00Z", headline="Readout"):
    return {
        "id": sid, "confidence_tier": conf, "impact_tier": "high",
        "direction": direction, "headline": headline, "created_at": created_at,
    }


def _db(*, asset_row, scenarios, signals_by_entity):
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


def _hist_inserts(db):
    return [c.args for c in db.execute.call_args_list
            if "scenario_calibration_history" in (c.args[0] or "")]


def test_move_stats_counts_supports_and_contradicts():
    sigs = [
        {"id": "a", "confidence_tier": "confirmed", "stance": "supports"},
        {"id": "b", "confidence_tier": "confirmed", "stance": "contradicts"},
        {"id": "c", "confidence_tier": "disputed", "stance": "contradicts"},  # 0 weight
    ]
    n_sup, n_con, trigger = move_stats(sigs)
    assert (n_sup, n_con) == (1, 1)
    assert trigger == "b"  # latest weighted mover


def test_first_calibration_writes_one_history_row():
    import services.scenario_calibration as sc
    sc.resolve_asset_to_subject = lambda db, asset: ("drug", "focal-1")
    db = _db(
        asset_row={"asset": "drug:semaglutide"},
        scenarios=[{"id": "scn-1", "name": "Signal: label expands",
                    "prior_prob": 0.3, "current_prob": None,
                    "created_at": "2026-05-01T00:00:00Z"}],
        signals_by_entity={"focal-1": [_sig("confirmed")]},
    )
    calibrate_engagement_scenarios(db, "eng-1")
    inserts = _hist_inserts(db)
    assert len(inserts) == 1
    params = inserts[0][1]
    # [scenario_id, prev, new, delta, n_sup, n_con, trigger, method, note]
    assert params[1] == 0.3 and params[2] > 0.3          # prev=prior, raised
    assert params[3] > 0 and params[4] >= 1               # delta>0, supporting
    assert params[5] == 0                                 # no contradiction


def test_idempotent_recompute_writes_no_history():
    import services.scenario_calibration as sc
    sc.resolve_asset_to_subject = lambda db, asset: ("drug", "focal-1")
    # current_prob already at the value this evidence calibrates to (0.495)
    db = _db(
        asset_row={"asset": "drug:semaglutide"},
        scenarios=[{"id": "scn-1", "name": "Signal: label expands",
                    "prior_prob": 0.3, "current_prob": 0.495,
                    "created_at": "2026-05-01T00:00:00Z"}],
        signals_by_entity={"focal-1": [_sig("confirmed")]},
    )
    calibrate_engagement_scenarios(db, "eng-1")
    assert _hist_inserts(db) == []  # no actual move → no row


def test_contradicting_signal_writes_downward_row():
    import services.scenario_calibration as sc

    def resolve(db, asset):
        return ("drug", "rival-1") if "tirzepatide" in asset else ("drug", "focal-1")
    sc.resolve_asset_to_subject = resolve

    db = _db(
        asset_row={"asset": "drug:semaglutide"},
        scenarios=[{"id": "scn-1", "name": "Competitive pressure: tirzepatide",
                    "prior_prob": 0.5, "current_prob": None,
                    "created_at": "2026-05-01T00:00:00Z"}],
        signals_by_entity={"rival-1": [
            _sig("confirmed", direction="negative", sid="neg-1",
                 headline="SURMOUNT misses endpoint")]},
    )
    calibrate_engagement_scenarios(db, "eng-1")
    inserts = _hist_inserts(db)
    assert len(inserts) == 1
    params = inserts[0][1]
    assert params[2] < 0.5 and params[3] < 0      # new<prior, delta<0
    assert params[5] >= 1                          # n_contradicting
    assert params[6] == "neg-1"                    # triggering signal
