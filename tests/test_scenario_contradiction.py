"""Loop 1 (Helix output-quality) — contradiction handling + signal stance.

The calibration loop historically only *corroborated* (monotonic ≥ prior); a
signal that should LOWER a scenario could not. This is the conservation-shaped
gap the demand memo flags ("don't average contradictions away — they're often
the insight") and the Helix Output-Quality Benchmark's **OQ3** gate.

Mechanism (TA-general, deterministic): a signal carries a polarity in
``signals.direction`` (positive|negative|neutral|mixed) derived from its source
predicate. For a *competitive-pressure* scenario (the threat = a rival being
strong), a ``negative``-on-rival signal CONTRADICTS the scenario and pulls its
probability toward a floor; a ``positive`` one supports it (as before). Nothing
here is obesity-specific — it keys off predicate + scenario kind.
"""

from __future__ import annotations

from services.fact_signals import signal_direction, build_signal_row
from services.scenario_calibration import calibrate_scenario_prob


def _sig(direction=None, conf="confirmed", headline="readout",
         created_at="2026-05-20T00:00:00Z"):
    return {
        "id": f"sig-{direction}-{conf}",
        "confidence_tier": conf,
        "impact_tier": "high",
        "headline": headline,
        "direction": direction,
        "created_at": created_at,
    }


class TestSignalDirection:
    def test_setbacks_are_negative(self):
        assert signal_direction("safety_signal", {}) == "negative"
        assert signal_direction("regulatory_setback", {}) == "negative"

    def test_wins_are_positive(self):
        assert signal_direction("regulatory_approval", {}) == "positive"
        assert signal_direction("fda_approval_date", {}) == "positive"
        assert signal_direction("competitor_launch", {}) == "positive"

    def test_trial_result_reads_outcome_text(self):
        assert signal_direction("trial_result", {"description": "did not meet primary endpoint"}) == "negative"
        assert signal_direction("trial_result", {"description": "met primary endpoint, superior to comparator"}) == "positive"
        # no directional language → neutral, never a guess
        assert signal_direction("trial_result", {"description": "topline data reported"}) == "neutral"

    def test_unknown_predicate_neutral(self):
        assert signal_direction("mechanism_of_action", {}) == "neutral"

    def test_build_signal_row_populates_direction(self):
        row = build_signal_row({
            "predicate": "regulatory_setback", "subject_entity_id": "d1",
            "subject_entity_type": "drug", "source_doc_id": "doc1",
            "object_value": {"description": "CRL issued"}, "fact_class": "corporate",
        })
        assert row is not None
        assert row["direction"] == "negative"


class TestContradictionLowersProbability:
    def test_negative_signal_on_competitive_scenario_lowers_below_prior(self):
        # OQ3: a contradicting signal MUST be able to pull a scenario down.
        current, note = calibrate_scenario_prob(
            prior=0.6, signals=[_sig(direction="negative")],
            entity_label="tirzepatide", competitive=True,
        )
        assert current is not None
        assert current < 0.6, f"contradiction did not lower probability: {current}"
        assert "contradict" in note.lower()

    def test_positive_signal_on_competitive_scenario_still_raises(self):
        current, _ = calibrate_scenario_prob(
            prior=0.3, signals=[_sig(direction="positive")],
            entity_label="tirzepatide", competitive=True,
        )
        assert current > 0.3

    def test_non_competitive_scenario_never_lowers_on_negative(self):
        # Conservative: outside competitive-pressure semantics we do NOT guess a
        # contradiction (a negative focal signal often SUPPORTS a risk scenario).
        current, _ = calibrate_scenario_prob(
            prior=0.3, signals=[_sig(direction="negative")],
            entity_label="focal", competitive=False,
        )
        assert current >= 0.3

    def test_bounded_to_floor(self):
        current, _ = calibrate_scenario_prob(
            prior=0.5,
            signals=[_sig(direction="negative") for _ in range(40)],
            entity_label="rival", competitive=True,
        )
        assert current >= 0.05

    def test_mixed_window_nets_out_and_is_explained(self):
        current, note = calibrate_scenario_prob(
            prior=0.5,
            signals=[_sig(direction="positive"), _sig(direction="negative")],
            entity_label="rival", competitive=True,
        )
        assert current is not None
        assert "corroborat" in note.lower() and "contradict" in note.lower()
