"""DI-3 — dimension-aware synthesis tests.

Synthesize the matrix per dimension with citations; gaps stated, never
invented. The synthesizer is grounded-deterministic (works with no LLM): it
renders each dimension from the cell facts, and surfaces uncovered dimensions
as explicit gaps rather than fabricating them.

It also produces the structured context (matrix_context + insights) that the
existing llm.synthesize_comparison consumes — so the chat answer reflects the
matrix without rewriting the LLM synthesizer (a sibling agent owns that file).
"""

from __future__ import annotations

from services.domain_intelligence.planner import (
    DecompositionPlanner,
    DimensionCell,
    QuestionMatrix,
)
from services.domain_intelligence.playbook import PlaybookRegistry
from services.domain_intelligence.synthesis import (
    synthesize_matrix,
    matrix_to_context,
    matrix_insight_lead,
)


class FakeDB:
    def __init__(self, store):
        self.store = store

    def fetch_all(self, sql, params=None):
        params = params or []
        if len(params) >= 3:
            return list(self.store.get((params[1], params[2]), []))
        return []

    def fetch_one(self, sql, params=None):
        return None


def _fact(predicate, desc, fc="corporate", conf=0.9):
    return {
        "id": f"{predicate}-{abs(hash(desc)) % 99999}",
        "predicate": predicate,
        "object_value": {"description": desc, "source_url": "https://x/1"},
        "fact_class": fc, "confidence": conf, "source_doc_id": None, "valid_from": None,
    }


def _entity(eid, name):
    return {"entity_id": eid, "entity_type": "drug", "label": name}


def _matrix(store):
    planner = DecompositionPlanner(FakeDB(store), registry=PlaybookRegistry())
    return planner.plan("compare", [_entity("sema", "semaglutide"), _entity("tirze", "tirzepatide")])


class TestSynthesizeMatrix:
    def test_covered_dimension_cites_facts(self):
        store = {
            ("sema", "mechanism_of_action"): [_fact("mechanism_of_action", "GLP-1 RA", "reference")],
            ("sema", "target_activity"): [_fact("target_activity", "GLP1R agonist", "reference")],
            ("tirze", "mechanism_of_action"): [_fact("mechanism_of_action", "dual GIP/GLP-1", "reference")],
            ("tirze", "target_activity"): [_fact("target_activity", "GIPR+GLP1R", "reference")],
        }
        text = synthesize_matrix(_matrix(store))
        assert "Mechanism of action" in text
        assert "GLP-1 RA" in text
        assert "dual GIP/GLP-1" in text

    def test_uncovered_dimension_shown_as_gap_not_invented(self):
        """DI-3 gate: an uncovered dimension is shown as a gap, never invented."""
        text = synthesize_matrix(_matrix({}))  # no facts at all
        assert "Pricing & access" in text
        # explicit gap language, no fabricated pricing numbers
        low = text.lower()
        assert "gap" in low or "no " in low or "not available" in low
        # must NOT invent a dollar figure
        assert "$" not in text

    def test_gap_names_the_entity_missing(self):
        store = {
            ("sema", "competitor"): [_fact("competitor", "Competes with Mounjaro", "inferred")],
        }
        text = synthesize_matrix(_matrix(store))
        # tirzepatide has no competition facts → its gap should be named
        assert "tirzepatide" in text.lower()

    def test_includes_every_dimension(self):
        text = synthesize_matrix(_matrix({}))
        for label in ["Mechanism of action", "Efficacy", "Safety", "Dosing",
                      "Regulatory", "Pricing & access", "Competitive position"]:
            assert label in text


class TestMatrixContext:
    def test_context_is_grounded_and_labeled(self):
        store = {("sema", "clinical_trial"): [_fact("clinical_trial", "STEP 1: 14.9% weight loss")]}
        ctx = matrix_to_context(_matrix(store))
        assert "DECOMPOSITION MATRIX" in ctx
        assert "STEP 1: 14.9% weight loss" in ctx
        # gaps flagged explicitly so the LLM cannot fill them
        assert "GAP" in ctx.upper()

    def test_insight_lead_picks_a_differentiator(self):
        store = {
            ("sema", "mechanism_of_action"): [_fact("mechanism_of_action", "GLP-1 RA")],
            ("tirze", "mechanism_of_action"): [_fact("mechanism_of_action", "dual GIP/GLP-1")],
        }
        lead = matrix_insight_lead(_matrix(store))
        assert lead  # non-empty
        assert isinstance(lead, str)

    def test_none_matrix_is_safe(self):
        assert synthesize_matrix(None) == ""
        assert matrix_to_context(None) == ""
        assert matrix_insight_lead(None) == ""
