"""Tests for SEC EDGAR XBRL financial data and full-text search.

TDD: Tests written before implementation.
Validates fetch_xbrl_facts() and search_filings() on the SECEdgarConnector.
"""

from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from connectors.base import RawRecord, RecordType, SourceType
from connectors.sec_edgar import SECEdgarConnector


# ── Fixtures ──

MOCK_XBRL_IFRS = {
    "entityName": "NOVO NORDISK A/S",
    "cik": "353278",
    "facts": {
        "ifrs-full": {
            "Revenue": {
                "units": {
                    "DKK": [
                        {"fy": 2025, "fp": "FY", "val": 309064000000, "end": "2025-12-31", "filed": "2026-02-04"},
                        {"fy": 2024, "fp": "FY", "val": 290403000000, "end": "2024-12-31", "filed": "2025-02-05"},
                        {"fy": 2025, "fp": "Q3", "val": 80000000000, "end": "2025-09-30", "filed": "2025-11-01"},
                    ]
                }
            },
            "ResearchAndDevelopmentExpense": {
                "units": {
                    "DKK": [
                        {"fy": 2025, "fp": "FY", "val": 52039000000, "end": "2025-12-31", "filed": "2026-02-04"},
                    ]
                }
            },
            "ProfitLoss": {
                "units": {
                    "DKK": [
                        {"fy": 2025, "fp": "FY", "val": 83000000000, "end": "2025-12-31", "filed": "2026-02-04"},
                    ]
                }
            },
        }
    },
}

MOCK_XBRL_US_GAAP = {
    "entityName": "ELI LILLY AND COMPANY",
    "cik": "59478",
    "facts": {
        "us-gaap": {
            "Revenues": {
                "units": {
                    "USD": [
                        {"fy": 2025, "fp": "FY", "val": 45000000000, "end": "2025-12-31", "filed": "2026-02-15"},
                        {"fy": 2024, "fp": "FY", "val": 34124000000, "end": "2024-12-31", "filed": "2025-02-15"},
                    ]
                }
            },
            "ResearchAndDevelopmentExpense": {
                "units": {
                    "USD": [
                        {"fy": 2025, "fp": "FY", "val": 11200000000, "end": "2025-12-31", "filed": "2026-02-15"},
                    ]
                }
            },
            "NetIncomeLoss": {
                "units": {
                    "USD": [
                        {"fy": 2025, "fp": "FY", "val": 5800000000, "end": "2025-12-31", "filed": "2026-02-15"},
                        {"fy": 2025, "fp": "Q2", "val": 1400000000, "end": "2025-06-30", "filed": "2025-08-01"},
                    ]
                }
            },
            "Assets": {
                "units": {
                    "USD": [
                        {"fy": 2025, "fp": "FY", "val": 64000000000, "end": "2025-12-31", "filed": "2026-02-15"},
                    ]
                }
            },
        }
    },
}

MOCK_SEARCH_RESULTS = {
    "hits": {
        "hits": [
            {
                "_source": {
                    "entity_name": "ELI LILLY AND COMPANY",
                    "file_num": "001-06351",
                    "file_date": "2026-02-15",
                    "form_type": "10-K",
                    "display_names": ["Eli Lilly and Company"],
                },
                "_id": "0000059478-26-000015:tirzepatide",
            },
            {
                "_source": {
                    "entity_name": "NOVO NORDISK A/S",
                    "file_num": "001-15208",
                    "file_date": "2026-01-30",
                    "form_type": "8-K",
                    "display_names": ["Novo Nordisk A/S"],
                },
                "_id": "0000353278-26-000003:tirzepatide",
            },
        ],
        "total": {"value": 2},
    },
    "query": {"q": '"tirzepatide"', "forms": "10-K,10-Q,8-K"},
}

MOCK_SEARCH_EMPTY = {
    "hits": {
        "hits": [],
        "total": {"value": 0},
    },
    "query": {"q": '"nonexistentdrug12345"', "forms": "10-K,10-Q,8-K"},
}


def _make_connector() -> SECEdgarConnector:
    """Create a connector without real config."""
    conn = SECEdgarConnector(config=None)
    conn.target_ciks = ["0000353278"]
    return conn


