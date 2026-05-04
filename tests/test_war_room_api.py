"""SPEC-021 — War Room API tests.

Endpoints:
  POST    /war-rooms                  viewer+   create (optional source_signal_id)
  GET     /war-rooms                  viewer+   list current user's rooms
  GET     /war-rooms/{id}             anon      detail with rounds + reactions
  POST    /war-rooms/{id}/rounds      owner     run a player move; returns reactions
  DELETE  /war-rooms/{id}             owner     soft delete

DB + LLM are mocked.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent


# ────────────────────────────────────────────────────────────────────
# Fake DB — users + war rooms + rounds + reactions
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
        "enterprise@demo.market-zero.io": {
            "id": "uuid-enterprise", "email": "enterprise@demo.market-zero.io",
            "password_hash": hash_password("demo"), "role": "enterprise",
            "is_active": True,
        },
    }
    rooms: dict[str, dict] = {}
    rounds: list[dict] = []
    reactions: list[dict] = []
    comments: list[dict] = []
    next_id = [1]

    def _gen_id(prefix: str) -> str:
        nid = f"{prefix}-{next_id[0]}"
        next_id[0] += 1
        return nid

    # ── Insert helpers shared by execute + fetch_one (RETURNING form) ──

    def _insert_war_room(params):
        rid = _gen_id("wr")
        rooms[rid] = {
            "id": rid,
            "title": params[0],
            "owner_user_id": params[1],
            "scenario_question": params[2],
            "primary_entity_type": params[3],
            "primary_entity_id": params[4],
            "primary_entity_name": params[5],
            "source_signal_id": params[6],
            "game_phase": params[7] if len(params) > 7 else "launch",
            "status": "active",
            "archived_at": None,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
        return rid

    def _insert_war_room_round(params):
        rid = _gen_id("rnd")
        rounds.append({
            "id": rid,
            "war_room_id": params[0],
            "round_number": params[1],
            "player_company_id": params[2],
            "player_company_name": params[3],
            "move_type": params[4],
            "move_payload": params[5],
            "notes": params[6] if len(params) > 6 else None,
            "created_at": datetime.now(timezone.utc),
        })
        return rid

    def _insert_war_room_reaction(params):
        rid = _gen_id("rxn")
        if len(params) >= 14:
            reactions.append({
                "id": rid,
                "round_id": params[0],
                "competitor_company_id": params[1],
                "competitor_company_name": params[2],
                "reaction_type": params[3],
                "headline": params[4],
                "specific_action": params[5],
                "asset_leveraged": params[6],
                "rationale": params[7],
                "evidence_basis": params[8],
                "stripped_citations": params[9],
                "evidence_validated": params[10],
                "scores": params[11],
                "confidence_score": params[12],
                "confidence": params[13],
                "created_at": datetime.now(timezone.utc),
            })
        else:
            reactions.append({
                "id": rid,
                "round_id": params[0],
                "competitor_company_id": params[1],
                "competitor_company_name": params[2],
                "reaction_type": params[3],
                "headline": params[4],
                "specific_action": params[5],
                "asset_leveraged": params[6],
                "rationale": params[7],
                "evidence_basis": params[8],
                "scores": params[9],
                "confidence": params[10],
                "created_at": datetime.now(timezone.utc),
            })
        return rid

    def _insert_comment(params):
        cid = _gen_id("cmt")
        c = {
            "id": cid,
            "war_room_id": params[0],
            "round_id": params[1],
            "author_user_id": params[2],
            "author_display_name": params[3],
            "body": params[4],
            "created_at": datetime.now(timezone.utc),
            "edited_at": None,
        }
        comments.append(c)
        return c

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
        # INSERT INTO war_rooms ... RETURNING id (via fetch_one)
        if "insert into war_rooms" in s and "returning" in s and params:
            rid = _insert_war_room(params)
            return {"id": rid}
        # INSERT INTO war_room_rounds ... RETURNING id (via fetch_one)
        if "insert into war_room_rounds" in s and "returning" in s and params:
            rid = _insert_war_room_round(params)
            return {"id": rid}
        # INSERT INTO war_room_comments ... RETURNING ... (via fetch_one)
        if "insert into war_room_comments" in s and "returning" in s and params:
            return _insert_comment(params)
        # War room read-back by id::text
        if "from war_rooms" in s and "id::text" in s and params:
            return dict(rooms.get(str(params[0]))) if rooms.get(str(params[0])) else None
        # Legacy path: WHERE id = (with cast-style)
        if "from war_rooms" in s and "where id" in s and "owner_user_id" not in s and params:
            return dict(rooms.get(str(params[0]))) if rooms.get(str(params[0])) else None
        # Legacy create read-back (kept for back-compat, no longer hit)
        if "from war_rooms" in s and "owner_user_id" in s and "title" in s and params:
            owner, title = params[0], params[1]
            matches = [r for r in rooms.values()
                       if r.get("owner_user_id") == owner and r.get("title") == title]
            if matches:
                return dict(sorted(matches, key=lambda r: r["created_at"], reverse=True)[0])
            return None
        # Round MAX(round_number)
        if "from war_room_rounds" in s and "max" in s and params:
            wr_id = str(params[0])
            mx = max(
                (r["round_number"] for r in rounds if r["war_room_id"] == wr_id),
                default=0,
            )
            return {"max_round": mx}
        # Round read-back by id::text (post-RETURNING refactor)
        if "from war_room_rounds" in s and "id::text" in s and params:
            for r in rounds:
                if r["id"] == str(params[0]):
                    return dict(r)
            return None
        # Round read-back by (war_room_id, round_number) — legacy
        if "from war_room_rounds" in s and "round_number" in s and "war_room_id" in s and params:
            wr_id, rn = str(params[0]), params[1]
            for r in rounds:
                if r["war_room_id"] == wr_id and r["round_number"] == rn:
                    return dict(r)
            return None
        # Round sanity check (war_room_id only)
        if "war_room_id from war_room_rounds" in s and params:
            for r in rounds:
                if r["id"] == str(params[0]):
                    return {"war_room_id": r["war_room_id"]}
            return None
        # Comment by id::text
        if "from war_room_comments" in s and "id::text" in s and params:
            for c in comments:
                if c["id"] == str(params[0]):
                    return dict(c)
            return None
        return None

    def fake_fetch_all(sql, params=None):
        s = (sql or "").lower()
        # War rooms list with optional filters (always starts with owner)
        if "from war_rooms" in s and "owner_user_id" in s and params:
            owner = params[0]
            out = [dict(r) for r in rooms.values() if r.get("owner_user_id") == owner]
            idx = 1
            if "status = %s" in s:
                out = [r for r in out if r.get("status") == params[idx]]
                idx += 1
            if "archived_at is not null" in s:
                out = [r for r in out if r.get("archived_at") is not None]
            elif "archived_at is null" in s:
                out = [r for r in out if r.get("archived_at") is None]
            if "title ilike %s" in s:
                pattern = (params[idx] or "").strip("%").lower()
                out = [r for r in out if pattern in (r.get("title") or "").lower()]
                idx += 1
            if "primary_entity_id = %s" in s:
                out = [r for r in out if r.get("primary_entity_id") == params[idx]]
                idx += 1
            return sorted(out, key=lambda r: r.get("created_at"), reverse=True)
        if "from war_room_rounds" in s and params:
            wr_id = str(params[0])
            return sorted(
                [dict(r) for r in rounds if r["war_room_id"] == wr_id],
                key=lambda r: r["round_number"],
            )
        if "from war_room_reactions" in s and params:
            round_id = str(params[0])
            return [dict(r) for r in reactions if r["round_id"] == round_id]
        if "from war_room_comments" in s and "round_id" in s and "war_room_id" in s and params and len(params) >= 2:
            return sorted(
                [dict(c) for c in comments
                 if c["war_room_id"] == str(params[0]) and str(c.get("round_id")) == str(params[1])],
                key=lambda c: c["created_at"],
            )
        if "from war_room_comments" in s and params:
            return sorted(
                [dict(c) for c in comments if c["war_room_id"] == str(params[0])],
                key=lambda c: c["created_at"],
            )
        return []

    def fake_execute(sql, params=None):
        s = (sql or "").lower()
        # PATCH war_rooms — must be tested BEFORE the DELETE/close path
        # (the close path is identifiable by literal `'closed'` in the SQL).
        if (
            "update war_rooms" in s
            and "where id::text" in s
            and "'closed'" not in s
            and params
        ):
            room_id = str(params[-1])
            if room_id not in rooms:
                return None
            pi = 0
            if "title = %s" in s:
                rooms[room_id]["title"] = params[pi]; pi += 1
            if "scenario_question = %s" in s:
                rooms[room_id]["scenario_question"] = params[pi]; pi += 1
            if "status = %s" in s:
                rooms[room_id]["status"] = params[pi]; pi += 1
            if "archived_at = now()" in s:
                rooms[room_id]["archived_at"] = datetime.now(timezone.utc)
            elif "archived_at = null" in s:
                rooms[room_id]["archived_at"] = None
            rooms[room_id]["updated_at"] = datetime.now(timezone.utc)
            return None
        # DELETE-style soft-close (status hardcoded 'closed')
        if "update war_rooms" in s and "set status" in s and "'closed'" in s and params:
            room_id = str(params[-1])
            if room_id in rooms:
                rooms[room_id]["status"] = "closed"
            return None
        # Legacy plain INSERT (no RETURNING) — keep for back-compat
        if "insert into war_rooms" in s and "returning" not in s and params:
            _insert_war_room(params)
            return None
        if "insert into war_room_rounds" in s and "returning" not in s and params:
            _insert_war_room_round(params)
            return None
        if "insert into war_room_reactions" in s and params:
            _insert_war_room_reaction(params)
            return None
        # Comment edit
        if "update war_room_comments" in s and params:
            cid = str(params[-1])
            for c in comments:
                if c["id"] == cid:
                    c["body"] = params[0]
                    c["edited_at"] = datetime.now(timezone.utc)
                    break
            return None
        # Comment delete
        if "delete from war_room_comments" in s and params:
            cid = str(params[0])
            for i, c in enumerate(comments):
                if c["id"] == cid:
                    comments.pop(i)
                    break
            return None
        if "insert into move_suggestions" in s and params:
            return None
        return None

    db = MagicMock()
    db.fetch_one.side_effect = fake_fetch_one
    db.fetch_all.side_effect = fake_fetch_all
    db.execute.side_effect = fake_execute
    return db, rooms, rounds, reactions


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


# Stubbed reaction generator that returns 2 deterministic reactions
def _stub_reactions(*args, **kwargs):
    return [
        {
            "competitor_company_id": "ent-lilly",
            "competitor_company_name": "Eli Lilly",
            "reaction_type": "counter_launch",
            "headline": "Accelerate tirzepatide MASH program",
            "specific_action": "Move SURMOUNT-MASH to Phase 3 by Q4",
            "asset_leveraged": {"id": "drug-tirzepatide", "name": "tirzepatide", "rationale": "Active Phase 2"},
            "rationale": "Tirzepatide has sufficient phase-2 data to support acceleration.",
            "evidence_basis": ["NCT05123456"],
            "scores": {
                "market_share_delta": 5, "time_to_execute_months": 12,
                "capex_required_musd": 250, "regulatory_risk": 4,
                "payer_acceptance": 7,
            },
            "confidence": "medium",
        },
        {
            "competitor_company_id": "ent-amgen",
            "competitor_company_name": "Amgen",
            "reaction_type": "hold_position",
            "headline": "Monitor MariTide readout before responding",
            "specific_action": "Wait for AMG-133 Phase 2 data",
            "asset_leveraged": {"id": "drug-maritide", "name": "MariTide", "rationale": "Pre-readout"},
            "rationale": "No actionable asset until Phase 2 reads out.",
            "evidence_basis": [],
            "scores": {
                "market_share_delta": 0, "time_to_execute_months": 6,
                "capex_required_musd": 50, "regulatory_risk": 2,
                "payer_acceptance": 5,
            },
            "confidence": "high",
        },
    ]


# ────────────────────────────────────────────────────────────────────
# Module + routes
# ────────────────────────────────────────────────────────────────────

def test_war_room_route_module_exists():
    assert (REPO_ROOT / "api" / "routes" / "war_room.py").exists()


def test_war_room_routes_registered():
    from api.app import create_app
    app = create_app()
    paths = {getattr(r, "path", None) for r in app.routes}
    assert any(p and p.endswith("/war-rooms") for p in paths)
    assert any(p and "/war-rooms/" in (p or "") for p in paths)


# ────────────────────────────────────────────────────────────────────
# POST /war-rooms — create
# ────────────────────────────────────────────────────────────────────

def test_create_room_401_anonymous():
    db, _, _, _ = _make_db()
    r = _client(db).post("/war-rooms", json={
        "title": "Pfizer guidance scenario",
        "primary_entity_type": "company",
        "primary_entity_id": "ent-pfizer",
        "primary_entity_name": "Pfizer Inc.",
    })
    assert r.status_code == 401


def test_create_room_201_for_viewer():
    db, rooms, _, _ = _make_db()
    client = _client(db)
    tok = _login(client, "viewer@demo.market-zero.io")
    r = client.post("/war-rooms", headers=_hdr(tok), json={
        "title": "Pfizer guidance scenario",
        "scenario_question": "What if Pfizer raises FY guidance?",
        "primary_entity_type": "company",
        "primary_entity_id": "ent-pfizer",
        "primary_entity_name": "Pfizer Inc.",
        "game_phase": "launch",
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["title"] == "Pfizer guidance scenario"
    assert body["primary_entity_id"] == "ent-pfizer"
    assert body["status"] == "active"
    assert body["owner_user_id"] == "uuid-viewer"
    assert len(rooms) == 1


def test_create_room_with_source_signal_id():
    db, rooms, _, _ = _make_db()
    client = _client(db)
    tok = _login(client, "viewer@demo.market-zero.io")
    r = client.post("/war-rooms", headers=_hdr(tok), json={
        "title": "From signal X",
        "source_signal_id": "sig-abc",
        "primary_entity_type": "company",
        "primary_entity_id": "ent-pfizer",
        "primary_entity_name": "Pfizer Inc.",
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["source_signal_id"] == "sig-abc"


# ────────────────────────────────────────────────────────────────────
# GET /war-rooms — list
# ────────────────────────────────────────────────────────────────────

def test_list_rooms_401_anonymous():
    db, _, _, _ = _make_db()
    r = _client(db).get("/war-rooms")
    assert r.status_code == 401


def test_list_rooms_returns_only_users_own():
    db, _, _, _ = _make_db()
    client = _client(db)
    vt = _login(client, "viewer@demo.market-zero.io")
    ut = _login(client, "uploader@demo.market-zero.io")
    client.post("/war-rooms", headers=_hdr(vt), json={
        "title": "viewer's room",
        "primary_entity_type": "company", "primary_entity_id": "x",
        "primary_entity_name": "X",
    })
    client.post("/war-rooms", headers=_hdr(ut), json={
        "title": "uploader's room",
        "primary_entity_type": "company", "primary_entity_id": "y",
        "primary_entity_name": "Y",
    })
    r = client.get("/war-rooms", headers=_hdr(vt)).json()
    assert len(r["war_rooms"]) == 1
    assert r["war_rooms"][0]["title"] == "viewer's room"


# ────────────────────────────────────────────────────────────────────
# GET /war-rooms/{id} — detail (anon)
# ────────────────────────────────────────────────────────────────────

def test_detail_endpoint_anon_returns_room():
    db, _, _, _ = _make_db()
    client = _client(db)
    tok = _login(client, "viewer@demo.market-zero.io")
    create = client.post("/war-rooms", headers=_hdr(tok), json={
        "title": "anon-readable",
        "primary_entity_type": "company", "primary_entity_id": "x",
        "primary_entity_name": "X",
    })
    rid = create.json()["id"]
    # Anonymous read
    r = client.get(f"/war-rooms/{rid}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == rid
    assert "rounds" in body


def test_detail_endpoint_404_for_unknown_id():
    db, _, _, _ = _make_db()
    r = _client(db).get("/war-rooms/does-not-exist")
    assert r.status_code == 404


# ────────────────────────────────────────────────────────────────────
# POST /war-rooms/{id}/rounds — submit move
# ────────────────────────────────────────────────────────────────────

def test_round_endpoint_401_anonymous():
    db, _, _, _ = _make_db()
    client = _client(db)
    tok = _login(client, "viewer@demo.market-zero.io")
    create = client.post("/war-rooms", headers=_hdr(tok), json={
        "title": "x", "primary_entity_type": "company",
        "primary_entity_id": "x", "primary_entity_name": "X",
    })
    rid = create.json()["id"]
    r = client.post(f"/war-rooms/{rid}/rounds", json={
        "move_type": "trial_readout",
        "move_payload": {"target_drug": "tirzepatide"},
    })
    assert r.status_code == 401


def test_round_endpoint_403_for_non_owner():
    db, _, _, _ = _make_db()
    client = _client(db)
    vt = _login(client, "viewer@demo.market-zero.io")
    create = client.post("/war-rooms", headers=_hdr(vt), json={
        "title": "owned by viewer",
        "primary_entity_type": "company", "primary_entity_id": "x",
        "primary_entity_name": "X",
    })
    rid = create.json()["id"]
    # Different user tries to add a round
    ut = _login(client, "uploader@demo.market-zero.io")
    r = client.post(
        f"/war-rooms/{rid}/rounds", headers=_hdr(ut),
        json={"move_type": "price_cut", "move_payload": {}},
    )
    assert r.status_code == 403


def test_round_endpoint_200_for_owner_returns_reactions():
    db, _, rounds_store, reactions_store = _make_db()
    client = _client(db)
    tok = _login(client, "viewer@demo.market-zero.io")
    create = client.post("/war-rooms", headers=_hdr(tok), json={
        "title": "test room",
        "primary_entity_type": "company",
        "primary_entity_id": "ent-novo",
        "primary_entity_name": "Novo Nordisk",
    })
    rid = create.json()["id"]

    with patch(
        "api.routes.war_room._generate_reactions",
        side_effect=_stub_reactions,
    ):
        r = client.post(
            f"/war-rooms/{rid}/rounds", headers=_hdr(tok),
            json={
                "move_type": "trial_readout",
                "move_payload": {"target_drug": "semaglutide", "endpoint": "MACE"},
                "notes": "Round 1",
            },
        )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["round_number"] == 1
    assert body["move_type"] == "trial_readout"
    assert "reactions" in body
    assert len(body["reactions"]) == 2
    rxn = body["reactions"][0]
    assert "scores" in rxn
    assert "reaction_type" in rxn
    assert len(rounds_store) == 1
    assert len(reactions_store) == 2


def test_round_endpoint_increments_round_number():
    db, _, _, _ = _make_db()
    client = _client(db)
    tok = _login(client, "viewer@demo.market-zero.io")
    create = client.post("/war-rooms", headers=_hdr(tok), json={
        "title": "multi-round room",
        "primary_entity_type": "company",
        "primary_entity_id": "ent-novo", "primary_entity_name": "Novo",
    })
    rid = create.json()["id"]

    with patch(
        "api.routes.war_room._generate_reactions",
        side_effect=_stub_reactions,
    ):
        r1 = client.post(f"/war-rooms/{rid}/rounds", headers=_hdr(tok),
                         json={"move_type": "price_cut", "move_payload": {}})
        r2 = client.post(f"/war-rooms/{rid}/rounds", headers=_hdr(tok),
                         json={"move_type": "label_expansion", "move_payload": {}})

    assert r1.json()["round_number"] == 1
    assert r2.json()["round_number"] == 2


# ────────────────────────────────────────────────────────────────────
# DELETE /war-rooms/{id}
# ────────────────────────────────────────────────────────────────────

def test_delete_room_403_for_non_owner():
    db, _, _, _ = _make_db()
    client = _client(db)
    vt = _login(client, "viewer@demo.market-zero.io")
    create = client.post("/war-rooms", headers=_hdr(vt), json={
        "title": "x", "primary_entity_type": "company",
        "primary_entity_id": "x", "primary_entity_name": "X",
    })
    rid = create.json()["id"]
    ut = _login(client, "uploader@demo.market-zero.io")
    r = client.delete(f"/war-rooms/{rid}", headers=_hdr(ut))
    assert r.status_code in (403, 404)


def test_delete_room_204_for_owner():
    db, rooms_store, _, _ = _make_db()
    client = _client(db)
    tok = _login(client, "viewer@demo.market-zero.io")
    create = client.post("/war-rooms", headers=_hdr(tok), json={
        "title": "deletable",
        "primary_entity_type": "company", "primary_entity_id": "x",
        "primary_entity_name": "X",
    })
    rid = create.json()["id"]
    r = client.delete(f"/war-rooms/{rid}", headers=_hdr(tok))
    assert r.status_code == 204
    # Soft delete: status set to 'closed'
    assert rooms_store[rid]["status"] == "closed"


# ────────────────────────────────────────────────────────────────────
# Move type validation
# ────────────────────────────────────────────────────────────────────

def test_round_endpoint_400_for_invalid_move_type():
    db, _, _, _ = _make_db()
    client = _client(db)
    tok = _login(client, "viewer@demo.market-zero.io")
    create = client.post("/war-rooms", headers=_hdr(tok), json={
        "title": "x", "primary_entity_type": "company",
        "primary_entity_id": "x", "primary_entity_name": "X",
    })
    rid = create.json()["id"]
    r = client.post(f"/war-rooms/{rid}/rounds", headers=_hdr(tok),
                    json={"move_type": "do_a_dance", "move_payload": {}})
    assert r.status_code == 400


# ────────────────────────────────────────────────────────────────────
# Audit fix #1: GET reaction returns strengthening fields after persist
# ────────────────────────────────────────────────────────────────────

def test_get_room_returns_strengthenings_in_reactions():
    """Regression: GET /war-rooms/{id} previously dropped confidence_score,
    stripped_citations, and evidence_validated from the reaction SELECT.
    The strengthenings landed in DB on POST but disappeared on GET."""
    db, _, _, _ = _make_db()
    client = _client(db)
    tok = _login(client, "viewer@demo.market-zero.io")
    create = client.post("/war-rooms", headers=_hdr(tok), json={
        "title": "strengthening regression test",
        "primary_entity_type": "company", "primary_entity_id": "ent-novo",
        "primary_entity_name": "Novo Nordisk",
    })
    rid = create.json()["id"]

    with patch("api.routes.war_room._generate_reactions",
               side_effect=_stub_reactions):
        client.post(
            f"/war-rooms/{rid}/rounds", headers=_hdr(tok),
            json={"move_type": "trial_readout",
                  "move_payload": {"target_drug": "semaglutide"}},
        )

    # GET via anon — confirm new fields round-trip
    r = client.get(f"/war-rooms/{rid}")
    assert r.status_code == 200
    body = r.json()
    assert len(body["rounds"]) == 1
    rxn = body["rounds"][0]["reactions"][0]
    # All three strengthenings present (not None / not missing)
    assert "confidence_score" in rxn, "confidence_score should be present in GET response"
    assert "stripped_citations" in rxn, "stripped_citations should be present"
    assert "evidence_validated" in rxn, "evidence_validated should be present"


# ────────────────────────────────────────────────────────────────────
# Audit fix #2: Partial INSERT failures surfaced in response
# ────────────────────────────────────────────────────────────────────

# ────────────────────────────────────────────────────────────────────
# Phase A.5: POST /war-rooms/{id}/suggest-moves
# ────────────────────────────────────────────────────────────────────

_STUB_SUGGESTIONS = [
    {
        "move_type": "trial_readout",
        "move_payload": {"target_drug": "semaglutide"},
        "rationale": "Player has Phase 3 trial reading out Q3.",
        "expected_impact_score": 0.85,
        "confidence_score": 0.7,
        "confidence": "high",
        "evidence_basis": ["semaglutide"],
        "stripped_citations": [],
        "evidence_validated": True,
    },
    {
        "move_type": "label_expansion",
        "move_payload": {"target_drug": "semaglutide", "expansion": "MASH"},
        "rationale": "Existing label allows expansion to MASH.",
        "expected_impact_score": 0.6,
        "confidence_score": 0.55,
        "confidence": "medium",
        "evidence_basis": ["semaglutide"],
        "stripped_citations": [],
        "evidence_validated": True,
    },
]


def test_suggest_moves_401_anonymous():
    db, _, _, _ = _make_db()
    client = _client(db)
    create = MagicMock()  # not used; we need to create a room first via auth
    tok_owner = _login(client, "viewer@demo.market-zero.io")
    rid = client.post("/war-rooms", headers=_hdr(tok_owner), json={
        "title": "x", "primary_entity_type": "company",
        "primary_entity_id": "x", "primary_entity_name": "X",
    }).json()["id"]
    # Anon attempt
    r = client.post(f"/war-rooms/{rid}/suggest-moves", json={"n": 3})
    assert r.status_code == 401


def test_suggest_moves_403_for_non_owner():
    db, _, _, _ = _make_db()
    client = _client(db)
    vt = _login(client, "viewer@demo.market-zero.io")
    rid = client.post("/war-rooms", headers=_hdr(vt), json={
        "title": "owned by viewer",
        "primary_entity_type": "company",
        "primary_entity_id": "x", "primary_entity_name": "X",
    }).json()["id"]
    ut = _login(client, "uploader@demo.market-zero.io")
    r = client.post(
        f"/war-rooms/{rid}/suggest-moves", headers=_hdr(ut), json={"n": 3},
    )
    assert r.status_code == 403


def test_suggest_moves_200_owner_returns_ranked_list():
    db, _, _, _ = _make_db()
    client = _client(db)
    tok = _login(client, "viewer@demo.market-zero.io")
    rid = client.post("/war-rooms", headers=_hdr(tok), json={
        "title": "ranked test",
        "primary_entity_type": "company",
        "primary_entity_id": "ent-novo", "primary_entity_name": "Novo Nordisk",
    }).json()["id"]

    with patch("api.routes.war_room._suggest_moves",
               return_value=list(_STUB_SUGGESTIONS)):
        r = client.post(
            f"/war-rooms/{rid}/suggest-moves", headers=_hdr(tok),
            json={"n": 3},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["war_room_id"] == rid
    assert "rule_version_id" in body
    assert body["count"] == 2
    assert len(body["suggestions"]) == 2
    # First by impact desc
    assert body["suggestions"][0]["move_type"] == "trial_readout"
    assert body["suggestions"][0]["expected_impact_score"] == 0.85


def test_suggest_moves_400_for_invalid_n():
    db, _, _, _ = _make_db()
    client = _client(db)
    tok = _login(client, "viewer@demo.market-zero.io")
    rid = client.post("/war-rooms", headers=_hdr(tok), json={
        "title": "x", "primary_entity_type": "company",
        "primary_entity_id": "x", "primary_entity_name": "X",
    }).json()["id"]
    r = client.post(
        f"/war-rooms/{rid}/suggest-moves", headers=_hdr(tok),
        json={"n": 0},
    )
    assert r.status_code == 400


# ────────────────────────────────────────────────────────────────────
# Phase B — PATCH /war-rooms/{id} (rename, archive, unarchive, re-open)
# ────────────────────────────────────────────────────────────────────

def test_patch_room_401_anonymous():
    db, _, _, _ = _make_db()
    client = _client(db)
    tok = _login(client, "viewer@demo.market-zero.io")
    rid = client.post("/war-rooms", headers=_hdr(tok), json={
        "title": "x", "primary_entity_type": "company",
        "primary_entity_id": "x", "primary_entity_name": "X",
    }).json()["id"]
    r = client.patch(f"/war-rooms/{rid}", json={"title": "renamed"})
    assert r.status_code == 401


def test_patch_room_403_for_non_owner():
    db, _, _, _ = _make_db()
    client = _client(db)
    vt = _login(client, "viewer@demo.market-zero.io")
    rid = client.post("/war-rooms", headers=_hdr(vt), json={
        "title": "viewer's", "primary_entity_type": "company",
        "primary_entity_id": "x", "primary_entity_name": "X",
    }).json()["id"]
    ut = _login(client, "uploader@demo.market-zero.io")
    r = client.patch(f"/war-rooms/{rid}", headers=_hdr(ut),
                     json={"title": "hijacked"})
    assert r.status_code == 403


def test_patch_room_renames_title():
    db, rooms_store, _, _ = _make_db()
    client = _client(db)
    tok = _login(client, "viewer@demo.market-zero.io")
    rid = client.post("/war-rooms", headers=_hdr(tok), json={
        "title": "old title", "primary_entity_type": "company",
        "primary_entity_id": "x", "primary_entity_name": "X",
    }).json()["id"]
    r = client.patch(f"/war-rooms/{rid}", headers=_hdr(tok),
                     json={"title": "new title"})
    assert r.status_code == 200, r.text
    assert r.json()["title"] == "new title"
    assert rooms_store[rid]["title"] == "new title"


def test_patch_room_archives_and_unarchives():
    db, rooms_store, _, _ = _make_db()
    client = _client(db)
    tok = _login(client, "viewer@demo.market-zero.io")
    rid = client.post("/war-rooms", headers=_hdr(tok), json={
        "title": "archivable", "primary_entity_type": "company",
        "primary_entity_id": "x", "primary_entity_name": "X",
    }).json()["id"]

    # Archive
    r = client.patch(f"/war-rooms/{rid}", headers=_hdr(tok),
                     json={"archived": True})
    assert r.status_code == 200
    assert r.json()["archived_at"] is not None
    assert rooms_store[rid]["archived_at"] is not None

    # Unarchive
    r = client.patch(f"/war-rooms/{rid}", headers=_hdr(tok),
                     json={"archived": False})
    assert r.status_code == 200
    assert r.json()["archived_at"] is None
    assert rooms_store[rid]["archived_at"] is None


def test_patch_room_changes_status():
    db, rooms_store, _, _ = _make_db()
    client = _client(db)
    tok = _login(client, "viewer@demo.market-zero.io")
    rid = client.post("/war-rooms", headers=_hdr(tok), json={
        "title": "status test", "primary_entity_type": "company",
        "primary_entity_id": "x", "primary_entity_name": "X",
    }).json()["id"]
    r = client.patch(f"/war-rooms/{rid}", headers=_hdr(tok),
                     json={"status": "closed"})
    assert r.status_code == 200
    assert r.json()["status"] == "closed"
    # Re-open
    r = client.patch(f"/war-rooms/{rid}", headers=_hdr(tok),
                     json={"status": "active"})
    assert r.status_code == 200
    assert r.json()["status"] == "active"


def test_patch_room_400_for_invalid_status():
    db, _, _, _ = _make_db()
    client = _client(db)
    tok = _login(client, "viewer@demo.market-zero.io")
    rid = client.post("/war-rooms", headers=_hdr(tok), json={
        "title": "x", "primary_entity_type": "company",
        "primary_entity_id": "x", "primary_entity_name": "X",
    }).json()["id"]
    r = client.patch(f"/war-rooms/{rid}", headers=_hdr(tok),
                     json={"status": "deleted"})
    assert r.status_code == 400


# ────────────────────────────────────────────────────────────────────
# Phase B — GET /war-rooms with filters
# ────────────────────────────────────────────────────────────────────

def test_list_rooms_filter_by_archived():
    db, _, _, _ = _make_db()
    client = _client(db)
    tok = _login(client, "viewer@demo.market-zero.io")
    rid_active = client.post("/war-rooms", headers=_hdr(tok), json={
        "title": "active room", "primary_entity_type": "company",
        "primary_entity_id": "x", "primary_entity_name": "X",
    }).json()["id"]
    rid_archived = client.post("/war-rooms", headers=_hdr(tok), json={
        "title": "to-archive", "primary_entity_type": "company",
        "primary_entity_id": "y", "primary_entity_name": "Y",
    }).json()["id"]
    client.patch(f"/war-rooms/{rid_archived}", headers=_hdr(tok),
                 json={"archived": True})

    # Default — no filter, includes both
    r = client.get("/war-rooms", headers=_hdr(tok))
    assert {x["id"] for x in r.json()["war_rooms"]} == {rid_active, rid_archived}

    # archived=true → only archived
    r = client.get("/war-rooms?archived=true", headers=_hdr(tok))
    ids = [x["id"] for x in r.json()["war_rooms"]]
    assert ids == [rid_archived]

    # archived=false → only non-archived
    r = client.get("/war-rooms?archived=false", headers=_hdr(tok))
    ids = [x["id"] for x in r.json()["war_rooms"]]
    assert ids == [rid_active]


def test_list_rooms_filter_by_title_search():
    db, _, _, _ = _make_db()
    client = _client(db)
    tok = _login(client, "viewer@demo.market-zero.io")
    client.post("/war-rooms", headers=_hdr(tok), json={
        "title": "tirzepatide MASH expansion",
        "primary_entity_type": "company",
        "primary_entity_id": "x", "primary_entity_name": "X",
    })
    client.post("/war-rooms", headers=_hdr(tok), json={
        "title": "semaglutide pricing pressure",
        "primary_entity_type": "company",
        "primary_entity_id": "y", "primary_entity_name": "Y",
    })
    r = client.get("/war-rooms?q=tirzepatide", headers=_hdr(tok))
    rooms = r.json()["war_rooms"]
    assert len(rooms) == 1
    assert "tirzepatide" in rooms[0]["title"].lower()


def test_list_rooms_filter_by_status_and_entity():
    db, _, _, _ = _make_db()
    client = _client(db)
    tok = _login(client, "viewer@demo.market-zero.io")
    rid_a = client.post("/war-rooms", headers=_hdr(tok), json={
        "title": "novo a", "primary_entity_type": "company",
        "primary_entity_id": "ent-novo", "primary_entity_name": "Novo",
    }).json()["id"]
    client.post("/war-rooms", headers=_hdr(tok), json={
        "title": "lilly a", "primary_entity_type": "company",
        "primary_entity_id": "ent-lilly", "primary_entity_name": "Lilly",
    })
    # Close one
    client.patch(f"/war-rooms/{rid_a}", headers=_hdr(tok),
                 json={"status": "closed"})

    # status=closed → only the closed novo room
    r = client.get("/war-rooms?status=closed", headers=_hdr(tok))
    assert [x["id"] for x in r.json()["war_rooms"]] == [rid_a]

    # entity_id=ent-lilly → only lilly room
    r = client.get("/war-rooms?entity_id=ent-lilly", headers=_hdr(tok))
    assert len(r.json()["war_rooms"]) == 1
    assert r.json()["war_rooms"][0]["primary_entity_id"] == "ent-lilly"


# ────────────────────────────────────────────────────────────────────
# Phase B — Comments CRUD
# ────────────────────────────────────────────────────────────────────

def test_create_comment_401_anonymous():
    db, _, _, _ = _make_db()
    client = _client(db)
    tok = _login(client, "viewer@demo.market-zero.io")
    rid = client.post("/war-rooms", headers=_hdr(tok), json={
        "title": "x", "primary_entity_type": "company",
        "primary_entity_id": "x", "primary_entity_name": "X",
    }).json()["id"]
    r = client.post(f"/war-rooms/{rid}/comments", json={"body": "hi"})
    assert r.status_code == 401


def test_create_comment_201_for_viewer():
    db, _, _, _ = _make_db()
    client = _client(db)
    owner_tok = _login(client, "viewer@demo.market-zero.io")
    rid = client.post("/war-rooms", headers=_hdr(owner_tok), json={
        "title": "commentable", "primary_entity_type": "company",
        "primary_entity_id": "x", "primary_entity_name": "X",
    }).json()["id"]
    # A different viewer (uploader) comments
    other_tok = _login(client, "uploader@demo.market-zero.io")
    r = client.post(f"/war-rooms/{rid}/comments", headers=_hdr(other_tok),
                    json={"body": "great room"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["body"] == "great room"
    assert body["author_user_id"] == "uuid-uploader"
    assert body["edited_at"] is None


def test_comment_body_length_validation():
    db, _, _, _ = _make_db()
    client = _client(db)
    tok = _login(client, "viewer@demo.market-zero.io")
    rid = client.post("/war-rooms", headers=_hdr(tok), json={
        "title": "x", "primary_entity_type": "company",
        "primary_entity_id": "x", "primary_entity_name": "X",
    }).json()["id"]
    # Empty body
    r = client.post(f"/war-rooms/{rid}/comments", headers=_hdr(tok),
                    json={"body": ""})
    assert r.status_code == 422
    # Over 4000 chars
    r = client.post(f"/war-rooms/{rid}/comments", headers=_hdr(tok),
                    json={"body": "a" * 4001})
    assert r.status_code == 422


def test_list_comments_anon_returns_chronological():
    db, _, _, _ = _make_db()
    client = _client(db)
    tok = _login(client, "viewer@demo.market-zero.io")
    rid = client.post("/war-rooms", headers=_hdr(tok), json={
        "title": "x", "primary_entity_type": "company",
        "primary_entity_id": "x", "primary_entity_name": "X",
    }).json()["id"]
    client.post(f"/war-rooms/{rid}/comments", headers=_hdr(tok),
                json={"body": "first"})
    client.post(f"/war-rooms/{rid}/comments", headers=_hdr(tok),
                json={"body": "second"})
    # Anonymous read
    r = client.get(f"/war-rooms/{rid}/comments")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 2
    assert [c["body"] for c in body["comments"]] == ["first", "second"]


def test_detail_includes_comments_array():
    db, _, _, _ = _make_db()
    client = _client(db)
    tok = _login(client, "viewer@demo.market-zero.io")
    rid = client.post("/war-rooms", headers=_hdr(tok), json={
        "title": "x", "primary_entity_type": "company",
        "primary_entity_id": "x", "primary_entity_name": "X",
    }).json()["id"]
    client.post(f"/war-rooms/{rid}/comments", headers=_hdr(tok),
                json={"body": "in detail"})
    r = client.get(f"/war-rooms/{rid}")
    assert r.status_code == 200
    assert "comments" in r.json()
    assert len(r.json()["comments"]) == 1


def test_patch_comment_by_author_sets_edited_at():
    db, _, _, _ = _make_db()
    client = _client(db)
    tok = _login(client, "viewer@demo.market-zero.io")
    rid = client.post("/war-rooms", headers=_hdr(tok), json={
        "title": "x", "primary_entity_type": "company",
        "primary_entity_id": "x", "primary_entity_name": "X",
    }).json()["id"]
    cid = client.post(
        f"/war-rooms/{rid}/comments", headers=_hdr(tok),
        json={"body": "original"},
    ).json()["id"]
    r = client.patch(
        f"/war-rooms/{rid}/comments/{cid}", headers=_hdr(tok),
        json={"body": "edited"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["body"] == "edited"
    assert r.json()["edited_at"] is not None


def test_patch_comment_403_for_non_author():
    db, _, _, _ = _make_db()
    client = _client(db)
    author_tok = _login(client, "viewer@demo.market-zero.io")
    rid = client.post("/war-rooms", headers=_hdr(author_tok), json={
        "title": "x", "primary_entity_type": "company",
        "primary_entity_id": "x", "primary_entity_name": "X",
    }).json()["id"]
    cid = client.post(
        f"/war-rooms/{rid}/comments", headers=_hdr(author_tok),
        json={"body": "mine"},
    ).json()["id"]
    other_tok = _login(client, "uploader@demo.market-zero.io")
    r = client.patch(
        f"/war-rooms/{rid}/comments/{cid}", headers=_hdr(other_tok),
        json={"body": "tampered"},
    )
    assert r.status_code == 403


def test_delete_comment_by_author():
    db, _, _, _ = _make_db()
    client = _client(db)
    tok = _login(client, "viewer@demo.market-zero.io")
    rid = client.post("/war-rooms", headers=_hdr(tok), json={
        "title": "x", "primary_entity_type": "company",
        "primary_entity_id": "x", "primary_entity_name": "X",
    }).json()["id"]
    cid = client.post(
        f"/war-rooms/{rid}/comments", headers=_hdr(tok),
        json={"body": "deletable"},
    ).json()["id"]
    r = client.delete(f"/war-rooms/{rid}/comments/{cid}", headers=_hdr(tok))
    assert r.status_code == 204
    # Confirm gone
    r = client.get(f"/war-rooms/{rid}/comments")
    assert r.json()["count"] == 0


def test_delete_comment_by_room_owner_when_not_author():
    db, _, _, _ = _make_db()
    client = _client(db)
    owner_tok = _login(client, "viewer@demo.market-zero.io")
    rid = client.post("/war-rooms", headers=_hdr(owner_tok), json={
        "title": "x", "primary_entity_type": "company",
        "primary_entity_id": "x", "primary_entity_name": "X",
    }).json()["id"]
    other_tok = _login(client, "uploader@demo.market-zero.io")
    cid = client.post(
        f"/war-rooms/{rid}/comments", headers=_hdr(other_tok),
        json={"body": "from uploader"},
    ).json()["id"]
    # Owner deletes someone else's comment in their room — allowed
    r = client.delete(f"/war-rooms/{rid}/comments/{cid}", headers=_hdr(owner_tok))
    assert r.status_code == 204


def test_delete_comment_403_for_stranger():
    db, _, _, _ = _make_db()
    client = _client(db)
    author_tok = _login(client, "viewer@demo.market-zero.io")
    rid = client.post("/war-rooms", headers=_hdr(author_tok), json={
        "title": "x", "primary_entity_type": "company",
        "primary_entity_id": "x", "primary_entity_name": "X",
    }).json()["id"]
    cid = client.post(
        f"/war-rooms/{rid}/comments", headers=_hdr(author_tok),
        json={"body": "mine"},
    ).json()["id"]
    other_tok = _login(client, "uploader@demo.market-zero.io")
    r = client.delete(f"/war-rooms/{rid}/comments/{cid}", headers=_hdr(other_tok))
    assert r.status_code == 403


# ────────────────────────────────────────────────────────────────────
# Phase B — _fetch_competitors fuzzy ILIKE coverage (audit gap)
# ────────────────────────────────────────────────────────────────────

def test_fetch_competitors_fuzzy_ilike_when_id_unknown():
    """When player_company_id is None, fall back to ILIKE on the first
    2 words of the player_company_name to exclude the player."""
    from api.routes.war_room import _fetch_competitors

    captured: dict = {}

    class _StubDB:
        def fetch_all(self, sql, params):
            captured["sql"] = sql
            captured["params"] = list(params)
            return []  # don't care about result, just verify the SQL/params

    _fetch_competitors(
        _StubDB(),
        exclude_company_id=None,
        exclude_company_name="Novo Nordisk Inc.",
    )
    # When id is None, the first 2-3 params relate to id (None, None) and the
    # next two relate to the ILIKE pattern on the first 2 words.
    sql_lower = captured["sql"].lower()
    assert "ilike" in sql_lower
    # Pattern preserves original casing (route doesn't lowercase the player name);
    # ILIKE is case-insensitive so this is correct behavior.
    assert "%Novo Nordisk%" in captured["params"]


def test_fetch_competitors_no_exclude_when_neither_provided():
    """If neither id nor name is given, no exclusion clause should fire."""
    from api.routes.war_room import _fetch_competitors

    captured: dict = {}

    class _StubDB:
        def fetch_all(self, sql, params):
            captured["sql"] = sql
            captured["params"] = list(params)
            return []

    _fetch_competitors(_StubDB(), exclude_company_id=None, exclude_company_name=None)
    # All Nones for the exclude params
    assert captured["params"][0] is None
    assert captured["params"][2] is None


# ────────────────────────────────────────────────────────────────────
# Original Phase A audit fix #2: partial INSERT failures still surfaced
# ────────────────────────────────────────────────────────────────────

def test_round_endpoint_surfaces_partial_failures():
    """If 1 of N reaction inserts fails, the response must surface it
    via persistence_errors + competitors_attempted/persisted counters,
    not silently drop the failed reaction."""
    from unittest.mock import MagicMock

    db, _, _, _ = _make_db()

    # Wrap db.execute so the war_room_reactions insert fails on the
    # second call; everything else passes through.
    real_execute = db.execute.side_effect
    insert_call_count = [0]

    def selective_failing_execute(sql, params=None):
        s = (sql or "").lower()
        if "insert into war_room_reactions" in s:
            insert_call_count[0] += 1
            if insert_call_count[0] == 2:  # second reaction fails
                raise RuntimeError("simulated DB failure on second reaction")
        return real_execute(sql, params)

    db.execute.side_effect = selective_failing_execute

    client = _client(db)
    tok = _login(client, "viewer@demo.market-zero.io")
    create = client.post("/war-rooms", headers=_hdr(tok), json={
        "title": "partial failure test",
        "primary_entity_type": "company", "primary_entity_id": "ent-x",
        "primary_entity_name": "X",
    })
    rid = create.json()["id"]

    with patch("api.routes.war_room._generate_reactions",
               side_effect=_stub_reactions):
        r = client.post(
            f"/war-rooms/{rid}/rounds", headers=_hdr(tok),
            json={"move_type": "price_cut", "move_payload": {}},
        )

    assert r.status_code == 200, r.text
    body = r.json()
    # 2 reactions attempted (stub returns 2), 1 persisted, 1 in errors
    assert body.get("competitors_attempted") == 2
    assert body.get("competitors_persisted") == 1
    assert "persistence_errors" in body
    assert len(body["persistence_errors"]) == 1
    err = body["persistence_errors"][0]
    assert "competitor_company_name" in err
    assert "error" in err
