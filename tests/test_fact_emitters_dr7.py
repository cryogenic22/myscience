"""DR-7 — literature fact emitter (PubMed → ledger). Pure-function tests."""
from __future__ import annotations

from datetime import date

from services.dossier_kb import route_predicate_to_domain
from services.fact_emitters.literature import (
    LiteratureEmitter,
    build_publication_claim,
    _is_epidemiology,
)


def _row(**kw):
    base = {
        "id": "row-1", "pmid": "12345", "drug_id": "drug-1",
        "title": "Semaglutide and cardiovascular outcomes in obesity",
        "abstract": "A large RCT of semaglutide ...",
        "journal": "NEJM", "publication_date": date(2025, 3, 1),
        "publication_type": "Journal Article", "mesh_terms": ["Obesity", "Humans"],
        "doi": "10.1056/abc", "source_url": None, "source_api": "pubmed",
        "quality_score": 0.7,
    }
    base.update(kw)
    return base


def test_claim_includes_type_journal_year_title():
    claim = build_publication_claim(_row(publication_type="Systematic Review"))
    assert claim == (
        "Systematic Review, NEJM (2025): "
        "Semaglutide and cardiovascular outcomes in obesity"
    )


def test_claim_drops_generic_journal_article_type():
    claim = build_publication_claim(_row())
    assert claim.startswith("NEJM (2025):")     # 'Journal Article' omitted


def test_epidemiology_detection():
    assert _is_epidemiology(["Prevalence", "Obesity"]) is True
    assert _is_epidemiology(["Epidemiologic Studies"]) is True
    assert _is_epidemiology(["Humans", "Obesity"]) is False
    assert _is_epidemiology(None) is False


def test_clinical_publication_routes_clinical_profile():
    fact = LiteratureEmitter().row_to_facts(_row())[0]
    assert fact.predicate == "key_publication"
    assert fact.fact_class == "reference"
    assert fact.source_row_id == "12345"          # pmid is the idempotency key
    assert route_predicate_to_domain(fact.predicate) == "clinical_profile"
    assert fact.evidence_text == "A large RCT of semaglutide ..."


def test_epidemiology_publication_routes_disease_domain():
    fact = LiteratureEmitter().row_to_facts(
        _row(mesh_terms=["Prevalence", "Obesity"]))[0]
    assert fact.predicate == "disease_evidence"
    assert route_predicate_to_domain(fact.predicate) == "disease_and_patient"


def test_high_value_type_boosts_confidence():
    plain = LiteratureEmitter().row_to_facts(_row(quality_score=0.7))[0]
    review = LiteratureEmitter().row_to_facts(
        _row(quality_score=0.7, publication_type="Systematic Review"))[0]
    assert review.confidence > plain.confidence
    assert review.confidence <= 1.0


def test_source_url_falls_back_to_doi():
    fact = LiteratureEmitter().row_to_facts(_row(source_url=None, doi="10.1/xy"))[0]
    assert fact.object_value["source_url"] == "https://doi.org/10.1/xy"


def test_skips_rows_without_title_or_drug():
    em = LiteratureEmitter()
    assert em.row_to_facts(_row(title="")) == []
    assert em.row_to_facts(_row(drug_id=None)) == []


def test_dr7_emitter_registered():
    from services.fact_emitters.base import get_emitters
    assert "literature" in get_emitters()
