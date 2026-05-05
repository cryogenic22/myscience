"""SPEC-021 D2 — cursor pagination helper.

Cursor encodes (sort_value, id) tuple in base64 so the client doesn't
need to know the schema. ORDER BY uses (sort_col DESC, id DESC) for
stable ordering across ties.

Usage in a route:

    from api.pagination import paginate, PageParams

    @router.get("/things")
    def list_things(
        page: PageParams = Depends(),
        db: Database = Depends(get_db),
    ):
        sql, params = paginate(
            base_sql="SELECT id, title, created_at FROM things WHERE owner = %s",
            base_params=[user.get("id")],
            page=page,
            sort_col="created_at",
        )
        rows = db.fetch_all(sql, params)
        return page.envelope(rows, sort_col="created_at")
"""

from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from typing import Any, Optional

from fastapi import Query


_DEFAULT_PAGE_SIZE = 20
_MAX_PAGE_SIZE = 100

# sort_col / id_col are interpolated into the SQL string (not passed
# as parameters because they're identifiers, not values). Reject
# anything that isn't a plain SQL identifier to prevent injection if
# a caller ever forwards user input here.
_SQL_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _safe_ident(name: str) -> str:
    """Validate that `name` is a plain SQL identifier. Raises ValueError
    otherwise. Defensive — callers should hardcode column names."""
    if not _SQL_IDENT_RE.match(name or ""):
        raise ValueError(f"unsafe SQL identifier: {name!r}")
    return name


def _encode_cursor(sort_value: Any, row_id: Any) -> str:
    """Encode (sort_value, id) into a URL-safe base64 string."""
    payload = json.dumps({"s": str(sort_value), "i": str(row_id)},
                         separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str) -> Optional[tuple[str, str]]:
    """Decode a cursor back to (sort_value_as_str, id_as_str). Returns
    None on any decode failure (caller treats as 'no cursor')."""
    if not cursor:
        return None
    try:
        pad = "=" * ((4 - len(cursor) % 4) % 4)
        raw = base64.urlsafe_b64decode(cursor + pad).decode("utf-8")
        d = json.loads(raw)
        return str(d["s"]), str(d["i"])
    except Exception:
        return None


@dataclass
class PageParams:
    cursor: Optional[str] = None
    limit: int = _DEFAULT_PAGE_SIZE

    def envelope(self, rows: list[dict], sort_col: str = "created_at") -> dict:
        """Wrap query results in the standard pagination envelope.

        Returns:
            {
                "items": rows,
                "next_cursor": "<base64 or None>",
                "count": <len(rows)>,
                "limit": <effective limit>,
            }

        We assume the route asked for `limit + 1` and dropped the
        overflow row before calling this — so `len(rows) == limit`
        means there's a next page.
        """
        next_cursor = None
        if len(rows) >= self.limit and rows:
            last = rows[-1]
            next_cursor = _encode_cursor(last.get(sort_col), last.get("id"))
        return {
            "items": rows,
            "next_cursor": next_cursor,
            "count": len(rows),
            "limit": self.limit,
        }


def page_params_dep(
    cursor: Optional[str] = Query(default=None, description="Opaque cursor from previous page"),
    limit: int = Query(default=_DEFAULT_PAGE_SIZE, ge=1, le=_MAX_PAGE_SIZE,
                       description=f"Page size (1..{_MAX_PAGE_SIZE})"),
) -> PageParams:
    """FastAPI dependency factory. Use as: `page = Depends(page_params_dep)`."""
    return PageParams(cursor=cursor, limit=limit)


def paginate(
    *,
    base_sql: str,
    base_params: list[Any],
    page: PageParams,
    sort_col: str = "created_at",
    id_col: str = "id",
) -> tuple[str, list[Any]]:
    """Compose a paginated SQL query.

    `base_sql` should NOT contain ORDER BY or LIMIT — we add them.
    Optionally include `WHERE ...` for the route's filters; the cursor
    condition is appended via AND.

    `sort_col` and `id_col` are SQL identifiers (column names) that
    get interpolated into the query string. They MUST be hardcoded
    constants — `_safe_ident` defensively raises if they look like
    anything other than a plain identifier.

    Returns (sql, params) ready to execute.
    """
    sort_col = _safe_ident(sort_col)
    id_col = _safe_ident(id_col)

    params = list(base_params)
    cursor_decoded = _decode_cursor(page.cursor) if page.cursor else None

    parts = [base_sql.rstrip().rstrip(";")]

    if cursor_decoded is not None:
        sort_value, row_id = cursor_decoded
        # Tuple comparison: (sort, id) < cursor ensures strict pagination
        # even when sort_col has ties. Postgres supports this directly.
        connector = "AND" if " WHERE " in base_sql.upper() else "WHERE"
        parts.append(
            f"{connector} ({sort_col}, {id_col}::text) < (%s, %s)"
        )
        params.extend([sort_value, row_id])

    parts.append(f"ORDER BY {sort_col} DESC, {id_col} DESC")
    # Fetch +1 to detect "is there a next page" without a separate count
    parts.append("LIMIT %s")
    params.append(page.limit + 1)

    return " ".join(parts), params
