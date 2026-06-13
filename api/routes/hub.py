"""DataHub API routes (D-API-1) — connector taxonomy + onboarding lifecycle.

Thin REST surface over ``services/connector_taxonomy.py`` (DataHub L2, #245),
which already owns the taxonomy + the ``draft→test→staged→prod`` lifecycle state
machine. These endpoints exist so the Frontend Connect wizard (F5) can read the
connector types and drive a source through onboarding without re-implementing the
rules client-side. No new business logic lives here — it maps service calls and
domain errors onto HTTP.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from api.deps import get_db
from db import Database
from services import connector_taxonomy as ct

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/hub", tags=["datahub"])


# ── Connector taxonomy ───────────────────────────────────────────────

@router.get("/connector-types")
def list_connector_types(db: Database = Depends(get_db)) -> dict:
    """Every connector type the platform knows how to onboard (F5 wizard step 1)."""
    types = ct.list_connector_types(db)
    return {"connector_types": [t.to_dict() for t in types]}


# ── Onboarding lifecycle ─────────────────────────────────────────────

class OnboardingActionBody(BaseModel):
    """Body for POST /hub/onboarding/{source_id}.

    action="start"   → begin onboarding in `draft` (idempotent); accepts the
                       initial metadata + an optional connector_type.
    action="advance" → move the lifecycle to `to_status`, enforcing the state
                       machine (`to_status` required).
    """
    action: str
    to_status: Optional[str] = None
    owner: Optional[str] = None
    contact: Optional[str] = None
    connector_type: Optional[str] = None
    go_live_date: Optional[str] = None  # ISO date (YYYY-MM-DD)
    escalation: Optional[str] = None


@router.get("/onboarding")
def list_onboarding(
    status: Optional[str] = Query(None, description="Filter by lifecycle status"),
    db: Database = Depends(get_db),
) -> dict:
    """All onboarding records (optionally filtered by lifecycle status)."""
    try:
        records = ct.list_onboarding(db, status=status)
    except ValueError as e:  # unknown status filter
        raise HTTPException(status_code=400, detail=str(e))
    return {"onboarding": [r.to_dict() for r in records]}


@router.get("/onboarding/{source_id}")
def get_onboarding(source_id: str, db: Database = Depends(get_db)) -> dict:
    """The onboarding record for one source, or 404 if it was never started."""
    record = ct.get_onboarding(db, source_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"no onboarding for source {source_id!r}")
    return record.to_dict()


@router.post("/onboarding/{source_id}")
def post_onboarding(
    source_id: str,
    body: OnboardingActionBody,
    db: Database = Depends(get_db),
) -> dict:
    """Start onboarding (``action=start``) or advance the lifecycle
    (``action=advance`` + ``to_status``). Domain errors map to HTTP:
    unknown connector type → 422, unknown/missing onboarding → 404, illegal
    transition → 409."""
    action = (body.action or "").strip().lower()
    if action == "start":
        go_live: Optional[date] = None
        if body.go_live_date:
            try:
                go_live = date.fromisoformat(body.go_live_date)
            except ValueError:
                raise HTTPException(status_code=400, detail="go_live_date must be ISO date YYYY-MM-DD")
        try:
            record = ct.start_onboarding(
                db, source_id,
                owner=body.owner, contact=body.contact,
                connector_type=body.connector_type,
                go_live_date=go_live, escalation=body.escalation,
            )
        except ct.UnknownConnectorType as e:
            raise HTTPException(status_code=422, detail=str(e))
        return record.to_dict()

    if action == "advance":
        if not body.to_status:
            raise HTTPException(status_code=400, detail="to_status is required for action=advance")
        try:
            record = ct.advance_onboarding(db, source_id, body.to_status)
        except ct.OnboardingNotFound as e:
            raise HTTPException(status_code=404, detail=str(e))
        except ct.InvalidTransition as e:
            raise HTTPException(status_code=409, detail=str(e))
        return record.to_dict()

    raise HTTPException(status_code=400, detail="action must be 'start' or 'advance'")
