"""Tests for new catalog API endpoints — Phase 4.5.

TDD: Verify completeness, bulk-update, bulk-resolve, freshness endpoints.
Uses MockDB to avoid real database dependency.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest


class MockDB:
    """Mock database for catalog API tests."""

    def __init__(self):
        self._results: dict[str, list[dict]] = {}
        self.executed: list[tuple[str, list]] = []

    def set_results(self, key: str, results: list[dict]):
        self._results[key] = results

    def fetch_all(self, sql: str, params=None) -> list[dict]:
        sql_lower = sql.lower()
        from_match = re.search(r'\bfrom\s+(\w+)', sql_lower)
        if from_match:
            primary = from_match.group(1)
            if primary in self._results:
                return self._results[primary]
        for key, results in self._results.items():
            if key in sql_lower:
                return results
        return []

    def fetch_one(self, sql: str, params=None) -> dict | None:
        sql_lower = sql.lower()
        if "information_schema" in sql_lower:
            return {"exists_": True}
        if "count(*)" in sql_lower:
            return {"cnt": 10, "total": 10}
        results = self.fetch_all(sql, params)
        return results[0] if results else None

    def execute(self, sql: str, params=None) -> None:
        self.executed.append((sql, params or []))


# ── Test completeness endpoint logic ──

class TestFieldCompleteness:
    def test_completeness_returns_all_types(self):
        """field_completeness should return scores for all entity types."""
        from api.routes.catalog import field_completeness

        db = MockDB()
        db.set_results("drugs", [{"cnt": 100}])
        db.set_results("companies", [{"cnt": 50}])

        # Mock fetch_one for COUNT and field queries
        original_fetch_one = db.fetch_one

        def custom_fetch_one(sql, params=None):
            if "count(*)" in sql.lower():
                return {"cnt": 100}
            if "filled" in sql.lower():
                return {"filled": 75}
            return original_fetch_one(sql, params)

        db.fetch_one = custom_fetch_one

        result = field_completeness(entity_type=None, db=db)
        assert "completeness" in result
        # Should have entries for all entity types
        assert len(result["completeness"]) > 0

    def test_completeness_for_single_type(self):
        db = MockDB()

        def custom_fetch_one(sql, params=None):
            if "count(*)" in sql.lower():
                return {"cnt": 50}
            if "filled" in sql.lower():
                return {"filled": 25}
            return None

        db.fetch_one = custom_fetch_one

        from api.routes.catalog import field_completeness
        result = field_completeness(entity_type="drug", db=db)
        assert "drug" in result["completeness"]
        assert result["completeness"]["drug"]["total"] == 50


# ── Test freshness endpoint logic ──

class TestSourceFreshness:
    def test_returns_freshness_dict(self):
        from api.routes.catalog import source_freshness

        db = MockDB()
        now = datetime.now(timezone.utc)
        db.set_results("drugs", [
            {"source_api": "fda_orange_book", "records": 500,
             "latest": now, "days_since": 5.0},
        ])

        result = source_freshness(db=db)
        assert "freshness" in result


# ── Test bulk operations ──

class TestBulkUpdate:
    def test_rejects_unknown_entity_type(self):
        from api.routes.catalog import bulk_update_entities, BulkUpdateRequest
        from fastapi import HTTPException

        db = MockDB()
        body = BulkUpdateRequest(entity_ids=["a"], fields={"name": "X"})

        with pytest.raises(HTTPException) as exc_info:
            bulk_update_entities(entity_type="bogus", body=body, db=db)
        assert exc_info.value.status_code == 400

    def test_rejects_non_editable_fields(self):
        from api.routes.catalog import bulk_update_entities, BulkUpdateRequest
        from fastapi import HTTPException

        db = MockDB()
        body = BulkUpdateRequest(entity_ids=["a"], fields={"generic_name": "X"})

        with pytest.raises(HTTPException) as exc_info:
            bulk_update_entities(entity_type="drug", body=body, db=db)
        assert exc_info.value.status_code == 400


class TestBulkResolve:
    def test_rejects_invalid_action(self):
        from api.routes.catalog import bulk_resolve_hitl, BulkResolveRequest
        from fastapi import HTTPException

        db = MockDB()
        body = BulkResolveRequest(review_ids=["r1"], action="invalid")

        with pytest.raises(HTTPException) as exc_info:
            bulk_resolve_hitl(body=body, db=db)
        assert exc_info.value.status_code == 400

    def test_resolves_valid_items(self):
        db = MockDB()

        from api.routes.catalog import bulk_resolve_hitl, BulkResolveRequest
        body = BulkResolveRequest(review_ids=["r1", "r2"], action="approved")
        result = bulk_resolve_hitl(body=body, db=db)

        assert result["ok"] is True
        assert result["resolved"] == 2
        assert result["action"] == "approved"
