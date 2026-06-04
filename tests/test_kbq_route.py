"""PB-SL10 — KBQ HTTP route tests (the wire, not just the service).

These exist because the by-asset endpoint was first mounted at /entities/kbq,
which the entities router's GET /entities/{entity_type} SILENTLY SHADOWS
(capturing entity_type="kbq"). A service-level test missed it; only a route
test through the real app catches the shadow. The endpoint now lives at /kbq.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


def _make_db(signals):
    db = MagicMock()

    def fetch_all(sql, params=None):
        if "from signals" in (sql or "").lower():
            return signals
        return []

    db.fetch_all = MagicMock(side_effect=fetch_all)
    db.fetch_one = MagicMock(return_value=None)
    return db


def _client(db, monkeypatch):
    from fastapi.testclient import TestClient
    from api.app import create_app
    from api.deps import get_db
    import services.kbq_views as kv

    # Resolve any asset to a fixed drug id so the route exercises the full path.
    monkeypatch.setattr(kv, "resolve_asset_to_subject", lambda db, asset: ("drug", "drug-1"))

    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def _sig(sid="s1", tags=("clinical",), headline="Phase 3 readout"):
    return {
        "id": sid, "kbq_tags": list(tags), "headline": headline,
        "impact_tier": "high", "impact_score": 0.9, "confidence_tier": "confirmed",
        "evidence_document_ids": [sid], "created_at": "2026-05-20T00:00:00Z",
        "status": "shipped", "primary_entity_name": "Semaglutide",
    }


def test_kbq_by_asset_route_reaches_handler(monkeypatch):
    """GET /kbq?asset= returns the 8 KBQ views — proving it is NOT shadowed by
    the /entities/{entity_type} route."""
    db = _make_db([_sig()])
    client = _client(db, monkeypatch)
    r = client.get("/kbq", params={"asset": "semaglutide"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["asset"] == "semaglutide"
    assert len(body["kbqs"]) == 8
    assert body["entity"]["type"] == "drug"
    # KBQ-3 (Clinical) got the clinical signal — the handler actually ran.
    clinical = next(v for v in body["kbqs"] if v["kbq"] == 3)
    assert any(it["signal_id"] == "s1" for it in clinical["items"])


def test_kbq_by_asset_requires_asset_param(monkeypatch):
    db = _make_db([])
    client = _client(db, monkeypatch)
    r = client.get("/kbq")
    assert r.status_code == 422  # missing required query param


def test_per_entity_kbq_route_still_works(monkeypatch):
    """The original 4-segment /entities/{type}/{id}/kbq route is unaffected."""
    db = _make_db([_sig()])
    client = _client(db, monkeypatch)
    r = client.get("/entities/drug/drug-1/kbq")
    assert r.status_code == 200, r.text
    assert len(r.json()["kbqs"]) == 8
