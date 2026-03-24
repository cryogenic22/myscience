"""Tests for auto_curate_v2 — 5-pass deterministic data curation runner.

TDD: These tests are written BEFORE the implementation.
Run with: pytest tests/test_auto_curate_v2.py -v
"""

from __future__ import annotations

import re
from unittest.mock import patch, MagicMock

import pytest


# ── MockDB (reuses pattern from test_fair_scorer / test_ctx_corpus) ──


class MockDB:
    """Mock database that returns pre-configured query results.

    Routes queries by matching keywords in the SQL text.
    Supports fetch_all, fetch_one, and execute with call recording.
    """

    def __init__(self):
        self._results: dict[str, list[dict]] = {}
        self._execute_calls: list[tuple[str, list | None]] = []
        self._fetch_one_results: dict[str, dict | None] = {}

    def set_results(self, query_key: str, results: list[dict]):
        """Set results for fetch_all queries matching query_key."""
        self._results[query_key] = results

    def set_fetch_one(self, query_key: str, result: dict | None):
        """Set result for fetch_one queries matching query_key."""
        self._fetch_one_results[query_key] = result

    def fetch_all(self, sql: str, params=None) -> list[dict]:
        sql_lower = sql.lower()
        for key, results in self._results.items():
            if key in sql_lower:
                return results
        return []

    def fetch_one(self, sql: str, params=None) -> dict | None:
        sql_lower = sql.lower()
        for key, result in self._fetch_one_results.items():
            if key in sql_lower:
                return result
        results = self.fetch_all(sql, params)
        return results[0] if results else None

    def execute(self, sql: str, params=None) -> None:
        self._execute_calls.append((sql, params))

    @property
    def execute_calls(self) -> list[tuple[str, list | None]]:
        return self._execute_calls


# ── Fixtures ──


@pytest.fixture
def mock_db():
    return MockDB()


# ═══════════════════════════════════════════════════════════════════════
# Pass 1: Company enrichment from SEC EDGAR
# ═══════════════════════════════════════════════════════════════════════


class TestEnrichCompaniesFromSEC:
    """Verify Pass 1: SEC EDGAR ticker/CIK enrichment."""

    def test_enrich_companies_matches_on_cleaned_name(self, mock_db):
        """Companies matched by stripping suffixes (Inc/Corp/Ltd etc)."""
        from scripts.auto_curate_v2 import enrich_companies_from_sec

        mock_db.set_results("companies", [
            {"id": "c001", "name": "Pfizer Inc."},
            {"id": "c002", "name": "Novo Nordisk A/S"},
        ])

        sec_data = {
            "0": {"cik_str": 78003, "ticker": "PFE", "title": "PFIZER INC"},
            "1": {"cik_str": 353278, "ticker": "NVO", "title": "NOVO NORDISK A/S"},
        }

        with patch("scripts.auto_curate_v2.requests") as mock_requests:
            mock_resp = MagicMock()
            mock_resp.json.return_value = sec_data
            mock_resp.raise_for_status = MagicMock()
            mock_requests.get.return_value = mock_resp

            result = enrich_companies_from_sec(mock_db)

        assert result["pass"] == "company_sec"
        assert result["total"] == 2
        assert result["enriched"] >= 1  # At least Pfizer should match

    def test_enrich_companies_updates_ticker_and_cik(self, mock_db):
        """Matched companies get ticker + CIK updated via UPDATE."""
        from scripts.auto_curate_v2 import enrich_companies_from_sec

        mock_db.set_results("companies", [
            {"id": "c001", "name": "Pfizer Inc"},
        ])

        sec_data = {
            "0": {"cik_str": 78003, "ticker": "PFE", "title": "PFIZER INC"},
        }

        with patch("scripts.auto_curate_v2.requests") as mock_requests:
            mock_resp = MagicMock()
            mock_resp.json.return_value = sec_data
            mock_resp.raise_for_status = MagicMock()
            mock_requests.get.return_value = mock_resp

            enrich_companies_from_sec(mock_db)

        # Should have executed at least one UPDATE
        update_calls = [c for c in mock_db.execute_calls if "UPDATE" in c[0].upper()]
        assert len(update_calls) >= 1
        sql, params = update_calls[0]
        assert "PFE" in params
        assert "78003" in params

    def test_enrich_companies_handles_empty_sec_response(self, mock_db):
        """Empty SEC JSON results in 0 enriched."""
        from scripts.auto_curate_v2 import enrich_companies_from_sec

        mock_db.set_results("companies", [
            {"id": "c001", "name": "Unknown Corp"},
        ])

        with patch("scripts.auto_curate_v2.requests") as mock_requests:
            mock_resp = MagicMock()
            mock_resp.json.return_value = {}
            mock_resp.raise_for_status = MagicMock()
            mock_requests.get.return_value = mock_resp

            result = enrich_companies_from_sec(mock_db)

        assert result["enriched"] == 0

    def test_enrich_companies_handles_request_failure(self, mock_db):
        """Network failure returns error result gracefully."""
        from scripts.auto_curate_v2 import enrich_companies_from_sec

        with patch("scripts.auto_curate_v2.requests") as mock_requests:
            mock_requests.get.side_effect = Exception("Connection timeout")

            result = enrich_companies_from_sec(mock_db)

        assert "error" in result
        assert result["pass"] == "company_sec"


