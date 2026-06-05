"""Tests for narrative numeric verification — SPEC-004 R2.

TDD: Tests written FIRST, then verify_narrative_numbers() implementation.
"""

from __future__ import annotations

import pytest


class TestVerifyNumbers:
    """Verify bold numbers in narrative against source data."""

    def test_matching_numbers_verified(self):
        from services.llm import verify_narrative_numbers
        narrative = "Pipeline score of **42.5** across trials."
        result = verify_narrative_numbers(narrative, source_numbers={42.5, 10, 3})
        assert result["verified"] >= 1
        assert result["flagged"] == 0

    def test_mismatched_number_flagged(self):
        from services.llm import verify_narrative_numbers
        narrative = "Pipeline score of **12.5** is notable."
        result = verify_narrative_numbers(narrative, source_numbers={8.5, 10})
        assert result["flagged"] >= 1

    def test_percentage_verified(self):
        from services.llm import verify_narrative_numbers
        narrative = "Success rate of **82%** in trials."
        result = verify_narrative_numbers(narrative, source_numbers={82, 0.82, 5})
        assert result["verified"] >= 1

    def test_no_bold_numbers_passes(self):
        from services.llm import verify_narrative_numbers
        narrative = "Semaglutide is a GLP-1 agonist with strong evidence."
        result = verify_narrative_numbers(narrative, source_numbers={42.5})
        assert result["verified"] == 0
        assert result["flagged"] == 0

    def test_evidence_numbers_checked(self):
        from services.llm import verify_narrative_numbers
        narrative = "Found **312** articles across **5** sources."
        result = verify_narrative_numbers(narrative, source_numbers={312, 5, 47})
        assert result["verified"] == 2

    def test_multiple_numbers(self):
        from services.llm import verify_narrative_numbers
        narrative = "Score **42.5**, trials **10**, invented **999**."
        result = verify_narrative_numbers(narrative, source_numbers={42.5, 10, 3})
        assert result["verified"] == 2
        assert result["flagged"] == 1

    def test_tolerates_rounding(self):
        from services.llm import verify_narrative_numbers
        narrative = "Pipeline score of **42** from the analysis."
        result = verify_narrative_numbers(narrative, source_numbers={42.3})
        assert result["verified"] >= 1
        assert result["flagged"] == 0

    def test_ignores_non_numeric_bold(self):
        from services.llm import verify_narrative_numbers
        narrative = "**Semaglutide** has **Novo Nordisk** as manufacturer."
        result = verify_narrative_numbers(narrative, source_numbers={42.5})
        assert result["verified"] == 0
        assert result["flagged"] == 0


class TestNumericGroundingHardening:
    """H2 — every number in a synthesized answer must trace to a provided
    context value, or be suppressed/flagged. Golden cases."""

    # (1) A number present in context survives intact.
    def test_grounded_number_survives(self):
        from services.llm import verify_narrative_numbers
        narrative = "Patients saw 23% weight loss in the trial."
        result = verify_narrative_numbers(narrative, source_numbers={23, 5})
        assert result["flagged"] == 0
        assert result["verified"] >= 1
        assert "[unverified]" not in result["narrative"]
        assert "23%" in result["narrative"]

    # (2) An invented unbolded percentage absent from context is flagged.
    def test_invented_percentage_is_flagged(self):
        from services.llm import verify_narrative_numbers
        narrative = "Patients saw 23% weight loss in the trial."
        result = verify_narrative_numbers(narrative, source_numbers={5, 10})
        assert result["flagged"] >= 1
        assert "[unverified]" in result["narrative"]
        # The figure is de-emphasised (marked), not silently kept as fact.
        assert "23% [unverified]" in result["narrative"]

    # (2b) An invented multiplier ("2.5x pipeline score") is flagged.
    def test_invented_multiplier_is_flagged(self):
        from services.llm import verify_narrative_numbers
        narrative = "It has a 2.5x pipeline score advantage."
        result = verify_narrative_numbers(narrative, source_numbers={1.2, 8})
        assert result["flagged"] >= 1
        assert "2.5x [unverified]" in result["narrative"]

    def test_grounded_multiplier_survives(self):
        from services.llm import verify_narrative_numbers
        narrative = "It has a 2.5x pipeline score advantage."
        result = verify_narrative_numbers(narrative, source_numbers={2.5})
        assert result["flagged"] == 0
        assert "[unverified]" not in result["narrative"]

    # Identifiers must NOT be treated as statistics (conservative).
    def test_identifiers_not_flagged(self):
        from services.llm import verify_narrative_numbers
        narrative = (
            "GLP-1 receptor agonist for Type 2 diabetes in a Phase 3 trial."
        )
        result = verify_narrative_numbers(narrative, source_numbers={42})
        assert result["flagged"] == 0
        assert "[unverified]" not in result["narrative"]

    # Bold invented numbers are unbolded AND marked (stronger than before).
    def test_invented_bold_number_marked(self):
        from services.llm import verify_narrative_numbers
        narrative = "Pipeline score of **999** is notable."
        result = verify_narrative_numbers(narrative, source_numbers={42.5})
        assert result["flagged"] >= 1
        assert "**999**" not in result["narrative"]   # bold removed
        assert "999 [unverified]" in result["narrative"]

    # A flagged figure is marked exactly once (no double-marking across passes).
    def test_no_double_marking(self):
        from services.llm import verify_narrative_numbers
        narrative = "Efficacy was **88%** in the cohort."
        result = verify_narrative_numbers(narrative, source_numbers={5})
        assert result["narrative"].count("[unverified]") == 1
