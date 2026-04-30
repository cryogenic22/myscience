"""Pydantic schema for FDA Purple Book biologic products.

SPEC-016 §7 swimlane Cycle 11.

The Purple Book is the canonical FDA list of licensed biologics +
biosimilars + interchangeables. Each row represents one BLA-approved
product. Reference-product fields are populated for biosimilars and
interchangeables only (originals leave them null).
"""

from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


BlaType = Literal["original", "biosimilar", "interchangeable"]
LicenseStatus = Literal["licensed", "withdrawn", "pending"]


class BiologicProduct(BaseModel):
    """One Purple Book row."""

    model_config = ConfigDict(extra="forbid")

    proprietary_name: str = Field(..., min_length=1, max_length=300)
    proper_name: str = Field(..., min_length=1, max_length=300)
    bla_number: str = Field(..., min_length=1, max_length=50)
    bla_type: BlaType
    license_status: LicenseStatus
    approval_date: date
    applicant: str = Field(..., min_length=1, max_length=300)

    strength: Optional[str] = Field(None, max_length=200)
    dosage_form: Optional[str] = Field(None, max_length=100)
    route_of_administration: Optional[str] = Field(None, max_length=100)
    product_presentation: Optional[str] = Field(None, max_length=200)

    # Populated for biosimilar / interchangeable rows only
    ref_product_proprietary_name: Optional[str] = Field(None, max_length=300)
    ref_product_proper_name: Optional[str] = Field(None, max_length=300)
