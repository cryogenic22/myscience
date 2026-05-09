"""SPEC_028 — War-Game Adversaries API.

Endpoints:
  POST   /war-games                          uploader+ (start a run)
  GET    /war-games                          viewer+   (list with filters)
  GET    /war-games/{run_id}                 viewer+   (run + adversaries)
  GET    /war-games/{run_id}/transcript      viewer+   (full chronological)
  POST   /war-games/{run_id}/cancel          uploader+ (cancel running)
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from api.deps import get_db, require_role
from db import Database
from services.war_game_adversary import (
    AdversarySpec,
    BriefNotEligible,
    GroundingRuleViolation,
    StubReactor,
    VALID_KINDS,
    VALID_STATUSES,
    WarGameNotFound,
    WarGameOrchestrator,
    WarGameRepository,
    WarGameStateError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/war-games", tags=["war-games"])


# ────────────────────────────────────────────────────────────────────
# Request schemas
# ────────────────────────────────────────────────────────────────────

class AdversaryBody(BaseModel):
    kind: str
    name: str = Field(min_length=1, max_length=200)
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    persona: Optional[dict] = None
    grounding_evidence_ids: list[str] = Field(min_length=1, max_length=100)

    @field_validator("kind")
    @classmethod
    def _check_kind(cls, v: str) -> str:
        if v not in VALID_KINDS:
            raise ValueError(f"kind must be in {sorted(VALID_KINDS)}")
        return v


class StartRunBody(BaseModel):
    brief_id: str = Field(min_length=1)
    num_rounds: int = Field(default=3, ge=1, le=10)
    adversaries: list[AdversaryBody] = Field(min_length=1, max_length=12)


# ────────────────────────────────────────────────────────────────────
# Routes
# ────────────────────────────────────────────────────────────────────

@router.post("", status_code=201)
def start_run(
    body: StartRunBody,
    user: dict = Depends(require_role("uploader")),
    db: Database = Depends(get_db),
):
    specs = [
        AdversarySpec(
            kind=a.kind,
            name=a.name,
            entity_type=a.entity_type,
            entity_id=a.entity_id,
            persona=a.persona or {},
            grounding_evidence_ids=a.grounding_evidence_ids,
        )
        for a in body.adversaries
    ]
    orchestrator = WarGameOrchestrator(reactor=StubReactor())
    try:
        run = orchestrator.run(
            db,
            brief_id=body.brief_id,
            adversaries=specs,
            num_rounds=body.num_rounds,
            started_by_user_id=str(user["id"]),
        )
    except WarGameNotFound as e:
        raise HTTPException(404, str(e))
    except BriefNotEligible as e:
        raise HTTPException(409, str(e))
    except GroundingRuleViolation as e:
        # 422 since the spec violation comes from caller-provided adversaries
        raise HTTPException(422, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return run.to_dict(include_actions=True)


@router.get("")
def list_runs(
    brief_id: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    if status is not None and status not in VALID_STATUSES:
        raise HTTPException(400, f"status must be in {sorted(VALID_STATUSES)}")
    try:
        runs = WarGameRepository.list(db, brief_id=brief_id, status=status,
                                       limit=limit, offset=offset)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {
        "runs": [r.to_dict() for r in runs],
        "limit": limit, "offset": offset, "count": len(runs),
    }


@router.get("/{run_id}")
def get_run(
    run_id: str,
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    run = WarGameRepository.get(db, run_id)
    if not run:
        raise HTTPException(404, f"run not found: {run_id}")
    return run.to_dict()


@router.get("/{run_id}/transcript")
def get_transcript(
    run_id: str,
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    run = WarGameRepository.get(db, run_id, include_actions=True)
    if not run:
        raise HTTPException(404, f"run not found: {run_id}")
    return run.to_dict(include_actions=True)


@router.post("/{run_id}/cancel", status_code=200)
def cancel_run(
    run_id: str,
    user: dict = Depends(require_role("uploader")),
    db: Database = Depends(get_db),
):
    try:
        run = WarGameRepository.cancel(db, run_id)
    except WarGameNotFound:
        raise HTTPException(404, f"run not found: {run_id}")
    except WarGameStateError as e:
        raise HTTPException(409, str(e))
    return run.to_dict()
