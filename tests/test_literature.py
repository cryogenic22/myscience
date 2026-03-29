"""Tests for services/literature.py — section parser + API route contracts.

TDD: Write tests first, then implement parse_sections().
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


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


class TestDocumentEndpointEnhancements:
    """Verify the document endpoint returns full_text_source and PDF URL."""

    def test_pdf_url_included_for_pmc_article(self):
        """When pmc_id is present, external_urls should include pdf link."""
        from fastapi.testclient import TestClient

        mock_db = MagicMock()
        mock_db.fetch_one.side_effect = [
            # Article lookup
            {
                "id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                "pmid": "12345678",
                "title": "Test Article",
                "abstract": "Test abstract for GLP-1.",
                "authors": ["Author A"],
                "journal": "Nature",
                "publication_date": "2025-01-15",
                "mesh_terms": [],
                "source_url": None,
            },
            # PMC lookup
            {
                "pmc_id": "PMC9999999",
                "full_text": "## Introduction\n\nFull text body.",
                "article_type": "research-article",
                "is_protocol": False,
                "is_systematic_review": False,
            },
        ]
        mock_db.fetch_all.return_value = []  # cross-links

        from api.routes.literature import router
        from api.deps import get_db
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_db] = lambda: mock_db
        client = TestClient(app)

        resp = client.get("/literature/12345678/document")
        assert resp.status_code == 200
        data = resp.json()
        assert data["full_text_source"] == "PMC"
        assert data["external_urls"]["pdf"] == "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9999999/pdf/"
        assert data["external_urls"]["pmc"] == "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9999999/"
        assert data["external_urls"]["pubmed"] == "https://pubmed.ncbi.nlm.nih.gov/12345678/"

    def test_no_pmc_means_no_pdf_url(self):
        """When no PMC data, full_text_source is null and pdf URL is null."""
        from fastapi.testclient import TestClient

        mock_db = MagicMock()
        mock_db.fetch_one.side_effect = [
            # Article lookup
            {
                "id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                "pmid": "12345678",
                "title": "Abstract-Only Article",
                "abstract": "Short abstract.",
                "authors": [],
                "journal": "Science",
                "publication_date": None,
                "mesh_terms": [],
                "source_url": None,
            },
            # PMC lookup -- no match
            None,
        ]
        mock_db.fetch_all.return_value = []

        from api.routes.literature import router
        from api.deps import get_db
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_db] = lambda: mock_db
        client = TestClient(app)

        resp = client.get("/literature/12345678/document")
        assert resp.status_code == 200
        data = resp.json()
        assert data["full_text_source"] is None
        assert data["external_urls"]["pdf"] is None
        assert data["has_full_text"] is False


class TestSimilarArticlesEndpoint:
    """Verify similar articles API endpoint."""

    def test_returns_similar_articles(self):
        """Should use find_similar and return formatted results."""
        from api.routes.literature import similar_articles
        from services.search import SearchResult

        mock_db = MagicMock()
        mock_db.fetch_one.return_value = {
            "eid": "aaa-bbb-ccc",
            "abstract_embedding": [0.1] * 1536,
        }

        mock_result = SearchResult(
            entity_id="ddd-eee-fff",
            entity_type="literature",
            title="Related GLP-1 Study",
            snippet="This study...",
            similarity=0.92,
            metadata={"pmid": "99999", "journal": "NEJM", "publication_date": "2025-06-01"},
            provenance={},
        )

        mock_search = MagicMock()
        mock_search.find_similar.return_value = [mock_result]

        result = similar_articles(article_id="aaa-bbb-ccc", limit=5, db=mock_db, search=mock_search)
        assert len(result["similar"]) == 1
        assert result["similar"][0]["pmid"] == "99999"
        assert result["similar"][0]["title"] == "Related GLP-1 Study"
        assert result["similar"][0]["similarity"] == 0.92
        mock_search.find_similar.assert_called_once_with("aaa-bbb-ccc", "literature", limit=5)

    def test_returns_empty_when_no_embedding(self):
        """No embedding → empty similar list."""
        from api.routes.literature import similar_articles

        mock_db = MagicMock()
        mock_db.fetch_one.return_value = {
            "eid": "aaa-bbb-ccc",
            "abstract_embedding": None,
        }
        mock_search = MagicMock()

        result = similar_articles(article_id="aaa-bbb-ccc", limit=5, db=mock_db, search=mock_search)
        assert result["similar"] == []
        mock_search.find_similar.assert_not_called()

    def test_404_when_article_not_found(self):
        """Missing article → 404."""
        from api.routes.literature import similar_articles
        from fastapi import HTTPException

        mock_db = MagicMock()
        mock_db.fetch_one.return_value = None
        mock_search = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            similar_articles(article_id="nonexistent", limit=5, db=mock_db, search=mock_search)
        assert exc_info.value.status_code == 404


class TestArticleSummaryEndpoint:
    """Verify AI summary endpoint."""

    def test_returns_summary_when_abstract_long_enough(self):
        """Should call LLM and return generated summary."""
        from api.routes.literature import article_summary

        mock_db = MagicMock()
        mock_db.fetch_one.side_effect = [
            # Article lookup
            {
                "id": "aaa-bbb-ccc",
                "pmid": "12345",
                "title": "GLP-1 Receptor Agonists in Obesity",
                "abstract": "A" * 200,  # > 100 chars
            },
            # PMC lookup — no full text
            None,
        ]

        mock_llm = MagicMock()
        mock_llm.enabled.return_value = True
        mock_llm.synthesize.return_value = {"narrative": "- Key finding 1\n- Key finding 2"}

        result = article_summary(article_id="12345", db=mock_db, llm=mock_llm)
        assert result["generated"] is True
        assert "Key finding" in result["summary"]
        mock_llm.synthesize.assert_called_once()

    def test_returns_null_when_text_too_short(self):
        """Abstract too short → null summary."""
        from api.routes.literature import article_summary

        mock_db = MagicMock()
        mock_db.fetch_one.side_effect = [
            {
                "id": "aaa-bbb-ccc",
                "pmid": "12345",
                "title": "Short",
                "abstract": "Too short.",
            },
            None,  # no PMC
        ]

        mock_llm = MagicMock()
        result = article_summary(article_id="12345", db=mock_db, llm=mock_llm)
        assert result["summary"] is None
        assert result["generated"] is False

    def test_returns_null_when_llm_disabled(self):
        """LLM disabled → null summary."""
        from api.routes.literature import article_summary

        mock_db = MagicMock()
        mock_db.fetch_one.side_effect = [
            {
                "id": "aaa-bbb-ccc",
                "pmid": "12345",
                "title": "Test",
                "abstract": "A" * 200,
            },
            None,
        ]

        mock_llm = MagicMock()
        mock_llm.enabled.return_value = False

        result = article_summary(article_id="12345", db=mock_db, llm=mock_llm)
        assert result["summary"] is None
        assert result["generated"] is False

    def test_404_when_article_not_found(self):
        """Missing article → 404."""
        from api.routes.literature import article_summary
        from fastapi import HTTPException

        mock_db = MagicMock()
        mock_db.fetch_one.return_value = None
        mock_llm = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            article_summary(article_id="nonexistent", db=mock_db, llm=mock_llm)
        assert exc_info.value.status_code == 404
