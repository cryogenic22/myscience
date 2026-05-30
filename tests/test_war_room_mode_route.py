"""W1 — PATCH /war-rooms/{id}/mode route tests.

Focused on the scenario-mode endpoint surface (not the full war-room API,
which has its own suite in test_war_room_api.py). Uses a narrow fake DB
that backs only the fields this endpoint touches: room ownership, the
mode column, and the round-count probe.

Covers:
- Default mode in GET payload (additive to the existing room serializer)
- 401 unauthenticated
- 403 non-owner
- 200 owner with valid mode (response shape + DB write)
- 400 invalid mode string (no DB write attempted)
- 404 missing room (no DB write attempted)
- Idempotent same-mode transition (no DB write)
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from fastapi.testclient import TestClient


# ──────────────────────────────────────────────────────────────────
# Fake DB — minimal: users for /auth/login, rooms with mode + owner.
# ──────────────────────────────────────────────────────────────────

def _make_db(rooms=None):
    from services.auth import hash_password

    users = {
        "owner@demo.market-zero.io": {
            "id": "uuid-owner",
            "email": "owner@demo.market-zero.io",
            "password_hash": hash_password("demo"),
            "role": "viewer",
            "is_active": True,
        },
        "intruder@demo.market-zero.io": {
            "id": "uuid-intruder",
            "email": "intruder@demo.market-zero.io",
            "password_hash": hash_password("demo"),
            "role": "viewer",
            "is_active": True,
        },
    }
    rooms = rooms or {}
    write_log: list[tuple[str, list]] = []

    def fetch_one(sql, params=None):
        s = (sql or "").lower()
        if "from users" in s and params:
            if "where lower(email)" in s or "where email" in s:
                return users.get(str(params[0]).lower())
            if "where id::text" in s or "where id =" in s:
                for u in users.values():
                    if u["id"] == params[0]:
                        return u
                return None
        # COUNT(*) probe used by load_scenario_state
        if "count" in s and "war_room_rounds" in s:
            return {"count": 0}
        # SELECT mode, mode_changed_at FROM war_rooms — narrow query used
        # by load_scenario_state. Must match BEFORE the full-room branch
        # (which also references mode now that _ROOM_COLS includes it).
        # Disambiguate on the absence of 'title' (the broad SELECT always
        # has it; the narrow one does not).
        if (
            "from war_rooms" in s
            and "id::text" in s
            and "mode" in s
            and "title" not in s
            and params
        ):
            room = rooms.get(str(params[0]))
            if not room:
                return None
            return {
                "mode": room.get("mode", "guided"),
                "mode_changed_at": room.get("mode_changed_at"),
            }
        # Full-room SELECT (the route's ownership check)
        if "from war_rooms" in s and "id::text" in s and params:
            room = rooms.get(str(params[0]))
            return dict(room) if room else None
        return None

    def execute(sql, params=None):
        s = (sql or "").lower()
        write_log.append((s, list(params or [])))
        if "update war_rooms" in s and "mode =" in s and params:
            room_id = str(params[-1])
            if room_id in rooms:
                rooms[room_id]["mode"] = params[0]
                rooms[room_id]["mode_changed_at"] = datetime.now(timezone.utc)
        return None

    def fetch_all(sql, params=None):
        return []

    db = MagicMock()
    db.fetch_one.side_effect = fetch_one
    db.fetch_all.side_effect = fetch_all
    db.execute.side_effect = execute
    return db, rooms, write_log


def _seed_room(rooms, *, room_id="wr-1", owner="uuid-owner", mode="guided"):
    rooms[room_id] = {
        "id": room_id,
        "title": "Pfizer guidance scenario",
        "owner_user_id": owner,
        "scenario_question": "What if Pfizer raises FY guidance?",
        "primary_entity_type": "company",
        "primary_entity_id": "ent-pfizer",
        "primary_entity_name": "Pfizer Inc.",
        "source_signal_id": None,
        "game_phase": "launch",
        "status": "active",
        "mode": mode,
        "mode_changed_at": None,
        "archived_at": None,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    return rooms[room_id]


def _client(db):
    from api.app import create_app
    from api.deps import get_db, get_llm
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_llm] = lambda: None
    return TestClient(app)


def _login(client, email):
    r = client.post("/auth/login", json={"email": email, "password": "demo"})
    return r.json().get("access_token", "") if r.status_code == 200 else ""


def _hdr(tok):
    return {"Authorization": f"Bearer {tok}"} if tok else {}


# ──────────────────────────────────────────────────────────────────
# Tests — the route surface
# ──────────────────────────────────────────────────────────────────

def test_mode_route_is_registered():
    from api.app import create_app
    app = create_app()
    paths = {getattr(r, "path", None) for r in app.routes}
    assert any(p and p.endswith("/war-rooms/{room_id}/mode") for p in paths)


def test_get_room_payload_includes_mode_and_mode_changed_at():
    db, rooms, _ = _make_db()
    _seed_room(rooms, mode="autonomous")
    r = _client(db).get("/war-rooms/wr-1")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mode"] == "autonomous"
    # mode_changed_at is None for a seeded room — key must still be present.
    assert "mode_changed_at" in body


def test_patch_mode_401_anonymous():
    db, rooms, _ = _make_db()
    _seed_room(rooms)
    r = _client(db).patch("/war-rooms/wr-1/mode", json={"mode": "autonomous"})
    assert r.status_code == 401


def test_patch_mode_403_non_owner():
    db, rooms, _ = _make_db()
    _seed_room(rooms, owner="uuid-owner")
    client = _client(db)
    tok = _login(client, "intruder@demo.market-zero.io")
    r = client.patch(
        "/war-rooms/wr-1/mode",
        headers=_hdr(tok),
        json={"mode": "autonomous"},
    )
    assert r.status_code == 403


def test_patch_mode_404_missing_room():
    db, rooms, write_log = _make_db()
    client = _client(db)
    tok = _login(client, "owner@demo.market-zero.io")
    r = client.patch(
        "/war-rooms/missing/mode",
        headers=_hdr(tok),
        json={"mode": "autonomous"},
    )
    assert r.status_code == 404
    # No transition attempt → no UPDATE issued.
    assert not any("update war_rooms" in s for s, _ in write_log)


def test_patch_mode_400_invalid_mode():
    db, rooms, write_log = _make_db()
    _seed_room(rooms)
    client = _client(db)
    tok = _login(client, "owner@demo.market-zero.io")
    r = client.patch(
        "/war-rooms/wr-1/mode",
        headers=_hdr(tok),
        json={"mode": "nope"},
    )
    assert r.status_code == 400
    # Error message must guide the operator to the valid set.
    body_msg = r.json().get("detail", "")
    for v in ("guided", "autonomous", "game_theoretic"):
        assert v in body_msg
    # No UPDATE should have been issued for an invalid mode.
    assert not any("update war_rooms" in s for s, _ in write_log)


def test_patch_mode_200_valid_transition_writes_and_returns_state():
    db, rooms, write_log = _make_db()
    _seed_room(rooms, mode="guided")
    client = _client(db)
    tok = _login(client, "owner@demo.market-zero.io")
    r = client.patch(
        "/war-rooms/wr-1/mode",
        headers=_hdr(tok),
        json={"mode": "autonomous"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["war_room_id"] == "wr-1"
    assert body["mode"] == "autonomous"
    assert body["round_count"] == 0
    assert body["mode_changed_at"] is not None
    # Exactly one UPDATE on war_rooms (mode column).
    updates = [s for s, _ in write_log if "update war_rooms" in s and "mode =" in s]
    assert len(updates) == 1, f"expected 1 UPDATE, got {len(updates)}"


def test_patch_mode_idempotent_same_mode_no_db_write():
    db, rooms, write_log = _make_db()
    _seed_room(rooms, mode="autonomous")
    client = _client(db)
    tok = _login(client, "owner@demo.market-zero.io")
    r = client.patch(
        "/war-rooms/wr-1/mode",
        headers=_hdr(tok),
        json={"mode": "autonomous"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["mode"] == "autonomous"
    # Same-mode → no UPDATE.
    updates = [s for s, _ in write_log if "update war_rooms" in s and "mode =" in s]
    assert len(updates) == 0


def test_patch_mode_accepts_all_three_modes():
    """Smoke — each of the three valid modes makes it through."""
    for target in ("guided", "autonomous", "game_theoretic"):
        db, rooms, _ = _make_db()
        # Start at a different mode so the transition is not a no-op.
        start = "guided" if target != "guided" else "autonomous"
        _seed_room(rooms, mode=start)
        client = _client(db)
        tok = _login(client, "owner@demo.market-zero.io")
        r = client.patch(
            "/war-rooms/wr-1/mode",
            headers=_hdr(tok),
            json={"mode": target},
        )
        assert r.status_code == 200, f"{target}: {r.text}"
        assert r.json()["mode"] == target
