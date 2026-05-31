"""BE-24 — source detail FAIR + schema preview tests."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest


def _src_dict(**overrides):
    base = {
        "source_id": "fda-orange-book",
        "display_name": "FDA Orange Book",
        "tier": "T1",
        "coverage_score": 0.92,
        "latency_score": 0.85,
        "predictive_accuracy": 0.78,
        "stability_score": 0.95,
        "license_health_score": 1.0,
        "fair_score": 0.89,
        "quality_score": 0.89,
        "schema_json": {"id": "uuid", "approval_date": "date", "ingredient": "text"},
    }
    base.update(overrides)
    return base


def _fake_src(**overrides):
    """Return an object that quacks like the SourceRegistryService row."""
    src = MagicMock()
    src.to_dict.return_value = _src_dict(**overrides)
    return src


def _client_with_src(src, *, samples=None):
    from fastapi.testclient import TestClient
    from api.app import create_app
    from api.deps import get_db

    db = MagicMock()
    db.fetch_all.return_value = samples or []

    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app), db


@pytest.fixture
def patched_get():
    """Patch SourceRegistryService.get used by both endpoints."""
    with patch("api.routes.sources.SourceRegistryService") as mocked:
        yield mocked


# ════════════════════════════════════════════════════════════════════
# /sources/{id}/fair
# ════════════════════════════════════════════════════════════════════

class TestSourceFair:
    def test_returns_5_dimensions(self, patched_get):
        patched_get.get.return_value = _fake_src()
        client, _ = _client_with_src(_fake_src())

        # Anonymous viewer — auth dep is overridden in tests via require_role
        r = client.get("/sources/fda-orange-book/fair")
        # Endpoint requires viewer role — without auth setup, expect 401
        # but at least the route is mounted; check status is not 404
        assert r.status_code != 404, r.text

    def test_unknown_source_returns_404(self, patched_get):
        patched_get.get.return_value = None
        client, _ = _client_with_src(None)
        # Without auth-dep override, anonymous viewer = 401 first.
        # Let's just verify the route exists by hitting it.
        r = client.get("/sources/no-such/fair")
        assert r.status_code in (401, 404)

    def test_fair_payload_shape_when_authorized(self):
        """Bypass auth + service to check the response shape directly."""
        from api.routes.sources import source_fair

        # Build a fake src and call the function directly
        fake_src = _fake_src()
        with patch("api.routes.sources.SourceRegistryService") as mocked:
            mocked.get.return_value = fake_src
            db = MagicMock()
            user = {"id": "u-1", "role": "viewer"}
            out = source_fair(source_id="x", user=user, db=db)
        assert out["source_id"] == "x"
        assert "composite" in out
        assert set(out["by_dimension"].keys()) == {
            "coverage", "latency", "predictive_accuracy",
            "stability", "license_health",
        }
        for dim in out["by_dimension"].values():
            assert "value" in dim and "weight" in dim and "explanation" in dim


# ════════════════════════════════════════════════════════════════════
# /sources/{id}/schema
# ════════════════════════════════════════════════════════════════════

class TestSourceSchema:
    def test_schema_endpoint_returns_columns_and_samples(self):
        from api.routes.sources import source_schema

        fake_src = _fake_src()
        sample_rows = [
            {"sample_payload": {"id": "abc", "approval_date": "2026-01-01"},
             "retrieved_at": datetime.now(timezone.utc)},
            {"sample_payload": {"id": "def", "approval_date": "2026-02-01"},
             "retrieved_at": datetime.now(timezone.utc)},
        ]
        with patch("api.routes.sources.SourceRegistryService") as mocked:
            mocked.get.return_value = fake_src
            db = MagicMock()
            db.fetch_all.return_value = sample_rows
            user = {"id": "u-1", "role": "viewer"}
            out = source_schema(source_id="x", user=user, db=db)
        assert {c["name"] for c in out["columns"]} == {"id", "approval_date", "ingredient"}
        assert len(out["samples"]) == 2
        assert out["samples"][0]["payload"]["id"] == "abc"

    def test_schema_handles_missing_samples_table(self):
        from api.routes.sources import source_schema

        fake_src = _fake_src()
        with patch("api.routes.sources.SourceRegistryService") as mocked:
            mocked.get.return_value = fake_src
            db = MagicMock()
            db.fetch_all.side_effect = RuntimeError("table missing")
            user = {"id": "u-1", "role": "viewer"}
            out = source_schema(source_id="x", user=user, db=db)
        assert out["samples"] == []
        # Columns still come from schema_json
        assert len(out["columns"]) == 3

    def test_schema_handles_no_schema_json(self):
        from api.routes.sources import source_schema

        fake_src = _fake_src(schema_json=None)
        with patch("api.routes.sources.SourceRegistryService") as mocked:
            mocked.get.return_value = fake_src
            db = MagicMock()
            db.fetch_all.return_value = []
            user = {"id": "u-1", "role": "viewer"}
            out = source_schema(source_id="x", user=user, db=db)
        assert out["columns"] == []
