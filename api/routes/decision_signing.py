"""SPEC_034 — Decision Signing API.

Endpoints (mounted on the decisions router prefix to namespace cleanly):
  POST  /decisions/{decision_id}/sign        uploader+ (decision owner)
  GET   /decisions/{decision_id}/replay      viewer+
  GET   /decisions/{decision_id}/verify      viewer+
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.deps import get_db, require_role
from db import Database
from services.decision_signing import (
    DecisionAlreadySigned,
    DecisionNotFound,
    DecisionNotSigned,
    DecisionSigningService,
    NotDecisionOwner,
)

logger = logging.getLogger(__name__)

# Use a distinct router so this layers on top of api/routes/decisions.py
# without touching the existing module.
router = APIRouter(prefix="/decisions", tags=["decision-signing"])


class SignBody(BaseModel):
    claim_ids: list[str] = Field(min_length=1, max_length=10000)
    brief_id: Optional[str] = None
    force: bool = False


@router.post("/{decision_id}/sign", status_code=200)
def sign(
    decision_id: str,
    body: SignBody,
    user: dict = Depends(require_role("uploader")),
    db: Database = Depends(get_db),
):
    try:
        signed = DecisionSigningService.sign(
            db,
            decision_id=decision_id,
            signing_user_id=str(user["id"]),
            claim_ids=body.claim_ids,
            brief_id=body.brief_id,
            force=body.force,
        )
    except DecisionNotFound:
        raise HTTPException(404, f"decision not found: {decision_id}")
    except NotDecisionOwner as e:
        raise HTTPException(403, str(e))
    except DecisionAlreadySigned as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return signed.to_dict()


@router.get("/{decision_id}/verify")
def verify(
    decision_id: str,
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    try:
        result = DecisionSigningService.verify(db, decision_id)
    except DecisionNotFound:
        raise HTTPException(404, f"decision not found: {decision_id}")
    except DecisionNotSigned:
        raise HTTPException(409, f"decision not signed: {decision_id}")
    return result


@router.get("/{decision_id}/replay")
def replay(
    decision_id: str,
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    try:
        bundle = DecisionSigningService.replay(db, decision_id)
    except DecisionNotFound:
        raise HTTPException(404, f"decision not found: {decision_id}")
    except DecisionNotSigned:
        raise HTTPException(409, f"decision not signed: {decision_id}")
    return bundle.to_dict()
