# SPEC W2 — Guided mode gate on the war room

*Bucket 4, Loop 2. Stacked on W1 (#110).*

## Problem

W1 added `ScenarioMode` to the war room (`guided | autonomous | game_theoretic`).
The toggle exists, the state is persisted, but it is **advisory only**: the
existing `POST /war-rooms/{id}/rounds` endpoint generates competitor
reactions regardless of mode. So today, the F11 frontend can switch a room
into "autonomous" mode and the operator can still submit Guided-style
human moves and get reactions — the mode is a label without enforcement.

This breaks the F11 promise: the three modes are first-class, not skins.
They have to be structurally distinct.

## Decision

Make the mode an enforced invariant on the round-submission surface:

1. `submit_round` and `suggest_moves_endpoint` are **Guided-mode-only**.
2. Calling either when the room is in `autonomous` or `game_theoretic` mode
   returns **409 Conflict** with a message telling the operator which mode
   they're in and what to switch to.
3. The gate lives in a single small module (`services/guided_mode.py`) with
   one typed exception (`GuidedModeBlocked`) so W3's autonomous-mode
   endpoint and W4's game-theoretic endpoint can use the symmetric gate.

The contract that "Guided mode means the war_game_engine generates
counter-projections to human moves" is already shipped — `submit_round`
already calls `war_game_engine.generate_reactions`. W2 does NOT change
this behaviour, it makes it **only-in-Guided**.

## Acceptance test

A single integration test in `tests/test_w2_guided_gate.py` reproduces
the contract:

```python
def test_acceptance_w2_guided_gate_contract(client_with_db):
    client, _ = client_with_db
    tok = _login(client, "owner@demo.market-zero.io")
    room_id = "wr-1"  # seeded with mode='guided'

    # 1. In Guided mode (default), round submission works.
    r = client.post(f"/war-rooms/{room_id}/rounds",
                    headers=_hdr(tok), json={"move_type": "launch", ...})
    assert r.status_code == 200
    assert "reactions" in r.json()

    # 2. Switch to autonomous; round submission now 409.
    r = client.patch(f"/war-rooms/{room_id}/mode",
                     headers=_hdr(tok), json={"mode": "autonomous"})
    assert r.status_code == 200

    r = client.post(f"/war-rooms/{room_id}/rounds",
                    headers=_hdr(tok), json={"move_type": "launch", ...})
    assert r.status_code == 409
    msg = r.json()["detail"]
    assert "autonomous" in msg          # tells operator what mode they're in
    assert "guided" in msg              # tells operator what they need to switch to

    # 3. suggest_moves is gated the same way.
    r = client.post(f"/war-rooms/{room_id}/suggest-moves",
                    headers=_hdr(tok), json={"n": 3})
    assert r.status_code == 409

    # 4. Switch back to guided; both endpoints work again.
    client.patch(f"/war-rooms/{room_id}/mode",
                 headers=_hdr(tok), json={"mode": "guided"})

    r = client.post(f"/war-rooms/{room_id}/rounds",
                    headers=_hdr(tok), json={"move_type": "launch", ...})
    assert r.status_code == 200
```

## Out of scope (deferred)

- Autonomous mode round-submission semantics (W3 — needs the agent loop runner)
- Game-theoretic mode payoff-matrix wiring through scenario state (W4)
- Frontend container that handles the 409 gracefully (frontend wiring PR)
- A `GET /war-rooms/{id}/guided` endpoint that returns the full F11 Guided
  contract shape in one call (frontend can compose from existing endpoints
  for now; revisit if shape proves unstable)

## Module surface

```python
# services/guided_mode.py

class GuidedModeBlocked(Exception):
    """Raised when a Guided-only operation is attempted on a non-Guided room.

    Carries `current_mode` so HTTP routes can include it in the 409 message.
    """
    def __init__(self, current_mode: ScenarioMode):
        self.current_mode = current_mode
        super().__init__(
            f"this operation is Guided-mode-only; room is currently in "
            f"{current_mode.value!r} mode — switch to guided to proceed"
        )


def assert_guided(mode: Union[str, ScenarioMode]) -> None:
    """Raise GuidedModeBlocked if mode is not GUIDED.

    Accepts either a string or enum. Single chokepoint so the gate lives
    in one place; submit_round and suggest_moves call this with the room's
    current mode loaded from `ScenarioState`.
    """
```

The chokepoint is intentionally small — one exception + one function. W3
adds `assert_autonomous` next to it; W4 adds `assert_game_theoretic`.

## HTTP changes

```python
# api/routes/war_room.py — minimal, additive

# submit_round (existing): after the owner check, before round insertion:
try:
    assert_guided(load_scenario_state(db, room_id).mode)
except GuidedModeBlocked as e:
    raise HTTPException(409, str(e))

# suggest_moves_endpoint (existing): same gate, same insertion point.
```

The owner check stays first so 401/403 still take precedence over 409.
The 409 only fires for an authenticated, authorised operator who is
trying to submit a Guided move in a non-Guided room.

## Red-team checklist

1. **Status-code priority**: 401 > 403 > 404 > 409. Tested explicitly so the
   gate doesn't accidentally leak room existence to non-owners.
2. **Bilateral gating**: both `autonomous` and `game_theoretic` → 409. Both
   directions covered.
3. **Reverse works**: switching back to `guided` re-enables submission.
   Tested.
4. **Error message is operator-actionable**: contains both current mode
   AND target mode ("guided"). Tested.
5. **Existing happy-path unchanged**: regression test confirms a
   default-mode room still accepts rounds with the same response shape.
6. **No new dependencies**: `guided_mode.py` imports only from
   `scenario_state`. No `war_game_engine`, no `war_game_adversary` — the
   gate is purely a state-check, not an engine.
7. **Anti-slop**: `assert_guided` is the single string→behaviour gate. Not
   `check_mode_is_guided`, not `validate_mode_for_round`. One name, one
   place.

## File plan

| File | Why |
|---|---|
| `specs/SPEC_W2_guided_mode_gate.md` | This SPEC |
| `services/guided_mode.py` | NEW — gate module |
| `tests/test_guided_mode.py` | Unit tests for the gate |
| `api/routes/war_room.py` | Wire the gate into submit_round + suggest_moves |
| `tests/test_w2_guided_gate.py` | Integration test (acceptance) + bilateral coverage |
