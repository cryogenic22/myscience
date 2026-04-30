"""Pydantic schema for FDA expedited-program designations.

SPEC-016 §7 swimlane A4.3 (Cycle 8).

Public source: OpenFDA `drug/drugsfda` endpoint exposes per-submission
review_priority and submission_class_code fields. Each maps onto one
or more designation types.

A designation event is a leading indicator of approval and feeds
KBQ 1 (Indications), KBQ 6 (SWOT), and the PoS / risk-tier scoring
in the intelligence layer.
"""

from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


DesignationType = Literal[
    "breakthrough",
    "fast_track",
    "orphan",
    "priority_review",
    "accelerated_approval",
    "rmat",
    "qidp",
]


class FdaDesignation(BaseModel):
    """One FDA expedited-program designation granted to a drug.

    granted_date is the submission_status_date when the designation
    was recorded. application_number ties it back to the underlying
    NDA / BLA / sNDA / sBLA.
    """

    model_config = ConfigDict(extra="forbid")

    drug_name: str = Field(..., min_length=1, max_length=300)
    sponsor_name: str = Field(..., min_length=1, max_length=300)
    designation_type: DesignationType
    granted_date: date
    indication: str = Field(..., min_length=1, max_length=1000)

    application_number: Optional[str] = Field(None, max_length=50)
    submission_number: Optional[str] = Field(None, max_length=50)
    notes: Optional[str] = Field(None, max_length=1000)
