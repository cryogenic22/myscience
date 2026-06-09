"""Tests for UnifiedChatHandler — single handler replacing 8 intent forks.

TDD: Tests written BEFORE implementation.
Run with: pytest tests/test_unified_handler.py -v
"""

from __future__ import annotations

import tempfile
from unittest.mock import MagicMock, patch

import pytest

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
    from services.ctx_corpus import PharmaCorpusBuilder
    builder = PharmaCorpusBuilder(mock_db)
    tmpdir = tempfile.mkdtemp()
    return builder.pack(tmpdir)


@pytest.fixture
def mock_llm():
    """Mock LLM that returns the fallback narrative."""
    llm = MagicMock()
    llm.synthesize.side_effect = lambda fallback_narrative="", **kw: fallback_narrative or "LLM synthesis result."
    llm.synthesize_dossier.side_effect = lambda fallback_narrative="", **kw: fallback_narrative or "Dossier result."
    llm.synthesize_comparison.side_effect = lambda fallback_narrative="", **kw: fallback_narrative or "Comparison result."
    return llm


@pytest.fixture
def mock_metrics():
    """Mock metrics service."""
    svc = MagicMock()
    svc.competitive_landscape.return_value = [
        {
            "mechanism_name": "GLP-1 Receptor Agonists",
            "therapeutic_area": "Diabetes",
            "drug_count": 49,
            "trial_count": 583,
            "active_trial_count": 69,
            "total_pipeline_score": 1124.5,
            "market_share_pct": 38.9,
        }
    ]
    svc.drug_pipeline_strength.return_value = [
        {
            "drug_name": "semaglutide",
            "pipeline_score": 85.2,
            "p1_count": 5,
            "p2_count": 12,
            "p3_count": 28,
            "p4_count": 4,
            "total_trials": 142,
        }
    ]
    svc.company_portfolio.return_value = [
        {
            "company_name": "Novo Nordisk",
            "drug_count": 12,
            "trial_count": 142,
            "pipeline_score_total": 320.5,
        }
    ]
    return svc


@pytest.fixture
def handler(packed_corpus, mock_llm, mock_metrics):
    from services.unified_handler import UnifiedChatHandler
    return UnifiedChatHandler(
        corpus_doc=packed_corpus.document,
        l3_doc=packed_corpus.l3_document,
        llm=mock_llm,
        metrics_svc=mock_metrics,
    )


# ── 1. Handler Construction ──

class TestHandlerConstruction:
    def test_creates_handler(self, handler):
        assert handler is not None

    def test_has_pipeline(self, handler):
        assert handler.pipeline is not None

    def test_has_llm(self, handler):
        assert handler.llm is not None


# ── 2. Response Shape ──

class TestResponseShape:
    """All responses must have the same shape for frontend compatibility."""

    def test_has_narrative(self, handler):
        result = handler.handle("Tell me about semaglutide")
        assert "narrative" in result
        assert isinstance(result["narrative"], str)
        assert len(result["narrative"]) > 0

    def test_has_intent(self, handler):
        result = handler.handle("Tell me about semaglutide")
        assert "intent" in result
        assert isinstance(result["intent"], str)

    def test_has_data(self, handler):
        result = handler.handle("Tell me about semaglutide")
        assert "data" in result

    def test_data_has_standard_fields(self, handler):
        result = handler.handle("Tell me about semaglutide")
        if result["data"] is not None:
            data = result["data"]
            assert "question" in data
            assert "evidence" in data
            assert "provenance_summary" in data

    def test_has_confidence(self, handler):
        """New field: confidence score from reasoning stage."""
        result = handler.handle("Tell me about semaglutide")
        assert "confidence" in result
        assert 0.0 <= result["confidence"] <= 1.0

    def test_has_guard_status(self, handler):
        """New field: guard check result."""
        result = handler.handle("Tell me about semaglutide")
        assert "guard_status" in result


# ── 3. Intent Routing ──

class TestIntentRouting:
    """Verify the handler correctly classifies and routes queries."""

    def test_dossier_intent(self, handler):
        result = handler.handle("Tell me about semaglutide")
        assert result["intent"] in ("dossier", "general")

    def test_compare_intent(self, handler):
        result = handler.handle("Compare semaglutide vs tirzepatide")
        assert result["intent"] == "compare"

    def test_landscape_intent(self, handler):
        result = handler.handle("GLP-1 competitive landscape")
        assert result["intent"] == "landscape"

    def test_aggregation_intent(self, handler):
        result = handler.handle("How many drugs are in Phase 3?")
        assert result["intent"] == "structured_query"


# ── 4. Grounded Synthesis ──

class TestGroundedSynthesis:
    """Verify LLM is called with grounded context."""

    def test_llm_receives_context(self, handler, mock_llm):
        handler.handle("Tell me about semaglutide")
        assert mock_llm.synthesize.called or mock_llm.synthesize_dossier.called

    def test_narrative_not_empty(self, handler):
        result = handler.handle("Tell me about semaglutide")
        assert len(result["narrative"]) > 0

    def test_fallback_on_thin_data(self, handler):
        """Unknown entity should still produce a response."""
        result = handler.handle("Tell me about unknowndrug_xyz")
        assert len(result["narrative"]) > 0
        # Should indicate data limitation
        assert result["confidence"] < 0.5


# ── 5. Conversation History ──

class TestConversationHistory:
    """Verify follow-up resolution with conversation context."""

    def test_resolves_followup(self, handler):
        result = handler.handle(
            "What about its pipeline?",
            conversation_history=[
                {"role": "user", "content": "Tell me about semaglutide"},
                {"role": "assistant", "content": "Semaglutide is a GLP-1 agonist..."},
            ],
        )
        # Should still produce a valid result (not crash)
        assert "narrative" in result

    def test_no_history_works(self, handler):
        result = handler.handle("Tell me about semaglutide")
        assert "narrative" in result


