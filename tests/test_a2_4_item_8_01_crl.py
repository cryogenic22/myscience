"""A2.4 — 8-K Item 8.01 → regulatory_crl detection (TDD).

SPEC-016 §7 swimlane A2.4 + per critique §2 KBQ 9 deep-dive: the FDA
does NOT publicly announce CRLs (Complete Response Letters). The path
to a CRL signal is the 8-K Item 8.01 filing where the company discloses
it, plus a press release.

Item 8.01 ("Other Events") is the catch-all 8-K item — it carries
CRLs, but also dozens of other things (litigation, product launches,
strategic statements). So the parser has to:

  1. Detect Item 8.01 blocks
  2. Filter for CRL-shaped narratives BEFORE running the LLM extractor
     (saves on API spend; most Item 8.01s are not CRLs)
  3. Extract structured CRL data (drug, application_number, reason
     categories, planned response)
  4. Emit regulatory_crl events — always high impact, negative direction
"""

from __future__ import annotations

from datetime import date

import pytest


# ────────────────────────────────────────────────────────────────────
# Fixtures
# ────────────────────────────────────────────────────────────────────

ITEM_8_01_CRL = """
Item 8.01 Other Events.

On April 28, 2026, Sarepta Therapeutics, Inc. (the "Company") received
a Complete Response Letter (the "CRL") from the U.S. Food and Drug
Administration (the "FDA") regarding the Company's New Drug Application
(NDA #218237) seeking accelerated approval for SRP-9001 for the treatment
of Duchenne muscular dystrophy.

In the CRL, the FDA cited the need for additional efficacy data from a
larger Phase 3 trial and raised concerns regarding manufacturing
controls. The Company plans to request a Type A meeting with the FDA
to discuss next steps and intends to provide an update on regulatory
plans by the end of Q3 2026.

Item 9.01 Financial Statements and Exhibits.
"""

ITEM_8_01_CRL_BIOLOGIC = """
Item 8.01 Other Events.

On April 28, 2026, the Company announced that it received a Complete
Response Letter from the FDA related to its Biologics License
Application (BLA) for tabelecleucel for the treatment of relapsed/
refractory Epstein-Barr virus positive post-transplant lymphoproliferative
disease.

The FDA's letter requested additional information on chemistry,
manufacturing, and controls (CMC) and cited inspection findings at a
third-party manufacturing facility. The Company is evaluating its
response and expects to resubmit within twelve months.
"""

ITEM_8_01_LITIGATION = """
Item 8.01 Other Events.

On April 28, 2026, the Company announced that it has reached a
settlement in the previously disclosed patent infringement litigation
with Generic Co. As part of the settlement, the Company will receive
a one-time payment of $50 million.
"""

ITEM_8_01_LAUNCH = """
Item 8.01 Other Events.

On April 28, 2026, the Company announced the U.S. commercial launch
of NewDrug for the treatment of moderate-to-severe atopic dermatitis,
following FDA approval received earlier in the year.
"""

NO_ITEM_8_01 = """
Item 1.01 Entry into a Material Definitive Agreement.

License agreement with Counter Co.
"""


# ────────────────────────────────────────────────────────────────────
# Cat 1 — Schema
# ────────────────────────────────────────────────────────────────────


class TestSchema:

    def test_module_exists(self):
        from services.extraction import regulatory_crl  # noqa: F401

    def test_required_fields(self):
        from services.extraction.regulatory_crl import CRLExtraction
        from pydantic import ValidationError

        c = CRLExtraction(
            agency="FDA",
            received_date=date(2026, 4, 28),
        )
        assert c.agency == "FDA"
        assert c.received_date == date(2026, 4, 28)

        with pytest.raises(ValidationError):
            CRLExtraction(received_date=date(2026, 4, 28))  # type: ignore[call-arg]

    def test_agency_enum(self):
        from services.extraction.regulatory_crl import CRLExtraction
        from pydantic import ValidationError

        for agency in ("FDA", "EMA", "MHRA", "PMDA", "Health_Canada", "TGA"):
            CRLExtraction(agency=agency, received_date=date(2026, 4, 28))  # type: ignore[arg-type]

        with pytest.raises(ValidationError):
            CRLExtraction(agency="bogus", received_date=date(2026, 4, 28))  # type: ignore[arg-type]

    def test_application_type_enum(self):
        from services.extraction.regulatory_crl import CRLExtraction

        for app_type in ("NDA", "BLA", "ANDA", "sNDA", "sBLA", "510k", "PMA"):
            CRLExtraction(
                agency="FDA",
                received_date=date(2026, 4, 28),
                application_type=app_type,  # type: ignore[arg-type]
            )

    def test_reason_categories_array(self):
        from services.extraction.regulatory_crl import CRLExtraction

        c = CRLExtraction(
            agency="FDA",
            received_date=date(2026, 4, 28),
            reason_categories=[
                "manufacturing_cmc",
                "additional_efficacy_data",
            ],
        )
        assert "manufacturing_cmc" in c.reason_categories
        assert len(c.reason_categories) == 2


