"""Tests for scripts/enrich_drugs.py and scripts/enrich_companies.py.

TDD: Verify enrichment logic with MockDB.
"""

from __future__ import annotations

import re

import pytest


class MockDB:
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
        # Handle EXISTS queries and table existence checks
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


# ── enrich_companies tests ──

class TestNormalizeForReference:
    """Verify reference data normalization."""

    def test_normalizes_pfizer(self):
        from scripts.enrich_companies import _normalize
        assert _normalize("Pfizer Inc.") == "pfizer"

    def test_normalizes_novo_nordisk(self):
        from scripts.enrich_companies import _normalize
        assert _normalize("Novo Nordisk A/S") == "novo nordisk a/s"  # A/S not in suffix list
        assert _normalize("Novo Nordisk") == "novo nordisk"

    def test_normalizes_eli_lilly(self):
        from scripts.enrich_companies import _normalize
        assert _normalize("Eli Lilly and Company") == "eli lilly and"  # "company" stripped


class TestTopPharmaReference:
    """Verify reference data covers expected companies."""

    def test_has_novo_nordisk(self):
        from scripts.enrich_companies import TOP_PHARMA_REFERENCE
        assert "novo nordisk" in TOP_PHARMA_REFERENCE
        ref = TOP_PHARMA_REFERENCE["novo nordisk"]
        assert ref["ticker"] == "NVO"
        assert ref["country"] == "Denmark"

    def test_has_eli_lilly(self):
        from scripts.enrich_companies import TOP_PHARMA_REFERENCE
        assert "eli lilly" in TOP_PHARMA_REFERENCE
        ref = TOP_PHARMA_REFERENCE["eli lilly"]
        assert ref["ticker"] == "LLY"

    def test_has_pfizer(self):
        from scripts.enrich_companies import TOP_PHARMA_REFERENCE
        assert "pfizer" in TOP_PHARMA_REFERENCE
        ref = TOP_PHARMA_REFERENCE["pfizer"]
        assert ref["market_cap_tier"] == "mega"

    def test_has_at_least_40_entries(self):
        from scripts.enrich_companies import TOP_PHARMA_REFERENCE
        assert len(TOP_PHARMA_REFERENCE) >= 40


class TestEnrichFromReference:
    def test_enriches_matching_company(self):
        db = MockDB()
        db.set_results("companies", [
            {"id": "c001", "name": "Pfizer", "ticker": None,
             "country": None, "region": None, "market_cap_tier": None},
        ])

        from scripts.enrich_companies import enrich_from_reference
        count = enrich_from_reference(db, dry_run=False)
        assert count == 1
        updates = [s for s, _ in db.executed if "UPDATE companies" in s]
        assert len(updates) >= 1

    def test_skips_already_enriched(self):
        db = MockDB()
        db.set_results("companies", [
            {"id": "c001", "name": "Pfizer", "ticker": "PFE",
             "country": "US", "region": "North America", "market_cap_tier": "mega"},
        ])

        from scripts.enrich_companies import enrich_from_reference
        count = enrich_from_reference(db, dry_run=False)
        assert count == 0

    def test_skips_unknown_company(self):
        db = MockDB()
        db.set_results("companies", [
            {"id": "c001", "name": "Totally Unknown Pharma XYZ",
             "ticker": None, "country": None, "region": None, "market_cap_tier": None},
        ])

        from scripts.enrich_companies import enrich_from_reference
        count = enrich_from_reference(db, dry_run=False)
        assert count == 0


class TestSetUnknownMarketCap:
    def test_sets_unknown_tier(self):
        db = MockDB()
        db.set_results("companies", [
            {"id": "c001", "name": "Small Unknown"},
        ])

        from scripts.enrich_companies import set_unknown_market_cap
        count = set_unknown_market_cap(db, dry_run=False)
        assert count == 1


# ── enrich_drugs tests ──

class TestEnrichFromMilestones:
    def test_skips_when_no_milestone_table(self):
        db = MockDB()
        # information_schema returns False for regulatory_milestones

        from scripts.enrich_drugs import enrich_from_milestones
        stats = enrich_from_milestones(db, dry_run=False)
        assert stats["approval_date"] == 0

    def test_positive_path_sets_approval_date(self):
        db = MockDB()
        db.set_results("information_schema", [{"exists_": True}])
        db.set_results("drugs", [
            {"drug_id": "d001", "earliest_approval": "2022-01-15"},
        ])

        from scripts.enrich_drugs import enrich_from_milestones
        stats = enrich_from_milestones(db, dry_run=False)
        assert stats["approval_date"] == 1
        updates = [s for s, _ in db.executed if "UPDATE drugs" in s]
        assert len(updates) >= 1

    def test_milestone_dry_run_no_writes(self):
        db = MockDB()
        db.set_results("information_schema", [{"exists_": True}])
        db.set_results("drugs", [
            {"drug_id": "d001", "earliest_approval": "2022-01-15"},
        ])

        from scripts.enrich_drugs import enrich_from_milestones
        stats = enrich_from_milestones(db, dry_run=True)
        assert stats["approval_date"] == 1
        assert len(db.executed) == 0


class TestEnrichFromLabels:
    def test_extracts_brand_from_label(self):
        db = MockDB()
        db.set_results("information_schema", [{"exists_": True}])
        db.set_results("drugs", [
            {"drug_id": "d001", "drug_name": "OZEMPIC", "manufacturer": "Novo Nordisk"},
        ])

        from scripts.enrich_drugs import enrich_from_labels
        stats = enrich_from_labels(db, dry_run=False)
        assert stats["brand_name"] == 1
        update_params = [p for s, p in db.executed if "UPDATE drugs" in s]
        assert update_params[0][0] == "Ozempic"  # title-cased

    def test_skips_when_no_labels_table(self):
        db = MockDB()
        # default: information_schema returns False

        from scripts.enrich_drugs import enrich_from_labels
        stats = enrich_from_labels(db, dry_run=False)
        assert stats["brand_name"] == 0

    def test_label_company_always_zero(self):
        """Documents that company enrichment from labels is not yet implemented."""
        db = MockDB()
        db.set_results("information_schema", [{"exists_": True}])
        db.set_results("drugs", [
            {"drug_id": "d001", "drug_name": "OZEMPIC", "manufacturer": "Novo Nordisk"},
        ])

        from scripts.enrich_drugs import enrich_from_labels
        stats = enrich_from_labels(db, dry_run=False)
        assert stats["company"] == 0


class TestEnrichCompanyFromTrials:
    def test_skips_when_no_sponsor_match(self):
        db = MockDB()
        db.set_results("drugs", [
            {"drug_id": "d001", "sponsor_name": "Unknown Sponsor Corp"},
        ])
        # No matching company
        db.set_results("companies", [])

        from scripts.enrich_drugs import enrich_company_from_trials
        count = enrich_company_from_trials(db, dry_run=False)
        assert count == 0

    def test_exact_match_creates_owns_link(self):
        db = MockDB()
        db.set_results("drugs", [
            {"drug_id": "d001", "sponsor_name": "Pfizer"},
        ])
        db.set_results("companies", [{"id": "c001"}])

        from scripts.enrich_drugs import enrich_company_from_trials
        count = enrich_company_from_trials(db, dry_run=False)
        assert count == 1
        inserts = [s for s, _ in db.executed if "INSERT INTO entity_links" in s]
        assert len(inserts) >= 1
