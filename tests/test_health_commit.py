"""/healthz exposes the deployed commit SHA so a deploy is verifiable with one
curl (Railway/Nixpacks builds without .git — the SHA comes from the injected env).
DB-free."""
from __future__ import annotations

from fastapi.testclient import TestClient

from api.app import create_app


def test_healthz_reports_commit_from_env(monkeypatch):
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "1ec3405deadbeef99")
    body = TestClient(create_app()).get("/healthz").json()
    assert body["status"] == "ok"
    assert body["commit"] == "1ec3405deadb"  # first 12 chars


def test_healthz_unknown_when_unset(monkeypatch):
    for v in ("RAILWAY_GIT_COMMIT_SHA", "GIT_COMMIT_SHA", "SOURCE_COMMIT"):
        monkeypatch.delenv(v, raising=False)
    body = TestClient(create_app()).get("/healthz").json()
    assert body["status"] == "ok"
    assert body["commit"] == "unknown"