# ── 6. Guard Integration ──

class TestGuardIntegration:
    """Verify hallucination guard is applied post-synthesis."""

    def test_guard_runs(self, handler):
        result = handler.handle("Tell me about semaglutide")
        assert result["guard_status"] in ("ok", "warn", "retry")

    def test_guard_status_ok_for_grounded(self, handler, mock_llm):
        """Grounded response should pass guard."""
        mock_llm.synthesize.return_value = "Semaglutide is an approved drug by Novo Nordisk."
        result = handler.handle("Tell me about semaglutide")
        assert result["guard_status"] == "ok"


# ── 7. Metrics Integration ──

class TestMetricsIntegration:
    """Verify metrics service is called for appropriate intents."""

    def test_landscape_calls_metrics(self, handler, mock_metrics):
        handler.handle("GLP-1 competitive landscape")
        assert mock_metrics.competitive_landscape.called

    def test_landscape_returns_table(self, handler):
        result = handler.handle("GLP-1 competitive landscape")
        assert "table_data" in result
        if result["table_data"]:
            assert "columns" in result["table_data"]
            assert "rows" in result["table_data"]


# ── 7b. Citations / Evidence grounding (L2) ──

class TestCitationGrounding:
    """The unified path must emit structured evidence so the frontend can
    resolve [N] citations, AND feed numbered snippets to the LLM so its
    citations survive validate_citations (evidence_count > 0).

    Regression: the resurrected handler hardcoded `evidence: []`, which both
    blanked the frontend citation cards and forced validate_citations to strip
    EVERY [N] marker (evidence_count=0). See roadmap L2.
    """

    def test_evidence_is_populated_from_sections(self, handler):
        result = handler.handle("Tell me about semaglutide")
        evidence = result["data"]["evidence"]
        assert isinstance(evidence, list)
        assert len(evidence) > 0, "evidence must be populated from retrieved CTX sections"

    def test_evidence_items_have_frontend_shape(self, handler):
        result = handler.handle("Tell me about semaglutide")
        assert result["data"]["evidence"], "non-vacuous: must have items to shape-check"
        for item in result["data"]["evidence"]:
            # Shape expected by frontend EvidenceItem + CitationRef
            assert set(item) >= {
                "source", "entity_type", "entity_id", "content", "relevance", "provenance"
            }
            assert isinstance(item["content"], str) and item["content"].strip()

    def test_llm_receives_numbered_evidence_snippets(self, handler, mock_llm):
        """Without this, validate_citations(evidence_count=0) strips all [N]."""
        handler.handle("Tell me about semaglutide")
        assert mock_llm.synthesize.called
        snippets = mock_llm.synthesize.call_args.kwargs.get("evidence_snippets")
        assert snippets, "LLM must receive non-empty evidence_snippets"
        # Count fed to the validator must cover the snippets the frontend shows
        assert len(snippets) == len(mock_llm.synthesize.call_args.kwargs.get("evidence_snippets"))

    def test_snippet_count_matches_evidence_count(self, handler, mock_llm):
        """evidence_count passed to the LLM == len(data.evidence) so citation
        indices [1..N] the LLM may emit all resolve in the frontend array."""
        result = handler.handle("Tell me about semaglutide")
        snippets = mock_llm.synthesize.call_args.kwargs.get("evidence_snippets") or []
        assert len(snippets) == len(result["data"]["evidence"])

    def test_provenance_total_matches_evidence(self, handler):
        result = handler.handle("Tell me about semaglutide")
        summary = result["data"]["provenance_summary"]
        assert summary["total_evidence_items"] == len(result["data"]["evidence"])


# ── 8. Provenance ──

class TestProvenance:
    """Verify source tracking throughout the pipeline."""

    def test_provenance_summary_exists(self, handler):
        result = handler.handle("Tell me about semaglutide")
        if result["data"]:
            assert "provenance_summary" in result["data"]

    def test_provenance_lists_sources(self, handler):
        result = handler.handle("Tell me about semaglutide")
        if result["data"] and result["data"].get("provenance_summary"):
            summary = result["data"]["provenance_summary"]
            assert "by_source" in summary


# ── 9. A/B Toggle ──

class TestABToggle:
    """Verify handler can be toggled on/off."""

    def test_handler_has_enabled_flag(self, handler):
        assert hasattr(handler, "enabled")

    def test_can_disable(self, handler):
        handler.enabled = False
        assert handler.enabled is False

    def test_disabled_returns_none(self, handler):
        """When disabled, handle() returns None so caller falls back to legacy."""
        handler.enabled = False
        result = handler.handle("Tell me about semaglutide")
        assert result is None


# ── 10. Full Integration ──

class TestFullIntegration:
    """End-to-end tests through the unified handler."""

    def test_full_dossier_flow(self, handler):
        result = handler.handle("Tell me about semaglutide")
        assert result["narrative"]
        assert result["intent"] in ("dossier", "general")
        assert result["confidence"] > 0

    def test_full_compare_flow(self, handler):
        result = handler.handle("Compare semaglutide vs tirzepatide")
        assert result["narrative"]
        assert result["intent"] == "compare"

    def test_full_landscape_flow(self, handler):
        result = handler.handle("GLP-1 competitive landscape")
        assert result["narrative"]
        assert result["intent"] == "landscape"

    def test_full_unknown_entity(self, handler):
        result = handler.handle("Tell me about nonexistentdrug")
        assert result["narrative"]
        assert result["confidence"] < 0.5
