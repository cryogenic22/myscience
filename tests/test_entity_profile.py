"""Tests for GET /catalog/entity-profile/{entity_type}/{entity_id}.

TDD: Verify the rich entity profile returns identity, FAIR scores,
AI readiness, connections, evidence, provenance, and recent changes.
Uses MockDB with dispatch pattern — no real database required.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone, timedelta

import pytest


class MockDB:
    """Mock database for entity-profile tests.

    Dispatches on SQL content to return pre-configured results.
    """

    def __init__(self):
        self._dispatch: list[tuple[str, object]] = []

    def when(self, pattern: str, result):
        """Register a SQL pattern → result mapping."""
        self._dispatch.append((pattern.lower(), result))
        return self

    def fetch_one(self, sql: str, params=None) -> dict | None:
        sql_lower = sql.lower()
        if "information_schema" in sql_lower:
            return {"exists_": True}
        for pattern, result in self._dispatch:
            if pattern in sql_lower:
                if isinstance(result, list):
                    return result[0] if result else None
                return result
        return None

    def fetch_all(self, sql: str, params=None) -> list[dict]:
        sql_lower = sql.lower()
        for pattern, result in self._dispatch:
            if pattern in sql_lower:
                if isinstance(result, list):
                    return result
                return [result] if result else []
        return []

    def execute(self, sql: str, params=None) -> None:
        pass


def _make_drug_row(retrieved_at=None, quality_score=None):
    """Build a realistic drug row dict."""
    return {
        "id": "aaaaaaaa-1111-2222-3333-444444444444",
        "generic_name": "semaglutide",
        "brand_name": "Ozempic",
        "company_id": "bbbbbbbb-1111-2222-3333-444444444444",
        "therapeutic_area_id": "cccccccc-1111-2222-3333-444444444444",
        "mechanism_id": "dddddddd-1111-2222-3333-444444444444",
        "approval_date": "2017-12-05",
        "patent_expiry_date": None,
        "supply_status": "available",
        "source_authority": "fda",
        "source_api": "fda_orange_book",
        "record_status": "verified",
        "quality_score": quality_score if quality_score is not None else 0.85,
        "content_hash": "abc123",
        "last_verified_at": datetime.now(timezone.utc),
        "retrieved_at": retrieved_at if retrieved_at is not None else datetime.now(timezone.utc),
        "pubchem_cid": "56843592",
        "canonical_smiles": None,
        "inchi_key": None,
        "molecular_formula": None,
        "molecular_weight": None,
        "xlogp": None,
        "tpsa": None,
    }


def _build_db_for_drug(drug_row=None):
    """Build a MockDB pre-wired for a drug entity profile request."""
    if drug_row is None:
        drug_row = _make_drug_row()
    db = MockDB()
    entity_id = drug_row["id"]

    # Entity fetch
    db.when("from drugs where", drug_row)

    # Link count
    db.when("count(*) as c from entity_links", {"c": 12})

    # Source diversity
    db.when("distinct source_api from entity_links", [
        {"source_api": "fda_orange_book"},
        {"source_api": "clinical_trials_gov"},
        {"source_api": "pubmed"},
    ])

    # Embedding check
    db.when("molecule_embedding is not null", {"has_emb": True})

    # Link existence
    db.when("exists", {"has_link": True})

    # Connections grouped by type
    db.when("link_type, count", [
        {"connected_type": "trial", "cnt": 8, "sample_labels": ["NCT001", "NCT002", "NCT003"]},
        {"connected_type": "company", "cnt": 1, "sample_labels": ["Novo Nordisk"]},
    ])

    # Evidence trail
    db.when("evidence", [
        {"title": "Semaglutide Phase 3 Results", "entity_type": "article",
         "publication_date": "2020-01-15", "link_type": "INVESTIGATES"},
    ])

    # Provenance
    db.when("distinct el.provenance_source", [
        {"provenance_source": "fda_orange_book"},
        {"provenance_source": "clinical_trials_gov"},
    ])

    # Change log
    db.when("data_change_log", [
        {"id": 1, "change_type": "updated", "changed_fields": '{"quality_score": 0.85}',
         "changed_at": datetime.now(timezone.utc)},
    ])

    return db


class TestEntityProfileIdentity:
    """identity section — basic entity data."""

    def test_returns_identity_section(self):
        from api.routes.catalog import entity_profile

        db = _build_db_for_drug()
        result = entity_profile("drug", "aaaaaaaa-1111-2222-3333-444444444444", db=db)

        assert "identity" in result
        assert result["identity"]["generic_name"] == "semaglutide"
        assert result["identity"]["brand_name"] == "Ozempic"
        assert result["entity_type"] == "drug"

    def test_404_for_missing_entity(self):
        from api.routes.catalog import entity_profile
        from fastapi import HTTPException

        db = MockDB()
        # No entity row registered — fetch_one returns None

        with pytest.raises(HTTPException) as exc_info:
            entity_profile("drug", "nonexistent-id", db=db)
        assert exc_info.value.status_code == 404

    def test_400_for_unknown_entity_type(self):
        from api.routes.catalog import entity_profile
        from fastapi import HTTPException

        db = MockDB()
        with pytest.raises(HTTPException) as exc_info:
            entity_profile("unicorn", "some-id", db=db)
        assert exc_info.value.status_code == 400


class TestEntityProfileFAIR:
    """fair_scores section — all dimensions between 0 and 1."""

    def test_returns_fair_scores_between_0_and_1(self):
        from api.routes.catalog import entity_profile

        db = _build_db_for_drug()
        result = entity_profile("drug", "aaaaaaaa-1111-2222-3333-444444444444", db=db)

        assert "fair_scores" in result
        scores = result["fair_scores"]
        for key in ("completeness", "link_density", "source_diversity",
                    "freshness", "resolution", "overall"):
            assert key in scores, f"Missing FAIR dimension: {key}"
            assert 0.0 <= scores[key] <= 1.0, f"{key} out of range: {scores[key]}"

    def test_completeness_reflects_filled_fields(self):
        from api.routes.catalog import entity_profile

        # Drug with most recommended fields filled
        drug = _make_drug_row()
        db = _build_db_for_drug(drug)
        result = entity_profile("drug", drug["id"], db=db)

        # generic_name, brand_name, company_id, ta_id, mechanism_id, approval_date
        # are all filled — completeness should be high
        assert result["fair_scores"]["completeness"] > 0.5

    def test_freshness_decays_with_age(self):
        from api.routes.catalog import entity_profile

        # Old record: 60 days ago
        old_date = datetime.now(timezone.utc) - timedelta(days=60)
        drug = _make_drug_row(retrieved_at=old_date)
        db = _build_db_for_drug(drug)
        result = entity_profile("drug", drug["id"], db=db)

        # 60/90 = 0.667 decay → freshness should be ~0.33
        assert result["fair_scores"]["freshness"] < 0.5

    def test_resolution_uses_quality_score(self):
        from api.routes.catalog import entity_profile

        drug = _make_drug_row(quality_score=0.92)
        db = _build_db_for_drug(drug)
        result = entity_profile("drug", drug["id"], db=db)

        assert abs(result["fair_scores"]["resolution"] - 0.92) < 0.01


class TestEntityProfileAIReadiness:
    """ai_readiness section — boolean indicators."""

    def test_returns_ai_readiness_booleans(self):
        from api.routes.catalog import entity_profile

        db = _build_db_for_drug()
        result = entity_profile("drug", "aaaaaaaa-1111-2222-3333-444444444444", db=db)

        assert "ai_readiness" in result
        ai = result["ai_readiness"]
        for key in ("has_embedding", "is_linked", "is_resolved"):
            assert key in ai, f"Missing AI readiness field: {key}"
            assert isinstance(ai[key], bool), f"{key} should be bool, got {type(ai[key])}"


class TestEntityProfileConnections:
    """connections section — grouped by entity type."""

    def test_returns_connections_grouped_by_type(self):
        from api.routes.catalog import entity_profile

        db = _build_db_for_drug()
        result = entity_profile("drug", "aaaaaaaa-1111-2222-3333-444444444444", db=db)

        assert "connections" in result
        conns = result["connections"]
        assert isinstance(conns, list)


class TestEntityProfileEvidence:
    """evidence section — linked literature/trial items."""

    def test_returns_evidence_trail(self):
        from api.routes.catalog import entity_profile

        db = _build_db_for_drug()
        result = entity_profile("drug", "aaaaaaaa-1111-2222-3333-444444444444", db=db)

        assert "evidence" in result
        assert isinstance(result["evidence"], list)


class TestEntityProfileProvenance:
    """provenance section — distinct source APIs."""

    def test_returns_provenance_sources(self):
        from api.routes.catalog import entity_profile

        db = _build_db_for_drug()
        result = entity_profile("drug", "aaaaaaaa-1111-2222-3333-444444444444", db=db)

        assert "provenance" in result
        assert isinstance(result["provenance"], list)
        assert len(result["provenance"]) > 0
