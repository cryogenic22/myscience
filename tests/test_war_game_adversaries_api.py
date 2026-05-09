"""SPEC_028 — War-Game Adversaries tests.

Covers: orchestrator with stub reactor produces grounded actions, brief
state gating, missing options rejection, grounding rule enforcement,
cancel state machine, transcript ordering, auth gates, red-team.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest


# ────────────────────────────────────────────────────────────────────
# Fake DB
# ────────────────────────────────────────────────────────────────────

def _make_db(seed_brief: bool = True, brief_state: str = "human_review"):
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

    briefs: dict[str, dict] = {}
    options_by_brief: dict[str, list[dict]] = {}
    runs: dict[str, dict] = {}
    advs: dict[str, dict] = {}
    actions: dict[str, dict] = {}
    next_id = [1]

    def _gen(p):
        n = next_id[0]; next_id[0] += 1
        return f"{p}-{n:04d}"

    if seed_brief:
        bid = "brf-0001"
        briefs[bid] = {"brief_id": bid, "state": brief_state, "decision_id": None}
        options_by_brief[bid] = [
            {"option_id": "opt-1", "ordinal": 1, "label": "Accelerate readout",
             "description": "Move readout up 4 months", "brief_id": bid},
            {"option_id": "opt-2", "ordinal": 2, "label": "Hold and observe",
             "description": "Maintain current schedule", "brief_id": bid},
        ]

    def fake_fetch_one(sql, params=None):
        s = (sql or "").lower()

        if "from users" in s and params:
            if "where lower(email)" in s or "where email" in s:
                return users.get(str(params[0]).lower())
            if "where id::text" in s or "where id =" in s:
                for u in users.values():
                    if u["id"] == params[0]: return u
                return None

        # SELECT brief
        if (
            "from decision_briefs" in s
            and "brief_id::text = %s" in s
            and "insert" not in s
            and params
        ):
            return briefs.get(str(params[0]))

        # INSERT war_game_runs RETURNING
        if "insert into war_game_runs" in s and "returning" in s and params:
            rid = _gen("run")
            row = {
                "run_id": rid,
                "brief_id": params[0],
                "status": "running",
                "num_rounds": params[1],
                "started_at": datetime.now(timezone.utc),
                "completed_at": None,
                "failure_reason": None,
                "summary_jsonb": {},
                "started_by_user_id": params[2],
            }
            runs[rid] = row
            return row

        # INSERT adversary RETURNING
        if "insert into war_game_adversaries" in s and "returning" in s and params:
            aid = _gen("adv")
            row = {
                "adversary_id": aid,
                "run_id": params[0],
                "kind": params[1],
                "name": params[2],
                "entity_type": params[3],
                "entity_id": params[4],
                "persona_jsonb": json.loads(params[5]) if isinstance(params[5], str) else (params[5] or {}),
                "grounding_evidence_ids": list(params[6] or []),
                "created_at": datetime.now(timezone.utc),
            }
            advs[aid] = row
            return row

        # INSERT action RETURNING
        if "insert into war_game_actions" in s and "returning" in s and params:
            aid = _gen("act")
            row = {
                "action_id": aid,
                "run_id": params[0],
                "adversary_id": params[1],
                "option_id": params[2],
                "round_num": params[3],
                "action_kind": params[4],
                "action_text": params[5],
                "grounding_evidence_id": params[6],
                "grounding_precedent": params[7],
                "confidence": params[8],
                "llm_call_id": params[9],
                "created_at": datetime.now(timezone.utc),
            }
            actions[aid] = row
            return row

        # SELECT run by id
        if "from war_game_runs" in s and "run_id::text = %s" in s and params:
            return runs.get(str(params[0]))

        return None

    def fake_fetch_all(sql, params=None):
        s = (sql or "").lower()

        # SELECT options
        if "from decision_brief_options" in s and "brief_id::text = %s" in s and params:
            return options_by_brief.get(str(params[0]), [])

        # SELECT adversaries
        if "from war_game_adversaries" in s and "where run_id::text = %s" in s and params:
            return sorted(
                [a for a in advs.values() if str(a["run_id"]) == str(params[0])],
                key=lambda a: a["created_at"],
            )

        # SELECT actions
        if "from war_game_actions" in s and "where run_id::text = %s" in s and params:
            out = [a for a in actions.values() if str(a["run_id"]) == str(params[0])]
            out.sort(key=lambda a: (a["round_num"], a["adversary_id"]))
            return out

        # LIST runs
        if "from war_game_runs" in s and "limit" in s:
            out = list(runs.values())
            if params:
                idx = 0
                if "brief_id::text = %s" in s:
                    out = [r for r in out if str(r["brief_id"]) == str(params[idx])]; idx += 1
                if "status = %s" in s:
                    out = [r for r in out if r["status"] == params[idx]]; idx += 1
                limit = params[-2]; offset = params[-1]
                out = sorted(out, key=lambda r: r["started_at"], reverse=True)
                out = out[offset:offset + limit]
            return out

        return []

    def fake_execute(sql, params=None):
        s = (sql or "").lower()
        if (
            "update war_game_runs" in s
            and "where run_id::text = %s" in s
            and params
        ):
            rid = str(params[-1])
            if rid not in runs: return None
            if "status = 'complete'" in s:
                runs[rid]["status"] = "complete"
                runs[rid]["completed_at"] = datetime.now(timezone.utc)
                v = params[0]
                runs[rid]["summary_jsonb"] = json.loads(v) if isinstance(v, str) else (v or {})
            elif "status = 'cancelled'" in s:
                runs[rid]["status"] = "cancelled"
                runs[rid]["completed_at"] = datetime.now(timezone.utc)
                runs[rid]["failure_reason"] = "cancelled by user"
            elif "status = 'failed'" in s:
                runs[rid]["status"] = "failed"
                runs[rid]["completed_at"] = datetime.now(timezone.utc)
                runs[rid]["failure_reason"] = params[0]
            return None
        return None

    db = MagicMock()
    db.fetch_one.side_effect = fake_fetch_one
    db.fetch_all.side_effect = fake_fetch_all
    db.execute.side_effect = fake_execute
    return db, briefs, options_by_brief, runs, advs, actions


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


def _start_payload(brief_id="brf-0001", num_rounds=2):
    return {
        "brief_id": brief_id,
        "num_rounds": num_rounds,
        "adversaries": [
            {"kind": "competitor", "name": "Pfizer Oncology",
             "entity_type": "company", "entity_id": "00000000-0000-0000-0000-000000000001",
             "persona": {"strategy": "fast-follower"},
             "grounding_evidence_ids": ["00000000-0000-0000-0000-000000000a01"]},
            {"kind": "payer", "name": "CVS Caremark",
             "persona": {"book": "PBM"},
             "grounding_evidence_ids": ["00000000-0000-0000-0000-000000000b01",
                                        "00000000-0000-0000-0000-000000000b02"]},
        ],
    }


# ────────────────────────────────────────────────────────────────────
# Module + routes
# ────────────────────────────────────────────────────────────────────

def test_module_imports():
    from api.routes import war_games as r
    from services.war_game_adversary import WarGameOrchestrator, StubReactor
    assert r.router.prefix == "/war-games"


def test_routes_registered():
    from api.app import create_app
    app = create_app()
    paths = {getattr(r, "path", "") for r in app.routes}
    assert "/war-games" in paths
    assert "/war-games/{run_id}" in paths
    assert "/war-games/{run_id}/transcript" in paths
    assert "/war-games/{run_id}/cancel" in paths


# ────────────────────────────────────────────────────────────────────
# Pure orchestrator unit tests (no HTTP)
# ────────────────────────────────────────────────────────────────────

class TestStubReactor:
    def test_grounding_required_in_persona(self):
        from services.war_game_adversary import StubReactor, WarGameAdversary, GroundingRuleViolation
        adv = WarGameAdversary(
            adversary_id="a-1", run_id="r-1", kind="competitor", name="X",
            entity_type=None, entity_id=None, persona={}, grounding_evidence_ids=[],
        )
        r = StubReactor()
        with pytest.raises(GroundingRuleViolation):
            r.react(adversary=adv, option={"option_id": "o", "label": "Test"},
                    round_num=1, prior_actions=[])

    def test_returns_grounded_output(self):
        from services.war_game_adversary import StubReactor, WarGameAdversary
        adv = WarGameAdversary(
            adversary_id="a-1", run_id="r-1", kind="payer", name="CVS",
            entity_type=None, entity_id=None, persona={},
            grounding_evidence_ids=["e-1", "e-2"],
        )
        out = StubReactor().react(
            adversary=adv, option={"option_id": "o", "label": "Tier 2"},
            round_num=1, prior_actions=[],
        )
        assert out.grounding_evidence_id in ("e-1", "e-2")
        assert out.action_kind == "react"
        assert "CVS" in out.action_text
        assert "Tier 2" in out.action_text


# ────────────────────────────────────────────────────────────────────
# API: start runs
# ────────────────────────────────────────────────────────────────────

def test_start_run_minimal():
    db, _, _, runs, advs, actions = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    r = client.post("/war-games", json=_start_payload(num_rounds=2), headers=_hdr(tok))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "complete"
    assert body["num_rounds"] == 2
    assert body["brief_id"] == "brf-0001"
    assert len(body["adversaries"]) == 2
    # 2 options × 2 adversaries × 2 rounds = 8 actions
    assert len(body["actions"]) == 8
    assert body["summary"]["total_actions"] == 8


def test_start_run_404_for_unknown_brief():
    db, _, _, _, _, _ = _make_db(seed_brief=False)
    client = _client(db); tok = _login(client, "editor@test.io")
    r = client.post("/war-games", json=_start_payload(brief_id="nope"), headers=_hdr(tok))
    assert r.status_code == 404


def test_start_run_409_for_brief_in_wrong_state():
    db, _, _, _, _, _ = _make_db(brief_state="committed")
    client = _client(db); tok = _login(client, "editor@test.io")
    r = client.post("/war-games", json=_start_payload(), headers=_hdr(tok))
    assert r.status_code == 409


def test_start_run_409_for_brief_with_no_options():
    db, _, opts, _, _, _ = _make_db()
    opts["brf-0001"] = []  # remove options
    client = _client(db); tok = _login(client, "editor@test.io")
    r = client.post("/war-games", json=_start_payload(), headers=_hdr(tok))
    assert r.status_code == 409
    assert "no options" in r.json().get("detail", "").lower()


def test_start_run_rejects_too_many_rounds():
    db, _, _, _, _, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    payload = _start_payload(num_rounds=99)
    r = client.post("/war-games", json=payload, headers=_hdr(tok))
    assert r.status_code == 422


def test_start_run_rejects_no_adversaries():
    db, _, _, _, _, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    payload = _start_payload()
    payload["adversaries"] = []
    r = client.post("/war-games", json=payload, headers=_hdr(tok))
    assert r.status_code == 422


def test_start_run_422_for_adversary_without_grounding():
    """The grounding rule is enforced at the SCHEMA level (min_length=1)."""
    db, _, _, _, _, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    payload = _start_payload()
    payload["adversaries"][0]["grounding_evidence_ids"] = []
    r = client.post("/war-games", json=payload, headers=_hdr(tok))
    assert r.status_code == 422


def test_start_run_invalid_kind():
    db, _, _, _, _, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    payload = _start_payload()
    payload["adversaries"][0]["kind"] = "wizard"
    r = client.post("/war-games", json=payload, headers=_hdr(tok))
    assert r.status_code == 422


# ────────────────────────────────────────────────────────────────────
# Get / list / transcript
# ────────────────────────────────────────────────────────────────────

def test_get_run_returns_panel():
    db, _, _, _, _, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    rid = client.post("/war-games", json=_start_payload(num_rounds=1), headers=_hdr(tok)).json()["run_id"]
    vtok = _login(client, "viewer@test.io")
    r = client.get(f"/war-games/{rid}", headers=_hdr(vtok))
    assert r.status_code == 200
    body = r.json()
    assert body["run_id"] == rid
    assert len(body["adversaries"]) == 2
    # GET (run) doesn't include actions by default
    assert "actions" not in body or body.get("actions") == []


def test_transcript_returns_actions_ordered():
    db, _, _, _, _, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    rid = client.post("/war-games", json=_start_payload(num_rounds=2), headers=_hdr(tok)).json()["run_id"]
    vtok = _login(client, "viewer@test.io")
    r = client.get(f"/war-games/{rid}/transcript", headers=_hdr(vtok))
    assert r.status_code == 200
    body = r.json()
    assert "actions" in body
    # 2 options × 2 adversaries × 2 rounds = 8
    assert len(body["actions"]) == 8
    # Sorted by round_num ASC
    rounds = [a["round_num"] for a in body["actions"]]
    assert rounds == sorted(rounds)


def test_list_runs_filters_by_brief():
    db, _, _, _, _, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    client.post("/war-games", json=_start_payload(num_rounds=1), headers=_hdr(tok))
    vtok = _login(client, "viewer@test.io")
    r = client.get("/war-games?brief_id=brf-0001", headers=_hdr(vtok))
    assert r.status_code == 200
    assert r.json()["count"] == 1


def test_list_runs_invalid_status_returns_400():
    db, _, _, _, _, _ = _make_db()
    client = _client(db); tok = _login(client, "viewer@test.io")
    r = client.get("/war-games?status=quantum", headers=_hdr(tok))
    assert r.status_code == 400


def test_get_run_404_for_unknown():
    db, _, _, _, _, _ = _make_db()
    client = _client(db); tok = _login(client, "viewer@test.io")
    r = client.get("/war-games/run-999", headers=_hdr(tok))
    assert r.status_code == 404


# ────────────────────────────────────────────────────────────────────
# Cancel
# ────────────────────────────────────────────────────────────────────

def test_cancel_complete_run_returns_409():
    db, _, _, runs, _, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    rid = client.post("/war-games", json=_start_payload(num_rounds=1), headers=_hdr(tok)).json()["run_id"]
    # Run completes synchronously; status='complete'
    r = client.post(f"/war-games/{rid}/cancel", headers=_hdr(tok))
    assert r.status_code == 409


def test_cancel_running_run_succeeds():
    """Manually flip a run to 'running' to test the cancel path."""
    db, _, _, runs, _, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    rid = client.post("/war-games", json=_start_payload(num_rounds=1), headers=_hdr(tok)).json()["run_id"]
    # Force back to running for test
    runs[rid]["status"] = "running"
    r = client.post(f"/war-games/{rid}/cancel", headers=_hdr(tok))
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"


# ────────────────────────────────────────────────────────────────────
# Auth
# ────────────────────────────────────────────────────────────────────

def test_unauth_start_returns_401():
    db, _, _, _, _, _ = _make_db()
    client = _client(db)
    r = client.post("/war-games", json=_start_payload())
    assert r.status_code in (401, 403)


def test_start_requires_uploader():
    db, _, _, _, _, _ = _make_db()
    client = _client(db); tok = _login(client, "viewer@test.io")
    r = client.post("/war-games", json=_start_payload(), headers=_hdr(tok))
    assert r.status_code in (401, 403)


# ────────────────────────────────────────────────────────────────────
# Red-team
# ────────────────────────────────────────────────────────────────────

def test_R1_grounding_rule_enforced_in_schema():
    """R1: schema rejects adversary with empty grounding_evidence_ids
    (cannot reach the orchestrator's deeper enforcement)."""
    db, _, _, _, _, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    payload = _start_payload()
    for a in payload["adversaries"]:
        a["grounding_evidence_ids"] = []
    r = client.post("/war-games", json=payload, headers=_hdr(tok))
    assert r.status_code == 422
