"""Epic 1 α2 — SEC 8-K orchestration pipeline (TDD).

The orchestrator stitches together everything from A2.1–A2.4 + α1:

  filing text + filer entity → 4 parsers (via α1 extractors) →
  event_row builders → DB writes (market_events, deals,
  investigators.roles_history)

This module is the bridge from "unit-tested parsers" to "real events
flowing." After α2, a connector can call process_8k_filing() once per
fetched filing and the right rows land in the right tables.

Tests:
  Cat 1 — Pipeline plumbing: dispatches to all 4 parsers per filing
  Cat 2 — Event-row writes to market_events (idempotent on event_hash)
  Cat 3 — Deals row writes for Item 1.01
  Cat 4 — roles_history append for Item 5.02 (with transition_id pairing)
  Cat 5 — Drug entity resolution attempt for Item 8.01 CRL
  Cat 6 — Feature-flag toggle (env var off → no writes)
  Cat 7 — Per-block error isolation (one bad block doesn't kill filing)
  Cat 8 — Result reporting (counts of events/deals/roles emitted)
"""

from __future__ import annotations

from datetime import date
from typing import Any, Optional
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def _enable_pipeline_flag(monkeypatch):
    """Most tests in this module assume the pipeline is enabled. The
    explicit feature-flag tests override this via their own monkeypatch."""
    monkeypatch.setenv("MZ_8K_PIPELINE_ENABLED", "true")
    yield


# ────────────────────────────────────────────────────────────────────
# Fixtures — synthetic 8-K compositions
# ────────────────────────────────────────────────────────────────────

# A complete 8-K with one Item per code we parse.
COMPOSITE_8K = """
Item 1.01 Entry into a Material Definitive Agreement.

On April 22, 2026, Pfizer Inc. (the "Company") entered into a License
Agreement with Pivotal Bio Therapeutics, Inc. for KRAS G12C inhibitor.
$50M upfront, up to $500M in milestones.

Item 2.02 Results of Operations and Financial Condition.

The Company reported Q1 2026 revenue of $14.9 billion and is raising
FY2026 revenue guidance from $58.5–61.5B to $61.0–64.0B.

Item 5.02 Departure of Directors or Certain Officers.

On April 15, 2026, Mikael Dolsten, Chief Scientific Officer, notified
the Company of his decision to retire effective June 30, 2026.

Item 8.01 Other Events.

On April 28, 2026, the Company received a Complete Response Letter from
the FDA regarding NDA #218237 for SRP-9001 in Duchenne muscular
dystrophy. The FDA cited additional efficacy data and CMC concerns.

Item 9.01 Financial Statements and Exhibits.
"""

EXEC_ONLY_8K = """
Item 5.02 Departure of Directors or Certain Officers.

On April 20, 2026, Anat Ashkenazi, Executive Vice President and CFO,
gave notice of her departure effective May 30, 2026.

Item 9.01.
"""

EMPTY_8K = """
Item 9.01 Financial Statements and Exhibits.
The exhibits are listed below.
"""


# ────────────────────────────────────────────────────────────────────
# Stub extractors that return canned results based on substring match
# ────────────────────────────────────────────────────────────────────


def _exec_change_stub_factory(plans: dict[str, list]):
    class _Stub:
        def extract(self, block):
            for key, value in plans.items():
                if key in block:
                    return value
            return []
    return _Stub()


def _deal_stub_factory(plans: dict[str, list]):
    class _Stub:
        def extract(self, block):
            for key, value in plans.items():
                if key in block:
                    return value
            return []
    return _Stub()


def _financial_stub_factory(plan):
    class _Stub:
        def extract(self, block):
            return plan
    return _Stub()


def _crl_stub_factory(plans: dict[str, list]):
    class _Stub:
        def extract(self, block):
            for key, value in plans.items():
                if key in block:
                    return value
            return []
    return _Stub()


def _build_extractors(
    *,
    exec_plan: Optional[dict] = None,
    deal_plan: Optional[dict] = None,
    financial_plan=None,
    crl_plan: Optional[dict] = None,
):
    """Construct the four extractors used by process_8k_filing."""
    from services.extraction_llm import (
        _ExecChangeExtractorImpl,
        _DealExtractorImpl,
        _CRLExtractorImpl,
        _FinancialExtractorImpl,
    )
    # Use the bare stub classes — the orchestrator only cares about the
    # .extract() method, not what made them.
    return {
        "exec_change": _exec_change_stub_factory(exec_plan or {}),
        "deal": _deal_stub_factory(deal_plan or {}),
        "financial": _financial_stub_factory(
            financial_plan or (None, [])
        ),
        "crl": _crl_stub_factory(crl_plan or {}),
    }


