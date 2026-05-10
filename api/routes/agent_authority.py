"""BE-13 — Agent authority settings endpoints (PB-504)."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, Field

from api.deps import get_db, require_role
from db import Database
from services.agent import authority as svc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent-authority", tags=["agent-authority"])


class PatchAuthorityBody(BaseModel):
    new_level: int = Field(ge=1, le=5)


@router.get("")
def list_authority(db: Database = Depends(get_db)):
    """All (agent, scenario_type) authority rows for the settings UI."""
    return {"authority": [a.to_dict() for a in svc.list_all(db)]}


@router.patch("/{agent}/{scenario_type}")
def patch_authority(
    body: PatchAuthorityBody,
    agent: str = Path(...),
    scenario_type: str = Path(...),
    user: dict = Depends(require_role("enterprise")),
    db: Database = Depends(get_db),
):
    """Manual override (admin / steward only). Audited with actor=user_id."""
    try:
        updated = svc.update_authority(
            db,
            agent=agent,
            scenario_type=scenario_type,
            new_level=body.new_level,
            actor_user_id=str(user.get("id") or "admin"),
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    if updated is None:
        raise HTTPException(500, "update_authority returned no row")
    return updated.to_dict()


@router.get("/promotions")
def list_promotions(
    limit: int = Query(default=100, ge=1, le=500),
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    """Paged audit log of recent promotions / demotions / overrides."""
    return {"promotions": svc.list_promotions(db, limit=limit)}
