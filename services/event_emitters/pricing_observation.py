"""Event-row builder for pricing_observation events.

SPEC-016 §7 swimlane Cycle 12.

Source = CMS ASP / NADAC / NICE etc. → tier_1 (government data).
trust_score = 0.95.

Pricing observations are LOW impact by default — the absolute
quarterly value isn't market-moving. The depth-phase delta detector
(Cycle N+) re-emits price_change events with high impact when ASP
moves more than X% QoQ or when an IRA-negotiated price lands.
"""

from __future__ import annotations

import hashlib
from datetime import date
from typing import Any

from services.extraction.pricing_observation import PricingObservation


def _impact_hint(_obs: PricingObservation) -> str:
    return "low"


def _compute_event_hash(
    *,
    drug_id: str,
    obs: PricingObservation,
    source_document_id: str,
) -> str:
    parts = [
        "pricing_observation",
        drug_id or "",
        obs.hcpcs_code,
        obs.payment_basis,
        obs.source_program,
        obs.period_start.isoformat(),
        obs.period_end.isoformat(),
        f"{obs.payment_limit_usd:.6f}",
        source_document_id or "",
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _build_description(obs: PricingObservation) -> str:
    return (
        f"{obs.hcpcs_code} ({obs.short_description}, {obs.dosage_unit}) "
        f"{obs.payment_basis.upper()} ${obs.payment_limit_usd:.4f} "
        f"({obs.period_start.isoformat()}–{obs.period_end.isoformat()}, "
        f"{obs.source_program})"
    )[:1000]


def build_event_row(
    *,
    observation: PricingObservation,
    drug_id: str,
    source_document_id: str,
    disclosed_date: date,
) -> dict[str, Any]:
    payload = {
        "hcpcs_code": observation.hcpcs_code,
        "short_description": observation.short_description,
        "dosage_unit": observation.dosage_unit,
        "payment_limit_usd": observation.payment_limit_usd,
        "payment_basis": observation.payment_basis,
        "source_program": observation.source_program,
        "period_start": observation.period_start.isoformat(),
        "period_end": observation.period_end.isoformat(),
        "notes": observation.notes,
    }
    return {
        "event_type": "pricing_observation",
        "description": _build_description(observation),
        "primary_entity_type": "drug",
        "primary_entity_id": drug_id,
        "primary_entity_name": observation.short_description,
        "event_date": observation.period_start,
        "disclosed_date": disclosed_date,
        "source_tier": "tier_1",
        "trust_score": 0.95,
        "status": "new",
        "event_hash": _compute_event_hash(
            drug_id=drug_id,
            obs=observation,
            source_document_id=source_document_id,
        ),
        "source_feed": f"cms_{observation.source_program}",
        "impact_hint": _impact_hint(observation),
        "payload": payload,
        "source_document_id": source_document_id,
    }
