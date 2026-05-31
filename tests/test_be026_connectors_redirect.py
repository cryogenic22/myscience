"""BE-26 — /connectors deprecation hints + canonical /api/v1/connectors.

Note: the user-facing HTML 301 from /connectors → /catalog is the
frontend's job (PB-809 cutover). Backend BE-26 deliverable is the
JSON-API canonical move + RFC 8594 deprecation triple on the
legacy path.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


def _client():
    from fastapi.testclient import TestClient
    from api.app import create_app
    from api.deps import get_db

    db = MagicMock()
    # list_connectors / get_connector_detail are called by the route;
    # both go through the database wrapper. Stub their return shape.
    db.fetch_all.return_value = []
    db.fetch_one.return_value = None

    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


class TestLegacyPathDeprecationHeaders:
    def test_bare_connectors_emits_deprecation_triple(self):
        client = _client()
        r = client.get("/connectors")
        assert r.status_code == 200, r.text
        assert r.headers.get("Deprecation") == "true"
        assert "Sunset" in r.headers
        link = r.headers.get("Link", "")
        assert "/api/v1/connectors" in link
        assert "successor-version" in link

    def test_canonical_v1_does_not_set_deprecation(self):
        """The canonical /api/v1/connectors path must NOT carry deprecation."""
        client = _client()
        r = client.get("/api/v1/connectors")
        assert r.status_code == 200, r.text
        assert r.headers.get("Deprecation") is None
        assert r.headers.get("Sunset") is None
        assert "successor-version" not in (r.headers.get("Link") or "")
