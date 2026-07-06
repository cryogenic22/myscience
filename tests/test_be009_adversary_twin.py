"""BE-9 — adversary twin model tests."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest


# ════════════════════════════════════════════════════════════════════
# Migration shape
# ════════════════════════════════════════════════════════════════════

class TestMigration071:
    def test_seeds_six_twins(self):
        path = (
            Path(__file__).parent.parent
            / "schema" / "migrations" / "071_adversary_twins.sql"
        )
        sql = path.read_text(encoding="utf-8").lower()
        for name in ("pfizer", "lilly", "astrazeneca", "fda", "payer", "kol panel"):
            assert name in sql, f"missing seed: {name}"
        assert "create table" in sql
        assert "posterior" in sql and "evidence_log" in sql
        assert "unique (kind, name)" in sql


# ════════════════════════════════════════════════════════════════════
# Service
# ════════════════════════════════════════════════════════════════════

def _row(name="Pfizer", kind="competitor",
         posterior=None, log=None):
    return {
        "twin_id": "tw-1",
        "name": name,
        "kind": kind,
        "posterior": posterior if posterior is not None else
                     {"aggressive": 0.55, "defensive": 0.25, "cash_constrained": 0.20},
        "last_updated_at": datetime.now(timezone.utc),
        "evidence_log": log or [],
    }


class TestNormalize:
    def test_normalises_to_unit_simplex(self):
        from services.adversary_twin import _normalize
        out = _normalize({"aggressive": 2.0, "defensive": 1.0, "cash_constrained": 1.0})
        assert sum(out.values()) == pytest.approx(1.0)
        assert out["aggressive"] == 0.5

    def test_handles_negative_values(self):
        from services.adversary_twin import _normalize
        out = _normalize({"aggressive": -1.0, "defensive": 0.5, "cash_constrained": 0.5})
        assert out["aggressive"] == 0.0
        assert sum(out.values()) == pytest.approx(1.0)

    def test_zero_total_returns_uniform(self):
        from services.adversary_twin import _normalize
        out = _normalize({"aggressive": 0, "defensive": 0, "cash_constrained": 0})
        assert all(v == pytest.approx(1/3) for v in out.values())


class TestGetAndList:
    def test_get_returns_twin(self):
        from services.adversary_twin import get
        db = MagicMock()
        db.fetch_one.return_value = _row()
        out = get(db, "tw-1")
        assert out.name == "Pfizer"
        assert out.posterior["aggressive"] == pytest.approx(0.55)

    def test_get_missing_returns_none(self):
        from services.adversary_twin import get
        db = MagicMock()
        db.fetch_one.return_value = None
        assert get(db, "missing") is None

    def test_list_filters_by_kind(self):
        from services.adversary_twin import list_twins
        db = MagicMock()
        db.fetch_all.return_value = [_row(name="Pfizer"), _row(name="Lilly")]
        out = list_twins(db, kind="competitor")
        assert len(out) == 2

    def test_list_rejects_unknown_kind(self):
        from services.adversary_twin import list_twins
        db = MagicMock()
        with pytest.raises(ValueError, match="kind must be in"):
            list_twins(db, kind="bogus")


class TestUpdateWithEvidence:
    def test_update_shifts_toward_target(self):
        from services.adversary_twin import update_with_evidence

        db = MagicMock()
        # First fetch_one is the GET inside update; second is UPDATE RETURNING.
        new_posterior = {"aggressive": 0.66, "defensive": 0.21, "cash_constrained": 0.13}
        db.fetch_one.side_effect = [
            _row(),
            _row(posterior=new_posterior, log=[
                {"ts": "x", "evidence_id": "ev-1",
                 "what_shifted": "approval news", "magnitude": 0.8,
                 "target_axis": "aggressive"},
            ]),
        ]
        out = update_with_evidence(
            db,
            twin_id="tw-1", evidence_id="ev-1", target_axis="aggressive",
            magnitude=0.8, what_shifted="approval news",
        )
        # New aggressive weight > old (0.55)
        assert out.posterior["aggressive"] > 0.55
        assert sum(out.posterior.values()) == pytest.approx(1.0)
        assert out.evidence_log[0]["evidence_id"] == "ev-1"

    def test_update_unknown_target_axis_raises(self):
        from services.adversary_twin import update_with_evidence

        db = MagicMock()
        with pytest.raises(ValueError, match="target_axis"):
            update_with_evidence(
                db, twin_id="x", evidence_id="ev-1",
                target_axis="bogus", magnitude=0.5, what_shifted="x",
            )

    def test_update_missing_twin_raises(self):
        from services.adversary_twin import update_with_evidence, TwinNotFound

        db = MagicMock()
        db.fetch_one.return_value = None
        with pytest.raises(TwinNotFound):
            update_with_evidence(
                db, twin_id="missing", evidence_id="ev",
                target_axis="aggressive", magnitude=0.5, what_shifted="x",
            )

    def test_evidence_log_capped_at_5(self):
        from services.adversary_twin import update_with_evidence, EVIDENCE_LOG_MAX

        old_log = [{"ts": "1", "evidence_id": str(i),
                    "what_shifted": "x", "magnitude": 0.1,
                    "target_axis": "aggressive"}
                   for i in range(EVIDENCE_LOG_MAX)]
        db = MagicMock()
        db.fetch_one.side_effect = [
            _row(log=old_log),
            _row(log=[{"ts": "new", "evidence_id": "ev-N",
                       "what_shifted": "x", "magnitude": 0.1,
                       "target_axis": "aggressive"}] + old_log[:EVIDENCE_LOG_MAX - 1]),
        ]
        out = update_with_evidence(
            db, twin_id="tw-1", evidence_id="ev-N",
            target_axis="aggressive", magnitude=0.5, what_shifted="x",
        )
        assert len(out.evidence_log) <= EVIDENCE_LOG_MAX
