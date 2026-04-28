"""Cycle 1 — SEC EDGAR 8-K pipeline runner (TDD).

The runner is the connector-side glue between the existing SEC EDGAR
connector (which fetches 8-K text) and the α1+α2+α3 pipeline.

Responsibilities:
  - Feature-flag check (MZ_8K_PIPELINE_ENABLED)
  - LLM credentials check (ANTHROPIC_API_KEY or OPENAI_API_KEY)
  - CIK → company_id resolution via DB
  - Build the 4 extractors via α1 factories
  - Call process_8k_filing() with all the wiring
  - Return ProcessResult or None (when skipped)

Tests cover the gating logic + dispatch. The actual orchestrator
behaviour is already tested in α2; we don't re-prove it here.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Optional
from unittest.mock import MagicMock, patch

import pytest


# ────────────────────────────────────────────────────────────────────
# Mock DB for cik resolution
# ────────────────────────────────────────────────────────────────────


class MockDB:
    """Pretends to be db.Database. fetch_one is what the runner calls
    for cik resolution; insert_event/etc. would be called by the
    adapter wrapping this DB (already tested in α3)."""

    def __init__(self):
        self.executed: list[tuple[str, Any]] = []
        self.cik_responses: dict[str, dict] = {}
        # Other adapter methods stubbed — this test doesn't go through
        # the orchestrator, just the runner-level dispatch
        self.fetch_one_default: Optional[dict] = None

    def fetch_one(self, query: str, params=None):
        self.executed.append((query, params))
        # CIK resolution query has 'companies' and 'cik' in it
        if "companies" in query.lower() and "cik" in query.lower():
            cik_param = params[0] if params else None
            return self.cik_responses.get(str(cik_param), self.fetch_one_default)
        return self.fetch_one_default

    def fetch_all(self, query: str, params=None):
        return []

    def execute(self, query: str, params=None):
        self.executed.append((query, params))


@pytest.fixture
def mock_db():
    return MockDB()


# ────────────────────────────────────────────────────────────────────
# Cat 1 — Feature flag gating
# ────────────────────────────────────────────────────────────────────


class TestFeatureFlagGating:

    def test_module_exists(self):
        from connectors.sec_edgar_8k_runner import run_8k_through_pipeline  # noqa: F401

    def test_returns_none_when_flag_off(self, mock_db, monkeypatch):
        from connectors.sec_edgar_8k_runner import run_8k_through_pipeline

        monkeypatch.setenv("MZ_8K_PIPELINE_ENABLED", "false")
        result = run_8k_through_pipeline(
            filing_text="Item 5.02 ...",
            cik="0000078003",
            company_name="Pfizer Inc.",
            accession="0000078003-26-000099",
            filing_date=date(2026, 4, 15),
            db=mock_db,
        )
        assert result is None
        # No DB queries — short-circuited before resolution
        assert mock_db.executed == []

    def test_returns_none_when_flag_unset(self, mock_db, monkeypatch):
        from connectors.sec_edgar_8k_runner import run_8k_through_pipeline

        monkeypatch.delenv("MZ_8K_PIPELINE_ENABLED", raising=False)
        result = run_8k_through_pipeline(
            filing_text="Item 5.02 ...",
            cik="0000078003",
            company_name="Pfizer Inc.",
            accession="acc",
            filing_date=date(2026, 4, 15),
            db=mock_db,
        )
        assert result is None


# ────────────────────────────────────────────────────────────────────
# Cat 2 — LLM credentials gating
# ────────────────────────────────────────────────────────────────────


class TestCredentialsGating:

    def test_returns_none_when_no_api_key(self, mock_db, monkeypatch):
        from connectors.sec_edgar_8k_runner import run_8k_through_pipeline

        monkeypatch.setenv("MZ_8K_PIPELINE_ENABLED", "true")
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        result = run_8k_through_pipeline(
            filing_text="Item 5.02 ...",
            cik="0000078003",
            company_name="Pfizer",
            accession="acc",
            filing_date=date(2026, 4, 15),
            db=mock_db,
        )
        assert result is None


# ────────────────────────────────────────────────────────────────────
# Cat 3 — CIK resolution
# ────────────────────────────────────────────────────────────────────


class TestCikResolution:

    def test_returns_none_when_cik_unresolved(self, mock_db, monkeypatch):
        from connectors.sec_edgar_8k_runner import run_8k_through_pipeline

        monkeypatch.setenv("MZ_8K_PIPELINE_ENABLED", "true")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake")

        # mock_db has no cik_responses configured → fetch_one returns None
        result = run_8k_through_pipeline(
            filing_text="Item 5.02 ...",
            cik="9999999999",
            company_name="UnknownCo",
            accession="acc",
            filing_date=date(2026, 4, 15),
            db=mock_db,
        )
        assert result is None
        # Verify a query was attempted
        assert len(mock_db.executed) >= 1

    def test_resolves_cik_via_db_query(self, mock_db, monkeypatch):
        """When the DB returns a row, that company_id is used."""
        from connectors.sec_edgar_8k_runner import run_8k_through_pipeline

        monkeypatch.setenv("MZ_8K_PIPELINE_ENABLED", "true")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake")

        mock_db.cik_responses["0000078003"] = {
            "id": "00000000-0000-0000-0000-00000000aaaa",
        }

        # We don't want to actually call the LLM. Patch the runner's
        # extractor builders to return inert stubs.
        with patch(
            "connectors.sec_edgar_8k_runner._build_structured_call",
            return_value=lambda system, user, schema: None,
        ):
            result = run_8k_through_pipeline(
                filing_text="Item 9.01 only — no parseable items",
                cik="0000078003",
                company_name="Pfizer Inc.",
                accession="0000078003-26-000099",
                filing_date=date(2026, 4, 15),
                db=mock_db,
            )

        assert result is not None
        assert result.events_emitted == 0   # no parseable items
        assert result.disabled is False


# ────────────────────────────────────────────────────────────────────
# Cat 4 — Source document id derivation
# ────────────────────────────────────────────────────────────────────


class TestSourceDocumentIdDerivation:

    def test_accession_to_uuid_is_deterministic(self):
        from connectors.sec_edgar_8k_runner import _accession_to_uuid
        a = _accession_to_uuid("0000078003-26-000099")
        b = _accession_to_uuid("0000078003-26-000099")
        assert a == b
        # UUID-shaped (8-4-4-4-12 hex)
        assert len(a) == 36
        assert a.count("-") == 4

    def test_different_accessions_produce_different_ids(self):
        from connectors.sec_edgar_8k_runner import _accession_to_uuid
        assert _accession_to_uuid("0000078003-26-000099") != \
               _accession_to_uuid("0000078003-26-000100")


# ────────────────────────────────────────────────────────────────────
# Cat 5 — Structured-call factory selection
# ────────────────────────────────────────────────────────────────────


class TestStructuredCallSelection:

    def test_prefers_anthropic_when_available(self, monkeypatch):
        """When ANTHROPIC_API_KEY is set, build_structured_call uses
        the Anthropic adapter."""
        from connectors.sec_edgar_8k_runner import _build_structured_call

        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake-anth")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        # We can't easily test "which adapter" without import-time mocking,
        # but the result should be callable (not None).
        call = _build_structured_call()
        assert call is not None
        assert callable(call)

    def test_falls_back_to_openai_when_no_anthropic(self, monkeypatch):
        from connectors.sec_edgar_8k_runner import _build_structured_call

        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", "sk-fake-openai")

        call = _build_structured_call()
        assert call is not None
        assert callable(call)

    def test_returns_none_when_no_credentials(self, monkeypatch):
        from connectors.sec_edgar_8k_runner import _build_structured_call

        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        assert _build_structured_call() is None


# ────────────────────────────────────────────────────────────────────
# Cat 6 — Form-type filter (only 8-K filings go through)
# ────────────────────────────────────────────────────────────────────


class TestFormTypeFilter:

    def test_should_run_for_8k(self):
        from connectors.sec_edgar_8k_runner import should_run_pipeline_for_form
        assert should_run_pipeline_for_form("8-K") is True
        assert should_run_pipeline_for_form("8-K/A") is True   # amended
        assert should_run_pipeline_for_form("8-k") is True     # case-insensitive

    def test_should_skip_other_forms(self):
        from connectors.sec_edgar_8k_runner import should_run_pipeline_for_form
        assert should_run_pipeline_for_form("10-K") is False
        assert should_run_pipeline_for_form("10-Q") is False
        assert should_run_pipeline_for_form("DEF 14A") is False
        assert should_run_pipeline_for_form("S-1") is False
        assert should_run_pipeline_for_form("") is False
        assert should_run_pipeline_for_form(None) is False  # type: ignore[arg-type]
