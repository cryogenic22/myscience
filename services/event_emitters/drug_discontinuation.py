"""Event-row builder for drug_discontinuation events.

SPEC-016 §7 swimlane A4.4 (Cycle 9).

Source = OpenFDA drugsfda → tier_1 (regulator-published).
trust_score = 0.95.

Impact-tier hint:
  - withdrawn (often safety-related)  → high
  - discontinued (commercial / sponsor decision) → medium
"""

from __future__ import annotations

import hashlib
from datetime import date
from typing import Any

from services.extraction.drug_discontinuation import DrugDiscontinuation


def _impact_hint(record: DrugDiscontinuation) -> str:
    if record.marketing_status == "withdrawn":
        return "high"
    return "medium"


def _compute_event_hash(
    *,
    drug_id: str,
    record: DrugDiscontinuation,
    source_document_id: str,
) -> str:
    parts = [
        "drug_discontinuation",
        drug_id or "",
        record.application_number,
        record.product_number,
        record.marketing_status,
        record.observed_date.isoformat(),
        source_document_id or "",
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _build_description(record: DrugDiscontinuation) -> str:
    verb = {
        "discontinued": "discontinued",
        "withdrawn": "withdrawn for sale",
    }.get(record.marketing_status, record.marketing_status)
    strength = f" {record.strength}" if record.strength else ""
    return (
        f"{record.drug_name}{strength} ({record.application_number}-"
        f"{record.product_number}) {verb} per Drugs@FDA"
    )[:1000]


def build_event_row(
    *,
    record: DrugDiscontinuation,
    drug_id: str,
    company_id: str,
    company_name: str,
    source_document_id: str,
    disclosed_date: date,
) -> dict[str, Any]:
    payload = {
        "drug_name": record.drug_name,
        "sponsor_name": record.sponsor_name,
        "application_number": record.application_number,
        "product_number": record.product_number,
        "marketing_status": record.marketing_status,
        "dosage_form": record.dosage_form,
        "strength": record.strength,
        "route": record.route,
        "company_id": company_id,
        "company_name": company_name,
        "notes": record.notes,
    }
    return {
        "event_type": "drug_discontinuation",
        "description": _build_description(record),
        "primary_entity_type": "drug",
        "primary_entity_id": drug_id,
        "primary_entity_name": record.drug_name,
        "event_date": record.observed_date,
        "disclosed_date": disclosed_date,
        "source_tier": "tier_1",
        "trust_score": 0.95,
        "status": "new",
        "event_hash": _compute_event_hash(
            drug_id=drug_id,
            record=record,
            source_document_id=source_document_id,
        ),
        "source_feed": "openfda_discontinuations",
        "impact_hint": _impact_hint(record),
        "payload": payload,
        "source_document_id": source_document_id,
    }
