"""SPEC-021 Phase C — Decision Ledger API tests.

Endpoints:
  POST   /decisions/from-round/{round_id}   viewer+ (room owner)
  GET    /decisions                         viewer+
  GET    /decisions/{id}                    anon
  PATCH  /decisions/{id}                    owner
  DELETE /decisions/{id}                    owner
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent


# ────────────────────────────────────────────────────────────────────
# Fake DB — users + war rooms + rounds + reactions + decisions
# ────────────────────────────────────────────────────────────────────

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
    # Pre-seed a war room owned by viewer with one round + one reaction
    rooms = {
        "wr-1": {
            "id": "wr-1",
            "title": "Pre-seeded room",
            "owner_user_id": "uuid-viewer",
            "source_signal_id": None,
        },
    }
    rounds = {
        "rnd-1": {
            "id": "rnd-1",
            "war_room_id": "wr-1",
            "move_type": "trial_readout",
            "move_payload": {"target_drug": "semaglutide"},
        },
    }
    reactions = {
        "rnd-1": [
            {"confidence_score": 0.6},
            {"confidence_score": 0.8},
        ],
    }
    decisions: dict[str, dict] = {}
    next_id = [1]

    def _gen_id(prefix: str) -> str:
        nid = f"{prefix}-{next_id[0]}"
        next_id[0] += 1
        return nid

    def _insert_decision(params, returning=True):
        did = _gen_id("dec")
        d = {
            "id": did,
            "war_room_round_id": params[0],
            "war_room_id": params[1],
            "source_signal_id": params[2],
            "title": params[3],
            "rationale": params[4],
            "move_type": params[5],
            "move_payload_snapshot": params[6],
            "owner_user_id": params[7],
            "owner_display_name": params[8],
            "target_metric": params[9],
            "target_value": params[10],
            "deadline": params[11],
            "confidence_at_commit": params[12],
            "status": "open",
            "actual_outcome": None,
            "actual_outcome_recorded_at": None,
            "calibration_score": None,
            "notes": None,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
        decisions[did] = d
        return d if returning else None

    def fake_fetch_one(sql, params=None):
        s = (sql or "").lower()

        # Users (auth)
        if "from users" in s and params:
            if "where lower(email)" in s or "where email" in s:
                return users.get(str(params[0]).lower())
            if "where id::text" in s or "where id =" in s:
                for u in users.values():
                    if u["id"] == params[0]:
                        return u
                return None

        # JOIN war_room_rounds + war_rooms
        if "from war_room_rounds r" in s and "join war_rooms w" in s and params:
            rid = str(params[0])
            r = rounds.get(rid)
            if not r:
                return None
            w = rooms.get(r["war_room_id"])
            return {
                "round_id": r["id"],
                "war_room_id": r["war_room_id"],
                "move_type": r["move_type"],
                "move_payload": r["move_payload"],
                "owner_user_id": w["owner_user_id"] if w else None,
                "room_title": w["title"] if w else None,
                "source_signal_id": w["source_signal_id"] if w else None,
            }

        # AVG confidence over reactions
        if "avg(confidence_score)" in s and "war_room_reactions" in s and params:
            rid = str(params[0])
            scores = [r["confidence_score"] for r in reactions.get(rid, []) if r.get("confidence_score") is not None]
            if not scores:
                return {"avg_conf": None}
            return {"avg_conf": sum(scores) / len(scores)}

        # INSERT INTO decisions ... RETURNING
        if "insert into decisions" in s and "returning" in s and params:
            return _insert_decision(params)

        # SELECT decision by id
        if "from decisions" in s and "id::text" in s and params:
            return decisions.get(str(params[0]))

        return None

    def fake_fetch_all(sql, params=None):
        s = (sql or "").lower()
        if "from decisions" in s and "owner_user_id" in s and params:
            owner = params[0]
            out = [dict(d) for d in decisions.values() if d.get("owner_user_id") == owner]
            idx = 1
            if "status = %s" in s:
                out = [d for d in out if d.get("status") == params[idx]]
                idx += 1
            if "war_room_id::text = %s" in s:
                out = [d for d in out if str(d.get("war_room_id")) == str(params[idx])]
                idx += 1
            if "deadline < current_date" in s:
                today = date.today()
                def is_overdue(d):
                    dl = d.get("deadline")
                    if dl is None:
                        return False
                    if isinstance(dl, str):
                        try:
                            dl = datetime.fromisoformat(dl).date()
                        except Exception:
                            return False
                    return dl < today and d.get("status") in ("open", "in_progress")
                out = [d for d in out if is_overdue(d)]
            return out
        return []

    def fake_execute(sql, params=None):
        s = (sql or "").lower()

        # Capture-outcome UPDATE — has actual_outcome_recorded_at = NOW()
        # AND calibration_score = %s (PATCH doesn't touch calibration).
        # Match this BEFORE the generic PATCH path so its fixed param order
        # is respected (route uses: actual_outcome, verdict, cal_score, notes, id).
        if (
            "update decisions" in s
            and "actual_outcome_recorded_at = now()" in s
            and "calibration_score = %s" in s
            and params
        ):
            did = str(params[-1])
            if did not in decisions:
                return None
            decisions[did]["actual_outcome"] = params[0]
            decisions[did]["status"] = params[1]
            decisions[did]["calibration_score"] = params[2]
            if params[3] is not None:
                decisions[did]["notes"] = params[3]
            decisions[did]["actual_outcome_recorded_at"] = datetime.now(timezone.utc)
            decisions[did]["updated_at"] = datetime.now(timezone.utc)
            return None

        # PATCH decision
        if "update decisions" in s and "where id::text" in s and params:
            did = str(params[-1])
            if did not in decisions:
                return None
            pi = 0
            if "status = %s" in s:
                decisions[did]["status"] = params[pi]; pi += 1
            if "notes = %s" in s:
                decisions[did]["notes"] = params[pi]; pi += 1
            if "deadline = null" in s:
                decisions[did]["deadline"] = None
            elif "deadline = %s" in s:
                decisions[did]["deadline"] = params[pi]; pi += 1
            if "target_metric = %s" in s:
                decisions[did]["target_metric"] = params[pi]; pi += 1
            if "target_value = %s" in s:
                decisions[did]["target_value"] = params[pi]; pi += 1
            if "actual_outcome = %s" in s:
                decisions[did]["actual_outcome"] = params[pi]; pi += 1
                decisions[did]["actual_outcome_recorded_at"] = datetime.now(timezone.utc)
            decisions[did]["updated_at"] = datetime.now(timezone.utc)
            return None

        # DELETE decision
        if "delete from decisions" in s and params:
            did = str(params[0])
            decisions.pop(did, None)
            return None

        return None

    db = MagicMock()
    db.fetch_one.side_effect = fake_fetch_one
    db.fetch_all.side_effect = fake_fetch_all
    db.execute.side_effect = fake_execute
    return db, decisions


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
# Module + routes
# ────────────────────────────────────────────────────────────────────

def test_decisions_route_module_exists():
    assert (REPO_ROOT / "api" / "routes" / "decisions.py").exists()


def test_decisions_routes_registered():
    from api.app import create_app
    app = create_app()
    paths = {getattr(r, "path", None) for r in app.routes}
    assert "/decisions" in paths
    assert "/decisions/from-round/{round_id}" in paths


# ────────────────────────────────────────────────────────────────────
# POST /decisions/from-round/{round_id}
# ────────────────────────────────────────────────────────────────────

def test_promote_round_401_anonymous():
    db, _ = _make_db()
    r = _client(db).post("/decisions/from-round/rnd-1", json={"title": "X"})
    assert r.status_code == 401


def test_promote_round_403_for_non_owner():
    db, _ = _make_db()
    client = _client(db)
    tok = _login(client, "uploader@demo.market-zero.io")  # not the room owner
    r = client.post(
        "/decisions/from-round/rnd-1", headers=_hdr(tok),
        json={"title": "Hijack attempt"},
    )
    assert r.status_code == 403


def test_promote_round_404_for_unknown_round():
    db, _ = _make_db()
    client = _client(db)
    tok = _login(client, "viewer@demo.market-zero.io")
    r = client.post(
        "/decisions/from-round/nonexistent", headers=_hdr(tok),
        json={"title": "X"},
    )
    assert r.status_code == 404


def test_promote_round_201_snapshots_round_data():
    db, decisions_store = _make_db()
    client = _client(db)
    tok = _login(client, "viewer@demo.market-zero.io")
    r = client.post(
        "/decisions/from-round/rnd-1", headers=_hdr(tok),
        json={
            "title": "Accelerate semaglutide MASH",
            "rationale": "Phase 3 data strong",
            "target_metric": "market_share_delta",
            "target_value": "+3pp",
            "deadline": "2026-12-31",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["title"] == "Accelerate semaglutide MASH"
    assert body["move_type"] == "trial_readout"  # snapshotted from round
    assert body["move_payload_snapshot"] == {"target_drug": "semaglutide"}  # snapshotted
    assert body["status"] == "open"
    assert body["owner_user_id"] == "uuid-viewer"
    # Mean of 0.6 and 0.8 → 0.7
    assert body["confidence_at_commit"] == pytest.approx(0.7, abs=0.01)
    assert body["war_room_id"] == "wr-1"
    assert body["war_room_round_id"] == "rnd-1"
    # Persisted
    assert len(decisions_store) == 1


def test_promote_round_400_for_invalid_deadline():
    db, _ = _make_db()
    client = _client(db)
    tok = _login(client, "viewer@demo.market-zero.io")
    r = client.post(
        "/decisions/from-round/rnd-1", headers=_hdr(tok),
        json={"title": "X", "deadline": "next tuesday"},
    )
    assert r.status_code == 400


def test_promote_round_uses_owner_display_name_override():
    db, _ = _make_db()
    client = _client(db)
    tok = _login(client, "viewer@demo.market-zero.io")
    r = client.post(
        "/decisions/from-round/rnd-1", headers=_hdr(tok),
        json={"title": "X", "owner_display_name": "Kapil Pant"},
    )
    assert r.status_code == 201
    assert r.json()["owner_display_name"] == "Kapil Pant"


# ────────────────────────────────────────────────────────────────────
# GET /decisions — list
# ────────────────────────────────────────────────────────────────────

def test_list_decisions_401_anonymous():
    db, _ = _make_db()
    r = _client(db).get("/decisions")
    assert r.status_code == 401


def test_list_decisions_returns_only_owners():
    db, _ = _make_db()
    client = _client(db)
    vt = _login(client, "viewer@demo.market-zero.io")
    # viewer promotes
    client.post("/decisions/from-round/rnd-1", headers=_hdr(vt),
                json={"title": "viewer's decision"})
    r = client.get("/decisions", headers=_hdr(vt))
    assert r.status_code == 200
    assert len(r.json()["decisions"]) == 1
    # Different user sees nothing
    ut = _login(client, "uploader@demo.market-zero.io")
    r = client.get("/decisions", headers=_hdr(ut))
    assert len(r.json()["decisions"]) == 0


def test_list_decisions_filter_by_status():
    db, _ = _make_db()
    client = _client(db)
    tok = _login(client, "viewer@demo.market-zero.io")
    did = client.post("/decisions/from-round/rnd-1", headers=_hdr(tok),
                       json={"title": "x"}).json()["id"]
    # Move to verified
    client.patch(f"/decisions/{did}", headers=_hdr(tok),
                 json={"status": "verified"})
    # Filter open → 0
    r = client.get("/decisions?status=open", headers=_hdr(tok))
    assert len(r.json()["decisions"]) == 0
    # Filter verified → 1
    r = client.get("/decisions?status=verified", headers=_hdr(tok))
    assert len(r.json()["decisions"]) == 1


def test_list_decisions_400_for_invalid_status():
    db, _ = _make_db()
    client = _client(db)
    tok = _login(client, "viewer@demo.market-zero.io")
    r = client.get("/decisions?status=banana", headers=_hdr(tok))
    assert r.status_code == 400


def test_list_decisions_filter_overdue():
    db, _ = _make_db()
    client = _client(db)
    tok = _login(client, "viewer@demo.market-zero.io")
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    future = (date.today() + timedelta(days=30)).isoformat()
    # One overdue, one future
    client.post("/decisions/from-round/rnd-1", headers=_hdr(tok),
                json={"title": "overdue", "deadline": yesterday})
    client.post("/decisions/from-round/rnd-1", headers=_hdr(tok),
                json={"title": "future", "deadline": future})
    r = client.get("/decisions?overdue=true", headers=_hdr(tok))
    assert r.status_code == 200
    assert len(r.json()["decisions"]) == 1
    assert r.json()["decisions"][0]["title"] == "overdue"


# ────────────────────────────────────────────────────────────────────
# GET /decisions/{id} — anon
# ────────────────────────────────────────────────────────────────────

def test_get_decision_anon_returns_full_record():
    db, _ = _make_db()
    client = _client(db)
    tok = _login(client, "viewer@demo.market-zero.io")
    did = client.post("/decisions/from-round/rnd-1", headers=_hdr(tok),
                       json={"title": "anon-readable",
                             "deadline": (date.today() + timedelta(days=10)).isoformat()}).json()["id"]
    # Anon read
    r = client.get(f"/decisions/{did}")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == did
    # Computed fields
    assert body["overdue"] is False
    assert body["days_to_deadline"] == 10


def test_get_decision_404_unknown():
    db, _ = _make_db()
    r = _client(db).get("/decisions/does-not-exist")
    assert r.status_code == 404


# ────────────────────────────────────────────────────────────────────
# PATCH /decisions/{id} — owner
# ────────────────────────────────────────────────────────────────────

def test_patch_decision_401_anonymous():
    db, _ = _make_db()
    client = _client(db)
    tok = _login(client, "viewer@demo.market-zero.io")
    did = client.post("/decisions/from-round/rnd-1", headers=_hdr(tok),
                       json={"title": "x"}).json()["id"]
    r = client.patch(f"/decisions/{did}", json={"status": "verified"})
    assert r.status_code == 401


def test_patch_decision_403_non_owner():
    db, _ = _make_db()
    client = _client(db)
    vt = _login(client, "viewer@demo.market-zero.io")
    did = client.post("/decisions/from-round/rnd-1", headers=_hdr(vt),
                       json={"title": "x"}).json()["id"]
    ut = _login(client, "uploader@demo.market-zero.io")
    r = client.patch(f"/decisions/{did}", headers=_hdr(ut),
                     json={"status": "cancelled"})
    assert r.status_code == 403


def test_patch_decision_status_transition():
    db, _ = _make_db()
    client = _client(db)
    tok = _login(client, "viewer@demo.market-zero.io")
    did = client.post("/decisions/from-round/rnd-1", headers=_hdr(tok),
                       json={"title": "x"}).json()["id"]
    r = client.patch(f"/decisions/{did}", headers=_hdr(tok),
                     json={"status": "in_progress"})
    assert r.status_code == 200
    assert r.json()["status"] == "in_progress"


def test_patch_decision_400_invalid_status():
    db, _ = _make_db()
    client = _client(db)
    tok = _login(client, "viewer@demo.market-zero.io")
    did = client.post("/decisions/from-round/rnd-1", headers=_hdr(tok),
                       json={"title": "x"}).json()["id"]
    r = client.patch(f"/decisions/{did}", headers=_hdr(tok),
                     json={"status": "deleted"})
    assert r.status_code == 400


def test_patch_decision_clear_deadline_with_empty_string():
    db, _ = _make_db()
    client = _client(db)
    tok = _login(client, "viewer@demo.market-zero.io")
    did = client.post("/decisions/from-round/rnd-1", headers=_hdr(tok),
                       json={"title": "x", "deadline": "2026-12-31"}).json()["id"]
    r = client.patch(f"/decisions/{did}", headers=_hdr(tok),
                     json={"deadline": ""})
    assert r.status_code == 200
    assert r.json()["deadline"] is None


def test_patch_decision_actual_outcome_sets_recorded_at():
    db, _ = _make_db()
    client = _client(db)
    tok = _login(client, "viewer@demo.market-zero.io")
    did = client.post("/decisions/from-round/rnd-1", headers=_hdr(tok),
                       json={"title": "x"}).json()["id"]
    r = client.patch(f"/decisions/{did}", headers=_hdr(tok),
                     json={"actual_outcome": "Lilly accelerated MASH program",
                           "status": "verified"})
    assert r.status_code == 200
    body = r.json()
    assert body["actual_outcome"] == "Lilly accelerated MASH program"
    assert body["actual_outcome_recorded_at"] is not None


# ────────────────────────────────────────────────────────────────────
# DELETE /decisions/{id} — owner
# ────────────────────────────────────────────────────────────────────

def test_delete_decision_403_non_owner():
    db, _ = _make_db()
    client = _client(db)
    vt = _login(client, "viewer@demo.market-zero.io")
    did = client.post("/decisions/from-round/rnd-1", headers=_hdr(vt),
                       json={"title": "x"}).json()["id"]
    ut = _login(client, "uploader@demo.market-zero.io")
    r = client.delete(f"/decisions/{did}", headers=_hdr(ut))
    assert r.status_code == 403


def test_delete_decision_204_owner():
    db, decisions_store = _make_db()
    client = _client(db)
    tok = _login(client, "viewer@demo.market-zero.io")
    did = client.post("/decisions/from-round/rnd-1", headers=_hdr(tok),
                       json={"title": "x"}).json()["id"]
    r = client.delete(f"/decisions/{did}", headers=_hdr(tok))
    assert r.status_code == 204
    assert did not in decisions_store


# ────────────────────────────────────────────────────────────────────
# Phase D MVP — suggest-outcome + capture-outcome
# ────────────────────────────────────────────────────────────────────

from unittest.mock import patch  # noqa: E402


_STUB_CANDIDATES = [
    {
        "signal_id": "sig-A",
        "headline": "Lilly accelerated SURMOUNT-MASH to Phase 3",
        "summary": "Confirmed via PR + ClinicalTrials.gov entry.",
        "kbq_tags": ["clinical"],
        "created_at": "2026-08-01T00:00:00+00:00",
        "primary_entity_name": "Eli Lilly",
        "primary_entity_id": "ent-lilly",
        "rule_version_id": "intel-v1.2.0",
        "confidence_tier": "confirmed",
        "trust_score": 0.85,
        "impact_tier": "high",
        "match_score": 0.85,
        "match_components": {"entity_overlap": 0.5, "kbq_overlap": 0.3, "temporal_proximity": 0.05},
    },
    {
        "signal_id": "sig-B",
        "headline": "Pfizer pricing pressure in EU",
        "summary": "Reported.",
        "kbq_tags": ["pricing_access"],
        "created_at": "2026-09-15T00:00:00+00:00",
        "primary_entity_name": "Pfizer",
        "primary_entity_id": "ent-pfizer",
        "rule_version_id": "intel-v1.2.0",
        "confidence_tier": "reported",
        "trust_score": 0.6,
        "impact_tier": "medium",
        "match_score": 0.45,
        "match_components": {"entity_overlap": 0.0, "kbq_overlap": 0.3, "temporal_proximity": 0.15},
    },
]


def test_suggest_outcome_401_anonymous():
    db, _ = _make_db()
    client = _client(db)
    tok = _login(client, "viewer@demo.market-zero.io")
    did = client.post("/decisions/from-round/rnd-1", headers=_hdr(tok),
                       json={"title": "x"}).json()["id"]
    r = client.post(f"/decisions/{did}/suggest-outcome")
    assert r.status_code == 401


def test_suggest_outcome_403_non_owner():
    db, _ = _make_db()
    client = _client(db)
    vt = _login(client, "viewer@demo.market-zero.io")
    did = client.post("/decisions/from-round/rnd-1", headers=_hdr(vt),
                       json={"title": "x"}).json()["id"]
    ut = _login(client, "uploader@demo.market-zero.io")
    r = client.post(f"/decisions/{did}/suggest-outcome", headers=_hdr(ut))
    assert r.status_code == 403


def test_suggest_outcome_200_returns_candidates():
    db, _ = _make_db()
    client = _client(db)
    tok = _login(client, "viewer@demo.market-zero.io")
    did = client.post("/decisions/from-round/rnd-1", headers=_hdr(tok),
                       json={"title": "x"}).json()["id"]
    with patch(
        "api.routes.decisions.match_signals_to_decision",
        return_value=list(_STUB_CANDIDATES),
    ):
        r = client.post(f"/decisions/{did}/suggest-outcome", headers=_hdr(tok))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["decision_id"] == did
    assert "rule_version_id" in body
    assert body["count"] == 2
    assert body["candidates"][0]["signal_id"] == "sig-A"
    assert "match_components" in body["candidates"][0]


def test_capture_outcome_401_anonymous():
    db, _ = _make_db()
    client = _client(db)
    tok = _login(client, "viewer@demo.market-zero.io")
    did = client.post("/decisions/from-round/rnd-1", headers=_hdr(tok),
                       json={"title": "x"}).json()["id"]
    r = client.post(
        f"/decisions/{did}/capture-outcome",
        json={"signal_id": "sig-A", "verdict": "verified", "actual_outcome": "x"},
    )
    assert r.status_code == 401


def test_capture_outcome_403_non_owner():
    db, _ = _make_db()
    client = _client(db)
    vt = _login(client, "viewer@demo.market-zero.io")
    did = client.post("/decisions/from-round/rnd-1", headers=_hdr(vt),
                       json={"title": "x"}).json()["id"]
    ut = _login(client, "uploader@demo.market-zero.io")
    r = client.post(
        f"/decisions/{did}/capture-outcome", headers=_hdr(ut),
        json={"signal_id": "sig-A", "verdict": "verified", "actual_outcome": "x"},
    )
    assert r.status_code == 403


def test_capture_outcome_400_invalid_verdict():
    db, _ = _make_db()
    client = _client(db)
    tok = _login(client, "viewer@demo.market-zero.io")
    did = client.post("/decisions/from-round/rnd-1", headers=_hdr(tok),
                       json={"title": "x"}).json()["id"]
    r = client.post(
        f"/decisions/{did}/capture-outcome", headers=_hdr(tok),
        json={"signal_id": "sig-A", "verdict": "banana", "actual_outcome": "x"},
    )
    assert r.status_code == 400


def test_capture_outcome_400_signal_not_found():
    db, _ = _make_db()
    client = _client(db)
    tok = _login(client, "viewer@demo.market-zero.io")
    did = client.post("/decisions/from-round/rnd-1", headers=_hdr(tok),
                       json={"title": "x"}).json()["id"]
    # Fake DB has no signals — capture should 400
    r = client.post(
        f"/decisions/{did}/capture-outcome", headers=_hdr(tok),
        json={"signal_id": "sig-nonexistent", "verdict": "verified", "actual_outcome": "x"},
    )
    assert r.status_code == 400


def test_capture_outcome_writes_actual_and_calibration():
    """End-to-end: capture verified outcome with high confidence_at_commit
    (mean of 0.6 + 0.8 = 0.7) → calibration_score should equal 0.7."""
    db, decisions_store = _make_db()
    # Add a fake signal so the lookup succeeds
    db._signals = {
        "sig-A": {
            "id": "sig-A",
            "kbq_tags": ["clinical"],
            "rule_version_id": "intel-v1.2.0",
            "primary_entity_name": "Eli Lilly",
        },
    }
    # Wire signal lookup into the existing fake_fetch_one
    real_fetch_one = db.fetch_one.side_effect
    def patched_fetch_one(sql, params=None):
        s = (sql or "").lower()
        if "from signals" in s and "id::text" in s and params:
            return db._signals.get(str(params[0]))
        if "primary_entity_id from war_rooms" in s and params:
            return {"primary_entity_id": "ent-novo"}
        return real_fetch_one(sql, params)
    db.fetch_one.side_effect = patched_fetch_one

    client = _client(db)
    tok = _login(client, "viewer@demo.market-zero.io")
    did = client.post("/decisions/from-round/rnd-1", headers=_hdr(tok),
                       json={"title": "x"}).json()["id"]
    # Sanity: the seeded round had confidence_score 0.6 + 0.8 → 0.7
    assert decisions_store[did]["confidence_at_commit"] == pytest.approx(0.7, abs=0.01)

    r = client.post(
        f"/decisions/{did}/capture-outcome", headers=_hdr(tok),
        json={
            "signal_id": "sig-A", "verdict": "verified",
            "actual_outcome": "Lilly accelerated SURMOUNT-MASH",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "verified"
    assert body["actual_outcome"] == "Lilly accelerated SURMOUNT-MASH"
    assert body["actual_outcome_recorded_at"] is not None
    # verified + 0.7 confidence → score = 0.7
    assert body["calibration_score"] == pytest.approx(0.7, abs=0.01)


def test_capture_outcome_writes_signal_score_adjustments():
    """Verify the learning-ledger insert fires per kbq_tag of the signal."""
    db, _ = _make_db()
    inserted_adjustments = []
    db._signals = {
        "sig-A": {
            "id": "sig-A",
            "kbq_tags": ["clinical", "regulatory"],  # 2 tags → expect 2 inserts
            "rule_version_id": "intel-v1.2.0",
            "primary_entity_name": "Eli Lilly",
        },
    }
    real_fetch_one = db.fetch_one.side_effect
    real_execute = db.execute.side_effect

    def patched_fetch_one(sql, params=None):
        s = (sql or "").lower()
        if "from signals" in s and "id::text" in s and params:
            return db._signals.get(str(params[0]))
        if "primary_entity_id from war_rooms" in s and params:
            return {"primary_entity_id": "ent-novo"}
        return real_fetch_one(sql, params)

    def patched_execute(sql, params=None):
        s = (sql or "").lower()
        if "insert into signal_score_adjustments" in s and params:
            inserted_adjustments.append({
                "rule_version_id": params[0],
                "kbq_tag": params[1],
                "decision_id": params[2],
                "matched_signal_id": params[3],
                "calibration_score": params[4],
                "weight_delta_suggested": params[5],
            })
            return None
        return real_execute(sql, params)

    db.fetch_one.side_effect = patched_fetch_one
    db.execute.side_effect = patched_execute

    client = _client(db)
    tok = _login(client, "viewer@demo.market-zero.io")
    did = client.post("/decisions/from-round/rnd-1", headers=_hdr(tok),
                       json={"title": "x"}).json()["id"]

    r = client.post(
        f"/decisions/{did}/capture-outcome", headers=_hdr(tok),
        json={"signal_id": "sig-A", "verdict": "verified", "actual_outcome": "x"},
    )
    assert r.status_code == 200, r.text
    # 2 KBQ tags on the signal → 2 inserts
    assert len(inserted_adjustments) == 2
    tags = {a["kbq_tag"] for a in inserted_adjustments}
    assert tags == {"clinical", "regulatory"}
    for adj in inserted_adjustments:
        assert adj["rule_version_id"] == "intel-v1.2.0"
        assert 0.0 <= adj["calibration_score"] <= 1.0
        # verified verdict → positive weight delta
        assert adj["weight_delta_suggested"] > 0
