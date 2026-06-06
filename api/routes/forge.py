"""DF-1 + DF-2 — Domain Forge API: a playable SME elicitation round.

One SME interaction = a playbook edit + a gold eval label + a validation signal.

Mounted on its OWN prefix (`/forge`) — NOT under /entities, whose greedy
`/{entity_type}[/{entity_id}]` routes would otherwise shadow these.

Endpoints:
  POST /forge/rounds                         uploader+  generate a round FROM real DB entities
  GET  /forge/rounds/{round_id}              viewer+    read a round
  POST /forge/rounds/{round_id}/answer       uploader+  submit a constrained answer
  GET  /forge/sessions/{session_id}          viewer+    session summary (rounds / score)
  GET  /forge/eval-items                      viewer+    gold eval items (for the harness)
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.deps import get_db, require_role
from db import Database
from services.domain_forge import (
    ForgeEngine,
    InvalidAnswer,
    RoundAlreadyAnswered,
    RoundNotFound,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/forge", tags=["forge"])

_engine = ForgeEngine()


# ────────────────────────────────────────────────────────────────────
# Schemas
# ────────────────────────────────────────────────────────────────────


class CreateRoundBody(BaseModel):
    session_id: str = Field(min_length=1, max_length=200)
    # DF-5: which game to play. Each is grounded in real DB rows.
    #   what_matters | signal_or_noise | routing | critique
    round_type: str = "what_matters"
    # intent / playbook_id default per round_type when omitted.
    intent: Optional[str] = None
    playbook_id: Optional[str] = None
    # Optional explicit entity pairing; otherwise real entities are picked.
    entities: Optional[list[dict]] = None
    # Round-type-specific params (all optional, sensible defaults):
    dimension_key: Optional[str] = None   # routing ③
    predicate: Optional[str] = None       # critique ④


class SubmitAnswerBody(BaseModel):
    """The SME's constrained answer. Shape depends on the round type:
      * what_matters ① : ranked / selected dimension keys.
      * routing      ③ : selected route keys.
      * signal_or_noise ② : signal_id + reason.
      * critique     ④ : grade (+ optional correction).
    """
    # what_matters / routing
    selected: list[str] = Field(default_factory=list)
    ranking: list[str] = Field(default_factory=list)
    # signal_or_noise
    signal_id: Optional[str] = None
    reason: Optional[str] = None
    # critique
    grade: Optional[str] = None
    correction: Optional[str] = None
    sme_id: Optional[str] = None


def _sme(body_sme: Optional[str], user: dict) -> Optional[str]:
    """Prefer an explicit sme_id from the body, else the authenticated user."""
    return body_sme or (str(user.get("id")) if user else None)


# ────────────────────────────────────────────────────────────────────
# Routes
# ────────────────────────────────────────────────────────────────────


@router.post("/rounds", status_code=201)
def create_round(
    body: CreateRoundBody,
    user: dict = Depends(require_role("uploader")),
    db: Database = Depends(get_db),
):
    # Pass only the round-type params the caller supplied (generators default
    # the rest); avoids overriding generator defaults with None.
    extra: dict = {}
    if body.dimension_key is not None:
        extra["dimension_key"] = body.dimension_key
    if body.predicate is not None:
        extra["predicate"] = body.predicate
    try:
        return _engine.create_round(
            db,
            session_id=body.session_id,
            round_type=body.round_type,
            intent=body.intent,
            playbook_id=body.playbook_id,
            entities=body.entities,
            created_by=(str(user.get("id")) if user else None),
            **extra,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/rounds/{round_id}")
def get_round(
    round_id: str,
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    rnd = _engine.get_round(db, round_id)
    if rnd is None:
        raise HTTPException(404, f"round not found: {round_id}")
    return rnd


@router.post("/rounds/{round_id}/answer")
def submit_answer(
    round_id: str,
    body: SubmitAnswerBody,
    user: dict = Depends(require_role("uploader")),
    db: Database = Depends(get_db),
):
    # One answer envelope covers every round type; the engine reads the fields
    # relevant to the stored round's round_type.
    answer = {
        "selected": body.selected,
        "ranking": body.ranking,
        "signal_id": body.signal_id,
        "reason": body.reason,
        "grade": body.grade,
        "correction": body.correction,
    }
    try:
        return _engine.submit_answer(
            db, round_id, answer, sme_id=_sme(body.sme_id, user),
        )
    except RoundNotFound as e:
        raise HTTPException(404, str(e))
    except RoundAlreadyAnswered as e:
        raise HTTPException(409, str(e))
    except InvalidAnswer as e:
        raise HTTPException(400, str(e))


@router.get("/sessions/{session_id}")
def session_summary(
    session_id: str,
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    return _engine.session_summary(db, session_id)


@router.get("/eval-items")
def list_eval_items(
    playbook_id: Optional[str] = Query(None),
    session_id: Optional[str] = Query(None),
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    return {
        "eval_items": _engine.list_eval_items(
            db, playbook_id=playbook_id, session_id=session_id
        )
    }
