"""Build market_events + deals row dicts for an Item 1.01 extraction.

SPEC-016 §7 swimlane A2.2. Pure functions — no DB I/O. Caller writes
the rows. Two builders because the deal payload lives in the deals
table (A1.6 / migration 042) AND is referenced via market_events
(deal_announced event). Both rows are needed.

Idempotency: event_hash = SHA-256 over canonical inputs.
"""

from __future__ import annotations

import hashlib
from datetime import date
from typing import Any, Optional

from services.extraction.deal_announced import DealExtraction


# ────────────────────────────────────────────────────────────────────
# Impact hint — heuristic; B3 scoring service refines
# ────────────────────────────────────────────────────────────────────


def _impact_hint(extraction: DealExtraction) -> str:
    """Map deal magnitude to high|medium|low.

    Heuristic:
      - total_potential >= $1B → high
      - "acquisition" with target a public co (we can't tell here) → high
      - upfront >= $100M → high
      - upfront >= $25M  → medium
      - else → low (or medium if undisclosed — undisclosed isn't small)
    """
    if extraction.total_potential_usd and extraction.total_potential_usd >= 1_000_000_000:
        return "high"
    if "acquisition" in extraction.deal_types:
        return "high"  # all M&A is high until proven otherwise
    if extraction.upfront_value_usd:
        if extraction.upfront_value_usd >= 100_000_000:
            return "high"
        if extraction.upfront_value_usd >= 25_000_000:
            return "medium"
    if not extraction.upfront_disclosed:
        return "medium"  # undisclosed != small
    return "low"


# ────────────────────────────────────────────────────────────────────
# Description builder
# ────────────────────────────────────────────────────────────────────


def _describe_terms(d: DealExtraction) -> str:
    parts: list[str] = []
    if d.upfront_value_usd is not None:
        parts.append(f"${d.upfront_value_usd / 1_000_000:.0f}M upfront")
    elif not d.upfront_disclosed:
        parts.append("undisclosed upfront")
    if d.milestones_total_usd is not None:
        parts.append(f"up to ${d.milestones_total_usd / 1_000_000:.0f}M milestones")
    if d.total_potential_usd is not None:
        parts.append(f"${d.total_potential_usd / 1_000_000:.0f}M total potential")
    if d.royalty_range_low_pct is not None and d.royalty_range_high_pct is not None:
        parts.append(
            f"royalties {d.royalty_range_low_pct:.0f}–{d.royalty_range_high_pct:.0f}%"
        )
    return ", ".join(parts) if parts else "terms undisclosed"


def _build_description(
    d: DealExtraction,
    primary_company_name: str,
    counterparty_company_name: Optional[str],
) -> str:
    primary_types = ", ".join(d.deal_types)
    other = counterparty_company_name or "(counterparty)"
    base = f"{primary_company_name}: {primary_types} with {other}"
    if d.subject_indication:
        base += f" — {d.subject_indication}"
    if d.geography and d.geography not in ("WW",):
        base += f" ({d.geography})"
    base += f". Terms: {_describe_terms(d)}"
    return base


# ────────────────────────────────────────────────────────────────────
# event_hash
# ────────────────────────────────────────────────────────────────────


