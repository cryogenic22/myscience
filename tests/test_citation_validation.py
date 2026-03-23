"""Tests for citation validation — SPEC-004 R3.

TDD: Tests written FIRST, then validate_citations() implementation.
"""

from __future__ import annotations

import pytest


class TestValidateCitations:
    """Verify post-synthesis citation validation."""

    def test_valid_citations_unchanged(self):
        from services.llm import validate_citations
        text = "Semaglutide showed results [1] and further evidence [2]."
        result = validate_citations(text, evidence_count=5)
        assert result["narrative"] == text
        assert result["valid"] == 2
        assert result["stripped"] == 0

    def test_strips_invalid_citation(self):
        from services.llm import validate_citations
        text = "This claim [99] is not supported."
        result = validate_citations(text, evidence_count=5)
        assert "[99]" not in result["narrative"]
        assert result["stripped"] == 1

    def test_strips_zero_citation(self):
        """Citations are 1-indexed, so [0] is invalid."""
        from services.llm import validate_citations
        text = "Zero-indexed [0] citation."
        result = validate_citations(text, evidence_count=5)
        assert "[0]" not in result["narrative"]
        assert result["stripped"] == 1

    def test_preserves_text_around(self):
        from services.llm import validate_citations
        text = "text [1] more [99] end"
        result = validate_citations(text, evidence_count=3)
        assert "[1]" in result["narrative"]
        assert "[99]" not in result["narrative"]
        assert "text" in result["narrative"]
        assert "end" in result["narrative"]

    def test_no_citations_unchanged(self):
        from services.llm import validate_citations
        text = "No citations here."
        result = validate_citations(text, evidence_count=5)
        assert result["narrative"] == text
        assert result["valid"] == 0
        assert result["stripped"] == 0

    def test_empty_evidence_strips_all(self):
        from services.llm import validate_citations
        text = "Claims [1] and [2] have no backing."
        result = validate_citations(text, evidence_count=0)
        assert "[1]" not in result["narrative"]
        assert "[2]" not in result["narrative"]
        assert result["stripped"] == 2

    def test_mixed_valid_invalid(self):
        from services.llm import validate_citations
        text = "First [1], second [2], fake [50]."
        result = validate_citations(text, evidence_count=3)
        assert "[1]" in result["narrative"]
        assert "[2]" in result["narrative"]
        assert "[50]" not in result["narrative"]
        assert result["valid"] == 2
        assert result["stripped"] == 1

    def test_handles_empty_narrative(self):
        from services.llm import validate_citations
        result = validate_citations("", evidence_count=5)
        assert result["narrative"] == ""
        assert result["valid"] == 0
