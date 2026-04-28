"""Build market_events row dicts for Item 2.02 extractions.

SPEC-016 §7 swimlane A2.3. Two builders + one classifier helper:

  build_financial_disclosure_row(...)      → financial_disclosure event
  build_guidance_change_row(...)           → guidance_change event
  classify_guidance_direction(...)         → raise|lower|reaffirm|narrow|initiate

The classifier is exposed because the diff service reads guidance
history from `guidance` table (created in B-sprint) and re-classifies
when an issuance arrives without prior_range_* set on it.
"""

from __future__ import annotations

import hashlib
from datetime import date
from typing import Any, Optional

from services.extraction.financial_disclosure import (
    FinancialDisclosureExtraction,
    GuidanceIssuance,
)


# ────────────────────────────────────────────────────────────────────
# Direction classifier
# ────────────────────────────────────────────────────────────────────


def classify_guidance_direction(
    *,
    new_low: Optional[float],
    new_high: Optional[float],
    prior_low: Optional[float],
    prior_high: Optional[float],
    epsilon_pct: float = 1.0,
) -> str:
    """Return raise | lower | reaffirm | narrow | initiate | withdraw.

    epsilon_pct controls the "reaffirm" threshold — changes within ±N%
    are treated as the same range. Default 1% absorbs rounding noise.
    """
    # Withdraw: new range absent
    if new_low is None and new_high is None:
        return "withdraw"

    # Initiate: no prior
    if prior_low is None or prior_high is None:
        return "initiate"

    new_mid = (new_low + new_high) / 2 if new_low is not None and new_high is not None else None
    prior_mid = (prior_low + prior_high) / 2

    if new_mid is None:
        return "initiate"

    # Compute % delta on midpoint
    if prior_mid == 0:
        return "raise" if new_mid > 0 else "lower"

    delta_pct = (new_mid - prior_mid) / abs(prior_mid) * 100.0

    if delta_pct > epsilon_pct:
        return "raise"
    if delta_pct < -epsilon_pct:
        return "lower"

    # Within reaffirm band on midpoint — distinguish narrow vs reaffirm
    new_width = (new_high - new_low) if (new_high is not None and new_low is not None) else None
    prior_width = prior_high - prior_low

    if new_width is not None and prior_width > 0:
        width_ratio = new_width / prior_width
        if width_ratio < 0.85:  # range tightened by >15%
            return "narrow"

    return "reaffirm"


# ────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────


def _impact_hint_disclosure(extraction: FinancialDisclosureExtraction) -> str:
    """Disclosures alone are medium-impact unless they signal a surprise.
    Without consensus comparison (Phase 3 with AlphaSense / Bloomberg),
    we ship medium as the safe default. The B3 scoring service refines."""
    return "medium"


def _impact_hint_guidance(issuance: GuidanceIssuance) -> str:
    """Raise + magnitude → high; lower → high (negative surprise);
    reaffirm/narrow → medium; initiate → medium; withdraw → high."""
    if issuance.direction in ("raise", "lower", "withdraw"):
        # Magnitude check on raise — if delta is small (<2%) treat as medium
        if (
            issuance.direction == "raise"
            and issuance.range_low is not None
            and issuance.prior_range_low is not None
        ):
            try:
                delta_pct = (
                    (issuance.range_low - issuance.prior_range_low)
                    / abs(issuance.prior_range_low)
                    * 100.0
                )
                if abs(delta_pct) < 2.0:
                    return "medium"
            except ZeroDivisionError:
                pass
        return "high"
    if issuance.direction in ("reaffirm", "narrow"):
        return "medium"
    return "medium"


# ────────────────────────────────────────────────────────────────────
# financial_disclosure event row
# ────────────────────────────────────────────────────────────────────


