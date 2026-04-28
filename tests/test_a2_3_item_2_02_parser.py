"""A2.3 — 8-K Item 2.02 parser → financial + guidance events (TDD).

SPEC-016 §7 swimlane A2.3. Item 2.02 ("Results of Operations and
Financial Condition") is the 8-K used between 10-Q filings to disclose
quarterly results + guidance.

Per critique §2 KBQ 1 deep-dive: the SIGNAL that matters is the
*guidance change* (delta vs prior quarter), not the absolute numbers.
So this parser produces TWO event types:

  - financial_disclosure : the period's reported numbers
  - guidance_change      : delta vs prior issuance, when guidance is
                           issued / raised / lowered / reaffirmed /
                           narrowed / withdrawn

A Guidance entity is its own record (metric, period, value, basis,
issued_at, superseded_by) so successive issuances can be diffed. The
diff service is in services/event_emitters/financial_disclosure.py.

Same architecture as A2.1/A2.2:
  - Pydantic-locked extraction schemas (FinancialDisclosureExtraction,
    GuidanceIssuance)
  - Rule-based header detection
  - Extractor Protocol + stub for tests
  - Event-row builders
"""

from __future__ import annotations

from datetime import date

import pytest


# ────────────────────────────────────────────────────────────────────
# Fixtures
# ────────────────────────────────────────────────────────────────────

ITEM_2_02_RAISE_GUIDANCE = """
Item 2.02 Results of Operations and Financial Condition.

On April 30, 2026, Pfizer Inc. (the "Company") issued a press release
announcing financial results for the quarter ended March 31, 2026.

For the first quarter, the Company reported revenue of $14.9 billion,
GAAP earnings per share of $0.62 and non-GAAP adjusted earnings per
share of $0.92.

The Company is raising its full-year 2026 revenue guidance to a range
of $61.0 to $64.0 billion, from a range of $58.5 to $61.5 billion
previously, and is increasing its full-year 2026 non-GAAP adjusted EPS
guidance to a range of $2.95 to $3.15.

A copy of the press release is attached as Exhibit 99.1 hereto.

Item 9.01 Financial Statements and Exhibits.
"""

ITEM_2_02_REAFFIRM = """
Item 2.02 Results of Operations and Financial Condition.

On April 30, 2026, Eli Lilly and Company reported quarterly revenue
of $9.3 billion. The Company reaffirmed its full-year 2026 revenue
guidance of $42.0 to $43.5 billion and its non-GAAP EPS guidance
of $13.50 to $14.00.
"""

ITEM_2_02_LOWER = """
Item 2.02 Results of Operations and Financial Condition.

Today, the Company is lowering its full-year 2026 revenue guidance
to $5.8 to $6.2 billion (previously $6.5 to $6.9 billion) reflecting
the impact of recent inventory adjustments and slower-than-expected
launch dynamics in the EU.
"""

NO_ITEM_2_02 = """
Item 5.02 Departure of Directors or Certain Officers.
On April 15, 2026, the CFO retired.
"""


# ────────────────────────────────────────────────────────────────────
# Cat 1 — Pydantic schemas
# ────────────────────────────────────────────────────────────────────


