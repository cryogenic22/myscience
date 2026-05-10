"""BE-18 — per-message source aggregation.

PB-605's "source strip" renders one chip per source (tier dot +
source name + cite count). This module provides the helper chat
handlers call to assemble the underlying ``source_aggregation``
list in the chat response.

Output shape::

    [
      {"source_id": "fda",       "source_name": "FDA",       "tier": "T1", "cite_count": 4},
      {"source_id": "pubmed",    "source_name": "PubMed",    "tier": "T3", "cite_count": 2},
      {"source_id": "sec_edgar", "source_name": "SEC EDGAR", "tier": "T2", "cite_count": 1},
    ]

Items are sorted: tier ascending (T1 first → highest authority
first), cite_count descending, source_name ascending. Stable so the
frontend can render ahead of streaming completion.
"""

from __future__ import annotations

from typing import Iterable, Optional

from services.evidence_ledger import lookup_source_metadata


# Tier sort order: T1 most authoritative → renders first.
_TIER_ORDER: dict[str, int] = {"T1": 0, "T2": 1, "T3": 2, "T4": 3}


def _resolve_source(record: dict) -> tuple[str, Optional[str], Optional[str]]:
    """Return (source_id, source_name, source_tier) for an evidence record.

    Falls back to the BE-1 source registry for legacy rows that don't
    have explicit source_name / source_tier fields.
    """
    source_id = record.get("source_id") or record.get("source") or "unknown"
    name = record.get("source_name")
    tier = record.get("source_tier")
    if name and tier:
        return source_id, name, tier
    reg_name, reg_tier = lookup_source_metadata(source_id)
    return source_id, name or reg_name, tier or reg_tier


def aggregate_by_source(evidence: Iterable[dict] | None) -> list[dict]:
    """Group evidence records by source and emit a sorted strip payload.

    Repeated citations from the same source increment ``cite_count``.
    Evidence whose source_id can't be resolved still surfaces (under
    "unknown") so the strip never silently drops anything.
    """
    items = list(evidence or [])
    if not items:
        return []

    buckets: dict[str, dict] = {}
    for it in items:
        if not isinstance(it, dict):
            continue
        sid, name, tier = _resolve_source(it)
        bucket = buckets.get(sid)
        if bucket is None:
            buckets[sid] = {
                "source_id":   sid,
                "source_name": name or sid,
                "tier":        tier,
                "cite_count":  1,
            }
        else:
            bucket["cite_count"] += 1
            if not bucket.get("tier") and tier:
                bucket["tier"] = tier
            if not bucket.get("source_name") and name:
                bucket["source_name"] = name

    out = list(buckets.values())
    out.sort(key=lambda r: (
        _TIER_ORDER.get((r.get("tier") or "T4").upper(), 99),
        -int(r["cite_count"]),
        str(r["source_name"] or "").lower(),
    ))
    return out
