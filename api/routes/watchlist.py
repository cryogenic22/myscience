"""SPEC-020 — Watchlist API.

Per-user CI watchlist. Viewer+ can manage their own entries.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from api.deps import get_db, require_role, get_current_user
from db import Database

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


class WatchlistAdd(BaseModel):
    entity_type: str
    entity_id: str
    label: Optional[str] = None


def _row_to_dict(row: dict) -> dict:
    created = row.get("created_at")
    return {
        "id": str(row.get("id")),
        "user_id": str(row.get("user_id")),
        "entity_type": row.get("entity_type"),
        "entity_id": row.get("entity_id"),
        "label": row.get("label"),
        "created_at": created.isoformat() if hasattr(created, "isoformat") else created,
    }


@router.get("")
def list_watchlist(
    user: Optional[dict] = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    # Anonymous visitors have no personal watchlist — return an empty list (200) rather than
    # 401. The CI cockpit loads /watchlist on open; a 401 there trips the frontend's global
    # session-expired handler (any 401 clears the auth token and fires `mz:auth-expired`),
    # which was breaking multiple CI pages for logged-out visitors. Mutations (POST/DELETE)
    # still require a real viewer, so nothing can be written without authentication.
    if not user:
        return {"entries": []}
    try:
        rows = db.fetch_all(
            """SELECT id, user_id, entity_type, entity_id, label, created_at
               FROM watchlist_entries WHERE user_id = %s::uuid
               ORDER BY created_at DESC""",
            [user.get("id")],
        )
    except Exception:
        logger.exception("watchlist list failed")
        rows = []
    return {"entries": [_row_to_dict(r) for r in rows]}


@router.post("", status_code=201)
def add_watchlist(
    body: WatchlistAdd,
    response: Response,
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    """Add a watchlist entry. Idempotent on (user, entity_type, entity_id).

    Returns 201 on new insert, 200 with the existing row on duplicate.
    """
    if not body.entity_type or not body.entity_id:
        raise HTTPException(400, "entity_type and entity_id are required")

    # Check for existing
    try:
        existing = db.fetch_one(
            """SELECT id, user_id, entity_type, entity_id, label, created_at
               FROM watchlist_entries
               WHERE user_id = %s::uuid AND entity_type = %s AND entity_id = %s""",
            [user.get("id"), body.entity_type, body.entity_id],
        )
    except Exception:
        existing = None

    if existing:
        response.status_code = 200
        return _row_to_dict(existing)

    try:
        db.execute(
            """INSERT INTO watchlist_entries
                   (user_id, entity_type, entity_id, label)
               VALUES (%s::uuid, %s, %s, %s)""",
            [user.get("id"), body.entity_type, body.entity_id, body.label],
        )
    except Exception as exc:
        logger.exception("watchlist insert failed")
        raise HTTPException(500, f"insert failed: {exc}") from exc

    # Read back the inserted row
    try:
        row = db.fetch_one(
            """SELECT id, user_id, entity_type, entity_id, label, created_at
               FROM watchlist_entries
               WHERE user_id = %s::uuid AND entity_type = %s AND entity_id = %s""",
            [user.get("id"), body.entity_type, body.entity_id],
        )
    except Exception:
        row = None

    if not row:
        raise HTTPException(500, "insert succeeded but read-back failed")
    return _row_to_dict(row)


@router.delete("/{entry_id}", status_code=204)
def delete_watchlist(
    entry_id: str,
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    try:
        existing = db.fetch_one(
            """SELECT id, user_id FROM watchlist_entries WHERE id::text = %s""",
            [entry_id],
        )
    except Exception:
        existing = None

    if not existing:
        raise HTTPException(404, f"watchlist entry not found: {entry_id}")
    if str(existing.get("user_id")) != str(user.get("id")):
        # Don't reveal that the row exists for someone else
        raise HTTPException(404, f"watchlist entry not found: {entry_id}")

    try:
        db.execute(
            "DELETE FROM watchlist_entries WHERE id::text = %s",
            [entry_id],
        )
    except Exception as exc:
        logger.exception("watchlist delete failed")
        raise HTTPException(500, f"delete failed: {exc}") from exc

    return Response(status_code=204)
