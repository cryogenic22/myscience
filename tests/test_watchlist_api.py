"""SPEC-020 — Watchlist API tests.

Endpoints:
  GET     /watchlist          anon → empty; viewer+ → own entries (anon read must not 401,
                              or the CI cockpit's load-time call trips the frontend's global
                              session-expired handler and breaks multiple pages)
  POST    /watchlist          viewer+   add (idempotent on user/type/id)
  DELETE  /watchlist/{id}     viewer+   remove (404 if not yours)
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent


# ────────────────────────────────────────────────────────────────────
# Fake DB — users + watchlist_entries
# ────────────────────────────────────────────────────────────────────

def _make_db():
    from services.auth import hash_password

    users = {
        "viewer@demo.market-zero.io": {
            "id": "uuid-viewer", "email": "viewer@demo.market-zero.io",
            "password_hash": hash_password("demo"), "role": "viewer",
            "is_active": True,
        },
        "uploader@demo.market-zero.io": {
            "id": "uuid-uploader", "email": "uploader@demo.market-zero.io",
            "password_hash": hash_password("demo"), "role": "uploader",
            "is_active": True,
        },
        "enterprise@demo.market-zero.io": {
            "id": "uuid-enterprise", "email": "enterprise@demo.market-zero.io",
            "password_hash": hash_password("demo"), "role": "enterprise",
            "is_active": True,
        },
    }
    # In-memory watchlist store: list of dicts
    entries: list[dict] = []
    next_id = [1]

    def fake_fetch_one(sql, params=None):
        s = (sql or "").lower()
        if "from users" in s and params:
            if "where lower(email)" in s or "where email" in s:
                return users.get(str(params[0]).lower())
            if "where id::text" in s or "where id =" in s:
                for u in users.values():
                    if u["id"] == params[0]:
                        return u
                return None
        if "from watchlist_entries" in s and params:
            # Lookup by id (DELETE flow)
            if "where id" in s and "where user_id" not in s:
                eid = str(params[0])
                for e in entries:
                    if e["id"] == eid:
                        return dict(e)
                return None
            # Idempotent lookup by (user_id, entity_type, entity_id) for POST
            if "where user_id" in s and "entity_type" in s and "entity_id" in s:
                user_id, etype, eid = params[0], params[1], params[2]
                for e in entries:
                    if (e["user_id"] == user_id and e["entity_type"] == etype
                            and e["entity_id"] == eid):
                        return dict(e)
                return None
        return None

    def fake_fetch_all(sql, params=None):
        s = (sql or "").lower()
        if "from watchlist_entries" in s and params:
            user_id = params[0]
            return [dict(e) for e in entries if e["user_id"] == user_id]
        return []

    def fake_execute(sql, params=None):
        s = (sql or "").lower()
        if "insert into watchlist_entries" in s and params:
            user_id, etype, eid, label = params[0], params[1], params[2], params[3]
            # Don't duplicate (UNIQUE constraint)
            for e in entries:
                if (e["user_id"] == user_id and e["entity_type"] == etype
                        and e["entity_id"] == eid):
                    return None
            entries.append({
                "id": f"wl-{next_id[0]}",
                "user_id": user_id,
                "entity_type": etype,
                "entity_id": eid,
                "label": label,
                "created_at": datetime.now(timezone.utc),
            })
            next_id[0] += 1
            return None
        if "delete from watchlist_entries" in s and params:
            eid = params[0]
            for i, e in enumerate(entries):
                if e["id"] == eid:
                    entries.pop(i)
                    return None
            return None
        return None

    db = MagicMock()
    db.fetch_one.side_effect = fake_fetch_one
    db.fetch_all.side_effect = fake_fetch_all
    db.execute.side_effect = fake_execute
    return db, entries


def _client(db):
    from fastapi.testclient import TestClient
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


# ────────────────────────────────────────────────────────────────────
# Module + routes
# ────────────────────────────────────────────────────────────────────

def test_watchlist_route_module_exists():
    assert (REPO_ROOT / "api" / "routes" / "watchlist.py").exists()


def test_watchlist_routes_registered():
    from api.app import create_app
    app = create_app()
    paths = {getattr(r, "path", None) for r in app.routes}
    assert any(p and p.endswith("/watchlist") for p in paths)


# ────────────────────────────────────────────────────────────────────
# GET /watchlist
# ────────────────────────────────────────────────────────────────────

def test_list_endpoint_returns_empty_for_anonymous():
    """Anonymous GET must be 200 with an empty list — NOT 401. A 401 here trips the frontend's
    session-expired handler (clears the token, fires mz:auth-expired) on every CI-cockpit load,
    which broke multiple pages for logged-out visitors. Writes stay auth-gated (below)."""
    db, _ = _make_db()
    r = _client(db).get("/watchlist")
    assert r.status_code == 200, r.text
    assert r.json() == {"entries": []}


def test_list_endpoint_returns_200_for_viewer():
    db, _ = _make_db()
    client = _client(db)
    tok = _login(client, "viewer@demo.market-zero.io")
    r = client.get("/watchlist", headers=_hdr(tok))
    assert r.status_code == 200, r.text
    body = r.json()
    assert "entries" in body
    assert body["entries"] == []


def test_list_endpoint_returns_only_users_own_entries():
    db, entries = _make_db()
    client = _client(db)
    # Viewer adds one
    vt = _login(client, "viewer@demo.market-zero.io")
    client.post("/watchlist", headers=_hdr(vt),
                json={"entity_type": "company", "entity_id": "ent-pfizer", "label": "Pfizer"})
    # Uploader adds one
    ut = _login(client, "uploader@demo.market-zero.io")
    client.post("/watchlist", headers=_hdr(ut),
                json={"entity_type": "company", "entity_id": "ent-amgen", "label": "Amgen"})
    # Viewer should see only their own
    r = client.get("/watchlist", headers=_hdr(vt))
    body = r.json()
    assert len(body["entries"]) == 1
    assert body["entries"][0]["entity_id"] == "ent-pfizer"


# ────────────────────────────────────────────────────────────────────
# POST /watchlist
# ────────────────────────────────────────────────────────────────────

def test_add_endpoint_401_anonymous():
    db, _ = _make_db()
    r = _client(db).post("/watchlist",
                          json={"entity_type": "company", "entity_id": "x"})
    assert r.status_code == 401


def test_add_endpoint_201_creates_entry():
    db, entries = _make_db()
    client = _client(db)
    tok = _login(client, "viewer@demo.market-zero.io")
    r = client.post("/watchlist", headers=_hdr(tok),
                    json={"entity_type": "drug", "entity_id": "drug-semaglutide",
                          "label": "Semaglutide"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["entity_id"] == "drug-semaglutide"
    assert body["label"] == "Semaglutide"
    assert len(entries) == 1


def test_add_endpoint_idempotent_on_duplicate():
    db, entries = _make_db()
    client = _client(db)
    tok = _login(client, "viewer@demo.market-zero.io")
    body = {"entity_type": "drug", "entity_id": "drug-semaglutide", "label": "Sema"}

    r1 = client.post("/watchlist", headers=_hdr(tok), json=body)
    assert r1.status_code == 201
    first_id = r1.json()["id"]

    r2 = client.post("/watchlist", headers=_hdr(tok), json=body)
    assert r2.status_code in (200, 201), r2.text
    assert r2.json()["id"] == first_id
    assert len(entries) == 1


# ────────────────────────────────────────────────────────────────────
# DELETE /watchlist/{id}
# ────────────────────────────────────────────────────────────────────

def test_delete_endpoint_204_for_own_entry():
    db, entries = _make_db()
    client = _client(db)
    tok = _login(client, "viewer@demo.market-zero.io")
    r1 = client.post("/watchlist", headers=_hdr(tok),
                     json={"entity_type": "drug", "entity_id": "x", "label": "X"})
    eid = r1.json()["id"]
    r2 = client.delete(f"/watchlist/{eid}", headers=_hdr(tok))
    assert r2.status_code == 204
    assert len(entries) == 0


def test_delete_endpoint_404_for_other_users_entry():
    db, _ = _make_db()
    client = _client(db)
    # Uploader creates
    ut = _login(client, "uploader@demo.market-zero.io")
    r1 = client.post("/watchlist", headers=_hdr(ut),
                     json={"entity_type": "drug", "entity_id": "x", "label": "X"})
    eid = r1.json()["id"]
    # Viewer tries to delete uploader's entry
    vt = _login(client, "viewer@demo.market-zero.io")
    r2 = client.delete(f"/watchlist/{eid}", headers=_hdr(vt))
    assert r2.status_code == 404


def test_delete_endpoint_404_for_unknown_id():
    db, _ = _make_db()
    client = _client(db)
    tok = _login(client, "viewer@demo.market-zero.io")
    r = client.delete("/watchlist/does-not-exist", headers=_hdr(tok))
    assert r.status_code == 404
