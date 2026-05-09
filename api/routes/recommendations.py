"""SPEC_033 — Counter-Recommendation API.

Endpoints:
  POST  /recommendations/synthesize        uploader+
  GET   /recommendations                   viewer+
  GET   /recommendations/{recommendation_id}  viewer+
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from api.deps import get_db, require_role
from db import Database
from services import counter_recommendation as svc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


# ────────────────────────────────────────────────────────────────────
# Schemas
# ────────────────────────────────────────────────────────────────────

class OptionBody(BaseModel):
    option_id: str = Field(min_length=1, max_length=100)
    label: str = Field(min_length=1, max_length=500)
    score: float = Field(ge=0.0, le=1.0)
    predicted_outcome: Optional[str] = Field(default=None, max_length=2000)
    risk_notes: Optional[str] = Field(default=None, max_length=2000)
    dimension_scores: Optional[dict[str, float]] = None


class SynthesizeBody(BaseModel):
    brief_id: Optional[str] = None
    options: list[OptionBody] = Field(min_length=1, max_length=20)
    method: str = Field(default="score_based")

    @field_validator("method")
    @classmethod
    def _check_method(cls, v: str) -> str:
        if v not in svc.VALID_METHODS:
            raise ValueError(f"method must be in {sorted(svc.VALID_METHODS)}")
        return v


# ────────────────────────────────────────────────────────────────────
# Routes
# ────────────────────────────────────────────────────────────────────

@router.post("/synthesize", status_code=200)
def synthesize(
    body: SynthesizeBody,
    user: dict = Depends(require_role("uploader")),
    db: Database = Depends(get_db),
):
    options = [
        svc.OptionInput(
            option_id=o.option_id, label=o.label, score=o.score,
            predicted_outcome=o.predicted_outcome,
            risk_notes=o.risk_notes,
            dimension_scores=o.dimension_scores,
        )
        for o in body.options
    ]
    synthesizer = svc.CounterRecSynthesizer()
    try:
        result = synthesizer.synthesize(
            db,
            options=options,
            brief_id=body.brief_id,
            method=body.method,
            started_by_user_id=str(user["id"]),
        )
    except svc.CounterRecRuleViolation as e:
        raise HTTPException(422, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return result.to_dict()


@router.get("")
def list_recs(
    brief_id: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    try:
        recs = svc.list_recommendations(db, brief_id=brief_id, limit=limit, offset=offset)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"recommendations": recs, "limit": limit, "offset": offset, "count": len(recs)}


@router.get("/{recommendation_id}")
def get_rec(
    recommendation_id: str,
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    rec = svc.get_recommendation(db, recommendation_id)
    if not rec:
        raise HTTPException(404, f"recommendation not found: {recommendation_id}")
    return rec
