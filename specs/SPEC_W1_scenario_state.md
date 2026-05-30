# SPEC W1 — Scenario state + mode toggle

*Bucket 4, Loop 1. Backend wiring for the F11 WarRoomPage.*

## Problem

F11 shipped a 3-mode war-room shell (Guided / Autonomous / Game-theoretic) on
the frontend (PR #108). The shell is headless and takes `mode` + `onModeChange`
as props. There is currently **no backend representation of "what mode this
war room is in"**. Two adjacent surfaces exist but neither owns the concept:

1. `services/scenario_engine.py` — counterfactual graph mutator
   ("landscape without entity X"). Different concept; the name is taken.
2. `api/routes/war_room.py` — owns `war_rooms` CRUD + round submission, but
   has no notion of mode. Submitting a round just generates competitor
   reactions; there is no "this room is in autonomous mode" awareness.
3. `api/routes/war_games.py` — a separate orchestrator that runs N rounds in
   one shot. Conceptually closer to autonomous mode but lives in its own
   table and contract.

So today, switching modes on the frontend is a no-op the backend cannot honor.
W2/W3/W4 cannot land cleanly because they have nowhere to plug in.

## Decision

Introduce `ScenarioState` as the single backend object the F11 page binds to.
It owns three things and **only** three things at W1 scope:

1. The room's current `mode` (the F11 toggle, persisted).
2. A read-only derived snapshot (round count, mode last changed at).
3. The mode-transition chokepoint — one function, validated, idempotent.

W2/W3/W4 will hang their per-mode engines off this object. W1 ships ONLY the
state + transition. It does not change round semantics, does not change reaction
generation, does not touch `war_games`/`scenarios` namespaces.

### Naming

Module: `services/scenario_state.py`. Not `scenario.py` (too generic; collides
with the counterfactual `scenario_engine` mental model). Not
`war_room_scenario.py` (verbose, and Z7 will eventually graduate this to a
first-class Scenario entity — `scenario_state` reads well in both worlds).

### Enum values match F11 verbatim

The F11 frontend declares:

```ts
export type WarRoomMode = 'guided' | 'autonomous' | 'game_theoretic';
```

Backend `ScenarioMode` MUST emit these three string values exactly. A
divergence test pins the contract.

## Acceptance test

A single runnable test in `tests/test_scenario_state.py` reproduces the
contract:

```python
def test_acceptance_w1_full_contract(mock_db):
    # 1. Default mode for a new war room is guided.
    state = load_scenario_state(mock_db, "room-1")
    assert state.mode is ScenarioMode.GUIDED

    # 2. Mode transition persists and round count is preserved.
    new = transition_mode(mock_db, "room-1", ScenarioMode.AUTONOMOUS)
    assert new.mode is ScenarioMode.AUTONOMOUS
    assert new.war_room_id == "room-1"

    # 3. Idempotent — same mode returns unchanged state, no DB write.
    same = transition_mode(mock_db, "room-1", ScenarioMode.AUTONOMOUS)
    assert same.mode is ScenarioMode.AUTONOMOUS
    assert mock_db.write_count == 1  # only the first transition wrote

    # 4. Invalid mode (string from untrusted input) is rejected at the door.
    with pytest.raises(InvalidScenarioMode):
        transition_mode(mock_db, "room-1", "nope")

    # 5. Nonexistent room raises typed error (not a swallow-leak).
    with pytest.raises(ScenarioNotFound):
        load_scenario_state(mock_db, "missing-room")
```

A second test pins the F11 contract:

```python
def test_scenario_mode_values_match_f11_frontend_contract():
    assert {m.value for m in ScenarioMode} == {"guided", "autonomous", "game_theoretic"}
```

## Out of scope (deferred to W2–W5)

- Real Guided agent engine (W2)
- Autonomous loop runner (W3)
- Game-theoretic backend (W4 — `payoff_matrix` endpoint already exists; W4 wires it through Scenario state)
- Flywheel chips (W5)
- Unifying `war_rooms` and `war_games` tables (Z7)
- Per-mode round semantics
- Frontend container that calls the new PATCH endpoint

## Schema

Migration `schema/migrations/071_scenario_mode.sql`:

```sql
ALTER TABLE war_rooms
  ADD COLUMN mode TEXT NOT NULL DEFAULT 'guided'
    CHECK (mode IN ('guided', 'autonomous', 'game_theoretic'));

ALTER TABLE war_rooms
  ADD COLUMN mode_changed_at TIMESTAMPTZ;

CREATE INDEX idx_war_rooms_mode ON war_rooms (mode) WHERE mode != 'guided';
```

Partial index because GUIDED is the default — only the explicit non-default
modes are interesting for analytics.

## Module surface

```python
# services/scenario_state.py

class ScenarioMode(str, Enum):
    GUIDED = "guided"
    AUTONOMOUS = "autonomous"
    GAME_THEORETIC = "game_theoretic"

class InvalidScenarioMode(ValueError):
    """Raised when a string cannot be coerced to ScenarioMode."""

class ScenarioNotFound(LookupError):
    """Raised when a war_room_id has no row."""

@dataclass(frozen=True)
class ScenarioState:
    war_room_id: str
    mode: ScenarioMode
    round_count: int
    mode_changed_at: Optional[datetime]

def load_scenario_state(db, war_room_id: str) -> ScenarioState: ...
def transition_mode(db, war_room_id: str, target: ScenarioMode | str) -> ScenarioState: ...
def coerce_mode(value: str | ScenarioMode) -> ScenarioMode: ...
```

`coerce_mode` is the single string→enum chokepoint — exposed publicly so the
HTTP route uses the same gate the service layer does.

## HTTP surface

```python
# api/routes/war_room.py — add ONE endpoint, no behavioural changes elsewhere.

@router.patch("/{room_id}/mode")
def patch_room_mode(
    room_id: str,
    body: PatchModeBody,   # { mode: str }
    user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
) -> dict:
    """Owner-only. Returns ScenarioState dict."""
```

Response shape:

```json
{
  "war_room_id": "...",
  "mode": "autonomous",
  "round_count": 0,
  "mode_changed_at": "2026-05-30T19:42:00Z"
}
```

`get_room` is **extended** to return `mode` and `mode_changed_at` in its
response payload so the F11 page can read initial state. No other shape changes.

## Red-team checklist (run before PR)

1. **Race**: two PATCHes flip mode at once. The CHECK constraint stops invalid
   values; last-write-wins on valid ones is acceptable for W1 — there is no
   in-flight mode-specific state to corrupt yet. Documented in the module
   docstring.
2. **Silent-empty leak**: `load_scenario_state` on a missing room must raise
   `ScenarioNotFound`, not return a default state. Tested.
3. **String coercion**: HTTP bodies arrive as strings. The single chokepoint
   `coerce_mode` raises typed `InvalidScenarioMode`; route maps to 400.
   Tested at both unit and route layer.
4. **Default not silently shipped**: existing rooms get `mode='guided'` from
   the column DEFAULT — verified in migration test.
5. **No duplication**: this module does NOT call `war_game_engine`,
   `war_game_adversary`, `game_theory`, or `scenario_engine`. It only reads
   from / writes to `war_rooms`. A grep test enforces no cross-imports.
6. **F11 contract drift**: the enum-values test pins exactly the three
   strings the frontend ships. Any future rename forces a coordinated change.
7. **Anti-slop**: no new dataclass duplicates `ScenarioResult` from
   `scenario_engine.py`. They are different domains — confirmed by grep.

## File plan

| File | Why |
|---|---|
| `specs/SPEC_W1_scenario_state.md` | This SPEC |
| `schema/migrations/071_scenario_mode.sql` | Adds `mode` + `mode_changed_at` to `war_rooms` |
| `services/scenario_state.py` | New module — ScenarioState + transitions |
| `tests/test_scenario_state.py` | Unit tests including the acceptance test |
| `api/routes/war_room.py` | `PATCH /war-rooms/{id}/mode` endpoint + extend `get_room` payload |
| `tests/test_war_room_mode_route.py` | Route tests |
| `docs/execution-log.md` | Append Loop 19 entry |

## Out-of-band (will not happen this loop)

- F11 page wired to the new endpoint (a frontend container PR, separate)
- Migration of `war_games` → unified scenario state (Z7's job)
- Per-mode round behavior change (W2/W3/W4)
