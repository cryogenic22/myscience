"""Event-row builder for press-release trial readout events.

SPEC-016 §7 swimlane A3.3 (Cycle 4).

Source = company press release → tier_2 trust score (~0.75). Lower
than SEC 8-K (tier_1 = 0.95) because:
  - Companies cherry-pick favourable framings
  - The full numerics often omit secondary endpoints
  - Confirmation lags (CT.gov posted_results / journal pub) lift it
    to confirmed-tier later via the corroboration loop.

Idempotency: event_hash is SHA-256 over (trial_id, drug_name,
phase, primary_endpoint_met, readout_date, source_document_id).
Re-running yields the same hash → ON CONFLICT DO NOTHING.

Impact-tier hint:
  - Phase 3 readout                                → high
  - Phase 3 missed primary                          → high (negative; market-moving)
  - Phase 2/2-3                                     → medium
  - Earlier phase / missed primary on early phase   → low
"""

from __future__ import annotations

import hashlib
from datetime import date
from typing import Any

from services.extraction.trial_readout import TrialReadoutExtraction


# ────────────────────────────────────────────────────────────────────
# Impact-tier hint
# ────────────────────────────────────────────────────────────────────


def _impact_hint(extraction: TrialReadoutExtraction) -> str:
    phase = extraction.phase
    missed = not extraction.primary_endpoint_met

    # Missed primary in any registrational phase moves markets harder
    # than a positive readout — Phase 2 missed = high too.
    if missed and phase in {"Phase 2", "Phase 2, Phase 3", "Phase 3"}:
        return "high"
    if phase == "Phase 3" or phase == "Phase 2, Phase 3":
        return "high"
    if phase in {"Phase 2", "Phase 1, Phase 2"}:
        return "medium"
    return "low"


# ────────────────────────────────────────────────────────────────────
# Trust score (tier_2 baseline; corroboration loop promotes/demotes)
# ────────────────────────────────────────────────────────────────────


def _trust_score(extraction: TrialReadoutExtraction) -> float:
    """Press release baseline = 0.75. Slightly higher when full numerics
    are present (HR + p-value + CI) since fabricated numerics are rarer
    than fabricated framings."""
    base = 0.75
    has_full_numerics = any(
        eo.hazard_ratio is not None and eo.p_value is not None
        for eo in extraction.efficacy_outcomes
    )
    if has_full_numerics:
        base = 0.78
    return base


# ────────────────────────────────────────────────────────────────────
# Event hash — idempotency key
# ────────────────────────────────────────────────────────────────────


def _compute_event_hash(
    *,
    trial_id: str,
    extraction: TrialReadoutExtraction,
    source_document_id: str,
) -> str:
    parts = [
        "trial_readout",
        trial_id or "",
        (extraction.drug_name or "").strip().lower(),
        extraction.phase,
        "met" if extraction.primary_endpoint_met else "missed",
        extraction.readout_date.isoformat(),
        source_document_id or "",
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


# ────────────────────────────────────────────────────────────────────
# Description (human-readable)
# ────────────────────────────────────────────────────────────────────


def _build_description(extraction: TrialReadoutExtraction) -> str:
    verb = "met" if extraction.primary_endpoint_met else "did not meet"
    parts = [
        f"{extraction.phase} {extraction.trial_identifier}",
        f"{verb} primary endpoint",
    ]
    if extraction.indication:
        parts.append(f"in {extraction.indication}")
    summary = " — ".join(parts) + ". " + extraction.headline_summary
    return summary[:1000]


# ────────────────────────────────────────────────────────────────────
# Public API
# ────────────────────────────────────────────────────────────────────


def build_event_row(
    *,
    extraction: TrialReadoutExtraction,
    company_id: str,
    company_name: str,
    trial_id: str,
    source_document_id: str,
    disclosed_date: date,
) -> dict[str, Any]:
    """Build a market_events row dict for INSERT.

    Caller resolves company_id (sponsor) and trial_id (from the
    extraction's trial_identifier via entity_aliases / nct_id lookup).
    """
    payload = {
        "trial_identifier": extraction.trial_identifier,
        "drug_name": extraction.drug_name,
        "sponsor_name": extraction.sponsor_name,
        "indication": extraction.indication,
        "phase": extraction.phase,
        "primary_endpoint_met": extraction.primary_endpoint_met,
        "sample_size": extraction.sample_size,
        "efficacy_outcomes": [
            eo.model_dump() for eo in extraction.efficacy_outcomes
        ],
        "safety_summary": extraction.safety_summary,
        "headline_summary": extraction.headline_summary,
        "company_id": company_id,
        "company_name": company_name,
    }

    return {
        "event_type": "trial_readout",
        "description": _build_description(extraction),
        "primary_entity_type": "trial",
        "primary_entity_id": trial_id,
        "primary_entity_name": extraction.trial_identifier,
        "event_date": extraction.readout_date,
        "disclosed_date": disclosed_date,
        "source_tier": "tier_2",  # Company press release
        "trust_score": _trust_score(extraction),
        "status": "new",
        "event_hash": _compute_event_hash(
            trial_id=trial_id,
            extraction=extraction,
            source_document_id=source_document_id,
        ),
        "source_feed": "press_release_readout",
        "impact_hint": _impact_hint(extraction),
        "payload": payload,
        "source_document_id": source_document_id,
    }
