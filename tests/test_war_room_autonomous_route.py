"""W3 / PB-H13 — HTTP tests for POST /war-rooms/{id}/run-autonomous.

Reuses the W2 fake-DB harness. Proves the route is registered (not shadowed),
owner-gated, validates moves, and returns a transcript. The reaction
generator is stubbed so no LLM/DB grounding is exercised here — the grounding
itself is covered by the Guided path; this test owns the autonomous wiring.
"""
from __future__ import annotations

from unittest.mock import patch

from tests.test_w2_guided_gate import (
    _client, _hdr, _login, _make_db, _seed_room, _stub_reactions,
)


@patch("api.routes.war_room._generate_reactions", side_effect=_stub_reactions)
def test_run_autonomous_happy_path(mock_rxn):
    db, rooms, _, _, _ = _make_db()
    _seed_room(rooms, mode="autonomous")
    client = _client(db)
    tok = _login(client, "owner@demo.market-zero.io")
    r = client.post("/war-rooms/wr-1/run-autonomous", headers=_hdr(tok),
                    json={"rounds": 3, "our_moves": ["price_cut", "trial_readout"]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mode"] == "autonomous"
    assert body["war_room_id"] == "wr-1"
    assert body["summary"]["rounds_played"] == 3
    assert len(body["rounds"]) == 3
    assert len(body["narration"]) == 3
    # Each round carries the stubbed reaction.
    assert all(len(rd["reactions"]) == 1 for rd in body["rounds"])


@patch("api.routes.war_room._generate_reactions", side_effect=_stub_reactions)
def test_run_autonomous_defaults_moves(mock_rxn):
    db, rooms, _, _, _ = _make_db()
    _seed_room(rooms, mode="autonomous")
    client = _client(db)
    tok = _login(client, "owner@demo.market-zero.io")
    r = client.post("/war-rooms/wr-1/run-autonomous", headers=_hdr(tok), json={})
    assert r.status_code == 200, r.text
    assert r.json()["summary"]["rounds_played"] == 3  # default rounds


def test_run_autonomous_401_anonymous():
    db, rooms, _, _, _ = _make_db()
    _seed_room(rooms, mode="autonomous")
    r = _client(db).post("/war-rooms/wr-1/run-autonomous", json={"rounds": 2})
    assert r.status_code == 401  # route exists (not 404) + auth required


def test_run_autonomous_403_non_owner():
    db, rooms, _, _, _ = _make_db()
    _seed_room(rooms, owner="uuid-owner", mode="autonomous")
    client = _client(db)
    tok = _login(client, "intruder@demo.market-zero.io")
    r = client.post("/war-rooms/wr-1/run-autonomous", headers=_hdr(tok), json={"rounds": 2})
    assert r.status_code == 403


def test_run_autonomous_404_missing_room():
    db, rooms, _, _, _ = _make_db()
    client = _client(db)
    tok = _login(client, "owner@demo.market-zero.io")
    r = client.post("/war-rooms/missing/run-autonomous", headers=_hdr(tok), json={"rounds": 2})
    assert r.status_code == 404


@patch("api.routes.war_room._generate_reactions", side_effect=_stub_reactions)
def test_run_autonomous_400_invalid_move(mock_rxn):
    db, rooms, _, _, _ = _make_db()
    _seed_room(rooms, mode="autonomous")
    client = _client(db)
    tok = _login(client, "owner@demo.market-zero.io")
    r = client.post("/war-rooms/wr-1/run-autonomous", headers=_hdr(tok),
                    json={"our_moves": ["not_a_real_move"]})
    assert r.status_code == 400
    assert "invalid move_type" in r.json().get("detail", "")
