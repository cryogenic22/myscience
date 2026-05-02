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
    next_id = [1]

    def _gen_id(prefix: str) -> str:
        nid = f"{prefix}-{next_id[0]}"
        next_id[0] += 1
        return nid

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
        if "from war_rooms" in s and "where id" in s and params:
            return dict(rooms.get(str(params[0]))) if rooms.get(str(params[0])) else None
        # Create read-back: WHERE owner_user_id = ... AND title = ...
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
        # Round read-back: WHERE war_room_id = ... AND round_number = ...
        if "from war_room_rounds" in s and "round_number" in s and "war_room_id" in s and params:
            wr_id, rn = str(params[0]), params[1]
            for r in rounds:
                if r["war_room_id"] == wr_id and r["round_number"] == rn:
                    return dict(r)
            return None
        return None

    def fake_fetch_all(sql, params=None):
        s = (sql or "").lower()
        if "from war_rooms" in s and "owner_user_id" in s and params:
            return [dict(r) for r in rooms.values() if r.get("owner_user_id") == params[0]]
        if "from war_room_rounds" in s and params:
            wr_id = str(params[0])
            return sorted(
                [dict(r) for r in rounds if r["war_room_id"] == wr_id],
                key=lambda r: r["round_number"],
            )
        if "from war_room_reactions" in s and params:
            round_id = str(params[0])
            return [dict(r) for r in reactions if r["round_id"] == round_id]
        return []

    def fake_execute(sql, params=None):
        s = (sql or "").lower()
        if "insert into war_rooms" in s and params:
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
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            }
            # Attach generated id for read-back
            fake_execute.last_room_id = rid
            return None
        if "insert into war_room_rounds" in s and params:
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
            fake_execute.last_round_id = rid
            return None
        if "insert into war_room_reactions" in s and params:
            rid = _gen_id("rxn")
            # Accept both legacy (11 params) and post-046 (14 params) shapes
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
            return None
        if "update war_rooms" in s and "set status" in s and params:
            # Route hardcodes status='closed'; param is just the room id
            room_id = str(params[-1])
            if room_id in rooms:
                rooms[room_id]["status"] = "closed"
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
