"""SPEC_023 — Decision Briefs API tests.

Covers the full state machine, option attachment, evidence_refs validation,
auth requirements, archive semantics, and red-team edge cases.

Endpoints under test:
  POST    /decision-briefs                                editor+
  GET     /decision-briefs                                viewer+
  GET     /decision-briefs/{id}                           viewer+
  PATCH   /decision-briefs/{id}                           editor+
  DELETE  /decision-briefs/{id}                           editor+
  POST    /decision-briefs/{id}/options                   editor+
  DELETE  /decision-briefs/{id}/options/{option_id}       editor+
  POST    /decision-briefs/{id}/transitions               editor+
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest


# ────────────────────────────────────────────────────────────────────
# Fake DB — minimal schema for decision_briefs + options + state_log
# ────────────────────────────────────────────────────────────────────

def _make_db():
    """Build a MagicMock DB pre-seeded with two test users and an empty
    briefs/options/state_log store. Returns (db, briefs_dict, options_dict,
    state_log_list, users_dict)."""
    from services.auth import hash_password

    users = {
        "viewer@test.io": {
            "id": "uuid-viewer", "email": "viewer@test.io",
            "password_hash": hash_password("demo"), "role": "viewer",
            "is_active": True,
        },
        "editor@test.io": {
            "id": "uuid-editor", "email": "editor@test.io",
            "password_hash": hash_password("demo"), "role": "uploader",
            "is_active": True,
        },
    }

    briefs: dict[str, dict] = {}
    options: dict[str, dict] = {}        # option_id -> option_row
    state_log: list[dict] = []
    next_id = [1]

    def _gen_id(prefix: str) -> str:
        n = next_id[0]
        next_id[0] += 1
        return f"{prefix}-{n:04d}"

    def fake_fetch_one(sql, params=None):
        s = (sql or "").lower()

        # Auth: SELECT user
        if "from users" in s and params:
            if "where lower(email)" in s or "where email" in s:
                return users.get(str(params[0]).lower())
            if "where id::text" in s or "where id =" in s:
                for u in users.values():
                    if u["id"] == params[0]:
                        return u
                return None

        # INSERT INTO decision_briefs ... RETURNING
        if "insert into decision_briefs" in s and "returning" in s and params:
            bid = _gen_id("brf")
            row = {
                "brief_id": bid,
                "question": params[0],
                "trigger_kind": params[1],
                "trigger_signal_ids": list(params[2] or []),
                "trigger_metadata": json.loads(params[3]) if isinstance(params[3], str) else (params[3] or {}),
                "stakeholders": list(params[4] or []),
                "time_horizon_days": params[5],
                "evidence_refs": json.loads(params[6]) if isinstance(params[6], str) else (params[6] or []),
                "constraints": list(params[7] or []),
                "success_criteria": params[8],
                "confidence_to_proceed": params[9],
                "state": "draft",
                "owner_user_id": params[10],
                "war_room_id": params[11],
                "decision_id": None,
                "archived_at": None,
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            }
            briefs[bid] = row
            return row

        # SELECT brief by id (with all columns)
        if "from decision_briefs" in s and "brief_id::text = %s" in s and "where" in s and params:
            return briefs.get(str(params[0]))

        # INSERT INTO decision_brief_options RETURNING
        if "insert into decision_brief_options" in s and "returning" in s and params:
            oid = _gen_id("opt")
            row = {
                "option_id": oid,
                "brief_id": params[0],
                "ordinal": params[1],
                "label": params[2],
                "description": params[3],
                "predicted_outcome": params[4],
                "cost_estimate": params[5],
                "risk_notes": params[6],
                "created_at": datetime.now(timezone.utc),
            }
            options[oid] = row
            return row

        return None

    def fake_fetch_all(sql, params=None):
        s = (sql or "").lower()

        # SELECT options for a brief
        if "from decision_brief_options" in s and params:
            bid = str(params[0])
            return sorted(
                [o for o in options.values() if str(o["brief_id"]) == bid],
                key=lambda o: o["ordinal"],
            )

        # SELECT state log for a brief
        if "from decision_brief_state_log" in s and params:
            bid = str(params[0])
            return sorted(
                [l for l in state_log if str(l["brief_id"]) == bid],
                key=lambda l: l["transitioned_at"],
            )

        # LIST briefs
        if "from decision_briefs" in s and "limit" in s:
            out = list(briefs.values())
            # naive filter parsing — match params positionally per route
            if params:
                idx = 0
                if "state = %s" in s:
                    out = [b for b in out if b["state"] == params[idx]]
                    idx += 1
                if "owner_user_id::text = %s" in s:
                    out = [b for b in out if str(b.get("owner_user_id") or "") == str(params[idx])]
                    idx += 1
                if "trigger_kind = %s" in s:
                    out = [b for b in out if b["trigger_kind"] == params[idx]]
                    idx += 1
                if "archived_at is null" in s:
                    out = [b for b in out if b.get("archived_at") is None]
                limit = params[-2]
                offset = params[-1]
                out = out[offset:offset + limit]
            return out

        return []

    def fake_execute(sql, params=None):
        s = (sql or "").lower()

        # PATCH decision_briefs
        if "update decision_briefs" in s and "where brief_id::text = %s" in s and params:
            bid = str(params[-1])
            if bid not in briefs:
                return None
            pi = 0
            if "question = %s" in s:
                briefs[bid]["question"] = params[pi]; pi += 1
            if "stakeholders = %s" in s:
                briefs[bid]["stakeholders"] = list(params[pi] or []); pi += 1
            if "time_horizon_days = %s" in s:
                briefs[bid]["time_horizon_days"] = params[pi]; pi += 1
            if "evidence_refs = %s::jsonb" in s:
                v = params[pi]
                briefs[bid]["evidence_refs"] = json.loads(v) if isinstance(v, str) else (v or [])
                pi += 1
            if "constraints = %s" in s:
                briefs[bid]["constraints"] = list(params[pi] or []); pi += 1
            if "success_criteria = %s" in s:
                briefs[bid]["success_criteria"] = params[pi]; pi += 1
            if "confidence_to_proceed = %s" in s:
                briefs[bid]["confidence_to_proceed"] = params[pi]; pi += 1
            if "state = %s" in s:
                briefs[bid]["state"] = params[pi]; pi += 1
            if "decision_id = %s" in s:
                briefs[bid]["decision_id"] = params[pi]; pi += 1
            if "archived_at = now()" in s:
                briefs[bid]["archived_at"] = datetime.now(timezone.utc)
            briefs[bid]["updated_at"] = datetime.now(timezone.utc)
            return None

        # INSERT state log
        if "insert into decision_brief_state_log" in s and params:
            state_log.append({
                "log_id": _gen_id("log"),
                "brief_id": params[0],
                "from_state": params[1],
                "to_state": params[2],
                "actor_user_id": params[3],
                "reason": params[4],
                "transitioned_at": datetime.now(timezone.utc),
            })
            return None

        # DELETE option
        if "delete from decision_brief_options" in s and params:
            bid, oid = str(params[0]), str(params[1])
            options.pop(oid, None)
            return None

        return None

    db = MagicMock()
    db.fetch_one.side_effect = fake_fetch_one
    db.fetch_all.side_effect = fake_fetch_all
    db.execute.side_effect = fake_execute
    return db, briefs, options, state_log, users


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
# Imports under test exist
# ────────────────────────────────────────────────────────────────────

def test_module_importable():
    from api.routes import decision_briefs as _m
    from services.decision_brief import DecisionBriefService, BriefState, LEGAL_TRANSITIONS
    assert _m.router.prefix == "/decision-briefs"
    assert "draft" in {s.value for s in BriefState}
    assert len(LEGAL_TRANSITIONS) == 8
    assert LEGAL_TRANSITIONS[BriefState.CLOSED] == set()


def test_route_registered_in_app():
    from api.app import create_app
    app = create_app()
    paths = {getattr(r, "path", "") for r in app.routes}
    assert "/decision-briefs" in paths
    assert "/decision-briefs/{brief_id}" in paths
    assert "/decision-briefs/{brief_id}/transitions" in paths


# ────────────────────────────────────────────────────────────────────
# Create
# ────────────────────────────────────────────────────────────────────

def test_create_minimal_brief():
    db, briefs, _, state_log, _ = _make_db()
    client = _client(db)
    tok = _login(client, "editor@test.io")
    r = client.post(
        "/decision-briefs",
        json={"question": "Should we accelerate Phase 3 readout?"},
        headers=_hdr(tok),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["question"] == "Should we accelerate Phase 3 readout?"
    assert body["state"] == "draft"
    assert body["trigger_kind"] == "manual"
    assert body["owner_user_id"] == "uuid-editor"
    assert body["options"] == []
    # Initial state-log entry was written
    assert len(body["state_log"]) == 1
    assert body["state_log"][0]["to_state"] == "draft"
    assert body["state_log"][0]["from_state"] is None


def test_create_full_brief_payload():
    db, briefs, _, _, _ = _make_db()
    client = _client(db)
    tok = _login(client, "editor@test.io")
    payload = {
        "question": "Reposition or hold in 2L NSCLC?",
        "trigger_kind": "threshold",
        "trigger_signal_ids": ["aaaa-1111", "bbbb-2222"],
        "trigger_metadata": {"materiality_score": 87, "clusters": 0},
        "stakeholders": ["commercial", "medical", "rd"],
        "time_horizon_days": 90,
        "evidence_refs": [
            {"type": "kbq_view", "id": "kbq-3", "snapshot_at": "2026-05-09"},
            {"type": "signal", "id": "sig-1"},
        ],
        "constraints": ["no IRA exposure increase"],
        "success_criteria": "Hit P3 readout primary endpoint by Q4",
        "confidence_to_proceed": 0.72,
    }
    r = client.post("/decision-briefs", json=payload, headers=_hdr(tok))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["trigger_kind"] == "threshold"
    assert body["trigger_metadata"]["materiality_score"] == 87
    assert len(body["evidence_refs"]) == 2
    assert body["confidence_to_proceed"] == 0.72


def test_create_rejects_invalid_trigger_kind():
    db, _, _, _, _ = _make_db()
    client = _client(db)
    tok = _login(client, "editor@test.io")
    r = client.post(
        "/decision-briefs",
        json={"question": "x?", "trigger_kind": "telepathy"},
        headers=_hdr(tok),
    )
    assert r.status_code == 422  # pydantic field_validator catches this


def test_create_rejects_invalid_evidence_ref_type():
    db, _, _, _, _ = _make_db()
    client = _client(db)
    tok = _login(client, "editor@test.io")
    r = client.post(
        "/decision-briefs",
        json={
            "question": "x?",
            "evidence_refs": [{"type": "magic_potion", "id": "p-1"}],
        },
        headers=_hdr(tok),
    )
    assert r.status_code == 400
    assert "type" in r.json().get("detail", "")


def test_create_rejects_evidence_ref_missing_id():
    db, _, _, _, _ = _make_db()
    client = _client(db)
    tok = _login(client, "editor@test.io")
    r = client.post(
        "/decision-briefs",
        json={
            "question": "x?",
            "evidence_refs": [{"type": "signal"}],
        },
        headers=_hdr(tok),
    )
    assert r.status_code == 400


def test_create_rejects_confidence_out_of_range():
    db, _, _, _, _ = _make_db()
    client = _client(db)
    tok = _login(client, "editor@test.io")
    # > 1.0
    r = client.post(
        "/decision-briefs",
        json={"question": "x?", "confidence_to_proceed": 1.5},
        headers=_hdr(tok),
    )
    assert r.status_code == 422
    # < 0.0
    r = client.post(
        "/decision-briefs",
        json={"question": "x?", "confidence_to_proceed": -0.1},
        headers=_hdr(tok),
    )
    assert r.status_code == 422


def test_create_rejects_blank_question():
    db, _, _, _, _ = _make_db()
    client = _client(db)
    tok = _login(client, "editor@test.io")
    r = client.post(
        "/decision-briefs",
        json={"question": "   "},
        headers=_hdr(tok),
    )
    # Pydantic min_length=1 catches "" but not "   "; service must reject
    # Both 400 and 422 are acceptable depending on which layer rejects
    assert r.status_code in (400, 422)


# ────────────────────────────────────────────────────────────────────
# Get
# ────────────────────────────────────────────────────────────────────

def test_get_returns_brief_with_options_and_log():
    db, _, _, _, _ = _make_db()
    client = _client(db)
    tok = _login(client, "editor@test.io")
    create = client.post(
        "/decision-briefs",
        json={"question": "x?"},
        headers=_hdr(tok),
    )
    bid = create.json()["brief_id"]

    # Add an option
    opt_r = client.post(
        f"/decision-briefs/{bid}/options",
        json={"label": "Accelerate readout"},
        headers=_hdr(tok),
    )
    assert opt_r.status_code == 201

    # Fetch with viewer role
    vtok = _login(client, "viewer@test.io")
    r = client.get(f"/decision-briefs/{bid}", headers=_hdr(vtok))
    assert r.status_code == 200
    body = r.json()
    assert len(body["options"]) == 1
    assert body["options"][0]["ordinal"] == 1
    assert body["options"][0]["label"] == "Accelerate readout"
    assert len(body["state_log"]) >= 1


def test_get_404_for_unknown():
    db, _, _, _, _ = _make_db()
    client = _client(db)
    tok = _login(client, "viewer@test.io")
    r = client.get("/decision-briefs/nope-9999", headers=_hdr(tok))
    assert r.status_code == 404


# ────────────────────────────────────────────────────────────────────
# List
# ────────────────────────────────────────────────────────────────────

def test_list_briefs_returns_pagination_envelope():
    db, _, _, _, _ = _make_db()
    client = _client(db)
    tok = _login(client, "editor@test.io")
    for i in range(3):
        client.post(
            "/decision-briefs",
            json={"question": f"Q{i}?"},
            headers=_hdr(tok),
        )
    vtok = _login(client, "viewer@test.io")
    r = client.get("/decision-briefs?limit=10&offset=0", headers=_hdr(vtok))
    assert r.status_code == 200
    body = r.json()
    assert body["limit"] == 10
    assert body["offset"] == 0
    assert body["count"] == 3
    assert len(body["briefs"]) == 3


def test_list_filters_by_state():
    db, _, _, _, _ = _make_db()
    client = _client(db)
    tok = _login(client, "editor@test.io")
    client.post("/decision-briefs", json={"question": "Q?"}, headers=_hdr(tok))
    r = client.get("/decision-briefs?state=committed", headers=_hdr(tok))
    assert r.status_code == 200
    assert r.json()["count"] == 0  # no committed briefs


def test_list_rejects_invalid_state_filter():
    db, _, _, _, _ = _make_db()
    client = _client(db)
    tok = _login(client, "viewer@test.io")
    r = client.get("/decision-briefs?state=pondering", headers=_hdr(tok))
    assert r.status_code == 400


# ────────────────────────────────────────────────────────────────────
# Options
# ────────────────────────────────────────────────────────────────────

def test_add_option_assigns_sequential_ordinal():
    db, _, _, _, _ = _make_db()
    client = _client(db)
    tok = _login(client, "editor@test.io")
    bid = client.post("/decision-briefs", json={"question": "Q?"}, headers=_hdr(tok)).json()["brief_id"]

    o1 = client.post(f"/decision-briefs/{bid}/options",
                     json={"label": "A"}, headers=_hdr(tok)).json()
    o2 = client.post(f"/decision-briefs/{bid}/options",
                     json={"label": "B"}, headers=_hdr(tok)).json()
    assert o1["ordinal"] == 1
    assert o2["ordinal"] == 2


def test_add_option_in_committed_state_returns_409():
    db, briefs, _, _, _ = _make_db()
    client = _client(db)
    tok = _login(client, "editor@test.io")
    bid = client.post("/decision-briefs", json={"question": "Q?"}, headers=_hdr(tok)).json()["brief_id"]
    # Force-flip the state in the fake DB to simulate post-commit
    briefs[bid]["state"] = "committed"
    r = client.post(f"/decision-briefs/{bid}/options",
                    json={"label": "C"}, headers=_hdr(tok))
    assert r.status_code == 409


def test_remove_option_returns_204():
    db, _, _, _, _ = _make_db()
    client = _client(db)
    tok = _login(client, "editor@test.io")
    bid = client.post("/decision-briefs", json={"question": "Q?"}, headers=_hdr(tok)).json()["brief_id"]
    opt = client.post(f"/decision-briefs/{bid}/options",
                      json={"label": "A"}, headers=_hdr(tok)).json()
    r = client.delete(f"/decision-briefs/{bid}/options/{opt['option_id']}",
                      headers=_hdr(tok))
    assert r.status_code == 204


# ────────────────────────────────────────────────────────────────────
# State machine
# ────────────────────────────────────────────────────────────────────

def test_transition_draft_to_human_review_legal():
    db, _, _, state_log, _ = _make_db()
    client = _client(db)
    tok = _login(client, "editor@test.io")
    bid = client.post("/decision-briefs", json={"question": "Q?"}, headers=_hdr(tok)).json()["brief_id"]
    r = client.post(
        f"/decision-briefs/{bid}/transitions",
        json={"to_state": "human_review", "reason": "ready for review"},
        headers=_hdr(tok),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["state"] == "human_review"
    # State log captured the transition
    assert any(l["to_state"] == "human_review" for l in body["state_log"])


def test_transition_skip_states_returns_409():
    db, _, _, _, _ = _make_db()
    client = _client(db)
    tok = _login(client, "editor@test.io")
    bid = client.post("/decision-briefs", json={"question": "Q?"}, headers=_hdr(tok)).json()["brief_id"]
    # Try draft → committed (illegal jump)
    r = client.post(
        f"/decision-briefs/{bid}/transitions",
        json={"to_state": "committed"},
        headers=_hdr(tok),
    )
    assert r.status_code == 409
    assert "illegal transition" in r.json().get("detail", "").lower()


def test_transition_to_simulation_pending_requires_2_options():
    db, _, _, _, _ = _make_db()
    client = _client(db)
    tok = _login(client, "editor@test.io")
    bid = client.post("/decision-briefs", json={"question": "Q?"}, headers=_hdr(tok)).json()["brief_id"]
    # Move to human_review (legal)
    client.post(f"/decision-briefs/{bid}/transitions",
                json={"to_state": "human_review"}, headers=_hdr(tok))
    # Try to move to simulation_pending with 0 options
    r = client.post(f"/decision-briefs/{bid}/transitions",
                    json={"to_state": "simulation_pending"}, headers=_hdr(tok))
    assert r.status_code == 409
    assert "options" in r.json().get("detail", "").lower()
    # Add 2 options, then it should succeed
    client.post(f"/decision-briefs/{bid}/options", json={"label": "A"}, headers=_hdr(tok))
    client.post(f"/decision-briefs/{bid}/options", json={"label": "B"}, headers=_hdr(tok))
    r = client.post(f"/decision-briefs/{bid}/transitions",
                    json={"to_state": "simulation_pending"}, headers=_hdr(tok))
    assert r.status_code == 200, r.text


def test_transition_invalid_target_state_returns_422():
    db, _, _, _, _ = _make_db()
    client = _client(db)
    tok = _login(client, "editor@test.io")
    bid = client.post("/decision-briefs", json={"question": "Q?"}, headers=_hdr(tok)).json()["brief_id"]
    r = client.post(
        f"/decision-briefs/{bid}/transitions",
        json={"to_state": "imagining"},
        headers=_hdr(tok),
    )
    # Pydantic validator on body catches this before service
    assert r.status_code == 422


def test_state_log_records_actor_and_reason():
    db, _, _, _, _ = _make_db()
    client = _client(db)
    tok = _login(client, "editor@test.io")
    bid = client.post("/decision-briefs", json={"question": "Q?"}, headers=_hdr(tok)).json()["brief_id"]
    client.post(f"/decision-briefs/{bid}/transitions",
                json={"to_state": "human_review", "reason": "QA review"},
                headers=_hdr(tok))
    body = client.get(f"/decision-briefs/{bid}", headers=_hdr(tok)).json()
    last = body["state_log"][-1]
    assert last["from_state"] == "draft"
    assert last["to_state"] == "human_review"
    assert last["actor_user_id"] == "uuid-editor"
    assert last["reason"] == "QA review"


# ────────────────────────────────────────────────────────────────────
# PATCH (edit fields)
# ────────────────────────────────────────────────────────────────────

def test_patch_in_draft_state_succeeds():
    db, _, _, _, _ = _make_db()
    client = _client(db)
    tok = _login(client, "editor@test.io")
    bid = client.post("/decision-briefs", json={"question": "Q?"}, headers=_hdr(tok)).json()["brief_id"]
    r = client.patch(
        f"/decision-briefs/{bid}",
        json={"question": "Updated Q?", "stakeholders": ["medical"]},
        headers=_hdr(tok),
    )
    assert r.status_code == 200, r.text
    assert r.json()["question"] == "Updated Q?"
    assert r.json()["stakeholders"] == ["medical"]


def test_patch_in_committed_state_returns_409():
    db, briefs, _, _, _ = _make_db()
    client = _client(db)
    tok = _login(client, "editor@test.io")
    bid = client.post("/decision-briefs", json={"question": "Q?"}, headers=_hdr(tok)).json()["brief_id"]
    briefs[bid]["state"] = "committed"
    r = client.patch(f"/decision-briefs/{bid}",
                     json={"question": "Try edit"}, headers=_hdr(tok))
    assert r.status_code == 409


# ────────────────────────────────────────────────────────────────────
# Archive
# ────────────────────────────────────────────────────────────────────

def test_archive_draft_brief():
    db, briefs, _, _, _ = _make_db()
    client = _client(db)
    tok = _login(client, "editor@test.io")
    bid = client.post("/decision-briefs", json={"question": "Q?"}, headers=_hdr(tok)).json()["brief_id"]
    r = client.delete(f"/decision-briefs/{bid}", headers=_hdr(tok))
    assert r.status_code == 200
    # After archive, GET without include_archived returns 404
    g = client.get(f"/decision-briefs/{bid}", headers=_hdr(tok))
    assert g.status_code == 404
    # With include_archived=true, returns the brief
    g = client.get(f"/decision-briefs/{bid}?include_archived=true", headers=_hdr(tok))
    assert g.status_code == 200


def test_archive_committed_brief_returns_409():
    db, briefs, _, _, _ = _make_db()
    client = _client(db)
    tok = _login(client, "editor@test.io")
    bid = client.post("/decision-briefs", json={"question": "Q?"}, headers=_hdr(tok)).json()["brief_id"]
    briefs[bid]["state"] = "committed"
    r = client.delete(f"/decision-briefs/{bid}", headers=_hdr(tok))
    assert r.status_code == 409


# ────────────────────────────────────────────────────────────────────
# Auth
# ────────────────────────────────────────────────────────────────────

def test_create_requires_editor_role():
    db, _, _, _, _ = _make_db()
    client = _client(db)
    tok = _login(client, "viewer@test.io")  # viewer cannot create
    r = client.post("/decision-briefs", json={"question": "Q?"}, headers=_hdr(tok))
    assert r.status_code in (401, 403)


def test_unauthenticated_create_returns_401():
    db, _, _, _, _ = _make_db()
    client = _client(db)
    r = client.post("/decision-briefs", json={"question": "Q?"})
    assert r.status_code in (401, 403)


def test_unauthenticated_list_returns_401():
    db, _, _, _, _ = _make_db()
    client = _client(db)
    r = client.get("/decision-briefs")
    assert r.status_code in (401, 403)


# ────────────────────────────────────────────────────────────────────
# RED-TEAM — explicit attack vectors
# ────────────────────────────────────────────────────────────────────
#
# A1. SQL injection via state filter            → covered by test_list_rejects_invalid_state_filter (state must be enum)
# A2. SQL injection via owner_user_id           → str() coercion + parameterized; cannot inject
# A3. JSONB injection via evidence_refs         → json.dumps() server-side; never f-string
# A4. UUID confusion (passing brief_id as state)→ pydantic validators reject
# A5. Massive payload (DoS via large evidence_refs) → covered by A6
# A6. Excessive option count (DoS)              → no DB-level cap yet; service relies on rate limiter (SPEC-021 D2)
#                                                 RECOMMENDATION: add max_options=50 service-level guard in follow-up
# A7. State race (two concurrent transitions)   → DB row-level lock recommended; current impl is best-effort
# A8. Cross-tenant leak                          → owner_user_id filter + future RBAC check on get/patch
# A9. Replay/idempotency                         → no automatic idempotency on create; intentional (multiple briefs
#                                                 from the same trigger are valid by spec)
# A10. Malformed UUIDs in trigger_signal_ids    → DB cast to ::uuid[] rejects with 500; SHOULD return 400.
#       Add explicit pydantic validation for UUID format in follow-up.

def test_redteam_a3_evidence_refs_cannot_inject_via_jsonb():
    """Even if a malicious user puts SQL-looking content in evidence_refs,
    the service json.dumps() it into a parameterized JSONB cast — no injection
    risk. We just verify it round-trips intact."""
    db, _, _, _, _ = _make_db()
    client = _client(db)
    tok = _login(client, "editor@test.io")
    payload = {
        "question": "x?",
        "evidence_refs": [
            {"type": "signal", "id": "sig-1", "extra": "'; DROP TABLE decision_briefs; --"},
        ],
    }
    r = client.post("/decision-briefs", json=payload, headers=_hdr(tok))
    assert r.status_code == 201
    assert r.json()["evidence_refs"][0]["extra"].startswith("'; DROP")


def test_redteam_a4_uuid_confusion_via_to_state_field():
    """Confirm pydantic field_validator rejects non-state values to prevent
    accidental UUID-leakage into state column."""
    db, _, _, _, _ = _make_db()
    client = _client(db)
    tok = _login(client, "editor@test.io")
    bid = client.post("/decision-briefs", json={"question": "Q?"}, headers=_hdr(tok)).json()["brief_id"]
    r = client.post(
        f"/decision-briefs/{bid}/transitions",
        json={"to_state": "00000000-0000-0000-0000-000000000000"},
        headers=_hdr(tok),
    )
    assert r.status_code == 422


# ════════════════════════════════════════════════════════════════════
# Regression tests for prod bugs B1
# ════════════════════════════════════════════════════════════════════

def test_b1_postgres_array_literal_string_doesnt_split_chars():
    """Regression for prod bug: psycopg2 sometimes returns Postgres array
    literals as the string '{}' instead of a list []. The hydrator must
    detect and treat as empty (not split into ['{', '}'])."""
    from services.decision_brief import _row_to_brief
    from datetime import datetime, timezone
    row = {
        "brief_id": "brf-x", "question": "x", "trigger_kind": "manual",
        "trigger_signal_ids": "{}",  # string, not list
        "trigger_metadata": {}, "stakeholders": [], "time_horizon_days": None,
        "evidence_refs": [], "constraints": [], "success_criteria": None,
        "confidence_to_proceed": None, "state": "draft",
        "owner_user_id": None, "war_room_id": None, "decision_id": None,
        "archived_at": None,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    brief = _row_to_brief(row)
    assert brief.trigger_signal_ids == []  # NOT ["{", "}"]


def test_b1_populated_array_literal_string_parses_uuids():
    from services.decision_brief import _row_to_brief
    from datetime import datetime, timezone
    row = {
        "brief_id": "brf-x", "question": "x", "trigger_kind": "manual",
        "trigger_signal_ids": "{aaaa-1111,bbbb-2222}",
        "trigger_metadata": {}, "stakeholders": [], "time_horizon_days": None,
        "evidence_refs": [], "constraints": [], "success_criteria": None,
        "confidence_to_proceed": None, "state": "draft",
        "owner_user_id": None, "war_room_id": None, "decision_id": None,
        "archived_at": None,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    brief = _row_to_brief(row)
    assert brief.trigger_signal_ids == ["aaaa-1111", "bbbb-2222"]
