"""Tests for CTXQueryPipeline — staged retrieve→reason→synthesize pipeline.

TDD: These tests are written BEFORE the implementation.
Run with: pytest tests/test_ctx_pipeline.py -v
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Reuse mock data from corpus tests
from tests.test_ctx_corpus import MOCK_DRUGS, MOCK_COMPANIES, MOCK_TRIALS, MOCK_MECHANISMS, MockDB


# ── Fixtures ──

@pytest.fixture
def mock_db():
    db = MockDB()
    db.set_results("drugs", MOCK_DRUGS)
    db.set_results("companies", MOCK_COMPANIES)
    db.set_results("clinical_trials", MOCK_TRIALS)
    db.set_results("mechanisms", MOCK_MECHANISMS)
    return db


@pytest.fixture
def packed_corpus(mock_db):
    """Build a packed CTX corpus from mock data."""
    from services.ctx_corpus import PharmaCorpusBuilder
    builder = PharmaCorpusBuilder(mock_db)
    tmpdir = tempfile.mkdtemp()
    result = builder.pack(tmpdir)
    return result


@pytest.fixture
def pipeline(packed_corpus):
    """Create a CTXQueryPipeline with packed corpus."""
    from services.ctx_pipeline import CTXQueryPipeline
    return CTXQueryPipeline(
        corpus_doc=packed_corpus.document,
        l3_doc=packed_corpus.l3_document,
    )


# ── 1. Pipeline Construction ──

class TestPipelineConstruction:
    """Verify pipeline initializes all components."""

    def test_creates_pipeline(self, pipeline):
        assert pipeline is not None

    def test_has_keyword_index(self, pipeline):
        assert pipeline.keyword_index is not None

    def test_has_entity_graph(self, pipeline):
        assert pipeline.entity_graph is not None

    def test_has_guard(self, pipeline):
        assert pipeline.guard is not None

    def test_has_section_list(self, pipeline):
        """Pipeline should know available sections for routing."""
        sections = pipeline.available_sections
        assert isinstance(sections, list)
        assert len(sections) > 0


# ── 2. Understand Stage ──

class TestUnderstandStage:
    """Verify question understanding: entity detection, classification."""

    def test_detects_drug_entity(self, pipeline):
        plan = pipeline.understand("Tell me about semaglutide")
        assert len(plan.entities_detected) > 0
        assert any("semaglutide" in e.lower() for e in plan.entities_detected)

    def test_detects_company_entity(self, pipeline):
        plan = pipeline.understand("Novo Nordisk portfolio")
        assert len(plan.entities_detected) > 0

    def test_classifies_comparison(self, pipeline):
        plan = pipeline.understand("Compare semaglutide vs tirzepatide")
        assert plan.intent == "compare"
        assert len(plan.entities_detected) >= 2

    def test_classifies_landscape(self, pipeline):
        plan = pipeline.understand("GLP-1 competitive landscape")
        assert plan.intent == "landscape"

    def test_classifies_aggregation(self, pipeline):
        plan = pipeline.understand("How many drugs are in Phase 3?")
        assert plan.intent == "structured_query"


class TestTrustRouting:
    """Category/'who-leads' queries must route to a metric-backed intent so the
    grounded landscape/pipeline metrics fire — instead of falling to 'general'
    and hallucinating (the 'Medtronic dominates diabetes' failure).
    """

    @pytest.mark.parametrize("q", [
        "Which companies dominate the diabetes drugs space?",
        "Who are the leaders in obesity drugs?",
        "What companies make GLP-1 drugs?",
        "Which firms are the biggest players in oncology?",
    ])
    def test_company_leader_queries_route_to_landscape(self, pipeline, q):
        assert pipeline.understand(q).intent == "landscape"

    def test_phase_query_routes_to_pipeline(self, pipeline):
        assert pipeline.understand("What drugs are in Phase 3 for diabetes?").intent == "pipeline"

    def test_count_phase_query_stays_structured(self, pipeline):
        # Regression: a count question that mentions a phase must NOT become pipeline
        assert pipeline.understand("How many drugs are in Phase 3?").intent == "structured_query"

    def test_dossier_still_dossier(self, pipeline):
        assert pipeline.understand("Tell me about semaglutide").intent == "dossier"

    def test_junk_org_helper_flags_academic_sponsors(self):
        from services.ctx_pipeline import _is_junk_org
        assert _is_junk_org("ENTITY-COMPANY-BAKER-HEART-AND-DIABETES-INSTITUTE")
        assert _is_junk_org("COMPANY-DASMAN-DIABETES-INSTITUTE")
        assert _is_junk_org("University of Colorado, Denver")
        # Real market players must NOT be flagged
        assert not _is_junk_org("COMPANY-NOVO-NORDISK")
        assert not _is_junk_org("ENTITY-DRUG-SEMAGLUTIDE")
        assert not _is_junk_org("Eli Lilly")

    def test_preserves_original_question(self, pipeline):
        plan = pipeline.understand("Tell me about semaglutide")
        assert plan.original_question == "Tell me about semaglutide"

    def test_resolves_coreference(self, pipeline):
        """Coreference with conversation history."""
        plan = pipeline.understand(
            "What about its pipeline?",
            history=[
                {"role": "user", "content": "Tell me about semaglutide"},
                {"role": "assistant", "content": "Semaglutide is a GLP-1 agonist..."},
            ],
        )
        # "its" should resolve to semaglutide
        assert "semaglutide" in plan.resolved_question.lower()

    def test_suggests_sources(self, pipeline):
        """Plan should suggest which data sources to query."""
        plan = pipeline.understand("Tell me about semaglutide")
        assert len(plan.suggested_sources) > 0


# ── 3. Retrieve Stage ──

class TestRetrieveStage:
    """Verify data retrieval via CTX hydration."""

    def test_retrieval_returns_sections(self, pipeline):
        plan = pipeline.understand("Tell me about semaglutide")
        result = pipeline.retrieve(plan)
        assert result.ctx_sections is not None
        assert len(result.ctx_sections) > 0

    def test_retrieval_has_token_count(self, pipeline):
        plan = pipeline.understand("Tell me about semaglutide")
        result = pipeline.retrieve(plan)
        assert result.token_count > 0

    def test_retrieval_under_budget(self, pipeline):
        """Retrieved context should be under 5000 tokens."""
        plan = pipeline.understand("Tell me about semaglutide")
        result = pipeline.retrieve(plan)
        assert result.token_count < 5000, f"Retrieval too large: {result.token_count} tokens"

    def test_retrieval_has_provenance(self, pipeline):
        """Every piece of retrieved data should have source tracking."""
        plan = pipeline.understand("Tell me about semaglutide")
        result = pipeline.retrieve(plan)
        assert len(result.sources_queried) > 0

    def test_retrieval_uses_entity_graph(self, pipeline):
        """Entity graph should expand retrieval to related entities."""
        plan = pipeline.understand("Tell me about semaglutide")
        result = pipeline.retrieve(plan)
        # Should retrieve semaglutide section + potentially related sections
        assert len(result.ctx_sections) >= 1

    def test_retrieval_renders_context_text(self, pipeline):
        """Retrieved data should be renderable as text for LLM."""
        plan = pipeline.understand("Tell me about semaglutide")
        result = pipeline.retrieve(plan)
        text = result.render_context()
        assert isinstance(text, str)
        assert len(text) > 0
        assert "semaglutide" in text.lower()


# ── 4. Reason Stage ──

class TestReasonStage:
    """Verify reasoning: sufficiency, gaps, conflicts."""

    def test_reason_returns_result(self, pipeline):
        plan = pipeline.understand("Tell me about semaglutide")
        retrieval = pipeline.retrieve(plan)
        reasoning = pipeline.reason(plan, retrieval)
        assert reasoning is not None

    def test_sufficient_data(self, pipeline):
        """Known entity should have sufficient data."""
        plan = pipeline.understand("Tell me about semaglutide")
        retrieval = pipeline.retrieve(plan)
        reasoning = pipeline.reason(plan, retrieval)
        assert reasoning.sufficient is True

    def test_insufficient_data_detected(self, pipeline):
        """Unknown entity should flag insufficient data."""
        plan = pipeline.understand("Tell me about unknowndrug_xyz")
        retrieval = pipeline.retrieve(plan)
        reasoning = pipeline.reason(plan, retrieval)
        assert reasoning.sufficient is False
        assert len(reasoning.gaps) > 0

    def test_confidence_score(self, pipeline):
        """Reasoning should produce a confidence score."""
        plan = pipeline.understand("Tell me about semaglutide")
        retrieval = pipeline.retrieve(plan)
        reasoning = pipeline.reason(plan, retrieval)
        assert 0.0 <= reasoning.confidence <= 1.0

    def test_computes_insights_for_comparison(self, pipeline):
        """Compare queries should get pre-computed differentials."""
        plan = pipeline.understand("Compare semaglutide vs tirzepatide")
        retrieval = pipeline.retrieve(plan)
        reasoning = pipeline.reason(plan, retrieval)
        # Should have computed insights (even if basic on mock data)
        assert isinstance(reasoning.computed_insights, list)


# ── 5. Context Guard Integration ──

class TestContextGuard:
    """Verify hallucination detection via ContextGuard."""

    def test_guard_passes_grounded_response(self, pipeline):
        """Response using only provided data should pass guard."""
        guard_result = pipeline.check_response(
            response="Semaglutide is an approved drug made by Novo Nordisk.",
            context="semaglutide approved drug Novo Nordisk",
        )
        assert guard_result.low_confidence is False
        assert guard_result.recommendation == "ok"

    def test_guard_catches_hallucination(self, pipeline):
        """Response with hallucination signals should be flagged."""
        guard_result = pipeline.check_response(
            response="Based on my training data, semaglutide reduces MACE by 26%.",
            context="semaglutide GLP-1 receptor agonist",
        )
        assert guard_result.low_confidence is True
        assert len(guard_result.signals_detected) > 0


# ── 6. Grounding Wrapper ──

class TestGrounding:
    """Verify grounded prompt construction."""

    def test_builds_grounded_system_prompt(self, pipeline):
        """System prompt should include grounding rules."""
        prompt = pipeline.build_system_prompt(intent="dossier")
        assert isinstance(prompt, str)
        assert len(prompt) > 0
        # Should contain grounding instructions
        assert "invent" in prompt.lower() or "grounding" in prompt.lower() or "only" in prompt.lower()

    def test_system_prompt_includes_entity_count(self, pipeline):
        """Grounded prompt should remind LLM of entity count."""
        prompt = pipeline.build_system_prompt(intent="dossier")
        # Should contain a number (entity count) somewhere
        import re
        assert re.search(r'\d+', prompt), "No entity count in system prompt"


# ── 7. Keyword Index ──

class TestKeywordIndex:
    """Verify entity matching via keyword index."""

    def test_keyword_match_drug(self, pipeline):
        """Should match drug names."""
        matches = pipeline.keyword_index.match("semaglutide mechanism")
        assert len(matches) > 0

    def test_keyword_match_returns_section_names(self, pipeline):
        """Matched results should be section names for hydration."""
        matches = pipeline.keyword_index.match("semaglutide")
        for m in matches:
            assert isinstance(m, str)

    def test_keyword_no_false_positives(self, pipeline):
        """Unrelated queries should return empty or minimal matches."""
        matches = pipeline.keyword_index.match("quantum computing")
        # May still match something generic, but shouldn't match drug-specific
        assert len(matches) <= 1


# ── 8. Full Pipeline Integration ──

class TestFullPipeline:
    """End-to-end pipeline: understand → retrieve → reason."""

    def test_full_flow_known_entity(self, pipeline):
        """Full pipeline for a known entity."""
        plan = pipeline.understand("Tell me about semaglutide")
        retrieval = pipeline.retrieve(plan)
        reasoning = pipeline.reason(plan, retrieval)

        assert reasoning.sufficient is True
        assert reasoning.confidence > 0
        assert retrieval.token_count < 5000

    def test_full_flow_comparison(self, pipeline):
        """Full pipeline for a comparison query."""
        plan = pipeline.understand("Compare semaglutide vs tirzepatide")
        retrieval = pipeline.retrieve(plan)
        reasoning = pipeline.reason(plan, retrieval)

        assert plan.intent == "compare"
        assert len(plan.entities_detected) >= 2
        assert retrieval.token_count < 5000

    def test_full_flow_unknown_entity(self, pipeline):
        """Full pipeline for an unknown entity — should detect gaps."""
        plan = pipeline.understand("Tell me about nonexistentdrug")
        retrieval = pipeline.retrieve(plan)
        reasoning = pipeline.reason(plan, retrieval)

        assert reasoning.sufficient is False
        assert reasoning.confidence < 0.5