class TestSchemas:

    def test_module_exists(self):
        from services.extraction import financial_disclosure  # noqa: F401

    def test_financial_disclosure_required_fields(self):
        from services.extraction.financial_disclosure import FinancialDisclosureExtraction
        from pydantic import ValidationError

        f = FinancialDisclosureExtraction(
            fiscal_period_end=date(2026, 3, 31),
            fiscal_period_label="Q1 2026",
        )
        assert f.fiscal_period_end == date(2026, 3, 31)

        with pytest.raises(ValidationError):
            FinancialDisclosureExtraction(  # type: ignore[call-arg]
                fiscal_period_label="Q1 2026",
            )

    def test_financial_disclosure_carries_metrics(self):
        from services.extraction.financial_disclosure import (
            FinancialDisclosureExtraction,
            FinancialMetric,
        )
        f = FinancialDisclosureExtraction(
            fiscal_period_end=date(2026, 3, 31),
            fiscal_period_label="Q1 2026",
            metrics=[
                FinancialMetric(name="revenue", basis="GAAP",
                                value_usd=14_900_000_000),
                FinancialMetric(name="eps", basis="GAAP", value=0.62),
                FinancialMetric(name="eps", basis="non-GAAP", value=0.92),
            ],
        )
        assert len(f.metrics) == 3
        assert {m.name for m in f.metrics} == {"revenue", "eps"}

    def test_metric_basis_enum(self):
        from services.extraction.financial_disclosure import FinancialMetric
        from pydantic import ValidationError

        FinancialMetric(name="revenue", basis="GAAP", value=1.0)
        FinancialMetric(name="revenue", basis="non-GAAP", value=1.0)

        with pytest.raises(ValidationError):
            FinancialMetric(name="revenue", basis="invalid", value=1.0)  # type: ignore[arg-type]

    def test_guidance_issuance_required_fields(self):
        from services.extraction.financial_disclosure import (
            GuidanceIssuance,
            GuidanceMetric,
        )
        g = GuidanceIssuance(
            issued_at=date(2026, 4, 30),
            metric=GuidanceMetric.REVENUE,
            period_label="FY2026",
            basis="non-GAAP",
            range_low=61_000_000_000,
            range_high=64_000_000_000,
            direction="raise",
        )
        assert g.metric == GuidanceMetric.REVENUE
        assert g.direction == "raise"

    def test_guidance_direction_enum(self):
        from services.extraction.financial_disclosure import (
            GuidanceIssuance,
            GuidanceMetric,
        )
        for d in ("raise", "lower", "reaffirm", "narrow", "initiate", "withdraw"):
            GuidanceIssuance(
                issued_at=date(2026, 4, 30),
                metric=GuidanceMetric.REVENUE,
                period_label="FY2026",
                basis="non-GAAP",
                direction=d,  # type: ignore[arg-type]
            )

        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            GuidanceIssuance(
                issued_at=date(2026, 4, 30),
                metric=GuidanceMetric.REVENUE,
                period_label="FY2026",
                basis="non-GAAP",
                direction="bogus",  # type: ignore[arg-type]
            )

    def test_guidance_range_invariant(self):
        """range_low <= range_high when both present."""
        from services.extraction.financial_disclosure import (
            GuidanceIssuance,
            GuidanceMetric,
        )
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            GuidanceIssuance(
                issued_at=date(2026, 4, 30),
                metric=GuidanceMetric.REVENUE,
                period_label="FY2026",
                basis="non-GAAP",
                direction="raise",
                range_low=64_000_000_000,
                range_high=61_000_000_000,  # < low
            )


# ────────────────────────────────────────────────────────────────────
# Cat 2 — Header detection
# ────────────────────────────────────────────────────────────────────


class TestItem202HeaderDetection:

    def test_module_exists(self):
        from connectors.sec_8k import item_2_02  # noqa: F401

    def test_detects_item_2_02_block(self):
        from connectors.sec_8k.item_2_02 import detect_item_2_02_blocks
        blocks = detect_item_2_02_blocks(ITEM_2_02_RAISE_GUIDANCE)
        assert len(blocks) == 1
        assert "raising its full-year 2026 revenue guidance" in blocks[0]

    def test_block_excludes_next_item(self):
        from connectors.sec_8k.item_2_02 import detect_item_2_02_blocks
        blocks = detect_item_2_02_blocks(ITEM_2_02_RAISE_GUIDANCE)
        assert "Item 9.01" not in blocks[0]

    def test_no_item_2_02_returns_empty(self):
        from connectors.sec_8k.item_2_02 import detect_item_2_02_blocks
        assert detect_item_2_02_blocks(NO_ITEM_2_02) == []


# ────────────────────────────────────────────────────────────────────
# Cat 3 — Parser orchestration
# ────────────────────────────────────────────────────────────────────


class StubFinancialExtractor:
    """Returns (FinancialDisclosureExtraction | None, list[GuidanceIssuance])."""

    def __init__(self, plan: dict[str, tuple]):
        self.plan = plan
        self.calls: list[str] = []

    def extract(self, block: str):
        self.calls.append(block)
        for key, value in self.plan.items():
            if key in block:
                return value
        return None, []


