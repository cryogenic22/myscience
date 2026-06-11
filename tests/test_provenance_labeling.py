"""Lane-1: evidence carries a NAMED connector, and that name reaches the LLM.

Eval gate G1 (provenance) sat near 0% because matrix evidence was labelled with
the internal pipeline stage ("plan:mechanism"), and the snippet fed to the LLM was
content-only — the model had no source to attribute to. These tests pin both
halves of the fix: predicate→connector naming, and the [source:] marker in the
snippet text.
"""

from services.unified_handler import (
    _PREDICATE_SOURCE,
    _display_source,
    _provenance_footer,
    UnifiedChatHandler,
)


def test_display_source_maps_predicate_to_named_connector():
    assert _display_source(None, "clinical_trial") == "ClinicalTrials.gov"
    assert _display_source(None, "adverse_event") == "openFDA FAERS"
    assert _display_source(None, "mechanism_of_action") == "MeSH / curated mechanism"
    assert _display_source(None, "label_indication") == "openFDA Drug Labels"


def test_display_source_never_returns_internal_plan_label():
    # The internal stage name is not a source the reader can attribute to.
    assert _display_source("plan:mechanism", None) == "platform data"
    assert _display_source("plan", "") == "platform data"


def test_display_source_cleans_metrics_label_and_keeps_clean_names():
    assert _display_source("metrics.top_companies_by_topic", None) == "platform metrics"
    assert _display_source("ClinicalTrials.gov", None) == "ClinicalTrials.gov"


def test_matrix_evidence_carries_named_source_not_plan_stage():
    decomposition = {
        "cells": [
            {
                "dimension": "mechanism",
                "entity_id": "drug-1",
                "facts": [
                    {"id": "f1", "claim": "Glucagon-Like Peptide-1 Receptor Agonist",
                     "predicate": "mechanism_of_action", "fact_class": "reference"},
                ],
            },
            {
                "dimension": "clinical_profile",
                "entity_id": "drug-1",
                "facts": [
                    {"id": "f2", "claim": "Phase 3 trial NCT123",
                     "predicate": "clinical_trial", "fact_class": "corporate"},
                ],
            },
        ]
    }
    ev = UnifiedChatHandler._matrix_to_evidence(decomposition)
    sources = [e["source"] for e in ev]
    assert "MeSH / curated mechanism" in sources
    assert "ClinicalTrials.gov" in sources
    # No internal stage label leaks as the source.
    assert not any(s.startswith("plan") for s in sources)
    # The dimension is still recorded in provenance for the frontend.
    assert ev[0]["provenance"]["dimension"] == "mechanism"


def test_provenance_footer_maps_each_citation_to_named_connector():
    """Deterministic provenance: every [N] traces to a named connector + cadence,
    since no LLM narrates this reliably (eval gate G1)."""
    evidence = [
        {"source": "ClinicalTrials.gov", "provenance": {"predicate": "clinical_trial"}},
        {"source": "openFDA FAERS", "provenance": {"predicate": "adverse_event"}},
        {"source": "ClinicalTrials.gov", "provenance": {"predicate": "clinical_trial"}},
    ]
    footer = _provenance_footer(evidence)
    assert "Provenance" in footer
    assert "ClinicalTrials.gov (daily refresh)" in footer
    assert "openFDA FAERS (weekly refresh)" in footer
    # citations 1 & 3 share a source → grouped; 2 is FAERS
    assert "[1],[3] ClinicalTrials.gov" in footer
    assert "[2] openFDA FAERS" in footer
    # honest about coverage being ingest, not the world
    assert "not everything that exists" in footer


def test_provenance_footer_empty_when_no_evidence():
    assert _provenance_footer([]) == ""


def test_predicate_source_map_covers_emitter_predicates():
    # The fact emitters produce these predicates — each must name a connector.
    for p in ["clinical_trial", "adverse_event", "label_indication", "safety_signal",
              "mechanism_of_action", "phase_transition", "market_event"]:
        assert p in _PREDICATE_SOURCE and _PREDICATE_SOURCE[p]
