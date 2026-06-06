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
    intent: str = "compare"
    playbook_id: str = "compare.drug_x_drug"
    # Optional explicit entity pairing; otherwise two fact-rich drugs are picked.
    entities: Optional[list[dict]] = None


class SubmitAnswerBody(BaseModel):
    # The SME's constrained answer: ranked / selected dimension keys.
    selected: list[str] = Field(default_factory=list)
    ranking: list[str] = Field(default_factory=list)
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
    try:
        return _engine.create_round(
            db,
            session_id=body.session_id,
            intent=body.intent,
            playbook_id=body.playbook_id,
            entities=body.entities,
            created_by=(str(user.get("id")) if user else None),
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
    try:
        return _engine.submit_answer(
            db, round_id,
            {"selected": body.selected, "ranking": body.ranking},
            sme_id=_sme(body.sme_id, user),
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
