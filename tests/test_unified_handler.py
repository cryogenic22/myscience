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
        assert all(isinstance(s, str) and s.strip() for s in snippets)

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


# ── 7c. Topic resolution + leaders evidence (trust routing) ──

class TestTopicAndLeaders:
    def test_mechanism_alias_resolves(self, handler):
        from services.ctx_pipeline import QueryPlan
        p = QueryPlan(original_question="What companies make GLP-1 drugs?",
                      resolved_question="", entities_detected=["glp 1"])
        assert handler._resolve_topic(p) == "Glucagon-Like Peptide"

    def test_topic_falls_back_to_entity(self, handler):
        from services.ctx_pipeline import QueryPlan
        p = QueryPlan(original_question="Tell me about semaglutide",
                      resolved_question="", entities_detected=["semaglutide"])
        # No mechanism alias / area term → first entity
        assert handler._resolve_topic(p) == "semaglutide"

    def test_leaders_become_citable_evidence(self, handler):
        leaders = [
            {"company_name": "Novo Nordisk", "drug_count": 68, "trial_count": 708},
            {"company_name": "Eli Lilly", "drug_count": 33, "trial_count": 200},
        ]
        ev = handler._leaders_as_evidence(leaders)
        assert len(ev) == 2
        assert ev[0]["entity_type"] == "company"
        assert "Novo Nordisk" in ev[0]["content"] and "68 drugs" in ev[0]["content"]
        assert set(ev[0]) >= {"source", "entity_type", "entity_id", "content", "relevance", "provenance"}
        # P5 (G3): the count must NOT be ASSERTED as leadership/dominance — that is
        # the self-inflicted count-fallacy the system then prompts against. (The
        # neutral disclaimer may mention "leadership" only to negate it.)
        c = ev[0]["content"].lower()
        assert "market leader by drug count" not in c
        assert "count of ingested records" in c and "not market share" in c

    def test_company_leaders_question_uses_leaders_prompt(self, handler, mock_llm):
        """'which companies dominate X' must synthesize with the company-centric
        prompt, not the mechanism-centric landscape one."""
        handler.handle("Which companies dominate the diabetes drugs space?")
        assert mock_llm.synthesize.called
        assert mock_llm.synthesize.call_args.kwargs.get("intent") == "leaders"


class _FakeCountDB:
    """Minimal db stub: answers the per-drug trial COUNT with a fixture value."""
    def __init__(self, counts: dict):
        self.counts = counts

    def fetch_one(self, sql, params=None):
        key = (params or [None])[0]
        return {"n": self.counts.get(key, 0)}


