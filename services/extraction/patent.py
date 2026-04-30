"""Pydantic schema for USPTO patent records.

SPEC-016 §7 swimlane A5.1 (Cycle 10).

Source: USPTO PatentsView API. Each record represents one granted
patent. The patents table (migration A1.5) consumes these records
directly; the event emitter (services/event_emitters/patent_grant)
also produces a market_event per fresh grant.
"""

from __future__ import annotations

from datetime import date
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class PatentRecord(BaseModel):
    """One USPTO granted patent."""

    model_config = ConfigDict(extra="forbid")

    patent_number: str = Field(..., min_length=1, max_length=50)
    title: str = Field(..., min_length=1, max_length=500)
    assignee_name: str = Field(..., min_length=1, max_length=500)
    grant_date: date

    abstract: Optional[str] = Field(None, max_length=10000)
    filing_date: Optional[date] = None
    application_number: Optional[str] = Field(None, max_length=50)
    inventors: List[str] = Field(default_factory=list)
    num_claims: Optional[int] = Field(None, ge=0)
    cpc_groups: List[str] = Field(default_factory=list)
    assignee_country: Optional[str] = Field(None, max_length=20)
