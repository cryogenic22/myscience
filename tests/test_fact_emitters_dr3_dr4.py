"""DR-3/DR-4 — tests for the adverse-event + drug-label emitters.

Pure mapping (row_to_facts, build_claim, clean_indication) needs no DB. Routing
is asserted against the real dossier predicate router so the facts actually land
in a domain. See tests/test_fact_emitters.py for the shared conventions.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from services.fact_emitters.adverse_events import (
    AdverseEventEmitter,
    build_claim,
    is_non_adr_term,
)
from services.fact_emitters.drug_labels import (
    DrugLabelEmitter,
    clean_indication,
)
from services.fact_emitters.base import get_emitters
from services.dossier_kb import route_predicate_to_domain


# ── DR-3: adverse events ───────────────────────────────────────────

def _ae(**over):
    row = {
        "drug_id": "drug-sema",
        "reaction": "Nausea",
        "report_count": 12,
        "serious_count": 8,
        "fatal_count": 1,
        "drug_name": "Ozempic",
        "source_api": "fda_faers",
        "source_url": "https://fda.gov/faers",
    }
    row.update(over)
    return row


class TestAdverseEventMapping:
    def test_build_claim_with_serious_and_fatal(self):
        assert build_claim("Nausea", 12, 8, 1) == "Nausea — 12 reports (8 serious, 1 fatal)"

    def test_build_claim_singular_and_no_extras(self):
        assert build_claim("Rash", 1, 0, 0) == "Rash — 1 report"

    def test_row_to_facts_emits_signal_class_safety_fact(self):
        f = AdverseEventEmitter().row_to_facts(_ae())[0]
        assert f.predicate == "adverse_event"
        assert f.fact_class == "signal"
        assert f.subject_entity_id == "drug-sema"
        assert f.source_row_id == "drug-sema:nausea"
        assert f.object_value["report_count"] == 12
        assert "Nausea" in f.object_value["description"]
        assert f.evidence_text

    def test_confidence_scales_with_reports_and_caps(self):
        low = AdverseEventEmitter().row_to_facts(_ae(report_count=2))[0]
        high = AdverseEventEmitter().row_to_facts(_ae(report_count=999))[0]
        assert low.confidence < high.confidence
        assert high.confidence <= 0.85

    def test_no_drug_or_reaction_emits_nothing(self):
        assert AdverseEventEmitter().row_to_facts(_ae(drug_id=None)) == []
        assert AdverseEventEmitter().row_to_facts(_ae(reaction="")) == []

    def test_routes_to_clinical_profile(self):
        assert route_predicate_to_domain("adverse_event") == "clinical_profile"


class TestAdverseEventDiscipline:
    """FAERS hygiene: medication-error / lack-of-efficacy MedDRA terms are NOT
    adverse drug reactions and must not surface as safety facts (the regression
    flagged in docs/raw_notes.md + eval PV-01). Real ADRs still pass."""

    # All confirmed present in prod for tirzepatide/semaglutide (read-only probe).
    MED_ERROR_TERMS = [
        "Incorrect dose administered",
        "Extra dose administered",
        "Increased dose administered",
        "Product dose omission issue",
        "Drug dose omission by device",
        "Intentional dose omission",
        "Off label use",
        "Product use in unapproved indication",
        "Accidental overdose",
        "Product dispensing error",
        "Intercepted product dispensing error",
        "Wrong technique in product usage process",
        "Wrong product administered",
        "Wrong patient received product",
        "Medication error",
        "Circumstance or information capable of leading to medication error",
        "Drug ineffective",
        "Drug ineffective for unapproved indication",
    ]

    REAL_ADRS = [
        "Nausea",
        "Diarrhoea",
        "Optic ischaemic neuropathy",
        "Pancreatitis acute",
        "Injection site reaction",
        "Cholelithiasis",
        "Hyperferritinaemia",
    ]

    def test_classifier_flags_medication_errors(self):
        for t in self.MED_ERROR_TERMS:
            assert is_non_adr_term(t), f"should flag non-ADR: {t!r}"

    def test_classifier_passes_real_adrs(self):
        for t in self.REAL_ADRS:
            assert not is_non_adr_term(t), f"should NOT flag real ADR: {t!r}"

    def test_classifier_is_case_insensitive(self):
        assert is_non_adr_term("DRUG INEFFECTIVE")
        assert is_non_adr_term("  incorrect dose administered  ")

    def test_emitter_drops_medication_error_reactions(self):
        em = AdverseEventEmitter()
        for t in self.MED_ERROR_TERMS:
            assert em.row_to_facts(_ae(reaction=t)) == [], f"emitted non-ADR: {t!r}"

    def test_emitter_keeps_real_adrs(self):
        em = AdverseEventEmitter()
        for t in self.REAL_ADRS:
            assert len(em.row_to_facts(_ae(reaction=t))) == 1, f"dropped ADR: {t!r}"

    def test_safety_fact_carries_spontaneous_reporting_caveat(self):
        f = AdverseEventEmitter().row_to_facts(_ae())[0]
        assert f.object_value.get("reporting_caveat")
        assert "spontaneous" in (f.evidence_text or "").lower()

    def test_retraction_extracts_reaction_from_stored_fact(self):
        from scripts.retract_non_adr_faers_facts import extract_reaction
        assert extract_reaction({"reaction": "Incorrect dose administered"}) == \
            "Incorrect dose administered"
        # falls back to description head when reaction key absent
        assert extract_reaction(
            {"description": "Drug ineffective — 49 reports"}) == "Drug ineffective"
        assert extract_reaction({}) == ""


# ── DR-4: drug labels ──────────────────────────────────────────────

def _label(**over):
    row = {
        "id": "label-1",
        "drug_id": "drug-sema",
        "drug_name": "Ozempic",
        "indications": "1 INDICATIONS AND USAGE OZEMPIC is indicated as an adjunct to diet to improve glycemic control in adults with type 2 diabetes",
        "boxed_warning": "WARNING: RISK OF THYROID C-CELL TUMORS",
        "manufacturer": "Novo Nordisk",
        "effective_date": date(2025, 10, 14),
        "source_api": "fda_spl",
        "source_url": "https://dailymed.nlm.nih.gov/x",
    }
    row.update(over)
    return row


class TestDrugLabelMapping:
    def test_clean_indication_strips_section_boilerplate(self):
        out = clean_indication("1 INDICATIONS AND USAGE OZEMPIC is indicated for type 2 diabetes")
        assert out == "OZEMPIC is indicated for type 2 diabetes"

    def test_clean_indication_handles_none(self):
        assert clean_indication(None) == ""

    def test_emits_indication_and_boxed_warning_facts(self):
        facts = DrugLabelEmitter().row_to_facts(_label())
        preds = {f.predicate for f in facts}
        assert preds == {"label_indication", "safety_signal"}
        ind = next(f for f in facts if f.predicate == "label_indication")
        assert ind.fact_class == "corporate"
        assert ind.source_row_id == "label-1:indication"
        assert not ind.object_value["description"].startswith("1 INDICATIONS")
        assert ind.valid_from == datetime(2025, 10, 14, tzinfo=timezone.utc)
        boxed = next(f for f in facts if f.predicate == "safety_signal")
        assert boxed.source_row_id == "label-1:boxed"
        assert boxed.object_value["description"].startswith("Boxed warning:")

    def test_label_without_indication_or_boxed_emits_nothing(self):
        assert DrugLabelEmitter().row_to_facts(
            _label(indications=None, boxed_warning=None)) == []

    def test_indication_only_when_no_boxed(self):
        facts = DrugLabelEmitter().row_to_facts(_label(boxed_warning=None))
        assert len(facts) == 1
        assert facts[0].predicate == "label_indication"

    def test_routes_to_clinical_profile(self):
        assert route_predicate_to_domain("label_indication") == "clinical_profile"
        assert route_predicate_to_domain("safety_signal") == "clinical_profile"


class TestRegistry:
    def test_all_three_emitters_registered(self):
        names = set(get_emitters())
        assert {"clinical_trials", "adverse_events", "drug_labels"} <= names
