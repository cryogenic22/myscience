"""Event-row builder for ema_chmp_opinion events.

SPEC-016 §7 swimlane A6.1 (Cycle 7).

Source = EMA CHMP meeting-highlights → tier_1 (regulator-published).
trust_score = 0.95.

Impact-tier hint:
  - positive (first MA recommendation)  → high
  - negative                             → high
  - withdrawn                            → high
  - extension (label expansion)          → medium
"""

from __future__ import annotations

import hashlib
from datetime import date
from typing import Any

from services.extraction.ema_chmp_opinion import ChmpOpinion


_HIGH_IMPACT_TYPES = {"positive", "negative", "withdrawn"}


def _impact_hint(opinion: ChmpOpinion) -> str:
    if opinion.opinion_type in _HIGH_IMPACT_TYPES:
        return "high"
    return "medium"


def _compute_event_hash(
    *,
    drug_id: str,
    opinion: ChmpOpinion,
    source_document_id: str,
) -> str:
    parts = [
        "ema_chmp_opinion",
        drug_id or "",
        opinion.inn.strip().lower(),
        opinion.opinion_type,
        opinion.opinion_date.isoformat(),
        opinion.indication.strip().lower()[:200],
        source_document_id or "",
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _build_description(opinion: ChmpOpinion) -> str:
    verb = {
        "positive": "recommended for approval",
        "negative": "received negative opinion",
        "withdrawn": "application withdrawn",
        "extension": "recommended for new indication",
    }.get(opinion.opinion_type, "CHMP opinion")
    return (
        f"{opinion.brand_name} ({opinion.inn}) {verb} by CHMP "
        f"for {opinion.indication[:200]}"
    )[:1000]


def build_event_row(
    *,
    opinion: ChmpOpinion,
    drug_id: str,
    company_id: str,
    company_name: str,
    source_document_id: str,
    disclosed_date: date,
) -> dict[str, Any]:
    payload = {
        "inn": opinion.inn,
        "brand_name": opinion.brand_name,
        "applicant": opinion.applicant,
        "opinion_type": opinion.opinion_type,
        "indication": opinion.indication,
        "company_id": company_id,
        "company_name": company_name,
        "notes": opinion.notes,
    }
    return {
        "event_type": "ema_chmp_opinion",
        "description": _build_description(opinion),
        "primary_entity_type": "drug",
        "primary_entity_id": drug_id,
        "primary_entity_name": opinion.brand_name,
        "event_date": opinion.opinion_date,
        "disclosed_date": disclosed_date,
        "source_tier": "tier_1",
        "trust_score": 0.95,
        "status": "new",
        "event_hash": _compute_event_hash(
            drug_id=drug_id,
            opinion=opinion,
            source_document_id=source_document_id,
        ),
        "source_feed": "ema_chmp_highlights",
        "impact_hint": _impact_hint(opinion),
        "payload": payload,
        "source_document_id": source_document_id,
    }
