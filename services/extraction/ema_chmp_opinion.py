"""Pydantic schema for EMA CHMP opinion extraction.

SPEC-016 §7 swimlane A6.1 (Cycle 7).

The CHMP (Committee for Medicinal Products for Human Use) issues
monthly opinions on Marketing Authorization Applications:

  positive  — recommendation for approval (first MAA)
  negative  — recommendation against approval
  withdrawn — applicant withdrew the application
  extension — recommendation for a new indication on an existing MAA

These map 1:1 to ema_chmp_opinion market_events.
"""

from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


OpinionType = Literal["positive", "negative", "withdrawn", "extension"]


class ChmpOpinion(BaseModel):
    """One CHMP opinion row from a meeting-highlights page."""

    model_config = ConfigDict(extra="forbid")

    inn: str = Field(
        ...,
        min_length=1, max_length=200,
        description="International Non-proprietary Name (e.g. tirzepatide).",
    )
    brand_name: str = Field(
        ...,
        min_length=1, max_length=200,
        description="EU brand name (often 'invented name' on the EMA page).",
    )
    applicant: str = Field(
        ...,
        min_length=1, max_length=300,
        description="Applicant / future MAH (e.g. 'Eli Lilly Nederland B.V.').",
    )
    opinion_type: OpinionType = Field(...)
    opinion_date: date = Field(
        ...,
        description="Last day of the CHMP meeting at which the opinion "
                    "was adopted. Sourced from the meeting heading.",
    )
    indication: str = Field(
        ...,
        min_length=1, max_length=1000,
        description="Indication being recommended for / extended to.",
    )

    notes: Optional[str] = Field(None, max_length=1000)
