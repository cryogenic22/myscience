"""SPEC-021 D2 — cursor pagination helper tests."""

from __future__ import annotations

import pytest

from api import pagination as p


def test_encode_decode_roundtrip():
    cursor = p._encode_cursor("2026-05-04T00:00:00", "abc-123")
    decoded = p._decode_cursor(cursor)
    assert decoded == ("2026-05-04T00:00:00", "abc-123")


def test_decode_invalid_returns_none():
    assert p._decode_cursor("garbage!@#$") is None
    assert p._decode_cursor("") is None
    assert p._decode_cursor(None) is None


def test_paginate_no_cursor_adds_order_and_limit():
    page = p.PageParams(cursor=None, limit=20)
    sql, params = p.paginate(
        base_sql="SELECT id, title, created_at FROM things WHERE owner = %s",
        base_params=["user-1"],
        page=page,
        sort_col="created_at",
    )
    assert "ORDER BY created_at DESC" in sql
    assert "LIMIT %s" in sql
    # +1 for page-overflow check
    assert params == ["user-1", 21]


def test_paginate_with_cursor_adds_tuple_filter():
    cursor = p._encode_cursor("2026-05-01", "xyz")
    page = p.PageParams(cursor=cursor, limit=10)
    sql, params = p.paginate(
        base_sql="SELECT id, created_at FROM things WHERE owner = %s",
        base_params=["user-1"],
        page=page,
        sort_col="created_at",
    )
    assert "(created_at, id::text) <" in sql
    assert "AND" in sql  # appended after WHERE
    assert "2026-05-01" in params
    assert "xyz" in params


def test_paginate_no_where_uses_where_for_cursor():
    cursor = p._encode_cursor("2026-05-01", "xyz")
    page = p.PageParams(cursor=cursor, limit=10)
    sql, _ = p.paginate(
        base_sql="SELECT id, created_at FROM things",
        base_params=[],
        page=page,
    )
    # No WHERE in base → cursor uses WHERE not AND
    assert " WHERE (created_at, id::text) <" in sql


def test_envelope_emits_next_cursor_when_full_page():
    page = p.PageParams(cursor=None, limit=2)
    rows = [
        {"id": "a", "created_at": "2026-05-04"},
        {"id": "b", "created_at": "2026-05-03"},
    ]
    env = page.envelope(rows, sort_col="created_at")
    assert env["count"] == 2
    assert env["next_cursor"] is not None
    # Decode to verify it points at the last row
    decoded = p._decode_cursor(env["next_cursor"])
    assert decoded == ("2026-05-03", "b")


def test_envelope_no_cursor_when_short_page():
    page = p.PageParams(cursor=None, limit=10)
    rows = [{"id": "a", "created_at": "2026-05-04"}]
    env = page.envelope(rows)
    assert env["next_cursor"] is None


def test_safe_ident_rejects_injection_attempt():
    """Defensive — sort_col/id_col are interpolated into SQL, so they
    must validate as identifiers. Any attempt to inject SQL via these
    parameters raises ValueError."""
    page = p.PageParams(cursor=None, limit=10)
    with pytest.raises(ValueError, match="unsafe SQL identifier"):
        p.paginate(
            base_sql="SELECT id FROM things",
            base_params=[],
            page=page,
            sort_col="created_at; DROP TABLE things;--",
        )
    with pytest.raises(ValueError, match="unsafe SQL identifier"):
        p.paginate(
            base_sql="SELECT id FROM things",
            base_params=[],
            page=page,
            id_col="id) UNION SELECT 1--",
        )


def test_safe_ident_accepts_valid_names():
    page = p.PageParams(cursor=None, limit=5)
    sql, _ = p.paginate(
        base_sql="SELECT id, my_column FROM things",
        base_params=[],
        page=page,
        sort_col="my_column",
        id_col="id",
    )
    assert "ORDER BY my_column DESC, id DESC" in sql
