"""BE-22 — /catalog/stats by_tier rollup tests."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


def _client_with_db(stats_rows):
    """``stats_rows`` is a dict of (sql-substring → return value)."""
    from fastapi.testclient import TestClient
    from api.app import create_app
    from api.deps import get_db

    db = MagicMock()

    def fake_fetch_one(sql, params=None):
        s = (sql or "").lower()
        for needle, value in stats_rows.items():
            if needle in s and "fetch_one" in needle:
                return value
        # Default count(*) → 0 entity counts
        if "count(*) as cnt from" in s:
            return {"cnt": 0}
        return None

    def fake_fetch_all(sql, params=None):
        s = (sql or "").lower()
        for needle, value in stats_rows.items():
            if needle in s and "fetch_all" in needle:
                return value
        return []

    db.fetch_one.side_effect = fake_fetch_one
    db.fetch_all.side_effect = fake_fetch_all

    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app), db


class TestCatalogStatsByTier:
    def test_response_shape_includes_by_tier(self):
        client, _ = _client_with_db({})
        r = client.get("/catalog/stats")
        assert r.status_code == 200, r.text
        body = r.json()
        assert "by_tier" in body, "BE-22 acceptance: response must carry by_tier"
        assert set(body["by_tier"].keys()) == {"T1", "T2", "T3", "T4"}

    def test_each_tier_carries_required_fields(self):
        client, _ = _client_with_db({})
        r = client.get("/catalog/stats")
        for tier, payload in r.json()["by_tier"].items():
            for key in ("sources", "records", "avg_freshness_hours", "avg_fair_score"):
                assert key in payload, f"{tier} missing {key}"

    def test_default_zeros_when_no_sources_table(self):
        client, _ = _client_with_db({})
        r = client.get("/catalog/stats")
        for tier, payload in r.json()["by_tier"].items():
            assert payload["sources"] == 0
            assert payload["records"] == 0
            # nullable freshness / fair when no data
            assert payload["avg_freshness_hours"] is None
            assert payload["avg_fair_score"] is None
