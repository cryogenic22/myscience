"""Build market_events row dict for a regulatory_crl extraction.

SPEC-016 §7 swimlane A2.4. CRL events are ALWAYS:
  - tier_1 (SEC filing source)
  - high impact (per CI design)
  - negative direction (downstream Signal layer reads this)
"""

from __future__ import annotations

import hashlib
from datetime import date
from typing import Any, Optional

from services.extraction.regulatory_crl import CRLExtraction


def _compute_event_hash(
    *,
    primary_entity_id: str,
    extraction: CRLExtraction,
    source_document_id: str,
) -> str:
    parts = [
        "regulatory_crl",
        primary_entity_id or "",
        extraction.agency,
        extraction.received_date.isoformat(),
        (extraction.application_type or ""),
        (extraction.application_number or ""),
        (extraction.drug_name or "").strip().lower(),
        source_document_id or "",
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _build_description(
    extraction: CRLExtraction,
    company_name: str,
) -> str:
    drug = extraction.drug_name or "(drug undisclosed)"
    indication = (
        f" for {extraction.indication}" if extraction.indication else ""
    )
    app = ""
    if extraction.application_type and extraction.application_number:
        app = f" ({extraction.application_type} #{extraction.application_number})"
    elif extraction.application_type:
        app = f" ({extraction.application_type})"
    reasons = ""
    if extraction.reason_categories:
        reasons = f" — reasons cited: {', '.join(extraction.reason_categories)}"

    return (
        f"{company_name}: {extraction.agency} Complete Response Letter "
        f"for {drug}{indication}{app}{reasons}"
    )


def build_event_row(
    *,
    extraction: CRLExtraction,
    company_id: str,
    company_name: str,
    drug_id: Optional[str],
    source_document_id: str,
    disclosed_date: date,
) -> dict[str, Any]:
    """Build a market_events row for a regulatory_crl event.

    primary_entity is the DRUG when drug_id is resolved; falls back to
    the company when not. CRLs are always high-impact and negative.
    """
    if drug_id:
        primary_entity_type = "drug"
        primary_entity_id = drug_id
        primary_entity_name = extraction.drug_name
    else:
        primary_entity_type = "company"
        primary_entity_id = company_id
        primary_entity_name = company_name

    return {
        "event_type": "regulatory_crl",
        "description": _build_description(extraction, company_name),
        "primary_entity_type": primary_entity_type,
        "primary_entity_id": primary_entity_id,
        "primary_entity_name": primary_entity_name,
        "event_date": extraction.received_date,
        "disclosed_date": disclosed_date,
        "source_tier": "tier_1",
        "trust_score": 0.95,
        "status": "new",
        "event_hash": _compute_event_hash(
            primary_entity_id=primary_entity_id,
            extraction=extraction,
            source_document_id=source_document_id,
        ),
        "source_feed": "sec_8k_item_8_01",
        "impact_hint": "high",  # CRLs are always high
        "payload": {
            "agency": extraction.agency,
            "application_type": extraction.application_type,
            "application_number": extraction.application_number,
            "drug_name": extraction.drug_name,
            "drug_id": drug_id,
            "indication": extraction.indication,
            "reason_categories": extraction.reason_categories,
            "plan_for_response": extraction.plan_for_response,
            "company_id": company_id,
            "company_name": company_name,
            "signal_direction_hint": "negative",  # always
            "notes": extraction.notes,
        },
        "source_document_id": source_document_id,
    }
