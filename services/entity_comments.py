"""Generic entity comments (UX02 / PB-UX02).

A reusable comment thread keyed by (target_type, target_id) — the collaboration
primitive that war-room rounds had hardcoded, generalised so any entity (brief,
scenario, insight, gap, dossier domain, …) can carry a discussion. Thin store
over the entity_comments table (migration 076).
"""
from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

_MENTION_RE = re.compile(r"@([A-Za-z0-9_][\w.-]{0,63})")

_INSERT_SQL = """
    INSERT INTO entity_comments
        (target_type, target_id, author_user_id, author_display_name, body)
    VALUES (%(target_type)s, %(target_id)s, %(author_user_id)s,
            %(author_display_name)s, %(body)s)
    RETURNING id, target_type, target_id, author_user_id, author_display_name,
              body, created_at, edited_at
"""

_LIST_SQL = """
    SELECT id, target_type, target_id, author_user_id, author_display_name,
           body, created_at, edited_at
      FROM entity_comments
     WHERE target_type = %s AND target_id = %s
     ORDER BY created_at ASC
"""


def parse_mentions(body: str) -> list[str]:
    """Extract @mention handles from a comment body (deduped, order-preserving)."""
    seen: dict[str, None] = {}
    for m in _MENTION_RE.findall(body or ""):
        seen.setdefault(m, None)
    return list(seen.keys())


def add_comment(
    db,
    target_type: str,
    target_id: str,
    body: str,
    *,
    author_user_id: Optional[str] = None,
    author_display_name: str = "Anonymous",
) -> dict:
    """Append a comment to an entity's thread. Raises ValueError on empty body."""
    if not body or not body.strip():
        raise ValueError("comment body cannot be empty")
    row = db.fetch_one(_INSERT_SQL, {
        "target_type": target_type,
        "target_id": target_id,
        "author_user_id": author_user_id,
        "author_display_name": author_display_name,
        "body": body.strip(),
    })
    return _row_to_dict(row) if row else {}


def list_comments(db, target_type: str, target_id: str) -> list[dict]:
    try:
        rows = db.fetch_all(_LIST_SQL, [target_type, target_id]) or []
    except Exception:
        logger.exception("list_comments failed for %s/%s", target_type, target_id)
        return []
    return [_row_to_dict(r) for r in rows]


def _row_to_dict(r) -> dict:
    created = r.get("created_at")
    edited = r.get("edited_at")
    return {
        "id": str(r.get("id", "")),
        "target_type": r.get("target_type"),
        "target_id": r.get("target_id"),
        "author_user_id": r.get("author_user_id"),
        "author_display_name": r.get("author_display_name", "Anonymous"),
        "body": r.get("body", ""),
        "mentions": parse_mentions(r.get("body", "")),
        "created_at": created.isoformat() if hasattr(created, "isoformat") else created,
        "edited_at": edited.isoformat() if hasattr(edited, "isoformat") else edited,
    }
