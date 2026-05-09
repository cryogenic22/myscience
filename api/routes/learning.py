"""SPEC_032 — Learning Service API.

Endpoints:
  POST  /learning/run                       uploader+
  GET   /learning/runs                      viewer+
  GET   /learning/runs/{run_id}             viewer+
  GET   /learning/source-attributions       viewer+
  GET   /learning/prompt-flags              viewer+
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.deps import get_db, require_role
from db import Database
from services import learning_service as svc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/learning", tags=["learning"])


class RunBody(BaseModel):
    since: Optional[datetime] = None
    alpha: Optional[float] = Field(default=None, gt=0.0, le=1.0)
    auto_register_unknown_sources: bool = False


@router.post("/run", status_code=200)
def run_learning(
    body: RunBody,
    user: dict = Depends(require_role("uploader")),
    db: Database = Depends(get_db),
):
    service = svc.LearningService(
        alpha=body.alpha or svc.DEFAULT_EWMA_ALPHA,
        auto_register_unknown_sources=body.auto_register_unknown_sources,
    )
    result = service.run(db, since=body.since, started_by_user_id=str(user["id"]))
    return result.to_dict()


@router.get("/runs")
def list_runs(
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    try:
        runs = svc.list_runs(db, status=status, limit=limit, offset=offset)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"runs": runs, "limit": limit, "offset": offset, "count": len(runs)}


@router.get("/runs/{run_id}")
def get_run(
    run_id: str,
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    rec = svc.get_run(db, run_id)
    if not rec:
        raise HTTPException(404, f"run not found: {run_id}")
    return rec


@router.get("/source-attributions")
def list_source_attributions(
    source_id: Optional[str] = Query(default=None),
    since: Optional[datetime] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    try:
        attrs = svc.list_attributions(db, source_id=source_id, since=since, limit=limit)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"attributions": attrs, "count": len(attrs)}


@router.get("/prompt-flags")
def list_prompt_flags(
    since_days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=100, ge=1, le=500),
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    flags = svc.list_prompt_flags(db, since_days=since_days, limit=limit)
    return {"flags": flags, "count": len(flags)}