# ═══════════════════════════════════════════════════════════════════════
# Pass 2: Orphan company linking
# ═══════════════════════════════════════════════════════════════════════


class TestLinkOrphanCompanies:
    """Verify Pass 2: linking orphan companies to trials as sponsors."""

    def test_orphan_companies_linked_to_matching_trials(self, mock_db):
        """Orphan companies matched by sponsor_name create SPONSORS links."""
        from scripts.auto_curate_v2 import link_orphan_companies

        mock_db.set_results("not exists", [
            {"id": "c010", "name": "Acme Pharmaceuticals Inc"},
        ])
        mock_db.set_results("clinical_trials", [
            {"id": "t100"},
            {"id": "t101"},
        ])

        result = link_orphan_companies(mock_db)

        assert result["pass"] == "orphan_companies"
        assert result["orphans"] == 1
        assert result["linked"] == 2

        # Verify SPONSORS links were inserted
        insert_calls = [c for c in mock_db.execute_calls if "INSERT" in c[0].upper()]
        assert len(insert_calls) == 2
        for sql, params in insert_calls:
            assert "SPONSORS" in sql  # link_type is a SQL literal
            assert "auto_curate_orphan" in sql  # provenance_source is a SQL literal
            assert "c010" in params  # company id is a param

    def test_orphan_skips_short_names(self, mock_db):
        """Companies with cleaned name < 4 chars are skipped."""
        from scripts.auto_curate_v2 import link_orphan_companies

        mock_db.set_results("not exists", [
            {"id": "c010", "name": "AB Inc"},  # "AB" after cleaning = 2 chars
        ])

        result = link_orphan_companies(mock_db)
        assert result["linked"] == 0

    def test_orphan_no_matching_trials(self, mock_db):
        """No matching trials means 0 links created."""
        from scripts.auto_curate_v2 import link_orphan_companies

        mock_db.set_results("not exists", [
            {"id": "c010", "name": "Unique Biotech Corp"},
        ])
        # No results for clinical_trials query
        mock_db.set_results("clinical_trials", [])

        result = link_orphan_companies(mock_db)
        assert result["orphans"] == 1
        assert result["linked"] == 0


# ═══════════════════════════════════════════════════════════════════════
# Pass 3: Resolution sweep with MentionNormalizer
# ═══════════════════════════════════════════════════════════════════════


class TestResolutionSweep:
    """Verify Pass 3: resolve pending entities via normalized name matching."""

    def test_resolution_sweep_resolves_matching_drug(self, mock_db):
        """Pending drug entity resolved when normalized name matches drugs table."""
        from scripts.auto_curate_v2 import resolution_sweep

        mock_db.set_results("unresolved_entities", [
            {"id": "u001", "entity_type": "drug", "raw_value": "SEMAGLUTIDE 0.5 MG INJECTION"},
        ])
        mock_db.set_fetch_one("drugs", {"id": "d001"})

        result = resolution_sweep(mock_db, batch_size=100)

        assert result["pass"] == "resolution_sweep"
        assert result["processed"] == 1
        assert result["resolved"] == 1

        # Verify UPDATE was called
        update_calls = [c for c in mock_db.execute_calls if "UPDATE" in c[0].upper()]
        assert len(update_calls) == 1
        sql, params = update_calls[0]
        assert "resolved" in sql.lower()
        assert "d001" in params

    def test_resolution_sweep_resolves_company(self, mock_db):
        """Pending company entity resolved via normalized company name."""
        from scripts.auto_curate_v2 import resolution_sweep

        mock_db.set_results("unresolved_entities", [
            {"id": "u002", "entity_type": "company", "raw_value": "Eli Lilly and Company"},
        ])
        mock_db.set_fetch_one("companies", {"id": "c002"})

        result = resolution_sweep(mock_db, batch_size=100)
        assert result["resolved"] == 1

    def test_resolution_sweep_skips_short_values(self, mock_db):
        """Raw values normalizing to < 3 chars are skipped."""
        from scripts.auto_curate_v2 import resolution_sweep

        mock_db.set_results("unresolved_entities", [
            {"id": "u003", "entity_type": "drug", "raw_value": "AB"},
        ])

        result = resolution_sweep(mock_db, batch_size=100)
        assert result["resolved"] == 0

    def test_resolution_sweep_no_match(self, mock_db):
        """Unresolved entity with no DB match stays unresolved."""
        from scripts.auto_curate_v2 import resolution_sweep

        mock_db.set_results("unresolved_entities", [
            {"id": "u004", "entity_type": "drug", "raw_value": "Nonexistent Drug XYZ"},
        ])
        # No match in drugs table
        mock_db.set_fetch_one("drugs", None)

        result = resolution_sweep(mock_db, batch_size=100)
        assert result["processed"] == 1
        assert result["resolved"] == 0


