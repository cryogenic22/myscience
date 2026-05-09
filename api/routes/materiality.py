"""SPEC_031 — Materiality Scoring API.

Endpoints:
  POST  /materiality/score        uploader+
  GET   /materiality/weights      viewer+
  PUT   /materiality/weights      uploader+
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from api.deps import get_db, require_role
from db import Database
from services import materiality as svc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/materiality", tags=["materiality"])


# ────────────────────────────────────────────────────────────────────
# Request schemas
# ────────────────────────────────────────────────────────────────────

class ScoreBody(BaseModel):
    source_tier: Optional[int] = Field(default=None, ge=1, le=4)
    entity_criticality: Optional[str] = Field(default=None, max_length=50)
    claim_type: Optional[str] = Field(default=None, max_length=50)
    age_days: Optional[float] = Field(default=None, ge=-1, le=10000)
    signal_id: Optional[str] = None  # if set, persist score to signals row

    @field_validator("entity_criticality")
    @classmethod
    def _check_crit(cls, v: Optional[str]) -> Optional[str]:
        # Don't reject — service falls back to 'other'. Just normalize.
        return v.strip().lower() if v else v


class UpdateWeightsBody(BaseModel):
    weights: dict[str, float] = Field(min_length=1)
    tier_values: dict[str, float] = Field(min_length=1)
    claim_type_values: dict[str, float] = Field(min_length=1)
    criticality_values: dict[str, float] = Field(min_length=1)
    recency_half_life_days: float = Field(default=30.0, gt=0, le=3650)


# ────────────────────────────────────────────────────────────────────
# Routes
# ────────────────────────────────────────────────────────────────────

@router.post("/score", status_code=200)
def score(
    body: ScoreBody,
    user: dict = Depends(require_role("uploader")),
    db: Database = Depends(get_db),
):
    cfg = svc.get_active_config(db)
    result = svc.compute_materiality(
        source_tier=body.source_tier,
        entity_criticality=body.entity_criticality,
        claim_type=body.claim_type,
        age_days=body.age_days,
        config=cfg,
    )
    if body.signal_id:
        svc.persist_score_to_signal(db, signal_id=body.signal_id, result=result)
    out = result.to_dict()
    if body.signal_id:
        out["persisted_to_signal_id"] = body.signal_id
    return out


@router.get("/weights")
def get_weights(
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    cfg = svc.get_active_config(db)
    return cfg.to_dict()


@router.put("/weights", status_code=200)
def update_weights(
    body: UpdateWeightsBody,
    user: dict = Depends(require_role("uploader")),
    db: Database = Depends(get_db),
):
    # Coerce tier_values keys to ints (caller passes string-keyed JSON; we
    # normalize here for the service contract)
    try:
        tier_values_int = {}
        for k, v in body.tier_values.items():
            try:
                tier_values_int[int(k)] = float(v)
            except (TypeError, ValueError):
                raise HTTPException(400, f"tier_values key {k!r} must be an integer")
    except HTTPException:
        raise

    try:
        cfg = svc.replace_active_config(
            db,
            weights=body.weights,
            tier_values=tier_values_int,
            claim_type_values=body.claim_type_values,
            criticality_values=body.criticality_values,
            recency_half_life_days=body.recency_half_life_days,
            user_id=str(user["id"]),
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return cfg.to_dict()
