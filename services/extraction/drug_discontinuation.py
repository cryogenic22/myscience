"""Pydantic schema for FDA drug discontinuation observations.

SPEC-016 §7 swimlane A4.4 (Cycle 9).

Source: OpenFDA drugsfda.json `products[].marketing_status` field.
Two terminal states feed the discontinuation stream:

  discontinued  — sponsor has stopped marketing in the US
  withdrawn     — withdrawn for sale (often safety-related)

Each record represents one product-level observation. Application
+ product number identifies the unique SKU.
"""

from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


MarketingStatus = Literal["discontinued", "withdrawn"]


class DrugDiscontinuation(BaseModel):
    """One discontinued / withdrawn drug-product observation."""

    model_config = ConfigDict(extra="forbid")

    drug_name: str = Field(..., min_length=1, max_length=300)
    sponsor_name: str = Field(..., min_length=1, max_length=300)
    application_number: str = Field(..., max_length=50)
    product_number: str = Field(..., max_length=50)
    marketing_status: MarketingStatus
    observed_date: date

    dosage_form: Optional[str] = Field(None, max_length=100)
    strength: Optional[str] = Field(None, max_length=100)
    route: Optional[str] = Field(None, max_length=100)
    notes: Optional[str] = Field(None, max_length=500)
