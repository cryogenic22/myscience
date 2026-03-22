"""Tests for services/literature.py — section parser for Literature Explorer.

TDD: Write tests first, then implement parse_sections().
"""

from __future__ import annotations

import pytest


class TestParseSections:
    """Verify PMC full_text → section tree parsing."""

    def test_abstract_only(self):
        """No full_text → single Abstract section from pubmed abstract."""
        from services.literature import parse_sections
        sections = parse_sections(full_text=None, abstract="This study evaluated GLP-1 agonists.")
        assert len(sections) == 1
        assert sections[0]["title"] == "Abstract"
        assert sections[0]["level"] == 1
        assert "GLP-1 agonists" in sections[0]["content"]
        assert sections[0]["children"] == []

    def test_with_full_text(self):
        """## headers in full_text → multiple level-1 sections."""
        from services.literature import parse_sections
        full_text = (
            "## Introduction\n\n"
            "This is the introduction.\n\n"
            "## Methods\n\n"
            "We conducted a randomized trial.\n\n"
            "## Results\n\n"
            "The primary endpoint was met."
        )
        sections = parse_sections(full_text=full_text, abstract="Study abstract here.")
        titles = [s["title"] for s in sections]
        assert "Abstract" in titles
        assert "Introduction" in titles
        assert "Methods" in titles
        assert "Results" in titles
        # Abstract should be first
        assert sections[0]["title"] == "Abstract"
        # Introduction content should be present
        intro = [s for s in sections if s["title"] == "Introduction"][0]
        assert "introduction" in intro["content"].lower()

    def test_nested_subsections(self):
        """### under ## → children array populated."""
        from services.literature import parse_sections
        full_text = (
            "## Methods\n\n"
            "Overview of methods.\n\n"
            "### Study Design\n\n"
            "Randomized, double-blind.\n\n"
            "### Participants\n\n"
            "Adults aged 18-65.\n\n"
            "## Results\n\n"
            "Primary endpoint results."
        )
        sections = parse_sections(full_text=full_text, abstract=None)
        methods = [s for s in sections if s["title"] == "Methods"][0]
        assert len(methods["children"]) == 2
        assert methods["children"][0]["title"] == "Study Design"
        assert methods["children"][0]["level"] == 2
        assert methods["children"][1]["title"] == "Participants"
        # Results should be a separate top-level section
        results = [s for s in sections if s["title"] == "Results"]
        assert len(results) == 1

    def test_empty_both(self):
        """No full_text and no abstract → empty list."""
        from services.literature import parse_sections
        sections = parse_sections(full_text=None, abstract=None)
        assert sections == []

    def test_no_headers(self):
        """Full text without ## markers → single 'Full Text' section."""
        from services.literature import parse_sections
        sections = parse_sections(
            full_text="Just a long block of text with no section headers.",
            abstract=None,
        )
        assert len(sections) == 1
        assert sections[0]["title"] == "Full Text"
        assert "long block of text" in sections[0]["content"]

    def test_ids_unique(self):
        """All section and subsection IDs must be unique."""
        from services.literature import parse_sections
        full_text = (
            "## Introduction\n\nText.\n\n"
            "## Methods\n\nText.\n\n"
            "### Design\n\nText.\n\n"
            "### Analysis\n\nText.\n\n"
            "## Results\n\nText."
        )
        sections = parse_sections(full_text=full_text, abstract="Abstract text.")
        all_ids = []
        for s in sections:
            all_ids.append(s["id"])
            for child in s.get("children", []):
                all_ids.append(child["id"])
        assert len(all_ids) == len(set(all_ids)), f"Duplicate IDs found: {all_ids}"

    def test_abstract_dedup(self):
        """If PMC full_text starts with ## Abstract, skip it — use pubmed abstract instead."""
        from services.literature import parse_sections
        full_text = (
            "## Abstract\n\n"
            "PMC version of abstract.\n\n"
            "## Introduction\n\n"
            "Introduction text."
        )
        sections = parse_sections(
            full_text=full_text,
            abstract="PubMed version of abstract.",
        )
        # Should have Abstract (from pubmed) + Introduction — not two abstract sections
        abstract_sections = [s for s in sections if s["title"].lower() == "abstract"]
        assert len(abstract_sections) == 1
        assert "PubMed version" in abstract_sections[0]["content"]
