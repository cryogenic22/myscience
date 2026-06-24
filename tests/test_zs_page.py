"""Lane-1, DB-free tests for the password-gated /zs static page router.

Asserts the HTTP Basic gate (401 without/with-wrong creds, 200 with right creds),
that the page + its JSX source are actually served, and that ZS_PAGE_PASSWORD /
ZS_PAGE_USER override the defaults.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import zs as zs_route


@pytest.fixture
def client(monkeypatch):
    # Unset env so the documented defaults (zs / zs-future) apply unless a test
    # sets them explicitly.
    monkeypatch.delenv("ZS_PAGE_USER", raising=False)
    monkeypatch.delenv("ZS_PAGE_PASSWORD", raising=False)
    app = FastAPI()
    app.include_router(zs_route.router)
    return TestClient(app)


def test_no_credentials_is_401_with_challenge(client):
    r = client.get("/zs")
    assert r.status_code == 401
    # browser prompt is driven by the WWW-Authenticate challenge
    assert "basic" in r.headers.get("www-authenticate", "").lower()


def test_wrong_password_is_401(client):
    r = client.get("/zs", auth=("zs", "nope"))
    assert r.status_code == 401


def test_correct_default_credentials_serve_page(client):
    r = client.get("/zs", auth=("zs", "zs-future"))
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    body = r.text
    # the shell wires recharts/react via importmap and mounts into #root
    assert 'id="root"' in body
    assert "importmap" in body


def test_jsx_source_served_as_text_when_authed(client):
    r = client.get("/zs/zs-future-state-v2.jsx", auth=("zs", "zs-future"))
    assert r.status_code == 200
    assert "text/plain" in r.headers["content-type"]
    assert "ZSFutureState" in r.text  # the default-export component


def test_jsx_source_requires_auth(client):
    r = client.get("/zs/zs-future-state-v2.jsx")
    assert r.status_code == 401


def test_env_overrides_credentials(monkeypatch):
    monkeypatch.setenv("ZS_PAGE_USER", "alice")
    monkeypatch.setenv("ZS_PAGE_PASSWORD", "s3cret")
    app = FastAPI()
    app.include_router(zs_route.router)
    c = TestClient(app)
    # old defaults now rejected
    assert c.get("/zs", auth=("zs", "zs-future")).status_code == 401
    # configured creds accepted
    assert c.get("/zs", auth=("alice", "s3cret")).status_code == 200
