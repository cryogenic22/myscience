"""SEC-001a — regression tests for the unauth control-plane surface.

Red-team 2026-07-10 (COORDINATION §9.4): the three `/debug/*` routes were
anonymously reachable in production, and `/zs` fell back to the documented
default credentials (`zs` / `zs-future`) when `ZS_PAGE_*` env was unset
(fail-open). These tests pin the fail-closed behaviour:

  * `/debug/{migrate,seed-users,routes}` require a deploy secret matching
    `MZ_DEBUG_TOKEN`; when the env is unset OR the token is wrong the route
    404s (does not even confirm it exists). No user-JWT — that would deadlock
    the `/debug/seed-users` bootstrap.
  * `/zs` `require_auth` fails closed (503) when `ZS_PAGE_USER` /
    `ZS_PAGE_PASSWORD` are not configured; the old `zs`/`zs-future` default is
    gone.

RED before the fix: the debug routes return 200 anonymously and
`require_auth("zs","zs-future")` returns "zs".
"""
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPBasicCredentials
from fastapi.testclient import TestClient

from api.app import create_app


# ---------------------------------------------------------------- /debug/*

def _client(monkeypatch, token: str | None):
    if token is None:
        monkeypatch.delenv("MZ_DEBUG_TOKEN", raising=False)
    else:
        monkeypatch.setenv("MZ_DEBUG_TOKEN", token)
    return TestClient(create_app())


@pytest.mark.parametrize(
    "method,path",
    [("get", "/debug/routes"), ("post", "/debug/migrate"), ("post", "/debug/seed-users")],
)
def test_debug_routes_closed_when_token_unset(monkeypatch, method, path):
    """Unset MZ_DEBUG_TOKEN => every /debug route 404s (fail closed)."""
    client = _client(monkeypatch, None)
    resp = getattr(client, method)(path)
    assert resp.status_code == 404, f"{path} anonymously reachable: {resp.status_code}"


@pytest.mark.parametrize(
    "method,path",
    [("get", "/debug/routes"), ("post", "/debug/migrate"), ("post", "/debug/seed-users")],
)
def test_debug_routes_404_on_wrong_token(monkeypatch, method, path):
    client = _client(monkeypatch, "correct-horse")
    resp = getattr(client, method)(path, headers={"X-Debug-Token": "wrong"})
    assert resp.status_code == 404


def test_debug_routes_reachable_with_correct_token(monkeypatch):
    """The gate passes with the right token (route handler runs)."""
    client = _client(monkeypatch, "correct-horse")
    resp = client.get("/debug/routes", headers={"X-Debug-Token": "correct-horse"})
    assert resp.status_code == 200
    assert "total_routes" in resp.json()


# ------------------------------------------------------------------- /zs

def test_zs_auth_fails_closed_when_unconfigured(monkeypatch):
    """No ZS_PAGE_* env => deny (503), never accept the old default."""
    monkeypatch.delenv("ZS_PAGE_USER", raising=False)
    monkeypatch.delenv("ZS_PAGE_PASSWORD", raising=False)
    from api.routes.zs import require_auth

    with pytest.raises(HTTPException) as ei:
        require_auth(HTTPBasicCredentials(username="zs", password="zs-future"))
    assert ei.value.status_code == 503


def test_zs_auth_accepts_configured_creds(monkeypatch):
    monkeypatch.setenv("ZS_PAGE_USER", "alice")
    monkeypatch.setenv("ZS_PAGE_PASSWORD", "s3cret-pw")
    from api.routes.zs import require_auth

    assert require_auth(HTTPBasicCredentials(username="alice", password="s3cret-pw")) == "alice"


def test_zs_auth_rejects_old_default_once_configured(monkeypatch):
    """With real creds set, the retired zs/zs-future default must 401."""
    monkeypatch.setenv("ZS_PAGE_USER", "alice")
    monkeypatch.setenv("ZS_PAGE_PASSWORD", "s3cret-pw")
    from api.routes.zs import require_auth

    with pytest.raises(HTTPException) as ei:
        require_auth(HTTPBasicCredentials(username="zs", password="zs-future"))
    assert ei.value.status_code == 401