def _hash_disclosure(
    *, company_id: str, e: FinancialDisclosureExtraction, src_id: str,
) -> str:
    parts = [
        "financial_disclosure",
        company_id or "",
        e.fiscal_period_end.isoformat(),
        e.fiscal_period_label,
        # Fingerprint of metrics — sorted name|basis to be order-independent
        ",".join(sorted(f"{m.name}|{m.basis}" for m in e.metrics)),
        src_id or "",
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def build_financial_disclosure_row(
    *,
    extraction: FinancialDisclosureExtraction,
    company_id: str,
    company_name: str,
    source_document_id: str,
    disclosed_date: date,
) -> dict[str, Any]:
    """Build a market_events row for the financial_disclosure event."""
    metric_summary = ", ".join(
        f"{m.name} ({m.basis})" for m in extraction.metrics[:6]
    ) or "metrics"
    description = (
        f"{company_name}: {extraction.fiscal_period_label} financial "
        f"disclosure — {metric_summary}"
    )

    return {
        "event_type": "financial_disclosure",
        "description": description,
        "primary_entity_type": "company",
        "primary_entity_id": company_id,
        "primary_entity_name": company_name,
        "event_date": extraction.fiscal_period_end,
        "disclosed_date": disclosed_date,
        "source_tier": "tier_1",
        "trust_score": 0.95,
        "status": "new",
        "event_hash": _hash_disclosure(
            company_id=company_id, e=extraction, src_id=source_document_id,
        ),
        "source_feed": "sec_8k_item_2_02",
        "impact_hint": _impact_hint_disclosure(extraction),
        "payload": {
            "fiscal_period_end": extraction.fiscal_period_end.isoformat(),
            "fiscal_period_label": extraction.fiscal_period_label,
            "metrics": [m.model_dump() for m in extraction.metrics],
        },
        "source_document_id": source_document_id,
    }


# ────────────────────────────────────────────────────────────────────
# guidance_change event row
# ────────────────────────────────────────────────────────────────────


def _hash_guidance(
    *, company_id: str, g: GuidanceIssuance, src_id: str,
) -> str:
    parts = [
        "guidance_change",
        company_id or "",
        g.metric.value,
        g.period_label,
        g.basis,
        g.issued_at.isoformat(),
        f"{g.range_low or 0}",
        f"{g.range_high or 0}",
        src_id or "",
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _format_guidance_amount(metric: str, value: float) -> str:
    if metric == "eps":
        return f"${value:.2f}"
    if abs(value) >= 1_000_000_000:
        return f"${value / 1_000_000_000:.1f}B"
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:.0f}M"
    return f"${value:,.0f}"


def _describe_guidance(g: GuidanceIssuance) -> str:
    if g.direction == "withdraw":
        return f"{g.metric.value} guidance for {g.period_label} ({g.basis}) withdrawn"

    if g.range_low is not None and g.range_high is not None:
        new_str = (
            f"{_format_guidance_amount(g.metric.value, g.range_low)}"
            f"–{_format_guidance_amount(g.metric.value, g.range_high)}"
        )
    else:
        new_str = "(range undisclosed)"

    base = (
        f"{g.metric.value} {g.direction} for {g.period_label} ({g.basis}): "
        f"{new_str}"
    )

    if (
        g.prior_range_low is not None
        and g.prior_range_high is not None
        and g.direction in ("raise", "lower", "narrow")
    ):
        prior_str = (
            f"{_format_guidance_amount(g.metric.value, g.prior_range_low)}"
            f"–{_format_guidance_amount(g.metric.value, g.prior_range_high)}"
        )
        base += f" (prior {prior_str})"

    return base


def _delta_pct(new_val: Optional[float], prior_val: Optional[float]) -> Optional[float]:
    if new_val is None or prior_val is None or prior_val == 0:
        return None
    return (new_val - prior_val) / abs(prior_val) * 100.0


def build_guidance_change_row(
    *,
    issuance: GuidanceIssuance,
    company_id: str,
    company_name: str,
    source_document_id: str,
    disclosed_date: date,
) -> dict[str, Any]:
    """Build a market_events row for a guidance_change event."""
    delta_low = _delta_pct(issuance.range_low, issuance.prior_range_low)
    delta_high = _delta_pct(issuance.range_high, issuance.prior_range_high)

    # Signal direction hint — the intelligence layer reads this
    # and sets Signal.direction (positive/negative/neutral/mixed).
    if issuance.direction == "raise":
        signal_direction = "positive"
    elif issuance.direction in ("lower", "withdraw"):
        signal_direction = "negative"
    elif issuance.direction == "narrow":
        signal_direction = "neutral"
    elif issuance.direction == "reaffirm":
        signal_direction = "neutral"
    else:  # initiate
        signal_direction = "neutral"

    return {
        "event_type": "guidance_change",
        "description": f"{company_name}: {_describe_guidance(issuance)}",
        "primary_entity_type": "company",
        "primary_entity_id": company_id,
        "primary_entity_name": company_name,
        "event_date": issuance.issued_at,
        "disclosed_date": disclosed_date,
        "source_tier": "tier_1",
        "trust_score": 0.95,
        "status": "new",
        "event_hash": _hash_guidance(
            company_id=company_id, g=issuance, src_id=source_document_id,
        ),
        "source_feed": "sec_8k_item_2_02",
        "impact_hint": _impact_hint_guidance(issuance),
        "payload": {
            "metric": issuance.metric.value,
            "period_label": issuance.period_label,
            "basis": issuance.basis,
            "direction": issuance.direction,
            "range_low": issuance.range_low,
            "range_high": issuance.range_high,
            "prior_range_low": issuance.prior_range_low,
            "prior_range_high": issuance.prior_range_high,
            "delta_pct_low": delta_low,
            "delta_pct_high": delta_high,
            "signal_direction_hint": signal_direction,
            "notes": issuance.notes,
        },
        "source_document_id": source_document_id,
    }