class TestItem202ParserOrchestration:

    def test_parser_calls_extractor(self):
        from connectors.sec_8k.item_2_02 import parse_item_2_02
        from services.extraction.financial_disclosure import (
            FinancialDisclosureExtraction,
            FinancialMetric,
            GuidanceIssuance,
            GuidanceMetric,
        )

        stub = StubFinancialExtractor({
            "raising its full-year 2026 revenue guidance": (
                FinancialDisclosureExtraction(
                    fiscal_period_end=date(2026, 3, 31),
                    fiscal_period_label="Q1 2026",
                    metrics=[
                        FinancialMetric(name="revenue", basis="GAAP",
                                        value_usd=14_900_000_000),
                        FinancialMetric(name="eps", basis="GAAP", value=0.62),
                        FinancialMetric(name="eps", basis="non-GAAP", value=0.92),
                    ],
                ),
                [
                    GuidanceIssuance(
                        issued_at=date(2026, 4, 30),
                        metric=GuidanceMetric.REVENUE,
                        period_label="FY2026",
                        basis="non-GAAP",
                        range_low=61_000_000_000,
                        range_high=64_000_000_000,
                        direction="raise",
                        prior_range_low=58_500_000_000,
                        prior_range_high=61_500_000_000,
                    ),
                    GuidanceIssuance(
                        issued_at=date(2026, 4, 30),
                        metric=GuidanceMetric.EPS,
                        period_label="FY2026",
                        basis="non-GAAP",
                        range_low=2.95,
                        range_high=3.15,
                        direction="raise",
                    ),
                ],
            ),
        })

        result = parse_item_2_02(ITEM_2_02_RAISE_GUIDANCE, extractor=stub)
        assert result.financial_disclosure is not None
        assert len(result.guidance_issuances) == 2
        assert result.guidance_issuances[0].direction == "raise"

    def test_parser_returns_none_disclosure_on_no_blocks(self):
        from connectors.sec_8k.item_2_02 import parse_item_2_02
        stub = StubFinancialExtractor({})
        result = parse_item_2_02(NO_ITEM_2_02, extractor=stub)
        assert result.financial_disclosure is None
        assert result.guidance_issuances == []

    def test_parser_swallows_extractor_errors(self):
        from connectors.sec_8k.item_2_02 import parse_item_2_02

        class BrokenExtractor:
            def extract(self, block):
                raise ValueError("bad LLM output")

        result = parse_item_2_02(ITEM_2_02_RAISE_GUIDANCE,
                                 extractor=BrokenExtractor())
        assert result.financial_disclosure is None
        assert result.guidance_issuances == []


# ────────────────────────────────────────────────────────────────────
# Cat 4 — Guidance diff (raise / lower / reaffirm vs prior issuance)
# ────────────────────────────────────────────────────────────────────


class TestGuidanceDiff:

    def test_classify_raise(self):
        from services.event_emitters.financial_disclosure import classify_guidance_direction
        # New range entirely above prior
        d = classify_guidance_direction(
            new_low=61_000_000_000, new_high=64_000_000_000,
            prior_low=58_500_000_000, prior_high=61_500_000_000,
        )
        assert d == "raise"

    def test_classify_lower(self):
        from services.event_emitters.financial_disclosure import classify_guidance_direction
        d = classify_guidance_direction(
            new_low=5_800_000_000, new_high=6_200_000_000,
            prior_low=6_500_000_000, prior_high=6_900_000_000,
        )
        assert d == "lower"

    def test_classify_reaffirm(self):
        from services.event_emitters.financial_disclosure import classify_guidance_direction
        d = classify_guidance_direction(
            new_low=42_000_000_000, new_high=43_500_000_000,
            prior_low=42_000_000_000, prior_high=43_500_000_000,
        )
        assert d == "reaffirm"

    def test_classify_narrow(self):
        from services.event_emitters.financial_disclosure import classify_guidance_direction
        # Narrowed: midpoint same, range tighter
        d = classify_guidance_direction(
            new_low=42_500_000_000, new_high=43_000_000_000,
            prior_low=42_000_000_000, prior_high=43_500_000_000,
        )
        assert d == "narrow"

    def test_classify_initiate(self):
        """No prior → initiate."""
        from services.event_emitters.financial_disclosure import classify_guidance_direction
        d = classify_guidance_direction(
            new_low=10_000_000_000, new_high=12_000_000_000,
            prior_low=None, prior_high=None,
        )
        assert d == "initiate"


# ────────────────────────────────────────────────────────────────────
# Cat 5 — Event-row builders
# ────────────────────────────────────────────────────────────────────