class TestTrialTotalEvidence:
    """Chat #16: surface the REAL per-drug trial total as cited ClinicalTrials.gov
    evidence so a compare states the true figure (and it survives neutralization),
    instead of the model inventing a count that gets stripped."""

    def test_gate_fires_for_trials_and_compares_only(self):
        from services.unified_handler import _wants_trial_totals
        assert _wants_trial_totals("Compare semaglutide vs tirzepatide")
        assert _wants_trial_totals("how many trials does semaglutide have")
        assert _wants_trial_totals("semaglutide pipeline depth")
        # Unrelated questions must NOT get a trial-count line.
        assert not _wants_trial_totals("what is semaglutide's mechanism of action")
        assert not _wants_trial_totals("who makes Ozempic")

    def test_builder_grounds_real_counts_and_attributes_clinicaltrials(self):
        from services.unified_handler import (
            _trial_total_evidence_items, _grounded_count_numbers, _snippet_for_evidence,
        )
        items = _trial_total_evidence_items([
            ("sema-id", "Semaglutide", 224), ("tirz-id", "Tirzepatide", 120),
        ])
        assert len(items) == 2
        # The exact real counts become GROUNDED (aggregate-count context).
        assert {"224", "120"} <= _grounded_count_numbers(items)
        # The LLM-facing snippet attributes the count to ClinicalTrials.gov.
        snip = _snippet_for_evidence(items[0])
        assert "224 clinical trials" in snip and "ClinicalTrials.gov" in snip
        # Frontend/citation shape parity with other evidence builders.
        assert set(items[0]) >= {"source", "entity_type", "entity_id", "content", "relevance", "provenance"}
        # Never fabricate: zero / missing-label rows are dropped.
        assert _trial_total_evidence_items([("x", "", 9), ("y", "Y", 0)]) == []

    def test_real_count_survives_neutralization_only_when_grounded(self):
        """The whole point: with the injected total in evidence the true count is KEPT;
        without it, the same bare count is neutralized as a fabrication."""
        from services.unified_handler import (
            _trial_total_evidence_items, _neutralize_ungrounded_counts,
        )
        narrative = ("Semaglutide is linked to 224 clinical trials; tirzepatide is "
                     "linked to 120 clinical trials.")
        evidence = _trial_total_evidence_items([
            ("sema-id", "Semaglutide", 224), ("tirz-id", "Tirzepatide", 120),
        ])
        kept = _neutralize_ungrounded_counts(narrative, evidence)
        assert "224 clinical trials" in kept and "120 clinical trials" in kept
        # Same narrative, no grounding evidence → both figures neutralized.
        stripped = _neutralize_ungrounded_counts(narrative, [])
        assert "224" not in stripped and "120" not in stripped
        assert "a number of clinical trials" in stripped

    def test_method_injects_drug_counts_respecting_gate_and_filter(self, handler, monkeypatch):
        from services.ctx_pipeline import QueryPlan
        from services.unified_handler import _grounded_count_numbers
        monkeypatch.setattr(handler, "db", _FakeCountDB({"sema": 224, "tirz": 120, "co": 5}))
        monkeypatch.setattr(handler, "_resolve_plan_entities", lambda plan: [
            {"entity_id": "sema", "entity_type": "drug", "label": "Semaglutide"},
            {"entity_id": "tirz", "entity_type": "drug", "label": "Tirzepatide"},
            {"entity_id": "co", "entity_type": "company", "label": "Novo Nordisk"},  # skipped
        ])
        plan = QueryPlan(original_question="Compare semaglutide vs tirzepatide",
                         resolved_question="", entities_detected=[])
        items = handler._trial_total_evidence(plan, "Compare semaglutide vs tirzepatide")
        assert len(items) == 2  # company filtered out
        assert {"224", "120"} <= _grounded_count_numbers(items)
        # Gate: an unrelated question yields nothing even with resolvable drugs.
        assert handler._trial_total_evidence(plan, "what is semaglutide's mechanism") == []
        # Never fabricate: a zero count contributes nothing.
        monkeypatch.setattr(handler, "db", _FakeCountDB({"sema": 0, "tirz": 120}))
        only = handler._trial_total_evidence(plan, "compare them")
        assert len(only) == 1 and "120 clinical trials" in only[0]["content"]


# ── 7d. PLAN stage (Domain Intelligence decomposition) ──

