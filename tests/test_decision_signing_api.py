"""SPEC_034 — Decision Signing tests.

Covers: deterministic snapshot hash + signature, ownership enforcement,
re-sign rules, replay bundle shape, signature tampering detection,
auth gates, red-team.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest


# ════════════════════════════════════════════════════════════════════
# Pure crypto/math
# ════════════════════════════════════════════════════════════════════

class TestSnapshotHash:
    def test_deterministic_across_orderings(self):
        from services.decision_signing import compute_snapshot_hash
        a = compute_snapshot_hash(decision_id="dec-1",
                                  claim_ids=["c-2", "c-1", "c-3"])
        b = compute_snapshot_hash(decision_id="dec-1",
                                  claim_ids=["c-3", "c-1", "c-2"])
        assert a == b

    def test_different_claim_set_different_hash(self):
        from services.decision_signing import compute_snapshot_hash
        a = compute_snapshot_hash(decision_id="dec-1", claim_ids=["c-1"])
        b = compute_snapshot_hash(decision_id="dec-1", claim_ids=["c-2"])
        assert a != b

    def test_returns_32_bytes(self):
        from services.decision_signing import compute_snapshot_hash
        h = compute_snapshot_hash(decision_id="dec-1", claim_ids=["c-1"])
        assert len(h) == 32

    def test_different_decision_id_different_hash(self):
        from services.decision_signing import compute_snapshot_hash
        a = compute_snapshot_hash(decision_id="dec-1", claim_ids=["c-1"])
        b = compute_snapshot_hash(decision_id="dec-2", claim_ids=["c-1"])
        assert a != b

    def test_brief_id_changes_hash(self):
        from services.decision_signing import compute_snapshot_hash
        a = compute_snapshot_hash(decision_id="dec-1", claim_ids=["c-1"])
        b = compute_snapshot_hash(decision_id="dec-1", claim_ids=["c-1"], brief_id="brf-1")
        assert a != b


class TestSignatureMath:
    def _payload(self, **overrides):
        base = {
            "decision_id": "dec-1",
            "title": "Test decision",
            "rationale": "because",
            "owner_user_id": "user-1",
            "target_metric": "share",
            "target_value": "+5pp",
            "deadline": "2026-12-31",
            "confidence_at_commit": 0.8,
            "evidence_snapshot_hash": "abc123",
            "signing_algo": "hmac-sha256-v1",
            "signed_at": "2026-05-09T00:00:00+00:00",
            "signing_user_id": "user-1",
        }
        base.update(overrides)
        return base

    def test_signature_deterministic(self):
        from services.decision_signing import compute_signature
        s1 = compute_signature(self._payload(), secret=b"test-secret")
        s2 = compute_signature(self._payload(), secret=b"test-secret")
        assert s1 == s2

    def test_signature_returns_32_bytes(self):
        from services.decision_signing import compute_signature
        s = compute_signature(self._payload(), secret=b"test-secret")
        assert len(s) == 32

    def test_signature_changes_when_payload_field_changes(self):
        from services.decision_signing import compute_signature
        s1 = compute_signature(self._payload(), secret=b"test-secret")
        s2 = compute_signature(self._payload(title="DIFFERENT"), secret=b"test-secret")
        assert s1 != s2

    def test_verify_returns_true_for_matching(self):
        from services.decision_signing import compute_signature, verify_signature
        p = self._payload()
        s = compute_signature(p, secret=b"test-secret")
        assert verify_signature(p, s, secret=b"test-secret") is True

    def test_verify_returns_false_for_tampered_field(self):
        from services.decision_signing import compute_signature, verify_signature
        p = self._payload()
        s = compute_signature(p, secret=b"test-secret")
        p["title"] = "TAMPERED"
        assert verify_signature(p, s, secret=b"test-secret") is False

    def test_verify_returns_false_for_wrong_secret(self):
        from services.decision_signing import compute_signature, verify_signature
        p = self._payload()
        s = compute_signature(p, secret=b"secret-A")
        assert verify_signature(p, s, secret=b"secret-B") is False


class TestServerSecret:
    def test_falls_back_to_dev_constant_when_env_missing(self, monkeypatch):
        from services.decision_signing import get_server_secret, DEV_FALLBACK_SECRET
        monkeypatch.delenv("MZ_DECISION_SIGNING_SECRET", raising=False)
        secret = get_server_secret()
        assert secret == DEV_FALLBACK_SECRET.encode("utf-8")

    def test_uses_env_when_present(self, monkeypatch):
        from services.decision_signing import get_server_secret
        monkeypatch.setenv("MZ_DECISION_SIGNING_SECRET", "real-secret-xyz")
        secret = get_server_secret()
        assert secret == b"real-secret-xyz"


# ════════════════════════════════════════════════════════════════════
# Fake DB
# ════════════════════════════════════════════════════════════════════

def _make_db(*, decisions=None):
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
        "other@test.io": {
            "id": "uuid-other", "email": "other@test.io",
            "password_hash": hash_password("demo"), "role": "uploader", "is_active": True,
        },
    }

    decisions_db: dict[str, dict] = {}
    for d in (decisions or []):
        decisions_db[str(d["id"])] = dict(d)

    def fake_fetch_one(sql, params=None):
        s = (sql or "").lower()
        if "from users" in s and params:
            if "where lower(email)" in s or "where email" in s:
                return users.get(str(params[0]).lower())
            if "where id::text" in s or "where id =" in s:
                for u in users.values():
                    if u["id"] == params[0]: return u
                return None

        if "from decisions" in s and "where id::text = %s" in s and params:
            return decisions_db.get(str(params[0]))

        return None

    def fake_fetch_all(sql, params=None):
        return []

    def fake_execute(sql, params=None):
        s = (sql or "").lower()
        if "update decisions" in s and "where id::text = %s" in s and params:
            did = str(params[-1])
            if did not in decisions_db: return None
            d = decisions_db[did]
            d["evidence_snapshot_hash"] = bytes(params[0]) if isinstance(params[0], (bytes, bytearray, memoryview)) else params[0]
            d["signature"] = bytes(params[1]) if isinstance(params[1], (bytes, bytearray, memoryview)) else params[1]
            d["signing_algo"] = params[2]
            d["signed_at"] = params[3]
            d["signing_user_id"] = params[4]
            md = params[5]
            d["signing_metadata_jsonb"] = json.loads(md) if isinstance(md, str) else (md or {})
            return None
        return None

    db = MagicMock()
    db.fetch_one.side_effect = fake_fetch_one
    db.fetch_all.side_effect = fake_fetch_all
    db.execute.side_effect = fake_execute
    return db, decisions_db


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


def _seed_decision(owner="uuid-editor"):
    return {
        "id": "dec-001",
        "title": "Accelerate Phase 3", "rationale": "Material readout window",
        "owner_user_id": owner, "owner_display_name": "Editor",
        "target_metric": "share", "target_value": "+5pp",
        "deadline": None, "confidence_at_commit": 0.74,
        "status": "open", "actual_outcome": None, "calibration_score": None,
        "war_room_id": None, "source_signal_id": None,
        "evidence_snapshot_hash": None, "signature": None,
        "signing_algo": None, "signed_at": None, "signing_user_id": None,
        "signing_metadata_jsonb": None,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }


# ════════════════════════════════════════════════════════════════════
# Routes registered
# ════════════════════════════════════════════════════════════════════

def test_module_imports():
    from api.routes import decision_signing as r
    from services.decision_signing import DecisionSigningService
    assert r.router.prefix == "/decisions"


def test_routes_registered():
    from api.app import create_app
    app = create_app()
    paths = {getattr(r, "path", "") for r in app.routes}
    assert "/decisions/{decision_id}/sign" in paths
    assert "/decisions/{decision_id}/replay" in paths
    assert "/decisions/{decision_id}/verify" in paths


# ════════════════════════════════════════════════════════════════════
# Sign endpoint
# ════════════════════════════════════════════════════════════════════

def test_sign_succeeds_for_owner():
    db, decisions_db = _make_db(decisions=[_seed_decision()])
    client = _client(db); tok = _login(client, "editor@test.io")
    r = client.post("/decisions/dec-001/sign", json={
        "claim_ids": ["c-1", "c-2", "c-3"],
    }, headers=_hdr(tok))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["signing_algo"] == "hmac-sha256-v1"
    assert len(body["snapshot_hash"]) == 64  # sha256 hex
    assert len(body["signature"]) == 64
    assert decisions_db["dec-001"]["signature"] is not None


def test_sign_rejects_non_owner_with_403():
    db, _ = _make_db(decisions=[_seed_decision(owner="uuid-other")])
    client = _client(db); tok = _login(client, "editor@test.io")  # not owner
    r = client.post("/decisions/dec-001/sign", json={
        "claim_ids": ["c-1"],
    }, headers=_hdr(tok))
    assert r.status_code == 403


def test_sign_404_for_unknown():
    db, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    r = client.post("/decisions/nope/sign", json={"claim_ids": ["c-1"]},
                    headers=_hdr(tok))
    assert r.status_code == 404


def test_sign_rejects_re_sign_without_force():
    db, decisions_db = _make_db(decisions=[_seed_decision()])
    client = _client(db); tok = _login(client, "editor@test.io")
    client.post("/decisions/dec-001/sign", json={"claim_ids": ["c-1"]},
                headers=_hdr(tok))
    r = client.post("/decisions/dec-001/sign", json={"claim_ids": ["c-2"]},
                    headers=_hdr(tok))
    assert r.status_code == 409


def test_sign_with_force_replaces_signature():
    db, decisions_db = _make_db(decisions=[_seed_decision()])
    client = _client(db); tok = _login(client, "editor@test.io")
    s1 = client.post("/decisions/dec-001/sign",
                     json={"claim_ids": ["c-1"]}, headers=_hdr(tok)).json()
    s2 = client.post("/decisions/dec-001/sign",
                     json={"claim_ids": ["c-2"], "force": True},
                     headers=_hdr(tok)).json()
    assert s1["signature"] != s2["signature"]
    assert s1["snapshot_hash"] != s2["snapshot_hash"]


def test_sign_rejects_empty_claim_ids():
    db, _ = _make_db(decisions=[_seed_decision()])
    client = _client(db); tok = _login(client, "editor@test.io")
    r = client.post("/decisions/dec-001/sign", json={"claim_ids": []},
                    headers=_hdr(tok))
    # pydantic min_length=1
    assert r.status_code == 422


# ════════════════════════════════════════════════════════════════════
# Verify endpoint
# ════════════════════════════════════════════════════════════════════

def test_verify_returns_true_for_unmodified_decision():
    db, _ = _make_db(decisions=[_seed_decision()])
    client = _client(db); tok = _login(client, "editor@test.io")
    client.post("/decisions/dec-001/sign", json={"claim_ids": ["c-1"]},
                headers=_hdr(tok))

    vtok = _login(client, "viewer@test.io")
    r = client.get("/decisions/dec-001/verify", headers=_hdr(vtok))
    assert r.status_code == 200
    assert r.json()["valid"] is True


def test_verify_returns_false_after_field_tampering():
    db, decisions_db = _make_db(decisions=[_seed_decision()])
    client = _client(db); tok = _login(client, "editor@test.io")
    client.post("/decisions/dec-001/sign", json={"claim_ids": ["c-1"]},
                headers=_hdr(tok))

    # Tamper with the title in the DB directly
    decisions_db["dec-001"]["title"] = "TAMPERED TITLE"

    vtok = _login(client, "viewer@test.io")
    r = client.get("/decisions/dec-001/verify", headers=_hdr(vtok))
    assert r.status_code == 200
    assert r.json()["valid"] is False


def test_verify_409_for_unsigned_decision():
    db, _ = _make_db(decisions=[_seed_decision()])
    client = _client(db); tok = _login(client, "viewer@test.io")
    r = client.get("/decisions/dec-001/verify", headers=_hdr(tok))
    assert r.status_code == 409


def test_verify_404_for_unknown():
    db, _ = _make_db()
    client = _client(db); tok = _login(client, "viewer@test.io")
    r = client.get("/decisions/nope/verify", headers=_hdr(tok))
    assert r.status_code == 404


# ════════════════════════════════════════════════════════════════════
# Replay endpoint
# ════════════════════════════════════════════════════════════════════

def test_replay_returns_full_bundle():
    db, _ = _make_db(decisions=[_seed_decision()])
    client = _client(db); tok = _login(client, "editor@test.io")
    client.post("/decisions/dec-001/sign", json={
        "claim_ids": ["c-1", "c-2"], "brief_id": "brf-001",
    }, headers=_hdr(tok))

    vtok = _login(client, "viewer@test.io")
    r = client.get("/decisions/dec-001/replay", headers=_hdr(vtok))
    assert r.status_code == 200
    body = r.json()
    assert body["decision"]["decision_id"] == "dec-001"
    assert body["evidence_snapshot"]["claim_ids"] == ["c-1", "c-2"]
    assert body["evidence_snapshot"]["brief_id"] == "brf-001"
    assert body["signature"]["algo"] == "hmac-sha256-v1"
    # Without SPEC-024 ledger present, claims/evidence_records are empty arrays
    assert isinstance(body["claims"], list)
    assert isinstance(body["evidence_records"], list)
    assert isinstance(body["llm_calls"], list)


def test_replay_409_for_unsigned():
    db, _ = _make_db(decisions=[_seed_decision()])
    client = _client(db); tok = _login(client, "viewer@test.io")
    r = client.get("/decisions/dec-001/replay", headers=_hdr(tok))
    assert r.status_code == 409


def test_replay_404_for_unknown():
    db, _ = _make_db()
    client = _client(db); tok = _login(client, "viewer@test.io")
    r = client.get("/decisions/nope/replay", headers=_hdr(tok))
    assert r.status_code == 404


# ════════════════════════════════════════════════════════════════════
# Auth
# ════════════════════════════════════════════════════════════════════

def test_sign_requires_uploader():
    db, _ = _make_db(decisions=[_seed_decision()])
    client = _client(db); tok = _login(client, "viewer@test.io")
    r = client.post("/decisions/dec-001/sign", json={"claim_ids": ["c-1"]},
                    headers=_hdr(tok))
    assert r.status_code in (401, 403)


def test_unauth_verify_401():
    db, _ = _make_db(decisions=[_seed_decision()])
    client = _client(db)
    r = client.get("/decisions/dec-001/verify")
    assert r.status_code in (401, 403)


def test_unauth_replay_401():
    db, _ = _make_db(decisions=[_seed_decision()])
    client = _client(db)
    r = client.get("/decisions/dec-001/replay")
    assert r.status_code in (401, 403)


# ════════════════════════════════════════════════════════════════════
# Red-team
# ════════════════════════════════════════════════════════════════════

def test_R6_signature_bound_to_decision_id():
    """R6: signature for one decision cannot be replayed onto another
    because decision_id is part of the signed payload."""
    from services.decision_signing import compute_signature, verify_signature
    payload_a = {"decision_id": "dec-A", "title": "x"}
    payload_b = {"decision_id": "dec-B", "title": "x"}
    sig_a = compute_signature(payload_a, secret=b"test")
    # Same secret, different decision_id → verification fails
    assert verify_signature(payload_b, sig_a, secret=b"test") is False


def test_R1_post_sign_field_mutation_caught():
    """R1: mutating ANY signed field breaks verification."""
    db, decisions_db = _make_db(decisions=[_seed_decision()])
    client = _client(db); tok = _login(client, "editor@test.io")
    client.post("/decisions/dec-001/sign", json={"claim_ids": ["c-1"]},
                headers=_hdr(tok))

    for field, new_value in [
        ("rationale", "MUTATED RATIONALE"),
        ("target_value", "+99pp"),
        ("confidence_at_commit", 0.99),
    ]:
        decisions_db["dec-001"][field] = new_value
        vtok = _login(client, "viewer@test.io")
        r = client.get("/decisions/dec-001/verify", headers=_hdr(vtok))
        assert r.status_code == 200
        assert r.json()["valid"] is False, f"verify should fail after {field} mutated"
        # restore for next iteration (re-sign, then mutate again)
        decisions_db["dec-001"][field] = _seed_decision()[field]
        # Re-verify (should pass again)
        r2 = client.get("/decisions/dec-001/verify", headers=_hdr(vtok))
        assert r2.json()["valid"] is True