# ────────────────────────────────────────────────────────────────────
# Mock DB — record method calls + parameters for assertions
# ────────────────────────────────────────────────────────────────────


class MockDB:
    """Records all execute() / fetch_*() calls. Stub for the Database
    class. Tests assert against the captured call log."""

    def __init__(self, existing_event_hashes: Optional[set[str]] = None):
        self.events_inserted: list[dict] = []
        self.deals_inserted: list[dict] = []
        self.roles_history_appends: list[dict] = []
        self.existing_event_hashes = existing_event_hashes or set()

    # The orchestrator uses these higher-level helpers (Adapter pattern)
    def insert_event(self, row: dict) -> bool:
        """Returns True if inserted, False if duplicate (idempotent)."""
        if row["event_hash"] in self.existing_event_hashes:
            return False
        self.existing_event_hashes.add(row["event_hash"])
        self.events_inserted.append(row)
        return True

    def insert_deal(self, row: dict) -> str:
        self.deals_inserted.append(row)
        return f"deal-id-{len(self.deals_inserted)}"

    def append_roles_history(
        self, person_name: str, entry: dict, *, company_id: str,
    ) -> bool:
        self.roles_history_appends.append({
            "person_name": person_name,
            "company_id": company_id,
            "entry": entry,
        })
        return True

    def resolve_drug_id(self, drug_name: str) -> Optional[str]:
        """Stubbed entity resolver. Tests can override by mutating attr."""
        return getattr(self, "_drug_resolutions", {}).get(drug_name)

    def set_drug_resolution(self, drug_name: str, drug_id: str):
        if not hasattr(self, "_drug_resolutions"):
            self._drug_resolutions = {}
        self._drug_resolutions[drug_name] = drug_id


# ────────────────────────────────────────────────────────────────────
# Cat 1 — Plumbing: 4 parsers dispatched per filing
# ────────────────────────────────────────────────────────────────────


class TestPipelinePlumbing:

    def test_module_exists(self):
        from services.sec_8k_pipeline import process_8k_filing  # noqa: F401

    def test_returns_processresult_with_counts(self):
        """Composite filing → all 4 parsers run → counts reflect what was
        produced via the stubs."""
        from datetime import date
        from services.sec_8k_pipeline import process_8k_filing
        from services.extraction.exec_change import ExecChangeExtraction
        from services.extraction.deal_announced import DealExtraction
        from services.extraction.financial_disclosure import (
            FinancialDisclosureExtraction, FinancialMetric,
            GuidanceIssuance, GuidanceMetric,
        )
        from services.extraction.regulatory_crl import CRLExtraction

        extractors = _build_extractors(
            exec_plan={
                "Mikael Dolsten": [
                    ExecChangeExtraction(
                        person_name="Mikael Dolsten",
                        change_type="departure",
                        prior_role="Chief Scientific Officer",
                        effective_date=date(2026, 6, 30),
                        functional_area="CSO",
                    ),
                ],
            },
            deal_plan={
                "Pivotal Bio": [
                    DealExtraction(
                        deal_types=["license_in"],
                        announced_date=date(2026, 4, 22),
                        licensor_name="Pivotal Bio Therapeutics, Inc.",
                        licensee_name="Pfizer Inc.",
                        upfront_value_usd=50_000_000,
                        milestones_total_usd=500_000_000,
                    ),
                ],
            },
            financial_plan=(
                FinancialDisclosureExtraction(
                    fiscal_period_end=date(2026, 3, 31),
                    fiscal_period_label="Q1 2026",
                    metrics=[
                        FinancialMetric(name="revenue", basis="GAAP",
                                        value_usd=14_900_000_000),
                    ],
                ),
                [
                    GuidanceIssuance(
                        issued_at=date(2026, 4, 30),
                        metric=GuidanceMetric.REVENUE,
                        period_label="FY2026",
                        basis="non-GAAP",
                        direction="raise",
                        range_low=61_000_000_000,
                        range_high=64_000_000_000,
                        prior_range_low=58_500_000_000,
                        prior_range_high=61_500_000_000,
                    ),
                ],
            ),
            crl_plan={
                "SRP-9001": [
                    CRLExtraction(
                        agency="FDA",
                        received_date=date(2026, 4, 28),
                        application_type="NDA",
                        application_number="218237",
                        drug_name="SRP-9001",
                        indication="Duchenne muscular dystrophy",
                        reason_categories=["additional_efficacy_data",
                                           "manufacturing_cmc"],
                    ),
                ],
            },
        )

        db = MockDB()
        result = process_8k_filing(
            filing_text=COMPOSITE_8K,
            filer_company_id="00000000-0000-0000-0000-00000000aaaa",
            filer_company_name="Pfizer Inc.",
            source_document_id="00000000-0000-0000-0000-00000000bbbb",
            disclosed_date=date(2026, 4, 28),
            db=db,
            extractors=extractors,
        )

        # Composite filing yielded:
        # - 1 exec_change event
        # - 1 deal_announced event + 1 deals row
        # - 1 financial_disclosure event + 1 guidance_change event
        # - 1 regulatory_crl event
        assert result.events_emitted == 5
        assert result.deals_emitted == 1
        assert result.roles_appended == 1
        assert result.errors == []
        # All event types present in the captured DB writes
        types = {e["event_type"] for e in db.events_inserted}
        assert types == {
            "exec_change", "deal_announced",
            "financial_disclosure", "guidance_change",
            "regulatory_crl",
        }

    def test_empty_filing_emits_nothing(self):
        from services.sec_8k_pipeline import process_8k_filing
        extractors = _build_extractors()
        db = MockDB()
        result = process_8k_filing(
            filing_text=EMPTY_8K,
            filer_company_id="x",
            filer_company_name="Co",
            source_document_id="src-id",
            disclosed_date=date(2026, 4, 28),
            db=db,
            extractors=extractors,
        )
        assert result.events_emitted == 0
        assert result.deals_emitted == 0
        assert db.events_inserted == []


