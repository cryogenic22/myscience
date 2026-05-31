"""BE-17 — 4-dimension confidence assessment.

Replaces the three inconsistent UI primitives (ConfidenceBadge,
CalibrationChip, ImpactBadge) with a single composite + 4-axis
breakdown that the PB-604 ConfidencePill renders without further
backend calls.

Acceptance shape (per AGENT_BACKLOG#BE-17)::

    {
      "composite": 0.74,
      "by_dimension": {
        "evidence_quality":  0.82,   # avg of citation tier weights
        "source_diversity":  0.71,   # 1 - HHI of source distribution
        "recency":           0.65,   # mean exp-decay over published dates
        "calibration":       0.78,   # historical hit rate from sources reg
      }
    }

All values are in [0, 1]. Composite is the weighted mean (default
weights mirror the materiality scorer documented in
``services/materiality.py``).

The function is **pure** — it takes a list of evidence-shaped
dicts plus an optional calibration map and returns the assessment.
The chat handlers / synthesise layer call it after assembling the
evidence pack and splice the result into the response payload.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Iterable, Optional


# Tier weights — mirror DEFAULT_TIER_VALUES from services/materiality.py
# so the same authoritative-public bias applies in both surfaces.
_TIER_WEIGHTS: dict[str, float] = {
    "T1": 1.0,
    "T2": 0.7,
    "T3": 0.4,
    "T4": 0.6,
}

# Composite mixing weights (sum to 1.0).
_COMPOSITE_WEIGHTS: dict[str, float] = {
    "evidence_quality": 0.35,
    "source_diversity": 0.20,
    "recency":          0.20,
    "calibration":      0.25,
}

_DEFAULT_HALF_LIFE_DAYS = 90.0  # half-life for the recency factor


def _coerce_dt(value) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return None


def _evidence_quality(items: Iterable[dict]) -> float:
    weights: list[float] = []
    for it in items:
        tier = it.get("source_tier") if isinstance(it, dict) else None
        if not tier:
            # Treat unknown as T3 (safe scientific default per BE-1 registry).
            weights.append(_TIER_WEIGHTS["T3"])
        else:
            weights.append(_TIER_WEIGHTS.get(str(tier).upper(), _TIER_WEIGHTS["T3"]))
    if not weights:
        return 0.0
    return sum(weights) / len(weights)


def _source_diversity(items: Iterable[dict]) -> float:
    """1 - Herfindahl-Hirschman index of source share. Higher = more
    diverse. With one source: 0.0. With N evenly spread: 1 - 1/N → ~1."""
    counts: dict[str, int] = {}
    for it in items:
        sid = (it.get("source_id") or it.get("source") or "unknown") if isinstance(it, dict) else "unknown"
        counts[sid] = counts.get(sid, 0) + 1
    total = sum(counts.values())
    if total <= 1:
        return 0.0
    hhi = sum((c / total) ** 2 for c in counts.values())
    return max(0.0, min(1.0, 1.0 - hhi))


def _recency(items: Iterable[dict], half_life_days: float = _DEFAULT_HALF_LIFE_DAYS) -> float:
    now = datetime.now(timezone.utc)
    factors: list[float] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        ts = _coerce_dt(it.get("published_at") or it.get("retrieved_at"))
        if ts is None:
            factors.append(0.5)  # neutral default for undated evidence
            continue
        age_days = max(0.0, (now - ts).total_seconds() / 86400.0)
        factors.append(math.exp(-math.log(2) * age_days / half_life_days))
    if not factors:
        return 0.0
    return sum(factors) / len(factors)


def _calibration(items: Iterable[dict], calibration_map: Optional[dict]) -> float:
    """Mean historical hit-rate across the cited sources.

    ``calibration_map`` is an optional ``{source_id: hit_rate}`` lookup
    sourced from `sources.predictive_accuracy` (SPEC-027). Missing
    entries fall back to a neutral 0.7 — better than 0.5 because we
    only ingest curated sources, but not perfect.
    """
    if calibration_map is None:
        calibration_map = {}
    rates: list[float] = []
    seen_sources: set[str] = set()
    for it in items:
        if not isinstance(it, dict):
            continue
        sid = it.get("source_id") or it.get("source")
        if not sid or sid in seen_sources:
            continue
        seen_sources.add(sid)
        rates.append(float(calibration_map.get(sid, 0.7)))
    if not rates:
        return 0.0
    return sum(rates) / len(rates)


def compute_confidence_assessment(
    evidence: list[dict] | None,
    *,
    calibration_map: Optional[dict] = None,
    composite_weights: Optional[dict[str, float]] = None,
) -> dict:
    """Return the 4-dimension confidence assessment for the chat response.

    See module docstring for the response shape.
    """
    items = list(evidence or [])
    if not items:
        return {
            "composite": 0.0,
            "by_dimension": {
                "evidence_quality": 0.0,
                "source_diversity": 0.0,
                "recency":          0.0,
                "calibration":      0.0,
            },
        }

    by_dim = {
        "evidence_quality": _evidence_quality(items),
        "source_diversity": _source_diversity(items),
        "recency":          _recency(items),
        "calibration":      _calibration(items, calibration_map),
    }

    weights = composite_weights or _COMPOSITE_WEIGHTS
    total = sum(weights.values()) or 1.0
    composite = sum(by_dim[k] * weights[k] / total for k in by_dim)
    composite = max(0.0, min(1.0, composite))

    return {
        "composite": round(composite, 4),
        "by_dimension": {k: round(v, 4) for k, v in by_dim.items()},
    }
