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

    def test_all_sources_have_profiles(self):
        """All source keys in DATASET_PROFILES should be present and well-formed."""
        from api.routes.catalog import DATASET_PROFILES

        expected_sources = [
            "clinical_trials_gov", "pubmed", "fda_orange_book",
            "openfda_faers", "openfda_labels", "fda_shortages",
            "sec_edgar", "mesh_ontology", "pmc", "ema",
            "nadac", "pharma_news",
            "chembl", "pubchem", "open_targets",
            "backfill",
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


# ── MockDB for rich browse queries ──

class RichMockDB:
    """MockDB that supports the JOIN-heavy browse queries."""

    def __init__(self):
        self._fetch_all_results: list[dict] = []
        self._fetch_one_result: dict | None = None
        self.queries: list[str] = []

    def set_fetch_all(self, rows: list[dict]):
        self._fetch_all_results = rows

    def set_total(self, total: int):
        self._fetch_one_result = {"total": total, "exists_": True}

    def fetch_all(self, sql: str, params=None) -> list[dict]:
        self.queries.append(sql)
        return list(self._fetch_all_results)

    def fetch_one(self, sql: str, params=None) -> dict | None:
        self.queries.append(sql)
        sql_lower = sql.lower()
        if "information_schema" in sql_lower:
            return {"exists_": True}
        if "count(*)" in sql_lower:
            return self._fetch_one_result or {"total": 0}
        return self._fetch_one_result


# ── Test enriched browse endpoints ──

class TestBrowseDrugsEnriched:
    """browse_entities for drugs should return joined data with mechanism, company, TA."""

    def _make_drug_row(self, **overrides):
        base = {
            "id": "d1", "_label": "Semaglutide", "brand_name": "Ozempic",
            "approval_date": "2017-12-05", "supply_status": "NORMAL",
            "quality_score": 0.85, "record_status": "active",
            "mechanism_name": "GLP-1 receptor agonist",
            "company_name": "Novo Nordisk", "therapeutic_area": "Diabetes",
            "trial_count": 42, "pipeline_score": 18.5,
        }
        base.update(overrides)
        return base

    def test_drug_browse_returns_joined_fields(self):
        """Drug rows should include mechanism_name, company_name, therapeutic_area, trial_count, pipeline_score."""
        from api.routes.catalog import _browse_drugs, ENTITY_TABLES

        db = RichMockDB()
        db.set_total(1)
        db.set_fetch_all([self._make_drug_row()])

        result = _browse_drugs(
            search=None, status=None, quality_min=None,
            sort=None, sort_by=None, sort_dir=None,
            limit_val=50, offset_val=0, db=db, meta=ENTITY_TABLES["drug"],
        )

        assert result["entity_type"] == "drug"
        assert len(result["results"]) == 1
        row = result["results"][0]
        assert row["mechanism_name"] == "GLP-1 receptor agonist"
        assert row["company_name"] == "Novo Nordisk"
        assert row["therapeutic_area"] == "Diabetes"
        assert row["trial_count"] == 42
        assert row["pipeline_score"] == 18.5

    def test_drug_browse_default_sort_is_pipeline_score(self):
        """Default sort for drugs should be pipeline_score DESC, not alphabetical."""
        from api.routes.catalog import _browse_drugs, ENTITY_TABLES

        db = RichMockDB()
        db.set_total(2)
        db.set_fetch_all([
            self._make_drug_row(_label="Semaglutide", pipeline_score=18.5),
            self._make_drug_row(_label="Aspirin", pipeline_score=2.0),
        ])

        _browse_drugs(
            search=None, status=None, quality_min=None,
            sort=None, sort_by=None, sort_dir=None,
            limit_val=50, offset_val=0, db=db, meta=ENTITY_TABLES["drug"],
        )

        # Verify ORDER BY in SQL references pipeline_score DESC
        select_query = [q for q in db.queries if "FROM drugs d" in q and "LIMIT" in q]
        assert len(select_query) == 1
        assert "pipeline_score" in select_query[0].lower()
        assert "DESC" in select_query[0]

    def test_drug_browse_sort_by_name(self):
        """sort=name should order by _label ASC."""
        from api.routes.catalog import _browse_drugs, ENTITY_TABLES

        db = RichMockDB()
        db.set_total(1)
        db.set_fetch_all([self._make_drug_row()])

        _browse_drugs(
            search=None, status=None, quality_min=None,
            sort="name", sort_by=None, sort_dir=None,
            limit_val=50, offset_val=0, db=db, meta=ENTITY_TABLES["drug"],
        )

        select_query = [q for q in db.queries if "FROM drugs d" in q and "LIMIT" in q]
        assert len(select_query) == 1
        assert "_label" in select_query[0]
        assert "ASC" in select_query[0]

    def test_drug_browse_sort_by_quality(self):
        """sort=quality should order by quality_score DESC."""
        from api.routes.catalog import _browse_drugs, ENTITY_TABLES

        db = RichMockDB()
        db.set_total(1)
        db.set_fetch_all([self._make_drug_row()])

        _browse_drugs(
            search=None, status=None, quality_min=None,
            sort="quality", sort_by=None, sort_dir=None,
            limit_val=50, offset_val=0, db=db, meta=ENTITY_TABLES["drug"],
        )

        select_query = [q for q in db.queries if "FROM drugs d" in q and "LIMIT" in q]
        assert len(select_query) == 1
        assert "quality_score" in select_query[0].lower()
        assert "DESC" in select_query[0]

    def test_drug_browse_search_filter(self):
        """Search should filter by generic_name and brand_name."""
        from api.routes.catalog import _browse_drugs, ENTITY_TABLES

        db = RichMockDB()
        db.set_total(1)
        db.set_fetch_all([self._make_drug_row()])

        _browse_drugs(
            search="sema", status=None, quality_min=None,
            sort=None, sort_by=None, sort_dir=None,
            limit_val=50, offset_val=0, db=db, meta=ENTITY_TABLES["drug"],
        )

        select_query = [q for q in db.queries if "FROM drugs d" in q and "LIMIT" in q]
        assert len(select_query) == 1
        assert "ILIKE" in select_query[0]

    def test_drug_browse_pagination(self):
        """Pagination should pass through limit and offset."""
        from api.routes.catalog import _browse_drugs, ENTITY_TABLES

        db = RichMockDB()
        db.set_total(100)
        db.set_fetch_all([self._make_drug_row()])

        result = _browse_drugs(
            search=None, status=None, quality_min=None,
            sort=None, sort_by=None, sort_dir=None,
            limit_val=10, offset_val=20, db=db, meta=ENTITY_TABLES["drug"],
        )

        assert result["total"] == 100
        assert result["limit"] == 10
        assert result["offset"] == 20

    def test_drug_browse_status_filter(self):
        """Status filter should add WHERE d.record_status = %s."""
        from api.routes.catalog import _browse_drugs, ENTITY_TABLES

        db = RichMockDB()
        db.set_total(1)
        db.set_fetch_all([self._make_drug_row(record_status="excluded")])

        _browse_drugs(
            search=None, status="excluded", quality_min=None,
            sort=None, sort_by=None, sort_dir=None,
            limit_val=50, offset_val=0, db=db, meta=ENTITY_TABLES["drug"],
        )

        select_query = [q for q in db.queries if "FROM drugs d" in q and "LIMIT" in q]
        assert "record_status" in select_query[0].lower()

    def test_drug_browse_quality_min_filter(self):
        """quality_min should filter drugs below threshold."""
        from api.routes.catalog import _browse_drugs, ENTITY_TABLES

        db = RichMockDB()
        db.set_total(1)
        db.set_fetch_all([self._make_drug_row(quality_score=0.9)])

        _browse_drugs(
            search=None, status=None, quality_min=0.8,
            sort=None, sort_by=None, sort_dir=None,
            limit_val=50, offset_val=0, db=db, meta=ENTITY_TABLES["drug"],
        )

        count_query = [q for q in db.queries if "COUNT(*)" in q]
        assert len(count_query) >= 1
        assert "quality_score" in count_query[0].lower()


class TestBrowseCompaniesEnriched:
    """browse_entities for companies should return drug_count, trial_count, pipeline_score."""

    def _make_company_row(self, **overrides):
        base = {
            "id": "c1", "_label": "Novo Nordisk", "ticker": "NVO",
            "cik": "0001005286", "country": "Denmark",
            "quality_score": 0.92, "record_status": "active",
            "drug_count": 12, "trial_count": 85, "pipeline_score": 45.0,
        }
        base.update(overrides)
        return base

    def test_company_browse_returns_joined_fields(self):
        """Company rows should include drug_count, trial_count, pipeline_score."""
        from api.routes.catalog import _browse_companies, ENTITY_TABLES

        db = RichMockDB()
        db.set_total(1)
        db.set_fetch_all([self._make_company_row()])

        result = _browse_companies(
            search=None, status=None, quality_min=None,
            sort=None, sort_by=None, sort_dir=None,
            limit_val=50, offset_val=0, db=db, meta=ENTITY_TABLES["company"],
        )

        assert result["entity_type"] == "company"
        row = result["results"][0]
        assert row["drug_count"] == 12
        assert row["trial_count"] == 85
        assert row["pipeline_score"] == 45.0
        assert row["ticker"] == "NVO"
        assert row["country"] == "Denmark"

    def test_company_browse_default_sort_is_pipeline_score(self):
        """Default sort for companies should be pipeline_score DESC."""
        from api.routes.catalog import _browse_companies, ENTITY_TABLES

        db = RichMockDB()
        db.set_total(1)
        db.set_fetch_all([self._make_company_row()])

        _browse_companies(
            search=None, status=None, quality_min=None,
            sort=None, sort_by=None, sort_dir=None,
            limit_val=50, offset_val=0, db=db, meta=ENTITY_TABLES["company"],
        )

        select_query = [q for q in db.queries if "FROM companies c" in q and "LIMIT" in q]
        assert len(select_query) == 1
        assert "pipeline_score" in select_query[0].lower()
        assert "DESC" in select_query[0]

    def test_company_browse_search(self):
        """Search should filter by name and ticker."""
        from api.routes.catalog import _browse_companies, ENTITY_TABLES

        db = RichMockDB()
        db.set_total(1)
        db.set_fetch_all([self._make_company_row()])

        _browse_companies(
            search="novo", status=None, quality_min=None,
            sort=None, sort_by=None, sort_dir=None,
            limit_val=50, offset_val=0, db=db, meta=ENTITY_TABLES["company"],
        )

        select_query = [q for q in db.queries if "FROM companies c" in q and "LIMIT" in q]
        assert "ILIKE" in select_query[0]


class TestBrowseTrialsDefault:
    """Trials should default sort to start_date DESC."""

    def test_trial_default_sort_is_recent(self):
        from api.routes.catalog import _resolve_sort

        col, direction = _resolve_sort("trial", None, None, None)
        assert col == "start_date"
        assert direction == "DESC"


class TestBrowseGenericDefault:
    """Non-drug, non-company types should default sort to quality_score DESC."""

    def test_mechanism_default_sort(self):
        from api.routes.catalog import _resolve_sort

        col, direction = _resolve_sort("mechanism", None, None, None)
        assert col == "quality_score"
        assert direction == "DESC"

    def test_article_default_sort(self):
        from api.routes.catalog import _resolve_sort

        col, direction = _resolve_sort("article", None, None, None)
        assert col == "quality_score"
        assert direction == "DESC"


class TestSortParameter:
    """The sort query parameter should override default sort."""

    def test_sort_pipeline_score(self):
        from api.routes.catalog import _resolve_sort

        col, direction = _resolve_sort("drug", "pipeline_score", None, None)
        assert col == "pipeline_score"
        assert direction == "DESC"

    def test_sort_quality(self):
        from api.routes.catalog import _resolve_sort

        col, direction = _resolve_sort("drug", "quality", None, None)
        assert col == "quality_score"
        assert direction == "DESC"

    def test_sort_name(self):
        from api.routes.catalog import _resolve_sort

        col, direction = _resolve_sort("drug", "name", None, None)
        assert col == "_label"
        assert direction == "ASC"

    def test_sort_recent(self):
        from api.routes.catalog import _resolve_sort

        col, direction = _resolve_sort("drug", "recent", None, None)
        assert col == "retrieved_at"
        assert direction == "DESC"

    def test_sort_recent_for_trial(self):
        from api.routes.catalog import _resolve_sort

        col, direction = _resolve_sort("trial", "recent", None, None)
        assert col == "start_date"
        assert direction == "DESC"

    def test_legacy_sort_by_still_works(self):
        from api.routes.catalog import _resolve_sort

        col, direction = _resolve_sort("drug", None, "label", "desc")
        assert col == "_label"
        assert direction == "DESC"

    def test_new_sort_takes_precedence_over_legacy(self):
        from api.routes.catalog import _resolve_sort

        col, direction = _resolve_sort("drug", "quality", "label", "asc")
        assert col == "quality_score"
        assert direction == "DESC"


# ── Test featured endpoint ──

class TestFeaturedEntities:
    """GET /catalog/featured should return top 3 drugs and companies."""

    def test_featured_returns_drugs_and_companies(self):
        from api.routes.catalog import featured_entities

        db = RichMockDB()
        db.set_fetch_all([
            {"id": "d1", "name": "Semaglutide", "brand_name": "Ozempic",
             "entity_type": "drug", "mechanism_name": "GLP-1",
             "company_name": "Novo Nordisk", "pipeline_score": 18.5,
             "trial_count": 42, "quality_score": 0.85},
        ])

        result = featured_entities(db=db)

        assert "featured" in result
        assert "drugs" in result["featured"]
        assert "companies" in result["featured"]

    def test_featured_handles_empty_db(self):
        """featured should return empty lists if DB has no data."""
        from api.routes.catalog import featured_entities

        db = RichMockDB()
        db.set_fetch_all([])

        result = featured_entities(db=db)

        assert result["featured"]["drugs"] == []
        assert result["featured"]["companies"] == []

    def test_featured_handles_mv_missing(self):
        """featured should gracefully handle missing mv_drug_pipeline_strength."""
        from api.routes.catalog import featured_entities

        class FailingDB:
            def fetch_all(self, sql, params=None):
                raise Exception("relation mv_drug_pipeline_strength does not exist")

        result = featured_entities(db=FailingDB())

        assert result["featured"]["drugs"] == []
        assert result["featured"]["companies"] == []


# ── Test source records endpoint ──

class SourceRecordsMockDB:
    """MockDB for source_records endpoint."""

    def __init__(self):
        self._col_rows: list[dict] = []
        self._count: int = 0
        self._records: list[dict] = []

    def fetch_all(self, sql: str, params=None) -> list[dict]:
        sql_lower = sql.lower()
        if "information_schema.columns" in sql_lower:
            return self._col_rows
        if "source_api" in sql_lower and "limit" in sql_lower:
            return self._records
        return []

    def fetch_one(self, sql: str, params=None) -> dict | None:
        sql_lower = sql.lower()
        if "count(*)" in sql_lower:
            return {"total": self._count, "cnt": self._count}
        return None


class TestSourceRecords:
    """GET /catalog/sources/{source_key}/records tests."""

    def test_returns_records_for_known_source(self):
        from api.routes.catalog import source_records

        db = SourceRecordsMockDB()
        db._col_rows = [
            {"column_name": "id", "data_type": "uuid"},
            {"column_name": "generic_name", "data_type": "text"},
            {"column_name": "brand_name", "data_type": "text"},
        ]
        db._count = 500
        db._records = [
            {"id": "d1", "generic_name": "semaglutide", "brand_name": "Ozempic"},
            {"id": "d2", "generic_name": "tirzepatide", "brand_name": "Mounjaro"},
        ]

        result = source_records(source_key="fda_orange_book", entity_type=None, limit=20, offset=0, db=db)

        assert result["source_key"] == "fda_orange_book"
        assert result["entity_type"] == "drug"
        assert result["table"] == "drugs"
        assert len(result["columns"]) == 3
        assert len(result["records"]) == 2
        assert result["total"] == 500
        assert result["limit"] == 20
        assert result["offset"] == 0

    def test_respects_limit_offset(self):
        from api.routes.catalog import source_records

        db = SourceRecordsMockDB()
        db._col_rows = [{"column_name": "id", "data_type": "uuid"}]
        db._count = 100
        db._records = [{"id": "d1"}]

        result = source_records(source_key="fda_orange_book", entity_type=None, limit=5, offset=10, db=db)

        assert result["limit"] == 5
        assert result["offset"] == 10
        assert result["total"] == 100

    def test_returns_404_for_unknown_source(self):
        from api.routes.catalog import source_records
        from fastapi import HTTPException

        db = SourceRecordsMockDB()

        with pytest.raises(HTTPException) as exc_info:
            source_records(source_key="bogus_source", entity_type=None, limit=20, offset=0, db=db)
        assert exc_info.value.status_code == 404

    def test_filters_hidden_columns(self):
        from api.routes.catalog import source_records

        db = SourceRecordsMockDB()
        db._col_rows = [
            {"column_name": "id", "data_type": "uuid"},
            {"column_name": "generic_name", "data_type": "text"},
            {"column_name": "content_hash", "data_type": "text"},
            {"column_name": "molecule_embedding", "data_type": "vector"},
        ]
        db._count = 1
        db._records = [{"id": "d1", "generic_name": "test"}]

        result = source_records(source_key="fda_orange_book", entity_type=None, limit=20, offset=0, db=db)

        col_names = [c["name"] for c in result["columns"]]
        assert "id" in col_names
        assert "generic_name" in col_names
        assert "content_hash" not in col_names
        assert "molecule_embedding" not in col_names

    def test_selects_entity_type(self):
        from api.routes.catalog import source_records

        db = SourceRecordsMockDB()
        db._col_rows = [
            {"column_name": "id", "data_type": "uuid"},
            {"column_name": "patent_number", "data_type": "text"},
        ]
        db._count = 50
        db._records = [{"id": "p1", "patent_number": "US123456"}]

        result = source_records(source_key="fda_orange_book", entity_type="patent", limit=20, offset=0, db=db)

        assert result["entity_type"] == "patent"
        assert result["table"] == "patents"

    def test_rejects_invalid_entity_type(self):
        from api.routes.catalog import source_records
        from fastapi import HTTPException

        db = SourceRecordsMockDB()

        with pytest.raises(HTTPException) as exc_info:
            source_records(source_key="fda_orange_book", entity_type="bogus", limit=20, offset=0, db=db)
        assert exc_info.value.status_code == 400


# ── Test source connections endpoint ──

class SourceConnectionsMockDB:
    """MockDB for source_connections endpoint."""

    def __init__(self):
        self._out_rows: list[dict] = []
        self._in_rows: list[dict] = []
        self._sample_rows: list[dict] = []
        self._call_count = 0

    def fetch_all(self, sql: str, params=None) -> list[dict]:
        sql_lower = sql.lower()
        if "v_entity_labels" in sql_lower:
            return self._sample_rows
        if "group by" in sql_lower:
            # The implementation calls outgoing first, then incoming
            self._call_count += 1
            if self._call_count == 1:
                return self._out_rows
            return self._in_rows
        return []

    def fetch_one(self, sql: str, params=None) -> dict | None:
        return None


class TestSourceConnections:
    """GET /catalog/sources/{source_key}/connections tests."""

    def test_returns_connections_for_known_source(self):
        from api.routes.catalog import source_connections

        db = SourceConnectionsMockDB()
        db._out_rows = [
            {"target_entity_type": "therapeutic_area", "link_type": "TREATS", "count": 500},
            {"target_entity_type": "company", "link_type": "OWNS", "count": 200},
        ]
        db._in_rows = [
            {"source_entity_type": "literature", "link_type": "EVIDENCE_FOR", "count": 1000},
        ]

        result = source_connections(source_key="fda_orange_book", db=db)

        assert result["source_key"] == "fda_orange_book"
        assert result["total_outgoing"] == 700
        assert result["total_incoming"] == 1000
        assert len(result["connections"]) >= 1

    def test_returns_404_for_unknown_source(self):
        from api.routes.catalog import source_connections
        from fastapi import HTTPException

        db = SourceConnectionsMockDB()

        with pytest.raises(HTTPException) as exc_info:
            source_connections(source_key="bogus_source", db=db)
        assert exc_info.value.status_code == 404

    def test_returns_empty_connections_for_source_with_no_links(self):
        from api.routes.catalog import source_connections

        db = SourceConnectionsMockDB()

        result = source_connections(source_key="fda_orange_book", db=db)

        assert result["connections"] == []
        assert result["total_outgoing"] == 0
        assert result["total_incoming"] == 0


class TestBrowseRejectsUnknownType:
    """browse_entities should 400 for unknown entity types."""

    def test_unknown_type_raises_400(self):
        from api.routes.catalog import browse_entities
        from fastapi import HTTPException

        db = RichMockDB()
        with pytest.raises(HTTPException) as exc_info:
            browse_entities(
                entity_type="bogus", search=None, status=None,
                quality_min=None, sort=None, sort_by=None, sort_dir=None,
                limit=50, offset=0, db=db,
            )
        assert exc_info.value.status_code == 400


# ── Test entity-events endpoint ──


class EventsMockDB:
    """MockDB that supports the UNION-style entity-events queries."""

    def __init__(self):
        self._table_results: dict[str, list[dict]] = {}
        self._table_exists: set[str] = set()
        self.queries: list[str] = []

    class conn:
        """Fake conn for rollback calls."""
        @staticmethod
        def rollback():
            pass

    def add_table(self, table_name: str, rows: list[dict] | None = None):
        self._table_exists.add(table_name)
        if rows is not None:
            self._table_results[table_name] = rows

    def fetch_one(self, sql: str, params=None) -> dict | None:
        self.queries.append(sql)
        sql_lower = sql.lower()
        if "information_schema" in sql_lower:
            # Check if table exists
            for tbl in self._table_exists:
                if tbl in str(params):
                    return {"exists_": True}
            return {"exists_": False}
        return None

    def fetch_all(self, sql: str, params=None) -> list[dict]:
        self.queries.append(sql)
        sql_lower = sql.lower()
        for table_name, rows in self._table_results.items():
            if table_name in sql_lower:
                return list(rows)
        return []


class TestEntityEvents:
    """GET /catalog/entity-events/{entity_type}/{entity_id} tests."""

    def test_returns_events_for_known_entity(self):
        """Endpoint should return events from multiple sources."""
        from api.routes.catalog import entity_events
        from datetime import datetime, timezone

        db = EventsMockDB()
        now = datetime.now(timezone.utc)

        db.add_table("data_change_log", [
            {"change_type": "manual_edit", "changed_fields": ["brand_name"],
             "changed_at": now},
        ])
        db.add_table("steward_actions", [
            {"action_type": "enrich", "details": "Added brand name",
             "status": "completed", "completed_at": now},
        ])
        db.add_table("market_events", [
            {"event_type": "approval", "description": "FDA approval granted",
             "source_url": "https://fda.gov", "event_date": now, "created_at": now},
        ])
        # entity_links always queried (no _table_exists check)
        db._table_results["entity_links"] = [
            {"link_type": "TREATS", "target_entity_type": "therapeutic_area",
             "target_entity_id": "ta1", "source_entity_type": "drug",
             "source_entity_id": "d1", "provenance_source": "cross_linker",
             "created_at": now},
        ]

        result = entity_events(entity_type="drug", entity_id="d1", limit=10, db=db)

        assert "events" in result
        assert "total" in result
        assert result["total"] >= 1
        event_types = {e["event_type"] for e in result["events"]}
        # Should have at least field_change and new_connection
        assert "field_change" in event_types
        assert "new_connection" in event_types

    def test_empty_events_for_entity_with_no_activity(self):
        """Endpoint should return empty list for entity with no events."""
        from api.routes.catalog import entity_events

        db = EventsMockDB()
        # Tables exist but return no rows
        db.add_table("data_change_log", [])
        db.add_table("steward_actions", [])
        db.add_table("market_events", [])

        result = entity_events(entity_type="drug", entity_id="d-none", limit=10, db=db)

        assert result["events"] == []
        assert result["total"] == 0

    def test_respects_limit_parameter(self):
        """Limit should cap the number of returned events."""
        from api.routes.catalog import entity_events
        from datetime import datetime, timezone, timedelta

        db = EventsMockDB()
        now = datetime.now(timezone.utc)

        # Provide many entity_links results
        db.add_table("data_change_log", [])
        db.add_table("steward_actions", [])
        db.add_table("market_events", [])
        db._table_results["entity_links"] = [
            {"link_type": "TREATS", "target_entity_type": "therapeutic_area",
             "target_entity_id": f"ta{i}", "source_entity_type": "drug",
             "source_entity_id": "d1", "provenance_source": "cross_linker",
             "created_at": now - timedelta(hours=i)}
            for i in range(20)
        ]

        result = entity_events(entity_type="drug", entity_id="d1", limit=3, db=db)

        assert len(result["events"]) <= 3
        assert result["total"] >= 3

    def test_rejects_unknown_entity_type(self):
        """Unknown entity type should raise 400."""
        from api.routes.catalog import entity_events
        from fastapi import HTTPException

        db = EventsMockDB()

        with pytest.raises(HTTPException) as exc_info:
            entity_events(entity_type="bogus_type", entity_id="x", limit=10, db=db)
        assert exc_info.value.status_code == 400
