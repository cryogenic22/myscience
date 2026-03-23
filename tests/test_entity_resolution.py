"""Tests for entity resolution confidence — SPEC-004 R6.

TDD: resolve_entity() returns match_score indicating resolution quality.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock


class MockDB:
    def __init__(self):
        self._exact = None
        self._fuzzy = None

    def fetch_one(self, sql, params=None):
        sql_lower = sql.lower()
        if "lower" in sql_lower and "like" in sql_lower:
            return self._fuzzy
        if "lower" in sql_lower and "=" in sql_lower:
            return self._exact
        if "id::text" in sql_lower and "=" in sql_lower:
            return self._exact
        return None


class TestResolveEntityMatchScore:
    """Verify match_score in resolve_entity results."""

    def test_exact_match_score_1(self):
        from services.chat_handlers.formatting import resolve_entity
        db = MockDB()
        db._exact = {"entity_id": "d1", "label": "semaglutide"}
        result = resolve_entity("semaglutide", "drug", db)
        assert result is not None
        assert result["match_score"] == 1.0

    def test_fuzzy_match_lower_score(self):
        from services.chat_handlers.formatting import resolve_entity
        db = MockDB()
        db._exact = None
        db._fuzzy = {"entity_id": "d1", "label": "semaglutide"}
        result = resolve_entity("sema", "drug", db)
        assert result is not None
        assert result["match_score"] < 1.0
        assert result["match_score"] >= 0.5

    def test_uuid_match_score_1(self):
        from services.chat_handlers.formatting import resolve_entity
        db = MockDB()
        db._exact = {"entity_id": "550e8400-e29b-41d4-a716-446655440000", "label": "semaglutide"}
        result = resolve_entity("550e8400-e29b-41d4-a716-446655440000", "drug", db)
        assert result is not None
        assert result["match_score"] == 1.0

    def test_no_match_returns_none(self):
        from services.chat_handlers.formatting import resolve_entity
        db = MockDB()
        result = resolve_entity("nonexistent_drug_xyz", "drug", db)
        assert result is None

    def test_match_score_present_in_all_results(self):
        """Every non-None result must have match_score."""
        from services.chat_handlers.formatting import resolve_entity
        db = MockDB()
        db._exact = {"entity_id": "d1", "label": "semaglutide"}
        result = resolve_entity("semaglutide", "", db)
        assert result is not None
        assert "match_score" in result
        assert 0.0 <= result["match_score"] <= 1.0

    def test_empty_type_searches_all_tables(self):
        from services.chat_handlers.formatting import resolve_entity
        db = MockDB()
        db._exact = {"entity_id": "d1", "label": "semaglutide"}
        result = resolve_entity("semaglutide", "", db)
        assert result is not None
