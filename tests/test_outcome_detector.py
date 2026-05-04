"""SPEC-021 Phase D MVP — outcome_detector unit tests.

Pure-function scoring math + the DB-bound matcher with a stub DB.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from services import outcome_detector as od


# ────────────────────────────────────────────────────────────────────
# _kbq_for_move
# ────────────────────────────────────────────────────────────────────

class TestKbqForMove:

    def test_every_known_move_maps_to_at_least_one_kbq(self):
        from services.war_game_engine import MOVE_TYPES
        for mt in MOVE_TYPES:
            kbqs = od._kbq_for_move(mt)
            assert len(kbqs) >= 1, f"move_type {mt!r} has no KBQ mapping"

    def test_unknown_move_returns_empty(self):
        assert od._kbq_for_move("nonexistent") == set()

    def test_trial_readout_includes_clinical(self):
        assert "clinical" in od._kbq_for_move("trial_readout")

    def test_acquisition_includes_m_and_a(self):
        assert "m_and_a" in od._kbq_for_move("acquisition")


# ────────────────────────────────────────────────────────────────────
# _score_entity
# ────────────────────────────────────────────────────────────────────

class TestScoreEntity:

    def test_same_entity_full_credit(self):
        assert od._score_entity("ent-1", "ent-1") == od._W_ENTITY

    def test_different_entity_zero(self):
        assert od._score_entity("ent-1", "ent-2") == 0.0

    def test_related_entity_half_credit(self):
        score = od._score_entity("ent-1", "ent-2", ["ent-1", "ent-99"])
        assert score == od._W_ENTITY * 0.5

    def test_none_inputs_zero(self):
        assert od._score_entity(None, "ent-1") == 0.0
        assert od._score_entity("ent-1", None) == 0.0


# ────────────────────────────────────────────────────────────────────
# _score_kbq
# ────────────────────────────────────────────────────────────────────

class TestScoreKbq:

    def test_full_overlap_full_credit(self):
        # trial_readout expects {clinical}; signal has [clinical, regulatory]
        score = od._score_kbq("trial_readout", ["clinical", "regulatory"])
        assert score == pytest.approx(od._W_KBQ, abs=0.001)

    def test_no_overlap_zero(self):
        score = od._score_kbq("trial_readout", ["pricing_access"])
        assert score == 0.0

    def test_partial_overlap_proportional(self):
        # acquisition expects {m_and_a, strategic}; signal has only [m_and_a]
        score = od._score_kbq("acquisition", ["m_and_a"])
        # 1 of 2 = 50% of _W_KBQ
        assert score == pytest.approx(od._W_KBQ * 0.5, abs=0.001)

    def test_empty_signal_tags_zero(self):
        assert od._score_kbq("trial_readout", []) == 0.0
        assert od._score_kbq("trial_readout", None) == 0.0

    def test_unknown_move_zero(self):
        assert od._score_kbq("unknown", ["clinical"]) == 0.0


# ────────────────────────────────────────────────────────────────────
# _score_temporal
# ────────────────────────────────────────────────────────────────────

class TestScoreTemporal:

    def _dt(self, y, m, d):
        return datetime(y, m, d, tzinfo=timezone.utc)

    def test_signal_before_decision_zero(self):
        # Signal landed before decision was committed — can't be its outcome
        s = od._score_temporal(
            self._dt(2026, 5, 1),
            date(2026, 12, 31),
            self._dt(2026, 4, 1),
        )
        assert s == 0.0

    def test_signal_in_window_full_credit(self):
        s = od._score_temporal(
            self._dt(2026, 5, 1),
            date(2026, 12, 31),
            self._dt(2026, 8, 1),
        )
        assert s == od._W_TEMPORAL

    def test_signal_just_after_window_half_credit(self):
        s = od._score_temporal(
            self._dt(2026, 5, 1),
            date(2026, 6, 1),
            # window = [May 1, July 1] (deadline + 30d). Signal Aug 15 → 45 days late
            self._dt(2026, 8, 15),
        )
        assert s == pytest.approx(od._W_TEMPORAL * 0.5, abs=0.001)

    def test_signal_far_after_window_zero(self):
        s = od._score_temporal(
            self._dt(2026, 5, 1),
            date(2026, 6, 1),
            self._dt(2027, 5, 1),
        )
        assert s == 0.0

    def test_no_deadline_uses_180_day_window(self):
        s = od._score_temporal(
            self._dt(2026, 5, 1),
            None,
            self._dt(2026, 9, 1),  # 4 months later — in 180d window
        )
        assert s == od._W_TEMPORAL


# ────────────────────────────────────────────────────────────────────
# compute_calibration_score — all 4 quadrants
# ────────────────────────────────────────────────────────────────────

class TestCalibrationScore:

    def test_verified_high_confidence_full_credit(self):
        s = od.compute_calibration_score(verdict="verified", confidence_at_commit=0.8)
        assert s == 0.8

    def test_verified_low_confidence_inverse(self):
        # We hedged but were right — partial credit (= 1 - 0.2 = 0.8)
        s = od.compute_calibration_score(verdict="verified", confidence_at_commit=0.2)
        assert s == pytest.approx(0.8, abs=0.001)

    def test_missed_high_confidence_inverse(self):
        # We were confident and wrong — heavy penalty (= 1 - 0.8 = 0.2)
        s = od.compute_calibration_score(verdict="missed", confidence_at_commit=0.8)
        assert s == pytest.approx(0.2, abs=0.001)

    def test_missed_low_confidence_light_penalty(self):
        # We hedged AND were wrong — small penalty (= 0.2)
        s = od.compute_calibration_score(verdict="missed", confidence_at_commit=0.2)
        assert s == pytest.approx(0.2, abs=0.001)

    def test_null_confidence_returns_neutral(self):
        s = od.compute_calibration_score(verdict="verified", confidence_at_commit=None)
        assert s == 0.5

    def test_cancelled_returns_neutral(self):
        s = od.compute_calibration_score(verdict="cancelled", confidence_at_commit=0.7)
        assert s == 0.5

    def test_clamps_input(self):
        s = od.compute_calibration_score(verdict="verified", confidence_at_commit=1.7)
        assert s == 1.0


# ────────────────────────────────────────────────────────────────────
# suggest_weight_delta
# ────────────────────────────────────────────────────────────────────

class TestWeightDelta:

    def test_verified_positive(self):
        d = od.suggest_weight_delta(calibration_score=0.9, verdict="verified")
        assert d > 0

    def test_missed_negative(self):
        d = od.suggest_weight_delta(calibration_score=0.2, verdict="missed")
        assert d < 0

    def test_cancelled_zero(self):
        d = od.suggest_weight_delta(calibration_score=0.7, verdict="cancelled")
        assert d == 0.0

    def test_neutral_calibration_zero_magnitude(self):
        d = od.suggest_weight_delta(calibration_score=0.5, verdict="verified")
        assert abs(d) < 1e-9


# ────────────────────────────────────────────────────────────────────
# match_signals_to_decision
# ────────────────────────────────────────────────────────────────────

class TestMatchSignalsToDecision:

    def _decision(self, **overrides):
        base = {
            "id": "dec-1",
            "move_type": "trial_readout",
            "source_signal_id": None,
            "created_at": datetime(2026, 5, 1, tzinfo=timezone.utc),
            "deadline": date(2026, 12, 31),
            "confidence_at_commit": 0.6,
        }
        base.update(overrides)
        return base

    def _signals_db(self, signals):
        db = MagicMock()
        db.fetch_all.return_value = signals
        return db

    def _make_signal(self, sid, *, entity_id="ent-novo", kbq=("clinical",),
                     created=datetime(2026, 8, 1, tzinfo=timezone.utc),
                     name="Novo Nordisk", related=None):
        return {
            "id": sid,
            "headline": f"Signal {sid}",
            "summary": "summary",
            "kbq_tags": list(kbq),
            "primary_entity_id": entity_id,
            "primary_entity_name": name,
            "related_entity_ids": list(related or []),
            "created_at": created,
            "confidence_tier": "reported",
            "trust_score": 0.7,
            "impact_tier": "high",
            "rule_version_id": "intel-v1.2.0",
        }

    def test_returns_high_score_match(self):
        db = self._signals_db([
            self._make_signal("sig-1"),  # entity match + KBQ match + in-window
        ])
        out = od.match_signals_to_decision(
            db, decision=self._decision(), entity_id_for_matching="ent-novo",
        )
        assert len(out) == 1
        assert out[0]["signal_id"] == "sig-1"
        assert out[0]["match_score"] >= 0.8  # 0.5 + 0.3 + 0.2

    def test_excludes_below_threshold(self):
        db = self._signals_db([
            # Wrong entity, wrong KBQ → score = 0
            self._make_signal("sig-low", entity_id="ent-other", kbq=["pricing_access"]),
        ])
        out = od.match_signals_to_decision(
            db, decision=self._decision(), entity_id_for_matching="ent-novo",
        )
        assert out == []

    def test_excludes_source_signal(self):
        db = self._signals_db([
            self._make_signal("sig-source"),  # would be high-score
            self._make_signal("sig-other"),
        ])
        out = od.match_signals_to_decision(
            db,
            decision=self._decision(source_signal_id="sig-source"),
            entity_id_for_matching="ent-novo",
        )
        assert {c["signal_id"] for c in out} == {"sig-other"}

    def test_sorts_by_match_score_descending(self):
        db = self._signals_db([
            # Low score: KBQ partial (only 1 of 2 expected), wrong entity
            self._make_signal("sig-low", entity_id="ent-other", kbq=["clinical"],
                              related=["ent-novo"]),
            # High score: full entity match + full KBQ + in-window
            self._make_signal("sig-high"),
        ])
        out = od.match_signals_to_decision(
            db, decision=self._decision(), entity_id_for_matching="ent-novo",
        )
        assert out[0]["signal_id"] == "sig-high"
        assert out[0]["match_score"] > out[1]["match_score"]

    def test_caps_at_max_candidates(self):
        # 8 high-scoring signals; matcher should return only top 5
        db = self._signals_db([
            self._make_signal(f"sig-{i}") for i in range(8)
        ])
        out = od.match_signals_to_decision(
            db, decision=self._decision(), entity_id_for_matching="ent-novo",
        )
        assert len(out) == od.MAX_CANDIDATES

    def test_returns_match_components(self):
        db = self._signals_db([self._make_signal("sig-1")])
        out = od.match_signals_to_decision(
            db, decision=self._decision(), entity_id_for_matching="ent-novo",
        )
        comp = out[0]["match_components"]
        assert "entity_overlap" in comp
        assert "kbq_overlap" in comp
        assert "temporal_proximity" in comp

    def test_db_failure_returns_empty(self):
        db = MagicMock()
        db.fetch_all.side_effect = RuntimeError("connection lost")
        out = od.match_signals_to_decision(
            db, decision=self._decision(), entity_id_for_matching="ent-novo",
        )
        assert out == []
