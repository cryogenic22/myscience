"""Tests for entity dossier view — Sprint 5.

Validates that the catalog entity_detail endpoint returns data shapes
matching what the EntityDossier frontend component expects:
- entity dict with type-specific fields
- entity_type string
- quality_results, change_log, links, tags, aliases arrays
- editable_fields array

Also tests the API contract for each entity type's structured sections.
"""

from __future__ import annotations

import re
from unittest.mock import patch

import pytest
from fastapi import HTTPException


class MockDB:
    """Lightweight DB stub for catalog API tests."""

    def __init__(self):
        self._results: dict[str, list[dict]] = {}
        self._fetch_one_results: dict[str, dict] = {}
        self._tables: set[str] = set()
        self.executed: list[tuple[str, list]] = []

    def set_results(self, key: str, results: list[dict]):
        self._results[key] = results

    def set_table_exists(self, table: str):
        self._tables.add(table)

    def fetch_all(self, sql: str, params=None) -> list[dict]:
        sql_lower = sql.lower()
        # Check for entity_links
        if "entity_links" in sql_lower:
            return self._results.get("entity_links", [])
        if "data_quality" in sql_lower:
            return self._results.get("data_quality_results", [])
        if "data_change_log" in sql_lower:
            return self._results.get("data_change_log", [])
        if "entity_tags" in sql_lower:
            return self._results.get("entity_tags", [])
        if "entity_aliases" in sql_lower:
            return self._results.get("entity_aliases", [])
        from_match = re.search(r"\bfrom\s+(\w+)", sql_lower)
        if from_match:
            primary = from_match.group(1)
            if primary in self._results:
                return self._results[primary]
        return []

    def fetch_one(self, sql: str, params=None) -> dict | None:
        sql_lower = sql.lower()
        if "information_schema" in sql_lower:
            # Check if the table is in our known set
            table_match = re.search(r"table_name\s*=\s*'(\w+)'", sql_lower)
            if table_match and table_match.group(1) in self._tables:
                return {"exists_": True}
            # Default: table doesn't exist
            return None
        from_match = re.search(r"\bfrom\s+(\w+)", sql_lower)
        if from_match:
            primary = from_match.group(1)
            if primary in self._results and self._results[primary]:
                return self._results[primary][0]
        return None

    def execute(self, sql: str, params=None) -> None:
        self.executed.append((sql, params or []))


# ── Fixtures ──


def _make_drug_row() -> dict:
    return {
        "id": "d-001",
        "generic_name": "semaglutide",
        "brand_name": "Ozempic",
        "company_id": "c-001",
        "therapeutic_area_id": "ta-001",
        "mechanism_id": "m-001",
        "approval_date": "2017-12-05",
        "patent_expiry_date": "2032-01-01",
        "supply_status": "adequate",
        "source_authority": "FDA",
        "source_api": "fda_orange_book",
        "record_status": "active",
        "quality_score": 0.85,
        "content_hash": "abc123",
        "last_verified_at": "2026-03-01",
        "retrieved_at": "2026-03-01",
        "_label": "semaglutide",
    }


def _make_company_row() -> dict:
    return {
        "id": "c-001",
        "name": "Novo Nordisk",
        "ticker": "NVO",
        "cik": "12345",
        "region": "Europe",
        "country": "Denmark",
        "market_cap_tier": "large_cap",
        "sic_code": "2836",
        "source_api": "sec_edgar",
        "record_status": "active",
        "quality_score": 0.9,
        "content_hash": "xyz789",
        "last_verified_at": "2026-03-01",
        "retrieved_at": "2026-03-01",
        "_label": "Novo Nordisk",
    }


def _make_trial_row() -> dict:
    return {
        "id": "NCT12345678",
        "official_title": "SUSTAIN-6: A Long-term Outcomes Trial",
        "drug_id": "d-001",
        "sponsor_name": "Novo Nordisk",
        "status": "Completed",
        "phase": "Phase 3",
        "conditions": "Type 2 Diabetes",
        "enrollment_target": 3297,
        "start_date": "2013-02-01",
        "primary_completion_date": "2016-03-01",
        "study_type": "Interventional",
        "record_status": "active",
        "quality_score": 0.92,
        "source_api": "clinical_trials_gov",
        "retrieved_at": "2026-03-01",
        "_label": "SUSTAIN-6: A Long-term Outcomes Trial",
    }


def _make_links() -> list[dict]:
    return [
        {
            "source_entity_id": "d-001",
            "source_entity_type": "drug",
            "target_entity_id": "c-001",
            "target_entity_type": "company",
            "link_type": "manufactured_by",
            "confidence": 0.95,
            "provenance_source": "fda_orange_book",
        },
        {
            "source_entity_id": "d-001",
            "source_entity_type": "drug",
            "target_entity_id": "NCT12345678",
            "target_entity_type": "trial",
            "link_type": "tested_in",
            "confidence": 0.88,
            "provenance_source": "clinical_trials_gov",
        },
        {
            "source_entity_id": "d-001",
            "source_entity_type": "drug",
            "target_entity_id": "NCT99999999",
            "target_entity_type": "trial",
            "link_type": "tested_in",
            "confidence": 0.75,
            "provenance_source": "clinical_trials_gov",
        },
    ]


# ── Tests ──


