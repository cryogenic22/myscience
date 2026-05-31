"""Loop A — Engagements CRUD API tests.

Integration coverage for the route layer over engagement/BCB/priority-matrix
service modules. The lifecycle acceptance test exercises the full happy
path; subsequent tests pin specific error mappings (FSM violations → 409,
missing resources → 404, etc.).

DB + auth use the same fake-db pattern as test_war_room_api.py.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient


# ──────────────────────────────────────────────────────────────────
# Fake DB
# ──────────────────────────────────────────────────────────────────

def _make_db():
    from services.auth import hash_password

    users = {
        "uploader@demo.market-zero.io": {
            "id": "uuid-uploader", "email": "uploader@demo.market-zero.io",
            "password_hash": hash_password("demo"),
            "role": "uploader", "is_active": True,
        },
        "viewer@demo.market-zero.io": {
            "id": "uuid-viewer", "email": "viewer@demo.market-zero.io",
            "password_hash": hash_password("demo"),
            "role": "viewer", "is_active": True,
        },
    }

    engagements: dict[str, dict] = {}
    bcbs: dict[str, dict] = {}      # bcb_id → row
    audit: list[dict] = []

    def _eng_row(eid, name="Test", asset="drug:x", situation="defense",
                 stage="brief", status="draft", scope=None,
                 created_by="uuid-uploader"):
        now = datetime.now(timezone.utc)
        return {
            "id": eid, "name": name, "asset": asset, "sponsor": None,
            "situation": situation, "workshop_date": None,
            "stage": stage, "status": status,
            "scope": json.dumps(scope or {}),
            "created_by": created_by, "created_at": now, "updated_at": now,
            "tenant_scope": None,
        }

    def fetch_one(sql, params=None):
        s = (sql or "").lower()

        # ── auth ──
        if "from users" in s and params:
            if "where lower(email)" in s or "where email" in s:
                return users.get(str(params[0]).lower())
            if "where id::text" in s or "where id =" in s:
                for u in users.values():
                    if u["id"] == params[0]:
                        return u
                return None

        # ── engagements ──
        # INSERT ... RETURNING id (engagement) — service uses named params
        if "insert into engagements" in s and "returning" in s and params:
            eid = str(uuid4())
            # params may be dict (named params) or list
            if isinstance(params, dict):
                engagements[eid] = _eng_row(
                    eid,
                    name=params.get("name", "Test"),
                    asset=params.get("asset", "drug:x"),
                    situation=params.get("situation", "defense"),
                    stage=params.get("stage", "brief"),
                    status=params.get("status", "draft"),
                    scope=json.loads(params["scope"]) if params.get("scope") else {},
                    created_by=params.get("created_by", "uuid-uploader"),
                )
                engagements[eid]["sponsor"] = params.get("sponsor")
                engagements[eid]["workshop_date"] = params.get("workshop_date")
                engagements[eid]["tenant_scope"] = params.get("tenant_scope")
            else:
                engagements[eid] = _eng_row(eid)
            return {"id": eid}

        if "from engagements" in s and ("where id" in s) and params:
            key = params[0] if not isinstance(params, dict) else params.get("id")
            return engagements.get(str(key))

        # advance_stage / set_status: UPDATE ... RETURNING. Service uses
        # positional params: [new_value, eid]. Discriminate on which
        # column the SQL is setting.
        if "update engagements" in s and "returning" in s and params:
            if isinstance(params, list) and len(params) >= 2:
                new_value, eid = params[0], str(params[1])
                if eid in engagements:
                    if "set stage" in s:
                        engagements[eid]["stage"] = new_value
                    elif "set status" in s:
                        engagements[eid]["status"] = new_value
                    engagements[eid]["updated_at"] = datetime.now(timezone.utc)
                    return dict(engagements[eid])
                return None
            # Dict-shaped params fallback (forward-compat)
            pd = params if isinstance(params, dict) else {}
            eid = str(pd.get("id", ""))
            if eid in engagements:
                if "stage" in pd:
                    engagements[eid]["stage"] = pd["stage"]
                if "status" in pd:
                    engagements[eid]["status"] = pd["status"]
                engagements[eid]["updated_at"] = datetime.now(timezone.utc)
                return dict(engagements[eid])
            return None

        # ── BCB ──
        if "insert into business_context_briefs" in s and "returning" in s and params:
            bid = str(uuid4())
            pd = params if isinstance(params, dict) else {}
            now = datetime.now(timezone.utc)
            bcbs[bid] = {
                "id": bid,
                "engagement_id": pd.get("engagement_id"),
                "focal_asset": pd.get("focal_asset"),
                "situation": pd.get("situation"),
                "strategic_decisions": pd.get("strategic_decisions") or "[]",
                "competitive_set": pd.get("competitive_set") or "[]",
                "success_criteria": pd.get("success_criteria") or "[]",
                "constraints": pd.get("constraints") or "[]",
                "created_by": pd.get("created_by"),
                "created_at": now,
                "signed_off": False,
                "signed_off_by": None,
                "signed_off_at": None,
                "priority_matrix": None,
            }
            return {"id": bid}

        if "from business_context_briefs" in s and "where engagement_id" in s and params:
            key = params[0] if not isinstance(params, dict) else params.get("engagement_id")
            for b in bcbs.values():
                if b["engagement_id"] == key:
                    return dict(b)
            return None

        if "from business_context_briefs" in s and ("where id" in s) and params:
            key = params[0] if not isinstance(params, dict) else params.get("id")
            return bcbs.get(str(key))

        if "update business_context_briefs" in s and "returning" in s and params:
            pd = params if isinstance(params, dict) else {}
            bid = str(pd.get("id"))
            if bid in bcbs:
                if "signed_off" in pd:
                    bcbs[bid]["signed_off"] = pd["signed_off"]
                    bcbs[bid]["signed_off_by"] = pd.get("signed_off_by")
                    bcbs[bid]["signed_off_at"] = datetime.now(timezone.utc) if pd["signed_off"] else None
                if "priority_matrix" in pd:
                    bcbs[bid]["priority_matrix"] = pd["priority_matrix"]
                return dict(bcbs[bid])
            return None

        return None

    def fetch_all(sql, params=None):
        s = (sql or "").lower()
        if "from engagements" in s:
            rows = list(engagements.values())
            # Apply rudimentary status/situation filter
            if isinstance(params, list):
                # Last param is limit; earlier are filters in order
                # Conservative: just return all (the route is the unit test
                # boundary; filter logic lives in the service).
                pass
            return [dict(r) for r in rows]
        return []

    def execute(sql, params=None):
        s = (sql or "").lower()
        # Audit inserts
        if "insert into engagement_lifecycle_events" in s:
            audit.append({"sql": s, "params": params})
        return None

    db = MagicMock()
    db.fetch_one.side_effect = fetch_one
    db.fetch_all.side_effect = fetch_all
    db.execute.side_effect = execute
    return db, engagements, bcbs, audit


def _client(db):
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


# ──────────────────────────────────────────────────────────────────
# Acceptance test — full lifecycle
# ──────────────────────────────────────────────────────────────────

def test_acceptance_engagement_lifecycle():
    db, engagements, bcbs, _ = _make_db()
    client = _client(db)
    tok = _login(client, "uploader@demo.market-zero.io")
    hdr = _hdr(tok)

    # 1. POST creates an engagement in draft/brief.
    r = client.post("/engagements", headers=hdr, json={
        "name": "Wegovy MASH defense", "asset": "drug:wegovy",
        "situation": "defense",
    })
    assert r.status_code == 201, r.text
    body = r.json()
    eid = body["id"]
    assert body["stage"] == "brief"
    assert body["status"] == "draft"

    # 2. PATCH status moves to active.
    r = client.patch(f"/engagements/{eid}/status", headers=hdr,
                     json={"status": "active", "rationale": "kickoff"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "active"

    # 3. POST /advance to sources works.
    r = client.post(f"/engagements/{eid}/advance", headers=hdr,
                    json={"to_stage": "sources", "rationale": "have sources"})
    assert r.status_code == 200, r.text
    assert r.json()["stage"] == "sources"

    # 4. Skip-ahead rejected with 409.
    r = client.post(f"/engagements/{eid}/advance", headers=hdr,
                    json={"to_stage": "workshop", "rationale": "skip"})
    assert r.status_code == 409, r.text

    # 5. GET list includes the engagement.
    r = client.get("/engagements", headers=hdr)
    assert r.status_code == 200, r.text
    assert any(e["id"] == eid for e in r.json()["engagements"])

    # 6. POST /brief creates a BCB.
    r = client.post(f"/engagements/{eid}/brief", headers=hdr, json={
        "focal_asset": "drug:wegovy",
        "situation": "defense",
        "strategic_decisions": [
            {"statement": "Defend share post-MASH approval",
             "rationale": "Prevent payer carve-outs in first 6 months"},
        ],
        "competitive_set": [
            {"entity_ref": "company:lilly", "threat_level": "primary", "note": "tirzepatide"},
        ],
    })
    assert r.status_code == 201, r.text
    bid = r.json()["id"]
    assert r.json()["focal_asset"] == "drug:wegovy"

    # 7. GET /brief reads it back.
    r = client.get(f"/engagements/{eid}/brief", headers=hdr)
    assert r.status_code == 200, r.text
    assert r.json()["id"] == bid


# ──────────────────────────────────────────────────────────────────
# Auth tier tests
# ──────────────────────────────────────────────────────────────────

class TestAuthTiers:
    def test_create_engagement_401_anonymous(self):
        db, _, _, _ = _make_db()
        r = _client(db).post("/engagements", json={
            "name": "X", "asset": "drug:x", "situation": "defense",
        })
        assert r.status_code == 401

    def test_create_engagement_403_for_viewer(self):
        db, _, _, _ = _make_db()
        client = _client(db)
        tok = _login(client, "viewer@demo.market-zero.io")
        r = client.post("/engagements", headers=_hdr(tok), json={
            "name": "X", "asset": "drug:x", "situation": "defense",
        })
        assert r.status_code == 403

    def test_list_engagements_works_for_viewer(self):
        db, _, _, _ = _make_db()
        client = _client(db)
        tok = _login(client, "viewer@demo.market-zero.io")
        r = client.get("/engagements", headers=_hdr(tok))
        assert r.status_code == 200


# ──────────────────────────────────────────────────────────────────
# 404 / 400 / 409 mapping
# ──────────────────────────────────────────────────────────────────

class TestErrorMapping:
    def test_get_missing_engagement_404(self):
        db, _, _, _ = _make_db()
        client = _client(db)
        tok = _login(client, "uploader@demo.market-zero.io")
        r = client.get("/engagements/no-such-id", headers=_hdr(tok))
        assert r.status_code == 404

    def test_invalid_situation_400(self):
        db, _, _, _ = _make_db()
        client = _client(db)
        tok = _login(client, "uploader@demo.market-zero.io")
        r = client.post("/engagements", headers=_hdr(tok), json={
            "name": "X", "asset": "drug:x", "situation": "not-a-situation",
        })
        assert r.status_code == 400

    def test_empty_name_400(self):
        db, _, _, _ = _make_db()
        client = _client(db)
        tok = _login(client, "uploader@demo.market-zero.io")
        r = client.post("/engagements", headers=_hdr(tok), json={
            "name": "", "asset": "drug:x", "situation": "defense",
        })
        # Pydantic enforces min_length=1 → 422; service-level would be 400.
        assert r.status_code in (400, 422)

    def test_advance_missing_engagement_404(self):
        db, _, _, _ = _make_db()
        client = _client(db)
        tok = _login(client, "uploader@demo.market-zero.io")
        r = client.post("/engagements/missing/advance", headers=_hdr(tok),
                        json={"to_stage": "sources", "rationale": "x"})
        assert r.status_code == 404

    def test_bcb_empty_strategic_decisions_400(self):
        db, engagements, _, _ = _make_db()
        client = _client(db)
        tok = _login(client, "uploader@demo.market-zero.io")
        # Create an engagement first
        r = client.post("/engagements", headers=_hdr(tok), json={
            "name": "X", "asset": "drug:x", "situation": "defense",
        })
        eid = r.json()["id"]
        # Then a brief with empty strategic_decisions
        r = client.post(f"/engagements/{eid}/brief", headers=_hdr(tok), json={
            "focal_asset": "drug:x", "situation": "defense",
            "strategic_decisions": [], "competitive_set": [],
        })
        # Pydantic min_length=1 → 422
        assert r.status_code in (400, 422)


# ──────────────────────────────────────────────────────────────────
# Route registration
# ──────────────────────────────────────────────────────────────────

def test_engagements_routes_registered():
    from api.app import create_app
    app = create_app()
    paths = {getattr(r, "path", None) for r in app.routes}
    assert any(p and p.endswith("/engagements") for p in paths)
    assert any(p and p.endswith("/engagements/{eid}") for p in paths)
    assert any(p and p.endswith("/engagements/{eid}/advance") for p in paths)
    assert any(p and p.endswith("/engagements/{eid}/brief") for p in paths)
    assert any(p and p.endswith("/briefs/{bcb_id}/priority-matrix") for p in paths)
