"""Epic 1 α3 — DBAdapter implementation against real Postgres (TDD).

Implements the DBAdapter Protocol from α2 against the existing
db.Database wrapper. Persistence semantics:

  insert_event(row) — INSERT INTO market_events with ON CONFLICT
    DO NOTHING on event_hash. Returns True if inserted, False on
    duplicate (idempotent).

  insert_deal(row) — INSERT INTO deals RETURNING id.

  append_roles_history(person_name, entry, *, company_id) —
    UPSERT investigators row by canonical_name; jsonb_array append
    on roles_history.

  resolve_drug_id(drug_name) — multi-step lookup: exact name match
    on drugs.generic_name → drugs.brand_name → drug aliases via
    entity_aliases. Returns None when not found.

Tests use a mock Database that records (query, params) tuples so we can
assert against the SQL shape without needing a live connection.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import MagicMock

import pytest


# ────────────────────────────────────────────────────────────────────
# Mock Database that captures execute / fetch calls
# ────────────────────────────────────────────────────────────────────


class CapturingDB:
    """Pretends to be db.Database. Tests assert on captured calls."""

    def __init__(self):
        self.executed: list[tuple[str, Any]] = []
        # Optional: predetermine fetch_one/fetch_all responses
        self.fetch_one_responses: list[Any] = []
        self.fetch_all_responses: list[Any] = []

    def execute(self, query: str, params=None):
        self.executed.append((query, params))

    def fetch_one(self, query: str, params=None):
        self.executed.append((query, params))
        if self.fetch_one_responses:
            return self.fetch_one_responses.pop(0)
        return None

    def fetch_all(self, query: str, params=None):
        self.executed.append((query, params))
        if self.fetch_all_responses:
            return self.fetch_all_responses.pop(0)
        return []


@pytest.fixture
def mock_db():
    return CapturingDB()


# ────────────────────────────────────────────────────────────────────
# Cat 1 — insert_event
# ────────────────────────────────────────────────────────────────────


SAMPLE_EVENT_ROW = {
    "event_type": "exec_change",
    "description": "Pfizer Inc.: Mikael Dolsten departure from CSO",
    "primary_entity_type": "company",
    "primary_entity_id": "00000000-0000-0000-0000-00000000aaaa",
    "primary_entity_name": "Pfizer Inc.",
    "event_date": date(2026, 6, 30),
    "disclosed_date": date(2026, 4, 15),
    "source_tier": "tier_1",
    "trust_score": 0.95,
    "status": "new",
    "event_hash": "a" * 64,
    "source_feed": "sec_8k_item_5_02",
    "impact_hint": "high",
    "payload": {"person_name": "Mikael Dolsten",
                "change_type": "departure"},
    "source_document_id": "00000000-0000-0000-0000-00000000bbbb",
}


class TestInsertEvent:

    def test_module_exists(self):
        from services.db_adapter_8k import build_adapter  # noqa: F401

    def test_insert_event_uses_on_conflict_do_nothing(self, mock_db):
        """On a fresh hash, the INSERT goes through and returns True."""
        from services.db_adapter_8k import build_adapter

        adapter = build_adapter(mock_db)
        # Simulate fresh insert: ON CONFLICT returned a row (pretend the
        # adapter uses RETURNING id to detect insertion vs no-op)
        mock_db.fetch_one_responses = [{"id": "evt-id-1"}]

        ok = adapter.insert_event(SAMPLE_EVENT_ROW)
        assert ok is True

        assert len(mock_db.executed) == 1
        sql, params = mock_db.executed[0]
        assert "INSERT INTO market_events" in sql
        assert "ON CONFLICT" in sql.upper()
        assert "DO NOTHING" in sql.upper() or "DO UPDATE" in sql.upper()
        # All required columns present in the SQL
        for col in ("event_type", "event_hash", "source_tier",
                    "primary_entity_type", "primary_entity_id"):
            assert col in sql

    def test_insert_event_returns_false_on_duplicate(self, mock_db):
        """When ON CONFLICT triggers and RETURNING yields nothing,
        insert_event returns False (the duplicate is silently skipped)."""
        from services.db_adapter_8k import build_adapter

        adapter = build_adapter(mock_db)
        # Simulate duplicate: RETURNING returns None
        mock_db.fetch_one_responses = [None]

        ok = adapter.insert_event(SAMPLE_EVENT_ROW)
        assert ok is False

    def test_insert_event_serialises_payload_as_jsonb(self, mock_db):
        """payload dict must be passed as JSON for jsonb column."""
        from services.db_adapter_8k import build_adapter
        import json

        adapter = build_adapter(mock_db)
        mock_db.fetch_one_responses = [{"id": "evt-id-1"}]
        adapter.insert_event(SAMPLE_EVENT_ROW)

        _, params = mock_db.executed[0]
        # Find the payload param — it should be a JSON string
        # (psycopg2 accepts dict for jsonb, but some adapters require dumps;
        # the rule we enforce: it is EITHER a dict OR a json string)
        # Look for a "person_name" reference somewhere in params
        params_repr = repr(params)
        assert "Mikael Dolsten" in params_repr
        # And the event_hash is in params
        assert "a" * 64 in params_repr


# ────────────────────────────────────────────────────────────────────
# Cat 2 — insert_deal
# ────────────────────────────────────────────────────────────────────


SAMPLE_DEAL_ROW = {
    "deal_types": ["license_in", "co_development"],
    "acquirer_id": None,
    "target_id": None,
    "licensor_id": "00000000-0000-0000-0000-000000000bbb",
    "licensee_id": "00000000-0000-0000-0000-000000000aaa",
    "subject_drug_ids": [],
    "subject_indications": [{"name": "KRAS G12C inhibitor"}],
    "geography": "WW",
    "currency": "USD",
    "upfront_value_usd": 50_000_000,
    "upfront_disclosed": True,
    "milestones_total_usd": 500_000_000,
    "milestones_breakdown": None,
    "royalty_terms": {"range_low_pct": 8, "range_high_pct": 14},
    "total_potential_usd": None,
    "equity_component": False,
    "announced_date": date(2026, 4, 22),
    "closing_date": None,
    "status": "announced",
    "source_document_id": "00000000-0000-0000-0000-000000000ccc",
    "press_release_url": None,
    "filing_url": None,
    "notes": None,
}


class TestInsertDeal:

    def test_returns_deal_id(self, mock_db):
        from services.db_adapter_8k import build_adapter

        adapter = build_adapter(mock_db)
        mock_db.fetch_one_responses = [
            {"id": "00000000-0000-0000-0000-deadbeef0001"},
        ]

        deal_id = adapter.insert_deal(SAMPLE_DEAL_ROW)
        assert deal_id == "00000000-0000-0000-0000-deadbeef0001"

        sql, _ = mock_db.executed[0]
        assert "INSERT INTO deals" in sql
        assert "RETURNING" in sql.upper()

    def test_includes_all_columns(self, mock_db):
        from services.db_adapter_8k import build_adapter

        adapter = build_adapter(mock_db)
        mock_db.fetch_one_responses = [{"id": "x"}]
        adapter.insert_deal(SAMPLE_DEAL_ROW)

        sql, _ = mock_db.executed[0]
        for col in ("deal_types", "acquirer_id", "target_id",
                    "licensor_id", "licensee_id", "upfront_value_usd",
                    "milestones_total_usd", "royalty_terms",
                    "announced_date", "status"):
            assert col in sql, f"missing column in INSERT: {col}"


# ────────────────────────────────────────────────────────────────────
# Cat 3 — append_roles_history
# ────────────────────────────────────────────────────────────────────


SAMPLE_ROLE_ENTRY = {
    "company_id": "00000000-0000-0000-0000-00000000aaaa",
    "company_name": "Pfizer Inc.",
    "title": "Chief Scientific Officer",
    "functional_area": "CSO",
    "seniority_tier": "C-suite",
    "start_date": None,
    "end_date": "2026-06-30",
    "transition_id": "00000000-0000-0000-0000-00000000eeee",
    "source_document_id": "00000000-0000-0000-0000-00000000bbbb",
    "confirmed": True,
}


class TestAppendRolesHistory:

    def test_creates_investigator_when_absent(self, mock_db):
        """When canonical_name lookup returns nothing, the adapter
        INSERTs a fresh investigators row with the new entry as the
        first member of roles_history."""
        from services.db_adapter_8k import build_adapter

        adapter = build_adapter(mock_db)
        # Simulate: SELECT returns nothing → fall through to INSERT
        mock_db.fetch_one_responses = [None]

        ok = adapter.append_roles_history(
            "Mikael Dolsten",
            SAMPLE_ROLE_ENTRY,
            company_id=SAMPLE_ROLE_ENTRY["company_id"],
        )
        assert ok is True

        # First call: SELECT to look up by canonical_name
        sel_sql, sel_params = mock_db.executed[0]
        assert "SELECT" in sel_sql
        assert "investigators" in sel_sql
        assert "canonical_name" in sel_sql

        # Then an INSERT
        ins_sql, ins_params = mock_db.executed[1]
        assert "INSERT INTO investigators" in ins_sql
        assert "roles_history" in ins_sql

    def test_appends_to_existing_investigator(self, mock_db):
        """When canonical_name lookup hits, the adapter UPDATEs the row
        appending the entry via jsonb_insert / jsonb_set."""
        from services.db_adapter_8k import build_adapter

        adapter = build_adapter(mock_db)
        mock_db.fetch_one_responses = [
            {"id": "00000000-0000-0000-0000-00000000pppp"},
        ]

        ok = adapter.append_roles_history(
            "Mikael Dolsten",
            SAMPLE_ROLE_ENTRY,
            company_id=SAMPLE_ROLE_ENTRY["company_id"],
        )
        assert ok is True

        # Last call should be an UPDATE on roles_history
        upd_sql, upd_params = mock_db.executed[-1]
        assert "UPDATE investigators" in upd_sql
        assert "roles_history" in upd_sql
        # Either jsonb_insert or array || cast
        assert (
            "jsonb_insert" in upd_sql
            or "||" in upd_sql
            or "jsonb_set" in upd_sql
        )

    def test_canonical_name_normalised_for_lookup(self, mock_db):
        """The lookup uses normalise_name() so honorifics/degree suffixes
        on the input don't break the match."""
        from services.db_adapter_8k import build_adapter

        adapter = build_adapter(mock_db)
        mock_db.fetch_one_responses = [None]
        adapter.append_roles_history(
            "Mikael Dolsten, M.D., Ph.D.",
            SAMPLE_ROLE_ENTRY,
            company_id="x",
        )
        # Canonical form: lowercased, no honorifics, no degree suffixes
        sel_sql, sel_params = mock_db.executed[0]
        # The canonical_name passed in params should be normalised
        params_repr = repr(sel_params)
        assert "mikael dolsten" in params_repr.lower()
        assert "M.D." not in params_repr
        assert "Ph.D." not in params_repr


