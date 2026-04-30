"""Pydantic schema for pricing observations.

SPEC-016 §7 swimlane Cycle 12.

A PricingObservation is one HCPCS-keyed price point for a given
period. Sources can be CMS ASP (Medicare Part B), CMS NADAC (retail
acquisition cost, Part D), state Medicaid pricing, or international
HTA prices. The schema is generic enough to cover all of them.

The deltas matter more than the absolute level (price changes drive
analysis), but the unified market_events stream stores observations
and the diff service (Cycle N+) emits price_change events keyed off
QoQ deltas.
"""

from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# Open enum — extensible. Add nadac, wac, awp, nice_ta, iqwig, etc.
PaymentBasis = Literal["asp", "nadac", "wac", "awp", "nice_ta", "iqwig"]

# Where the observation comes from
SourceProgram = Literal[
    "medicare_part_b",
    "medicare_part_d",
    "medicaid",
    "nice_uk",
    "iqwig_de",
    "other",
]


class PricingObservation(BaseModel):
    """One pricing observation for a HCPCS-keyed product."""

    model_config = ConfigDict(extra="forbid")

    hcpcs_code: str = Field(..., min_length=1, max_length=20)
    short_description: str = Field(..., min_length=1, max_length=500)
    dosage_unit: str = Field(..., min_length=1, max_length=100)

    payment_limit_usd: float = Field(..., gt=0)
    payment_basis: PaymentBasis
    source_program: SourceProgram

    period_start: date
    period_end: date

    notes: Optional[str] = Field(None, max_length=500)
