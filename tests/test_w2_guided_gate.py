"""W2 — integration tests for the Guided-mode gate at the HTTP boundary.

Verifies that:
- In Guided mode, round submission + move suggestion work as before
  (no behavioural change for the default path).
- Switching to autonomous or game_theoretic mode flips both endpoints
  to 409 Conflict with an operator-actionable message.
- Switching back to Guided re-enables submission (reversibility).
- The 409 only fires AFTER 401/403/404 — owner-check still takes
  precedence so we don't leak room existence to non-owners.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


# ──────────────────────────────────────────────────────────────────
# Fake DB — extends the W1 mode-route fake with round insertion,
# competitor fetch (returns empty for determinism), and reaction
# persistence. Reaction generator is stubbed so tests don't call LLM.
# ──────────────────────────────────────────────────────────────────

def _make_db(rooms=None):
    from services.auth import hash_password

    users = {
        "owner@demo.market-zero.io": {
            "id": "uuid-owner", "email": "owner@demo.market-zero.io",
            "password_hash": hash_password("demo"),
            "role": "viewer", "is_active": True,
        },
        "intruder@demo.market-zero.io": {
            "id": "uuid-intruder", "email": "intruder@demo.market-zero.io",
            "password_hash": hash_password("demo"),
            "role": "viewer", "is_active": True,
        },
    }
    rooms = rooms or {}
    rounds: list[dict] = []
    reactions: list[dict] = []
    write_log: list[tuple[str, list]] = []
    next_id = [1]

    def _gen(prefix):
        nid = f"{prefix}-{next_id[0]}"
        next_id[0] += 1
        return nid

    def fetch_one(sql, params=None):
        s = (sql or "").lower()
        if "from users" in s and params:
            if "where lower(email)" in s or "where email" in s:
                return users.get(str(params[0]).lower())
            if "where id::text" in s or "where id =" in s:
                for u in users.values():
                    if u["id"] == params[0]:
                        return u
                return None
        # count probe used by load_scenario_state
        if "count" in s and "war_room_rounds" in s and "max" not in s:
            wr = str(params[0]) if params else None
            return {"count": sum(1 for r in rounds if r["war_room_id"] == wr)}
        # narrow mode/mode_changed_at select (W1 chokepoint)
        if (
            "from war_rooms" in s and "id::text" in s
            and "mode" in s and "title" not in s and params
        ):
            room = rooms.get(str(params[0]))
            if not room:
                return None
            return {
                "mode": room.get("mode", "guided"),
                "mode_changed_at": room.get("mode_changed_at"),
            }
        # full-room select (the route's owner check)
        if "from war_rooms" in s and "id::text" in s and params:
            room = rooms.get(str(params[0]))
            return dict(room) if room else None
        # MAX(round_number) probe
        if "from war_room_rounds" in s and "max" in s and params:
            wr = str(params[0])
            mx = max(
                (r["round_number"] for r in rounds if r["war_room_id"] == wr),
                default=0,
            )
            return {"max_round": mx}
        # INSERT INTO war_room_rounds ... RETURNING id
        if "insert into war_room_rounds" in s and "returning" in s and params:
            rid = _gen("rnd")
            rounds.append({
                "id": rid,
                "war_room_id": str(params[0]),
                "round_number": params[1],
                "player_company_id": params[2],
                "player_company_name": params[3],
                "move_type": params[4],
                "move_payload": params[5],
                "notes": params[6] if len(params) > 6 else None,
                "created_at": datetime.now(timezone.utc),
            })
            return {"id": rid}
        # Round read-back by id::text
        if "from war_room_rounds" in s and "id::text" in s and params:
            for r in rounds:
                if r["id"] == str(params[0]):
                    return dict(r)
            return None
        return None

    def fetch_all(sql, params=None):
        s = (sql or "").lower()
        if "from war_room_rounds" in s and params:
            wr = str(params[0])
            # History query restricts by round_number < x
            rows = [dict(r) for r in rounds if r["war_room_id"] == wr]
            return sorted(rows, key=lambda r: r["round_number"])
        # competitor fetch
        if "from companies" in s:
            return []
        return []

    def execute(sql, params=None):
        s = (sql or "").lower()
        write_log.append((s, list(params or [])))
        if "update war_rooms" in s and "mode =" in s and params:
            room_id = str(params[-1])
            if room_id in rooms:
                rooms[room_id]["mode"] = params[0]
                rooms[room_id]["mode_changed_at"] = datetime.now(timezone.utc)
        if "insert into war_room_reactions" in s:
            reactions.append({"sql": s})
        return None

    from unittest.mock import MagicMock
    db = MagicMock()
    db.fetch_one.side_effect = fetch_one
    db.fetch_all.side_effect = fetch_all
    db.execute.side_effect = execute
    return db, rooms, rounds, reactions, write_log


def _seed_room(rooms, *, room_id="wr-1", owner="uuid-owner", mode="guided"):
    rooms[room_id] = {
        "id": room_id, "title": "Pfizer guidance scenario",
        "owner_user_id": owner, "scenario_question": "What if?",
        "primary_entity_type": "company", "primary_entity_id": "ent-pfizer",
        "primary_entity_name": "Pfizer Inc.",
        "source_signal_id": None, "game_phase": "launch",
        "status": "active", "mode": mode, "mode_changed_at": None,
        "archived_at": None,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    return rooms[room_id]


def _client(db):
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


# Stub reaction generator — deterministic, no LLM call.
def _stub_reactions(*args, **kwargs):
    return [{
        "competitor_company_id": "ent-lilly",
        "competitor_company_name": "Eli Lilly",
        "reaction_type": "counter_launch",
        "headline": "stub",
        "specific_action": "stub action",
        "asset_leveraged": {"id": "drug-x", "name": "x", "rationale": "stub"},
        "rationale": "stub", "evidence_basis": [],
        "stripped_citations": [], "evidence_validated": True,
        "scores": {}, "confidence_score": 0.5, "confidence": "medium",
    }]


def _stub_suggestions(*args, **kwargs):
    return [{
        "move_type": "launch", "headline": "stub suggestion",
        "rationale": "stub", "expected_impact_score": 0.7,
        "supporting_evidence": [], "confidence": "medium",
    }]


VALID_ROUND_BODY = {
    "move_type": "price_cut",  # one of services.war_game_engine.MOVE_TYPES
    "move_payload": {"target": "Pfizer"},
    "player_company_id": "uuid-owner",
    "player_company_name": "Novo Nordisk",
}


# ──────────────────────────────────────────────────────────────────
# Acceptance — the W2 SPEC contract in a single test
# ──────────────────────────────────────────────────────────────────

@patch("api.routes.war_room._generate_reactions", side_effect=_stub_reactions)
@patch("api.routes.war_room._suggest_moves", side_effect=_stub_suggestions)
def test_acceptance_w2_guided_gate_contract(mock_sug, mock_rxn):
    db, rooms, rounds, _, _ = _make_db()
    _seed_room(rooms, mode="guided")
    client = _client(db)
    tok = _login(client, "owner@demo.market-zero.io")
    hdr = _hdr(tok)

    # 1. In Guided mode (default), round submission works.
    r = client.post("/war-rooms/wr-1/rounds", headers=hdr, json=VALID_ROUND_BODY)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "reactions" in body
    assert len(rounds) == 1, "Guided round must persist"

    # 2. Switch to autonomous; round submission now 409.
    r = client.patch("/war-rooms/wr-1/mode", headers=hdr,
                     json={"mode": "autonomous"})
    assert r.status_code == 200

    r = client.post("/war-rooms/wr-1/rounds", headers=hdr, json=VALID_ROUND_BODY)
    assert r.status_code == 409, r.text
    msg = r.json().get("detail", "")
    assert "autonomous" in msg, "message must say what mode the room IS in"
    assert "guided" in msg, "message must say what mode to switch TO"
    # The blocked attempt must NOT have persisted a round.
    assert len(rounds) == 1, "blocked round must not be persisted"

    # 3. suggest_moves is gated the same way.
    r = client.post("/war-rooms/wr-1/suggest-moves", headers=hdr,
                    json={"n": 3})
    assert r.status_code == 409
    assert "autonomous" in r.json().get("detail", "")

    # 4. Switch back to guided; both endpoints work again (reversibility).
    client.patch("/war-rooms/wr-1/mode", headers=hdr, json={"mode": "guided"})

    r = client.post("/war-rooms/wr-1/rounds", headers=hdr, json=VALID_ROUND_BODY)
    assert r.status_code == 200, r.text
    assert len(rounds) == 2

    r = client.post("/war-rooms/wr-1/suggest-moves", headers=hdr,
                    json={"n": 3})
    assert r.status_code == 200


# ──────────────────────────────────────────────────────────────────
# Bilateral coverage — both non-Guided modes
# ──────────────────────────────────────────────────────────────────

@patch("api.routes.war_room._generate_reactions", side_effect=_stub_reactions)
def test_submit_round_409_in_game_theoretic_mode(mock_rxn):
    db, rooms, rounds, _, _ = _make_db()
    _seed_room(rooms, mode="game_theoretic")
    client = _client(db)
    tok = _login(client, "owner@demo.market-zero.io")
    r = client.post("/war-rooms/wr-1/rounds",
                    headers=_hdr(tok), json=VALID_ROUND_BODY)
    assert r.status_code == 409
    msg = r.json().get("detail", "")
    assert "game_theoretic" in msg
    assert "guided" in msg
    assert len(rounds) == 0


@patch("api.routes.war_room._suggest_moves", side_effect=_stub_suggestions)
def test_suggest_moves_409_in_game_theoretic_mode(mock_sug):
    db, rooms, _, _, _ = _make_db()
    _seed_room(rooms, mode="game_theoretic")
    client = _client(db)
    tok = _login(client, "owner@demo.market-zero.io")
    r = client.post("/war-rooms/wr-1/suggest-moves",
                    headers=_hdr(tok), json={"n": 3})
    assert r.status_code == 409


# ──────────────────────────────────────────────────────────────────
# Status-code priority — 401/403/404 still take precedence over 409
# (so we don't leak room existence to anonymous or non-owners)
# ──────────────────────────────────────────────────────────────────

def test_submit_round_401_anonymous_even_in_non_guided_mode():
    db, rooms, _, _, _ = _make_db()
    _seed_room(rooms, mode="autonomous")
    r = _client(db).post("/war-rooms/wr-1/rounds", json=VALID_ROUND_BODY)
    assert r.status_code == 401  # never 409


def test_submit_round_403_non_owner_even_in_non_guided_mode():
    db, rooms, _, _, _ = _make_db()
    _seed_room(rooms, owner="uuid-owner", mode="autonomous")
    client = _client(db)
    tok = _login(client, "intruder@demo.market-zero.io")
    r = client.post("/war-rooms/wr-1/rounds",
                    headers=_hdr(tok), json=VALID_ROUND_BODY)
    assert r.status_code == 403  # never 409 — gate runs AFTER owner check


def test_submit_round_404_missing_room_even_with_valid_owner():
    db, rooms, _, _, _ = _make_db()
    client = _client(db)
    tok = _login(client, "owner@demo.market-zero.io")
    r = client.post("/war-rooms/missing/rounds",
                    headers=_hdr(tok), json=VALID_ROUND_BODY)
    assert r.status_code == 404  # never 409


# ──────────────────────────────────────────────────────────────────
# Regression — happy path response shape is unchanged
# ──────────────────────────────────────────────────────────────────

@patch("api.routes.war_room._generate_reactions", side_effect=_stub_reactions)
def test_guided_round_response_shape_unchanged(mock_rxn):
    """The W2 gate must not silently mutate the existing response payload."""
    db, rooms, _, _, _ = _make_db()
    _seed_room(rooms, mode="guided")
    client = _client(db)
    tok = _login(client, "owner@demo.market-zero.io")
    r = client.post("/war-rooms/wr-1/rounds",
                    headers=_hdr(tok), json=VALID_ROUND_BODY)
    assert r.status_code == 200, r.text
    body = r.json()
    # Pre-W2 keys must still be present.
    for key in ("id", "war_room_id", "round_number", "move_type",
                "reactions", "competitors_attempted", "competitors_persisted"):
        assert key in body, f"missing key {key!r} — response shape regressed"
