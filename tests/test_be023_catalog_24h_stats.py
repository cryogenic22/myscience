"""BE-23 — /catalog/24h-stats endpoint tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest


def _client_with_db(*, has_runs=False, has_dq=False,
                    runs_aggregate=None, runs_by_source=None,
                    dq_drifts=0):
    from fastapi.testclient import TestClient
    from api.app import create_app
    from api.deps import get_db

    db = MagicMock()

    def fake_fetch_one(sql, params=None):
        s = (sql or "").lower()
        # _table_exists uses params=[table_name] and asks for exists_
        if "from information_schema.tables" in s:
            if params and len(params) >= 1:
                tname = str(params[0])
                if tname == "connector_runs":
                    return {"exists_": has_runs}
                if tname == "data_quality_results":
                    return {"exists_": has_dq}
                return {"exists_": False}
            return {"exists_": False}
        if "from connector_runs" in s and "count(*)::int as cycles" in s:
            return runs_aggregate or {}
        if "from data_quality_results" in s and "as drifts" in s:
            return {"drifts": dq_drifts}
        return None

    def fake_fetch_all(sql, params=None):
        s = (sql or "").lower()
        if "from connector_runs" in s and "group by source_key" in s:
            return runs_by_source or []
        return []

    db.fetch_one.side_effect = fake_fetch_one
    db.fetch_all.side_effect = fake_fetch_all

    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


class TestCatalog24hStats:
    def test_zeros_when_tables_missing(self):
        client = _client_with_db()
        r = client.get("/catalog/24h-stats")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["cycles_run"] == 0
        assert body["records_ingested"] == 0
        assert body["drift_events"] == 0
        assert body["est_cost_usd"] == 0.0
        assert body["by_source"] == []
        assert body["health"] == 1.0

    def test_aggregate_and_by_source_when_tables_present(self):
        client = _client_with_db(
            has_runs=True,
            runs_aggregate={"cycles": 12, "records": 4500, "cost": 1.42},
            runs_by_source=[
                {"source_key": "clinical_trials_gov", "cycles": 6,
                 "records": 4000, "failures": 0,
                 "last_run_at": datetime.now(timezone.utc)},
                {"source_key": "pubmed", "cycles": 6,
                 "records": 500, "failures": 1,
                 "last_run_at": datetime.now(timezone.utc) - timedelta(hours=2)},
            ],
            has_dq=True, dq_drifts=3,
        )
        r = client.get("/catalog/24h-stats")
        body = r.json()
        assert body["cycles_run"] == 12
        assert body["records_ingested"] == 4500
        assert body["est_cost_usd"] == 1.42
        assert body["drift_events"] == 3
        assert len(body["by_source"]) == 2
        # Sort: records DESC → clinical_trials_gov first
        assert body["by_source"][0]["source_key"] == "clinical_trials_gov"
        # Health = 1 - failures/cycles = 1 - 1/12 ≈ 0.9167
        assert 0.9 < body["health"] < 1.0
