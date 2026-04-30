"""Event-row builder for biosimilar_approval events.

SPEC-016 §7 swimlane Cycle 11.

Source = FDA Purple Book → tier_1. trust_score = 0.95.

Design choice: the primary entity is the REFERENCE branded biologic
(the threat target), not the biosimilar itself. The intelligence
layer needs these events on the brand timeline (e.g. "Humira's
biosimilar competition"). The biosimilar drug_id is carried in the
payload for cross-linking.

Both biosimilar and interchangeable approvals are HIGH impact —
interchangeable a touch more so (auto-substitution at the pharmacy
counter without prescriber re-write).
"""

from __future__ import annotations

import hashlib
from datetime import date
from typing import Any

from services.extraction.biologic_product import BiologicProduct


def _impact_hint(_product: BiologicProduct) -> str:
    return "high"


def _compute_event_hash(
    *,
    product: BiologicProduct,
    reference_drug_id: str,
    source_document_id: str,
) -> str:
    parts = [
        "biosimilar_approval",
        reference_drug_id or "",
        product.bla_number,
        product.proper_name.strip().lower(),
        product.approval_date.isoformat(),
        source_document_id or "",
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _build_description(product: BiologicProduct) -> str:
    label = "biosimilar"
    if product.bla_type == "interchangeable":
        label = "interchangeable biosimilar"
    ref = product.ref_product_proprietary_name or "(reference brand)"
    return (
        f"{product.proprietary_name} ({product.proper_name}) approved as a "
        f"{label} to {ref} — applicant {product.applicant}"
    )[:1000]


def build_event_row(
    *,
    product: BiologicProduct,
    biosimilar_drug_id: str,
    reference_drug_id: str,
    applicant_company_id: str,
    source_document_id: str,
    disclosed_date: date,
) -> dict[str, Any]:
    payload = {
        "proprietary_name": product.proprietary_name,
        "proper_name": product.proper_name,
        "bla_number": product.bla_number,
        "bla_type": product.bla_type,
        "applicant": product.applicant,
        "ref_product_proprietary_name": product.ref_product_proprietary_name,
        "ref_product_proper_name": product.ref_product_proper_name,
        "biosimilar_drug_id": biosimilar_drug_id,
        "applicant_company_id": applicant_company_id,
        "strength": product.strength,
        "dosage_form": product.dosage_form,
        "route_of_administration": product.route_of_administration,
    }

    return {
        "event_type": "biosimilar_approval",
        "description": _build_description(product),
        "primary_entity_type": "drug",
        "primary_entity_id": reference_drug_id,
        "primary_entity_name": product.ref_product_proprietary_name
                                or product.ref_product_proper_name
                                or "(reference biologic)",
        "event_date": product.approval_date,
        "disclosed_date": disclosed_date,
        "source_tier": "tier_1",
        "trust_score": 0.95,
        "status": "new",
        "event_hash": _compute_event_hash(
            product=product,
            reference_drug_id=reference_drug_id,
            source_document_id=source_document_id,
        ),
        "source_feed": "fda_purple_book",
        "impact_hint": _impact_hint(product),
        "payload": payload,
        "source_document_id": source_document_id,
    }
