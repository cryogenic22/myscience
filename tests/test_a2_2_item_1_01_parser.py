"""A2.2 — 8-K Item 1.01 parser → deal_announced events (TDD).

SPEC-016 §7 swimlane A2, task A2.2. Item 1.01 ("Entry into a Material
Definitive Agreement") is the structured anchor for KBQ 10 (M&A).

Same architectural pattern as A2.1:
  - Pydantic-locked extraction schema (DealExtraction)
  - Rule-based header detection
  - Extractor Protocol — stub in tests, real LLM in services/extraction_llm.py
  - Sanity validators on financial terms (per critique R6)
  - Event-row builder + deals-row builder

The CI design's deal taxonomy is COMPOSITE — a single deal can be
license_in + co_development + option simultaneously. So deal_types is
a list, not a single enum.
"""

from __future__ import annotations

from datetime import date

import pytest


# ────────────────────────────────────────────────────────────────────
# Fixtures
# ────────────────────────────────────────────────────────────────────

ITEM_1_01_LICENSE = """
Item 1.01 Entry into a Material Definitive Agreement.

On April 22, 2026, Pfizer Inc. (the "Company") entered into a License
Agreement with Pivotal Bio Therapeutics, Inc. ("Pivotal Bio") pursuant
to which the Company will receive an exclusive worldwide license to
develop and commercialize Pivotal Bio's lead KRAS G12C inhibitor.

Under the terms of the agreement, Pivotal Bio will receive an upfront
payment of $50 million, and is eligible to receive up to $500 million
in development and regulatory milestones, plus tiered royalties on net
sales ranging from high-single-digit to low-double-digit percentages.

Item 9.01 Financial Statements and Exhibits.
"""

ITEM_1_01_ACQUISITION = """
Item 1.01 Entry into a Material Definitive Agreement.

On April 22, 2026, Bristol-Myers Squibb Company entered into an
Agreement and Plan of Merger with Trillium Therapeutics Inc.
Under the terms, BMS will acquire all outstanding shares of Trillium
for $18.50 per share in cash, representing a total transaction value
of approximately $2.25 billion.

The closing of the acquisition is expected to occur in Q3 2026.
"""

ITEM_1_01_COLLABORATION = """
Item 1.01 Entry into a Material Definitive Agreement.

On April 22, 2026, Eli Lilly and Company entered into a Research
Collaboration and License Agreement with NewCo Bio. The collaboration
will focus on the discovery and development of novel small molecules
targeting Alzheimer's disease.

Lilly will pay an upfront fee of $25 million and may make additional
research, development, regulatory, and commercial milestone payments
of up to $750 million in the aggregate. The agreement also includes
an option for Lilly to take an exclusive license following Phase 1
data, with additional opt-in fees of up to $100 million.
"""

ITEM_1_01_UNDISCLOSED = """
Item 1.01 Entry into a Material Definitive Agreement.

On April 22, 2026, the Company entered into an asset purchase
agreement with Vendor Bio for global rights to Compound X. Financial
terms of the transaction were not disclosed.
"""

NO_ITEM_1_01 = """
Item 5.02 Departure of Directors or Certain Officers.

On April 15, 2026, the CEO retired.
"""


# ────────────────────────────────────────────────────────────────────
# Cat 1 — Pydantic schema
# ────────────────────────────────────────────────────────────────────


