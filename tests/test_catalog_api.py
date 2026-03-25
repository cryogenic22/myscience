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


# ── Test dataset profile endpoint ──

class TestDatasetProfile:
    def test_returns_profile_for_known_source(self):
        """dataset_profile should return static metadata + live stats for a known source."""
        from api.routes.catalog import dataset_profile

        db = MockDB()
        now = datetime.now(timezone.utc)

        # Mock: clinical_trials table has records with this source
        def custom_fetch_one(sql, params=None):
            sql_lower = sql.lower()
            if "information_schema" in sql_lower:
                return {"exists_": True}
            if "count(*)" in sql_lower and "source_api" in sql_lower:
                return {"cnt": 5307, "latest": now}
            if "avg" in sql_lower:
                return {"avg_score": 0.98}
            return None

        db.fetch_one = custom_fetch_one

        result = dataset_profile(source_key="clinical_trials_gov", db=db)

        assert result["source_key"] == "clinical_trials_gov"
        assert result["display_name"] == "ClinicalTrials.gov"
        assert "trial" in result["entity_types"]
        assert result["refresh_schedule"] == "Daily at 02:00 UTC"
        assert result["collection_method"] == "API (REST JSON)"
        assert len(result["fields_collected"]) > 0
        assert result["description"]
        assert result["source_url"] == "https://clinicaltrials.gov"
        assert result["coverage_notes"]

    def test_returns_profile_for_backfill(self):
        """Backfill (internal enrichment) should have source_url as None."""
        from api.routes.catalog import dataset_profile

        db = MockDB()
        db.fetch_one = lambda sql, params=None: (
            {"exists_": True} if "information_schema" in sql.lower()
            else {"cnt": 0, "latest": None} if "count(*)" in sql.lower()
            else None
        )

        result = dataset_profile(source_key="backfill", db=db)

        assert result["source_key"] == "backfill"
        assert result["source_url"] is None
        assert "drug" in result["entity_types"]
        assert result["collection_method"] == "Internal (LLM + heuristic)"

    def test_rejects_unknown_source(self):
        """dataset_profile should 404 for unknown sources."""
        from api.routes.catalog import dataset_profile
        from fastapi import HTTPException

        db = MockDB()

        with pytest.raises(HTTPException) as exc_info:
            dataset_profile(source_key="bogus_source", db=db)
        assert exc_info.value.status_code == 404

    def test_all_ten_sources_have_profiles(self):
        """All 10 source keys in DATASET_PROFILES should be present and well-formed."""
        from api.routes.catalog import DATASET_PROFILES

        expected_sources = [
            "clinical_trials_gov", "pubmed", "fda_orange_book",
            "openfda_faers", "openfda_labels", "fda_shortages",
            "sec_edgar", "mesh_ontology", "pmc", "backfill",
        ]

        assert set(DATASET_PROFILES.keys()) == set(expected_sources)

        required_fields = [
            "display_name", "description", "entity_types",
            "refresh_schedule", "collection_method", "fields_collected",
            "coverage_notes",
        ]

        for source_key, profile in DATASET_PROFILES.items():
            for field in required_fields:
                assert field in profile, f"{source_key} missing {field}"
            assert isinstance(profile["entity_types"], list), f"{source_key} entity_types should be a list"
            assert isinstance(profile["fields_collected"], list), f"{source_key} fields_collected should be a list"
            assert len(profile["fields_collected"]) > 0, f"{source_key} fields_collected should not be empty"

    def test_profile_includes_live_stats_fields(self):
        """dataset_profile response should always include records, quality_score, last_refreshed, freshness."""
        from api.routes.catalog import dataset_profile

        db = MockDB()
        db.fetch_one = lambda sql, params=None: (
            {"exists_": False} if "information_schema" in sql.lower()
            else {"cnt": 0, "latest": None} if "count(*)" in sql.lower()
            else None
        )

        for source_key in ["clinical_trials_gov", "pubmed", "sec_edgar"]:
            result = dataset_profile(source_key=source_key, db=db)
            assert "records" in result, f"{source_key} missing records"
            assert "quality_score" in result, f"{source_key} missing quality_score"
            assert "last_refreshed" in result, f"{source_key} missing last_refreshed"
            assert "freshness" in result, f"{source_key} missing freshness"
