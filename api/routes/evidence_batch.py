"""Loop #19 — Batch evidence resolver.

Frontend signal cards in /ci hold `evidence_document_ids: UUID[]`. This
endpoint resolves those ids to the lightweight metadata the UI needs
(source name + tier + date + snippet + url) in a single round-trip.

Anonymous read — signals themselves are listable anonymously, so the
evidence backing them must be too. The endpoint clamps the input list
to 50 ids and returns missing_ids so the UI can render unresolved
chips for anything the join didn't find.
"""

from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from api.deps import get_db
from db import Database

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/evidence", tags=["evidence"])


class EvidenceBatchRequest(BaseModel):
    ids: List[str] = Field(..., min_length=1, max_length=50)


def _tier_from_source(source_id: str | None) -> str:
    """Map a source_id (clinicaltrials.gov, pubmed, etc.) to a coarse tier.

    Mirrors the curation policy in domain/pharma/pack.py — clinical
    registries and peer-reviewed pubs are tier_1, regulatory filings
    and large reference DBs are tier_2, news/press is tier_3.
    """
    if not source_id:
        return "unknown"
    s = source_id.strip().lower()
    if s in {"clinicaltrials.gov", "pubmed", "pmc"}:
        return "tier_1"
    if s in {"sec_edgar", "fda_orange_book", "fda_shortages", "openfda", "pubchem", "chembl"}:
        return "tier_2"
    if s in {"pharma_news", "press_release"}:
        return "tier_3"
    return "unknown"


def _row_to_doc(row: dict) -> dict:
    text = row.get("extracted_text") or ""
    snippet = text[:280] if text else None
    retrieved = row.get("retrieved_at")
    return {
        "evidence_id": str(row["evidence_id"]),
        "source_id": row.get("source_id"),
        "source_url": row.get("source_url"),
        "source_tier": _tier_from_source(row.get("source_id")),
        "retrieved_at": retrieved.isoformat() if retrieved is not None and hasattr(retrieved, "isoformat") else retrieved,
        "snippet": snippet,
        "confidence": row.get("confidence"),
    }


@router.post("/by-ids")
def resolve_evidence_batch(
    body: EvidenceBatchRequest,
    db: Database = Depends(get_db),
) -> dict:
    """Resolve a batch of evidence_ids to display-ready metadata."""
    # Dedupe + cap. Pydantic validates length but a request that sends
    # duplicates should still be safe.
    unique_ids = list({i for i in body.ids if i})
    if not unique_ids:
        return {"documents": [], "missing_ids": []}

    sql = """
        SELECT evidence_id, source_id, source_url, retrieved_at,
               extracted_text, confidence
          FROM evidence_records
         WHERE evidence_id = ANY(%s::uuid[])
    """

    try:
        rows = db.fetch_all(sql, [unique_ids])
    except Exception:
        logger.exception("evidence batch resolve failed")
        rows = []

    documents = [_row_to_doc(r) for r in rows]
    found = {d["evidence_id"] for d in documents}
    missing = [i for i in unique_ids if i not in found]

    return {"documents": documents, "missing_ids": missing}
