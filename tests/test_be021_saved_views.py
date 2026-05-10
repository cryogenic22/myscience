"""BE-21 — saved-views service + endpoint tests."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest


# ════════════════════════════════════════════════════════════════════
# Migration shape
# ════════════════════════════════════════════════════════════════════

class TestMigration069:
    def test_creates_saved_views_table(self):
        path = (
            Path(__file__).parent.parent
            / "schema" / "migrations" / "069_saved_views.sql"
        )
        assert path.exists()
        sql = path.read_text(encoding="utf-8").lower()
        assert "create table" in sql and "saved_views" in sql
        for col in ("view_id", "owner_user_id", "name", "version", "state",
                    "shareable_slug", "created_at", "updated_at"):
            assert col in sql, f"missing column {col}"
        assert "create index" in sql and "owner_user_id" in sql


# ════════════════════════════════════════════════════════════════════
# Service layer
# ════════════════════════════════════════════════════════════════════

def _row(view_id="v-1", owner="u-1", name="My View", version=1,
         state=None, slug=None):
    now = datetime.now(timezone.utc)
    return {
        "view_id": view_id,
        "owner_user_id": owner,
        "name": name,
        "version": version,
        "state": state if state is not None else {"hops": 2, "centre": "drug-1"},
        "shareable_slug": slug,
        "created_at": now,
        "updated_at": now,
    }


class TestService:
    def test_list_returns_dicts(self):
        from services.saved_views import list_views
        db = MagicMock()
        db.fetch_all.return_value = [_row(), _row(view_id="v-2", name="Other")]
        out = list_views(db, owner_user_id="u-1")
        assert len(out) == 2
        assert out[0]["view_id"] == "v-1"

    def test_create_minimal(self):
        from services.saved_views import create_view
        db = MagicMock()
        db.fetch_one.return_value = _row()
        out = create_view(
            db, owner_user_id="u-1",
            name="My View", state={"hops": 2}, shareable=False,
        )
        assert out["name"] == "My View"
        assert out["shareable_slug"] is None

    def test_create_with_shareable_mints_slug(self):
        from services.saved_views import create_view
        db = MagicMock()
        # Capture the params the INSERT was called with
        captured = {}
        def fake_fetch_one(sql, params=None):
            captured["params"] = params
            return _row(slug=params[3])
        db.fetch_one.side_effect = fake_fetch_one
        out = create_view(
            db, owner_user_id="u-1",
            name="x", state={}, shareable=True,
        )
        assert captured["params"][3] is not None
        assert len(captured["params"][3]) >= 8  # slug present

    def test_create_rejects_empty_name(self):
        from services.saved_views import create_view
        db = MagicMock()
        with pytest.raises(ValueError, match="name"):
            create_view(db, owner_user_id="u-1", name="   ", state={})

    def test_create_rejects_oversized_state(self):
        from services.saved_views import create_view, MAX_STATE_BYTES
        db = MagicMock()
        big = {"k" * 10: "v" * MAX_STATE_BYTES}
        with pytest.raises(ValueError, match="state"):
            create_view(db, owner_user_id="u-1", name="x", state=big)

    def test_get_owner_scoped(self):
        from services.saved_views import get_view
        db = MagicMock()
        db.fetch_one.return_value = _row()
        out = get_view(db, view_id="v-1", owner_user_id="u-1")
        assert out["view_id"] == "v-1"
        # The SELECT must include owner check
        sql = str(db.fetch_one.call_args.args[0]).lower()
        assert "owner_user_id" in sql

    def test_get_owner_missing_returns_none(self):
        from services.saved_views import get_view
        db = MagicMock()
        db.fetch_one.return_value = None
        assert get_view(db, view_id="v-1", owner_user_id="u-1") is None

    def test_patch_bumps_version(self):
        from services.saved_views import patch_view
        db = MagicMock()
        # First fetch_one is the GET inside patch_view; second is the UPDATE RETURNING
        db.fetch_one.side_effect = [
            _row(version=3),
            _row(version=4, name="Renamed"),
        ]
        out = patch_view(db, view_id="v-1", owner_user_id="u-1", name="Renamed")
        assert out["version"] == 4

    def test_patch_unknown_returns_none(self):
        from services.saved_views import patch_view
        db = MagicMock()
        db.fetch_one.return_value = None
        assert patch_view(db, view_id="missing", owner_user_id="u-1", name="x") is None

    def test_patch_share_toggle_mints_or_clears_slug(self):
        from services.saved_views import patch_view
        db = MagicMock()
        # First call: GET returns row without slug; second: UPDATE returns row with slug
        seq = [_row(slug=None), _row(slug="abc12345")]
        db.fetch_one.side_effect = lambda sql, params=None: seq.pop(0)
        out = patch_view(db, view_id="v-1", owner_user_id="u-1", shareable=True)
        assert out["shareable_slug"] == "abc12345"

    def test_delete_returns_bool(self):
        from services.saved_views import delete_view
        db = MagicMock()
        db.fetch_one.return_value = {"view_id": "v-1"}
        assert delete_view(db, view_id="v-1", owner_user_id="u-1") is True
        db.fetch_one.return_value = None
        assert delete_view(db, view_id="v-2", owner_user_id="u-1") is False

    def test_get_by_slug_no_owner_check(self):
        from services.saved_views import get_by_slug
        db = MagicMock()
        db.fetch_one.return_value = _row(slug="my-slug")
        out = get_by_slug(db, slug="my-slug")
        assert out["shareable_slug"] == "my-slug"
        sql = str(db.fetch_one.call_args.args[0]).lower()
        assert "shareable_slug" in sql
