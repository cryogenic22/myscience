"""Tests for WHO GPRM international drug pricing connector.

TDD: Covers GPRM record parsing, country/currency extraction, ATC code mapping,
drug matching, multi-country storage, and run() integration.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Optional

import pytest


# ── MockDB (matches project pattern from test_drug_pricing.py) ──

class MockDB:
    """Lightweight DB mock that routes queries by table name."""

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
        results = self.fetch_all(sql, params)
        return results[0] if results else None

    def execute(self, sql: str, params=None) -> None:
        self.executed.append((sql, params or []))


# ============================================================
# TestGPRMParsing — raw WHO GPRM records -> structured pricing
# ============================================================

class TestGPRMParsing:
    """Verify parsing of WHO GPRM medicine price records."""

    def test_parses_gprm_record(self):
        """Raw GPRM JSON -> structured pricing record with correct fields."""
        from scripts.fetch_who_gprm import parse_gprm_records

        raw = [
            {
                "medicine_name": "Metformin",
                "dosage_form": "Tablet",
                "strength": "500mg",
                "country": "France",
                "price_per_unit": 0.045,
                "currency": "EUR",
                "price_type": "public",
                "year": 2025,
                "atc_code": "A10BA02",
            }
        ]
        result = parse_gprm_records(raw)
        assert len(result) == 1
        rec = result[0]
        assert rec["drug_name"] == "Metformin"
        assert rec["unit_price"] == pytest.approx(0.045)
        assert rec["price_type"] == "gprm_public"
        assert rec["currency"] == "EUR"
        assert rec["country"] == "France"
        assert rec["source_api"] == "who_gprm"
        assert rec["effective_date"] == date(2025, 1, 1)

    def test_extracts_country_and_currency(self):
        """Country and currency extracted correctly from GPRM record."""
        from scripts.fetch_who_gprm import parse_gprm_records

        raw = [
            {
                "medicine_name": "Atorvastatin",
                "dosage_form": "Tablet",
                "strength": "10mg",
                "country": "Brazil",
                "price_per_unit": 0.12,
                "currency": "BRL",
                "price_type": "retail",
                "year": 2024,
                "atc_code": "C10AA05",
            }
        ]
        result = parse_gprm_records(raw)
        assert len(result) == 1
        assert result[0]["country"] == "Brazil"
        assert result[0]["currency"] == "BRL"

    def test_handles_missing_price(self):
        """Null price -> record skipped."""
        from scripts.fetch_who_gprm import parse_gprm_records

        raw = [
            {
                "medicine_name": "Metformin",
                "dosage_form": "Tablet",
                "strength": "500mg",
                "country": "France",
                "price_per_unit": None,
                "currency": "EUR",
                "price_type": "public",
                "year": 2025,
                "atc_code": "A10BA02",
            }
        ]
        result = parse_gprm_records(raw)
        assert len(result) == 0

    def test_maps_atc_to_drug_name(self):
        """When medicine_name missing, ATC description used as drug name."""
        from scripts.fetch_who_gprm import parse_gprm_records

        raw = [
            {
                "medicine_name": "",
                "dosage_form": "Tablet",
                "strength": "500mg",
                "country": "Germany",
                "price_per_unit": 0.03,
                "currency": "EUR",
                "price_type": "public",
                "year": 2025,
                "atc_code": "A10BA02",
                "atc_description": "Metformin",
            }
        ]
        result = parse_gprm_records(raw)
        assert len(result) == 1
        assert result[0]["drug_name"] == "Metformin"


# ============================================================
# TestGPRMDrugMatching — match GPRM names to drugs table
# ============================================================

class TestGPRMDrugMatching:
    """Verify drug matching and storage for GPRM records."""

    def test_matches_drug_by_name(self):
        """'metformin' -> drugs table match by generic_name."""
        from scripts.fetch_who_gprm import match_drugs

        db = MockDB()
        db.set_results("drugs", [{"id": "d001-uuid"}])

        records = [
            {
                "drug_name": "Metformin",
                "price_type": "gprm_public",
                "unit_price": 0.045,
                "unit": "per tablet",
                "currency": "EUR",
                "country": "France",
                "source_api": "who_gprm",
                "source_url": None,
                "effective_date": date(2025, 1, 1),
                "strength": "500mg",
                "dosage_form": "Tablet",
                "atc_code": "A10BA02",
            }
        ]
        matched = match_drugs(db, records)
        assert len(matched) == 1
        assert matched[0]["drug_id"] == "d001-uuid"

    def test_stores_with_country(self):
        """Country field populated correctly in matched record."""
        from scripts.fetch_who_gprm import match_drugs

        db = MockDB()
        db.set_results("drugs", [{"id": "d001-uuid"}])

        records = [
            {
                "drug_name": "Atorvastatin",
                "price_type": "gprm_retail",
                "unit_price": 0.12,
                "unit": "per tablet",
                "currency": "BRL",
                "country": "Brazil",
                "source_api": "who_gprm",
                "source_url": None,
                "effective_date": date(2024, 1, 1),
                "strength": "10mg",
                "dosage_form": "Tablet",
                "atc_code": "C10AA05",
            }
        ]
        matched = match_drugs(db, records)
        assert matched[0]["country"] == "Brazil"
        assert matched[0]["currency"] == "BRL"

    def test_multiple_countries_stored(self):
        """Same drug, different countries -> multiple matched rows."""
        from scripts.fetch_who_gprm import match_drugs

        db = MockDB()
        db.set_results("drugs", [{"id": "d001-uuid"}])

        records = [
            {
                "drug_name": "Metformin",
                "price_type": "gprm_public",
                "unit_price": 0.045,
                "unit": "per tablet",
                "currency": "EUR",
                "country": "France",
                "source_api": "who_gprm",
                "source_url": None,
                "effective_date": date(2025, 1, 1),
                "strength": "500mg",
                "dosage_form": "Tablet",
                "atc_code": "A10BA02",
            },
            {
                "drug_name": "Metformin",
                "price_type": "gprm_public",
                "unit_price": 0.032,
                "unit": "per tablet",
                "currency": "INR",
                "country": "India",
                "source_api": "who_gprm",
                "source_url": None,
                "effective_date": date(2025, 1, 1),
                "strength": "500mg",
                "dosage_form": "Tablet",
                "atc_code": "A10BA02",
            },
        ]
        matched = match_drugs(db, records)
        assert len(matched) == 2
        countries = {r["country"] for r in matched}
        assert countries == {"France", "India"}


# ============================================================
# TestGPRMIntegration — run() orchestration
# ============================================================

class TestGPRMIntegration:
    """Verify the run() entry point orchestrates parse + match + store."""

    def test_run_returns_stats(self):
        """run() returns {fetched, stored, matched, countries} summary."""
        from scripts.fetch_who_gprm import store_pricing, parse_gprm_records

        db = MockDB()
        db.set_results("drugs", [{"id": "d001-uuid"}])

        raw = [
            {
                "medicine_name": "Metformin",
                "dosage_form": "Tablet",
                "strength": "500mg",
                "country": "France",
                "price_per_unit": 0.045,
                "currency": "EUR",
                "price_type": "public",
                "year": 2025,
                "atc_code": "A10BA02",
            },
            {
                "medicine_name": "Metformin",
                "dosage_form": "Tablet",
                "strength": "500mg",
                "country": "India",
                "price_per_unit": 0.032,
                "currency": "INR",
                "price_type": "public",
                "year": 2025,
                "atc_code": "A10BA02",
            },
            {
                "medicine_name": "Atorvastatin",
                "dosage_form": "Tablet",
                "strength": "10mg",
                "country": "Brazil",
                "price_per_unit": None,
                "currency": "BRL",
                "price_type": "retail",
                "year": 2024,
                "atc_code": "C10AA05",
            },
        ]

        parsed = parse_gprm_records(raw)
        # 2 valid records (1 skipped due to null price)
        assert len(parsed) == 2

        # Attach drug_id for store
        for rec in parsed:
            rec["drug_id"] = "d001-uuid"

        stats = store_pricing(db, parsed, dry_run=False)
        assert stats["stored"] == 2
        assert stats["countries"] == 2
        assert "France" in stats["country_list"]
        assert "India" in stats["country_list"]