# ────────────────────────────────────────────────────────────────────
# Cat 2 — CRL filter (does this Item 8.01 mention a CRL?)
# ────────────────────────────────────────────────────────────────────


class TestCRLFilter:

    def test_filter_module_exists(self):
        from connectors.sec_8k import item_8_01  # noqa: F401

    def test_block_is_crl_positive(self):
        from connectors.sec_8k.item_8_01 import block_mentions_crl
        assert block_mentions_crl(ITEM_8_01_CRL) is True
        assert block_mentions_crl(ITEM_8_01_CRL_BIOLOGIC) is True

    def test_block_is_crl_negative(self):
        from connectors.sec_8k.item_8_01 import block_mentions_crl
        assert block_mentions_crl(ITEM_8_01_LITIGATION) is False
        assert block_mentions_crl(ITEM_8_01_LAUNCH) is False
        assert block_mentions_crl("") is False

    def test_filter_matches_phrase_variants(self):
        """Various ways companies write 'received a CRL'."""
        from connectors.sec_8k.item_8_01 import block_mentions_crl

        variants = [
            "received a Complete Response Letter from the FDA",
            "the FDA issued a Complete Response Letter",
            "FDA Complete Response Letter regarding the NDA",
            "the Company received a CRL from the FDA",
            "FDA action: Complete Response",
        ]
        for v in variants:
            assert block_mentions_crl(v) is True, f"failed: {v!r}"


# ────────────────────────────────────────────────────────────────────
# Cat 3 — Header detection + parser
# ────────────────────────────────────────────────────────────────────


class TestItem801HeaderDetection:

    def test_detects_item_8_01_block(self):
        from connectors.sec_8k.item_8_01 import detect_item_8_01_blocks
        blocks = detect_item_8_01_blocks(ITEM_8_01_CRL)
        assert len(blocks) == 1
        assert "Complete Response Letter" in blocks[0]

    def test_excludes_next_item(self):
        from connectors.sec_8k.item_8_01 import detect_item_8_01_blocks
        blocks = detect_item_8_01_blocks(ITEM_8_01_CRL)
        assert "Item 9.01" not in blocks[0]

    def test_no_item_8_01_returns_empty(self):
        from connectors.sec_8k.item_8_01 import detect_item_8_01_blocks
        assert detect_item_8_01_blocks(NO_ITEM_8_01) == []


# ────────────────────────────────────────────────────────────────────
# Cat 4 — Parser orchestration with stub
# ────────────────────────────────────────────────────────────────────


class StubCRLExtractor:
    def __init__(self, plan: dict[str, list]):
        self.plan = plan
        self.calls: list[str] = []

    def extract(self, block: str):
        self.calls.append(block)
        for key, value in self.plan.items():
            if key in block:
                return value
        return []


class TestItem801ParserOrchestration:

    def test_parser_only_calls_extractor_for_crl_blocks(self):
        """The CRL filter saves API spend by short-circuiting non-CRL
        Item 8.01 blocks before they reach the LLM."""
        from connectors.sec_8k.item_8_01 import parse_item_8_01

        stub = StubCRLExtractor({})
        # Litigation block — should be filtered out, NO LLM call
        result = parse_item_8_01(ITEM_8_01_LITIGATION, extractor=stub)
        assert result == []
        assert stub.calls == []

        # Launch block — same thing
        stub2 = StubCRLExtractor({})
        result = parse_item_8_01(ITEM_8_01_LAUNCH, extractor=stub2)
        assert result == []
        assert stub2.calls == []

    def test_parser_extracts_crl_block(self):
        from connectors.sec_8k.item_8_01 import parse_item_8_01
        from services.extraction.regulatory_crl import CRLExtraction

        stub = StubCRLExtractor({
            "SRP-9001": [
                CRLExtraction(
                    agency="FDA",
                    received_date=date(2026, 4, 28),
                    application_type="NDA",
                    application_number="218237",
                    drug_name="SRP-9001",
                    indication="Duchenne muscular dystrophy",
                    reason_categories=[
                        "additional_efficacy_data",
                        "manufacturing_cmc",
                    ],
                    plan_for_response="request Type A meeting with FDA",
                ),
            ],
        })

        result = parse_item_8_01(ITEM_8_01_CRL, extractor=stub)
        assert len(result) == 1
        assert result[0].drug_name == "SRP-9001"
        assert "manufacturing_cmc" in result[0].reason_categories
        # Stub WAS called because filter detected CRL
        assert len(stub.calls) == 1

    def test_parser_swallows_extractor_errors(self):
        from connectors.sec_8k.item_8_01 import parse_item_8_01

        class BrokenExtractor:
            def extract(self, block):
                raise RuntimeError("extractor exploded")

        out = parse_item_8_01(ITEM_8_01_CRL, extractor=BrokenExtractor())
        assert out == []


