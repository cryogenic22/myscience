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


class TestLowMatchScoreWarning:
    """Verify fuzzy match warning is added to LLM extra_context in dossier handler."""

    def _make_dossier_mocks(self, match_score):
        """Helper to create mocks for dossier handler tests."""
        from unittest.mock import MagicMock

        mock_resolved = {
            "entity_id": "d1",
            "label": "semaglutide",
            "entity_type": "drug",
            "match_score": match_score,
        }

        mock_result = MagicMock()
        mock_result.evidence = []
        mock_result.graph_context = {"nodes": [], "edges": [], "node_count": 0, "edge_count": 0}
        mock_result.metrics_context = {}
        mock_result.entity_focus = []
        mock_result.provenance_summary = {}

        drug_row = {
            "generic_name": "semaglutide",
            "brand_name": "Ozempic",
            "supply_status": "NORMAL",
            "company_name": "Novo Nordisk",
            "therapeutic_area": "Diabetes",
            "mechanism": "GLP-1 RA",
        }
        conn_row = {
            "trial_links": 0,
            "evidence_links": 0,
            "ta_links": 0,
            "mech_links": 0,
            "owns_links": 0,
            "total": 0,
        }

        mock_db = MagicMock()
        # fetch_one is called: first for drug_row, second for conn_row, third for events
        mock_db.fetch_one.side_effect = [drug_row, conn_row]
        mock_db.fetch_all.return_value = []  # market events

        mock_engine = MagicMock()
        mock_engine.entity_dossier.return_value = mock_result

        mock_llm = MagicMock()
        mock_llm.synthesize_dossier.return_value = "Test narrative"

        return mock_resolved, mock_db, mock_engine, mock_llm

    def test_low_match_score_adds_warning_context(self):
        """When match_score < 0.8, dossier handler should include fuzzy match warning."""
        from unittest.mock import patch

        mock_resolved, mock_db, mock_engine, mock_llm = self._make_dossier_mocks(0.7)

        with patch("services.chat_handlers.handlers.resolve_entity", return_value=mock_resolved):
            from services.chat_handlers.handlers import handle_dossier
            result = handle_dossier(
                params={"entity_name": "sema"},
                db=mock_db,
                engine=mock_engine,
                llm=mock_llm,
            )

        # Verify the LLM was called with the fuzzy match warning in extra_context
        call_kwargs = mock_llm.synthesize_dossier.call_args
        extra_context = call_kwargs.kwargs.get("extra_context") or call_kwargs[1].get("extra_context", "")
        assert "[NOTE: Entity matched via fuzzy search" in str(extra_context)

    def test_exact_match_no_warning(self):
        """When match_score is 1.0, no fuzzy warning should be added."""
        from unittest.mock import patch

        mock_resolved, mock_db, mock_engine, mock_llm = self._make_dossier_mocks(1.0)

        with patch("services.chat_handlers.handlers.resolve_entity", return_value=mock_resolved):
            from services.chat_handlers.handlers import handle_dossier
            result = handle_dossier(
                params={"entity_name": "semaglutide"},
                db=mock_db,
                engine=mock_engine,
                llm=mock_llm,
            )

        call_kwargs = mock_llm.synthesize_dossier.call_args
        extra_context = call_kwargs.kwargs.get("extra_context") or call_kwargs[1].get("extra_context")
        # No fuzzy warning for exact match
        if extra_context:
            assert "[NOTE: Entity matched via fuzzy search" not in str(extra_context)

    def test_dossier_confidence_uses_match_score(self):
        """Dossier handler should pass match_score to confidence computation."""
        from unittest.mock import patch

        mock_resolved, mock_db, mock_engine, mock_llm = self._make_dossier_mocks(0.7)

        with patch("services.chat_handlers.handlers.resolve_entity", return_value=mock_resolved):
            from services.chat_handlers.handlers import handle_dossier
            result = handle_dossier(
                params={"entity_name": "sema"},
                db=mock_db,
                engine=mock_engine,
                llm=mock_llm,
            )

        # Confidence should be present and reflect the fuzzy match_score
        assert "confidence" in result
        # With match_score=0.7, entity component is 0.3*0.7=0.21, and no other signals
        # so confidence should be 0.21
        assert result["confidence"] == 0.21