class TestPlanStage:
    def test_no_db_means_no_decomposition(self, handler):
        """Graceful: handler without a db must not crash and must omit/None the
        decomposition (falls back to the legacy retrieve path)."""
        result = handler.handle("Tell me about semaglutide")
        # Frontend-canonical key (CanvasPanel reads `decomposition_matrix`).
        assert result["data"].get("decomposition_matrix") in (None, {}, [])

    def test_decomposition_uses_frontend_canonical_key(self, handler, monkeypatch):
        """The live path must emit `decomposition_matrix` (what CanvasPanel/
        DecompositionMatrix read) — not `decomposition` — or the matrix UI never
        renders for unified-handler answers."""
        decomp = {
            "playbook_id": "compare.drug_x_drug", "intent": "compare",
            "entities": [{"entity_id": "sema", "label": "semaglutide"}],
            "dimensions": [{"key": "mechanism", "label": "Mechanism"}],
            "cells": [{"dimension": "mechanism", "entity_id": "sema",
                       "coverage": "covered", "facts": []}],
            "coverage_summary": {"mechanism": "covered"}, "gaps": [],
        }
        monkeypatch.setattr(handler, "_plan_decomposition", lambda plan: decomp)
        data = handler.handle("Compare semaglutide vs tirzepatide")["data"]
        assert data.get("decomposition_matrix") == decomp
        assert "decomposition" not in data  # no stale duplicate key

    def test_matrix_to_evidence_shape(self, handler):
        decomposition = {
            "cells": [
                {"dimension": "clinical_efficacy", "entity_id": "d1",
                 "facts": [{"id": "f1", "claim": "Phase 3 readout positive",
                            "predicate": "clinical_trial", "fact_class": "outcome"}]},
            ]
        }
        ev = handler._matrix_to_evidence(decomposition)
        assert len(ev) == 1
        assert ev[0]["entity_type"] == "fact"
        assert "Phase 3 readout positive" in ev[0]["content"]
        assert set(ev[0]) >= {"source", "entity_type", "entity_id", "content", "relevance", "provenance"}

    def test_matrix_to_evidence_keeps_all_facts_per_cell(self, handler):
        """Conservation: every grounded fact in a cell (capped at 3) must become
        its own citable evidence item — not just the last one. Each item carries
        its OWN claim/predicate/id (no leak from the last loop iteration). A
        regression here silently starves the synthesis prompt of attributable
        claims (eval gate G1)."""
        decomposition = {
            "cells": [
                {"dimension": "clinical_efficacy", "entity_id": "d1",
                 "facts": [
                     {"id": "f1", "claim": "STEP 1 met primary endpoint",
                      "predicate": "clinical_trial", "fact_class": "outcome"},
                     {"id": "f2", "claim": "GLP-1 receptor agonist",
                      "predicate": "mechanism_of_action", "fact_class": "mechanism"},
                     {"id": "f3", "claim": "Approved 2021",
                      "predicate": "approval_event", "fact_class": "regulatory"},
                 ]},
            ]
        }
        ev = handler._matrix_to_evidence(decomposition)
        assert len(ev) == 3
        claims = [e["content"] for e in ev]
        assert any("STEP 1 met primary endpoint" in c for c in claims)
        assert any("GLP-1 receptor agonist" in c for c in claims)
        assert any("Approved 2021" in c for c in claims)
        # Each item carries its OWN predicate (no leak from the last fact).
        preds = {e["provenance"]["predicate"] for e in ev}
        assert preds == {"clinical_trial", "mechanism_of_action", "approval_event"}
        # Each item carries its OWN fact id.
        assert {e["entity_id"] for e in ev} == {"f1", "f2", "f3"}

    def test_matrix_to_evidence_caps_at_three_per_cell(self, handler):
        """The [:3] cap per cell is intentional (readability/budget) — keep it."""
        decomposition = {
            "cells": [
                {"dimension": "clinical_efficacy", "entity_id": "d1",
                 "facts": [{"id": f"f{i}", "claim": f"trial {i}",
                            "predicate": "clinical_trial", "fact_class": "outcome"}
                           for i in range(5)]},
            ]
        }
        ev = handler._matrix_to_evidence(decomposition)
        assert len(ev) == 3

    def test_matrix_to_evidence_empty(self, handler):
        assert handler._matrix_to_evidence(None) == []
        assert handler._matrix_to_evidence({"cells": []}) == []

    def _stub_handler(self, packed_corpus, mock_llm, mock_metrics):
        from services.unified_handler import UnifiedChatHandler
        return UnifiedChatHandler(
            corpus_doc=packed_corpus.document, l3_doc=packed_corpus.l3_document,
            llm=mock_llm, metrics_svc=mock_metrics, db=object(),  # non-None db
        )

    def test_resolve_plan_entities_drops_fuzzy(self, packed_corpus, mock_llm, mock_metrics, monkeypatch):
        """Only confident (exact/alias/id) matches target the matrix; fuzzy noise
        (combo products, disease words) is dropped."""
        import services.dossier_kb as dk
        from services.ctx_pipeline import QueryPlan

        class RA:
            def __init__(self, t, i, via): self.subject_type, self.subject_id, self.matched_via = t, i, via
            @property
            def resolved(self): return self.matched_via != "unresolved"

        def fake(db, name):
            n = name.lower()
            return {
                "semaglutide": RA("drug", "SEMA", "exact"),
                "diabetes": RA("drug", "DIAB", "fuzzy"),
            }.get(n, RA("drug", "", "unresolved"))

        monkeypatch.setattr(dk, "resolve_asset", fake)
        h = self._stub_handler(packed_corpus, mock_llm, mock_metrics)
        plan = QueryPlan(original_question="tell me about semaglutide for diabetes",
                         resolved_question="", entities_detected=["semaglutide"])
        ids = [e["entity_id"] for e in h._resolve_plan_entities(plan)]
        assert "SEMA" in ids and "DIAB" not in ids

    def test_plan_skipped_for_company_leaders(self, packed_corpus, mock_llm, mock_metrics, monkeypatch):
        import services.dossier_kb as dk
        called = {"n": 0}
        def fake(db, name):
            called["n"] += 1
            raise AssertionError("resolve_asset must not be called for leaders Qs")
        monkeypatch.setattr(dk, "resolve_asset", fake)
        h = self._stub_handler(packed_corpus, mock_llm, mock_metrics)
        from services.ctx_pipeline import QueryPlan
        plan = QueryPlan(original_question="Which companies dominate the diabetes drugs space?",
                         resolved_question="", entities_detected=["diabetes"])
        assert h._plan_decomposition(plan) is None
        assert called["n"] == 0


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