# ────────────────────────────────────────────────────────────────────
# Cat 5 — Event-row builder
# ────────────────────────────────────────────────────────────────────


class TestCRLEventRowBuilder:

    def test_module_exists(self):
        from services.event_emitters import regulatory_crl  # noqa: F401

    def test_build_event_row_required_fields(self):
        from services.event_emitters.regulatory_crl import build_event_row
        from services.extraction.regulatory_crl import CRLExtraction

        c = CRLExtraction(
            agency="FDA",
            received_date=date(2026, 4, 28),
            application_type="NDA",
            application_number="218237",
            drug_name="SRP-9001",
            indication="Duchenne muscular dystrophy",
            reason_categories=["additional_efficacy_data", "manufacturing_cmc"],
        )

        row = build_event_row(
            extraction=c,
            company_id="00000000-0000-0000-0000-00000000aaaa",
            company_name="Sarepta Therapeutics, Inc.",
            drug_id="00000000-0000-0000-0000-00000000dddd",  # may be None
            source_document_id="00000000-0000-0000-0000-00000000bbbb",
            disclosed_date=date(2026, 4, 28),
        )

        assert row["event_type"] == "regulatory_crl"
        assert row["primary_entity_type"] == "drug"  # CRL is about a drug
        assert row["primary_entity_id"] == "00000000-0000-0000-0000-00000000dddd"
        # When drug not yet resolved, fall back to company
        # (covered separately below)
        assert row["event_date"] == date(2026, 4, 28)
        assert row["source_tier"] == "tier_1"
        assert row["status"] == "new"
        assert isinstance(row["event_hash"], str) and len(row["event_hash"]) == 64
        # CRLs are always HIGH impact
        assert row["impact_hint"] == "high"
        # CRLs are always negative direction
        assert row["payload"]["signal_direction_hint"] == "negative"
        assert "Complete Response Letter" in row["description"] or "CRL" in row["description"]
        assert "Sarepta" in row["description"]

    def test_falls_back_to_company_when_drug_unresolved(self):
        from services.event_emitters.regulatory_crl import build_event_row
        from services.extraction.regulatory_crl import CRLExtraction

        c = CRLExtraction(
            agency="FDA",
            received_date=date(2026, 4, 28),
            application_number="218237",
            drug_name="UnresolvedDrug",
        )
        row = build_event_row(
            extraction=c,
            company_id="00000000-0000-0000-0000-00000000aaaa",
            company_name="Co",
            drug_id=None,  # not resolved
            source_document_id="00000000-0000-0000-0000-00000000bbbb",
            disclosed_date=date(2026, 4, 28),
        )
        # When drug_id is None, primary_entity falls back to company
        assert row["primary_entity_type"] == "company"
        assert row["primary_entity_id"] == "00000000-0000-0000-0000-00000000aaaa"

    def test_event_hash_deterministic(self):
        from services.event_emitters.regulatory_crl import build_event_row
        from services.extraction.regulatory_crl import CRLExtraction

        c = CRLExtraction(
            agency="FDA",
            received_date=date(2026, 4, 28),
            application_type="NDA",
            application_number="218237",
            drug_name="X",
        )
        kwargs = dict(
            extraction=c,
            company_id="00000000-0000-0000-0000-000000000001",
            company_name="Co",
            drug_id=None,
            source_document_id="00000000-0000-0000-0000-000000000002",
            disclosed_date=date(2026, 4, 28),
        )
        a = build_event_row(**kwargs)
        b = build_event_row(**kwargs)
        assert a["event_hash"] == b["event_hash"]
