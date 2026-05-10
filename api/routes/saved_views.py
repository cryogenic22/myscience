"""BE-21 — saved-views CRUD."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.deps import get_db, require_role
from db import Database
from services import saved_views as svc

logger = logging.getLogger(__name__)

router = APIRouter(tags=["saved_views"])


class CreateBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    state: dict = Field(default_factory=dict)
    shareable: bool = False


class PatchBody(BaseModel):
    name: Optional[str] = Field(default=None, max_length=200)
    state: Optional[dict] = None
    shareable: Optional[bool] = None


@router.get("/saved-views")
def list_endpoint(
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    return {"views": svc.list_views(db, owner_user_id=str(user["id"]))}


@router.post("/saved-views", status_code=201)
def create_endpoint(
    body: CreateBody,
    user: dict = Depends(require_role("uploader")),
    db: Database = Depends(get_db),
):
    try:
        return svc.create_view(
            db,
            owner_user_id=str(user["id"]),
            name=body.name,
            state=body.state or {},
            shareable=body.shareable,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/saved-views/{view_id}")
def get_endpoint(
    view_id: str,
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    view = svc.get_view(db, view_id=view_id, owner_user_id=str(user["id"]))
    if not view:
        raise HTTPException(404, f"saved view not found: {view_id}")
    return view


@router.patch("/saved-views/{view_id}")
def patch_endpoint(
    view_id: str,
    body: PatchBody,
    user: dict = Depends(require_role("uploader")),
    db: Database = Depends(get_db),
):
    try:
        view = svc.patch_view(
            db,
            view_id=view_id,
            owner_user_id=str(user["id"]),
            name=body.name,
            state=body.state,
            shareable=body.shareable,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not view:
        raise HTTPException(404, f"saved view not found: {view_id}")
    return view


@router.delete("/saved-views/{view_id}", status_code=204)
def delete_endpoint(
    view_id: str,
    user: dict = Depends(require_role("uploader")),
    db: Database = Depends(get_db),
):
    if not svc.delete_view(db, view_id=view_id, owner_user_id=str(user["id"])):
        raise HTTPException(404, f"saved view not found: {view_id}")
    return None


# Public (un-authenticated) shareable-link view.
@router.get("/shared/views/{slug}")
def get_shared_endpoint(slug: str, db: Database = Depends(get_db)):
    view = svc.get_by_slug(db, slug=slug)
    if not view:
        raise HTTPException(404, f"shared view not found: {slug}")
    # Don't leak owner identity in the public shareable response.
    out = dict(view)
    out.pop("owner_user_id", None)
    return out
