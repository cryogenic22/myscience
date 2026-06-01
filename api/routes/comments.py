"""Generic entity comments API (UX02 / PB-UX02).

GET  /comments?target_type=&target_id=   → the thread for an entity
POST /comments                           → append a comment
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional

from api.deps import get_db, require_role
from db import Database
from services.entity_comments import add_comment, list_comments

router = APIRouter(tags=["comments"])


class CommentBody(BaseModel):
    target_type: str
    target_id: str
    body: str


@router.get("/comments")
def get_comments(
    target_type: str = Query(...),
    target_id: str = Query(...),
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    items = list_comments(db, target_type, target_id)
    return {"comments": items, "count": len(items)}


@router.post("/comments", status_code=201)
def post_comment(
    body: CommentBody,
    user: dict = Depends(require_role("uploader")),
    db: Database = Depends(get_db),
):
    try:
        return add_comment(
            db, body.target_type, body.target_id, body.body,
            author_user_id=str(user.get("id")) if user.get("id") is not None else None,
            author_display_name=str(user.get("display_name") or user.get("email") or "Analyst"),
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