# ═══════════════════════════════════════════════════════════════════════
# Pass 4: HITL auto-resolve (substring heuristic)
# ═══════════════════════════════════════════════════════════════════════


class TestHITLAutoResolve:
    """Verify Pass 4: auto-approve HITL items with substring match."""

    def test_hitl_substring_match_approves(self, mock_db):
        """HITL item where suggested name is substring of raw_value gets auto-approved."""
        from scripts.auto_curate_v2 import hitl_auto_resolve

        mock_db.set_results("hitl_queued", [
            {
                "id": "h001",
                "raw_value": "semaglutide injection",
                "suggested_match_id": "d001",
                "suggested_match_name": "semaglutide",
                "suggested_confidence": 0.7,
            },
        ])

        result = hitl_auto_resolve(mock_db, batch_size=100)

        assert result["pass"] == "hitl_auto"
        assert result["processed"] == 1
        assert result["resolved"] == 1

    def test_hitl_reverse_substring_match(self, mock_db):
        """Also matches when raw_value is substring of suggested name."""
        from scripts.auto_curate_v2 import hitl_auto_resolve

        mock_db.set_results("hitl_queued", [
            {
                "id": "h002",
                "raw_value": "lilly",
                "suggested_match_id": "c002",
                "suggested_match_name": "Eli Lilly and Company",
                "suggested_confidence": 0.6,
            },
        ])

        result = hitl_auto_resolve(mock_db, batch_size=100)
        assert result["resolved"] == 1

    def test_hitl_no_substring_match(self, mock_db):
        """Non-matching HITL item is NOT auto-resolved."""
        from scripts.auto_curate_v2 import hitl_auto_resolve

        mock_db.set_results("hitl_queued", [
            {
                "id": "h003",
                "raw_value": "totally different drug",
                "suggested_match_id": "d099",
                "suggested_match_name": "unrelated compound",
                "suggested_confidence": 0.6,
            },
        ])

        result = hitl_auto_resolve(mock_db, batch_size=100)
        assert result["resolved"] == 0

    def test_hitl_empty_values_skipped(self, mock_db):
        """Items with empty raw_value or suggested_match_name are skipped."""
        from scripts.auto_curate_v2 import hitl_auto_resolve

        mock_db.set_results("hitl_queued", [
            {
                "id": "h004",
                "raw_value": "",
                "suggested_match_id": "d001",
                "suggested_match_name": "semaglutide",
                "suggested_confidence": 0.7,
            },
            {
                "id": "h005",
                "raw_value": "some drug",
                "suggested_match_id": "d001",
                "suggested_match_name": "",
                "suggested_confidence": 0.7,
            },
        ])

        result = hitl_auto_resolve(mock_db, batch_size=100)
        assert result["resolved"] == 0


# ═══════════════════════════════════════════════════════════════════════
# Pass 5: FAIR score computation
# ═══════════════════════════════════════════════════════════════════════


class TestComputeFAIR:
    """Verify Pass 5: FAIR score computation and persistence."""

    def test_compute_fair_returns_score(self, mock_db):
        """compute_fair calls FAIRScorer.compute() and .persist()."""
        from scripts.auto_curate_v2 import compute_fair

        mock_scorer = MagicMock()
        mock_scorer.compute.return_value = {
            "overall_score": 0.72,
            "entity_completeness": {},
            "link_density": 0.5,
            "source_diversity": 0.3,
            "freshness": 0.8,
            "resolution_rate": 0.9,
            "total_records": 5000,
            "total_links": 50000,
        }

        with patch("scripts.auto_curate_v2.FAIRScorer", return_value=mock_scorer):
            result = compute_fair(mock_db)

        assert result["pass"] == "fair_score"
        assert result["fair_score"] == 0.72
        mock_scorer.persist.assert_called_once()

    def test_compute_fair_handles_error(self, mock_db):
        """FAIRScorer failure returns error result gracefully."""
        from scripts.auto_curate_v2 import compute_fair

        mock_scorer = MagicMock()
        mock_scorer.compute.side_effect = Exception("DB connection lost")

        with patch("scripts.auto_curate_v2.FAIRScorer", return_value=mock_scorer):
            result = compute_fair(mock_db)

        assert "error" in result
        assert result["pass"] == "fair_score"


