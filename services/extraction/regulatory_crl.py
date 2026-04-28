"""Pydantic schema for 8-K Item 8.01 CRL extraction → regulatory_crl events.

SPEC-016 §7 swimlane A2.4. Per critique §2 KBQ 9 deep-dive: the FDA
does NOT publicly announce CRLs. The path to a CRL signal is the 8-K
Item 8.01 disclosure where the company discloses it.

CRL = Complete Response Letter — FDA's "no, not yet" letter. Always
high-impact, always negative direction.
"""

from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


Agency = Literal["FDA", "EMA", "MHRA", "PMDA", "Health_Canada", "TGA"]

ApplicationType = Literal[
    "NDA", "BLA", "ANDA", "sNDA", "sBLA", "510k", "PMA",
    "MAA", "JMA",  # EU / JP equivalents
]


# Open enum — extensible. Common categories so signal scoring + UI can
# colour-code reasons.
ReasonCategory = Literal[
    "additional_efficacy_data",
    "additional_safety_data",
    "manufacturing_cmc",         # chemistry, manufacturing, controls
    "facility_inspection",
    "labelling",
    "post_marketing_commitment",
    "trial_design",
    "comparator_arm",
    "biostatistics",
    "other",
]


class CRLExtraction(BaseModel):
    """A Complete Response Letter from a regulator."""

    model_config = ConfigDict(extra="forbid")

    agency: Agency = Field(...)
    received_date: date = Field(
        ...,
        description="Date the company received the letter. Often differs "
                    "from filing date by 1-4 days.",
    )

    application_type: Optional[ApplicationType] = None
    application_number: Optional[str] = Field(
        None,
        description='Regulatory application number (e.g. "218237" for an FDA NDA).',
    )

    drug_name: Optional[str] = Field(
        None,
        description="Drug code or generic name as stated in the filing. "
                    "Resolver maps to drugs.id when possible.",
    )
    indication: Optional[str] = Field(
        None,
        description="Indication being sought (free text — resolver maps "
                    "to therapeutic_areas / indications when possible).",
    )

    reason_categories: list[ReasonCategory] = Field(
        default_factory=list,
        description="Coded reasons. >=1 typical; FDA usually states multiple.",
    )

    plan_for_response: Optional[str] = Field(
        None,
        max_length=500,
        description="Free-text summary of how the company plans to respond "
                    '("request Type A meeting", "resubmit within twelve months").',
    )

    notes: Optional[str] = Field(None, max_length=1000)
