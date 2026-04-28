"""Pydantic schema for 8-K Item 1.01 extraction → deal_announced events.

SPEC-016 §7 swimlane A2.2. Aligns with the deals-table schema from
A1.6 (migration 042) and the OpenAPI intel.yaml event_type='deal_announced'.

Sanity validators per critique R6:
  - upfront + max_milestones <= total_potential * 1.05 (5% rounding slack)
  - royalty range in [0, 30] percent, low <= high
  - deal_types non-empty, all members from the agreed enum
"""

from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


DealType = Literal[
    "acquisition",
    "asset_purchase",
    "license_in",
    "license_out",
    "collaboration",
    "option",
    "co_promotion",
    "co_development",
    "royalty_monetisation",
]


class DealExtraction(BaseModel):
    """A single deal extracted from an Item 1.01 narrative.

    deal_types is COMPOSITE — a deal can be license_in + co_development +
    option simultaneously. Direction-aware party fields: acquirer/target
    for M&A; licensor/licensee for licenses. Both pairs may be present
    on composite deals (e.g. acquisition + license-back).
    """

    model_config = ConfigDict(extra="forbid")

    # Deal classification — composite array, at least one member
    deal_types: list[DealType] = Field(
        ...,
        min_length=1,
        description="Composite type list. >=1 member required.",
    )

    # When was it announced (filing exhibit's stated date — NOT the 8-K
    # filing date, which can lag by up to 4 business days)
    announced_date: date = Field(...)
    closing_date: Optional[date] = Field(
        None,
        description="Expected/actual closing. None for licenses with no "
                    "separate close.",
    )

    # Parties — direction matters
    acquirer_name: Optional[str] = None
    target_name: Optional[str] = None
    licensor_name: Optional[str] = None
    licensee_name: Optional[str] = None

    # Subject
    subject_drug_names: list[str] = Field(default_factory=list)
    subject_indication: Optional[str] = Field(
        None,
        description="Free-text indication descriptor. Resolver maps to "
                    "therapeutic_areas / indications when possible.",
    )
    geography: Optional[str] = Field(
        None,
        description='ISO country code, "WW" worldwide, "EU5", "ROW", etc.',
    )

    # Financial terms
    currency: str = Field("USD", min_length=3, max_length=3)
    upfront_disclosed: bool = Field(
        True,
        description="Set to False when the press release says terms are "
                    "undisclosed. UI flags this prominently — never imply "
                    "small deal by absent number.",
    )
    upfront_value_usd: Optional[float] = Field(
        None,
        ge=0,
        description="USD upfront payment. None if not disclosed.",
    )
    milestones_total_usd: Optional[float] = Field(
        None,
        ge=0,
        description="Sum of all milestone potentials.",
    )
    total_potential_usd: Optional[float] = Field(
        None,
        ge=0,
        description="Headline 'biobucks' figure. Sanity-checked vs "
                    "upfront + milestones.",
    )
    royalty_range_low_pct: Optional[float] = Field(
        None,
        ge=0,
        le=30,
        description="Royalty floor percentage (0-30).",
    )
    royalty_range_high_pct: Optional[float] = Field(
        None,
        ge=0,
        le=30,
        description="Royalty ceiling percentage (0-30).",
    )
    equity_component: bool = Field(
        False,
        description="True if the deal includes equity (warrants, stock).",
    )

    # Free-text notes — preserved for analyst review
    notes: Optional[str] = Field(None, max_length=1000)

    # ── Validators ──

    @field_validator("currency")
    @classmethod
    def _currency_uppercase(cls, v: str) -> str:
        return v.upper()

    @model_validator(mode="after")
    def _check_term_sanity(self) -> "DealExtraction":
        """upfront + max_milestones <= total_potential * 1.05.

        Per critique R6 — catches LLM extraction errors. Only enforced
        when all three values are present; NULLs short-circuit (we
        can't verify what we don't have).
        """
        if (
            self.upfront_value_usd is not None
            and self.milestones_total_usd is not None
            and self.total_potential_usd is not None
        ):
            implied = self.upfront_value_usd + self.milestones_total_usd
            if implied > self.total_potential_usd * 1.05:
                raise ValueError(
                    f"term sanity: upfront ({self.upfront_value_usd}) + "
                    f"milestones ({self.milestones_total_usd}) = {implied} "
                    f"> total_potential ({self.total_potential_usd}) * 1.05"
                )
        return self

    @model_validator(mode="after")
    def _check_royalty_range(self) -> "DealExtraction":
        if (
            self.royalty_range_low_pct is not None
            and self.royalty_range_high_pct is not None
        ):
            if self.royalty_range_low_pct > self.royalty_range_high_pct:
                raise ValueError(
                    f"royalty range: low ({self.royalty_range_low_pct}) > "
                    f"high ({self.royalty_range_high_pct})"
                )
        return self
