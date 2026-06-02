"""DR-6 — mechanism / target fact emitters (ChEMBL/MeSH → ledger).

Pure-function tests on ``row_to_facts`` + domain routing. No DB.
"""
from __future__ import annotations

from services.dossier_kb import route_predicate_to_domain
from services.fact_emitters.mechanisms import (
    BioactivityEmitter,
    MechanismEmitter,
    build_activity_claim,
    build_mechanism_claim,
)


# ── MechanismEmitter ────────────────────────────────────────────────────────

def test_mechanism_claim_combines_name_and_class():
    row = {"mechanism_name": "Glucagon-Like Peptide-1 Receptor Agonists",
           "mechanism_class": "incretin_mimetic"}
    assert build_mechanism_claim(row) == (
        "Glucagon-Like Peptide-1 Receptor Agonists (incretin_mimetic)"
    )


def test_mechanism_claim_omits_redundant_class():
    # class already implied by the name → don't append it
    row = {"mechanism_name": "Appetite Depressants",
           "mechanism_class": "Appetite Depressants"}
    assert build_mechanism_claim(row) == "Appetite Depressants"


def test_mechanism_row_to_fact_is_reference_class_and_routes_clinical():
    fact = MechanismEmitter().row_to_facts({
        "drug_id": "drug-1",
        "mechanism_id": "mech-7",
        "mechanism_name": "Sodium-Glucose Transporter 2 Inhibitors",
        "mechanism_class": "sglt2_inhibitor",
        "mesh_id": "D000077203",
        "scope_note": "Agents that inhibit SGLT2 in the kidney.",
        "source_api": "mesh_ontology",
        "source_url": "https://id.nlm.nih.gov/mesh/D000077203.json",
    })[0]
    assert fact.predicate == "mechanism_of_action"
    assert fact.subject_entity_type == "drug"
    assert fact.subject_entity_id == "drug-1"
    assert fact.source_row_id == "mech-7"          # idempotency key = mechanism id
    assert fact.fact_class == "reference"          # curated MeSH, not corporate
    assert fact.confidence == 0.9
    assert fact.evidence_text == "Agents that inhibit SGLT2 in the kidney."
    assert route_predicate_to_domain(fact.predicate) == "clinical_profile"
    assert fact.object_value["mechanism_class"] == "sglt2_inhibitor"


def test_mechanism_falls_back_to_claim_when_no_scope_note():
    fact = MechanismEmitter().row_to_facts({
        "drug_id": "drug-1", "mechanism_id": "mech-1",
        "mechanism_name": "DPP-4 Inhibitors", "mechanism_class": "dpp4",
        "scope_note": None,
    })[0]
    assert fact.evidence_text == "DPP-4 Inhibitors (dpp4)"


def test_mechanism_skips_rows_missing_ids():
    em = MechanismEmitter()
    assert em.row_to_facts({"drug_id": None, "mechanism_id": "m"}) == []
    assert em.row_to_facts({"drug_id": "d", "mechanism_id": None}) == []


# ── BioactivityEmitter ──────────────────────────────────────────────────────

def test_activity_claim_with_value_pchembl_and_target():
    row = {"activity_type": "IC50", "activity_relation": "=",
           "activity_value": 12.0, "activity_units": "nM",
           "pchembl_value": 7.92, "target_name": "GLP-1 receptor"}
    claim = build_activity_claim(row)
    assert "IC50 = 12 nM" in claim
    assert "pCHEMBL 7.92" in claim
    assert "vs GLP-1 receptor" in claim


def test_activity_claim_without_target_name():
    row = {"activity_type": "Ki", "activity_value": 5.0, "activity_units": "nM",
           "pchembl_value": 8.3, "target_name": None}
    claim = build_activity_claim(row)
    assert "vs" not in claim           # no target → no 'vs' clause
    assert "Ki" in claim and "pCHEMBL 8.3" in claim


def test_bioactivity_row_to_fact_reference_class_routes_clinical():
    fact = BioactivityEmitter().row_to_facts({
        "activity_id": "act-99", "drug_id": "drug-2",
        "activity_type": "EC50", "activity_value": 0.5, "activity_units": "nM",
        "activity_relation": "=", "pchembl_value": 9.3,
        "assay_description": "Agonist activity at human GLP-1R.",
        "target_name": None, "source_api": "chembl",
        "source_url": "https://www.ebi.ac.uk/chembl/",
    })[0]
    assert fact.predicate == "target_activity"
    assert fact.source_row_id == "act-99"
    assert fact.fact_class == "reference"
    assert fact.confidence == 0.8           # fixed, NOT derived from pCHEMBL
    assert fact.evidence_text == "Agonist activity at human GLP-1R."
    assert fact.object_value["pchembl_value"] == 9.3
    assert route_predicate_to_domain(fact.predicate) == "clinical_profile"


def test_bioactivity_skips_rows_missing_ids():
    assert BioactivityEmitter().row_to_facts(
        {"activity_id": None, "drug_id": "d"}) == []


def test_dr6_emitters_registered():
    from services.fact_emitters.base import get_emitters
    names = set(get_emitters().keys())
    assert {"mechanisms", "bioactivities"} <= names