# ────────────────────────────────────────────────────────────────────
# Cat 2 — Idempotency
# ────────────────────────────────────────────────────────────────────


class TestIdempotency:

    def test_duplicate_event_hash_does_not_re_insert(self):
        """Re-running the pipeline on the same filing produces zero new
        rows on the second call (DB returns False from insert_event)."""
        from services.sec_8k_pipeline import process_8k_filing
        from services.extraction.exec_change import ExecChangeExtraction

        extractors = _build_extractors(
            exec_plan={
                "Anat Ashkenazi": [
                    ExecChangeExtraction(
                        person_name="Anat Ashkenazi",
                        change_type="departure",
                        prior_role="Executive Vice President and CFO",
                        effective_date=date(2026, 5, 30),
                        functional_area="CFO",
                    ),
                ],
            },
        )

        db = MockDB()
        kwargs = dict(
            filing_text=EXEC_ONLY_8K,
            filer_company_id="00000000-0000-0000-0000-00000000aaaa",
            filer_company_name="Eli Lilly",
            source_document_id="src-id",
            disclosed_date=date(2026, 4, 20),
            db=db,
            extractors=extractors,
        )

        first = process_8k_filing(**kwargs)
        assert first.events_emitted == 1
        assert len(db.events_inserted) == 1

        # Second call with identical inputs — event_hash matches, DB
        # returns False, no new rows
        second = process_8k_filing(**kwargs)
        assert second.events_emitted == 0
        assert second.duplicates_skipped == 1
        # DB still only has one row
        assert len(db.events_inserted) == 1


# ────────────────────────────────────────────────────────────────────
# Cat 3 — Deals row written for Item 1.01
# ────────────────────────────────────────────────────────────────────


