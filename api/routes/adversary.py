"""BE-10 — GET /adversaries/{id}/posterior."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional

from api.deps import get_db
from db import Database
from services import adversary_twin as svc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/adversaries", tags=["adversary"])


@router.get("")
def list_adversaries(
    kind: Optional[str] = Query(None, description="competitor|regulator|payer|kol"),
    db: Database = Depends(get_db),
):
    """Public list of all adversary twins (PB-502 right rail seed)."""
    try:
        twins = svc.list_twins(db, kind=kind)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"twins": [t.to_dict() for t in twins]}


@router.get("/{twin_id}/posterior")
def get_posterior(twin_id: str, db: Database = Depends(get_db)):
    """BE-10 acceptance shape::

        {
          "posterior": {"aggressive": 0.61, "defensive": 0.24, "cash_constrained": 0.15},
          "last_updated_at": "...",
          "last_5_evidence_updates": [...]
        }
    """
    twin = svc.get(db, twin_id)
    if twin is None:
        raise HTTPException(404, f"adversary not found: {twin_id}")
    payload = twin.to_dict()
    return {
        "twin_id":                 payload["twin_id"],
        "name":                    payload["name"],
        "kind":                    payload["kind"],
        "posterior":               payload["posterior"],
        "last_updated_at":         payload["last_updated_at"],
        "last_5_evidence_updates": payload["last_5_evidence_updates"],
    }
