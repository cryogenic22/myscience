"""Event-row builder for patent_grant events.

SPEC-016 §7 swimlane A5.1 (Cycle 10).

Source = USPTO PatentsView → tier_1 (USPTO is the canonical issuer).
trust_score = 0.95.

Impact-tier hint is a heuristic over claim count — broader patents
(more claims) tend to be more strategically valuable. The B3 scoring
service later re-evaluates with mechanism overlap, drug binding, etc.
"""

from __future__ import annotations

import hashlib
from datetime import date
from typing import Any

from services.extraction.patent import PatentRecord


def _impact_hint(patent: PatentRecord) -> str:
    n = patent.num_claims or 0
    if n >= 30:
        return "high"
    if n >= 10:
        return "medium"
    return "low"


def _compute_event_hash(
    *,
    patent: PatentRecord,
    company_id: str,
    source_document_id: str,
) -> str:
    parts = [
        "patent_grant",
        company_id or "",
        patent.patent_number,
        patent.grant_date.isoformat(),
        source_document_id or "",
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _build_description(patent: PatentRecord) -> str:
    return (
        f"Patent {patent.patent_number} granted to {patent.assignee_name}: "
        f"{patent.title[:200]}"
    )[:1000]


def build_event_row(
    *,
    patent: PatentRecord,
    company_id: str,
    company_name: str,
    source_document_id: str,
    disclosed_date: date,
) -> dict[str, Any]:
    payload = {
        "patent_number": patent.patent_number,
        "title": patent.title,
        "assignee_name": patent.assignee_name,
        "abstract": patent.abstract,
        "filing_date": patent.filing_date.isoformat() if patent.filing_date else None,
        "application_number": patent.application_number,
        "inventors": patent.inventors,
        "num_claims": patent.num_claims,
        "cpc_groups": patent.cpc_groups,
        "assignee_country": patent.assignee_country,
        "company_id": company_id,
        "company_name": company_name,
    }
    return {
        "event_type": "patent_grant",
        "description": _build_description(patent),
        "primary_entity_type": "company",
        "primary_entity_id": company_id,
        "primary_entity_name": company_name,
        "event_date": patent.grant_date,
        "disclosed_date": disclosed_date,
        "source_tier": "tier_1",
        "trust_score": 0.95,
        "status": "new",
        "event_hash": _compute_event_hash(
            patent=patent,
            company_id=company_id,
            source_document_id=source_document_id,
        ),
        "source_feed": "uspto_patentsview",
        "impact_hint": _impact_hint(patent),
        "payload": payload,
        "source_document_id": source_document_id,
    }
