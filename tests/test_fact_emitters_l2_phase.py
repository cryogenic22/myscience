"""L2 — phase-transition / development-lens fact emitter.

Pure-function tests on ``row_to_facts`` + domain routing + the development_success
playbook coverage. No DB.

The emitter derives three predicates from a drug's ``clinical_trials`` set (a
current-snapshot table, not a time-series): ``phase_transition`` (the program
advanced from one phase to a higher one), ``approval_event`` (reached
post-marketing / Phase 4 studies — an inference), and ``discontinuation`` (a
terminated / withdrawn / suspended trial). Filling these flips the
``development_success`` lens PARTIAL→COVERED (it routes to all three plus the
already-present ``clinical_trial``).
"""
from __future__ import annotations

from services.dossier_kb import route_predicate_to_domain
from services.fact_emitters.phase_transitions import (
    PhaseTransitionEmitter,
    phase_ordinal,
)


# ── phase parsing ───────────────────────────────────────────────────────────

def test_phase_ordinal_handles_real_prod_vocabulary():
    assert phase_ordinal("Phase 1") == 1
    assert phase_ordinal("Phase 4") == 4
    assert phase_ordinal("EARLY_Phase 1") == 1          # early-phase still phase 1
    assert phase_ordinal("Phase 2, Phase 3") == 3       # combined → the max
    assert phase_ordinal("Phase 1, Phase 2") == 2
    assert phase_ordinal("N/A") is None
    assert phase_ordinal("None") is None
    assert phase_ordinal(None) is None
    assert phase_ordinal("") is None


# ── phase_transition ──────────────────────────────────────────────────────────

def _drug_row(trials):
    return {"drug_id": "drug-1", "trials": trials}


def test_phase_transition_emits_consecutive_upward_steps():
    facts = PhaseTransitionEmitter().row_to_facts(_drug_row([
        {"id": "NCT1", "phase": "Phase 1", "status": "COMPLETED",
         "start_date": "2018-01-01", "source_api": "clinical_trials_gov"},
        {"id": "NCT2", "phase": "Phase 2", "status": "COMPLETED",
         "start_date": "2020-01-01"},
        {"id": "NCT3", "phase": "Phase 3", "status": "RECRUITING",
         "start_date": "2022-01-01", "official_title": "A Phase 3 study"},
    ]))
    transitions = [f for f in facts if f.predicate == "phase_transition"]
    # 1→2 and 2→3
    assert {(f.object_value["from_phase"], f.object_value["to_phase"])
            for f in transitions} == {(1, 2), (2, 3)}
    f23 = next(f for f in transitions
               if f.object_value["to_phase"] == 3)
    assert f23.subject_entity_type == "drug"
    assert f23.subject_entity_id == "drug-1"
    assert f23.fact_class == "corporate"
    assert f23.source_row_id == "drug-1:to_phase_3"        # synthetic, stable
    assert f23.valid_from is not None                       # earliest phase-3 start
    assert f23.valid_from.year == 2022
    assert route_predicate_to_domain("phase_transition") == "pipeline_and_macro"


def test_phase_transition_skips_phase_with_no_lower_phase_observed():
    # only Phase 4 trials → no observed *transition*; approval handles this case
    facts = PhaseTransitionEmitter().row_to_facts(_drug_row([
        {"id": "NCT9", "phase": "Phase 4", "status": "COMPLETED",
         "start_date": "2021-01-01"},
    ]))
    assert [f for f in facts if f.predicate == "phase_transition"] == []


def test_phase_transition_uses_earliest_start_per_phase():
    facts = PhaseTransitionEmitter().row_to_facts(_drug_row([
        {"id": "A", "phase": "Phase 1", "status": "COMPLETED",
         "start_date": "2015-06-01"},
        {"id": "B", "phase": "Phase 2", "status": "COMPLETED",
         "start_date": "2019-01-01"},
        {"id": "C", "phase": "Phase 2", "status": "COMPLETED",
         "start_date": "2017-01-01"},   # earlier phase-2 trial
    ]))
    f = next(f for f in facts if f.predicate == "phase_transition"
             and f.object_value["to_phase"] == 2)
    assert f.valid_from.year == 2017


