"""DataHub SPA deep-link fix — /hub/catalog and /hub/connect must serve the
React app on hard-refresh / bookmark, not the /hub API router's 404.

The bug: spa_fallback auto-collects 'hub' as an API prefix (the /hub router is
mounted), so a 404 under /hub is NOT rewritten to index.html. In-app navigate()
worked, but a direct browser load of /hub/catalog or /hub/connect returned the
API 404. Fix mirrors the /bridge collision: an explicit @app.get handler for
each React route wins over the prefix middleware.

FRONTEND_DIR (frontend/dist) is absent in CI, so we point it at a tmp index.html
to exercise the `if FRONTEND_DIR.exists()` SPA branch.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest


def _client(tmp_path, monkeypatch):
    import api.app as appmod
    from fastapi.testclient import TestClient
    from api.deps import get_db

    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text(
        "<!doctype html><html><body><div id=\"root\"></div></body></html>",
        encoding="utf-8",
    )
    monkeypatch.setattr(appmod, "FRONTEND_DIR", dist)

    db = MagicMock()
    db.fetch_all.return_value = []
    db.fetch_one.return_value = None
    app = appmod.create_app()
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


@pytest.mark.parametrize("path", ["/hub/catalog", "/hub/connect"])
def test_hub_react_route_serves_index_html(tmp_path, monkeypatch, path):
    client = _client(tmp_path, monkeypatch)
    r = client.get(path)
    assert r.status_code == 200, f"{path} -> {r.status_code} (deep-link 404 regression)"
    assert '<div id="root">' in r.text  # the SPA shell, not a JSON 404


def test_unmapped_hub_path_still_404s_not_swallowed(tmp_path, monkeypatch):
    # The fix must be TARGETED: only the two React routes are SPA-served. A bogus
    # /hub/* must still 404 (it's an API prefix) — proving we didn't blanket-rewrite
    # every /hub 404 into index.html (which would mask real API errors).
    client = _client(tmp_path, monkeypatch)
    r = client.get("/hub/definitely-not-a-real-route")
    assert r.status_code == 404


def test_real_hub_api_route_not_shadowed_by_spa(tmp_path, monkeypatch):
    # The SPA handlers must not shadow the live /hub API router. /hub/connector-types
    # is require_role('viewer'); anonymous gets 401/403 — crucially NOT 200 text/html.
    client = _client(tmp_path, monkeypatch)
    r = client.get("/hub/connector-types")
    assert r.status_code != 200 or "application/json" in r.headers.get("content-type", "")
    assert '<div id="root">' not in r.text  # never the SPA shell
