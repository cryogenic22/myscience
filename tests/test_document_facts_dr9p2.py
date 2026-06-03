"""DR-9 Phase 2 — decks/PDFs -> structured facts. Unit tests (no LLM, no DB).

A fake StructuredCall stands in for the LLM; a fake resolver stands in for the
drug spine.
"""
from __future__ import annotations

from services.dossier_kb import route_predicate_to_domain
from services.fact_emitters.document_facts import (
    build_readout_fact,
    extract_document_facts,
)
from services.extraction.trial_readout import TrialReadoutExtraction


def _readout_dict(**kw):
    base = {
        "trial_identifier": "REDEFINE 4",
        "phase": "Phase 3",
        "drug_name": "CagriSema",
        "sponsor_name": "Novo Nordisk",
        "indication": "obesity",
        "primary_endpoint_met": False,
        "readout_date": "2026-02-23",
        "sample_size": 800,
        "efficacy_outcomes": [
            {"endpoint_name": "weight loss at 84 weeks", "endpoint_type": "primary",
             "met": False, "response_rate_pct": 23.0},
        ],
        "safety_summary": "GI AEs consistent with class.",
        "headline_summary": "CagriSema 23% weight loss; non-inferiority vs tirzepatide not met.",
    }
    base.update(kw)
    return base


def _call_returning(payload):
    def _call(system_prompt, user_prompt, json_schema):
        return payload
    return _call


def _resolver_ok(name):
    return ("drug", "drug-cagrisema")


def _resolver_none(name):
    return None


# ── build_readout_fact (pure mapping) ────────────────────────────────────────

def test_build_readout_fact_shape_and_routing():
    readout = TrialReadoutExtraction.model_validate(_readout_dict())
    fact = build_readout_fact(readout, subject_entity_id="drug-1",
                              source_url="upload://deck.pptx")
    assert fact.predicate == "trial_result"
    assert route_predicate_to_domain(fact.predicate) == "clinical_profile"
    assert fact.fact_class == "corporate"        # company self-reported deck
    assert fact.confidence == 0.7
    assert "not met" in fact.object_value["description"]
    assert fact.object_value["trial_identifier"] == "REDEFINE 4"
    assert fact.object_value["outcomes"][0]["response_rate_pct"] == 23.0
    assert "non-inferiority" in fact.evidence_text
    assert "Safety:" in fact.evidence_text


def test_source_row_id_is_deterministic_for_idempotency():
    readout = TrialReadoutExtraction.model_validate(_readout_dict())
    a = build_readout_fact(readout, subject_entity_id="drug-1")
    b = build_readout_fact(readout, subject_entity_id="drug-1")
    assert a.source_row_id == b.source_row_id
    # different drug -> different key
    c = build_readout_fact(readout, subject_entity_id="drug-2")
    assert c.source_row_id != a.source_row_id


# ── extract_document_facts (LLM + resolver wiring) ───────────────────────────

def test_extract_emits_fact_when_readout_and_resolver_ok():
    facts = extract_document_facts(
        "…deck text…",
        structured_call=_call_returning(_readout_dict()),
        resolver=_resolver_ok,
    )
    assert len(facts) == 1
    assert facts[0].subject_entity_id == "drug-cagrisema"


def test_extract_skips_when_drug_unresolved():
    facts = extract_document_facts(
        "…deck text…",
        structured_call=_call_returning(_readout_dict()),
        resolver=_resolver_none,
    )
    assert facts == []


def test_extract_returns_empty_when_llm_returns_nothing():
    facts = extract_document_facts(
        "a financial slide, not a readout",
        structured_call=_call_returning(None),
        resolver=_resolver_ok,
    )
    assert facts == []


def test_extract_returns_empty_on_blank_text():
    facts = extract_document_facts(
        "   ", structured_call=_call_returning(_readout_dict()),
        resolver=_resolver_ok,
    )
    assert facts == []


def test_extract_is_exception_safe_on_bad_llm_payload():
    # malformed payload fails Pydantic validation inside extract_structured ->
    # None -> [] (never raises)
    facts = extract_document_facts(
        "…", structured_call=_call_returning({"garbage": 1}),
        resolver=_resolver_ok,
    )
    assert facts == []


def test_default_structured_call_none_without_key(monkeypatch):
    """PB-SL06 — no OPENAI_API_KEY → None so the upload route degrades to
    facts_emitted=0 instead of erroring."""
    from services.fact_emitters.document_facts import default_structured_call
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert default_structured_call() is None
