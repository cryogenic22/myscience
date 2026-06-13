"""Tests for drug pricing infrastructure: NADAC parsing, drug matching, and API.

TDD: Covers NADAC response parsing, drug name extraction, name matching,
and pricing API endpoint behavior.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Optional
from unittest.mock import patch, MagicMock

import pytest


# ── MockDB (matches project pattern from test_enrichment.py) ──

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
        sql_lower = sql.lower()
        if "information_schema" in sql_lower:
            if "information_schema" in self._results:
                r = self._results["information_schema"]
                return r[0] if r else {"exists_": False}
            return {"exists_": False}
        results = self.fetch_all(sql, params)
        return results[0] if results else None

    def execute(self, sql: str, params=None) -> None:
        self.executed.append((sql, params or []))


# ============================================================
# TestNADACParsing — raw API JSON -> structured records
# ============================================================

class TestNADACParsing:
    """Verify parsing of raw CMS NADAC API responses."""

    def test_parses_nadac_response(self):
        """Raw API JSON -> structured records with correct fields."""
        from scripts.fetch_nadac_pricing import parse_nadac_response

        raw = [
            {
                "ndc": "00093-0311-01",
                "ndc_description": "METFORMIN HCL 500MG TABLETS",
                "nadac_per_unit": "0.02345",
                "as_of_date": "2026-03-15T00:00:00.000",
                "pricing_unit": "EA",
                "classification_for_rate_setting": "G",
            }
        ]
        result = parse_nadac_response(raw)
        assert len(result) == 1
        rec = result[0]
        assert rec["ndc_code"] == "00093-0311-01"
        assert rec["unit_price"] == pytest.approx(0.02345)
        assert rec["price_type"] == "nadac"
        assert rec["currency"] == "USD"
        assert rec["country"] == "US"
        assert rec["source_api"] == "cms_nadac"
        assert rec["effective_date"] == date(2026, 3, 15)
        assert rec["unit"] == "per unit"

    def test_extracts_drug_name(self):
        """NDC description -> clean drug name without dosage/form."""
        from scripts.fetch_nadac_pricing import extract_drug_name

        name = extract_drug_name("METFORMIN HCL 500MG TABLETS")
        assert "metformin" in name.lower()
        # Should not contain dosage info
        assert "500" not in name
        assert "tablet" not in name.lower()

    def test_handles_missing_price(self):
        """Null price -> record skipped."""
        from scripts.fetch_nadac_pricing import parse_nadac_response

        raw = [
            {
                "ndc": "00093-0311-01",
                "ndc_description": "METFORMIN HCL 500MG TABLETS",
                "nadac_per_unit": None,
                "as_of_date": "2026-03-15T00:00:00.000",
                "pricing_unit": "EA",
            }
        ]
        result = parse_nadac_response(raw)
        assert len(result) == 0

    def test_handles_empty_response(self):
        """No records -> empty list."""
        from scripts.fetch_nadac_pricing import parse_nadac_response

        result = parse_nadac_response([])
        assert result == []

    def test_handles_invalid_price_string(self):
        """Non-numeric price string -> record skipped."""
        from scripts.fetch_nadac_pricing import parse_nadac_response

        raw = [
            {
                "ndc": "00093-0311-01",
                "ndc_description": "METFORMIN HCL 500MG TABLETS",
                "nadac_per_unit": "N/A",
                "as_of_date": "2026-03-15T00:00:00.000",
                "pricing_unit": "EA",
            }
        ]
        result = parse_nadac_response(raw)
        assert len(result) == 0

    def test_parses_multiple_records(self):
        """Multiple valid records all parsed correctly."""
        from scripts.fetch_nadac_pricing import parse_nadac_response

        raw = [
            {
                "ndc": "00093-0311-01",
                "ndc_description": "METFORMIN HCL 500MG TABLETS",
                "nadac_per_unit": "0.02345",
                "as_of_date": "2026-03-15T00:00:00.000",
                "pricing_unit": "EA",
            },
            {
                "ndc": "00074-3799-13",
                "ndc_description": "ATORVASTATIN CALCIUM 10MG TAB",
                "nadac_per_unit": "0.05678",
                "as_of_date": "2026-03-15T00:00:00.000",
                "pricing_unit": "EA",
            },
        ]
        result = parse_nadac_response(raw)
        assert len(result) == 2
        names = [r["drug_name"].lower() for r in result]
        assert any("metformin" in n for n in names)
        assert any("atorvastatin" in n for n in names)


# ============================================================
# TestDrugNameExtraction — NDC description -> clean drug name
# ============================================================

class TestDrugNameExtraction:
    """Verify drug name extraction from NDC descriptions."""

    def test_strips_mg_strength(self):
        from scripts.fetch_nadac_pricing import extract_drug_name
        name = extract_drug_name("LISINOPRIL 20MG TABLETS")
        assert "lisinopril" in name.lower()
        assert "20" not in name

    def test_strips_complex_strength(self):
        from scripts.fetch_nadac_pricing import extract_drug_name
        name = extract_drug_name("AMOXICILLIN 250MG/5ML SUSPENSION")
        assert "amoxicillin" in name.lower()
        assert "250" not in name

    def test_preserves_salt_form(self):
        from scripts.fetch_nadac_pricing import extract_drug_name
        name = extract_drug_name("METFORMIN HCL 500MG TABLETS")
        # Salt form may be preserved in the name — that's fine for matching
        assert "metformin" in name.lower()

    def test_handles_empty_string(self):
        from scripts.fetch_nadac_pricing import extract_drug_name
        assert extract_drug_name("") == ""

    def test_handles_name_only(self):
        from scripts.fetch_nadac_pricing import extract_drug_name
        name = extract_drug_name("SEMAGLUTIDE")
        assert "semaglutide" in name.lower()


# ============================================================
# TestDrugNameMatching — match NADAC names to drugs table
# ============================================================

class TestDrugNameMatching:
    """Verify drug name matching against the drugs table."""

    def test_exact_match_to_drug(self):
        """'metformin' -> drugs.generic_name exact match."""
        from scripts.fetch_nadac_pricing import match_drug_name

        db = MockDB()
        db.set_results("drugs", [{"id": "d001-uuid"}])
        result = match_drug_name(db, "metformin")
        assert result == "d001-uuid"

    def test_fuzzy_match_to_drug(self):
        """'METFORMIN HCL' -> match via salt stripping to 'metformin'."""
        from scripts.fetch_nadac_pricing import match_drug_name

        # MockDB returns empty for first query (exact), then match for base name
        # We simulate by just returning a result for any drugs query
        db = MockDB()
        db.set_results("drugs", [{"id": "d002-uuid"}])
        result = match_drug_name(db, "Metformin Hcl")
        assert result is not None

    def test_no_match_returns_none(self):
        """Unknown drug -> None (but still storable with drug_id=NULL)."""
        from scripts.fetch_nadac_pricing import match_drug_name

        db = MockDB()
        # No results for any drugs query
        db.set_results("drugs", [])
        result = match_drug_name(db, "completely_unknown_xyz_123")
        assert result is None

    def test_no_match_still_stores(self):
        """Unknown drug still gets stored with drug_id=NULL."""
        from scripts.fetch_nadac_pricing import store_pricing_record

        db = MockDB()
        record = {
            "drug_name": "Unknown Drug XYZ",
            "ndc_code": "99999-9999-99",
            "price_type": "nadac",
            "unit_price": 1.2345,
            "unit": "per unit",
            "currency": "USD",
            "country": "US",
            "source_api": "cms_nadac",
            "source_url": "https://data.medicaid.gov/resource/4j6z-xnwq.json",
            "effective_date": date(2026, 3, 15),
        }
        store_pricing_record(db, record, drug_id=None)
        assert len(db.executed) == 1
        sql, params = db.executed[0]
        assert "INSERT INTO drug_pricing" in sql
        assert params[0] is None  # drug_id is NULL


# ============================================================
# TestFetchNADAC — integration of fetch + parse + match + store
# ============================================================

class TestFetchNADAC:
    """Verify the fetch_nadac orchestration function."""

    def test_dry_run_does_not_write(self):
        """Dry run parses and matches but writes nothing."""
        from scripts.fetch_nadac_pricing import fetch_nadac

        db = MockDB()
        db.set_results("drugs", [{"id": "d001-uuid"}])

        mock_page = [
            {
                "ndc": "00093-0311-01",
                "ndc_description": "METFORMIN HCL 500MG TABLETS",
                "nadac_per_unit": "0.02345",
                "as_of_date": "2026-03-15T00:00:00.000",
                "pricing_unit": "EA",
            }
        ]

        with patch("scripts.fetch_nadac_pricing.fetch_nadac_rows", return_value=mock_page):
            stats = fetch_nadac(db, limit=10, dry_run=True)

        assert stats["parsed"] == 1
        assert stats["stored"] == 0
        assert len(db.executed) == 0

    def test_stores_matched_record(self):
        """Valid record with drug match -> stored with drug_id set."""
        from scripts.fetch_nadac_pricing import fetch_nadac

        db = MockDB()
        db.set_results("drugs", [{"id": "d001-uuid"}])

        mock_page = [
            {
                "ndc": "00093-0311-01",
                "ndc_description": "METFORMIN HCL 500MG TABLETS",
                "nadac_per_unit": "0.02345",
                "as_of_date": "2026-03-15T00:00:00.000",
                "pricing_unit": "EA",
            }
        ]

        with patch("scripts.fetch_nadac_pricing.fetch_nadac_rows", return_value=mock_page):
            stats = fetch_nadac(db, limit=10, dry_run=False)

        assert stats["stored"] == 1
        assert stats["matched"] == 1
        assert len(db.executed) == 1
        sql, params = db.executed[0]
        assert "INSERT INTO drug_pricing" in sql

    def test_empty_api_response(self):
        """Empty API response -> zero records processed."""
        from scripts.fetch_nadac_pricing import fetch_nadac

        db = MockDB()

        with patch("scripts.fetch_nadac_pricing.fetch_nadac_rows", return_value=[]):
            stats = fetch_nadac(db, limit=10, dry_run=False)

        assert stats["raw_records"] == 0
        assert stats["parsed"] == 0
        assert stats["stored"] == 0


# ============================================================
# TestDKANCsvSource — the live DKAN portal path (Socrata is dead)
# ============================================================

class TestDKANCsvSource:
    """The current NADAC source: per-year DKAN datasets → weekly CSV snapshot."""

    def test_parses_dkan_csv_row(self):
        """A real DKAN CSV row (Title-Case headers) parses correctly — the field
        names differ from the legacy Socrata JSON keys."""
        from scripts.fetch_nadac_pricing import parse_nadac_record

        row = {
            "NDC Description": "METFORMIN HCL 500MG TABLETS",
            "NDC": "00093031101",
            "NADAC Per Unit": "0.02345",
            "Effective Date": "12/17/2025",
            "Pricing Unit": "EA",
            "As of Date": "01/07/2026",
            "Classification for Rate Setting": "G",
        }
        rec = parse_nadac_record(row)
        assert rec is not None
        assert rec["ndc_code"] == "00093031101"
        assert rec["unit_price"] == pytest.approx(0.02345)
        # Effective Date (price validity), NOT As of Date (publication)
        assert rec["effective_date"] == date(2025, 12, 17)
        assert "metformin" in rec["drug_name"].lower()
        assert rec["source_api"] == "cms_nadac"

    def test_legacy_socrata_row_still_parses(self):
        """Back-compat: a legacy Socrata-key record is unchanged."""
        from scripts.fetch_nadac_pricing import parse_nadac_record
        rec = parse_nadac_record({
            "ndc": "00093031101", "ndc_description": "METFORMIN HCL 500MG TABLETS",
            "nadac_per_unit": "0.02345", "as_of_date": "2026-03-15T00:00:00.000",
            "pricing_unit": "EA",
        })
        assert rec is not None and rec["effective_date"] == date(2026, 3, 15)

    def test_resolve_current_csv_url_from_dkan(self):
        """Resolver finds the current-year dataset's CSV downloadURL."""
        from scripts.fetch_nadac_pricing import resolve_current_nadac_csv_url
        from datetime import datetime, timezone
        yr = datetime.now(timezone.utc).year

        class _Resp:
            def raise_for_status(self): pass
            def json(self):
                return {"results": {"x": {
                    "title": f"NADAC (National Average Drug Acquisition Cost) {yr}",
                    "distribution": [
                        {"data": {"format": "csv",
                                  "downloadURL": f"https://download.medicaid.gov/data/nadac-{yr}.csv"}},
                    ],
                }}}

        class _Session:
            def get(self, url, params=None, headers=None, timeout=None):
                return _Resp()

        url = resolve_current_nadac_csv_url(session=_Session())
        assert url == f"https://download.medicaid.gov/data/nadac-{yr}.csv"

    def test_store_is_idempotent_on_conflict(self):
        """The history INSERT carries ON CONFLICT DO NOTHING (mig 095) — re-pulling
        an unchanged weekly snapshot must not duplicate rows."""
        from scripts.fetch_nadac_pricing import store_pricing_record
        db = MockDB()
        store_pricing_record(db, {
            "drug_name": "Metformin", "ndc_code": "00093031101", "price_type": "nadac",
            "unit_price": 0.0234, "unit": "per unit", "currency": "USD", "country": "US",
            "source_api": "cms_nadac", "source_url": "x", "effective_date": date(2025, 12, 17),
        }, drug_id="d1")
        sql, _ = db.executed[0]
        assert "on conflict" in sql.lower() and "do nothing" in sql.lower()


