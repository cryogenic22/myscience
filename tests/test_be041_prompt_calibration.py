"""BE-41 — outcome-to-prompt-weight backprop tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest


def test_migration_077_creates_calibration_table():
    sql = (Path(__file__).parent.parent / "schema" / "migrations"
           / "077_prompt_calibration.sql").read_text(encoding="utf-8").lower()
    assert "create table" in sql and "prompt_calibration" in sql
    for col in ("prompt_id", "calibration_score", "outcomes_seen", "updated_at"):
        assert col in sql


# ════════════════════════════════════════════════════════════════════
# aggregate
# ════════════════════════════════════════════════════════════════════

def test_aggregate_groups_per_prompt():
    from services.curator.prompt_calibration import aggregate
    rows = [
        {"prompt_id": "p-1", "outcome_correct": True},
        {"prompt_id": "p-1", "outcome_correct": False},
        {"prompt_id": "p-2", "outcome_correct": True},
    ]
    out = aggregate(rows)
    assert out["p-1"] == {"hits": 1, "total": 2}
    assert out["p-2"] == {"hits": 1, "total": 1}


# ════════════════════════════════════════════════════════════════════
# update_one
# ════════════════════════════════════════════════════════════════════

class TestUpdateOne:
    def test_lifts_score_for_winning_prompt(self):
        from services.curator.prompt_calibration import update_one
        new_s, new_n = update_one(
            prompt_id="p", hits=10, total=10,
            current_score=0.5, current_outcomes=20,
        )
        assert new_s > 0.5
        assert new_n == 30

    def test_zero_total_is_noop(self):
        from services.curator.prompt_calibration import update_one
        new_s, new_n = update_one(
            prompt_id="p", hits=0, total=0,
            current_score=0.5, current_outcomes=20,
        )
        assert (new_s, new_n) == (0.5, 20)

    def test_clamps_to_unit_interval(self):
        from services.curator.prompt_calibration import update_one
        new_s, _ = update_one(
            prompt_id="p", hits=10, total=10,
            current_score=0.99, current_outcomes=0,
            learning_rate=0.5,
        )
        assert 0.0 <= new_s <= 1.0


# ════════════════════════════════════════════════════════════════════
# run_recalibration
# ════════════════════════════════════════════════════════════════════

class TestRunRecalibration:
    def test_no_outcomes_returns_zero_summary(self):
        from services.curator.prompt_calibration import run_recalibration
        db = MagicMock()
        db.fetch_all.return_value = []
        out = run_recalibration(db)
        assert out["verified_outcomes"] == 0
        assert out["prompts_updated"] == 0

    def test_demotes_failing_prompt_above_min_outcomes(self):
        from services.curator.prompt_calibration import (
            run_recalibration, FLAG_MIN_OUTCOMES,
        )
        # 10 outcomes, 0 hits → score crashes; FLAG_MIN_OUTCOMES (5) met.
        outcomes = [
            {"prompt_id": "p-bad", "decision_id": f"d-{i}",
             "outcome_correct": False}
            for i in range(10)
        ]
        db = MagicMock()
        db.fetch_all.side_effect = [
            outcomes,                                    # outcome rows
            [{"prompt_id": "p-bad",                      # current calibration
              "calibration_score": 0.30, "outcomes_seen": 5}],
        ]
        out = run_recalibration(db)
        assert out["prompts_updated"] == 1
        assert out["flagged"] >= 1
        # Demotion UPDATE fired
        sqls = [str(c.args[0]).lower() for c in db.execute.call_args_list if c.args]
        assert any("update prompt_registry set is_active" in s for s in sqls)

    def test_no_demotion_below_min_outcomes(self):
        from services.curator.prompt_calibration import run_recalibration
        # Only 2 outcomes — below FLAG_MIN_OUTCOMES even if all wrong.
        outcomes = [
            {"prompt_id": "p-new", "decision_id": "d-1", "outcome_correct": False},
            {"prompt_id": "p-new", "decision_id": "d-2", "outcome_correct": False},
        ]
        db = MagicMock()
        db.fetch_all.side_effect = [outcomes, []]
        out = run_recalibration(db)
        assert out["flagged"] == 0