class TestEventRowBuilders:

    def test_build_financial_disclosure_row(self):
        from services.event_emitters.financial_disclosure import build_financial_disclosure_row
        from services.extraction.financial_disclosure import (
            FinancialDisclosureExtraction,
            FinancialMetric,
        )

        f = FinancialDisclosureExtraction(
            fiscal_period_end=date(2026, 3, 31),
            fiscal_period_label="Q1 2026",
            metrics=[
                FinancialMetric(name="revenue", basis="GAAP", value_usd=14_900_000_000),
                FinancialMetric(name="eps", basis="non-GAAP", value=0.92),
            ],
        )

        row = build_financial_disclosure_row(
            extraction=f,
            company_id="00000000-0000-0000-0000-00000000aaaa",
            company_name="Pfizer Inc.",
            source_document_id="00000000-0000-0000-0000-00000000bbbb",
            disclosed_date=date(2026, 4, 30),
        )

        assert row["event_type"] == "financial_disclosure"
        assert row["primary_entity_name"] == "Pfizer Inc."
        assert row["event_date"] == date(2026, 3, 31)  # period end, not filing date
        assert row["disclosed_date"] == date(2026, 4, 30)
        assert row["source_tier"] == "tier_1"
        assert isinstance(row["event_hash"], str) and len(row["event_hash"]) == 64
        assert "Q1 2026" in row["description"]

    def test_build_guidance_change_row(self):
        from services.event_emitters.financial_disclosure import build_guidance_change_row
        from services.extraction.financial_disclosure import (
            GuidanceIssuance,
            GuidanceMetric,
        )

        g = GuidanceIssuance(
            issued_at=date(2026, 4, 30),
            metric=GuidanceMetric.REVENUE,
            period_label="FY2026",
            basis="non-GAAP",
            range_low=61_000_000_000,
            range_high=64_000_000_000,
            direction="raise",
            prior_range_low=58_500_000_000,
            prior_range_high=61_500_000_000,
        )

        row = build_guidance_change_row(
            issuance=g,
            company_id="00000000-0000-0000-0000-00000000aaaa",
            company_name="Pfizer Inc.",
            source_document_id="00000000-0000-0000-0000-00000000bbbb",
            disclosed_date=date(2026, 4, 30),
        )

        assert row["event_type"] == "guidance_change"
        assert "raise" in row["description"].lower()
        assert "FY2026" in row["description"]
        assert row["impact_hint"] in ("high", "medium")  # raise + magnitude → not low
        assert row["payload"]["direction"] == "raise"
        assert row["payload"]["delta_pct_low"] is not None
        # New low (61) vs prior low (58.5) ≈ +4.27% — verify approximately
        assert 3 < row["payload"]["delta_pct_low"] < 6

    def test_guidance_change_event_hash_deterministic(self):
        from services.event_emitters.financial_disclosure import build_guidance_change_row
        from services.extraction.financial_disclosure import (
            GuidanceIssuance,
            GuidanceMetric,
        )

        g = GuidanceIssuance(
            issued_at=date(2026, 4, 30),
            metric=GuidanceMetric.REVENUE,
            period_label="FY2026",
            basis="non-GAAP",
            range_low=61_000_000_000,
            range_high=64_000_000_000,
            direction="raise",
        )
        kwargs = dict(
            issuance=g,
            company_id="00000000-0000-0000-0000-000000000001",
            company_name="Co",
            source_document_id="00000000-0000-0000-0000-000000000002",
            disclosed_date=date(2026, 4, 30),
        )
        a = build_guidance_change_row(**kwargs)
        b = build_guidance_change_row(**kwargs)
        assert a["event_hash"] == b["event_hash"]

    def test_lower_guidance_is_negative_direction_signal(self):
        """A lower-guidance event should carry direction='negative' on the
        downstream Signal layer."""
        from services.event_emitters.financial_disclosure import build_guidance_change_row
        from services.extraction.financial_disclosure import (
            GuidanceIssuance,
            GuidanceMetric,
        )

        g = GuidanceIssuance(
            issued_at=date(2026, 4, 30),
            metric=GuidanceMetric.REVENUE,
            period_label="FY2026",
            basis="non-GAAP",
            range_low=5_800_000_000,
            range_high=6_200_000_000,
            direction="lower",
            prior_range_low=6_500_000_000,
            prior_range_high=6_900_000_000,
        )
        row = build_guidance_change_row(
            issuance=g,
            company_id="00000000-0000-0000-0000-000000000001",
            company_name="Co",
            source_document_id="00000000-0000-0000-0000-000000000002",
            disclosed_date=date(2026, 4, 30),
        )
        assert row["payload"]["direction"] == "lower"
        # Lower guidance is negative for the company
        assert row["payload"]["signal_direction_hint"] == "negative"