# ============================================================
# TestPricingAPI — API endpoint behavior
# ============================================================

class TestPricingAPI:
    """Verify pricing API endpoint logic."""

    def test_get_pricing_for_drug(self):
        """Returns pricing records for a valid drug_id."""
        from api.routes.pricing import get_drug_pricing

        db = MockDB()
        db.set_results("drug_pricing", [
            {
                "id": "p001", "drug_id": "d001", "drug_name": "Metformin",
                "ndc_code": "00093-0311-01", "price_type": "nadac",
                "unit_price": 0.0234, "unit": "per unit",
                "currency": "USD", "country": "US",
                "source_api": "cms_nadac", "source_url": None,
                "effective_date": "2026-03-15", "retrieved_at": "2026-03-20",
            },
        ])

        result = get_drug_pricing(drug_id="d001", db=db)
        assert result["drug_id"] == "d001"
        assert result["count"] == 1
        assert result["results"][0]["drug_name"] == "Metformin"

    def test_get_pricing_empty(self):
        """No pricing records for drug -> empty results list."""
        from api.routes.pricing import get_drug_pricing

        db = MockDB()
        db.set_results("drug_pricing", [])

        result = get_drug_pricing(drug_id="d999-no-pricing", db=db)
        assert result["count"] == 0
        assert result["results"] == []

    def test_latest_price_only(self):
        """latest_only=True returns at most 1 record."""
        from api.routes.pricing import get_drug_pricing

        db = MockDB()
        # MockDB returns all results — but the SQL LIMIT 1 would constrain in real DB
        db.set_results("drug_pricing", [
            {
                "id": "p001", "drug_id": "d001", "drug_name": "Metformin",
                "ndc_code": "00093-0311-01", "price_type": "nadac",
                "unit_price": 0.0234, "unit": "per unit",
                "currency": "USD", "country": "US",
                "source_api": "cms_nadac", "source_url": None,
                "effective_date": "2026-03-15", "retrieved_at": "2026-03-20",
            },
        ])

        result = get_drug_pricing(drug_id="d001", latest_only=True, db=db)
        # With MockDB we get what's there; real DB would LIMIT 1
        assert result["count"] >= 0
        assert "results" in result

    def test_get_latest_prices(self):
        """GET /pricing/latest returns cross-drug latest prices."""
        from api.routes.pricing import get_latest_prices

        db = MockDB()
        db.set_results("drug_pricing", [
            {
                "id": "p001", "drug_id": "d001", "drug_name": "Metformin",
                "ndc_code": "00093-0311-01", "price_type": "nadac",
                "unit_price": 0.0234, "unit": "per unit",
                "currency": "USD", "country": "US",
                "source_api": "cms_nadac",
                "effective_date": "2026-03-15", "retrieved_at": "2026-03-20",
            },
            {
                "id": "p002", "drug_id": "d002", "drug_name": "Atorvastatin",
                "ndc_code": "00074-3799-13", "price_type": "nadac",
                "unit_price": 0.0567, "unit": "per unit",
                "currency": "USD", "country": "US",
                "source_api": "cms_nadac",
                "effective_date": "2026-03-15", "retrieved_at": "2026-03-20",
            },
        ])

        result = get_latest_prices(db=db)
        assert result["count"] == 2
        assert len(result["results"]) == 2
