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
