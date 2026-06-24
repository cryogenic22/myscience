"""TICKET-2 (F3): entity-link id validation — kill the abc-123 placeholder leak.

The synthesis prompt hands the model a worked example
``[Semaglutide](/entity/drug/abc-123)``; when the queried entity is poorly
resolved the model copies ``abc-123`` verbatim and it renders as a fake,
clickable citation (reviewer Q3 produced ``[Donanemab](/entity/drug/abc-123)``).
``validate_citations`` historically did NOT validate ``/entity/{type}/{id}``
links against the evidence, so the fake link survived to the screen.

These tests pin: sentinel/example ids and ids absent from this turn's evidence
are stripped to plain label text (no information loss), while a real resolved id
survives — both as a pure function and through the live UnifiedChatHandler path.

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


class TestStripInvalidEntityLinks:
    """Pure function: services.llm.strip_invalid_entity_links."""

    def test_strips_placeholder_sentinel_keeps_label(self):
        from services.llm import strip_invalid_entity_links

        text = "The drug [Donanemab](/entity/drug/abc-123) was reviewed."
        result = strip_invalid_entity_links(text)
        assert "abc-123" not in result["narrative"]
        assert "(/entity/" not in result["narrative"]  # link removed entirely
        assert "Donanemab" in result["narrative"]  # label preserved
        assert result["stripped"] == 1

    def test_strips_company_sentinel(self):
        from services.llm import strip_invalid_entity_links

        text = "[Novo Nordisk](/entity/company/c-456) leads the space."
        result = strip_invalid_entity_links(text)
        assert "c-456" not in result["narrative"]
        assert "Novo Nordisk" in result["narrative"]
        assert result["stripped"] == 1

    def test_strips_renamed_sentinel(self):
        """The new, deliberately-uncopyable example id must also never survive."""
        from services.llm import strip_invalid_entity_links

        text = "[Sema](/entity/drug/EXAMPLE_ID_DO_NOT_COPY) here."
        result = strip_invalid_entity_links(text)
        assert "EXAMPLE_ID_DO_NOT_COPY" not in result["narrative"]
        assert "Sema" in result["narrative"]
        assert result["stripped"] == 1

    def test_keeps_link_with_known_id(self):
        from services.llm import strip_invalid_entity_links

        text = "[Semaglutide](/entity/drug/drug-123) is a GLP-1 agonist."
        result = strip_invalid_entity_links(text, valid_entity_ids={"drug-123"})
        assert "[Semaglutide](/entity/drug/drug-123)" in result["narrative"]
        assert result["stripped"] == 0

    def test_strips_unknown_id_when_set_provided(self):
        from services.llm import strip_invalid_entity_links

        text = "[Mystery](/entity/drug/nope-999) appears as the headline."
        result = strip_invalid_entity_links(text, valid_entity_ids={"drug-123"})
        assert "nope-999" not in result["narrative"]
        assert "Mystery" in result["narrative"]
        assert result["stripped"] == 1

    def test_id_match_is_case_insensitive(self):
        from services.llm import strip_invalid_entity_links

        text = "[Sema](/entity/drug/DRUG-Semaglutide) is studied."
        result = strip_invalid_entity_links(text, valid_entity_ids={"drug-semaglutide"})
        assert "DRUG-Semaglutide" in result["narrative"]  # kept (case-insensitive)
        assert result["stripped"] == 0

    def test_no_links_unchanged(self):
        from services.llm import strip_invalid_entity_links

        text = "Plain prose with a [1] numbered citation, no entity links."
        result = strip_invalid_entity_links(text)
        assert result["narrative"] == text
        assert result["stripped"] == 0

    def test_empty_narrative(self):
        from services.llm import strip_invalid_entity_links

        result = strip_invalid_entity_links("")
        assert result["narrative"] == ""
        assert result["stripped"] == 0

    def test_mixed_known_and_sentinel(self):
        from services.llm import strip_invalid_entity_links

        text = (
            "[Semaglutide](/entity/drug/drug-123) beats "
            "[Donanemab](/entity/drug/abc-123) on footprint."
        )
        result = strip_invalid_entity_links(text, valid_entity_ids={"drug-123"})
        assert "[Semaglutide](/entity/drug/drug-123)" in result["narrative"]
        assert "abc-123" not in result["narrative"]
        assert "Donanemab" in result["narrative"]
        assert result["stripped"] == 1


class TestPromptSentinelRenamed:
    """The synthesis prompt must not TELL the model to emit a copyable fake id."""

    def test_citation_protocol_has_no_copyable_sentinel(self):
        import services.llm as llm_mod

        assert "abc-123" not in llm_mod._CITATION_PROTOCOL
        assert "c-456" not in llm_mod._CITATION_PROTOCOL


class TestLivePathStripsFakeLinks:
    """The live UnifiedChatHandler path must strip a fabricated entity link
    (the abc-123 the model copies from the prompt example) before it reaches
    the user, validating against this turn's actual evidence ids."""

    @pytest.fixture
    def handler(self):
        from services.ctx_corpus import PharmaCorpusBuilder
        from services.unified_handler import UnifiedChatHandler

        db = MockDB()
        db.set_results("drugs", MOCK_DRUGS)
        db.set_results("companies", MOCK_COMPANIES)
        db.set_results("clinical_trials", MOCK_TRIALS)
        db.set_results("mechanisms", MOCK_MECHANISMS)
        builder = PharmaCorpusBuilder(db)
        packed = builder.pack(tempfile.mkdtemp())
        llm = MagicMock()
        return UnifiedChatHandler(
            corpus_doc=packed.document,
            l3_doc=packed.l3_document,
            llm=llm,
            metrics_svc=MagicMock(),
        )

    def test_fabricated_entity_link_stripped_from_response(self, handler):
        handler.llm.synthesize.side_effect = lambda **kw: (
            "Recent activity for [Donanemab](/entity/drug/abc-123) and "
            "[Other](/entity/drug/UNKNOWN-XYZ) was reviewed."
        )
        result = handler.handle("What FDA approvals exist for donanemab?")
        narrative = result["narrative"]
        assert "abc-123" not in narrative
        assert "UNKNOWN-XYZ" not in narrative
        assert "(/entity/" not in narrative  # no fabricated clickable links survive
        # Label text preserved — the answer still names the entities.
        assert "Donanemab" in narrative
        assert "Other" in narrative