def _compute_event_hash(
    *,
    primary_company_id: str,
    extraction: DealExtraction,
    source_document_id: str,
) -> str:
    parts = [
        "deal_announced",
        primary_company_id or "",
        ",".join(sorted(extraction.deal_types)),
        extraction.announced_date.isoformat(),
        (extraction.acquirer_name or "").strip().lower(),
        (extraction.target_name or "").strip().lower(),
        (extraction.licensor_name or "").strip().lower(),
        (extraction.licensee_name or "").strip().lower(),
        f"{extraction.upfront_value_usd or 0}",
        f"{extraction.total_potential_usd or 0}",
        source_document_id or "",
    ]
    payload = "|".join(parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ────────────────────────────────────────────────────────────────────
# Public API — two builders
# ────────────────────────────────────────────────────────────────────


def build_event_row(
    *,
    extraction: DealExtraction,
    primary_company_id: str,
    primary_company_name: str,
    counterparty_company_id: Optional[str],
    counterparty_company_name: Optional[str],
    source_document_id: str,
    disclosed_date: date,
) -> dict[str, Any]:
    """Build a market_events row dict for the deal_announced event.

    primary_company is the filing company (the one issuing the 8-K).
    counterparty is the OTHER party. Both can be None for the
    counterparty when entity resolution couldn't match.
    """
    return {
        "event_type": "deal_announced",
        "description": _build_description(
            extraction, primary_company_name, counterparty_company_name,
        ),
        "primary_entity_type": "company",
        "primary_entity_id": primary_company_id,
        "primary_entity_name": primary_company_name,
        "event_date": extraction.announced_date,
        "disclosed_date": disclosed_date,
        "source_tier": "tier_1",
        "trust_score": 0.95,
        "status": "new",
        "event_hash": _compute_event_hash(
            primary_company_id=primary_company_id,
            extraction=extraction,
            source_document_id=source_document_id,
        ),
        "source_feed": "sec_8k_item_1_01",
        "impact_hint": _impact_hint(extraction),
        "payload": {
            "deal_types": extraction.deal_types,
            "acquirer_name": extraction.acquirer_name,
            "target_name": extraction.target_name,
            "licensor_name": extraction.licensor_name,
            "licensee_name": extraction.licensee_name,
            "counterparty_company_id": counterparty_company_id,
            "counterparty_company_name": counterparty_company_name,
            "subject_drug_names": extraction.subject_drug_names,
            "subject_indication": extraction.subject_indication,
            "geography": extraction.geography,
            "upfront_disclosed": extraction.upfront_disclosed,
            "upfront_value_usd": extraction.upfront_value_usd,
            "milestones_total_usd": extraction.milestones_total_usd,
            "total_potential_usd": extraction.total_potential_usd,
            "royalty_range_low_pct": extraction.royalty_range_low_pct,
            "royalty_range_high_pct": extraction.royalty_range_high_pct,
            "equity_component": extraction.equity_component,
            "notes": extraction.notes,
        },
        "source_document_id": source_document_id,
    }


def build_deals_row(
    *,
    extraction: DealExtraction,
    acquirer_id: Optional[str],
    target_id: Optional[str],
    licensor_id: Optional[str],
    licensee_id: Optional[str],
    source_document_id: str,
    press_release_url: Optional[str] = None,
    filing_url: Optional[str] = None,
    subject_drug_ids: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Build a deals-table row dict for INSERT INTO deals.

    Caller resolves entity ids upstream and passes them in. None means
    'counterparty unresolved'; the row still inserts (deals.acquirer_id
    et al. are nullable).
    """
    royalty_terms = None
    if extraction.royalty_range_low_pct is not None or extraction.royalty_range_high_pct is not None:
        royalty_terms = {
            "range_low_pct": extraction.royalty_range_low_pct,
            "range_high_pct": extraction.royalty_range_high_pct,
        }

    subject_indications: list[dict] = []
    if extraction.subject_indication:
        subject_indications.append({"name": extraction.subject_indication})

    return {
        "deal_types": list(extraction.deal_types),
        "acquirer_id": acquirer_id,
        "target_id": target_id,
        "licensor_id": licensor_id,
        "licensee_id": licensee_id,
        "subject_drug_ids": subject_drug_ids or [],
        "subject_indications": subject_indications,
        "geography": extraction.geography,
        "currency": extraction.currency,
        "upfront_value_usd": extraction.upfront_value_usd,
        "upfront_disclosed": extraction.upfront_disclosed,
        "milestones_total_usd": extraction.milestones_total_usd,
        "milestones_breakdown": None,  # populated when disclosed; LLM extracts
        "royalty_terms": royalty_terms,
        "total_potential_usd": extraction.total_potential_usd,
        "equity_component": extraction.equity_component,
        "announced_date": extraction.announced_date,
        "closing_date": extraction.closing_date,
        "status": "announced",
        "source_document_id": source_document_id,
        "press_release_url": press_release_url,
        "filing_url": filing_url,
        "notes": extraction.notes,
    }
