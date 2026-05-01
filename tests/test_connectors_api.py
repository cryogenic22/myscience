"""SPEC-019 — Connector management API tests.

Endpoints:
  GET    /connectors                   — anonymous, list
  GET    /connectors/{key}             — anonymous, dossier
  POST   /connectors/{key}/health-check — uploader+, calls connector.health_check()
  PUT    /connectors/{key}/config      — enterprise, mutates connector_config
  POST   /connectors/{key}/run         — uploader if auto_approve, else enterprise

DB + connector are mocked; no live Postgres or upstream API calls.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent


# ────────────────────────────────────────────────────────────────────
# Fake DB — combines users (for auth) + connector_config (for SPEC_019)
# ────────────────────────────────────────────────────────────────────

def _make_combined_db(*, configs: dict | None = None):
    """Fake DB that handles both users (auth) and connector_config (SPEC_019)
    in the same fetch_one router."""
    from services.auth import hash_password

    configs = configs or {}
    # Mutable so PUT can modify
    config_store: dict = dict(configs)
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

        # users — discriminate by WHERE clause
        if "from users" in sql_lower and params:
            if "where lower(email)" in sql_lower or "where email" in sql_lower:
                return users.get(str(params[0]).lower())
            if "where id::text" in sql_lower or "where id =" in sql_lower:
                for u in users.values():
                    if u["id"] == params[0]:
                        return u
                return None

        # connector_config
        if "from connector_config" in sql_lower and params:
            key = params[0]
            row = config_store.get(key)
            if not row:
                return None
            return {
                "source_key": key,
                "enabled": row.get("enabled", True),
                "auto_approve_runs": row.get("auto_approve_runs", False),
                "manual_only": row.get("manual_only", False),
                "notes": row.get("notes"),
            }

        return None

    def fake_fetch_all(sql, params=None):
        return []

    def fake_execute(sql, params=None):
        sql_lower = (sql or "").lower()
        # Capture INSERT/UPDATE on connector_config so PUT round-trips
        if "into connector_config" in sql_lower and params:
            key = params[0]
            config_store[key] = {
                "enabled": params[1] if len(params) > 1 else True,
                "auto_approve_runs": params[2] if len(params) > 2 else False,
                "manual_only": params[3] if len(params) > 3 else False,
                "notes": params[4] if len(params) > 4 else None,
            }
        return None

    db = MagicMock()
    db.fetch_one.side_effect = fake_fetch_one
    db.fetch_all.side_effect = fake_fetch_all
    db.execute.side_effect = fake_execute
    return db, config_store


def _client_with(db):
    """Build a TestClient with DB and LLM stubbed."""
    from fastapi.testclient import TestClient
    from api.app import create_app
    from api.deps import get_db, get_llm

    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_llm] = lambda: None
    return TestClient(app)


def _login(client, email: str) -> str:
    r = client.post("/auth/login", json={"email": email, "password": "demo"})
    if r.status_code != 200:
        return ""
    return r.json().get("access_token", "")


def _hdr(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"} if tok else {}


# ────────────────────────────────────────────────────────────────────
# Module exists + routes registered
# ────────────────────────────────────────────────────────────────────

def test_connectors_route_module_exists():
    assert (REPO_ROOT / "api" / "routes" / "connectors.py").exists()


def test_connectors_routes_registered():
    from api.app import create_app
    app = create_app()
    paths = {getattr(r, "path", None) for r in app.routes}
    assert any(p and p.endswith("/connectors") for p in paths)
    assert any(p and "/connectors/" in (p or "") for p in paths)


# ────────────────────────────────────────────────────────────────────
# GET /connectors — anonymous, list
# ────────────────────────────────────────────────────────────────────

def test_list_endpoint_returns_200_anonymous():
    db, _ = _make_combined_db()
    client = _client_with(db)
    r = client.get("/connectors")
    assert r.status_code == 200, r.text


def test_list_endpoint_response_shape():
    db, _ = _make_combined_db()
    client = _client_with(db)
    r = client.get("/connectors")
    body = r.json()
    assert "connectors" in body
    assert isinstance(body["connectors"], list)
    assert len(body["connectors"]) > 0
    sample = body["connectors"][0]
    for field in ("source_key", "label", "enabled", "schedule"):
        assert field in sample, f"connector item missing {field}"


# ────────────────────────────────────────────────────────────────────
# GET /connectors/{key} — anonymous, dossier
# ────────────────────────────────────────────────────────────────────

def test_dossier_endpoint_returns_200_anonymous():
    db, _ = _make_combined_db()
    client = _client_with(db)
    r = client.get("/connectors/fda_orange_book")
    assert r.status_code == 200, r.text


def test_dossier_endpoint_404_for_unknown_key():
    db, _ = _make_combined_db()
    client = _client_with(db)
    r = client.get("/connectors/not_a_real_source")
    assert r.status_code == 404


# ────────────────────────────────────────────────────────────────────
# POST /connectors/{key}/health-check — uploader+
# ────────────────────────────────────────────────────────────────────

def test_health_check_endpoint_401_anonymous():
    db, _ = _make_combined_db()
    client = _client_with(db)
    r = client.post("/connectors/fda_orange_book/health-check")
    assert r.status_code == 401


def test_health_check_endpoint_403_viewer():
    db, _ = _make_combined_db()
    client = _client_with(db)
    tok = _login(client, "viewer@demo.market-zero.io")
    r = client.post(
        "/connectors/fda_orange_book/health-check",
        headers=_hdr(tok),
    )
    assert r.status_code == 403


def test_health_check_endpoint_200_uploader_calls_health_check():
    """Uploader role can health-check; the connector's health_check() must run."""
    from connectors.base import HealthCheckResult, SourceType

    db, _ = _make_combined_db()
    client = _client_with(db)
    tok = _login(client, "uploader@demo.market-zero.io")

    fake_connector = MagicMock()
    fake_connector.health_check.return_value = HealthCheckResult(
        healthy=True,
        source_type=SourceType.FDA_ORANGE_BOOK,
        message="FDA Orange Book reachable",
        response_time_ms=42.0,
        checked_at=datetime.now(timezone.utc),
    )

    with patch("api.routes.connectors.get_connector", return_value=fake_connector):
        r = client.post(
            "/connectors/fda_orange_book/health-check",
            headers=_hdr(tok),
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("healthy") is True
    assert body.get("response_time_ms") == 42.0
    fake_connector.health_check.assert_called_once()


# ────────────────────────────────────────────────────────────────────
# PUT /connectors/{key}/config — enterprise only
# ────────────────────────────────────────────────────────────────────

def test_config_put_401_anonymous():
    db, _ = _make_combined_db()
    client = _client_with(db)
    r = client.put(
        "/connectors/fda_orange_book/config",
        json={"enabled": True, "auto_approve_runs": True},
    )
    assert r.status_code == 401


def test_config_put_403_uploader():
    db, _ = _make_combined_db()
    client = _client_with(db)
    tok = _login(client, "uploader@demo.market-zero.io")
    r = client.put(
        "/connectors/fda_orange_book/config",
        headers=_hdr(tok),
        json={"enabled": True, "auto_approve_runs": True},
    )
    assert r.status_code == 403


def test_config_put_200_enterprise_writes_row():
    db, store = _make_combined_db()
    client = _client_with(db)
    tok = _login(client, "enterprise@demo.market-zero.io")

    r = client.put(
        "/connectors/fda_orange_book/config",
        headers=_hdr(tok),
        json={
            "enabled": True,
            "auto_approve_runs": True,
            "manual_only": False,
            "notes": "auto-approved for demo",
        },
    )
    assert r.status_code == 200, r.text

    # Round-trip via GET
    r2 = client.get("/connectors/fda_orange_book")
    assert r2.status_code == 200
    cfg = r2.json().get("config", {})
    assert cfg.get("auto_approve_runs") is True
    assert cfg.get("notes") == "auto-approved for demo"


def test_config_put_400_for_unknown_key():
    db, _ = _make_combined_db()
    client = _client_with(db)
    tok = _login(client, "enterprise@demo.market-zero.io")
    r = client.put(
        "/connectors/not_a_real_source/config",
        headers=_hdr(tok),
        json={"enabled": True},
    )
    assert r.status_code in (400, 404)


# ────────────────────────────────────────────────────────────────────
# POST /connectors/{key}/run — uploader if auto_approve, else enterprise
# ────────────────────────────────────────────────────────────────────

def test_run_endpoint_401_anonymous():
    db, _ = _make_combined_db()
    client = _client_with(db)
    r = client.post("/connectors/fda_orange_book/run")
    assert r.status_code == 401


def test_run_endpoint_403_viewer():
    db, _ = _make_combined_db()
    client = _client_with(db)
    tok = _login(client, "viewer@demo.market-zero.io")
    r = client.post("/connectors/fda_orange_book/run", headers=_hdr(tok))
    assert r.status_code == 403


def test_run_endpoint_403_uploader_when_auto_approve_false():
    """Default config has auto_approve_runs=false → uploader gets 403."""
    db, _ = _make_combined_db()
    client = _client_with(db)
    tok = _login(client, "uploader@demo.market-zero.io")
    r = client.post("/connectors/fda_orange_book/run", headers=_hdr(tok))
    assert r.status_code == 403


def test_run_endpoint_200_uploader_when_auto_approve_true():
    db, _ = _make_combined_db(configs={
        "fda_orange_book": {
            "enabled": True, "auto_approve_runs": True,
            "manual_only": False, "notes": None,
        },
    })
    client = _client_with(db)
    tok = _login(client, "uploader@demo.market-zero.io")

    with patch("api.routes.connectors._trigger_connector_run", return_value={"queued": True}):
        r = client.post("/connectors/fda_orange_book/run", headers=_hdr(tok))
    assert r.status_code == 200, r.text


def test_run_endpoint_200_enterprise_regardless_of_auto_approve():
    db, _ = _make_combined_db()  # default: auto_approve=false
    client = _client_with(db)
    tok = _login(client, "enterprise@demo.market-zero.io")

    with patch("api.routes.connectors._trigger_connector_run", return_value={"queued": True}):
        r = client.post("/connectors/fda_orange_book/run", headers=_hdr(tok))
    assert r.status_code == 200, r.text


def test_run_endpoint_409_when_disabled():
    """enabled=false blocks runs even for enterprise."""
    db, _ = _make_combined_db(configs={
        "fda_orange_book": {
            "enabled": False, "auto_approve_runs": True,
            "manual_only": False, "notes": None,
        },
    })
    client = _client_with(db)
    tok = _login(client, "enterprise@demo.market-zero.io")
    r = client.post("/connectors/fda_orange_book/run", headers=_hdr(tok))
    assert r.status_code == 409
