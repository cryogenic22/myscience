"""UX02 / PB-UX02 — generic entity comments service."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from services.entity_comments import add_comment, list_comments, parse_mentions

NOW = datetime(2026, 6, 2, tzinfo=timezone.utc)


def test_parse_mentions_dedupes_and_preserves_order():
    assert parse_mentions("hey @riya and @priya, cc @riya") == ["riya", "priya"]
    assert parse_mentions("no mentions here") == []


def test_add_comment_rejects_empty_body():
    with pytest.raises(ValueError):
        add_comment(MagicMock(), "brief", "b1", "   ")


def test_add_comment_persists_and_returns_camel_row():
    db = MagicMock()
    db.fetch_one = MagicMock(return_value={
        "id": "c1", "target_type": "brief", "target_id": "b1",
        "author_user_id": "u1", "author_display_name": "Riya",
        "body": "ping @priya", "created_at": NOW, "edited_at": None,
    })
    out = add_comment(db, "brief", "b1", "ping @priya", author_user_id="u1", author_display_name="Riya")
    assert out["id"] == "c1"
    assert out["mentions"] == ["priya"]
    assert "INSERT INTO entity_comments" in db.fetch_one.call_args.args[0]


def test_list_comments_returns_thread():
    db = MagicMock()
    db.fetch_all = MagicMock(return_value=[
        {"id": "c1", "target_type": "scenario", "target_id": "s1", "author_user_id": None,
         "author_display_name": "Anon", "body": "first", "created_at": NOW, "edited_at": None},
    ])
    out = list_comments(db, "scenario", "s1")
    assert len(out) == 1 and out[0]["body"] == "first"
    assert db.fetch_all.call_args.args[1] == ["scenario", "s1"]
