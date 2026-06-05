"""DI-5 — SME playbook authoring API.

Makes Answer Playbooks editable at runtime (no code deploy): CRUD + validation
+ versioning + rollback over the `playbooks` / `playbook_versions` tables. A
DB-stored playbook overrides/extends the YAML seed; the PlaybookRegistry serves
the edited version to the DecompositionPlanner on the next query.

Mounted on its OWN prefix (`/playbooks`) — NOT under /entities, whose greedy
`/{entity_type}[/{entity_id}]` routes would otherwise shadow these.

Endpoints:
  GET    /playbooks                              viewer+   list (DB + seed)
  POST   /playbooks                              uploader+ create (v1)
  GET    /playbooks/predicates                   viewer+   route vocabulary (authoring aid)
  GET    /playbooks/{playbook_id}                viewer+   read current version
  PUT    /playbooks/{playbook_id}                uploader+ edit → new version
  DELETE /playbooks/{playbook_id}                uploader+ delete (revert to seed)
  GET    /playbooks/{playbook_id}/versions       viewer+   version history
  POST   /playbooks/{playbook_id}/rollback       uploader+ restore a prior version
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.deps import get_db, require_role
from db import Database
from services.domain_intelligence.authoring import (
    PlaybookAuthoringService,
    PlaybookConflict,
    PlaybookNotFound,
)
from services.domain_intelligence.validation import (
    PlaybookValidationError,
    known_predicates,
    whitelisted_link_types,
    whitelisted_source_tables,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/playbooks", tags=["playbooks"])


# ────────────────────────────────────────────────────────────────────
# Schemas
# ────────────────────────────────────────────────────────────────────


class CreatePlaybookBody(BaseModel):
    id: str = Field(min_length=1, max_length=200)
    pack: str = "pharma"
    trigger: dict = Field(default_factory=dict)
    dimensions: list = Field(default_factory=list)
    synthesis: dict = Field(default_factory=dict)
    author: Optional[str] = None


class UpdatePlaybookBody(BaseModel):
    # Partial: only present fields change. id is the key (path), never editable.
    pack: Optional[str] = None
    trigger: Optional[dict] = None
    dimensions: Optional[list] = None
    synthesis: Optional[dict] = None
    author: Optional[str] = None
    note: Optional[str] = None


class RollbackBody(BaseModel):
    target_version: int = Field(ge=1)
    author: Optional[str] = None
    note: Optional[str] = None


def _author(body_author: Optional[str], user: dict) -> Optional[str]:
    """Prefer an explicit author from the body, else the authenticated user."""
    return body_author or (str(user.get("id")) if user else None)


# ────────────────────────────────────────────────────────────────────
# Routes
# ────────────────────────────────────────────────────────────────────


@router.get("")
def list_playbooks(
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    return {"playbooks": PlaybookAuthoringService.list(db)}


# Static path BEFORE /{playbook_id} so it isn't captured as an id.
@router.get("/predicates")
def list_route_vocabulary(
    user: dict = Depends(require_role("viewer")),
):
    """The route vocabulary an SME may target — an authoring aid so the editor
    can offer valid routes and explain validation rejections."""
    return {
        "predicates": sorted(known_predicates()),
        "link_types": sorted(whitelisted_link_types()),
        "source_tables": sorted(whitelisted_source_tables()),
    }


@router.post("", status_code=201)
def create_playbook(
    body: CreatePlaybookBody,
    user: dict = Depends(require_role("uploader")),
    db: Database = Depends(get_db),
):
    try:
        return PlaybookAuthoringService.create(
            db,
            {
                "id": body.id,
                "pack": body.pack,
                "trigger": body.trigger,
                "dimensions": body.dimensions,
                "synthesis": body.synthesis,
            },
            author=_author(body.author, user),
        )
    except PlaybookConflict as e:
        raise HTTPException(409, str(e))
    except PlaybookValidationError as e:
        raise HTTPException(400, {"message": "playbook validation failed", "errors": e.errors})
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/{playbook_id}")
def get_playbook(
    playbook_id: str,
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    pb = PlaybookAuthoringService.get(db, playbook_id)
    if pb is None:
        raise HTTPException(404, f"playbook not found in DB: {playbook_id}")
    return pb


@router.put("/{playbook_id}")
def update_playbook(
    playbook_id: str,
    body: UpdatePlaybookBody,
    user: dict = Depends(require_role("uploader")),
    db: Database = Depends(get_db),
):
    try:
        return PlaybookAuthoringService.update(
            db, playbook_id,
            {
                "pack": body.pack,
                "trigger": body.trigger,
                "dimensions": body.dimensions,
                "synthesis": body.synthesis,
            },
            author=_author(body.author, user),
            note=body.note,
        )
    except PlaybookNotFound as e:
        raise HTTPException(404, str(e))
    except PlaybookValidationError as e:
        raise HTTPException(400, {"message": "playbook validation failed", "errors": e.errors})
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.delete("/{playbook_id}", status_code=204)
def delete_playbook(
    playbook_id: str,
    user: dict = Depends(require_role("uploader")),
    db: Database = Depends(get_db),
):
    try:
        PlaybookAuthoringService.delete(db, playbook_id, author=_author(None, user))
    except PlaybookNotFound as e:
        raise HTTPException(404, str(e))
    return None


@router.get("/{playbook_id}/versions")
def list_playbook_versions(
    playbook_id: str,
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    return {
        "playbook_id": playbook_id,
        "versions": PlaybookAuthoringService.list_versions(db, playbook_id),
    }


@router.post("/{playbook_id}/rollback")
def rollback_playbook(
    playbook_id: str,
    body: RollbackBody,
    user: dict = Depends(require_role("uploader")),
    db: Database = Depends(get_db),
):
    try:
        return PlaybookAuthoringService.rollback(
            db, playbook_id, body.target_version,
            author=_author(body.author, user), note=body.note,
        )
    except PlaybookNotFound as e:
        raise HTTPException(404, str(e))
    except PlaybookValidationError as e:
        raise HTTPException(400, {"message": "playbook validation failed", "errors": e.errors})
    except ValueError as e:
        raise HTTPException(400, str(e))
