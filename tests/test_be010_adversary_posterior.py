"""BE-10 — /adversaries/{id}/posterior endpoint tests."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest


def _twin_dict():
    return {
        "twin_id": "tw-1",
        "name": "Pfizer",
        "kind": "competitor",
        "posterior": {"aggressive": 0.61, "defensive": 0.24, "cash_constrained": 0.15},
        "last_updated_at": datetime.now(timezone.utc).isoformat(),
        "last_5_evidence_updates": [
            {"ts": "2026-05-01T00:00:00Z", "evidence_id": "ev-1",
             "what_shifted": "ASCO data", "magnitude": 0.4,
             "target_axis": "aggressive"},
        ],
    }


class TestPosteriorEndpoint:
    def test_route_registered(self):
        from api.app import create_app
        app = create_app()
        paths = {r.path for r in app.routes}
        assert "/adversaries/{twin_id}/posterior" in paths
        assert "/adversaries" in paths
        assert "/api/v1/adversaries/{twin_id}/posterior" in paths

    def test_returns_acceptance_shape(self):
        from fastapi.testclient import TestClient
        from api.app import create_app
        from api.deps import get_db

        twin = MagicMock()
        twin.to_dict.return_value = _twin_dict()

        with patch("api.routes.adversary.svc.get", return_value=twin):
            db = MagicMock()
            app = create_app()
            app.dependency_overrides[get_db] = lambda: db
            client = TestClient(app)
            r = client.get("/adversaries/tw-1/posterior")
        assert r.status_code == 200, r.text
        body = r.json()
        # BE-10 acceptance shape
        assert "posterior" in body
        assert set(body["posterior"].keys()) == {"aggressive", "defensive", "cash_constrained"}
        assert "last_updated_at" in body
        assert "last_5_evidence_updates" in body
        assert len(body["last_5_evidence_updates"]) == 1

    def test_returns_404_when_missing(self):
        from fastapi.testclient import TestClient
        from api.app import create_app
        from api.deps import get_db

        with patch("api.routes.adversary.svc.get", return_value=None):
            db = MagicMock()
            app = create_app()
            app.dependency_overrides[get_db] = lambda: db
            client = TestClient(app)
            r = client.get("/adversaries/nope/posterior")
        assert r.status_code == 404, r.text

    def test_list_filters_by_kind(self):
        from fastapi.testclient import TestClient
        from api.app import create_app
        from api.deps import get_db

        twin = MagicMock()
        twin.to_dict.return_value = _twin_dict()

        with patch("api.routes.adversary.svc.list_twins", return_value=[twin]):
            db = MagicMock()
            app = create_app()
            app.dependency_overrides[get_db] = lambda: db
            client = TestClient(app)
            r = client.get("/adversaries?kind=competitor")
        assert r.status_code == 200, r.text
        assert len(r.json()["twins"]) == 1

    def test_list_invalid_kind_400(self):
        from fastapi.testclient import TestClient
        from api.app import create_app
        from api.deps import get_db

        with patch("api.routes.adversary.svc.list_twins",
                   side_effect=ValueError("kind must be in ('competitor', 'regulator', 'payer', 'kol')")):
            db = MagicMock()
            app = create_app()
            app.dependency_overrides[get_db] = lambda: db
            client = TestClient(app)
            r = client.get("/adversaries?kind=bogus")
        assert r.status_code == 400, r.text
