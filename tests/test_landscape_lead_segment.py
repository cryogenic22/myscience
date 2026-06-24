"""TICKET-4 (F1): anchor landscape synthesis on the requested indication.

Reviewer Q1 ("GLP-1 in obesity") led with Diabetes T2 (615 trials) and falsely
claimed "limited data… for obesity" while the Obesity row (57 trials) was on
screen. Root cause (LIVE path = unified_handler): `_resolve_topic` returns the
MECHANISM (GLP-1) so the requested INDICATION never anchors, and segments arrive
`ORDER BY trial_count DESC`, so the LLM narrates row[0] = diabetes.

These tests pin: (a) the requested-indication segment is reordered to lead, and
(b) a false "no/limited data on <indication>" claim is corrected when a matching
segment was actually retrieved — as pure functions and through the live handler.

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


_DIABETES = {"mechanism_name": "GLP-1 RA", "therapeutic_area": "Diabetes Type 2",
             "drug_count": 40, "trial_count": 615, "active_trial_count": 200}
_OBESITY = {"mechanism_name": "GLP-1 RA", "therapeutic_area": "Obesity",
            "drug_count": 6, "trial_count": 57, "active_trial_count": 20}


class TestLeadWithIndication:
    """Pure function: services.unified_handler._lead_with_indication."""

    def test_requested_indication_leads(self):
        from services.unified_handler import _lead_with_indication

        out = _lead_with_indication([_DIABETES, _OBESITY], "obesity")
        assert out[0]["therapeutic_area"] == "Obesity"
        assert out[1]["therapeutic_area"] == "Diabetes Type 2"

    def test_stable_when_no_match(self):
        from services.unified_handler import _lead_with_indication

        out = _lead_with_indication([_DIABETES, _OBESITY], "oncology")
        assert out == [_DIABETES, _OBESITY]  # unchanged, no spurious reorder

    def test_empty_or_none(self):
        from services.unified_handler import _lead_with_indication

        assert _lead_with_indication([], "obesity") == []
        assert _lead_with_indication([_OBESITY], None) == [_OBESITY]


class TestCorrectFalseAbsence:
    """Pure function: services.llm.correct_false_absence_claims."""

    def test_corrects_limited_data_for_present_indication(self):
        from services.llm import correct_false_absence_claims

        out = correct_false_absence_claims(
            "There is limited data for obesity in the GLP-1 pipeline.", ["obesity"]
        )
        assert "limited data for obesity" not in out["narrative"]
        assert "data for obesity" in out["narrative"]
        assert out["changed"] >= 1

    def test_corrects_no_trials_on_indication(self):
        from services.llm import correct_false_absence_claims

        out = correct_false_absence_claims(
            "There are no trials on obesity worth noting.", ["obesity"]
        )
        assert "no trials on obesity" not in out["narrative"]
        assert out["changed"] >= 1

    def test_corrects_reverse_phrasing(self):
        from services.llm import correct_false_absence_claims

        out = correct_false_absence_claims(
            "Obesity has limited trial data so far.", ["obesity"]
        )
        assert "limited trial data" not in out["narrative"]
        assert "Obesity has trial data" in out["narrative"]
        assert out["changed"] >= 1

    def test_noop_when_term_not_present(self):
        """If the indication was NOT retrieved, an absence claim may be true — do
        not rewrite it."""
        from services.llm import correct_false_absence_claims

        text = "There is limited data for oncology in this corpus."
        out = correct_false_absence_claims(text, ["obesity"])
        assert out["narrative"] == text
        assert out["changed"] == 0

    def test_noop_on_non_absence_prose(self):
        from services.llm import correct_false_absence_claims

        text = "There is rich data for obesity across many trials."
        out = correct_false_absence_claims(text, ["obesity"])
        assert out["narrative"] == text
        assert out["changed"] == 0

    def test_empty(self):
        from services.llm import correct_false_absence_claims

        assert correct_false_absence_claims("", ["obesity"])["changed"] == 0
        assert correct_false_absence_claims("text", [])["changed"] == 0


class TestLivePathAnchorsRequestedIndication:
    """The live UnifiedChatHandler must reorder the requested-indication segment to
    lead AND not assert absence of data for an indication that was retrieved."""

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
        metrics = MagicMock()
        # competitive_landscape returns diabetes first (highest trial_count), as the
        # real ORDER BY trial_count DESC would.
        metrics.competitive_landscape.return_value = [dict(_DIABETES), dict(_OBESITY)]
        metrics.top_companies_by_topic.return_value = []
        h = UnifiedChatHandler(
            corpus_doc=packed.document, l3_doc=packed.l3_document,
            llm=MagicMock(), metrics_svc=metrics,
        )
        # Deterministic indication vocab (independent of MockDB internals).
        h._area_vocab_cache = {"obesity", "diabetes"}
        return h

    def test_obesity_leads_and_no_false_absence(self, handler):
        handler.llm.synthesize.side_effect = lambda **kw: (
            "The GLP-1 landscape is led by diabetes programs. There is limited "
            "data for obesity in this space."
        )
        result = handler.handle("What is the GLP-1 competitive landscape for obesity?")
        segments = result["data"]["metrics_context"]["competitive"]
        assert segments[0]["therapeutic_area"] == "Obesity"   # reordered to lead
        narrative = result["narrative"]
        assert "limited data for obesity" not in narrative      # false absence corrected