class TestDealsRowWrite:

    def test_item_1_01_writes_both_event_and_deal_rows(self):
        from services.sec_8k_pipeline import process_8k_filing
        from services.extraction.deal_announced import DealExtraction

        extractors = _build_extractors(
            deal_plan={
                "Pivotal Bio": [
                    DealExtraction(
                        deal_types=["license_in", "co_development"],
                        announced_date=date(2026, 4, 22),
                        licensor_name="Pivotal Bio",
                        licensee_name="Pfizer",
                        upfront_value_usd=50_000_000,
                        milestones_total_usd=500_000_000,
                        royalty_range_low_pct=8,
                        royalty_range_high_pct=14,
                        subject_indication="KRAS G12C inhibitor",
                        geography="WW",
                    ),
                ],
            },
        )
        db = MockDB()
        result = process_8k_filing(
            filing_text=COMPOSITE_8K,
            filer_company_id="00000000-0000-0000-0000-00000000aaaa",
            filer_company_name="Pfizer",
            source_document_id="src-id",
            disclosed_date=date(2026, 4, 22),
            db=db,
            extractors=extractors,
        )
        assert result.deals_emitted == 1
        assert len(db.deals_inserted) == 1
        d = db.deals_inserted[0]
        assert d["deal_types"] == ["license_in", "co_development"]
        assert d["licensee_id"] == "00000000-0000-0000-0000-00000000aaaa"
        assert d["upfront_value_usd"] == 50_000_000


# ────────────────────────────────────────────────────────────────────
# Cat 4 — roles_history append for Item 5.02
# ────────────────────────────────────────────────────────────────────


class TestRolesHistoryAppend:

    def test_exec_change_appends_roles_history_entry(self):
        from services.sec_8k_pipeline import process_8k_filing
        from services.extraction.exec_change import ExecChangeExtraction

        extractors = _build_extractors(
            exec_plan={
                "Mikael Dolsten": [
                    ExecChangeExtraction(
                        person_name="Mikael Dolsten",
                        change_type="departure",
                        prior_role="Chief Scientific Officer",
                        effective_date=date(2026, 6, 30),
                        functional_area="CSO",
                    ),
                ],
            },
        )
        db = MockDB()
        result = process_8k_filing(
            filing_text=COMPOSITE_8K,
            filer_company_id="00000000-0000-0000-0000-00000000aaaa",
            filer_company_name="Pfizer",
            source_document_id="src-id",
            disclosed_date=date(2026, 4, 15),
            db=db,
            extractors=extractors,
        )
        assert result.roles_appended == 1
        assert len(db.roles_history_appends) == 1
        ap = db.roles_history_appends[0]
        assert ap["person_name"] == "Mikael Dolsten"
        assert ap["entry"]["title"] == "Chief Scientific Officer"
        assert ap["entry"]["functional_area"] == "CSO"
        assert ap["entry"]["confirmed"] is True   # SEC = confirmed
        assert ap["entry"]["transition_id"] is not None


# ────────────────────────────────────────────────────────────────────
# Cat 5 — Drug entity resolution for CRL primary entity
# ────────────────────────────────────────────────────────────────────


class TestCRLEntityResolution:

    def test_crl_uses_resolved_drug_id_when_known(self):
        from services.sec_8k_pipeline import process_8k_filing
        from services.extraction.regulatory_crl import CRLExtraction

        extractors = _build_extractors(
            crl_plan={
                "SRP-9001": [
                    CRLExtraction(
                        agency="FDA",
                        received_date=date(2026, 4, 28),
                        application_type="NDA",
                        application_number="218237",
                        drug_name="SRP-9001",
                    ),
                ],
            },
        )
        db = MockDB()
        db.set_drug_resolution(
            "SRP-9001", "00000000-0000-0000-0000-00000000dddd",
        )
        result = process_8k_filing(
            filing_text=COMPOSITE_8K,
            filer_company_id="00000000-0000-0000-0000-00000000aaaa",
            filer_company_name="Sarepta",
            source_document_id="src-id",
            disclosed_date=date(2026, 4, 28),
            db=db,
            extractors=extractors,
        )
        assert result.events_emitted == 1
        crl = [e for e in db.events_inserted
               if e["event_type"] == "regulatory_crl"][0]
        assert crl["primary_entity_type"] == "drug"
        assert crl["primary_entity_id"] == "00000000-0000-0000-0000-00000000dddd"

    def test_crl_falls_back_to_company_when_drug_unresolved(self):
        from services.sec_8k_pipeline import process_8k_filing
        from services.extraction.regulatory_crl import CRLExtraction

        extractors = _build_extractors(
            crl_plan={
                "SRP-9001": [
                    CRLExtraction(
                        agency="FDA",
                        received_date=date(2026, 4, 28),
                        application_type="NDA",
                        application_number="218237",
                        drug_name="SRP-9001",
                    ),
                ],
            },
        )
        db = MockDB()  # no drug resolution
        process_8k_filing(
            filing_text=COMPOSITE_8K,
            filer_company_id="00000000-0000-0000-0000-00000000aaaa",
            filer_company_name="Sarepta",
            source_document_id="src-id",
            disclosed_date=date(2026, 4, 28),
            db=db,
            extractors=extractors,
        )
        crl = [e for e in db.events_inserted
               if e["event_type"] == "regulatory_crl"][0]
        assert crl["primary_entity_type"] == "company"
        assert crl["primary_entity_id"] == "00000000-0000-0000-0000-00000000aaaa"