class TestEntityDetailDrugResponse:
    """entity_detail for drug returns all fields EntityDossier needs."""

    def test_drug_detail_shape(self):
        from api.routes.catalog import entity_detail

        db = MockDB()
        db.set_results("drugs", [_make_drug_row()])
        db.set_results("entity_links", _make_links())
        db.set_results("data_quality_results", [])
        db.set_results("data_change_log", [])
        db.set_results("entity_tags", [])
        db.set_results("entity_aliases", [])

        result = entity_detail("drug", "d-001", db=db)

        # Top-level keys
        assert "entity" in result
        assert "entity_type" in result
        assert "quality_results" in result
        assert "change_log" in result
        assert "links" in result
        assert "tags" in result
        assert "aliases" in result
        assert "editable_fields" in result

        assert result["entity_type"] == "drug"

    def test_drug_entity_has_identity_fields(self):
        from api.routes.catalog import entity_detail

        db = MockDB()
        db.set_results("drugs", [_make_drug_row()])
        db.set_results("entity_links", [])

        result = entity_detail("drug", "d-001", db=db)
        entity = result["entity"]

        # Identity section fields
        assert entity["generic_name"] == "semaglutide"
        assert entity["brand_name"] == "Ozempic"
        assert "company_id" in entity
        assert "mechanism_id" in entity
        assert "therapeutic_area_id" in entity

    def test_drug_entity_has_pipeline_fields(self):
        from api.routes.catalog import entity_detail

        db = MockDB()
        db.set_results("drugs", [_make_drug_row()])
        db.set_results("entity_links", [])

        result = entity_detail("drug", "d-001", db=db)
        entity = result["entity"]

        # Pipeline section fields
        assert "approval_date" in entity
        assert "supply_status" in entity
        assert entity["supply_status"] == "adequate"

    def test_drug_links_returned(self):
        from api.routes.catalog import entity_detail

        db = MockDB()
        db.set_results("drugs", [_make_drug_row()])
        db.set_results("entity_links", _make_links())

        result = entity_detail("drug", "d-001", db=db)

        assert len(result["links"]) == 3
        link_types = {l["link_type"] for l in result["links"]}
        assert "manufactured_by" in link_types
        assert "tested_in" in link_types


class TestEntityDetailCompanyResponse:
    """entity_detail for company returns all fields EntityDossier needs."""

    def test_company_detail_shape(self):
        from api.routes.catalog import entity_detail

        db = MockDB()
        db.set_results("companies", [_make_company_row()])
        db.set_results("entity_links", [])

        result = entity_detail("company", "c-001", db=db)

        assert result["entity_type"] == "company"
        entity = result["entity"]

        # Identity section
        assert entity["name"] == "Novo Nordisk"
        assert entity["ticker"] == "NVO"
        assert entity["cik"] == "12345"
        assert entity["country"] == "Denmark"
        assert entity["region"] == "Europe"

        # Portfolio section
        assert "market_cap_tier" in entity

    def test_company_editable_fields(self):
        from api.routes.catalog import entity_detail

        db = MockDB()
        db.set_results("companies", [_make_company_row()])
        db.set_results("entity_links", [])

        result = entity_detail("company", "c-001", db=db)

        editable = result["editable_fields"]
        assert "region" in editable
        assert "country" in editable
        assert "market_cap_tier" in editable


class TestEntityDetailTrialResponse:
    """entity_detail for trial returns all fields EntityDossier needs."""

    def test_trial_detail_shape(self):
        from api.routes.catalog import entity_detail

        db = MockDB()
        db.set_results("clinical_trials", [_make_trial_row()])
        db.set_results("entity_links", [])

        result = entity_detail("trial", "NCT12345678", db=db)

        assert result["entity_type"] == "trial"
        entity = result["entity"]

        # Identity section
        assert "official_title" in entity
        assert entity["phase"] == "Phase 3"
        assert entity["status"] == "Completed"
        assert entity["sponsor_name"] == "Novo Nordisk"

        # Design section
        assert entity["enrollment_target"] == 3297
        assert "start_date" in entity
        assert "primary_completion_date" in entity
        assert entity["study_type"] == "Interventional"
        assert entity["conditions"] == "Type 2 Diabetes"

    def test_trial_not_found(self):
        from api.routes.catalog import entity_detail

        db = MockDB()
        db.set_results("clinical_trials", [])
        db.set_results("entity_links", [])

        with pytest.raises(HTTPException) as exc_info:
            entity_detail("trial", "NCT_NONEXISTENT", db=db)
        assert exc_info.value.status_code == 404


class TestEntityDetailInvalidType:
    """Reject unknown entity types."""

    def test_rejects_unknown_type(self):
        from api.routes.catalog import entity_detail

        db = MockDB()

        with pytest.raises(HTTPException) as exc_info:
            entity_detail("unicorn", "u-001", db=db)
        assert exc_info.value.status_code == 400


class TestEntityDossierConnectionCounts:
    """Verify link grouping logic mirrors frontend connection counting."""

    def test_links_group_by_entity_type(self):
        links = _make_links()

        # Mirror the frontend connectionSummary logic
        entity_id = "d-001"
        counts: dict[str, int] = {}
        for link in links:
            is_src = link["source_entity_id"] == entity_id
            related_type = link["target_entity_type"] if is_src else link["source_entity_type"]
            counts[related_type] = counts.get(related_type, 0) + 1

        assert counts["company"] == 1
        assert counts["trial"] == 2

    def test_empty_links_produce_no_connections(self):
        links: list[dict] = []
        entity_id = "d-001"
        counts: dict[str, int] = {}
        for link in links:
            is_src = link["source_entity_id"] == entity_id
            related_type = link["target_entity_type"] if is_src else link["source_entity_type"]
            counts[related_type] = counts.get(related_type, 0) + 1

        assert len(counts) == 0
