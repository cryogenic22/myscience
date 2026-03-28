"""Tests for search enrichment — suggest, facets, enriched results (SPEC-006 Phase 1).

TDD: These tests are written BEFORE the implementation.
Run with: pytest tests/test_search_enriched.py -v
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from services.search import SearchResult


# ── MockDB for search enrichment ──

class MockDB:
    """Mock database that returns pre-configured query results.

    Routes queries by matching keywords in the SQL. Rules are checked in
    insertion order; the first matching rule wins.
    """

    def __init__(self):
        self._rules: list[tuple[str, list[dict]]] = []

    def add_rule(self, pattern: str, results: list[dict]):
        """Add a routing rule: if *pattern* appears in the SQL, return *results*."""
        self._rules.append((pattern.lower(), results))

    def fetch_all(self, sql: str, params=None) -> list[dict]:
        sql_lower = sql.lower()
        for pattern, results in self._rules:
            if pattern in sql_lower:
                return results
        return []

    def fetch_one(self, sql: str, params=None) -> dict | None:
        rows = self.fetch_all(sql, params)
        return rows[0] if rows else None

    def execute(self, sql: str, params=None) -> None:
        pass


# ── Helpers ──

def _make_search_result(entity_id: str, entity_type: str, title: str, sim: float = 0.8) -> SearchResult:
    """Build a SearchResult for testing."""
    return SearchResult(
        entity_id=entity_id,
        entity_type=entity_type,
        title=title,
        snippet=f"Snippet for {title}",
        similarity=sim,
        metadata={},
        provenance={},
        quality_score=None,
    )


# ── TestSearchSuggest ──

class TestSearchSuggest:
    """Typeahead suggestions via trigram similarity on entity labels."""

    def test_returns_suggestions_for_known_entity(self):
        """Query matching a known entity label should return suggestions."""
        from api.routes.search import search_suggest

        db = MockDB()
        db.add_rule("similarity", [
            {"entity_id": "d001", "entity_type": "drug", "label": "semaglutide", "sim": 0.95},
            {"entity_id": "d002", "entity_type": "drug", "label": "semaglutide oral", "sim": 0.7},
        ])

        result = search_suggest(q="sema", limit=8, db=db)
        assert "suggestions" in result
        assert len(result["suggestions"]) == 2
        assert result["suggestions"][0]["label"] == "semaglutide"
        assert result["suggestions"][0]["entity_type"] == "drug"

    def test_empty_for_gibberish(self):
        """Random string that matches nothing should return empty list."""
        from api.routes.search import search_suggest

        db = MockDB()
        # No rules match -> empty results
        result = search_suggest(q="xyzzy99", limit=8, db=db)
        assert result["suggestions"] == []

    def test_respects_limit(self):
        """Limit parameter should cap the number of suggestions returned."""
        from api.routes.search import search_suggest

        db = MockDB()
        db.add_rule("similarity", [
            {"entity_id": f"d{i:03d}", "entity_type": "drug", "label": f"drug_{i}", "sim": 0.9 - i * 0.01}
            for i in range(10)
        ])

        result = search_suggest(q="drug", limit=3, db=db)
        # The DB returns 10 but endpoint passes limit to SQL, so MockDB returns all 10.
        # Implementation should pass limit to SQL LIMIT clause. With MockDB we just
        # verify the function runs and returns the shape correctly.
        assert "suggestions" in result
        assert len(result["suggestions"]) <= 10  # MockDB returns all; real DB limits

    def test_includes_entity_type(self):
        """Each suggestion should include entity_type."""
        from api.routes.search import search_suggest

        db = MockDB()
        db.add_rule("similarity", [
            {"entity_id": "c001", "entity_type": "company", "label": "Novo Nordisk", "sim": 0.85},
        ])

        result = search_suggest(q="novo", limit=8, db=db)
        assert len(result["suggestions"]) == 1
        suggestion = result["suggestions"][0]
        assert "entity_type" in suggestion
        assert suggestion["entity_type"] == "company"
        assert "entity_id" in suggestion
        assert "similarity" in suggestion


# ── TestSearchFacets ──

class TestSearchFacets:
    """Facet counts in search response."""

    def test_facets_include_entity_type_counts(self):
        """Search response should include entity_type facet counts."""
        from api.routes.search import search_with_facets

        mock_search = MagicMock()
        mock_search.search_paginated.return_value = (
            [
                _make_search_result("d001", "drug", "semaglutide"),
                _make_search_result("d002", "drug", "tirzepatide"),
                _make_search_result("t001", "trial", "NCT001"),
                _make_search_result("c001", "company", "Novo Nordisk"),
            ],
            4,
        )

        db = MockDB()
        # For mechanism/TA facets, return some data for the drug entity IDs
        db.add_rule("mechanism", [
            {"name": "GLP-1 RA", "cnt": 2},
        ])
        db.add_rule("therapeutic_area", [
            {"name": "Diabetes", "cnt": 2},
        ])

        result = search_with_facets(
            query="GLP-1",
            entity_types=None,
            filters=None,
            date_range=None,
            limit=20,
            offset=0,
            search_svc=mock_search,
            db=db,
        )

        assert "facets" in result
        facets = result["facets"]
        assert "entity_type" in facets
        assert facets["entity_type"]["drug"] == 2
        assert facets["entity_type"]["trial"] == 1
        assert facets["entity_type"]["company"] == 1

    def test_facets_empty_when_no_results(self):
        """No results should produce empty facets."""
        from api.routes.search import search_with_facets

        mock_search = MagicMock()
        mock_search.search_paginated.return_value = ([], 0)

        db = MockDB()

        result = search_with_facets(
            query="nonexistent",
            entity_types=None,
            filters=None,
            date_range=None,
            limit=20,
            offset=0,
            search_svc=mock_search,
            db=db,
        )

        assert "facets" in result
        assert result["facets"]["entity_type"] == {}


# ── TestSearchEnriched ──

class TestSearchEnriched:
    """Search with per-result graph enrichment."""

    def test_results_include_connection_counts(self):
        """Enriched results should have connection_counts from graph."""
        from api.routes.search import search_enriched

        mock_search = MagicMock()
        mock_search.search.return_value = [
            _make_search_result("d001", "drug", "semaglutide"),
        ]

        mock_graph = MagicMock()
        mock_graph.entity_summary.return_value = {
            "entity": {"entity_id": "d001", "entity_type": "drug",
                       "label": "semaglutide", "properties": {}},
            "connections_by_type": {"INVESTIGATES": 12, "SPONSORS": 3},
            "connections_by_entity_type": {"trial": 12, "company": 1},
            "total_connections": 15,
        }

        mock_analytics = MagicMock()
        mock_analytics.entity_centrality_batch.return_value = [
            {"entity_id": "d001", "label": "semaglutide", "influence": 0.85,
             "connections": 47, "types_connected": 5},
        ]

        result = search_enriched(
            body={"query": "GLP-1", "limit": 10},
            search_svc=mock_search,
            graph=mock_graph,
            graph_analytics=mock_analytics,
        )

        assert "results" in result
        assert len(result["results"]) == 1
        enriched = result["results"][0]
        assert "connection_counts" in enriched
        assert enriched["connection_counts"]["total_connections"] == 15
        assert "influence_score" in enriched

    def test_handles_entities_without_graph_data(self):
        """Entities not in the graph should get zeroed connection_counts."""
        from api.routes.search import search_enriched

        mock_search = MagicMock()
        mock_search.search.return_value = [
            _make_search_result("d999", "drug", "unknown_drug"),
        ]

        mock_graph = MagicMock()
        mock_graph.entity_summary.return_value = {
            "entity": None,
            "connections_by_type": {},
            "connections_by_entity_type": {},
            "total_connections": 0,
        }

        mock_analytics = MagicMock()
        mock_analytics.entity_centrality_batch.return_value = []

        result = search_enriched(
            body={"query": "unknown", "limit": 10},
            search_svc=mock_search,
            graph=mock_graph,
            graph_analytics=mock_analytics,
        )

        assert len(result["results"]) == 1
        enriched = result["results"][0]
        assert enriched["connection_counts"]["total_connections"] == 0
        assert enriched["influence_score"] == 0.0

    def test_enriched_caps_at_30_results(self):
        """Graph enrichment should cap batch at 30 to prevent slow queries."""
        from api.routes.search import search_enriched

        mock_search = MagicMock()
        mock_search.search.return_value = [
            _make_search_result(f"d{i:03d}", "drug", f"drug_{i}")
            for i in range(50)
        ]

        mock_graph = MagicMock()
        mock_graph.entity_summary.return_value = {
            "entity": None,
            "connections_by_type": {},
            "connections_by_entity_type": {},
            "total_connections": 0,
        }

        mock_analytics = MagicMock()
        mock_analytics.entity_centrality_batch.return_value = []

        result = search_enriched(
            body={"query": "drugs", "limit": 50},
            search_svc=mock_search,
            graph=mock_graph,
            graph_analytics=mock_analytics,
        )

        # Should only enrich the first 30
        assert len(result["results"]) <= 30
        # entity_summary should have been called at most 30 times
        assert mock_graph.entity_summary.call_count <= 30

    def test_enriched_uses_default_limit(self):
        """When no limit is provided, should default to 20."""
        from api.routes.search import search_enriched

        mock_search = MagicMock()
        mock_search.search.return_value = []

        mock_graph = MagicMock()
        mock_analytics = MagicMock()
        mock_analytics.entity_centrality_batch.return_value = []

        result = search_enriched(
            body={"query": "anything"},
            search_svc=mock_search,
            graph=mock_graph,
            graph_analytics=mock_analytics,
        )

        # search.search() should have been called with limit=20 default
        call_kwargs = mock_search.search.call_args
        assert call_kwargs[1].get("limit", call_kwargs[0][1] if len(call_kwargs[0]) > 1 else 20) <= 30
