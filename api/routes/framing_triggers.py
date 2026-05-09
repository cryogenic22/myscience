"""SPEC_029 — Framing Triggers API.

Endpoints:
  POST   /framing-triggers                          uploader+
  GET    /framing-triggers                          viewer+
  POST   /framing-triggers/tick                     uploader+
  GET    /framing-triggers/{trigger_id}             viewer+
  PATCH  /framing-triggers/{trigger_id}             uploader+
  DELETE /framing-triggers/{trigger_id}             uploader+
  POST   /framing-triggers/{trigger_id}/evaluate    uploader+
  GET    /framing-triggers/{trigger_id}/fires       viewer+
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from api.deps import get_db, require_role
from db import Database
from services.framing_triggers import (
    FramingOrchestrator,
    FramingTriggerService,
    TriggerNotFound,
    VALID_KINDS,
    validate_config,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/framing-triggers", tags=["framing-triggers"])


# ────────────────────────────────────────────────────────────────────
# Schemas
# ────────────────────────────────────────────────────────────────────

class CreateTriggerBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    kind: str
    config: dict
    assignee_user_id: Optional[str] = None

    @field_validator("kind")
    @classmethod
    def _check_kind(cls, v: str) -> str:
        if v not in VALID_KINDS:
            raise ValueError(f"kind must be in {sorted(VALID_KINDS)}")
        return v


class PatchTriggerBody(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    config: Optional[dict] = None
    assignee_user_id: Optional[str] = None
    is_active: Optional[bool] = None


# ────────────────────────────────────────────────────────────────────
# Routes
# ────────────────────────────────────────────────────────────────────

@router.post("", status_code=201)
def create_trigger(
    body: CreateTriggerBody,
    user: dict = Depends(require_role("uploader")),
    db: Database = Depends(get_db),
):
    try:
        validate_config(body.kind, body.config)
        t = FramingTriggerService.create(
            db,
            name=body.name,
            kind=body.kind,
            config=body.config,
            assignee_user_id=body.assignee_user_id,
            created_by_user_id=str(user["id"]),
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return t.to_dict()


@router.get("")
def list_triggers(
    kind: Optional[str] = Query(default=None),
    is_active: Optional[bool] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    try:
        ts = FramingTriggerService.list(db, kind=kind, is_active=is_active,
                                         limit=limit, offset=offset)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"triggers": [t.to_dict() for t in ts],
            "limit": limit, "offset": offset, "count": len(ts)}


# tick MUST come before /{trigger_id} to resolve correctly
@router.post("/tick", status_code=200)
def tick_all(
    user: dict = Depends(require_role("uploader")),
    db: Database = Depends(get_db),
):
    """Evaluate every active trigger now. Returns per-trigger results.
    Failures are isolated; one trigger's crash doesn't abort the others."""
    orch = FramingOrchestrator()
    results = orch.tick(db)
    return {"results": [r.to_dict() for r in results], "count": len(results)}


@router.get("/{trigger_id}")
def get_trigger(
    trigger_id: str,
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    t = FramingTriggerService.get(db, trigger_id)
    if not t:
        raise HTTPException(404, f"trigger not found: {trigger_id}")
    return t.to_dict()


@router.patch("/{trigger_id}")
def patch_trigger(
    trigger_id: str,
    body: PatchTriggerBody,
    user: dict = Depends(require_role("uploader")),
    db: Database = Depends(get_db),
):
    try:
        t = FramingTriggerService.update(
            db, trigger_id,
            name=body.name, config=body.config,
            assignee_user_id=body.assignee_user_id,
            is_active=body.is_active,
        )
    except TriggerNotFound:
        raise HTTPException(404, f"trigger not found: {trigger_id}")
    except ValueError as e:
        raise HTTPException(400, str(e))
    return t.to_dict()


@router.delete("/{trigger_id}", status_code=204)
def delete_trigger(
    trigger_id: str,
    user: dict = Depends(require_role("uploader")),
    db: Database = Depends(get_db),
):
    try:
        FramingTriggerService.delete(db, trigger_id)
    except TriggerNotFound:
        raise HTTPException(404, f"trigger not found: {trigger_id}")
    return None


@router.post("/{trigger_id}/evaluate", status_code=200)
def evaluate_one(
    trigger_id: str,
    user: dict = Depends(require_role("uploader")),
    db: Database = Depends(get_db),
):
    orch = FramingOrchestrator()
    try:
        result = orch.evaluate_one(db, trigger_id)
    except TriggerNotFound:
        raise HTTPException(404, f"trigger not found: {trigger_id}")
    return result.to_dict()


@router.get("/{trigger_id}/fires")
def list_fires(
    trigger_id: str,
    limit: int = Query(default=50, ge=1, le=500),
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    if not FramingTriggerService.get(db, trigger_id):
        raise HTTPException(404, f"trigger not found: {trigger_id}")
    fires = FramingTriggerService.list_fires(db, trigger_id, limit=limit)
    return {"trigger_id": trigger_id, "fires": fires, "count": len(fires)}
