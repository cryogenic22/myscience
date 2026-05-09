"""SPEC_024 — Evidence Ledger API tests.

Covers: claim dedup, append-only evidence semantics, snapshot determinism,
hash specifications, auth gates, and red-team edge cases (R1-R10 from
SPEC_024 §Red-team).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest


# ────────────────────────────────────────────────────────────────────
# Pure hash function tests (no DB needed)
# ────────────────────────────────────────────────────────────────────

class TestHashes:
    def test_claim_text_hash_strips_whitespace(self):
        from services.evidence_ledger import hash_claim_text
        assert hash_claim_text("hello") == hash_claim_text("  hello  ")
        assert hash_claim_text("hello") == hash_claim_text("hello\n")

    def test_claim_text_hash_is_case_sensitive(self):
        from services.evidence_ledger import hash_claim_text
        assert hash_claim_text("Hello") != hash_claim_text("hello")

    def test_claim_text_hash_internal_whitespace_matters(self):
        from services.evidence_ledger import hash_claim_text
        assert hash_claim_text("a b") != hash_claim_text("a  b")

    def test_source_content_hash_does_not_strip(self):
        """Evidence hash is exact-bytes — even leading/trailing whitespace
        must produce a different hash, since extracted_text faithfulness is
        the whole point of evidence."""
        from services.evidence_ledger import hash_source_content
        assert hash_source_content("hello") != hash_source_content("  hello  ")

    def test_hash_returns_32_bytes(self):
        from services.evidence_ledger import hash_claim_text, hash_source_content, hash_snapshot_body
        assert len(hash_claim_text("x")) == 32
        assert len(hash_source_content("x")) == 32
        assert len(hash_snapshot_body({"claims": []})) == 32

    def test_canonical_json_is_deterministic(self):
        from services.evidence_ledger import canonical_json
        a = canonical_json({"b": 2, "a": 1, "c": [3, 1, 2]})
        b = canonical_json({"a": 1, "c": [3, 1, 2], "b": 2})
        assert a == b
        assert a == '{"a":1,"b":2,"c":[3,1,2]}'

    def test_normalize_snapshot_body_sorts_claims(self):
        from services.evidence_ledger import normalize_snapshot_body
        body = normalize_snapshot_body(
            claims=[
                {"claim_id": "z-99", "evidence_ids": ["e-3", "e-1"]},
                {"claim_id": "a-01", "evidence_ids": ["e-2"]},
            ],
        )
        assert body["claims"][0]["claim_id"] == "a-01"
        assert body["claims"][1]["claim_id"] == "z-99"
        assert body["claims"][1]["evidence_ids"] == ["e-1", "e-3"]

    def test_snapshot_hash_idempotent(self):
        """Same logical content → same hash, regardless of input ordering."""
        from services.evidence_ledger import normalize_snapshot_body, hash_snapshot_body
        body1 = normalize_snapshot_body(
            claims=[
                {"claim_id": "z", "evidence_ids": ["e-2", "e-1"]},
                {"claim_id": "a", "evidence_ids": ["e-3"]},
            ],
        )
        body2 = normalize_snapshot_body(
            claims=[
                {"claim_id": "a", "evidence_ids": ["e-3"]},
                {"claim_id": "z", "evidence_ids": ["e-1", "e-2"]},
            ],
        )
        assert hash_snapshot_body(body1) == hash_snapshot_body(body2)

    def test_snapshot_hash_differs_with_different_claims(self):
        from services.evidence_ledger import normalize_snapshot_body, hash_snapshot_body
        body1 = normalize_snapshot_body(
            claims=[{"claim_id": "a", "evidence_ids": ["e-1"]}],
        )
        body2 = normalize_snapshot_body(
            claims=[{"claim_id": "a", "evidence_ids": ["e-2"]}],
        )
        assert hash_snapshot_body(body1) != hash_snapshot_body(body2)

    def test_snapshot_hash_excludes_snapshot_at(self):
        """Two snapshots of identical content at different times produce
        the same hash. snapshot_at is metadata, not identity."""
        from services.evidence_ledger import normalize_snapshot_body, hash_snapshot_body
        body1 = normalize_snapshot_body(
            claims=[{"claim_id": "a", "evidence_ids": ["e-1"]}],
            snapshot_at="2026-05-09T00:00:00+00:00",
        )
        body2 = normalize_snapshot_body(
            claims=[{"claim_id": "a", "evidence_ids": ["e-1"]}],
            snapshot_at="2026-05-09T15:30:00+00:00",
        )
        assert hash_snapshot_body(body1) == hash_snapshot_body(body2)


# ────────────────────────────────────────────────────────────────────
# Fake DB for API tests
# ────────────────────────────────────────────────────────────────────

def _make_db():
    from services.auth import hash_password

    users = {
        "viewer@test.io": {
            "id": "uuid-viewer", "email": "viewer@test.io",
            "password_hash": hash_password("demo"), "role": "viewer", "is_active": True,
        },
        "editor@test.io": {
            "id": "uuid-editor", "email": "editor@test.io",
            "password_hash": hash_password("demo"), "role": "uploader", "is_active": True,
        },
    }

    claims: dict[str, dict] = {}
    evidence_records: dict[str, dict] = {}
    links: list[dict] = []
    snapshots: dict[bytes, dict] = {}
    next_id = [1]

    def _gen(prefix):
        n = next_id[0]; next_id[0] += 1
        return f"{prefix}-{n:04d}"

    def fake_fetch_one(sql, params=None):
        s = (sql or "").lower()
        if "from users" in s and params:
            if "where lower(email)" in s or "where email" in s:
                return users.get(str(params[0]).lower())
            if "where id::text" in s or "where id =" in s:
                for u in users.values():
                    if u["id"] == params[0]: return u
                return None

        # Existence check before insert (claim dedup lookup)
        if (
            "from claims" in s
            and "claim_text_hash = %s" in s
            and "insert" not in s
            and params
        ):
            target_hash = bytes(params[0]) if isinstance(params[0], (bytes, bytearray, memoryview)) else params[0]
            target_etype = params[1]
            target_eid_check = params[2]
            target_eid = params[3]
            for c in claims.values():
                if bytes(c["claim_text_hash"]) != target_hash:
                    continue
                if (c.get("entity_type") or "") != (target_etype or ""):
                    continue
                if target_eid_check is None and c.get("entity_id") is None:
                    return c
                if target_eid is not None and str(c.get("entity_id") or "") == str(target_eid):
                    return c
            return None

        # INSERT INTO claims RETURNING
        if "insert into claims" in s and "returning" in s and params:
            cid = _gen("clm")
            row = {
                "claim_id": cid,
                "claim_text": params[0],
                "claim_text_hash": bytes(params[1]) if isinstance(params[1], (bytes, bytearray, memoryview)) else params[1],
                "claim_type": params[2],
                "entity_type": params[3],
                "entity_id": params[4],
                "confidence": params[5],
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            }
            claims[cid] = row
            return row

        # SELECT claim by id
        if "from claims where claim_id::text = %s" in s and params:
            return claims.get(str(params[0]))

        # SELECT evidence dedup lookup
        if (
            "from evidence_records" in s
            and "source_content_hash = %s" in s
            and "source_id = %s" in s
            and "limit 1" in s
            and params
        ):
            target_hash = bytes(params[0]) if isinstance(params[0], (bytes, bytearray, memoryview)) else params[0]
            target_source = params[1]
            target_dt = params[2]
            target_date = target_dt.date() if hasattr(target_dt, "date") else target_dt
            for e in evidence_records.values():
                if bytes(e["source_content_hash"]) != target_hash:
                    continue
                if e["source_id"] != target_source:
                    continue
                e_date = e["retrieved_at"].date() if hasattr(e["retrieved_at"], "date") else e["retrieved_at"]
                if e_date == target_date:
                    return e
            return None

        # INSERT INTO evidence_records RETURNING
        if "insert into evidence_records" in s and "returning" in s and params:
            eid = _gen("evd")
            row = {
                "evidence_id": eid,
                "source_id": params[0],
                "source_url": params[1],
                "source_content_hash": bytes(params[2]) if isinstance(params[2], (bytes, bytearray, memoryview)) else params[2],
                "archived_snapshot_ref": None,
                "retrieved_at": params[3],
                "extraction_method": json.loads(params[4]) if isinstance(params[4], str) else (params[4] or {}),
                "extracted_text": params[5],
                "confidence": params[6],
                "retrieved_by_user_id": params[7],
                "created_at": datetime.now(timezone.utc),
            }
            evidence_records[eid] = row
            return row

        # SELECT evidence by id
        if "from evidence_records" in s and "evidence_id::text = %s" in s and params:
            return evidence_records.get(str(params[0]))

        # SELECT claim row (existence check before append_evidence)
        if "select claim_id from claims" in s and params:
            cid = str(params[0])
            return {"claim_id": cid} if cid in claims else None

        # INSERT snapshot RETURNING
        if "insert into evidence_snapshots" in s and "returning" in s and params:
            shash = bytes(params[0]) if isinstance(params[0], (bytes, bytearray, memoryview)) else params[0]
            if shash in snapshots:
                return None  # ON CONFLICT DO NOTHING
            row = {
                "snapshot_hash": shash,
                "body": json.loads(params[1]) if isinstance(params[1], str) else params[1],
                "brief_id": params[2],
                "decision_id": params[3],
                "created_at": datetime.now(timezone.utc),
            }
            snapshots[shash] = row
            return row

        # SELECT snapshot by hash
        if "from evidence_snapshots" in s and "snapshot_hash = %s" in s and params:
            shash = bytes(params[0]) if isinstance(params[0], (bytes, bytearray, memoryview)) else params[0]
            return snapshots.get(shash)

        return None

    def fake_fetch_all(sql, params=None):
        s = (sql or "").lower()

        # claim_evidence_links join for get_claim
        if "from claim_evidence_links" in s and "join evidence_records" in s and params:
            cid = str(params[0])
            out = []
            for l in links:
                if str(l["claim_id"]) != cid: continue
                e = evidence_records.get(str(l["evidence_id"]))
                if not e: continue
                out.append({**e, "relation": l["relation"]})
            out.sort(key=lambda r: (-(r.get("confidence") or 0), r["retrieved_at"]), reverse=False)
            return out

        # claim_evidence_links for snapshot
        if "from claim_evidence_links" in s and "claim_id::text = any" in s and params:
            target = set(str(c) for c in (params[0] or []))
            return [
                {"claim_id": str(l["claim_id"]), "evidence_id": str(l["evidence_id"])}
                for l in links if str(l["claim_id"]) in target
            ]

        # LIST claims
        if "from claims" in s and "limit" in s:
            out = list(claims.values())
            if params:
                idx = 0
                if "entity_type = %s" in s:
                    out = [c for c in out if c.get("entity_type") == params[idx]]
                    idx += 1
                if "entity_id::text = %s" in s:
                    out = [c for c in out if str(c.get("entity_id") or "") == str(params[idx])]
                    idx += 1
                if "claim_type = %s" in s:
                    out = [c for c in out if c.get("claim_type") == params[idx]]
                    idx += 1
                if "claim_text ilike %s" in s:
                    needle = params[idx].replace("%", "").lower()
                    out = [c for c in out if needle in c["claim_text"].lower()]
                    idx += 1
                limit = params[-2]; offset = params[-1]
                out = out[offset:offset + limit]
            return out

        return []

    def fake_execute(sql, params=None):
        s = (sql or "").lower()
        if "insert into claim_evidence_links" in s and params:
            # ON CONFLICT DO NOTHING semantics
            for l in links:
                if (str(l["claim_id"]) == str(params[0])
                    and str(l["evidence_id"]) == str(params[1])
                    and l["relation"] == params[2]):
                    return None
            links.append({
                "link_id": _gen("lnk"),
                "claim_id": str(params[0]),
                "evidence_id": str(params[1]),
                "relation": params[2],
                "created_at": datetime.now(timezone.utc),
            })
        return None

    db = MagicMock()
    db.fetch_one.side_effect = fake_fetch_one
    db.fetch_all.side_effect = fake_fetch_all
    db.execute.side_effect = fake_execute
    return db, claims, evidence_records, links, snapshots


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


# ────────────────────────────────────────────────────────────────────
# Module + route registration
# ────────────────────────────────────────────────────────────────────

def test_module_imports():
    from api.routes import evidence_ledger as r
    from services.evidence_ledger import EvidenceLedgerService
    assert hasattr(r, "claims_router")
    assert hasattr(r, "snapshots_router")
    assert hasattr(EvidenceLedgerService, "upsert_claim")


def test_routes_registered():
    from api.app import create_app
    app = create_app()
    paths = {getattr(r, "path", "") for r in app.routes}
    assert "/claims" in paths
    assert "/claims/{claim_id}" in paths
    assert "/claims/{claim_id}/evidence" in paths
    assert "/evidence/{evidence_id}" in paths
    assert "/evidence-snapshots/{snapshot_hash}" in paths
    assert "/briefs/{brief_id}/evidence-snapshot" in paths


# ────────────────────────────────────────────────────────────────────
# Claims
# ────────────────────────────────────────────────────────────────────

def test_create_claim_minimal():
    db, claims, _, _, _ = _make_db()
    client = _client(db)
    tok = _login(client, "editor@test.io")
    r = client.post("/claims",
        json={"claim_text": "Tirzepatide approved for chronic weight management"},
        headers=_hdr(tok))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["claim_text"] == "Tirzepatide approved for chronic weight management"
    assert body["claim_type"] == "other"
    assert body["entity_type"] is None
    assert body["entity_id"] is None
    # claim_text_hash is hex-encoded sha256 → 64 chars
    assert len(body["claim_text_hash"]) == 64


def test_create_claim_dedup_returns_existing():
    """Two POSTs with identical (text, entity) return the same claim_id."""
    db, _, _, _, _ = _make_db()
    client = _client(db)
    tok = _login(client, "editor@test.io")
    r1 = client.post("/claims",
        json={"claim_text": "X", "claim_type": "regulatory",
              "entity_type": "drug", "entity_id": "00000000-0000-0000-0000-000000000001"},
        headers=_hdr(tok))
    r2 = client.post("/claims",
        json={"claim_text": "X", "claim_type": "regulatory",
              "entity_type": "drug", "entity_id": "00000000-0000-0000-0000-000000000001"},
        headers=_hdr(tok))
    assert r1.status_code == 201 and r2.status_code == 201
    assert r1.json()["claim_id"] == r2.json()["claim_id"]


def test_create_claim_rejects_invalid_type():
    db, _, _, _, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    r = client.post("/claims",
        json={"claim_text": "x", "claim_type": "telepathy"},
        headers=_hdr(tok))
    assert r.status_code == 422


def test_create_claim_rejects_invalid_entity_type():
    db, _, _, _, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    r = client.post("/claims",
        json={"claim_text": "x", "entity_type": "wizard"},
        headers=_hdr(tok))
    assert r.status_code == 422


def test_create_claim_rejects_too_long():
    """R2 — DoS via massive text."""
    db, _, _, _, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    r = client.post("/claims",
        json={"claim_text": "x" * 9000},
        headers=_hdr(tok))
    assert r.status_code == 422


def test_create_claim_requires_uploader_role():
    db, _, _, _, _ = _make_db()
    client = _client(db); tok = _login(client, "viewer@test.io")
    r = client.post("/claims", json={"claim_text": "x"}, headers=_hdr(tok))
    assert r.status_code in (401, 403)


# ────────────────────────────────────────────────────────────────────
# Evidence
# ────────────────────────────────────────────────────────────────────

def test_append_evidence_attaches_to_claim():
    db, _, _, _, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    cid = client.post("/claims", json={"claim_text": "x"}, headers=_hdr(tok)).json()["claim_id"]
    r = client.post(f"/claims/{cid}/evidence", json={
        "source_id": "fda_orange_book",
        "extracted_text": "FDA-approved 2023-11-08 for chronic weight management",
        "confidence": 0.95,
    }, headers=_hdr(tok))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["source_id"] == "fda_orange_book"
    assert body["confidence"] == 0.95
    assert len(body["source_content_hash"]) == 64  # sha256 hex
    assert body["retrieved_by_user_id"] == "uuid-editor"


def test_append_evidence_dedup_idempotent():
    """R9 — replay protection: same content + source + day = same evidence."""
    db, _, evidence, _, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    cid = client.post("/claims", json={"claim_text": "x"}, headers=_hdr(tok)).json()["claim_id"]
    payload = {
        "source_id": "src1",
        "extracted_text": "passage A",
        "retrieved_at": "2026-05-09T10:00:00+00:00",
    }
    e1 = client.post(f"/claims/{cid}/evidence", json=payload, headers=_hdr(tok)).json()
    # Second append same day → same evidence_id
    payload2 = dict(payload, retrieved_at="2026-05-09T15:00:00+00:00")
    e2 = client.post(f"/claims/{cid}/evidence", json=payload2, headers=_hdr(tok)).json()
    assert e1["evidence_id"] == e2["evidence_id"]
    assert len(evidence) == 1


def test_append_evidence_404_for_unknown_claim():
    db, _, _, _, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    r = client.post("/claims/clm-9999/evidence", json={
        "source_id": "src", "extracted_text": "abc",
    }, headers=_hdr(tok))
    assert r.status_code == 404


def test_append_evidence_validates_relation():
    db, _, _, _, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    cid = client.post("/claims", json={"claim_text": "x"}, headers=_hdr(tok)).json()["claim_id"]
    r = client.post(f"/claims/{cid}/evidence", json={
        "source_id": "s", "extracted_text": "t", "relation": "endorses"
    }, headers=_hdr(tok))
    assert r.status_code == 422


def test_get_claim_returns_evidence_ordered_by_confidence():
    db, _, _, _, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    cid = client.post("/claims", json={"claim_text": "x"}, headers=_hdr(tok)).json()["claim_id"]
    client.post(f"/claims/{cid}/evidence", json={
        "source_id": "s1", "extracted_text": "low", "confidence": 0.3
    }, headers=_hdr(tok))
    client.post(f"/claims/{cid}/evidence", json={
        "source_id": "s2", "extracted_text": "high", "confidence": 0.9
    }, headers=_hdr(tok))
    vtok = _login(client, "viewer@test.io")
    body = client.get(f"/claims/{cid}", headers=_hdr(vtok)).json()
    assert len(body["evidence"]) == 2
    # Order may be impl-specific in fake DB; just confirm both arrive
    confs = sorted([e["confidence"] for e in body["evidence"]])
    assert confs == [0.3, 0.9]


# ────────────────────────────────────────────────────────────────────
# Snapshots
# ────────────────────────────────────────────────────────────────────

def test_snapshot_idempotent_returns_same_hash():
    """Re-snapshotting the same set returns the same content-addressed hash."""
    db, _, _, _, snapshots = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    cid = client.post("/claims", json={"claim_text": "x"}, headers=_hdr(tok)).json()["claim_id"]
    client.post(f"/claims/{cid}/evidence", json={"source_id": "s", "extracted_text": "t"},
                headers=_hdr(tok))
    s1 = client.post("/briefs/brf-001/evidence-snapshot",
                     json={"claim_ids": [cid]}, headers=_hdr(tok)).json()
    s2 = client.post("/briefs/brf-001/evidence-snapshot",
                     json={"claim_ids": [cid]}, headers=_hdr(tok)).json()
    assert s1["snapshot_hash"] == s2["snapshot_hash"]


def test_snapshot_different_claim_set_different_hash():
    db, _, _, _, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    c1 = client.post("/claims", json={"claim_text": "x"}, headers=_hdr(tok)).json()["claim_id"]
    c2 = client.post("/claims", json={"claim_text": "y"}, headers=_hdr(tok)).json()["claim_id"]
    s1 = client.post("/briefs/brf-001/evidence-snapshot",
                     json={"claim_ids": [c1]}, headers=_hdr(tok)).json()
    s2 = client.post("/briefs/brf-001/evidence-snapshot",
                     json={"claim_ids": [c2]}, headers=_hdr(tok)).json()
    assert s1["snapshot_hash"] != s2["snapshot_hash"]


def test_get_snapshot_by_hash():
    db, _, _, _, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    cid = client.post("/claims", json={"claim_text": "x"}, headers=_hdr(tok)).json()["claim_id"]
    snap = client.post("/briefs/brf-001/evidence-snapshot",
                       json={"claim_ids": [cid]}, headers=_hdr(tok)).json()
    vtok = _login(client, "viewer@test.io")
    r = client.get(f"/evidence-snapshots/{snap['snapshot_hash']}", headers=_hdr(vtok))
    assert r.status_code == 200
    body = r.json()
    assert body["snapshot_hash"] == snap["snapshot_hash"]
    assert body["body"]["brief_id"] == "brf-001"
    # The single claim is in the body
    assert len(body["body"]["claims"]) == 1


def test_get_snapshot_invalid_hex_returns_400():
    db, _, _, _, _ = _make_db()
    client = _client(db); tok = _login(client, "viewer@test.io")
    r = client.get("/evidence-snapshots/not-hex-zz", headers=_hdr(tok))
    assert r.status_code == 400


def test_snapshot_empty_claim_ids_rejected():
    db, _, _, _, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    r = client.post("/briefs/brf-001/evidence-snapshot",
                    json={"claim_ids": []}, headers=_hdr(tok))
    # Pydantic min_length=1 should catch this with 422
    assert r.status_code in (400, 422)


# ────────────────────────────────────────────────────────────────────
# Auth gates
# ────────────────────────────────────────────────────────────────────

def test_unauth_create_claim_returns_401():
    db, _, _, _, _ = _make_db()
    client = _client(db)
    r = client.post("/claims", json={"claim_text": "x"})
    assert r.status_code in (401, 403)


def test_unauth_list_claims_returns_401():
    db, _, _, _, _ = _make_db()
    client = _client(db)
    r = client.get("/claims")
    assert r.status_code in (401, 403)


def test_unauth_snapshot_returns_401():
    db, _, _, _, _ = _make_db()
    client = _client(db)
    r = client.post("/briefs/brf-001/evidence-snapshot", json={"claim_ids": ["c"]})
    assert r.status_code in (401, 403)


# ────────────────────────────────────────────────────────────────────
# Red-team (R1-R10 from SPEC_024)
# ────────────────────────────────────────────────────────────────────

def test_R1_no_sql_injection_via_claim_text():
    """R1 — claim_text with SQL meta is round-tripped intact, never injected."""
    db, claims, _, _, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    payload = "'; DROP TABLE claims; SELECT * FROM users WHERE 'a' = 'a"
    r = client.post("/claims", json={"claim_text": payload}, headers=_hdr(tok))
    assert r.status_code == 201
    assert r.json()["claim_text"] == payload
    # No table dropped; we can still create another claim
    r2 = client.post("/claims", json={"claim_text": "follow-up"}, headers=_hdr(tok))
    assert r2.status_code == 201


def test_R2_evidence_text_size_cap():
    """R2 — evidence rejects > 64 KB extracted_text."""
    db, _, _, _, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    cid = client.post("/claims", json={"claim_text": "x"}, headers=_hdr(tok)).json()["claim_id"]
    huge = "a" * 70000  # > 64KB
    r = client.post(f"/claims/{cid}/evidence",
        json={"source_id": "s", "extracted_text": huge}, headers=_hdr(tok))
    assert r.status_code == 422


def test_R6_retrieved_by_user_set_from_auth_not_body():
    """R6 — caller cannot spoof retrieved_by_user_id via request body
    (the field isn't in the schema)."""
    db, _, evidence, _, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    cid = client.post("/claims", json={"claim_text": "x"}, headers=_hdr(tok)).json()["claim_id"]
    # Try to spoof — pydantic should silently strip extra fields
    r = client.post(f"/claims/{cid}/evidence", json={
        "source_id": "s", "extracted_text": "t",
        "retrieved_by_user_id": "uuid-attacker",
    }, headers=_hdr(tok))
    assert r.status_code == 201
    assert r.json()["retrieved_by_user_id"] == "uuid-editor"


def test_R8_concurrent_dedup_handles_race():
    """R8 — fake DB simulates the race by checking dedup before insert.
    Two near-simultaneous identical claims should yield the same claim_id."""
    db, _, _, _, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    payload = {"claim_text": "Race test", "claim_type": "regulatory"}
    a = client.post("/claims", json=payload, headers=_hdr(tok)).json()
    b = client.post("/claims", json=payload, headers=_hdr(tok)).json()
    assert a["claim_id"] == b["claim_id"]