# ────────────────────────────────────────────────────────────────────
# Cat 4 — resolve_drug_id
# ────────────────────────────────────────────────────────────────────


class TestResolveDrugId:

    def test_returns_none_for_unknown(self, mock_db):
        from services.db_adapter_8k import build_adapter

        adapter = build_adapter(mock_db)
        mock_db.fetch_one_responses = [None, None, None]  # 3 lookups all None

        result = adapter.resolve_drug_id("UnknownXYZ")
        assert result is None

    def test_finds_by_exact_generic_name(self, mock_db):
        from services.db_adapter_8k import build_adapter

        adapter = build_adapter(mock_db)
        # First lookup (generic_name) returns the drug
        mock_db.fetch_one_responses = [
            {"id": "00000000-0000-0000-0000-00000000d001"},
        ]

        result = adapter.resolve_drug_id("pembrolizumab")
        assert result == "00000000-0000-0000-0000-00000000d001"

        # Should have queried drugs by generic_name
        sql, params = mock_db.executed[0]
        assert "drugs" in sql
        assert "generic_name" in sql.lower()

    def test_falls_through_to_brand_name_then_aliases(self, mock_db):
        """If generic_name lookup misses, try brand_name; if that misses,
        try entity_aliases."""
        from services.db_adapter_8k import build_adapter

        adapter = build_adapter(mock_db)
        # generic_name miss → brand_name hit
        mock_db.fetch_one_responses = [
            None,
            {"id": "00000000-0000-0000-0000-00000000d002"},
        ]

        result = adapter.resolve_drug_id("Keytruda")
        assert result == "00000000-0000-0000-0000-00000000d002"

        assert len(mock_db.executed) == 2
        sql_brand, _ = mock_db.executed[1]
        assert "brand_name" in sql_brand.lower()

    def test_handles_empty_drug_name(self, mock_db):
        from services.db_adapter_8k import build_adapter
        adapter = build_adapter(mock_db)
        assert adapter.resolve_drug_id("") is None
        assert adapter.resolve_drug_id(None) is None  # type: ignore[arg-type]
        # No DB calls when input is empty
        assert mock_db.executed == []


