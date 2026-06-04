"""L6 — competition fact emitter tests (pure row_to_facts + routing)."""
from __future__ import annotations

from services.fact_emitters.competition import CompetitionEmitter


def _row(**kw):
    base = {
        "link_id": "lnk-1", "drug_id": "d-sema", "competitor_id": "d-tirz",
        "competitor_name": "tirzepatide", "subject_name": "semaglutide",
        "confidence": 0.8, "provenance_source": "cross_linker",
    }
    base.update(kw)
    return base


class TestCompetitionEmitter:
    def test_emits_one_competitor_fact(self):
        facts = CompetitionEmitter().row_to_facts(_row())
        assert len(facts) == 1
        f = facts[0]
        assert f.predicate == "competitor"
        assert f.subject_entity_type == "drug"
        assert f.subject_entity_id == "d-sema"
        assert f.object_value["competitor"] == "tirzepatide"
        assert f.object_value["competitor_id"] == "d-tirz"
        assert "tirzepatide" in f.object_value["description"]
        assert f.source_row_id == "lnk-1"        # idempotency key
        assert f.fact_class == "inferred"

    def test_skips_junk_competitor(self):
        # Placebo / arm rows must not become rivals.
        assert CompetitionEmitter().row_to_facts(_row(competitor_name="Placebo")) == []

    def test_skips_when_name_missing(self):
        assert CompetitionEmitter().row_to_facts(_row(competitor_name="")) == []

    def test_confidence_clamped(self):
        hi = CompetitionEmitter().row_to_facts(_row(confidence=2.0))[0]
        lo = CompetitionEmitter().row_to_facts(_row(confidence=0.0))[0]
        assert hi.confidence <= 0.95
        assert lo.confidence >= 0.3

    def test_confidence_defaults_when_missing(self):
        f = CompetitionEmitter().row_to_facts(_row(confidence=None))[0]
        assert 0.3 <= f.confidence <= 0.95

    def test_predicate_routes_to_competitive_domain(self):
        from services.dossier_kb import route_predicate_to_domain
        assert route_predicate_to_domain("competitor") == "competitive"

    def test_predicate_maps_to_kbq2(self):
        from services.kbq_views import _PREDICATE_KBQ
        assert _PREDICATE_KBQ["competitor"] == 2

    def test_registered_in_get_emitters(self):
        from services.fact_emitters.base import get_emitters
        assert "competition" in get_emitters()
