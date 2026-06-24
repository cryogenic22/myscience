"""TICKET-1 (F9): out-of-corpus named-event attribution guard.

Reviewer Q7 asked *"What were the most important oncology trial readouts at ASCO
2025?"* The corpus has no ASCO 2025 data. Instead of saying so, the system
**fabricated** — *"…ASCO 2025 highlighted advancements… particularly
cardiovascular risks…"* — attributing generic literature to a named real-world
congress, with full confidence and no citations. The closed-world prompt forbids
this, but it is advisory and the model ignores it under a named-event question.

These tests pin the deterministic enforcement: a named congress/event in the
QUESTION whose token never appears in the retrieved EVIDENCE is out of corpus, so
(a) its attribution in the narrative is stripped/reframed and (b) an explicit
"no data on <event>" limit is surfaced — as a pure function, through the both-path
``_post_validate`` floor, and through the live UnifiedChatHandler path.

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


class TestDetectOutOfCorpusEvents:
    """Pure function: services.llm.detect_out_of_corpus_events."""

    def test_year_anchor_absent_from_evidence_is_out_of_corpus(self):
        from services.llm import detect_out_of_corpus_events

        events = detect_out_of_corpus_events(
            "What were the oncology readouts at ASCO 2025?",
            evidence_text="Generic cardio-oncology literature with no congress.",
        )
        assert len(events) == 1
        assert events[0]["acronym"] == "ASCO"
        assert events[0]["year"] == "2025"
        assert events[0]["display"] == "ASCO 2025"

    def test_anchor_present_in_evidence_is_supported(self):
        from services.llm import detect_out_of_corpus_events

        events = detect_out_of_corpus_events(
            "What were the oncology readouts at ASCO 2025?",
            evidence_text="The ASCO abstract reported a 30% ORR in the cohort.",
        )
        assert events == []  # the congress IS in the evidence — not fabricated

    def test_bare_acronym_without_year_or_meeting_context_does_not_fire(self):
        """A bare congress acronym with no year and no event-context word is too
        ambiguous (tickers, genes) — must NOT fire (over-firing strips real prose)."""
        from services.llm import detect_out_of_corpus_events

        events = detect_out_of_corpus_events(
            "Tell me about ACC pathway inhibitors.", evidence_text=""
        )
        assert events == []

    def test_acronym_with_meeting_context_fires_without_year(self):
        from services.llm import detect_out_of_corpus_events

        events = detect_out_of_corpus_events(
            "Summarize the key abstracts presented at the ESMO congress.",
            evidence_text="No congress data here.",
        )
        assert [e["acronym"] for e in events] == ["ESMO"]

    def test_lowercase_homonym_never_trips(self):
        """Case-sensitive acronym match: 'chest'/'endo'/'ada' as common words
        must never be read as the CHEST/ENDO/ADA congresses."""
        from services.llm import detect_out_of_corpus_events

        events = detect_out_of_corpus_events(
            "Does the drug cause chest pain in 2025?", evidence_text=""
        )
        assert events == []

    def test_empty_question(self):
        from services.llm import detect_out_of_corpus_events

        assert detect_out_of_corpus_events("", evidence_text="x") == []

    @pytest.mark.parametrize("q", [
        "Were ADA results presented for the immunogenicity cohort?",  # ADA = anti-drug antibody
        "Summarize ESC-derived cardiomyocyte abstracts.",             # ESC = embryonic stem cell
        "Were ACC inhibitor data presented?",                         # ACC = acetyl-CoA-carboxylase
        "What AHA-classified events were reported in the readout?",
        "Which ATS criteria abstracts exist?",
        "Were ASN dosing data presented?",
    ])
    def test_homonym_acronym_with_distant_meeting_word_does_not_fire(self, q):
        """A clinical-homonym acronym must NOT fire just because a meeting/
        presentation word appears elsewhere in the question — the disambiguator
        must be DIRECTLY ADJACENT. (Reviewer finding #1: the over-firing class a
        past _TRIAL_COUNT_RE bug already cost a PR.)"""
        from services.llm import detect_out_of_corpus_events

        assert detect_out_of_corpus_events(q, evidence_text="") == []

    def test_meeting_noun_adjacent_fires_without_year(self):
        from services.llm import detect_out_of_corpus_events

        assert [e["acronym"] for e in detect_out_of_corpus_events(
            "Summarize key abstracts presented at the ESMO congress.", ""
        )] == ["ESMO"]

    def test_bogus_year_not_captured(self):
        """A 5-digit dose/id must not be read as a 4-digit year (reviewer #5)."""
        from services.llm import detect_out_of_corpus_events

        events = detect_out_of_corpus_events("ASCO 90210 abstracts presented", "")
        # fires via the adjacent meeting noun "abstracts", but no bogus year leaks
        assert all(e["year"] is None for e in events)
        assert all("9021" not in e["display"] for e in events)


class TestStripUnsupportedEventAttributions:
    """Pure function: services.llm.strip_unsupported_event_attributions."""

    def _events(self):
        return [{"acronym": "ASCO", "year": "2025", "display": "ASCO 2025"}]

    def test_strips_prepositional_attribution(self):
        from services.llm import strip_unsupported_event_attributions

        text = (
            "The most significant oncology trial readouts at ASCO 2025 highlighted "
            "advancements, particularly cardiovascular risks."
        )
        out = strip_unsupported_event_attributions(text, self._events())
        assert "ASCO 2025 highlighted" not in out["narrative"]
        assert " at ASCO 2025" not in out["narrative"]
        assert out["stripped"] >= 1
        # surrounding real prose survives
        assert "cardiovascular risks" in out["narrative"]

    def test_reframes_subject_verb_attribution(self):
        from services.llm import strip_unsupported_event_attributions

        text = "ASCO 2025 reported strong results across the cohort."
        out = strip_unsupported_event_attributions(text, self._events())
        assert "ASCO 2025 reported" not in out["narrative"]
        assert "the available evidence" in out["narrative"].lower()
        assert "strong results" in out["narrative"]
        assert out["stripped"] == 1

    def test_idempotent(self):
        from services.llm import strip_unsupported_event_attributions

        text = "Findings at ASCO 2025 showed benefit."
        once = strip_unsupported_event_attributions(text, self._events())["narrative"]
        twice = strip_unsupported_event_attributions(once, self._events())
        assert twice["narrative"] == once
        assert twice["stripped"] == 0

    def test_no_events_is_noop(self):
        from services.llm import strip_unsupported_event_attributions

        text = "ASCO 2025 highlighted advancements."
        out = strip_unsupported_event_attributions(text, [])
        assert out["narrative"] == text
        assert out["stripped"] == 0

    def test_subject_reframe_consumes_leading_article(self):
        """No "The the available evidence" dangling article (reviewer #2)."""
        from services.llm import strip_unsupported_event_attributions

        out = strip_unsupported_event_attributions(
            "The ASCO 2025 meeting revealed new oncology data [1].", self._events()
        )
        assert "the the" not in out["narrative"].lower()
        assert out["narrative"].startswith("The available evidence revealed")

    def test_prepositional_strip_leaves_clean_grammar(self):
        """No leading space / orphan comma / lowercase sentence start (reviewer #3)."""
        from services.llm import strip_unsupported_event_attributions

        assert strip_unsupported_event_attributions(
            "At ASCO 2025 the trial showed benefit.", self._events()
        )["narrative"] == "The trial showed benefit."
        assert strip_unsupported_event_attributions(
            "During ASCO 2025 sessions, ORR rose.", self._events()
        )["narrative"] == "ORR rose."

    def test_according_to_and_possessive_phrasings(self):
        """"According to <event>" + "<event>'s data" attributions (reviewer #4)."""
        from services.llm import strip_unsupported_event_attributions

        assert "ASCO 2025" not in strip_unsupported_event_attributions(
            "According to ASCO 2025, oncology readouts were strong.", self._events()
        )["narrative"]
        out = strip_unsupported_event_attributions(
            "ASCO 2025's data showed cardiovascular benefit.", self._events()
        )
        assert "ASCO 2025" not in out["narrative"]
        assert "the available evidence" in out["narrative"].lower()

    def test_reframe_preserves_internal_caps_terms(self):
        """The sentence-start recapitalization must not mangle mRNA/siRNA."""
        from services.llm import strip_unsupported_event_attributions

        out = strip_unsupported_event_attributions(
            "At ASCO 2025 mRNA platforms were discussed.", self._events()
        )
        assert "mRNA" in out["narrative"]
        assert "MRNA" not in out["narrative"]


class TestPostValidateFloor:
    """The both-path _post_validate floor neutralizes a fabricated event
    attribution when given the question + evidence text."""

    def _synth(self):
        from services.llm import LLMSynthesizer

        return LLMSynthesizer(MagicMock())

    def test_floor_neutralizes_absent_event(self):
        synth = self._synth()
        narrative = "Per ASCO 2025, the leading oncology readouts showed benefit."
        out = synth._post_validate(
            narrative,
            evidence_count=0,
            question="What were the readouts at ASCO 2025?",
            evidence_text="Cardio-oncology literature; no congress mentioned.",
        )
        assert "ASCO 2025" not in out or "Per ASCO 2025" not in out
        assert "showed benefit" in out

    def test_floor_leaves_supported_event_untouched(self):
        synth = self._synth()
        narrative = "The ASCO 2025 abstract reported a 30% ORR."
        out = synth._post_validate(
            narrative,
            evidence_count=1,
            question="What did ASCO 2025 report?",
            evidence_text="ASCO 2025 abstract: 30% ORR observed.",
        )
        assert "ASCO 2025" in out  # supported by evidence — preserved


class TestLivePathRefusesFabrication:
    """The live UnifiedChatHandler path must NOT attribute findings to a named
    congress absent from the corpus, and must surface an explicit no-data limit
    (reviewer Q7: the ASCO 2025 fabrication)."""

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

    def test_fabricated_congress_attribution_neutralized(self, handler):
        handler.llm.synthesize.side_effect = lambda **kw: (
            "The most significant oncology trial readouts at ASCO 2025 highlighted "
            "advancements in treatment, particularly cardiovascular risks."
        )
        result = handler.handle(
            "What were the most important oncology trial readouts at ASCO 2025?"
        )
        narrative = result["narrative"]
        # No attribution to the absent congress survives.
        assert "ASCO 2025 highlighted" not in narrative
        assert "ASCO 2025 showed" not in narrative
        assert "ASCO 2025 reported" not in narrative
        # An explicit no-data / out-of-corpus statement is present.
        assert "ASCO 2025" in narrative  # named in the honest limit
        low = narrative.lower()
        assert ("no data on asco 2025" in low) or ("out of corpus" in low)
        # The structured response contract carries the flag.
        assert "OUT_OF_CORPUS_EVENT" in result["data"]["review_flags"]