class TestDealSchema:

    def test_module_exists(self):
        from services.extraction import deal_announced  # noqa: F401

    def test_required_fields(self):
        from services.extraction.deal_announced import DealExtraction
        from pydantic import ValidationError

        d = DealExtraction(
            deal_types=["license_in"],
            announced_date=date(2026, 4, 22),
        )
        assert d.deal_types == ["license_in"]
        assert d.announced_date == date(2026, 4, 22)

        # Empty deal_types is invalid
        with pytest.raises(ValidationError):
            DealExtraction(deal_types=[], announced_date=date(2026, 4, 22))

        # Invalid deal_type member
        with pytest.raises(ValidationError):
            DealExtraction(
                deal_types=["bogus_type"],  # type: ignore[list-item]
                announced_date=date(2026, 4, 22),
            )

    def test_deal_types_enum_complete(self):
        """All 9 deal-type values per SPEC-016 §1.2 must be accepted."""
        from services.extraction.deal_announced import DealExtraction
        for t in [
            "acquisition", "asset_purchase", "license_in", "license_out",
            "collaboration", "option", "co_promotion", "co_development",
            "royalty_monetisation",
        ]:
            DealExtraction(
                deal_types=[t],  # type: ignore[list-item]
                announced_date=date(2026, 4, 22),
            )

    def test_composite_deal_types_allowed(self):
        """A deal can be license_in + co_development simultaneously."""
        from services.extraction.deal_announced import DealExtraction
        d = DealExtraction(
            deal_types=["license_in", "co_development", "option"],
            announced_date=date(2026, 4, 22),
        )
        assert sorted(d.deal_types) == ["co_development", "license_in", "option"]

    def test_term_sanity_check_blocks_inconsistent_totals(self):
        """upfront + max_milestones <= total_potential * 1.05 (5% rounding)."""
        from services.extraction.deal_announced import DealExtraction
        from pydantic import ValidationError

        # OK: 50 + 500 = 550 <= 800 * 1.05 = 840
        DealExtraction(
            deal_types=["license_in"],
            announced_date=date(2026, 4, 22),
            upfront_value_usd=50_000_000,
            milestones_total_usd=500_000_000,
            total_potential_usd=800_000_000,
        )

        # FAIL: 50 + 500 = 550 > 100 * 1.05 = 105
        with pytest.raises(ValidationError):
            DealExtraction(
                deal_types=["license_in"],
                announced_date=date(2026, 4, 22),
                upfront_value_usd=50_000_000,
                milestones_total_usd=500_000_000,
                total_potential_usd=100_000_000,
            )

    def test_royalty_range_sanity(self):
        """royalty range must be within [0, 30] percent."""
        from services.extraction.deal_announced import DealExtraction
        from pydantic import ValidationError

        # OK
        DealExtraction(
            deal_types=["license_in"],
            announced_date=date(2026, 4, 22),
            royalty_range_low_pct=8,
            royalty_range_high_pct=14,
        )

        # FAIL: low > high
        with pytest.raises(ValidationError):
            DealExtraction(
                deal_types=["license_in"],
                announced_date=date(2026, 4, 22),
                royalty_range_low_pct=20,
                royalty_range_high_pct=10,
            )

        # FAIL: > 30
        with pytest.raises(ValidationError):
            DealExtraction(
                deal_types=["license_in"],
                announced_date=date(2026, 4, 22),
                royalty_range_low_pct=10,
                royalty_range_high_pct=45,
            )

    def test_undisclosed_terms_default(self):
        """Default upfront_disclosed=True; explicit False signals 'undisclosed'."""
        from services.extraction.deal_announced import DealExtraction
        d = DealExtraction(
            deal_types=["asset_purchase"],
            announced_date=date(2026, 4, 22),
            upfront_disclosed=False,
        )
        assert d.upfront_disclosed is False
        assert d.upfront_value_usd is None

    def test_party_roles(self):
        """acquirer/target for M&A; licensor/licensee for licenses."""
        from services.extraction.deal_announced import DealExtraction
        d = DealExtraction(
            deal_types=["acquisition"],
            announced_date=date(2026, 4, 22),
            acquirer_name="Pfizer Inc.",
            target_name="Trillium Therapeutics Inc.",
        )
        assert d.acquirer_name == "Pfizer Inc."
        assert d.target_name == "Trillium Therapeutics Inc."


# ────────────────────────────────────────────────────────────────────
# Cat 2 — Header detection
# ────────────────────────────────────────────────────────────────────


class TestItem101HeaderDetection:

    def test_module_exists(self):
        from connectors.sec_8k import item_1_01  # noqa: F401

    def test_detects_item_1_01_block(self):
        from connectors.sec_8k.item_1_01 import detect_item_1_01_blocks
        blocks = detect_item_1_01_blocks(ITEM_1_01_LICENSE)
        assert len(blocks) == 1
        assert "Pivotal Bio" in blocks[0]
        assert "$50 million" in blocks[0] or "$500 million" in blocks[0]

    def test_block_excludes_next_item(self):
        from connectors.sec_8k.item_1_01 import detect_item_1_01_blocks
        blocks = detect_item_1_01_blocks(ITEM_1_01_LICENSE)
        assert "Item 9.01" not in blocks[0]

    def test_returns_empty_when_no_item_1_01(self):
        from connectors.sec_8k.item_1_01 import detect_item_1_01_blocks
        assert detect_item_1_01_blocks(NO_ITEM_1_01) == []

    def test_acquisition_detection(self):
        from connectors.sec_8k.item_1_01 import detect_item_1_01_blocks
        blocks = detect_item_1_01_blocks(ITEM_1_01_ACQUISITION)
        assert len(blocks) == 1
        assert "Trillium" in blocks[0]


