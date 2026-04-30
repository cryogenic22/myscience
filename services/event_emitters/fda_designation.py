"""Event-row builder for fda_designation events.

SPEC-016 §7 swimlane A4.3 (Cycle 8).

Source = OpenFDA → tier_1 (regulator-published). trust_score = 0.95.

Impact-tier hint:
  - breakthrough           → high (significant PoS lift)
  - priority_review        → high (NDA-stage signal of imminent approval)
  - accelerated_approval   → high (approval pathway)
  - rmat / qidp            → medium (program-specific)
  - fast_track             → medium (procedural; less PoS impact than BTD)
  - orphan                 → medium (market-sizing signal more than approval)
"""

from __future__ import annotations

import hashlib
from datetime import date
from typing import Any

from services.extraction.fda_designation import FdaDesignation


_HIGH_IMPACT = {"breakthrough", "priority_review", "accelerated_approval"}
_MEDIUM_IMPACT = {"rmat", "qidp", "fast_track", "orphan"}


def _impact_hint(designation: FdaDesignation) -> str:
    if designation.designation_type in _HIGH_IMPACT:
        return "high"
    if designation.designation_type in _MEDIUM_IMPACT:
        return "medium"
    return "low"


def _compute_event_hash(
    *,
    drug_id: str,
    designation: FdaDesignation,
    source_document_id: str,
) -> str:
    parts = [
        "fda_designation",
        drug_id or "",
        designation.drug_name.strip().lower(),
        designation.designation_type,
        designation.granted_date.isoformat(),
        (designation.application_number or ""),
        (designation.submission_number or ""),
        source_document_id or "",
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _build_description(designation: FdaDesignation) -> str:
    type_label = {
        "breakthrough": "Breakthrough Therapy",
        "fast_track": "Fast Track",
        "orphan": "Orphan Drug",
        "priority_review": "Priority Review",
        "accelerated_approval": "Accelerated Approval",
        "rmat": "RMAT",
        "qidp": "QIDP",
    }.get(designation.designation_type, designation.designation_type)
    return (
        f"{designation.drug_name}: {type_label} designation granted by FDA "
        f"for {designation.indication[:200]}"
    )[:1000]


def build_event_row(
    *,
    designation: FdaDesignation,
    drug_id: str,
    company_id: str,
    company_name: str,
    source_document_id: str,
    disclosed_date: date,
) -> dict[str, Any]:
    payload = {
        "drug_name": designation.drug_name,
        "sponsor_name": designation.sponsor_name,
        "designation_type": designation.designation_type,
        "indication": designation.indication,
        "application_number": designation.application_number,
        "submission_number": designation.submission_number,
        "company_id": company_id,
        "company_name": company_name,
        "notes": designation.notes,
    }
    return {
        "event_type": "fda_designation",
        "description": _build_description(designation),
        "primary_entity_type": "drug",
        "primary_entity_id": drug_id,
        "primary_entity_name": designation.drug_name,
        "event_date": designation.granted_date,
        "disclosed_date": disclosed_date,
        "source_tier": "tier_1",
        "trust_score": 0.95,
        "status": "new",
        "event_hash": _compute_event_hash(
            drug_id=drug_id,
            designation=designation,
            source_document_id=source_document_id,
        ),
        "source_feed": "openfda_designations",
        "impact_hint": _impact_hint(designation),
        "payload": payload,
        "source_document_id": source_document_id,
    }
