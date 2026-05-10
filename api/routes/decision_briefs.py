"""SPEC_023 — Decision Briefs API.

Endpoints:
  POST    /decision-briefs                                 uploader+
  GET     /decision-briefs                                 viewer+
  GET     /decision-briefs/{brief_id}                      viewer+
  PATCH   /decision-briefs/{brief_id}                      uploader+
  DELETE  /decision-briefs/{brief_id}                      uploader+
  POST    /decision-briefs/{brief_id}/options              uploader+
  DELETE  /decision-briefs/{brief_id}/options/{option_id}  uploader+
  POST    /decision-briefs/{brief_id}/transitions          uploader+

A Decision Brief is the canonical handoff from sensing → simulation. The
state machine is enforced by the service layer; illegal transitions return
409 Conflict with an explanatory message.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from api.deps import get_db, require_role
from db import Database
from services.decision_brief import (
    BriefImmutable,
    BriefNotFound,
    BriefState,
    DecisionBriefService,
    InsufficientOptions,
    InvalidStateTransition,
    InvalidTriggerKind,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/decision-briefs", tags=["decision-briefs"])


# ────────────────────────────────────────────────────────────────────
# Request/response schemas
# ────────────────────────────────────────────────────────────────────

class CreateBriefBody(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    trigger_kind: str = Field(default="manual")
    trigger_signal_ids: Optional[list[str]] = None
    trigger_metadata: Optional[dict] = None
    stakeholders: Optional[list[str]] = None
    time_horizon_days: Optional[int] = Field(default=None, gt=0, le=3650)
    evidence_refs: Optional[list[dict]] = None
    constraints: Optional[list[str]] = None
    success_criteria: Optional[str] = Field(default=None, max_length=4000)
    confidence_to_proceed: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    war_room_id: Optional[str] = None

    @field_validator("trigger_kind")
    @classmethod
    def _check_trigger(cls, v: str) -> str:
        if v not in {"manual", "threshold", "cluster", "calendar"}:
            raise ValueError(f"trigger_kind must be one of manual|threshold|cluster|calendar, got {v!r}")
        return v


class PatchBriefBody(BaseModel):
    question: Optional[str] = Field(default=None, min_length=1, max_length=2000)
    stakeholders: Optional[list[str]] = None
    time_horizon_days: Optional[int] = Field(default=None, gt=0, le=3650)
    evidence_refs: Optional[list[dict]] = None
    constraints: Optional[list[str]] = None
    success_criteria: Optional[str] = Field(default=None, max_length=4000)
    confidence_to_proceed: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class AddOptionBody(BaseModel):
    label: str = Field(min_length=1, max_length=500)
    description: Optional[str] = Field(default=None, max_length=4000)
    predicted_outcome: Optional[str] = Field(default=None, max_length=2000)
    cost_estimate: Optional[str] = Field(default=None, max_length=500)
    risk_notes: Optional[str] = Field(default=None, max_length=2000)


class TransitionBody(BaseModel):
    to_state: str
    reason: Optional[str] = Field(default=None, max_length=2000)

    @field_validator("to_state")
    @classmethod
    def _check_state(cls, v: str) -> str:
        try:
            BriefState(v)
        except ValueError:
            valid = sorted(s.value for s in BriefState)
            raise ValueError(f"to_state must be one of {valid}, got {v!r}")
        return v


# ────────────────────────────────────────────────────────────────────
# Routes
# ────────────────────────────────────────────────────────────────────

@router.post("", status_code=201)
def create_brief(
    body: CreateBriefBody,
    user: dict = Depends(require_role("uploader")),
    db: Database = Depends(get_db),
):
    try:
        brief = DecisionBriefService.create_draft(
            db,
            question=body.question,
            trigger_kind=body.trigger_kind,
            trigger_signal_ids=body.trigger_signal_ids or [],
            trigger_metadata=body.trigger_metadata or {},
            stakeholders=body.stakeholders or [],
            time_horizon_days=body.time_horizon_days,
            evidence_refs=body.evidence_refs or [],
            constraints=body.constraints or [],
            success_criteria=body.success_criteria,
            confidence_to_proceed=body.confidence_to_proceed,
            owner_user_id=str(user["id"]),
            war_room_id=body.war_room_id,
            actor_user_id=str(user["id"]),
        )
    except (ValueError, InvalidTriggerKind) as e:
        raise HTTPException(400, str(e))
    return brief.to_dict()


@router.get("")
def list_briefs(
    state: Optional[str] = Query(default=None),
    owner_user_id: Optional[str] = Query(default=None),
    trigger_kind: Optional[str] = Query(default=None),
    include_archived: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    if state is not None:
        try:
            BriefState(state)
        except ValueError:
            valid = sorted(s.value for s in BriefState)
            raise HTTPException(400, f"state must be one of {valid}")
    try:
        briefs = DecisionBriefService.list(
            db,
            state=state,
            owner_user_id=owner_user_id,
            trigger_kind=trigger_kind,
            include_archived=include_archived,
            limit=limit,
            offset=offset,
        )
    except (ValueError, InvalidTriggerKind) as e:
        raise HTTPException(400, str(e))
    return {
        "briefs": [b.to_dict() for b in briefs],
        "limit": limit,
        "offset": offset,
        "count": len(briefs),
    }


@router.get("/{brief_id}")
def get_brief(
    brief_id: str,
    include_archived: bool = Query(default=False),
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    brief = DecisionBriefService.get(db, brief_id, include_archived=include_archived)
    if not brief:
        raise HTTPException(404, f"brief not found: {brief_id}")
    return brief.to_dict()


@router.patch("/{brief_id}")
def patch_brief(
    brief_id: str,
    body: PatchBriefBody,
    user: dict = Depends(require_role("uploader")),
    db: Database = Depends(get_db),
):
    try:
        brief = DecisionBriefService.update(
            db,
            brief_id,
            question=body.question,
            stakeholders=body.stakeholders,
            time_horizon_days=body.time_horizon_days,
            evidence_refs=body.evidence_refs,
            constraints=body.constraints,
            success_criteria=body.success_criteria,
            confidence_to_proceed=body.confidence_to_proceed,
        )
    except BriefNotFound:
        raise HTTPException(404, f"brief not found: {brief_id}")
    except BriefImmutable as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return brief.to_dict()


@router.delete("/{brief_id}", status_code=200)
def archive_brief(
    brief_id: str,
    user: dict = Depends(require_role("uploader")),
    db: Database = Depends(get_db),
):
    try:
        brief = DecisionBriefService.archive(db, brief_id, actor_user_id=str(user["id"]))
    except BriefNotFound:
        raise HTTPException(404, f"brief not found: {brief_id}")
    except BriefImmutable as e:
        raise HTTPException(409, str(e))
    return brief.to_dict()


@router.post("/{brief_id}/options", status_code=201)
def add_option(
    brief_id: str,
    body: AddOptionBody,
    user: dict = Depends(require_role("uploader")),
    db: Database = Depends(get_db),
):
    try:
        opt = DecisionBriefService.add_option(
            db,
            brief_id,
            label=body.label,
            description=body.description,
            predicted_outcome=body.predicted_outcome,
            cost_estimate=body.cost_estimate,
            risk_notes=body.risk_notes,
        )
    except BriefNotFound:
        raise HTTPException(404, f"brief not found: {brief_id}")
    except BriefImmutable as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return opt.to_dict()


@router.delete("/{brief_id}/options/{option_id}", status_code=204)
def remove_option(
    brief_id: str,
    option_id: str,
    user: dict = Depends(require_role("uploader")),
    db: Database = Depends(get_db),
):
    try:
        DecisionBriefService.remove_option(db, brief_id, option_id)
    except BriefNotFound:
        raise HTTPException(404, f"brief not found: {brief_id}")
    except BriefImmutable as e:
        raise HTTPException(409, str(e))
    return None


@router.post("/{brief_id}/transitions", status_code=200)
def transition_brief(
    brief_id: str,
    body: TransitionBody,
    user: dict = Depends(require_role("uploader")),
    db: Database = Depends(get_db),
):
    try:
        brief = DecisionBriefService.transition(
            db,
            brief_id,
            body.to_state,
            actor_user_id=str(user["id"]),
            reason=body.reason,
        )
    except BriefNotFound:
        raise HTTPException(404, f"brief not found: {brief_id}")
    except (InvalidStateTransition, InsufficientOptions, BriefImmutable) as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return brief.to_dict()


# ════════════════════════════════════════════════════════════════════
# BE-7 · POST /decision-briefs/{brief_id}/suggest
# ════════════════════════════════════════════════════════════════════


class SuggestBody(BaseModel):
    current_text: str = Field(default="", max_length=64000)
    current_options: Optional[list[dict]] = None
    evidence_refs: Optional[list[dict]] = None
    cursor_position: Optional[dict] = None


@router.post("/{brief_id}/suggest", status_code=200)
def suggest_brief(
    brief_id: str,
    body: SuggestBody,
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    """BE-7 — strategist + curator inline suggestions (PB-402).

    Verifies the brief exists then delegates to
    ``services.brief_suggestions.suggest``. Returns a stale-token
    so the frontend can throttle rerequests when the body hasn't
    changed.
    """
    try:
        brief = DecisionBriefService.get(db, brief_id)
    except BriefNotFound:
        raise HTTPException(404, f"brief not found: {brief_id}")
    except Exception:
        brief = None  # service unavailable — still serve heuristics
    _ = brief  # presence-only; we don't actually need the brief content

    from services import brief_suggestions as svc
    # LLM is opt-in via deps; the service handles unavailability gracefully.
    try:
        from api.deps import get_llm
        llm = get_llm()
    except Exception:
        llm = None

    suggestions = svc.suggest(
        current_text=body.current_text,
        current_options=body.current_options,
        evidence_refs=body.evidence_refs,
        cursor_position=body.cursor_position,
        llm=llm,
    )
    return {
        "suggestions": suggestions,
        "stale_token": svc.stale_token(body.current_text),
    }
