"""SPEC-020 — Signals API tests.

Endpoints:
  GET   /signals                 anonymous   list (default: shipped+reviewed)
  GET   /signals/{id}            anonymous   detail with evidence
  POST  /signals/{id}/review     enterprise  set status + actor

DB and signals rows are mocked; no live Postgres needed.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent


# ────────────────────────────────────────────────────────────────────
# Fake DB — handles users + signals
# ────────────────────────────────────────────────────────────────────

def _make_signal_row(
    *,
    signal_id: str = "sig-1",
    status: str = "shipped",
    impact_tier: str = "high",
    impact_score: float = 0.9,
    confidence_tier: str = "confirmed",
    trust_score: float = 0.95,
    kbq_tags: list = None,
    headline: str = "Pfizer raises FY guidance",
    summary: str = "Q3 8-K Item 2.02 — guidance raised by ~3%",
    direction: str = "positive",
    primary_entity_type: str = "company",
    primary_entity_id: str = "ent-pfizer",
    primary_entity_name: str = "Pfizer Inc.",
    related_entity_ids: list = None,
    evidence_document_ids: list = None,
    rule_version_id: str = "v1",
    superseded_by: str = None,
    supersedence_reason: str = None,
    reviewed_by: str = None,
    reviewed_at: datetime = None,
    shipped_at: datetime = None,
    created_at: datetime = None,
    event_id: str = "evt-1",
):
    return {
        "id": signal_id,
        "event_id": event_id,
        "kbq_tags": kbq_tags if kbq_tags is not None else ["financial"],
        "headline": headline,
        "summary": summary,
        "direction": direction,
        "confidence_tier": confidence_tier,
        "trust_score": trust_score,
        "impact_tier": impact_tier,
        "impact_score": impact_score,
        "rule_version_id": rule_version_id,
        "primary_entity_type": primary_entity_type,
        "primary_entity_id": primary_entity_id,
        "primary_entity_name": primary_entity_name,
        "related_entity_ids": related_entity_ids or [],
        "evidence_document_ids": evidence_document_ids or ["doc-1"],
        "status": status,
        "superseded_by": superseded_by,
        "supersedence_reason": supersedence_reason,
        "created_at": created_at or datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc),
        "reviewed_by": reviewed_by,
        "reviewed_at": reviewed_at,
        "shipped_at": shipped_at or datetime(2026, 5, 1, 13, 0, tzinfo=timezone.utc),
    }


def _make_db(signals: list = None):
    """Fake DB serving users (auth) and signals (read + review)."""
    from services.auth import hash_password

    signals = signals if signals is not None else [_make_signal_row()]
    rows = list(signals)  # mutable for review tests
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
        "enterprise@demo.market-zero.io": {
            "id": "uuid-enterprise", "email": "enterprise@demo.market-zero.io",
            "password_hash": hash_password("demo"), "role": "enterprise",
            "is_active": True,
        },
    }

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
        if "from signals" in s and "where id" in s and params:
            for r in rows:
                if r["id"] == str(params[0]):
                    return dict(r)
            return None
        return None

    def fake_fetch_all(sql, params=None):
        s = (sql or "").lower()
        if "from signals" in s:
            out = list(rows)
            params_list = list(params or [])
            param_idx = 0

            if "status = any" in s:
                allowed = params_list[param_idx]
                param_idx += 1
                out = [r for r in out if r["status"] in allowed]
            elif " status =" in s:
                allowed = [params_list[param_idx]]
                param_idx += 1
                out = [r for r in out if r["status"] in allowed]

            if "impact_tier =" in s:
                tier = params_list[param_idx]
                param_idx += 1
                out = [r for r in out if r["impact_tier"] == tier]

            if "kbq_tags && " in s:
                tags = params_list[param_idx]
                param_idx += 1
                out = [r for r in out if any(t in r["kbq_tags"] for t in tags)]

            if "primary_entity_type =" in s:
                etype = params_list[param_idx]
                param_idx += 1
                out = [r for r in out if r["primary_entity_type"] == etype]

            if "primary_entity_id =" in s:
                eid = params_list[param_idx]
                param_idx += 1
                out = [r for r in out if r["primary_entity_id"] == eid]

            # order by impact_score desc, created_at desc
            impact_rank = {"high": 3, "medium": 2, "low": 1}
            out.sort(
                key=lambda r: (
                    impact_rank.get(r["impact_tier"], 0),
                    r["impact_score"],
                    r["created_at"],
                ),
                reverse=True,
            )
            return [dict(r) for r in out]
        return []

    def fake_execute(sql, params=None):
        s = (sql or "").lower()
        # Review update
        if "update signals" in s and "set status" in s and params:
            new_status = params[0]
            reviewed_by = params[1]
            sig_id = params[-1]
            for r in rows:
                if r["id"] == sig_id:
                    r["status"] = new_status
                    r["reviewed_by"] = reviewed_by
                    r["reviewed_at"] = datetime.now(timezone.utc)
                    if new_status == "shipped":
                        r["shipped_at"] = datetime.now(timezone.utc)
                    return None
        return None

    db = MagicMock()
    db.fetch_one.side_effect = fake_fetch_one
    db.fetch_all.side_effect = fake_fetch_all
    db.execute.side_effect = fake_execute
    return db, rows


def _client(db):
    from fastapi.testclient import TestClient
    from api.app import create_app
    from api.deps import get_db, get_llm

    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_llm] = lambda: None
    return TestClient(app)


def _login(client, email):
    r = client.post("/auth/login", json={"email": email, "password": "demo"})
    return r.json().get("access_token", "") if r.status_code == 200 else ""


def _hdr(tok):
    return {"Authorization": f"Bearer {tok}"} if tok else {}


# ────────────────────────────────────────────────────────────────────
# Module + routes
# ────────────────────────────────────────────────────────────────────

def test_signals_route_module_exists():
    assert (REPO_ROOT / "api" / "routes" / "signals.py").exists()


def test_signals_routes_registered():
    from api.app import create_app
    app = create_app()
    paths = {getattr(r, "path", None) for r in app.routes}
    assert any(p and p.endswith("/signals") for p in paths)
    assert any(p and "/signals/" in (p or "") for p in paths)


# ────────────────────────────────────────────────────────────────────
# GET /signals — list, anonymous
# ────────────────────────────────────────────────────────────────────

def test_list_endpoint_returns_200_anonymous():
    db, _ = _make_db()
    r = _client(db).get("/signals")
    assert r.status_code == 200, r.text


def test_list_endpoint_response_shape():
    db, _ = _make_db()
    body = _client(db).get("/signals").json()
    assert "signals" in body
    assert "count" in body
    assert isinstance(body["signals"], list)
    assert len(body["signals"]) == 1
    s = body["signals"][0]
    for f in ("id", "headline", "kbq_tags", "impact_tier", "confidence_tier",
              "primary_entity_name", "status", "evidence_document_ids"):
        assert f in s, f"signal missing field: {f}"


def test_list_endpoint_filters_by_status():
    db, _ = _make_db([
        _make_signal_row(signal_id="s1", status="shipped"),
        _make_signal_row(signal_id="s2", status="candidate"),
        _make_signal_row(signal_id="s3", status="reviewed"),
    ])
    body = _client(db).get("/signals?status=candidate").json()
    ids = {s["id"] for s in body["signals"]}
    assert ids == {"s2"}


def test_list_endpoint_filters_by_impact():
    db, _ = _make_db([
        _make_signal_row(signal_id="s1", impact_tier="high"),
        _make_signal_row(signal_id="s2", impact_tier="medium"),
        _make_signal_row(signal_id="s3", impact_tier="low"),
    ])
    body = _client(db).get("/signals?impact=high").json()
    assert {s["id"] for s in body["signals"]} == {"s1"}


def test_list_endpoint_filters_by_kbq():
    db, _ = _make_db([
        _make_signal_row(signal_id="s1", kbq_tags=["financial"]),
        _make_signal_row(signal_id="s2", kbq_tags=["clinical"]),
        _make_signal_row(signal_id="s3", kbq_tags=["clinical", "regulatory"]),
    ])
    body = _client(db).get("/signals?kbq=clinical").json()
    assert {s["id"] for s in body["signals"]} == {"s2", "s3"}


def test_list_endpoint_filters_by_entity():
    db, _ = _make_db([
        _make_signal_row(signal_id="s1", primary_entity_type="company",
                         primary_entity_id="ent-pfizer"),
        _make_signal_row(signal_id="s2", primary_entity_type="company",
                         primary_entity_id="ent-amgen"),
    ])
    body = _client(db).get("/signals?entity_type=company&entity_id=ent-pfizer").json()
    assert {s["id"] for s in body["signals"]} == {"s1"}


def test_list_endpoint_default_excludes_candidate_and_superseded():
    """Default view shows reviewed + shipped, NOT candidate/superseded/retracted."""
    db, _ = _make_db([
        _make_signal_row(signal_id="s1", status="shipped"),
        _make_signal_row(signal_id="s2", status="reviewed"),
        _make_signal_row(signal_id="s3", status="candidate"),
        _make_signal_row(signal_id="s4", status="superseded"),
        _make_signal_row(signal_id="s5", status="retracted"),
    ])
    body = _client(db).get("/signals").json()
    ids = {s["id"] for s in body["signals"]}
    assert ids == {"s1", "s2"}


def test_list_endpoint_orders_by_impact_then_recency():
    db, _ = _make_db([
        _make_signal_row(
            signal_id="low_recent", impact_tier="low", impact_score=0.2,
            created_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        ),
        _make_signal_row(
            signal_id="high_old", impact_tier="high", impact_score=0.9,
            created_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
        ),
        _make_signal_row(
            signal_id="med", impact_tier="medium", impact_score=0.5,
            created_at=datetime(2026, 4, 15, tzinfo=timezone.utc),
        ),
    ])
    body = _client(db).get("/signals").json()
    ids = [s["id"] for s in body["signals"]]
    assert ids == ["high_old", "med", "low_recent"]


# ────────────────────────────────────────────────────────────────────
# GET /signals/{id}
# ────────────────────────────────────────────────────────────────────

def test_detail_endpoint_returns_signal_with_evidence():
    db, _ = _make_db()
    body = _client(db).get("/signals/sig-1").json()
    assert body["id"] == "sig-1"
    assert "evidence_document_ids" in body
    assert isinstance(body["evidence_document_ids"], list)
    assert len(body["evidence_document_ids"]) >= 1


def test_detail_endpoint_404_for_unknown_id():
    db, _ = _make_db()
    r = _client(db).get("/signals/does-not-exist")
    assert r.status_code == 404


# ────────────────────────────────────────────────────────────────────
# POST /signals/{id}/review — enterprise only
# ────────────────────────────────────────────────────────────────────

def test_review_endpoint_401_anonymous():
    db, _ = _make_db()
    r = _client(db).post("/signals/sig-1/review", json={"status": "shipped"})
    assert r.status_code == 401


def test_review_endpoint_403_viewer():
    db, _ = _make_db()
    client = _client(db)
    tok = _login(client, "viewer@demo.market-zero.io")
    r = client.post("/signals/sig-1/review", headers=_hdr(tok),
                    json={"status": "shipped"})
    assert r.status_code == 403


def test_review_endpoint_403_uploader():
    db, _ = _make_db()
    client = _client(db)
    tok = _login(client, "uploader@demo.market-zero.io")
    r = client.post("/signals/sig-1/review", headers=_hdr(tok),
                    json={"status": "shipped"})
    assert r.status_code == 403


def test_review_endpoint_200_enterprise_sets_status_and_actor():
    db, rows = _make_db([_make_signal_row(signal_id="sig-1", status="candidate")])
    client = _client(db)
    tok = _login(client, "enterprise@demo.market-zero.io")
    r = client.post("/signals/sig-1/review", headers=_hdr(tok),
                    json={"status": "shipped"})
    assert r.status_code == 200, r.text
    # Verify state mutated
    after = next(r for r in rows if r["id"] == "sig-1")
    assert after["status"] == "shipped"
    assert after["reviewed_by"] == "uuid-enterprise"
    assert after["reviewed_at"] is not None
    assert after["shipped_at"] is not None


def test_review_endpoint_400_for_invalid_status():
    db, _ = _make_db()
    client = _client(db)
    tok = _login(client, "enterprise@demo.market-zero.io")
    r = client.post("/signals/sig-1/review", headers=_hdr(tok),
                    json={"status": "yolo"})
    assert r.status_code == 400
