"""TICKET-3 (F4): similarity floor / primary_unresolved.

Reviewer Q3 surfaced "Nimacimab injection" (and Q5 a Metformin/Fluoxetin trial) as
the canvas headline for an unrelated query: HybridSearch / CTX hydration always
return *something*, however weak, with no relevance floor, so a nearest-neighbour
entity fills the slot and is presented as if it answers the question.

LIVE path = CTXQueryPipeline. The fix surfaces `primary_unresolved` when the
asked-about subject (a resolved entity, OR the subject of a "tell me about X"
dossier) is ABSENT from the retrieved context — and the handler leads with an
honest "no confident match" instead of substituting. Self-correcting: it can NOT
fire when the subject DOES appear in the retrieved context.

TDD: RED before the change.
"""

from __future__ import annotations

import tempfile
from unittest.mock import MagicMock

import pytest

from tests.test_ctx_corpus import (
    MOCK_DRUGS,
    MOCK_COMPANIES,
    MOCK_TRIALS,
    MOCK_MECHANISMS,
    MockDB,
)


def _plan(**kw):
    from services.ctx_pipeline import QueryPlan

    kw.setdefault("original_question", kw.get("resolved_question", ""))
    kw.setdefault("resolved_question", kw.get("original_question", ""))
    return QueryPlan(**kw)


