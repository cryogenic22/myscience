"""Pydantic schemas for 8-K Item 2.02 extraction → financial + guidance.

SPEC-016 §7 swimlane A2.3.

Item 2.02 produces TWO event types per filing:
  - financial_disclosure : the period's reported numbers
  - guidance_change      : delta vs prior issuance, when guidance is
                           issued / raised / lowered / reaffirmed /
                           narrowed / withdrawn

The signal that matters to a CI analyst is usually the GUIDANCE CHANGE
(delta), not the absolute numbers (per critique §2 KBQ 1 deep-dive).
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ────────────────────────────────────────────────────────────────────
# Financial disclosure (period-level reported figures)
# ────────────────────────────────────────────────────────────────────


MetricBasis = Literal["GAAP", "non-GAAP"]


class FinancialMetric(BaseModel):
    """One reported financial metric.

    Use `value_usd` for currency amounts (revenue, R&D, SG&A);
    use `value` for ratios / per-share / counts (EPS, headcount).
    Exactly one of (value, value_usd) must be set on a real metric.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        ...,
        min_length=1,
        description="Canonical metric name: revenue | eps | rd | sga | "
                    "operating_income | net_income | margin | gross_margin | "
                    "free_cash_flow | …",
    )
    basis: MetricBasis
    value: Optional[float] = Field(
        None, description="Numeric value (per-share, ratio, count).",
    )
    value_usd: Optional[float] = Field(
        None, description="USD currency amount (full dollars, not millions).",
    )

    @model_validator(mode="after")
    def _exactly_one_value(self) -> "FinancialMetric":
        if (self.value is None) == (self.value_usd is None):
            raise ValueError(
                "FinancialMetric must have exactly one of value / value_usd"
            )
        return self


class FinancialDisclosureExtraction(BaseModel):
    """Reported financials for a fiscal period.

    Drives the `financial_disclosure` event. Absolute numbers — these
    are ALSO available via XBRL once the 10-Q lands a few weeks later;
    the 8-K Item 2.02 path gives an early read.
    """

    model_config = ConfigDict(extra="forbid")

    fiscal_period_end: date = Field(
        ...,
        description="Last day of the fiscal period being reported (the "
                    "event_date for the financial_disclosure event).",
    )
    fiscal_period_label: str = Field(
        ...,
        min_length=1,
        description='Human label: "Q1 2026", "FY2025", etc.',
    )
    metrics: list[FinancialMetric] = Field(default_factory=list)


# ────────────────────────────────────────────────────────────────────
# Guidance issuance (forward-looking)
# ────────────────────────────────────────────────────────────────────


class GuidanceMetric(str, Enum):
    REVENUE = "revenue"
    EPS = "eps"
    RD = "rd"
    SGA = "sga"
    OPERATING_INCOME = "operating_income"
    NET_INCOME = "net_income"
    MARGIN = "margin"
    GROSS_MARGIN = "gross_margin"
    FREE_CASH_FLOW = "free_cash_flow"
    OTHER = "other"


GuidanceDirection = Literal[
    "raise",     # range moved up
    "lower",     # range moved down
    "reaffirm",  # range unchanged
    "narrow",    # range tightened (midpoint same; bounds closer)
    "initiate",  # first time guidance issued for this period
    "withdraw",  # guidance pulled (no new range)
]


class GuidanceIssuance(BaseModel):
    """A single guidance issuance — drives the guidance_change event.

    Range fields use raw numbers (USD or per-share). EPS guidance:
    range_low/high in dollars (e.g. 2.95). Revenue guidance: dollars
    (e.g. 61_000_000_000).
    """

    model_config = ConfigDict(extra="forbid")

    issued_at: date = Field(
        ...,
        description="Date the company issued this guidance (filing date).",
    )
    metric: GuidanceMetric
    period_label: str = Field(
        ...,
        min_length=1,
        description='"FY2026", "Q4 2026", etc.',
    )
    basis: MetricBasis

    # Direction
    direction: GuidanceDirection

    # Range (None on withdraw)
    range_low: Optional[float] = None
    range_high: Optional[float] = None

    # Prior range (None on initiate; required-ish on raise/lower/narrow but
    # not strictly enforced — sometimes the LLM can't extract it from the
    # current filing alone and the diff service supplies it from history)
    prior_range_low: Optional[float] = None
    prior_range_high: Optional[float] = None

    # Free text — useful as evidence in the synthesis
    notes: Optional[str] = Field(None, max_length=500)

    @model_validator(mode="after")
    def _check_ranges(self) -> "GuidanceIssuance":
        if (
            self.range_low is not None
            and self.range_high is not None
            and self.range_low > self.range_high
        ):
            raise ValueError(
                f"range_low ({self.range_low}) > range_high ({self.range_high})"
            )
        if (
            self.prior_range_low is not None
            and self.prior_range_high is not None
            and self.prior_range_low > self.prior_range_high
        ):
            raise ValueError(
                f"prior_range_low ({self.prior_range_low}) > "
                f"prior_range_high ({self.prior_range_high})"
            )
        return self
