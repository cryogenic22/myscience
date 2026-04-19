"""SPEC_018 — Role-gating end-to-end tests.

Tests the FastAPI dependency injection: anonymous gets 401 on protected routes,
wrong role gets 403, right role passes. Login + me endpoints round-trip.

Uses app.dependency_overrides to mock DB so tests run without a live Postgres.
"""

from __future__ import annotations

import io
import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent


# ────────────────────────────────────────────────────────────────────
# Helpers — fake DB representing 3 demo users
# ────────────────────────────────────────────────────────────────────

def _make_demo_db():
    """Build a MagicMock DB that returns demo users by email."""
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

    def fake_fetch_one(sql, params=None):
        sql_lower = (sql or "").lower()
        if "from users" not in sql_lower:
            return None
        if not params:
            return None
        # Discriminate by WHERE clause (not SELECT) — login uses
        # `WHERE LOWER(email) = %s`, get_current_user uses `WHERE id::text = %s`.
        if "where lower(email)" in sql_lower or "where email" in sql_lower:
            return users.get(str(params[0]).lower())
        if "where id::text" in sql_lower or "where id =" in sql_lower:
            for u in users.values():
                if u["id"] == params[0]:
                    return u
            return None
        return None

    db = MagicMock()
    db.fetch_one.side_effect = fake_fetch_one
    db.execute = MagicMock()  # for last_login_at update
    return db


def _client_with_demo_db():
    """TestClient with DB dep overridden to demo users + LLM + pipeline stubbed."""
    from fastapi.testclient import TestClient
    from api.app import create_app
    from api.deps import get_db, get_llm, get_integration_pipeline

    app = create_app()
    db = _make_demo_db()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_llm] = lambda: None
    # Stub pipeline so /upload doesn't try to reach a real DB through it
    pipeline_mock = MagicMock()
    pipeline_mock.run.return_value = MagicMock(
        summary=lambda: {
            "etl_run_id": "test-run", "source": "user_document",
            "processed": 1, "inserted": 1, "updated": 0,
            "unchanged": 0, "skipped": 0, "failed": 0,
            "links_created": 0, "hitl_items": 0,
            "avg_quality": None, "errors": [], "duration_seconds": 0.01,
        },
    )
    app.dependency_overrides[get_integration_pipeline] = lambda: pipeline_mock
    return TestClient(app), db


def _login(client, email: str, password: str = "demo") -> str:
    """Return bearer token for an email (or empty string on failure)."""
    r = client.post("/auth/login", json={"email": email, "password": password})
    if r.status_code != 200:
        return ""
    return r.json().get("access_token", "")


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"} if token else {}


# ────────────────────────────────────────────────────────────────────
# Module / route registration
# ────────────────────────────────────────────────────────────────────

def test_auth_route_module_exists():
    assert (REPO_ROOT / "api" / "routes" / "auth.py").exists()


def test_auth_routes_registered():
    from api.app import create_app
    app = create_app()
    paths = {getattr(r, "path", None) for r in app.routes}
    assert any(p and p.endswith("/auth/login") for p in paths)
    assert any(p and p.endswith("/auth/me") for p in paths)


# ────────────────────────────────────────────────────────────────────
# /auth/login endpoint
# ────────────────────────────────────────────────────────────────────

def test_login_returns_token_for_valid_credentials():
    client, _ = _client_with_demo_db()
    r = client.post("/auth/login", json={
        "email": "viewer@demo.market-zero.io",
        "password": "demo",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("access_token")
    assert body.get("token_type", "").lower() == "bearer"
    assert body.get("role") == "viewer"


def test_login_returns_401_for_invalid_password():
    client, _ = _client_with_demo_db()
    r = client.post("/auth/login", json={
        "email": "viewer@demo.market-zero.io",
        "password": "wrong",
    })
    assert r.status_code == 401


def test_login_returns_401_for_unknown_email():
    client, _ = _client_with_demo_db()
    r = client.post("/auth/login", json={
        "email": "nobody@nowhere.io",
        "password": "demo",
    })
    assert r.status_code == 401


# ────────────────────────────────────────────────────────────────────
# /auth/me endpoint
# ────────────────────────────────────────────────────────────────────

def test_me_endpoint_requires_token():
    client, _ = _client_with_demo_db()
    r = client.get("/auth/me")
    assert r.status_code == 401


def test_me_endpoint_returns_user_info_with_valid_token():
    client, _ = _client_with_demo_db()
    token = _login(client, "uploader@demo.market-zero.io")
    assert token, "login should succeed"
    r = client.get("/auth/me", headers=_auth_headers(token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("email") == "uploader@demo.market-zero.io"
    assert body.get("role") == "uploader"


def test_me_endpoint_rejects_garbage_token():
    client, _ = _client_with_demo_db()
    r = client.get("/auth/me", headers=_auth_headers("not-a-real-token"))
    assert r.status_code == 401


# ────────────────────────────────────────────────────────────────────
# /upload role gate
# ────────────────────────────────────────────────────────────────────

def test_upload_returns_401_anonymous():
    client, _ = _client_with_demo_db()
    r = client.post(
        "/upload",
        files={"file": ("test.txt", io.BytesIO(b"semaglutide"), "text/plain")},
    )
    assert r.status_code == 401


def test_upload_returns_403_for_viewer_role():
    """Viewer doesn't have upload permission → 403."""
    client, _ = _client_with_demo_db()
    token = _login(client, "viewer@demo.market-zero.io")
    assert token
    r = client.post(
        "/upload",
        headers=_auth_headers(token),
        files={"file": ("test.txt", io.BytesIO(b"semaglutide"), "text/plain")},
    )
    assert r.status_code == 403


def test_upload_returns_200_for_uploader_role():
    client, _ = _client_with_demo_db()
    token = _login(client, "uploader@demo.market-zero.io")
    assert token
    r = client.post(
        "/upload",
        headers=_auth_headers(token),
        files={"file": ("test.txt", io.BytesIO(b"semaglutide"), "text/plain")},
    )
    assert r.status_code == 200, r.text


def test_upload_works_for_enterprise_role_via_hierarchy():
    """Enterprise role satisfies uploader requirement (hierarchy)."""
    client, _ = _client_with_demo_db()
    token = _login(client, "enterprise@demo.market-zero.io")
    assert token
    r = client.post(
        "/upload",
        headers=_auth_headers(token),
        files={"file": ("test.txt", io.BytesIO(b"semaglutide"), "text/plain")},
    )
    assert r.status_code == 200, r.text


# ────────────────────────────────────────────────────────────────────
# Static guard — regression-proof that the route stays gated
# ────────────────────────────────────────────────────────────────────

def test_static_check_upload_route_has_role_gate():
    src = (REPO_ROOT / "api" / "routes" / "upload.py").read_text(encoding="utf-8")
    has_gate = re.search(
        r"require_role\s*\(\s*['\"]uploader['\"]\s*\)",
        src,
    )
    assert has_gate, (
        "POST /upload must be gated with require_role('uploader'). "
        "Removing this gate without updating SPEC_018 is a security regression."
    )


def test_static_check_login_route_does_not_log_passwords():
    """Defensive: never log raw passwords."""
    src = (REPO_ROOT / "api" / "routes" / "auth.py").read_text(encoding="utf-8")
    # Look for log statements that include password
    bad = re.search(
        r"(?:logger|logging|print|log)\.[a-z]+\([^)]*password",
        src, re.IGNORECASE,
    )
    assert bad is None, (
        "auth.py must never log raw passwords. Found suspicious pattern."
    )
