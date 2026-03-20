"""Tests for scripts/dedup_companies.py — company deduplication.

TDD: Verify normalization, non-company detection, and merge logic.
"""

from __future__ import annotations

import pytest


# ── Pure function tests ──

class TestNormalizeCompanyName:
    """Verify company name normalization strips suffixes correctly."""

    def test_strips_inc(self):
        from scripts.dedup_companies import normalize_company_name
        assert normalize_company_name("Pfizer Inc.") == "pfizer"
        assert normalize_company_name("Pfizer Inc") == "pfizer"

    def test_strips_ltd(self):
        from scripts.dedup_companies import normalize_company_name
        assert normalize_company_name("Lupin Ltd") == "lupin"
        assert normalize_company_name("Lupin Ltd.") == "lupin"

    def test_strips_corp(self):
        from scripts.dedup_companies import normalize_company_name
        assert normalize_company_name("Novartis Pharms Corp") == "novartis"

    def test_strips_multiple_suffixes(self):
        from scripts.dedup_companies import normalize_company_name
        assert normalize_company_name("Amneal Pharms USA Inc") == "amneal"

    def test_collapses_whitespace(self):
        from scripts.dedup_companies import normalize_company_name
        assert normalize_company_name("  Pfizer   Inc  ") == "pfizer"

    def test_lowercases(self):
        from scripts.dedup_companies import normalize_company_name
        assert normalize_company_name("PFIZER") == "pfizer"

    def test_preserves_real_names(self):
        from scripts.dedup_companies import normalize_company_name
        assert normalize_company_name("Novo Nordisk") == "novo nordisk"
        assert normalize_company_name("Eli Lilly") == "eli lilly"

    def test_handles_pharmaceuticals(self):
        from scripts.dedup_companies import normalize_company_name
        result = normalize_company_name("Zydus Pharmaceuticals USA")
        assert result == "zydus"


class TestIsNonCompany:
    """Verify non-company entity detection."""

    def test_university_detected(self):
        from scripts.dedup_companies import _is_non_company
        assert _is_non_company("Johns Hopkins University")
        assert _is_non_company("University of Michigan")

    def test_hospital_detected(self):
        from scripts.dedup_companies import _is_non_company
        assert _is_non_company("Mayo Clinic Hospital")
        assert _is_non_company("Massachusetts General Hospital")

    def test_medical_center_detected(self):
        from scripts.dedup_companies import _is_non_company
        assert _is_non_company("Cleveland Medical Center")

    def test_nih_detected(self):
        from scripts.dedup_companies import _is_non_company
        assert _is_non_company("National Institutes of Health")

    def test_real_company_not_flagged(self):
        from scripts.dedup_companies import _is_non_company
        assert not _is_non_company("Pfizer Inc")
        assert not _is_non_company("Novo Nordisk")
        assert not _is_non_company("Eli Lilly and Company")
        assert not _is_non_company("AstraZeneca")


# ── MockDB tests ──

class MockDB:
    def __init__(self):
        self._results: dict[str, list[dict]] = {}
        self.executed: list[tuple[str, list]] = []

    def set_results(self, key: str, results: list[dict]):
        self._results[key] = results

    def fetch_all(self, sql: str, params=None) -> list[dict]:
        sql_lower = sql.lower()
        import re
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


class TestExcludeNonCompanies:
    def test_excludes_universities(self):
        db = MockDB()
        db.set_results("companies", [
            {"id": "c001", "name": "University of Michigan"},
            {"id": "c002", "name": "Pfizer Inc"},
        ])

        from scripts.dedup_companies import exclude_non_companies
        count = exclude_non_companies(db, dry_run=False)
        assert count == 1

    def test_dry_run_does_not_write(self):
        db = MockDB()
        db.set_results("companies", [
            {"id": "c001", "name": "Mayo Clinic Hospital"},
        ])

        from scripts.dedup_companies import exclude_non_companies
        count = exclude_non_companies(db, dry_run=True)
        assert count == 1
        assert len(db.executed) == 0


class TestDedupCompanies:
    def test_finds_duplicate_groups(self):
        db = MockDB()
        db.set_results("companies", [
            {"id": "c001", "name": "Pfizer Inc", "ticker": "PFE", "cik": "0000078003", "record_status": None},
            {"id": "c002", "name": "PFIZER", "ticker": None, "cik": None, "record_status": None},
        ])
        # Mock link count — return 0 for all
        db.set_results("entity_links", [{"cnt": 0}])

        from scripts.dedup_companies import dedup_companies
        stats = dedup_companies(db, dry_run=True)
        assert stats["groups_found"] == 1
        assert stats["merged"] == 1

    def test_no_duplicates_when_names_differ(self):
        db = MockDB()
        db.set_results("companies", [
            {"id": "c001", "name": "Pfizer", "ticker": "PFE", "cik": None, "record_status": None},
            {"id": "c002", "name": "Novartis", "ticker": "NVS", "cik": None, "record_status": None},
        ])

        from scripts.dedup_companies import dedup_companies
        stats = dedup_companies(db, dry_run=True)
        assert stats["groups_found"] == 0
        assert stats["merged"] == 0
