"""SPEC-021 Phase E — Inbox API tests."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest


def _make_db():
    from services.auth import hash_password

    users = {
        "viewer@demo.market-zero.io": {
            "id": "uuid-viewer", "email": "viewer@demo.market-zero.io",
            "password_hash": hash_password("demo"), "role": "viewer",
            "is_active": True,
        },
        "uploader@demo.market-zero.io": {
            "id": "uuid-uploader", "email": "uploader@demo.market-zero.io",
            "password_hash": hash_password("demo"), "role": "uploader",
            "is_active": True,
        },
    }

    # Stubbed inbox content per query
    pending_proposals_rows = [
        {
            "proposal_id": "prop-1",
            "decision_id": "dec-1",
            "matched_signal_id": "sig-1",
            "match_score": 0.85,
            "match_components": {"entity_overlap": 0.5, "kbq_overlap": 0.3, "temporal_proximity": 0.05},
            "proposed_at": datetime(2026, 5, 4, tzinfo=timezone.utc),
            "decision_title": "Accelerate semaglutide MASH",
            "decision_status": "in_progress",
            "signal_headline": "Lilly accelerated SURMOUNT-MASH",
            "signal_summary": "Confirmed",
            "signal_kbq_tags": ["clinical"],
            "signal_entity": "Eli Lilly",
        },
    ]

    overdue_rows = [
        {
            "id": "dec-overdue",
            "title": "Overdue decision",
            "deadline": date(2026, 4, 1),  # past
            "status": "open",
            "war_room_id": "wr-1",
            "target_metric": "market_share_delta",
            "target_value": "+3pp",
            "confidence_at_commit": 0.6,
            "created_at": datetime(2026, 3, 1, tzinfo=timezone.utc),
        },
    ]

    high_impact_signals = [
        {
            "id": "sig-hi-1",
            "headline": "Pfizer Q1 guidance raise",
            "summary": "+8% YoY",
            "kbq_tags": ["financial"],
            "primary_entity_id": "ent-pfizer",
            "primary_entity_type": "company",
            "primary_entity_name": "Pfizer",
            "impact_tier": "high",
            "trust_score": 0.9,
            "created_at": datetime(2026, 5, 3, tzinfo=timezone.utc),
        },
    ]

    calibration_row = {
        "total": 5,
        "mean_cal": 0.71,
        "verified": 4,
        "missed": 1,
    }

    db = MagicMock()

    def fake_fetch_one(sql, params=None):
        s = (sql or "").lower()
        if "from users" in s and params:
            if "where lower(email)" in s or "where email" in s:
                return users.get(str(params[0]).lower())
            if "where id::text" in s or "where id =" in s:
                for u in users.values():
                    if u["id"] == params[0]:
                        return u
                return None
        if "avg(calibration_score)" in s:
            return calibration_row
        return None

    def fake_fetch_all(sql, params=None):
        s = (sql or "").lower()
        if "from outcome_proposals" in s and "join decisions" in s:
            return pending_proposals_rows
        if "from decisions" in s and "deadline < current_date" in s:
            return overdue_rows
        if "from signals" in s and "impact_tier = 'high'" in s:
            return high_impact_signals
        return []

    db.fetch_one.side_effect = fake_fetch_one
    db.fetch_all.side_effect = fake_fetch_all
    return db


def _client(db):
    from fastapi.testclient import TestClient
    from api.app import create_app
    from api.deps import get_db
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def _login(client, email):
    r = client.post("/auth/login", json={"email": email, "password": "demo"})
    return r.json().get("access_token", "") if r.status_code == 200 else ""


def _hdr(tok):
    return {"Authorization": f"Bearer {tok}"} if tok else {}


def test_inbox_401_anonymous():
    db = _make_db()
    r = _client(db).get("/inbox")
    assert r.status_code == 401


def test_inbox_returns_all_four_sections():
    db = _make_db()
    client = _client(db)
    tok = _login(client, "viewer@demo.market-zero.io")
    r = client.get("/inbox", headers=_hdr(tok))
    assert r.status_code == 200, r.text
    body = r.json()
    assert "pending_proposals" in body
    assert "overdue_decisions" in body
    assert "high_impact_signals" in body
    assert "calibration_summary" in body


def test_inbox_pending_proposals_includes_signal_join():
    db = _make_db()
    client = _client(db)
    tok = _login(client, "viewer@demo.market-zero.io")
    body = client.get("/inbox", headers=_hdr(tok)).json()
    assert len(body["pending_proposals"]) == 1
    p = body["pending_proposals"][0]
    assert p["decision_title"] == "Accelerate semaglutide MASH"
    assert p["signal_headline"] == "Lilly accelerated SURMOUNT-MASH"
    assert p["signal_kbq_tags"] == ["clinical"]
    assert p["match_score"] == 0.85


def test_inbox_overdue_includes_days_overdue():
    db = _make_db()
    client = _client(db)
    tok = _login(client, "viewer@demo.market-zero.io")
    body = client.get("/inbox", headers=_hdr(tok)).json()
    assert len(body["overdue_decisions"]) == 1
    od = body["overdue_decisions"][0]
    assert od["title"] == "Overdue decision"
    assert od["days_overdue"] is not None
    assert od["days_overdue"] > 0


def test_inbox_calibration_summary_aggregates():
    db = _make_db()
    client = _client(db)
    tok = _login(client, "viewer@demo.market-zero.io")
    body = client.get("/inbox", headers=_hdr(tok)).json()
    cs = body["calibration_summary"]
    assert cs["last_30d_mean"] == pytest.approx(0.71, abs=0.01)
    assert cs["verified_count"] == 4
    assert cs["missed_count"] == 1
    assert cs["total"] == 5


def test_inbox_high_impact_signals_present():
    db = _make_db()
    client = _client(db)
    tok = _login(client, "viewer@demo.market-zero.io")
    body = client.get("/inbox", headers=_hdr(tok)).json()
    assert len(body["high_impact_signals"]) == 1
    sig = body["high_impact_signals"][0]
    assert sig["impact_tier"] == "high"
    assert sig["primary_entity_name"] == "Pfizer"