def _mock_response(data: dict, status_code: int = 200) -> MagicMock:
    """Build a mock requests.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = data
    resp.text = json.dumps(data)
    resp.content = json.dumps(data).encode()[:10000]
    return resp


# ── TestFetchXbrlFacts ──


class TestFetchXbrlFacts:
    """Tests for fetch_xbrl_facts() method."""

    def test_extracts_revenue_from_us_gaap(self):
        """US-GAAP Revenues concept should be extracted as 'revenue' metric."""
        conn = _make_connector()
        with patch.object(conn.session, "get", return_value=_mock_response(MOCK_XBRL_US_GAAP)):
            records = conn.fetch_xbrl_facts("0000059478")

        revenue_records = [r for r in records if r.data.get("metric_name") == "revenue"]
        assert len(revenue_records) >= 1
        # Should have FY 2025 revenue
        fy2025 = [r for r in revenue_records if r.data.get("fiscal_year") == 2025]
        assert len(fy2025) == 1
        assert fy2025[0].data["metric_value"] == 45000000000
        assert fy2025[0].data["currency"] == "USD"

    def test_extracts_revenue_from_ifrs(self):
        """IFRS Revenue concept should be extracted as 'revenue' metric."""
        conn = _make_connector()
        with patch.object(conn.session, "get", return_value=_mock_response(MOCK_XBRL_IFRS)):
            records = conn.fetch_xbrl_facts("0000353278")

        revenue_records = [r for r in records if r.data.get("metric_name") == "revenue"]
        assert len(revenue_records) >= 1
        # IFRS uses DKK for Novo Nordisk
        fy2025 = [r for r in revenue_records if r.data.get("fiscal_year") == 2025]
        assert len(fy2025) == 1
        assert fy2025[0].data["metric_value"] == 309064000000
        assert fy2025[0].data["currency"] == "DKK"

    def test_handles_missing_concept_gracefully(self):
        """If a concept is not present, it should be silently skipped."""
        sparse_data = {
            "entityName": "TEST COMPANY",
            "cik": "999999",
            "facts": {
                "us-gaap": {
                    "Revenues": {
                        "units": {
                            "USD": [
                                {"fy": 2025, "fp": "FY", "val": 100000, "end": "2025-12-31", "filed": "2026-02-01"},
                            ]
                        }
                    }
                    # No ResearchAndDevelopmentExpense, no NetIncomeLoss, etc.
                }
            },
        }
        conn = _make_connector()
        with patch.object(conn.session, "get", return_value=_mock_response(sparse_data)):
            records = conn.fetch_xbrl_facts("0000999999")

        # Should only have revenue records, not crash
        assert len(records) >= 1
        metric_names = {r.data["metric_name"] for r in records}
        assert "revenue" in metric_names
        # Should not have rd_expense since it was absent
        assert "rd_expense" not in metric_names

    def test_filters_to_annual_only(self):
        """Quarterly (Q1-Q4) data points should be excluded; only FY kept."""
        conn = _make_connector()
        with patch.object(conn.session, "get", return_value=_mock_response(MOCK_XBRL_IFRS)):
            records = conn.fetch_xbrl_facts("0000353278")

        # The IFRS mock has a Q3 data point for Revenue — it should be filtered out
        for r in records:
            assert r.data.get("fiscal_period") == "FY", (
                f"Non-annual data point found: {r.data}"
            )

    def test_returns_raw_records(self):
        """All returned objects should be RawRecord with correct type and source."""
        conn = _make_connector()
        with patch.object(conn.session, "get", return_value=_mock_response(MOCK_XBRL_US_GAAP)):
            records = conn.fetch_xbrl_facts("0000059478")

        assert len(records) > 0
        for r in records:
            assert isinstance(r, RawRecord)
            assert r.record_type == RecordType.COMPANY
            assert r.source_name == "SEC EDGAR"
            assert r.provenance.source_type == SourceType.SEC_EDGAR
            assert "xbrl/companyfacts" in r.provenance.api_endpoint

    def test_extracts_multiple_metrics(self):
        """Should extract all available metrics from a US-GAAP response."""
        conn = _make_connector()
        with patch.object(conn.session, "get", return_value=_mock_response(MOCK_XBRL_US_GAAP)):
            records = conn.fetch_xbrl_facts("0000059478")

        metric_names = {r.data["metric_name"] for r in records}
        # US-GAAP mock has: Revenues, R&D, NetIncomeLoss, Assets
        assert "revenue" in metric_names
        assert "rd_expense" in metric_names
        assert "profit" in metric_names
        assert "total_assets" in metric_names

    def test_handles_api_error(self):
        """Non-200 response should return empty list, not crash."""
        conn = _make_connector()
        error_resp = _mock_response({}, status_code=404)
        with patch.object(conn.session, "get", return_value=error_resp):
            records = conn.fetch_xbrl_facts("0000999999")

        assert records == []


# ── TestSearchFilings ──


class TestSearchFilings:
    """Tests for search_filings() method."""

    def test_returns_filing_records(self):
        """Should return RawRecord objects with correct data from search results."""
        conn = _make_connector()
        with patch.object(conn.session, "get", return_value=_mock_response(MOCK_SEARCH_RESULTS)):
            records = conn.search_filings("tirzepatide")

        assert len(records) == 2
        for r in records:
            assert isinstance(r, RawRecord)
            assert r.record_type == RecordType.EVENT
            assert r.source_name == "SEC EDGAR"
            assert r.data["drug_name"] == "tirzepatide"

        # Check first record details
        assert records[0].data["company_name"] == "ELI LILLY AND COMPANY"
        assert records[0].data["form_type"] == "10-K"

    def test_handles_zero_results(self):
        """Empty search should return empty list, not crash."""
        conn = _make_connector()
        with patch.object(conn.session, "get", return_value=_mock_response(MOCK_SEARCH_EMPTY)):
            records = conn.search_filings("nonexistentdrug12345")

        assert records == []

    def test_limits_results(self):
        """Should cap results at MAX_SEARCH_RESULTS (20)."""
        # Build a mock with 25 hits
        many_hits = {
            "hits": {
                "hits": [
                    {
                        "_source": {
                            "entity_name": f"COMPANY_{i}",
                            "file_num": f"001-{i:05d}",
                            "file_date": "2026-01-15",
                            "form_type": "10-K",
                            "display_names": [f"Company {i}"],
                        },
                        "_id": f"accession-{i}:semaglutide",
                    }
                    for i in range(25)
                ],
                "total": {"value": 25},
            },
        }
        conn = _make_connector()
        with patch.object(conn.session, "get", return_value=_mock_response(many_hits)):
            records = conn.search_filings("semaglutide")

        assert len(records) <= 20

    def test_search_record_provenance(self):
        """Search records should have proper provenance with the search URL."""
        conn = _make_connector()
        with patch.object(conn.session, "get", return_value=_mock_response(MOCK_SEARCH_RESULTS)):
            records = conn.search_filings("tirzepatide")

        assert len(records) > 0
        for r in records:
            assert r.provenance.source_type == SourceType.SEC_EDGAR
            assert "efts.sec.gov" in r.provenance.api_endpoint


# ── TestFetchIntegration ──


class TestFetchIntegration:
    """Tests that the enhanced fetch() method calls the new methods."""

    def test_fetch_calls_xbrl_for_each_cik(self):
        """fetch() should call fetch_xbrl_facts for each target CIK."""
        conn = _make_connector()
        conn.target_ciks = ["0000059478", "0000353278"]

        # Mock _fetch_company to return minimal records
        with patch.object(conn, "_fetch_company", return_value=[]), \
             patch.object(conn, "fetch_xbrl_facts", return_value=[]) as mock_xbrl, \
             patch.object(conn, "search_filings", return_value=[]):
            conn.fetch()

        assert mock_xbrl.call_count == 2
        mock_xbrl.assert_any_call("0000059478")
        mock_xbrl.assert_any_call("0000353278")

    def test_fetch_calls_search_for_target_drugs(self):
        """fetch() should call search_filings for target drug names if configured."""
        conn = _make_connector()
        conn.target_ciks = ["0000059478"]
        conn.target_drugs = ["tirzepatide", "semaglutide"]

        with patch.object(conn, "_fetch_company", return_value=[]), \
             patch.object(conn, "fetch_xbrl_facts", return_value=[]), \
             patch.object(conn, "search_filings", return_value=[]) as mock_search:
            conn.fetch()

        assert mock_search.call_count == 2
        mock_search.assert_any_call("tirzepatide")
        mock_search.assert_any_call("semaglutide")
