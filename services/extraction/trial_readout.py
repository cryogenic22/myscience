"""Pydantic schemas for press-release trial readout extraction.

SPEC-016 §7 swimlane A3.3 (Cycle 4).

Companies issue press releases when a trial reads out — typically
hours to days before the conference / journal publication. The
press release is a tier-2 signal (company self-reported); the same
result later confirmed by CT.gov posted_results / journal pub /
FDA approval is tier-1.

Drives the `trial_readout` market_event. The corroboration loop
later promotes confidence_tier="reported" → "confirmed" when a
matching CT.gov posted_results row, journal pub, or FDA approval
arrives within the corroboration window.
"""

from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# ────────────────────────────────────────────────────────────────────
# Enumerations
# ────────────────────────────────────────────────────────────────────


# Mirrors the normalised phase values produced by the CT.gov connector
# (see _normalize_phase). N/A = phase-agnostic / device / observational.
TrialPhase = Literal[
    "Early Phase 1",
    "Phase 1",
    "Phase 1, Phase 2",
    "Phase 2",
    "Phase 2, Phase 3",
    "Phase 3",
    "Phase 4",
    "N/A",
]


EndpointType = Literal["primary", "secondary", "exploratory"]


# ────────────────────────────────────────────────────────────────────
# EfficacyOutcome — one numeric line of the readout
# ────────────────────────────────────────────────────────────────────


class EfficacyOutcome(BaseModel):
    """Structured efficacy result. Optional fields handle the common
    cases (HR + p-value, response rate %, ORR, OS / PFS / DFS hazard
    ratio etc.) without forcing the LLM to invent data.
    """

    model_config = ConfigDict(extra="forbid")

    endpoint_name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Plain-English endpoint name as stated "
                    "(\"progression-free survival\", \"overall response rate\").",
    )
    endpoint_type: EndpointType = Field(
        ...,
        description="primary | secondary | exploratory",
    )
    met: bool = Field(
        ...,
        description="Did this specific endpoint meet its statistical bar?",
    )

    # Optional structured numerics — extract only when stated explicitly
    hazard_ratio: Optional[float] = Field(
        None, ge=0.0, le=10.0,
        description="HR if a survival/time-to-event endpoint and stated.",
    )
    p_value: Optional[float] = Field(
        None, ge=0.0, le=1.0,
        description="P-value of the primary statistical test, if stated.",
    )
    ci_low: Optional[float] = Field(
        None, ge=0.0, le=10.0,
        description="Lower bound of the confidence interval (typically 95%).",
    )
    ci_high: Optional[float] = Field(
        None, ge=0.0, le=10.0,
        description="Upper bound of the confidence interval (typically 95%).",
    )

    response_rate_pct: Optional[float] = Field(
        None, ge=0.0, le=100.0,
        description="Response rate as a percent (ORR, CR rate, etc.).",
    )

    sample_size: Optional[int] = Field(
        None, ge=1,
        description="Number of patients evaluated for THIS endpoint.",
    )


# ────────────────────────────────────────────────────────────────────
# TrialReadoutExtraction — top-level extraction for a press release
# ────────────────────────────────────────────────────────────────────


class TrialReadoutExtraction(BaseModel):
    """Structured readout from a company press release.

    The trial_identifier is whatever the press release uses — NCT id,
    acronym, or sponsor protocol id. The runner / orchestrator does
    the trial-id resolution via entity_aliases.
    """

    model_config = ConfigDict(extra="forbid")

    # ---- Trial identification ---------------------------------------
    trial_identifier: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="NCT id, acronym, or sponsor protocol id as stated "
                    "in the press release.",
    )
    phase: TrialPhase = Field(
        ...,
        description="Phase of the trial reading out.",
    )

    # ---- Subject ---------------------------------------------------
    drug_name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Drug code, generic, or brand name as stated.",
    )
    sponsor_name: Optional[str] = Field(
        None, max_length=200,
        description="Lead sponsor as stated. Used for entity resolution.",
    )
    indication: Optional[str] = Field(
        None, max_length=300,
        description="Indication / disease area being studied "
                    "(\"HER2-positive breast cancer\").",
    )

    # ---- Headline result -------------------------------------------
    primary_endpoint_met: bool = Field(
        ...,
        description="Did the trial meet its PRIMARY endpoint? Most "
                    "important boolean. A secondary-only positive readout "
                    "with a missed primary is False.",
    )

    readout_date: date = Field(
        ...,
        description="Date the readout was announced. The event_date.",
    )

    sample_size: Optional[int] = Field(
        None, ge=1,
        description="Total trial sample size if stated.",
    )

    # ---- Detailed efficacy -----------------------------------------
    efficacy_outcomes: list[EfficacyOutcome] = Field(
        default_factory=list,
        description="One entry per stated endpoint with structured numerics.",
    )

    # ---- Safety / tolerability summary ------------------------------
    safety_summary: Optional[str] = Field(
        None, max_length=1000,
        description="Free-text summary of TEAEs / SAEs as stated.",
    )

    # ---- Headline / company narrative --------------------------------
    headline_summary: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="One-paragraph narrative summary of the readout. "
                    "Used for event.description.",
    )
