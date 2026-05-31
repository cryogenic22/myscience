"""KB2 — Dossier Knowledge Base API tests.

Route-layer coverage over services/dossier_kb. Fake-db + auth pattern mirrors
test_engagements_api.py. Exercises: assemble (versioned), get latest, list
versions, coverage gaps, 404s, and auth tiers (viewer reads, uploader writes).
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient


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

    now = datetime(2026, 5, 31, tzinfo=timezone.utc)
    engagements = {
        "e1": {
            "id": "e1", "name": "Wegovy defense", "asset": "drug:wegovy",
            "sponsor": None, "situation": "defense", "workshop_date": None,
            "stage": "dossier", "status": "active", "scope": "{}",
            "created_by": "uuid-uploader", "created_at": now, "updated_at": now,
            "tenant_scope": None,
        }
    }
    facts = [
        {"id": "f1", "predicate": "wac_usd_monthly", "object_value": {"value": "675"},
         "fact_class": "corporate", "created_by": "data_automaton", "confidence": 0.95,
         "valid_from": None, "valid_to": None, "superseded_by": None},
        {"id": "f2", "predicate": "ma_deal", "object_value": {"value": "acquired X"},
         "fact_class": "corporate", "created_by": "sec_8k", "confidence": 0.9,
         "valid_from": None, "valid_to": None, "superseded_by": None},
    ]
    snapshots: list[dict] = []
    seq = {"n": 0}

    def fetch_one(sql, params=None):
        s = (sql or "").lower()
        # auth
        if "from users" in s and params:
            if "where lower(email)" in s or "where email" in s:
                return users.get(str(params[0]).lower())
            if "where id::text" in s or "where id =" in s:
                for u in users.values():
                    if u["id"] == params[0]:
                        return u
                return None
        # engagement lookup
        if "from engagements" in s and "where id" in s and params:
            key = params[0] if not isinstance(params, dict) else params.get("id")
            return engagements.get(str(key))
        # next version
        if "coalesce(max(version)" in s and params:
            eid = params[0]
            versions = [r["version"] for r in snapshots if r["engagement_id"] == eid]
            return {"v": max(versions) if versions else 0}
        # insert snapshot RETURNING
        if "insert into dossier_snapshots" in s and params:
            seq["n"] += 1
            new_id = f"snap-{seq['n']}"
            row = {
                "id": new_id, "engagement_id": params["engagement_id"],
                "focal_asset": params["focal_asset"], "version": params["version"],
                "domains": params["domains"], "coverage_score": params["coverage_score"],
                "fact_count": params["fact_count"], "assembled_by": params["assembled_by"],
                "assembled_at": now, "superseded_by": None,
            }
            snapshots.append(row)
            return {"id": new_id, "assembled_at": now}
        # latest head
        if "from dossier_snapshots" in s and "superseded_by is null" in s and params:
            eid = params[0]
            heads = [r for r in snapshots
                     if r["engagement_id"] == eid and r["superseded_by"] is None]
            heads.sort(key=lambda r: r["version"], reverse=True)
            return heads[0] if heads else None
        return None

    def fetch_all(sql, params=None):
        s = (sql or "").lower()
        if "from facts" in s:
            return list(facts)
        if "from dossier_snapshots" in s and params:
            eid = params[0]
            rows = [r for r in snapshots if r["engagement_id"] == eid]
            rows.sort(key=lambda r: r["version"], reverse=True)
            return [dict(r) for r in rows]
        return []

    def execute(sql, params=None):
        s = (sql or "").lower()
        if "set superseded_by" in s and params:
            new_id, eid, exclude_id = params
            for r in snapshots:
                if (r["engagement_id"] == eid and r["id"] != exclude_id
                        and r["superseded_by"] is None):
                    r["superseded_by"] = new_id

    from unittest.mock import MagicMock
    db = MagicMock()
    db.fetch_one.side_effect = fetch_one
    db.fetch_all.side_effect = fetch_all
    db.execute.side_effect = execute
    return db, snapshots


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


# ── Acceptance ─────────────────────────────────────────────────────


def test_acceptance_assemble_get_versions_gaps():
    db, _ = _make_db()
    client = _client(db)
    hdr = _hdr(_login(client, "uploader@demo.market-zero.io"))

    # No dossier yet → 404.
    r = client.get("/engagements/e1/dossier", headers=hdr)
    assert r.status_code == 404, r.text

    # Assemble v1.
    r = client.post("/engagements/e1/dossier/assemble", headers=hdr)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["version"] == 1
    assert body["focal_asset"] == "drug:wegovy"
    assert len(body["domains"]) == 8
    assert body["fact_count"] == 2
    assert 0 < body["coverage_score"] < 1
    # pricing + competitive both got a corporate fact.
    by = {d["domain"]: d for d in body["domains"]}
    assert by["pricing_and_access"]["facts"][0]["factClass"] == "corporate"
    assert by["competitive"]["facts"][0]["factClass"] == "corporate"

    # Assemble v2.
    r = client.post("/engagements/e1/dossier/assemble", headers=hdr)
    assert r.status_code == 201
    assert r.json()["version"] == 2

    # GET latest → v2.
    r = client.get("/engagements/e1/dossier", headers=hdr)
    assert r.status_code == 200, r.text
    assert r.json()["version"] == 2

    # Versions list → [2, 1].
    r = client.get("/engagements/e1/dossier/versions", headers=hdr)
    assert r.status_code == 200
    vs = r.json()
    assert vs["count"] == 2
    assert [v["version"] for v in vs["versions"]] == [2, 1]

    # Gaps → the un-evidenced domains, with coverage.
    r = client.get("/engagements/e1/dossier/gaps", headers=hdr)
    assert r.status_code == 200, r.text
    gaps = r.json()
    gap_domains = {g["domain"] for g in gaps["gaps"]}
    assert "pricing_and_access" not in gap_domains   # has a fact
    assert "disease_and_patient" in gap_domains        # empty
    assert "coverage_score" in gaps


def test_assemble_missing_engagement_404():
    db, _ = _make_db()
    client = _client(db)
    hdr = _hdr(_login(client, "uploader@demo.market-zero.io"))
    r = client.post("/engagements/nope/dossier/assemble", headers=hdr)
    assert r.status_code == 404, r.text


# ── Auth tiers ─────────────────────────────────────────────────────


def test_assemble_requires_uploader():
    db, _ = _make_db()
    client = _client(db)
    # anonymous
    assert client.post("/engagements/e1/dossier/assemble").status_code == 401
    # viewer forbidden
    hdr = _hdr(_login(client, "viewer@demo.market-zero.io"))
    assert client.post("/engagements/e1/dossier/assemble", headers=hdr).status_code == 403


def test_viewer_can_read_dossier():
    db, _ = _make_db()
    client = _client(db)
    up = _hdr(_login(client, "uploader@demo.market-zero.io"))
    client.post("/engagements/e1/dossier/assemble", headers=up)
    vh = _hdr(_login(client, "viewer@demo.market-zero.io"))
    r = client.get("/engagements/e1/dossier", headers=vh)
    assert r.status_code == 200, r.text
    assert r.json()["version"] == 1
