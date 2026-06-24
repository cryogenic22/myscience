"""TICKET-9 (F2): enforce "counts are not quality" in post-validation.

Reviewer Q1 narrated a drug-count proportion as *"34.3% of the market share"* and
Q4 framed a count as a *"robust… commitment."* No sales or market-share source is
ingested (the platform even surfaces a NO_SALES_VOLUME_SOURCE coverage limit), so a
"market share" figure is ALWAYS a count proportion mislabeled as a commercial
metric, and a count described as "robust" imports a quality verdict the data can't
support. The closed-world prompt forbids both but is advisory; these tests pin the
deterministic enforcement — qualify to an honest count basis — as a pure function,
through the both-path _post_validate floor, and through the live UnifiedChatHandler.

Deliberately conservative: only the always-unsupportable "market share" / "share of
the market" phrasing and "robust pipeline/portfolio" are touched; bare "market"
(market landscape, the obesity market) and grounded leader/ranking language are NOT
(they collide with the real grounded-leaders feature).

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


class TestQualifyCountAsQuality:
    """Pure function: services.llm.qualify_count_as_quality."""

    def test_percent_market_share_qualified_to_count_basis(self):
        from services.llm import qualify_count_as_quality

        out = qualify_count_as_quality("Novo Nordisk holds 34.3% market share in obesity.")
        assert "market share" not in out["narrative"]   # commercial claim gone
        assert "34.3%" in out["narrative"]               # the figure survives
        assert "ingested count" in out["narrative"].lower()
        assert out["changed"] >= 1

    def test_market_share_of_percent_qualified(self):
        from services.llm import qualify_count_as_quality

        out = qualify_count_as_quality("It commands a market share of 34.3% today.")
        assert "market share" not in out["narrative"]
        assert "34.3%" in out["narrative"]
        assert out["changed"] >= 1

    def test_bare_market_share_qualified(self):
        from services.llm import qualify_count_as_quality

        out = qualify_count_as_quality("The drug leads on market share.")
        assert "market share" not in out["narrative"]
        assert "ingested count" in out["narrative"].lower()
        assert out["changed"] >= 1

    def test_share_of_the_market_qualified(self):
        from services.llm import qualify_count_as_quality

        out = qualify_count_as_quality("It has the largest share of the market.")
        assert "share of the market" not in out["narrative"]
        assert out["changed"] >= 1

    def test_robust_pipeline_downgraded(self):
        from services.llm import qualify_count_as_quality

        out = qualify_count_as_quality("Eli Lilly has a robust pipeline in diabetes.")
        assert "robust pipeline" not in out["narrative"]
        assert "pipeline" in out["narrative"]            # the noun survives
        assert out["changed"] >= 1

    def test_does_not_touch_bare_market_words(self):
        """'market landscape', 'the obesity market', 'market players' are not the
        category error and must be left alone (no over-firing)."""
        from services.llm import qualify_count_as_quality

        text = (
            "The obesity market is competitive; the market landscape has many "
            "market players and a clear go-to-market motion."
        )
        out = qualify_count_as_quality(text)
        assert out["narrative"] == text
        assert out["changed"] == 0

    def test_does_not_touch_grounded_leader_language(self):
        """Grounded ranking language (the real leaders feature) is not stripped."""
        from services.llm import qualify_count_as_quality

        text = "Novo Nordisk and Eli Lilly lead the obesity space by portfolio size."
        out = qualify_count_as_quality(text)
        assert out["narrative"] == text
        assert out["changed"] == 0

    def test_idempotent(self):
        from services.llm import qualify_count_as_quality

        once = qualify_count_as_quality("It holds 34.3% market share and a robust pipeline.")
        twice = qualify_count_as_quality(once["narrative"])
        assert twice["narrative"] == once["narrative"]
        assert twice["changed"] == 0

    def test_empty(self):
        from services.llm import qualify_count_as_quality

        out = qualify_count_as_quality("")
        assert out["narrative"] == ""
        assert out["changed"] == 0


class TestPostValidateFloor:
    """The both-path _post_validate floor qualifies count-as-quality language."""

    def test_floor_qualifies_market_share(self):
        from services.llm import LLMSynthesizer

        synth = LLMSynthesizer(MagicMock())
        out = synth._post_validate("Novo holds 34.3% market share.", evidence_count=0)
        assert "market share" not in out
        assert "34.3%" in out


class TestLivePathQualifiesCountAsQuality:
    """The live UnifiedChatHandler path qualifies a count-as-market-share claim."""

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
        return UnifiedChatHandler(
            corpus_doc=packed.document,
            l3_doc=packed.l3_document,
            llm=MagicMock(),
            metrics_svc=MagicMock(),
        )

    def test_market_share_qualified_in_response(self, handler):
        handler.llm.synthesize.side_effect = lambda **kw: (
            "Novo Nordisk holds 34.3% market share, reflecting a robust pipeline."
        )
        result = handler.handle("Who leads the obesity drug market?")
        narrative = result["narrative"]
        assert "market share" not in narrative
        assert "robust pipeline" not in narrative
        assert "34.3%" in narrative  # the figure is preserved, only the framing qualified