def _retrieval(text: str):
    from services.ctx_pipeline import RetrievalResult

    # _header_text feeds render_context(); a section marker keeps ctx_sections-empty
    # from being the only signal. token_count drives the substantiveness boost only.
    return RetrievalResult(_header_text=text, token_count=len(text) // 4)


class TestDossierSubject:
    def test_extracts_subject(self):
        from services.ctx_pipeline import _dossier_subject, _subject_tokens

        assert _dossier_subject("Tell me about Nimacimab") == "Nimacimab"
        assert _dossier_subject("What is donanemab?") == "donanemab"
        assert _dossier_subject("Compare A and B") == ""   # not a dossier form
        assert _subject_tokens("the obesity market") == ["obesity", "market"]


class TestReasonPrimaryUnresolved:
    """ctx_pipeline.reason() sets the flag from subject-vs-context."""

    @pytest.fixture
    def pipeline(self):
        from services.ctx_corpus import PharmaCorpusBuilder
        from services.unified_handler import UnifiedChatHandler

        db = MockDB()
        for t, rows in (("drugs", MOCK_DRUGS), ("companies", MOCK_COMPANIES),
                        ("clinical_trials", MOCK_TRIALS), ("mechanisms", MOCK_MECHANISMS)):
            db.set_results(t, rows)
        packed = PharmaCorpusBuilder(db).pack(tempfile.mkdtemp())
        h = UnifiedChatHandler(corpus_doc=packed.document, l3_doc=packed.l3_document,
                               llm=MagicMock(), metrics_svc=MagicMock())
        return h.pipeline

    def test_resolved_entity_present_not_unresolved(self, pipeline):
        plan = _plan(entities_detected=["semaglutide"], intent="dossier",
                     original_question="Tell me about semaglutide")
        r = pipeline.reason(plan, _retrieval("DRUG-SEMAGLUTIDE\nMECHANISM: GLP-1 agonist"))
        assert r.primary_unresolved is False

    def test_named_entity_absent_is_unresolved(self, pipeline):
        plan = _plan(entities_detected=["nimacimab"], intent="dossier",
                     original_question="Tell me about nimacimab")
        r = pipeline.reason(plan, _retrieval("DRUG-SEMAGLUTIDE\nMECHANISM: GLP-1 agonist"))
        assert r.primary_unresolved is True

    def test_dossier_subject_absent_is_unresolved(self, pipeline):
        plan = _plan(entities_detected=[], intent="dossier",
                     original_question="Tell me about Nimacimab",
                     resolved_question="Tell me about Nimacimab")
        r = pipeline.reason(plan, _retrieval("DRUG-SEMAGLUTIDE\nMECHANISM: GLP-1 agonist"))
        assert r.primary_unresolved is True

    def test_dossier_subject_present_not_unresolved(self, pipeline):
        plan = _plan(entities_detected=[], intent="dossier",
                     original_question="Tell me about the obesity market",
                     resolved_question="Tell me about the obesity market")
        r = pipeline.reason(plan, _retrieval("Obesity GLP-1 competitive landscape data"))
        assert r.primary_unresolved is False

    def test_non_dossier_no_entity_does_not_fire(self, pipeline):
        """A category/landscape question with no named entity must NOT fire."""
        plan = _plan(entities_detected=[], intent="landscape",
                     original_question="What is the GLP-1 landscape?")
        r = pipeline.reason(plan, _retrieval("Some GLP-1 segments"))
        assert r.primary_unresolved is False

    def test_general_intent_whats_form_subject_absent_fires(self, pipeline):
        """Reviewer nit #1: 'what's X' classifies as 'general' but is subject-shaped;
        the dossier-subject branch must reach it (regex was broader than the gate)."""
        plan = _plan(entities_detected=[], intent="general",
                     original_question="what's Foobarib",
                     resolved_question="what's Foobarib")
        r = pipeline.reason(plan, _retrieval("DRUG-SEMAGLUTIDE\nMECHANISM: GLP-1 agonist"))
        assert r.primary_unresolved is True

    def test_general_intent_non_subject_form_does_not_fire(self, pipeline):
        """A 'general' question that is NOT subject-shaped yields no subject tokens
        and must not fire."""
        plan = _plan(entities_detected=[], intent="general",
                     original_question="How does the pipeline look overall?")
        r = pipeline.reason(plan, _retrieval("Some pipeline data"))
        assert r.primary_unresolved is False


class TestUnresolvedLead:
    def test_names_subject(self):
        from services.unified_handler import _unresolved_lead

        lead = _unresolved_lead(_plan(entities_detected=["Nimacimab"], intent="dossier"))
        assert "Nimacimab" in lead
        assert "confident match" in lead.lower()

    def test_dossier_subject_when_no_entity(self):
        from services.unified_handler import _unresolved_lead

        lead = _unresolved_lead(_plan(entities_detected=[], intent="dossier",
                                      original_question="Tell me about Foobarib",
                                      resolved_question="Tell me about Foobarib"))
        assert "Foobarib" in lead


class TestLivePathPrimaryUnresolved:
    @pytest.fixture
    def handler(self):
        from services.ctx_corpus import PharmaCorpusBuilder
        from services.unified_handler import UnifiedChatHandler

        db = MockDB()
        for t, rows in (("drugs", MOCK_DRUGS), ("companies", MOCK_COMPANIES),
                        ("clinical_trials", MOCK_TRIALS), ("mechanisms", MOCK_MECHANISMS)):
            db.set_results(t, rows)
        packed = PharmaCorpusBuilder(db).pack(tempfile.mkdtemp())
        return UnifiedChatHandler(corpus_doc=packed.document, l3_doc=packed.l3_document,
                                  llm=MagicMock(), metrics_svc=MagicMock())

    def test_absent_subject_leads_with_no_confident_match(self, handler):
        handler.llm.synthesize.side_effect = lambda **kw: (
            "Nimacimab injection is a monoclonal antibody in early development."
        )
        result = handler.handle("Tell me about Xyzzynib")
        assert result["data"]["primary_unresolved"] is True
        assert "PRIMARY_UNRESOLVED" in result["data"]["review_flags"]
        assert "confident match" in result["narrative"].lower()

    def test_resolved_subject_no_false_unresolved(self, handler):
        """A query whose subject IS in the corpus must NOT be flagged unresolved."""
        handler.llm.synthesize.side_effect = lambda **kw: "Semaglutide is a GLP-1 agonist."
        result = handler.handle("Tell me about semaglutide")
        assert result["data"]["primary_unresolved"] is False
        assert "confident match" not in result["narrative"].lower()