# ────────────────────────────────────────────────────────────────────
# Cat 3 — Parser orchestration with stub
# ────────────────────────────────────────────────────────────────────


class StubDealExtractor:
    def __init__(self, plan: dict[str, list]):
        self.plan = plan
        self.calls: list[str] = []

    def extract(self, block: str):
        self.calls.append(block)
        for key, value in self.plan.items():
            if key in block:
                return value
        return []


class TestItem101ParserOrchestration:

    def test_parser_calls_extractor_per_block(self):
        from connectors.sec_8k.item_1_01 import parse_item_1_01
        from services.extraction.deal_announced import DealExtraction

        stub = StubDealExtractor({
            "Pivotal Bio": [
                DealExtraction(
                    deal_types=["license_in"],
                    announced_date=date(2026, 4, 22),
                    licensor_name="Pivotal Bio Therapeutics, Inc.",
                    licensee_name="Pfizer Inc.",
                    upfront_value_usd=50_000_000,
                    milestones_total_usd=500_000_000,
                    royalty_range_low_pct=7,
                    royalty_range_high_pct=14,
                    subject_indication="KRAS G12C inhibitor",
                    geography="WW",
                ),
            ],
        })

        results = parse_item_1_01(ITEM_1_01_LICENSE, extractor=stub)
        assert len(results) == 1
        assert results[0].deal_types == ["license_in"]
        assert results[0].licensor_name == "Pivotal Bio Therapeutics, Inc."

    def test_parser_returns_empty_on_no_blocks(self):
        from connectors.sec_8k.item_1_01 import parse_item_1_01
        stub = StubDealExtractor({})
        assert parse_item_1_01(NO_ITEM_1_01, extractor=stub) == []
        assert stub.calls == []

    def test_parser_handles_multiple_deal_types(self):
        from connectors.sec_8k.item_1_01 import parse_item_1_01
        from services.extraction.deal_announced import DealExtraction

        stub = StubDealExtractor({
            "NewCo Bio": [
                DealExtraction(
                    deal_types=["collaboration", "license_out", "option"],
                    announced_date=date(2026, 4, 22),
                    upfront_value_usd=25_000_000,
                    milestones_total_usd=750_000_000,
                ),
            ],
        })
        results = parse_item_1_01(ITEM_1_01_COLLABORATION, extractor=stub)
        assert len(results) == 1
        assert "collaboration" in results[0].deal_types
        assert "option" in results[0].deal_types

    def test_parser_swallows_extractor_errors(self):
        from connectors.sec_8k.item_1_01 import parse_item_1_01

        class BrokenExtractor:
            def extract(self, block):
                raise ValueError("LLM returned garbage")

        out = parse_item_1_01(ITEM_1_01_LICENSE, extractor=BrokenExtractor())
        assert out == []


# ────────────────────────────────────────────────────────────────────
# Cat 4 — Event-row builder
# ────────────────────────────────────────────────────────────────────


