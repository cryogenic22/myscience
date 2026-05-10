"""BE-21 — Saved-views service.

Persistent graph view state with optional shareable slug. Backs the
PB-703 frontend that lets a user "save view" + revisit + share.
"""

from __future__ import annotations

import json
import logging
import secrets
import string
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)


_SLUG_ALPHABET = string.ascii_lowercase + string.digits
SLUG_LEN = 12

MAX_NAME_LEN = 200
MAX_STATE_BYTES = 64 * 1024  # 64 KB JSON cap — guards against page-state bloat


def _new_slug() -> str:
    return "".join(secrets.choice(_SLUG_ALPHABET) for _ in range(SLUG_LEN))


@dataclass
class SavedView:
    view_id: str
    owner_user_id: str
    name: str
    version: int
    state: dict
    shareable_slug: Optional[str]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    def to_dict(self) -> dict:
        return {
            "view_id":        str(self.view_id),
            "owner_user_id":  str(self.owner_user_id),
            "name":           self.name,
            "version":        self.version,
            "state":          self.state or {},
            "shareable_slug": self.shareable_slug,
            "created_at":     self.created_at.isoformat() if self.created_at else None,
            "updated_at":     self.updated_at.isoformat() if self.updated_at else None,
        }


def _row_to_view(row: dict) -> SavedView:
    state = row.get("state") or {}
    if isinstance(state, str):
        try:
            state = json.loads(state)
        except (TypeError, ValueError):
            state = {}
    return SavedView(
        view_id=str(row["view_id"]),
        owner_user_id=str(row["owner_user_id"]),
        name=row["name"],
        version=int(row.get("version") or 1),
        state=state,
        shareable_slug=row.get("shareable_slug"),
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


def _validate(*, name: str, state: dict) -> None:
    if not name or not name.strip():
        raise ValueError("name required")
    if len(name) > MAX_NAME_LEN:
        raise ValueError(f"name exceeds {MAX_NAME_LEN} chars")
    if state is None:
        raise ValueError("state required")
    if not isinstance(state, dict):
        raise ValueError("state must be a dict")
    encoded = json.dumps(state)
    if len(encoded) > MAX_STATE_BYTES:
        raise ValueError(f"state exceeds {MAX_STATE_BYTES} bytes")


def list_views(db: Any, *, owner_user_id: str, limit: int = 50) -> list[dict]:
    rows = db.fetch_all(
        """
        SELECT view_id, owner_user_id, name, version, state,
               shareable_slug, created_at, updated_at
          FROM saved_views
         WHERE owner_user_id::text = %s
         ORDER BY updated_at DESC
         LIMIT %s
        """,
        [str(owner_user_id), max(1, min(int(limit), 200))],
    ) or []
    return [_row_to_view(r).to_dict() for r in rows]


def create_view(
    db: Any,
    *,
    owner_user_id: str,
    name: str,
    state: dict,
    shareable: bool = False,
) -> dict:
    _validate(name=name, state=state)
    slug = _new_slug() if shareable else None
    row = db.fetch_one(
        """
        INSERT INTO saved_views (owner_user_id, name, state, shareable_slug)
        VALUES (%s::uuid, %s, %s::jsonb, %s)
        RETURNING view_id, owner_user_id, name, version, state,
                  shareable_slug, created_at, updated_at
        """,
        [str(owner_user_id), name, json.dumps(state), slug],
    )
    if not row:
        raise RuntimeError("create_view: insert returned no row")
    return _row_to_view(row).to_dict()


def get_view(db: Any, *, view_id: str, owner_user_id: Optional[str] = None) -> Optional[dict]:
    """Owner-scoped read. ``owner_user_id`` enforces tenancy when set;
    pass ``None`` for the shared-by-slug path which uses ``get_by_slug``."""
    if owner_user_id is not None:
        row = db.fetch_one(
            """SELECT view_id, owner_user_id, name, version, state,
                      shareable_slug, created_at, updated_at
                 FROM saved_views
                WHERE view_id::text = %s AND owner_user_id::text = %s""",
            [str(view_id), str(owner_user_id)],
        )
    else:
        row = db.fetch_one(
            """SELECT view_id, owner_user_id, name, version, state,
                      shareable_slug, created_at, updated_at
                 FROM saved_views
                WHERE view_id::text = %s""",
            [str(view_id)],
        )
    return _row_to_view(row).to_dict() if row else None


def get_by_slug(db: Any, *, slug: str) -> Optional[dict]:
    """Resolve a shareable slug. No owner check — that's the point."""
    row = db.fetch_one(
        """SELECT view_id, owner_user_id, name, version, state,
                  shareable_slug, created_at, updated_at
             FROM saved_views WHERE shareable_slug = %s""",
        [slug],
    )
    return _row_to_view(row).to_dict() if row else None


def patch_view(
    db: Any,
    *,
    view_id: str,
    owner_user_id: str,
    name: Optional[str] = None,
    state: Optional[dict] = None,
    shareable: Optional[bool] = None,
) -> Optional[dict]:
    """Owner-scoped partial update; bumps version on any change.

    ``shareable=True`` mints a slug if none exists; ``shareable=False``
    clears any existing slug.
    """
    existing = get_view(db, view_id=view_id, owner_user_id=owner_user_id)
    if not existing:
        return None
    eff_name  = name  if name  is not None else existing["name"]
    eff_state = state if state is not None else existing["state"]
    _validate(name=eff_name, state=eff_state)

    if shareable is True:
        eff_slug = existing.get("shareable_slug") or _new_slug()
    elif shareable is False:
        eff_slug = None
    else:
        eff_slug = existing.get("shareable_slug")

    row = db.fetch_one(
        """
        UPDATE saved_views
           SET name = %s,
               state = %s::jsonb,
               version = version + 1,
               shareable_slug = %s
         WHERE view_id::text = %s AND owner_user_id::text = %s
        RETURNING view_id, owner_user_id, name, version, state,
                  shareable_slug, created_at, updated_at
        """,
        [eff_name, json.dumps(eff_state), eff_slug,
         str(view_id), str(owner_user_id)],
    )
    return _row_to_view(row).to_dict() if row else None


def delete_view(db: Any, *, view_id: str, owner_user_id: str) -> bool:
    row = db.fetch_one(
        """DELETE FROM saved_views
            WHERE view_id::text = %s AND owner_user_id::text = %s
            RETURNING view_id""",
        [str(view_id), str(owner_user_id)],
    )
    return row is not None
