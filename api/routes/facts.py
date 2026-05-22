"""PB-1307 — facts ledger API.

GET  /facts   — facts about a subject valid AS-OF a date (default now);
               the temporal query the dossier + war-game read. Anonymous.
POST /facts   — assert a fact (uploader+). Extractors/agents write here.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.deps import get_db, require_role
from db import Database
from services.facts_ledger import assert_fact, facts_as_of, InvalidFact

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/facts", tags=["facts"])


class AssertFactBody(BaseModel):
    kind: str
    predicate: str = Field(min_length=1, max_length=200)
    subject_entity_type: str
    subject_entity_id: str
    object_value: dict
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    source_doc_id: Optional[str] = None
    confidence: float = 1.0


def _serialize(f: dict) -> dict:
    def iso(v: Any):
        return v.isoformat() if hasattr(v, "isoformat") else v
    return {
        "id": str(f.get("id")),
        "kind": f.get("kind"),
        "predicate": f.get("predicate"),
        "subject_entity_type": f.get("subject_entity_type"),
        "subject_entity_id": f.get("subject_entity_id"),
        "object_value": f.get("object_value"),
        "valid_from": iso(f.get("valid_from")),
        "valid_to": iso(f.get("valid_to")),
        "asserted_at": iso(f.get("asserted_at")),
        "source_doc_id": str(f["source_doc_id"]) if f.get("source_doc_id") else None,
        "confidence": f.get("confidence"),
        "created_by": f.get("created_by"),
    }


@router.get("")
def get_facts(
    subject_entity_type: str = Query(...),
    subject_entity_id: str = Query(...),
    as_of: Optional[datetime] = Query(None, description="ISO datetime; default now. Future dates surface anticipatory facts."),
    predicate: Optional[str] = Query(None),
    db: Database = Depends(get_db),
) -> dict:
    """Facts about a subject valid as-of a date. The war-game passes a future
    `as_of` to anchor on anticipatory facts (e.g. a 2027 price change)."""
    facts = facts_as_of(db, subject_entity_type, subject_entity_id, as_of=as_of, predicate=predicate)
    return {
        "subject": {"type": subject_entity_type, "id": subject_entity_id},
        "as_of": as_of.isoformat() if as_of else None,
        "facts": [_serialize(f) for f in facts],
        "count": len(facts),
    }


@router.post("", status_code=201)
def post_fact(
    body: AssertFactBody,
    user: dict = Depends(require_role("uploader")),
    db: Database = Depends(get_db),
) -> dict:
    try:
        fid = assert_fact(
            db,
            kind=body.kind,
            predicate=body.predicate,
            subject_entity_type=body.subject_entity_type,
            subject_entity_id=body.subject_entity_id,
            object_value=body.object_value,
            valid_from=body.valid_from,
            valid_to=body.valid_to,
            source_doc_id=body.source_doc_id,
            confidence=body.confidence,
            created_by=str(user.get("id", "system")),
        )
    except InvalidFact as e:
        raise HTTPException(400, str(e))
    return {"id": fid}