# ────────────────────────────────────────────────────────────────────
# Cat 5 — Pipeline integration: adapter end-to-end with stub extractors
# ────────────────────────────────────────────────────────────────────


class TestPipelineIntegrationWithRealAdapter:

    def test_pipeline_with_real_adapter_writes_event(self, mock_db, monkeypatch):
        """Wire up everything except the actual DB: real DBAdapter from
        services.db_adapter_8k against a CapturingDB. Confirms the SQL
        shape produced by the orchestrator matches what α2 designed for."""
        from services.db_adapter_8k import build_adapter
        from services.sec_8k_pipeline import process_8k_filing
        from services.extraction.exec_change import ExecChangeExtraction

        monkeypatch.setenv("MZ_8K_PIPELINE_ENABLED", "true")

        class _ExecStub:
            def extract(self, block):
                if "Anat Ashkenazi" in block:
                    return [
                        ExecChangeExtraction(
                            person_name="Anat Ashkenazi",
                            change_type="departure",
                            prior_role="Executive Vice President and CFO",
                            effective_date=date(2026, 5, 30),
                            functional_area="CFO",
                        ),
                    ]
                return []

        # Insert + roles_history attempts return canned ids
        mock_db.fetch_one_responses = [
            {"id": "evt-1"},     # insert_event RETURNING
            None,                 # canonical_name SELECT - no investigator yet
        ]

        adapter = build_adapter(mock_db)
        result = process_8k_filing(
            filing_text=(
                "Item 5.02 Departure of Directors or Certain Officers.\n"
                "On April 20, 2026, Anat Ashkenazi notified the Company "
                "of her departure effective May 30, 2026.\n"
                "Item 9.01"
            ),
            filer_company_id="00000000-0000-0000-0000-00000000aaaa",
            filer_company_name="Eli Lilly and Company",
            source_document_id="00000000-0000-0000-0000-00000000bbbb",
            disclosed_date=date(2026, 4, 20),
            db=adapter,
            extractors={
                "exec_change": _ExecStub(),
                "deal": None,       # not present in this filing
                "financial": None,
                "crl": None,
            },
        )
        assert result.events_emitted == 1
        # First captured query is the INSERT INTO market_events
        sql, _ = mock_db.executed[0]
        assert "INSERT INTO market_events" in sql