# ── approval_event ────────────────────────────────────────────────────────────

def test_approval_event_emitted_for_phase4_and_is_inferred():
    facts = PhaseTransitionEmitter().row_to_facts(_drug_row([
        {"id": "NCT4a", "phase": "Phase 4", "status": "COMPLETED",
         "start_date": "2019-01-01"},
        {"id": "NCT4b", "phase": "Phase 4", "status": "RECRUITING",
         "start_date": "2021-01-01"},
    ]))
    approvals = [f for f in facts if f.predicate == "approval_event"]
    assert len(approvals) == 1
    a = approvals[0]
    assert a.fact_class == "inferred"             # phase-4→approved is an inference
    assert a.confidence == 0.7
    assert a.object_value["phase4_trials"] == 2
    assert a.source_row_id == "drug-1:approval"
    assert a.valid_from.year == 2019              # earliest phase-4 start
    assert route_predicate_to_domain("approval_event") == "pipeline_and_macro"


def test_no_approval_event_without_phase4():
    facts = PhaseTransitionEmitter().row_to_facts(_drug_row([
        {"id": "NCT1", "phase": "Phase 3", "status": "COMPLETED",
         "start_date": "2020-01-01"},
    ]))
    assert [f for f in facts if f.predicate == "approval_event"] == []


# ── discontinuation ───────────────────────────────────────────────────────────

def test_discontinuation_per_terminated_trial_with_reason():
    facts = PhaseTransitionEmitter().row_to_facts(_drug_row([
        {"id": "NCT-T", "phase": "Phase 2", "status": "TERMINATED",
         "start_date": "2020-01-01", "completion_date": "2021-06-01",
         "failure_reason": "Lack of efficacy", "conditions": ["Obesity"],
         "source_api": "clinical_trials_gov",
         "source_url": "https://clinicaltrials.gov/study/NCT-T"},
        {"id": "NCT-OK", "phase": "Phase 3", "status": "COMPLETED",
         "start_date": "2021-01-01"},
    ]))
    disc = [f for f in facts if f.predicate == "discontinuation"]
    assert len(disc) == 1                          # only the terminated trial
    d = disc[0]
    assert d.subject_entity_id == "drug-1"
    assert d.source_row_id == "NCT-T"              # idempotency key = trial id
    assert d.fact_class == "corporate"             # registry status is ground truth
    assert d.object_value["status"] == "TERMINATED"
    assert d.object_value["failure_reason"] == "Lack of efficacy"
    assert "Lack of efficacy" in d.evidence_text
    assert d.valid_from.year == 2021               # completion date
    assert route_predicate_to_domain("discontinuation") == "pipeline_and_macro"


def test_discontinuation_covers_withdrawn_and_suspended():
    facts = PhaseTransitionEmitter().row_to_facts(_drug_row([
        {"id": "W", "phase": "Phase 1", "status": "WITHDRAWN",
         "start_date": "2020-01-01"},
        {"id": "S", "phase": "Phase 2", "status": "SUSPENDED",
         "start_date": "2020-01-01"},
    ]))
    statuses = {f.object_value["status"] for f in facts
                if f.predicate == "discontinuation"}
    assert statuses == {"WITHDRAWN", "SUSPENDED"}


# ── guards ────────────────────────────────────────────────────────────────────

def test_row_to_facts_skips_drug_with_no_trials_or_id():
    em = PhaseTransitionEmitter()
    assert em.row_to_facts({"drug_id": None, "trials": [{"id": "x"}]}) == []
    assert em.row_to_facts({"drug_id": "d", "trials": []}) == []


def test_l2_emitter_registered():
    from services.fact_emitters.base import get_emitters
    assert "phase_transitions" in get_emitters()
