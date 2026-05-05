"""SPEC-021 D2 — calibration_math unit tests.

Pure-functional parser + scoring; no DB or network.
"""

from __future__ import annotations

from datetime import date

import pytest

from services import calibration_math as cm


# ────────────────────────────────────────────────────────────────────
# parse_target_value
# ────────────────────────────────────────────────────────────────────

class TestParseTargetValue:

    def test_pp_positive(self):
        t = cm.parse_target_value("+3pp")
        assert t is not None
        assert t.unit == "pp"
        assert t.magnitude == 3.0
        assert t.direction == "increase"

    def test_pp_negative(self):
        t = cm.parse_target_value("-2 pp")
        assert t.unit == "pp"
        assert t.magnitude == -2.0
        assert t.direction == "decrease"

    def test_pp_with_quarter_deadline(self):
        t = cm.parse_target_value("+3pp by Q4 2026")
        assert t.unit == "pp"
        assert t.by_date is not None
        assert t.by_date.year == 2026
        assert t.by_date.month == 12

    def test_usd_billions(self):
        t = cm.parse_target_value("$5B")
        assert t.unit == "usd"
        assert t.magnitude == 5_000_000_000

    def test_usd_millions(self):
        t = cm.parse_target_value("$500M")
        assert t.unit == "usd"
        assert t.magnitude == 500_000_000

    def test_usd_decimal(self):
        t = cm.parse_target_value("$1.2B by 2027-12-31")
        assert t.unit == "usd"
        assert t.magnitude == pytest.approx(1_200_000_000, abs=1)
        assert t.by_date == date(2027, 12, 31)

    def test_phase(self):
        t = cm.parse_target_value("Phase 3 by Q3 2026")
        assert t.unit == "phase"
        assert t.magnitude == 3.0

    def test_duration_lte(self):
        t = cm.parse_target_value("<6 months")
        assert t.unit == "duration"
        assert t.magnitude == 180.0  # 6 * 30
        assert t.direction == "lte"

    def test_duration_in_days(self):
        t = cm.parse_target_value("<= 90 days")
        assert t.unit == "duration"
        assert t.magnitude == 90.0

    def test_percent_gte(self):
        t = cm.parse_target_value(">=80% adherence")
        assert t.unit == "percent"
        assert t.magnitude == 80.0
        assert t.direction == "gte"

    def test_percent_plain(self):
        t = cm.parse_target_value("80%")
        assert t.unit == "percent"
        assert t.magnitude == 80.0
        assert t.direction == "eq"

    def test_unparseable_returns_none(self):
        assert cm.parse_target_value("market dominance") is None
        assert cm.parse_target_value("") is None
        assert cm.parse_target_value(None) is None

    def test_pp_takes_precedence_over_percent(self):
        """'+3pp' must parse as pp, not as a stray '3%'."""
        t = cm.parse_target_value("+3pp by Q4")
        assert t.unit == "pp"


# ────────────────────────────────────────────────────────────────────
# compute_numeric_calibration
# ────────────────────────────────────────────────────────────────────

class TestNumericCalibration:

    def test_exact_pp_match(self):
        # Predicted +3pp, actual +3pp → 1.0
        s = cm.compute_numeric_calibration(target_value="+3pp", actual_outcome="+3pp")
        assert s == 1.0

    def test_close_pp_match_within_tolerance(self):
        # Within 1pp tolerance → still 1.0
        s = cm.compute_numeric_calibration(target_value="+3pp", actual_outcome="+2.5pp")
        assert s == 1.0

    def test_pp_mid_distance(self):
        # 2pp off (tolerance is 1pp; 4×tol = 4pp range)
        s = cm.compute_numeric_calibration(target_value="+3pp", actual_outcome="+5pp")
        assert 0.0 < s < 1.0

    def test_pp_opposite_sign_heavy_penalty(self):
        # Predicted +3pp, actual -3pp → opposite direction
        s = cm.compute_numeric_calibration(target_value="+3pp", actual_outcome="-3pp")
        assert s < 0.5  # heavy penalty for getting direction wrong

    def test_usd_relative_tolerance(self):
        # Predicted $5B, actual $5.4B → within 10% → still 1.0
        s = cm.compute_numeric_calibration(target_value="$5B", actual_outcome="$5.4B")
        assert s == 1.0

    def test_usd_off_by_25pct_within_decay_range(self):
        # 25% off — outside 10% tolerance but inside 4×tol (40%) → decays
        # to a value > 0 but < 1.
        s = cm.compute_numeric_calibration(target_value="$5B", actual_outcome="$3.75B")
        assert 0.0 < s < 1.0

    def test_usd_far_off_decays_to_zero(self):
        # 50% off is beyond 4× the 10% USD tolerance → 0.0 (genuinely poor)
        s = cm.compute_numeric_calibration(target_value="$5B", actual_outcome="$2.5B")
        assert s == 0.0

    def test_phase_match(self):
        s = cm.compute_numeric_calibration(target_value="Phase 3", actual_outcome="Phase 3")
        assert s == 1.0

    def test_phase_mismatch(self):
        s = cm.compute_numeric_calibration(target_value="Phase 3", actual_outcome="Phase 2")
        # 1 phase off, tolerance 0.5 — outside → < 1.0
        assert 0.0 <= s < 1.0

    def test_unit_mismatch_returns_none(self):
        # Predicted in pp, actual in usd → no comparison possible
        s = cm.compute_numeric_calibration(target_value="+3pp", actual_outcome="$5B")
        assert s is None

    def test_unparseable_returns_none(self):
        # Caller falls back to categorical heuristic
        s = cm.compute_numeric_calibration(
            target_value="market dominance",
            actual_outcome="we won",
        )
        assert s is None