class TestDealEventRowBuilder:

    def test_module_exists(self):
        from services.event_emitters import deal_announced  # noqa: F401

    def test_build_event_row_required_fields(self):
        from services.event_emitters.deal_announced import build_event_row
        from services.extraction.deal_announced import DealExtraction

        d = DealExtraction(
            deal_types=["license_in"],
            announced_date=date(2026, 4, 22),
            licensor_name="Pivotal Bio Therapeutics, Inc.",
            licensee_name="Pfizer Inc.",
            upfront_value_usd=50_000_000,
            milestones_total_usd=500_000_000,
        )

        row = build_event_row(
            extraction=d,
            primary_company_id="00000000-0000-0000-0000-00000000aaaa",
            primary_company_name="Pfizer Inc.",
            counterparty_company_id="00000000-0000-0000-0000-00000000bbbb",
            counterparty_company_name="Pivotal Bio Therapeutics, Inc.",
            source_document_id="00000000-0000-0000-0000-00000000cccc",
            disclosed_date=date(2026, 4, 22),
        )

        assert row["event_type"] == "deal_announced"
        assert row["primary_entity_type"] == "company"
        assert row["primary_entity_id"] == "00000000-0000-0000-0000-00000000aaaa"
        assert row["event_date"] == date(2026, 4, 22)
        assert row["source_tier"] == "tier_1"
        assert row["status"] == "new"
        assert isinstance(row["event_hash"], str) and len(row["event_hash"]) == 64
        assert "license_in" in row["description"].lower() or "license" in row["description"].lower()

    def test_event_hash_deterministic(self):
        from services.event_emitters.deal_announced import build_event_row
        from services.extraction.deal_announced import DealExtraction

        d = DealExtraction(
            deal_types=["acquisition"],
            announced_date=date(2026, 4, 22),
            acquirer_name="Pfizer",
            target_name="Trillium",
            total_potential_usd=2_250_000_000,
        )
        kwargs = dict(
            extraction=d,
            primary_company_id="00000000-0000-0000-0000-000000000001",
            primary_company_name="Pfizer",
            counterparty_company_id="00000000-0000-0000-0000-000000000002",
            counterparty_company_name="Trillium",
            source_document_id="00000000-0000-0000-0000-000000000003",
            disclosed_date=date(2026, 4, 22),
        )
        a = build_event_row(**kwargs)
        b = build_event_row(**kwargs)
        assert a["event_hash"] == b["event_hash"]

    def test_impact_hint_high_for_billion_dollar_deal(self):
        from services.event_emitters.deal_announced import build_event_row
        from services.extraction.deal_announced import DealExtraction

        d = DealExtraction(
            deal_types=["acquisition"],
            announced_date=date(2026, 4, 22),
            total_potential_usd=2_250_000_000,
        )
        row = build_event_row(
            extraction=d,
            primary_company_id="00000000-0000-0000-0000-000000000001",
            primary_company_name="Pfizer",
            counterparty_company_id="00000000-0000-0000-0000-000000000002",
            counterparty_company_name="Trillium",
            source_document_id="00000000-0000-0000-0000-000000000003",
            disclosed_date=date(2026, 4, 22),
        )
        assert row["impact_hint"] == "high"

    def test_impact_hint_undisclosed_terms_marked_explicitly(self):
        """undisclosed ≠ small. UI flag must be present per CI design."""
        from services.event_emitters.deal_announced import build_event_row
        from services.extraction.deal_announced import DealExtraction

        d = DealExtraction(
            deal_types=["asset_purchase"],
            announced_date=date(2026, 4, 22),
            upfront_disclosed=False,
        )
        row = build_event_row(
            extraction=d,
            primary_company_id="00000000-0000-0000-0000-000000000001",
            primary_company_name="Co",
            counterparty_company_id=None,
            counterparty_company_name="Vendor",
            source_document_id="00000000-0000-0000-0000-000000000003",
            disclosed_date=date(2026, 4, 22),
        )
        assert row["payload"]["upfront_disclosed"] is False
        assert "undisclosed" in row["description"].lower()

    def test_build_deals_row(self):
        """The deals-table row builder also returns a dict (for separate
        INSERT INTO deals)."""
        from services.event_emitters.deal_announced import build_deals_row
        from services.extraction.deal_announced import DealExtraction

        d = DealExtraction(
            deal_types=["license_in", "co_development"],
            announced_date=date(2026, 4, 22),
            licensor_name="Pivotal Bio",
            licensee_name="Pfizer",
            upfront_value_usd=50_000_000,
            milestones_total_usd=500_000_000,
            royalty_range_low_pct=7,
            royalty_range_high_pct=14,
            subject_indication="KRAS G12C inhibitor",
            geography="WW",
        )
        row = build_deals_row(
            extraction=d,
            acquirer_id=None,
            target_id=None,
            licensor_id="00000000-0000-0000-0000-000000000bbb",
            licensee_id="00000000-0000-0000-0000-00000000aaaa",
            source_document_id="00000000-0000-0000-0000-00000000cccc",
        )
        assert row["deal_types"] == ["license_in", "co_development"]
        assert row["licensor_id"] == "00000000-0000-0000-0000-000000000bbb"
        assert row["licensee_id"] == "00000000-0000-0000-0000-00000000aaaa"
        assert row["upfront_value_usd"] == 50_000_000
        assert row["royalty_terms"]["range_low_pct"] == 7
        assert row["status"] == "announced"
        assert row["geography"] == "WW"
