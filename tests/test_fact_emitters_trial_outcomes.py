"""TrialOutcomeEmitter — tests for the selective trial-outcome lift.

The ``trial_outcomes`` table holds ~3M registry-reported endpoint rows that
never become facts. This emitter converts only the HIGH-VALUE ones (a primary
endpoint, or any endpoint that carries an actual description) belonging to a
trial resolvable to a drug — mirroring AdverseEventEmitter's aggregate-not-dump
discipline. Pure mapping (``row_to_facts``, ``build_claim``, ``_qualifies``) is
DB-free; routing is asserted against the real dossier router so the facts land
in a domain. See tests/test_fact_emitters_dr3_dr4.py for the conventions.
"""

from __future__ import annotations

from services.fact_emitters.trial_outcomes import (
    TrialOutcomeEmitter,
    build_claim,
)
from services.fact_emitters.base import get_emitters
from services.dossier_kb import route_predicate_to_domain


def _outcome(**over):
    row = {
        "id": "outcome-1",
        "trial_id": "NCT05646706",
        "drug_id": "drug-sema",
        "outcome_type": "PRIMARY",
        "measure": "Change in body weight from baseline (%)",
        "time_frame": "Week 68",
        "description": "Percent change in body weight from baseline to week 68.",
        "phase": "Phase 3",
        "conditions": ["Obesity"],
        "source_api": "clinical_trials_gov",
        "source_url": "https://clinicaltrials.gov/study/NCT05646706",
    }
    row.update(over)
    return row


# ── selection policy (the governance — quality over volume) ─────────

class TestSelectionPolicy:
    def test_primary_with_description_qualifies(self):
        assert TrialOutcomeEmitter()._qualifies(_outcome()) is True

    def test_primary_without_description_still_qualifies(self):
        # A PRIMARY endpoint is meaningful even with no protocol blurb.
        assert TrialOutcomeEmitter()._qualifies(
            _outcome(description=None)) is True

    def test_secondary_with_description_qualifies(self):
        # Carries an actual result/value payload → meaningful.
        assert TrialOutcomeEmitter()._qualifies(
            _outcome(outcome_type="SECONDARY")) is True

    def test_secondary_without_description_is_skipped(self):
        # Empty placeholder secondary/other row → noise, skip (counted).
        assert TrialOutcomeEmitter()._qualifies(
            _outcome(outcome_type="SECONDARY", description=None)) is False
        assert TrialOutcomeEmitter()._qualifies(
            _outcome(outcome_type="OTHER", description="   ")) is False

    def test_no_drug_never_qualifies(self):
        assert TrialOutcomeEmitter()._qualifies(_outcome(drug_id=None)) is False

    def test_no_measure_never_qualifies(self):
        assert TrialOutcomeEmitter()._qualifies(_outcome(measure="")) is False


# ── build_claim / row_to_facts (pure) ──────────────────────────────

class TestTrialOutcomeMapping:
    def test_build_claim_reads_well(self):
        claim = build_claim(_outcome())
        assert claim == (
            "Primary endpoint: Change in body weight from baseline (%) "
            "(Week 68) — NCT05646706"
        )

    def test_build_claim_without_timeframe(self):
        claim = build_claim(_outcome(time_frame=None))
        assert claim == (
            "Primary endpoint: Change in body weight from baseline (%) "
            "— NCT05646706"
        )

    def test_row_to_facts_emits_one_efficacy_fact(self):
        facts = TrialOutcomeEmitter().row_to_facts(_outcome())
        assert len(facts) == 1
        f = facts[0]
        assert f.predicate == "efficacy_endpoint"
        assert f.subject_entity_type == "drug"
        assert f.subject_entity_id == "drug-sema"
        assert f.source_row_id == "outcome-1"
        assert f.fact_class == "corporate"
        assert f.object_value["outcome_type"] == "PRIMARY"
        assert f.object_value["measure"].startswith("Change in body weight")
        assert f.object_value["trial_id"] == "NCT05646706"
        assert f.object_value["time_frame"] == "Week 68"
        assert f.evidence_text  # DR-5: attestable snippet present
        assert f.source_url.endswith("NCT05646706")

    def test_primary_outcomes_get_higher_confidence(self):
        prim = TrialOutcomeEmitter().row_to_facts(_outcome())[0]
        sec = TrialOutcomeEmitter().row_to_facts(
            _outcome(outcome_type="SECONDARY"))[0]
        assert prim.confidence > sec.confidence

    def test_non_qualifying_row_emits_nothing(self):
        assert TrialOutcomeEmitter().row_to_facts(_outcome(drug_id=None)) == []
        assert TrialOutcomeEmitter().row_to_facts(
            _outcome(outcome_type="OTHER", description=None)) == []
        assert TrialOutcomeEmitter().row_to_facts(_outcome(measure="")) == []

    def test_evidence_prefers_description_over_measure(self):
        f = TrialOutcomeEmitter().row_to_facts(_outcome())[0]
        assert "Percent change in body weight" in f.evidence_text


# ── predicate routing (facts must land in a domain) ────────────────

class TestPredicateRouting:
    def test_efficacy_endpoint_routes_to_clinical_profile(self):
        assert route_predicate_to_domain("efficacy_endpoint") == "clinical_profile"


# ── registry ───────────────────────────────────────────────────────

class TestRegistry:
    def test_trial_outcomes_emitter_registered(self):
        assert "trial_outcomes" in get_emitters()