class TestCoverageHonestyContract:
    """H1 — handle() surfaces deterministic coverage limits + review_flags for
    queries that touch not-ingested sources (eval gate G2 / response contract F1)."""

    def test_payer_query_surfaces_limitations(self, handler):
        result = handler.handle("Are GLP-1s covered by payers and what is the formulary tier?")
        data = result["data"]
        assert data["limitations"], "payer query must surface a coverage limitation"
        # MZ-XR-002: source-specific flag replaces the generic SOURCE_COVERAGE_GAP.
        assert "NO_PAYER_SOURCE" in data["review_flags"]
        assert "Coverage limits" in result["narrative"]

    def test_clinical_query_has_no_false_limitations(self, handler):
        result = handler.handle("What is the mechanism of action of semaglutide?")
        assert result["data"]["limitations"] == []
        assert result["data"]["review_flags"] == []

    def test_matrix_gap_surfaces_through_contract(self, handler, monkeypatch):
        """F2 wiring: a decomposition with a real per-dimension gap surfaces a
        grounded MATRIX_GAP_* flag + limitation through handle() into the
        response contract AND the deterministic footer — not just the pure
        function. The question is a plain clinical one (no keyword-driven limit),
        so the limitation can ONLY come from the matrix gap path (eval gate G2)."""
        gappy = {
            "entities": [{"entity_id": "sema", "label": "semaglutide"}],
            "dimensions": [{"key": "pricing", "label": "Pricing & access"}],
            "cells": [{"dimension": "pricing", "entity_id": "sema",
                       "coverage": "gap", "facts": []}],
            "gaps": ["pricing"],
        }
        monkeypatch.setattr(handler, "_plan_decomposition", lambda plan: gappy)
        result = handler.handle("What is the mechanism of action of semaglutide?")
        data = result["data"]
        assert "MATRIX_GAP_PRICING" in data["review_flags"]
        assert any("pricing & access" in t.lower() for t in data["limitations"])
        assert "Coverage limits" in result["narrative"]

    def test_matrix_coverage_table_surfaces_in_narrative(self, handler, monkeypatch):
        """#5 wiring: when a matrix exists, handle() renders the per-lens coverage
        table into the narrative (Lens/Coverage/Source) — the 'render from an
        answer matrix' surface, not just prose."""
        decomp = {
            "entities": [{"entity_id": "sema", "label": "semaglutide"}],
            "dimensions": [
                {"key": "mechanism", "label": "Mechanism"},
                {"key": "pricing", "label": "Pricing & access"},
            ],
            "coverage_summary": {"mechanism": "covered", "pricing": "gap"},
            "cells": [
                {"dimension": "mechanism", "entity_id": "sema", "coverage": "covered",
                 "facts": [{"claim": "GLP-1 RA", "predicate": "mechanism_of_action"}]},
                {"dimension": "pricing", "entity_id": "sema", "coverage": "gap", "facts": []},
            ],
        }
        monkeypatch.setattr(handler, "_plan_decomposition", lambda plan: decomp)
        result = handler.handle("Tell me about semaglutide")
        narrative = result["narrative"]
        assert "Coverage by lens" in narrative
        assert "| Lens | Coverage | Source |" in narrative
        assert "Mechanism" in narrative and "Pricing & access" in narrative