# ────────────────────────────────────────────────────────────────────
# Cat 6 — Feature flag
# ────────────────────────────────────────────────────────────────────


class TestFeatureFlag:

    def test_flag_off_returns_immediately_no_writes(
        self, monkeypatch,
    ):
        """When MZ_8K_PIPELINE_ENABLED != 'true', the orchestrator returns
        an inert ProcessResult with disabled=True and writes nothing."""
        from services.sec_8k_pipeline import process_8k_filing

        monkeypatch.setenv("MZ_8K_PIPELINE_ENABLED", "false")

        extractors = _build_extractors()
        db = MockDB()
        result = process_8k_filing(
            filing_text=COMPOSITE_8K,
            filer_company_id="x",
            filer_company_name="Co",
            source_document_id="src-id",
            disclosed_date=date(2026, 4, 28),
            db=db,
            extractors=extractors,
        )
        assert result.disabled is True
        assert result.events_emitted == 0
        assert db.events_inserted == []

    def test_flag_on_runs_pipeline(self, monkeypatch):
        from services.sec_8k_pipeline import process_8k_filing
        from services.extraction.exec_change import ExecChangeExtraction

        monkeypatch.setenv("MZ_8K_PIPELINE_ENABLED", "true")

        extractors = _build_extractors(
            exec_plan={
                "Anat Ashkenazi": [
                    ExecChangeExtraction(
                        person_name="Anat Ashkenazi",
                        change_type="departure",
                        prior_role="EVP and CFO",
                        effective_date=date(2026, 5, 30),
                        functional_area="CFO",
                    ),
                ],
            },
        )
        db = MockDB()
        result = process_8k_filing(
            filing_text=EXEC_ONLY_8K,
            filer_company_id="x",
            filer_company_name="Co",
            source_document_id="src-id",
            disclosed_date=date(2026, 4, 20),
            db=db,
            extractors=extractors,
        )
        assert result.disabled is False
        assert result.events_emitted == 1


# ────────────────────────────────────────────────────────────────────
# Cat 7 — Per-parser error isolation
# ────────────────────────────────────────────────────────────────────


class TestErrorIsolation:

    def test_one_broken_extractor_doesnt_kill_others(self, caplog):
        """If one parser's extractor raises, the others still run and
        their events still get persisted. The parser layer (A2.1) is
        responsible for absorbing extractor errors and logging — the
        orchestrator just sees no rows from that parser. This is the
        correct division of error-isolation responsibility.
        """
        from services.sec_8k_pipeline import process_8k_filing
        from services.extraction.deal_announced import DealExtraction

        # exec_change extractor is broken; others work
        class _Broken:
            def extract(self, block):
                raise RuntimeError("LLM exploded")

        extractors = _build_extractors(
            deal_plan={
                "Pivotal Bio": [
                    DealExtraction(
                        deal_types=["license_in"],
                        announced_date=date(2026, 4, 22),
                        licensor_name="Pivotal Bio",
                        licensee_name="Pfizer",
                    ),
                ],
            },
        )
        # Override exec_change with a broken one
        extractors["exec_change"] = _Broken()

        db = MockDB()
        with caplog.at_level("WARNING"):
            result = process_8k_filing(
                filing_text=COMPOSITE_8K,
                filer_company_id="x",
                filer_company_name="Pfizer",
                source_document_id="src-id",
                disclosed_date=date(2026, 4, 22),
                db=db,
                extractors=extractors,
            )

        # Deal still landed; exec_change yielded nothing
        assert result.deals_emitted == 1
        types = {e["event_type"] for e in db.events_inserted}
        assert "deal_announced" in types
        assert "exec_change" not in types
        # The parser-level warning was emitted
        assert any(
            "Item 5.02 extractor failed" in r.message
            for r in caplog.records
        )
