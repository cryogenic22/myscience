"""Helix Output-Quality scorecard — pure scoring + non-vacuous structure.

Guards against a vacuous benchmark: a dimension with no denominator must score
'n/a' (not 'ready'), and the readiness bar must be high enough that 60% coverage
is 'thin', not a pass.
"""

from __future__ import annotations

from benchmark.helix_output_scorecard import score_state, compute_scorecard, _dim


class TestScoreState:
    def test_high_coverage_ready(self):
        assert score_state(0.95) == "ready"
        assert score_state(1.0) == "ready"

    def test_mid_coverage_thin(self):
        assert score_state(0.6) == "thin"
        assert score_state(0.85) == "thin"

    def test_low_coverage_gap(self):
        assert score_state(0.3) == "gap"
        assert score_state(0.0) == "gap"

    def test_no_denominator_is_not_ready(self):
        # the anti-vacuous rule: nothing to measure must NOT read as a pass
        assert score_state(None) == "n/a"


class TestDimension:
    def test_ratio_and_state_computed(self):
        d = _dim("OQ1", "x", num=9, den=10)
        assert d.ratio == 0.9 and d.state == "ready"

    def test_zero_denominator_na(self):
        d = _dim("OQ1", "x", num=0, den=0)
        assert d.ratio is None and d.state == "n/a"


class _DB:
    def __init__(self, m):
        self.m = m

    def fetch_one(self, sql, params=None):
        for k, v in self.m.items():
            if k in sql:
                return {"c": v}
        return {"c": 0}


def test_compute_scorecard_shape():
    db = _DB({
        "FROM signals": 100,
        "FROM signal_facts": 95,
        "FROM facts WHERE superseded_by IS NULL AND source_doc_id": 80,
        "FROM facts WHERE superseded_by IS NULL AND detected_at": 100,
        "FROM facts WHERE superseded_by IS NULL": 100,
    })
    card = compute_scorecard(db)
    keys = {d["key"] for d in card["dimensions"]}
    assert {"OQ1_sensing", "OQ2_calibration_audit", "OQ3_contradiction_ready",
            "OQ5_provenance", "OQ6_as_of"} <= keys
    assert "ready" in card and "gaps" in card and "summary" in card