# ═══════════════════════════════════════════════════════════════════════
# Master runner: run_all_curation
# ═══════════════════════════════════════════════════════════════════════


class TestRunAllCuration:
    """Verify the master runner orchestrates all 5 passes."""

    def test_full_pipeline_runs_all_passes(self, mock_db):
        """run_all_curation executes all 5 passes and returns results."""
        from scripts.auto_curate_v2 import run_all_curation

        with patch("scripts.auto_curate_v2.requests") as mock_requests, \
             patch("scripts.auto_curate_v2.FAIRScorer") as mock_scorer_cls:
            # SEC data
            mock_resp = MagicMock()
            mock_resp.json.return_value = {}
            mock_resp.raise_for_status = MagicMock()
            mock_requests.get.return_value = mock_resp

            # FAIR scorer
            mock_scorer = MagicMock()
            mock_scorer.compute.return_value = {
                "overall_score": 0.75,
                "entity_completeness": {},
                "link_density": 0.5,
                "source_diversity": 0.3,
                "freshness": 0.8,
                "resolution_rate": 0.9,
                "total_records": 5000,
                "total_links": 50000,
            }
            mock_scorer_cls.return_value = mock_scorer

            results = run_all_curation(mock_db)

        assert isinstance(results, list)
        assert len(results) == 5

        # Check all passes are represented
        pass_names = [r["pass"] for r in results]
        assert "company_sec" in pass_names
        assert "orphan_companies" in pass_names
        assert "resolution_sweep" in pass_names
        assert "hitl_auto" in pass_names
        assert "fair_score" in pass_names

    def test_full_pipeline_with_empty_tables(self, mock_db):
        """All passes handle empty tables gracefully (no crashes)."""
        from scripts.auto_curate_v2 import run_all_curation

        with patch("scripts.auto_curate_v2.requests") as mock_requests, \
             patch("scripts.auto_curate_v2.FAIRScorer") as mock_scorer_cls:
            mock_resp = MagicMock()
            mock_resp.json.return_value = {}
            mock_resp.raise_for_status = MagicMock()
            mock_requests.get.return_value = mock_resp

            mock_scorer = MagicMock()
            mock_scorer.compute.return_value = {
                "overall_score": 0.0,
                "entity_completeness": {},
                "link_density": 0.0,
                "source_diversity": 0.0,
                "freshness": 0.0,
                "resolution_rate": 1.0,
                "total_records": 0,
                "total_links": 0,
            }
            mock_scorer_cls.return_value = mock_scorer

            results = run_all_curation(mock_db)

        # All passes should succeed with 0 enrichments
        for r in results:
            assert "error" not in r or r.get("pass") in ("company_sec",)

    def test_idempotency_no_duplicate_links(self, mock_db):
        """Running twice doesn't create duplicate entity_links (ON CONFLICT DO NOTHING)."""
        from scripts.auto_curate_v2 import link_orphan_companies

        mock_db.set_results("not exists", [
            {"id": "c010", "name": "Acme Pharmaceuticals"},
        ])
        mock_db.set_results("clinical_trials", [
            {"id": "t100"},
        ])

        # Run twice
        link_orphan_companies(mock_db)
        first_count = len(mock_db.execute_calls)
        link_orphan_companies(mock_db)
        second_count = len(mock_db.execute_calls) - first_count

        # Both runs issue INSERT...ON CONFLICT DO NOTHING
        for sql, params in mock_db.execute_calls:
            if "INSERT" in sql.upper():
                assert "ON CONFLICT DO NOTHING" in sql.upper()

    def test_idempotency_resolution_only_updates_pending(self, mock_db):
        """resolution_sweep only processes status='pending' entries."""
        from scripts.auto_curate_v2 import resolution_sweep

        # Simulate already-resolved entries: fetch returns empty (no pending)
        mock_db.set_results("unresolved_entities", [])

        result = resolution_sweep(mock_db, batch_size=100)
        assert result["processed"] == 0
        assert result["resolved"] == 0
        assert len(mock_db.execute_calls) == 0


# ═══════════════════════════════════════════════════════════════════════
# CLI entry point
# ═══════════════════════════════════════════════════════════════════════


class TestCLIEntryPoint:
    """Verify the script can be invoked from command line."""

    def test_module_has_main_function(self):
        """auto_curate_v2 has a main() function for CLI usage."""
        from scripts.auto_curate_v2 import main
        assert callable(main)

    def test_module_has_run_all(self):
        """auto_curate_v2 has run_all_curation as the master entry point."""
        from scripts.auto_curate_v2 import run_all_curation
        assert callable(run_all_curation)
