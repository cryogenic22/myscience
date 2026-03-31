"""Tests for GET /catalog/source-profile/{source_key} endpoint.

TDD: Verify source metadata, entity breakdown, field completeness, and 404 for unknown sources.
Uses MockDB to avoid real database dependency.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

import pytest


class MockDB:
    """Mock database that routes queries based on SQL content."""

    def __init__(self):
        self._fetch_all_results: dict[str, list[dict]] = {}
        self._fetch_one_results: dict[str, dict] = {}
        self.queries: list[tuple[str, list]] = []

    def add_fetch_all(self, key: str, rows: list[dict]):
        """Register rows returned when `key` appears in the SQL."""
        self._fetch_all_results[key] = rows

    def add_fetch_one(self, key: str, row: dict):
        """Register a single-row result when `key` appears in the SQL."""
        self._fetch_one_results[key] = row

    def fetch_all(self, sql: str, params=None) -> list[dict]:
        self.queries.append((sql, params or []))
        sql_lower = sql.lower()
        for key, rows in self._fetch_all_results.items():
            if key.lower() in sql_lower:
                return rows
        return []

    def fetch_one(self, sql: str, params=None) -> dict | None:
        self.queries.append((sql, params or []))
        sql_lower = sql.lower()
        # Check specific overrides first
        for key, row in self._fetch_one_results.items():
            if key.lower() in sql_lower:
                return row
        # Default for information_schema
        if "information_schema" in sql_lower:
            return {"exists_": True}
        return None

    def execute(self, sql: str, params=None) -> None:
        self.queries.append((sql, params or []))


class TestSourceProfile:
    """Tests for the source_profile endpoint."""

    def test_returns_source_metadata(self):
        """source_profile should return label, schedule, and status for a known source."""
        from api.routes.catalog import source_profile

        db = MockDB()
        now = datetime.now(timezone.utc)

        # Freshness query: MAX(retrieved_at), COUNT(*)
        db.add_fetch_one(
            "max(retrieved_at)",
            {"latest": now, "total_records": 7205},
        )
        # Entity breakdown query
        db.add_fetch_all("group by entity_type", [
            {"entity_type": "trial", "count": 5307},
            {"entity_type": "investigator", "count": 800},
        ])
        # Field completeness
        db.add_fetch_one("count(*) as total", {"total": 5307})
        db.add_fetch_all("is not null", [
            {"field": "phase", "filled": 5100, "total": 5307},
        ])

        result = source_profile(source_key="clinical_trials_gov", db=db)

        assert result["source_key"] == "clinical_trials_gov"
        assert result["label"] == "ClinicalTrials.gov"
        assert "schedule" in result
        assert result["status"] in ("fresh", "ok", "stale", "never")

    def test_returns_entity_breakdown(self):
        """source_profile should include entity_breakdown with per-type counts."""
        from api.routes.catalog import source_profile

        db = MockDB()
        now = datetime.now(timezone.utc)

        db.add_fetch_one(
            "max(retrieved_at)",
            {"latest": now, "total_records": 6107},
        )
        db.add_fetch_all("group by entity_type", [
            {"entity_type": "trial", "count": 5307},
            {"entity_type": "investigator", "count": 800},
        ])

        result = source_profile(source_key="clinical_trials_gov", db=db)

        assert "entity_breakdown" in result
        assert isinstance(result["entity_breakdown"], list)
        # Should have entries from our mock
        if result["entity_breakdown"]:
            first = result["entity_breakdown"][0]
            assert "entity_type" in first
            assert "count" in first

    def test_returns_field_completeness(self):
        """source_profile should include field_completeness for the primary entity type."""
        from api.routes.catalog import source_profile

        db = MockDB()
        now = datetime.now(timezone.utc)

        db.add_fetch_one(
            "max(retrieved_at)",
            {"latest": now, "total_records": 500},
        )
        db.add_fetch_all("group by entity_type", [
            {"entity_type": "drug", "count": 500},
        ])

        result = source_profile(source_key="fda_orange_book", db=db)

        assert "field_completeness" in result
        assert isinstance(result["field_completeness"], list)

    def test_404_for_unknown_source(self):
        """source_profile should raise 404 for unrecognized source keys."""
        from api.routes.catalog import source_profile
        from fastapi import HTTPException

        db = MockDB()

        with pytest.raises(HTTPException) as exc_info:
            source_profile(source_key="totally_bogus_source", db=db)
        assert exc_info.value.status_code == 404

    def test_returns_total_records(self):
        """source_profile should include total_records count."""
        from api.routes.catalog import source_profile

        db = MockDB()
        now = datetime.now(timezone.utc)

        db.add_fetch_one(
            "max(retrieved_at)",
            {"latest": now, "total_records": 9999},
        )

        result = source_profile(source_key="pubmed", db=db)

        assert "total_records" in result

    def test_returns_cross_source_links(self):
        """source_profile should include cross_source_links."""
        from api.routes.catalog import source_profile

        db = MockDB()
        now = datetime.now(timezone.utc)

        db.add_fetch_one(
            "max(retrieved_at)",
            {"latest": now, "total_records": 100},
        )
        db.add_fetch_all("cross_source", [
            {"target_source": "pubmed", "link_type": "EVIDENCE_FOR", "count": 120},
        ])

        result = source_profile(source_key="clinical_trials_gov", db=db)

        assert "cross_source_links" in result
        assert isinstance(result["cross_source_links"], list)

    def test_returns_steward_actions(self):
        """source_profile should include recent steward_actions."""
        from api.routes.catalog import source_profile

        db = MockDB()
        now = datetime.now(timezone.utc)

        db.add_fetch_one(
            "max(retrieved_at)",
            {"latest": now, "total_records": 100},
        )
        db.add_fetch_all("steward_actions", [
            {"action_type": "backfill_ta", "status": "completed",
             "created_at": now, "entity_name": "TA links"},
        ])

        result = source_profile(source_key="clinical_trials_gov", db=db)

        assert "steward_actions" in result
        assert isinstance(result["steward_actions"], list)

    def test_never_status_when_no_data(self):
        """source_profile should return status='never' when no data exists for a source."""
        from api.routes.catalog import source_profile

        db = MockDB()

        # Return None for freshness query — no data found
        db.add_fetch_one(
            "max(retrieved_at)",
            {"latest": None, "total_records": 0},
        )

        result = source_profile(source_key="ema", db=db)

        assert result["status"] == "never"
        assert result["total_records"] == 0
        assert result["last_run"] is None

    def test_days_since_calculated(self):
        """source_profile should include days_since as a float."""
        from api.routes.catalog import source_profile

        db = MockDB()
        now = datetime.now(timezone.utc)

        db.add_fetch_one(
            "max(retrieved_at)",
            {"latest": now, "total_records": 100},
        )

        result = source_profile(source_key="clinical_trials_gov", db=db)

        assert "days_since" in result
        # Should be very small since we used 'now'
        if result["days_since"] is not None:
            assert result["days_since"] < 1.0
