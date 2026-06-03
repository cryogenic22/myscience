"""SPEC-020 — Signals API.

Read-only list/detail (anonymous) + reviewer mutation (enterprise).
The clustering/scoring service writes to the signals table; this API
never inserts.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from api.deps import get_db, require_role
from db import Database

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/signals", tags=["signals"])


# ────────────────────────────────────────────────────────────────────
# Constants
# ────────────────────────────────────────────────────────────────────

_DEFAULT_STATUSES = ("reviewed", "shipped")
_VALID_STATUSES = ("candidate", "reviewed", "shipped", "superseded", "retracted")
_REVIEWABLE_STATUSES = ("reviewed", "shipped", "retracted")
_VALID_IMPACTS = ("high", "medium", "low")
_VALID_CONFIDENCE = ("confirmed", "reported", "inferred", "disputed")


# ────────────────────────────────────────────────────────────────────
# Schemas
# ────────────────────────────────────────────────────────────────────

class ReviewBody(BaseModel):
    status: str


# ────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────

def _row_to_dict(row: dict) -> dict:
    """Normalise a signals row for JSON output (datetime → iso, defaults)."""
    def _iso(v):
        if v is None:
            return None
        if hasattr(v, "isoformat"):
            return v.isoformat()
        return str(v)

    return {
        "id": str(row.get("id")),
        "event_id": str(row["event_id"]) if row.get("event_id") else None,
        "kbq_tags": row.get("kbq_tags") or [],
        "headline": row.get("headline") or "",
        "summary": row.get("summary"),
        "direction": row.get("direction"),
        "confidence_tier": row.get("confidence_tier"),
        "trust_score": row.get("trust_score"),
        "impact_tier": row.get("impact_tier"),
        "impact_score": row.get("impact_score"),
        "rule_version_id": row.get("rule_version_id"),
        "primary_entity_type": row.get("primary_entity_type"),
        "primary_entity_id": row.get("primary_entity_id"),
        "primary_entity_name": row.get("primary_entity_name"),
        "related_entity_ids": row.get("related_entity_ids") or [],
        "evidence_document_ids": [
            str(d) for d in (row.get("evidence_document_ids") or [])
        ],
        "materiality_factors": row.get("materiality_factors"),
        "status": row.get("status"),
        "superseded_by": str(row["superseded_by"]) if row.get("superseded_by") else None,
        "supersedence_reason": row.get("supersedence_reason"),
        "created_at": _iso(row.get("created_at")),
        "reviewed_by": str(row["reviewed_by"]) if row.get("reviewed_by") else None,
        "reviewed_at": _iso(row.get("reviewed_at")),
        "shipped_at": _iso(row.get("shipped_at")),
    }


# ────────────────────────────────────────────────────────────────────
# GET /signals
# ────────────────────────────────────────────────────────────────────

@router.get("")
def list_signals(
    status: Optional[str] = Query(None, description="one status, or 'all' for every status (incl. candidate)"),
    impact: Optional[str] = Query(None, description="high|medium|low"),
    confidence: Optional[str] = Query(None, description="confirmed|reported|inferred|disputed"),
    kbq: Optional[str] = Query(
        None,
        description="comma-separated kbq tags — signal matches if it has ANY of them (e.g. `financial,clinical`)",
    ),
    entity_type: Optional[str] = Query(None),
    entity_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Database = Depends(get_db),
):
    """List signals. Default view: status in (reviewed, shipped)."""
    where_clauses = []
    params: list = []

    if status == "all":
        pass  # no status filter — reveal candidates (incl. auto-minted fact-signals)
    elif status:
        if status not in _VALID_STATUSES:
            raise HTTPException(400, f"invalid status: {status}")
        where_clauses.append("status = %s")
        params.append(status)
    else:
        where_clauses.append("status = ANY(%s)")
        params.append(list(_DEFAULT_STATUSES))

    if impact:
        if impact not in _VALID_IMPACTS:
            raise HTTPException(400, f"invalid impact: {impact}")
        where_clauses.append("impact_tier = %s")
        params.append(impact)

    if confidence:
        if confidence not in _VALID_CONFIDENCE:
            raise HTTPException(400, f"invalid confidence: {confidence}")
        where_clauses.append("confidence_tier = %s")
        params.append(confidence)

    if kbq:
        # PB-104 — CSV of any-of tags. Dedup, strip whitespace, drop empties.
        # If nothing survives the strip (e.g. `kbq=, ,`) treat it as no filter.
        tags = list({t.strip() for t in kbq.split(",") if t.strip()})
        if tags:
            where_clauses.append("kbq_tags && %s")
            params.append(tags)

    if entity_type:
        where_clauses.append("primary_entity_type = %s")
        params.append(entity_type)

    if entity_id:
        where_clauses.append("primary_entity_id = %s")
        params.append(entity_id)

    where_sql = " AND ".join(where_clauses) if where_clauses else "TRUE"
    sql = f"""
        SELECT id, event_id, kbq_tags, headline, summary, direction,
               confidence_tier, trust_score, impact_tier, impact_score,
               rule_version_id, primary_entity_type, primary_entity_id,
               primary_entity_name, related_entity_ids,
               evidence_document_ids, materiality_factors,
               status, superseded_by,
               supersedence_reason, created_at, reviewed_by, reviewed_at,
               shipped_at
        FROM signals
        WHERE {where_sql}
        ORDER BY
          CASE impact_tier
            WHEN 'high' THEN 3
            WHEN 'medium' THEN 2
            WHEN 'low' THEN 1
            ELSE 0
          END DESC,
          impact_score DESC,
          created_at DESC
        LIMIT %s OFFSET %s
    """
    params.extend([limit, offset])

    try:
        rows = db.fetch_all(sql, params)
    except Exception:
        logger.exception("signals list query failed")
        rows = []

    items = [_row_to_dict(r) for r in rows]
    return {
        "signals": items,
        "count": len(items),
        "limit": limit,
        "offset": offset,
    }


# ────────────────────────────────────────────────────────────────────
# GET /signals/{id}
# ────────────────────────────────────────────────────────────────────

@router.get("/{signal_id}")
def get_signal(signal_id: str, db: Database = Depends(get_db)):
    try:
        row = db.fetch_one(
            """SELECT id, event_id, kbq_tags, headline, summary, direction,
                      confidence_tier, trust_score, impact_tier, impact_score,
                      rule_version_id, primary_entity_type, primary_entity_id,
                      primary_entity_name, related_entity_ids,
                      evidence_document_ids, materiality_factors,
                      status, superseded_by,
                      supersedence_reason, created_at, reviewed_by, reviewed_at,
                      shipped_at
               FROM signals WHERE id::text = %s""",
            [signal_id],
        )
    except Exception:
        logger.exception("signals detail query failed")
        row = None

    if not row:
        raise HTTPException(404, f"signal not found: {signal_id}")
    result = _row_to_dict(row)
    result["linked_facts"] = _linked_facts(db, signal_id)
    return result


def _linked_facts(db: Database, signal_id: str) -> list[dict]:
    """PB-SL05 — the facts this signal feeds (via signal_facts), with their
    class + source for forward provenance (signal → fact → evidence → source)."""
    try:
        rows = db.fetch_all(
            """SELECT sf.role, f.id::text AS fact_id, f.predicate, f.fact_class,
                      f.object_value->>'description' AS claim,
                      f.confidence,
                      e.source_id, e.source_url
                 FROM signal_facts sf
                 JOIN facts f ON f.id = sf.fact_id
                 LEFT JOIN evidence_records e ON e.evidence_id = f.source_doc_id
                WHERE sf.signal_id::text = %s
                ORDER BY f.confidence DESC NULLS LAST""",
            [signal_id],
        )
        return [dict(r) for r in rows]
    except Exception:
        logger.exception("linked_facts query failed for %s", signal_id)
        return []


# ────────────────────────────────────────────────────────────────────
# POST /signals/{id}/review — enterprise only
# ────────────────────────────────────────────────────────────────────

@router.post("/{signal_id}/review")
def review_signal(
    signal_id: str,
    body: ReviewBody,
    user: dict = Depends(require_role("enterprise")),
    db: Database = Depends(get_db),
):
    """Set signal status (reviewed | shipped | retracted) and stamp the actor."""
    if body.status not in _REVIEWABLE_STATUSES:
        raise HTTPException(
            400,
            f"invalid review status: {body.status} "
            f"(allowed: {', '.join(_REVIEWABLE_STATUSES)})",
        )

    try:
        existing = db.fetch_one(
            "SELECT id FROM signals WHERE id::text = %s",
            [signal_id],
        )
    except Exception:
        existing = None
    if not existing:
        raise HTTPException(404, f"signal not found: {signal_id}")

    try:
        db.execute(
            """UPDATE signals
               SET status = %s,
                   reviewed_by = %s::uuid,
                   reviewed_at = NOW(),
                   shipped_at = CASE WHEN %s = 'shipped'
                                     THEN NOW() ELSE shipped_at END
               WHERE id::text = %s""",
            [body.status, user.get("id"), body.status, signal_id],
        )
    except Exception as exc:
        logger.exception("signals review update failed")
        raise HTTPException(500, f"review update failed: {exc}") from exc

    return {
        "id": signal_id,
        "status": body.status,
        "reviewed_by": user.get("id"),
    }
