"""Tests for the few-shot prompt library.

Validates exemplar retrieval, citation quality, and integration with
the LLM context pipeline.
"""

from __future__ import annotations

import re
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.few_shot_library import (
    FewShotExemplar,
    FewShotLibrary,
    EXEMPLARS,
)


# ── TestFewShotLibrary ────────────────────────────────────────────


class TestFewShotLibrary:
    """Core library behavior tests."""

    def setup_method(self):
        self.lib = FewShotLibrary()

    def test_get_exemplars_for_dossier(self):
        """Returns 2-3 exemplar pairs for dossier intent."""
        exemplars = self.lib.get_exemplars("dossier")
        assert len(exemplars) >= 1
        assert len(exemplars) <= 3
        assert all(e.intent == "dossier" for e in exemplars)

    def test_get_exemplars_for_compare(self):
        """Returns exemplar pairs for compare intent."""
        exemplars = self.lib.get_exemplars("compare")
        assert len(exemplars) >= 1
        assert all(e.intent == "compare" for e in exemplars)

    def test_get_exemplars_for_landscape(self):
        """Returns exemplar pairs for landscape intent."""
        exemplars = self.lib.get_exemplars("landscape")
        assert len(exemplars) >= 1
        assert all(e.intent == "landscape" for e in exemplars)

    def test_get_exemplars_for_pipeline(self):
        """Returns exemplar pairs for pipeline intent."""
        exemplars = self.lib.get_exemplars("pipeline")
        assert len(exemplars) >= 1
        assert all(e.intent == "pipeline" for e in exemplars)

    def test_get_exemplars_for_general(self):
        """Returns exemplar pairs for general intent."""
        exemplars = self.lib.get_exemplars("general")
        assert len(exemplars) >= 1
        assert all(e.intent == "general" for e in exemplars)

    def test_unknown_intent_returns_empty(self):
        """Unknown intent returns empty list."""
        assert self.lib.get_exemplars("unknown_intent_xyz") == []
        assert self.lib.get_exemplars("") == []
        assert self.lib.get_exemplars("hallucinated") == []

    def test_exemplars_have_required_fields(self):
        """Each exemplar has question, answer, and intent fields."""
        for intent, pool in EXEMPLARS.items():
            for ex in pool:
                assert isinstance(ex, FewShotExemplar), f"Not a FewShotExemplar: {ex}"
                assert ex.question, f"Empty question in {intent}"
                assert ex.answer, f"Empty answer in {intent}"
                assert ex.intent == intent, f"Intent mismatch: {ex.intent} != {intent}"

    def test_exemplars_contain_citations(self):
        """Every answer has [1], [2], or [metrics] markers."""
        citation_re = re.compile(r"\[(\d+|metrics)\]")
        for intent, pool in EXEMPLARS.items():
            for ex in pool:
                markers = citation_re.findall(ex.answer)
                assert len(markers) >= 2, (
                    f"Exemplar for intent={intent} q='{ex.question[:40]}...' "
                    f"has only {len(markers)} citation(s): {markers}"
                )

    def test_format_few_shot_context(self):
        """Formats as 'Example Q&A:' block for LLM."""
        exemplars = self.lib.get_exemplars("dossier", max_examples=2)
        block = self.lib.format_context(exemplars)
        assert "=== Example Q&A" in block
        assert "Q:" in block
        assert "A:" in block
        # Should contain the actual question/answer text
        assert exemplars[0].question in block
        assert exemplars[0].answer in block

    def test_format_empty_returns_empty(self):
        """Formatting empty list returns empty string."""
        assert self.lib.format_context([]) == ""

    def test_entity_type_preference(self):
        """When entity_type specified, matching exemplars come first."""
        exemplars = self.lib.get_exemplars("dossier", max_examples=1, entity_type="company")
        if exemplars:
            assert exemplars[0].entity_type == "company"


class TestFewShotExemplarCoverage:
    """Validates the breadth of exemplar coverage."""

    def test_minimum_exemplars_per_intent(self):
        """Each intent has at least 3 exemplars."""
        required_intents = ["dossier", "compare", "landscape", "pipeline", "general"]
        for intent in required_intents:
            pool = EXEMPLARS.get(intent, [])
            assert len(pool) >= 3, (
                f"Intent '{intent}' has only {len(pool)} exemplars (need >= 3)"
            )

    def test_total_exemplar_count(self):
        """At least 15 exemplars total across all intents."""
        total = sum(len(pool) for pool in EXEMPLARS.values())
        assert total >= 15, f"Only {total} exemplars total (need >= 15)"

    def test_all_answers_have_bold_entities(self):
        """Every answer uses **bold** for key entities."""
        bold_re = re.compile(r"\*\*[^*]+\*\*")
        for intent, pool in EXEMPLARS.items():
            for ex in pool:
                assert bold_re.search(ex.answer), (
                    f"No bold entities in {intent} exemplar: {ex.question[:40]}"
                )


class TestFewShotMaxExamples:
    """Validates the max_examples limiter."""

    def setup_method(self):
        self.lib = FewShotLibrary()

    def test_few_shot_limited_to_2_examples(self):
        """Default max is 2 per query to save tokens."""
        exemplars = self.lib.get_exemplars("dossier")
        assert len(exemplars) <= 2

    def test_max_examples_1(self):
        """Can request only 1 exemplar."""
        exemplars = self.lib.get_exemplars("dossier", max_examples=1)
        assert len(exemplars) == 1

    def test_max_examples_all(self):
        """Can request all exemplars."""
        exemplars = self.lib.get_exemplars("dossier", max_examples=10)
        assert len(exemplars) == len(EXEMPLARS["dossier"])


class TestFewShotIntegration:
    """Integration with llm.py context pipeline."""

    def test_few_shot_added_to_context_block(self):
        """Exemplars appear in assembled context."""
        from services.few_shot_library import FewShotLibrary

        lib = FewShotLibrary()
        exemplars = lib.get_exemplars("dossier", max_examples=2)
        block = lib.format_context(exemplars)

        # Simulate what _build_context_block does: append to context
        base_context = "USER QUESTION: Tell me about semaglutide\n\nINTENT: dossier"
        full_context = base_context + "\n\n" + block

        assert "Example Q&A" in full_context
        assert "Q:" in full_context
        assert "[1]" in full_context or "[2]" in full_context

    def test_few_shot_limited_to_2_examples_in_context(self):
        """Max 2 exemplars per query to save tokens."""
        lib = FewShotLibrary()
        exemplars = lib.get_exemplars("compare", max_examples=2)
        assert len(exemplars) <= 2
        block = lib.format_context(exemplars)
        # Count Q: markers — should be at most 2
        q_count = block.count("\nQ: ")
        assert q_count <= 2
