"""BE-35 — curator weight-learning tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest


# ════════════════════════════════════════════════════════════════════
# Migration 074
# ════════════════════════════════════════════════════════════════════

def test_migration_074_exists_and_creates_audit_table():
    path = Path(__file__).parent.parent / "schema" / "migrations" / "074_source_weight_audit.sql"
    sql = path.read_text(encoding="utf-8").lower()
    assert "create table" in sql and "source_weight_audit_log" in sql
    for col in ("source_id", "old_weight", "new_weight", "delta",
                "contributing_decisions", "actor"):
        assert col in sql


# ════════════════════════════════════════════════════════════════════
# aggregate_outcomes
# ════════════════════════════════════════════════════════════════════

class TestAggregate:
    def test_groups_per_source(self):
        from services.curator.weight_learning import aggregate_outcomes
        rows = [
            {"source_id": "fda", "decision_id": "d-1", "outcome_correct": True},
            {"source_id": "fda", "decision_id": "d-2", "outcome_correct": False},
            {"source_id": "pubmed", "decision_id": "d-3", "outcome_correct": True},
        ]
        out = aggregate_outcomes(rows)
        assert out["fda"] == {"hits": 1, "total": 2}
        assert out["pubmed"] == {"hits": 1, "total": 1}

    def test_skips_rows_without_source_id(self):
        from services.curator.weight_learning import aggregate_outcomes
        out = aggregate_outcomes([{"decision_id": "x"}])
        assert out == {}


# ════════════════════════════════════════════════════════════════════
# compute_changes
# ════════════════════════════════════════════════════════════════════

class TestComputeChanges:
    def test_lifts_high_performing_source(self):
        from services.curator.weight_learning import compute_changes
        out = compute_changes(
            aggregates={"fda": {"hits": 10, "total": 10}},
            current_weights={"fda": 0.7},
        )
        assert len(out) == 1
        assert out[0].new_weight > out[0].old_weight  # hit_rate=1.0 > 0.7

    def test_demotes_poor_performer(self):
        from services.curator.weight_learning import compute_changes
        out = compute_changes(
            aggregates={"shaky": {"hits": 0, "total": 10}},
            current_weights={"shaky": 0.7},
        )
        assert len(out) == 1
        assert out[0].new_weight < out[0].old_weight

    def test_clamps_to_unit_interval(self):
        from services.curator.weight_learning import compute_changes
        out = compute_changes(
            aggregates={"fda": {"hits": 10, "total": 10}},
            current_weights={"fda": 0.99},
            learning_rate=0.5,  # exaggerated rate
        )
        assert 0.0 <= out[0].new_weight <= 1.0

    def test_no_change_skipped(self):
        from services.curator.weight_learning import compute_changes
        # hit_rate equals current weight → zero delta → no change row
        out = compute_changes(
            aggregates={"fda": {"hits": 7, "total": 10}},
            current_weights={"fda": 0.7},
        )
        assert out == []

    def test_default_baseline_for_unknown_source(self):
        from services.curator.weight_learning import compute_changes, DEFAULT_BASELINE
        out = compute_changes(
            aggregates={"new-source": {"hits": 10, "total": 10}},
            current_weights={},
        )
        assert out[0].old_weight == pytest.approx(DEFAULT_BASELINE)


# ════════════════════════════════════════════════════════════════════
# apply_and_audit
# ════════════════════════════════════════════════════════════════════

class TestApplyAndAudit:
    def test_writes_update_and_audit_per_change(self):
        from services.curator.weight_learning import (
            apply_and_audit, WeightChange,
        )
        db = MagicMock()
        changes = [
            WeightChange(source_id="fda", old_weight=0.7, new_weight=0.75,
                         contributing_decisions=10),
            WeightChange(source_id="pubmed", old_weight=0.6, new_weight=0.55,
                         contributing_decisions=5),
        ]
        n = apply_and_audit(db, changes)
        assert n == 2
        sqls = [str(c.args[0]).lower() for c in db.execute.call_args_list if c.args]
        # Two UPDATE sources rows + two INSERT INTO source_weight_audit_log
        assert sum(1 for s in sqls if "update sources" in s and "predictive_accuracy" in s) == 2
        assert sum(1 for s in sqls if "insert into source_weight_audit_log" in s) == 2

    def test_db_failure_is_non_fatal(self):
        from services.curator.weight_learning import apply_and_audit, WeightChange
        db = MagicMock()
        db.execute.side_effect = RuntimeError("update failed")
        n = apply_and_audit(db, [
            WeightChange(source_id="fda", old_weight=0.7, new_weight=0.75,
                         contributing_decisions=1),
        ])
        # Failures swallowed — applied counter stays 0
        assert n == 0
