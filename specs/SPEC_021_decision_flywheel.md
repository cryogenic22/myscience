# SPEC-021: Decision Flywheel — CI as a War-Game Cockpit

*Date: 2 May 2026*
*Status: Phase A in progress*

---

## Vision

Reframe CI from a "feed reader" into a **decision flywheel** per the ZS
Agentic AI Decision Systems thesis: every signal is the entry point to a
**sense → model → decide → act → learn** loop.

Today's `/ci` surface is the **sense** layer. SPEC-015 will deepen sensing
(real signals via clustering). SPEC-021 builds the **model + decide + learn**
layers on top of what we already have, turning every signal into an
actionable hypothesis.

The unit of value is no longer "an analyst saw a signal." It is **"a
decision was made, simulated, committed, and post-mortemed."**

## The flywheel applied

| Stage | Today | SPEC-021 adds |
|---|---|---|
| **Sense** | /ci Digest + Signals | (no change) |
| **Model** | scenario_engine (6 endpoints, no UI) | War Room: pick a competitive move, system models grounded reactions across competitors, scores on 5 dimensions |
| **Decide** | nothing | Side-by-side option comparison, ranked by composite score, pick & commit |
| **Act** | nothing | Decision ledger entry with linked signals, simulated outcomes, owner, target date |
| **Learn** | feedback_loops service exists, not wired | 60-day post-mortem flow → adjust signal scoring rule weights based on which signals drove correct decisions |

## Phases

### Phase A — Simulation Layer (this sprint, ~3-4 hrs)
War rooms as durable simulation sessions. From any signal, click
"Simulate" → war room initialized with that signal's primary entity.
Pick a competitive move, the system generates competitor reactions
grounded in their dossiers (real DB entities, no fabrication).

### Phase B — War Room Catalog (next)
Listing of all war rooms (mine / team's), filter by entity / status,
multi-user comments, snapshot export. Reuses Phase A primitives.

### Phase C — Decision Ledger
A war room can produce a *decision* — committed action with owner,
target date, expected outcome (the simulated scores). Decision ledger
table, decisions list view, link from signals → decisions they
influenced.

### Phase D — Outcome Capture & Flywheel Closure
At the target date (or on demand), the decision owner records actual
outcome. The system compares actual vs. simulated. Cumulative outcome
data feeds back into:
- Signal scoring rule weights (signals that drove correct decisions
  get higher trust uplift)
- LLM reaction generation prompt (learned reaction patterns vs.
  observed competitor behavior)
- Confidence tier derivation (recalibrate when "confirmed" predictions
  routinely miss)

This is the closing of the flywheel. **It is the differentiator** —
most CI platforms stop at Phase A.

## Phase A — Detailed Design

### Borrowed primitives (from `specs/test.tsx`)

**Move types (8)** — what the player can do:
```
price_cut, new_indication, label_expansion, trial_readout,
acquisition, formulation_switch, geo_expansion, segment_pivot
```

**Reaction types (8)** — what competitors can do:
```
match_price, counter_launch, accelerate_trial, seek_partnership,
attack_label, hold_position, exit_segment, differentiate
```

**Reaction scoring dimensions (5)**:
```
market_share_delta (-10 to +10 % pts)
time_to_execute_months (1-36)
capex_required_musd (50-3000)
regulatory_risk (1-10)
payer_acceptance (1-10)
```

**Game phases (3)**: pre-launch / launch / post-launch.

### Storage

Migration `045_war_rooms.sql`:

```sql
CREATE TABLE war_rooms (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT NOT NULL,
    owner_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    scenario_question TEXT,
    primary_entity_type TEXT,          -- 'company' | 'drug' | …
    primary_entity_id TEXT,
    primary_entity_name TEXT,
    source_signal_id UUID REFERENCES signals(id) ON DELETE SET NULL,
    game_phase TEXT NOT NULL DEFAULT 'launch'
        CHECK (game_phase IN ('prelaunch', 'launch', 'postlaunch')),
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('draft', 'active', 'closed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE war_room_rounds (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    war_room_id UUID NOT NULL REFERENCES war_rooms(id) ON DELETE CASCADE,
    round_number INT NOT NULL,
    player_company_id UUID REFERENCES companies(id),
    player_company_name TEXT,
    move_type TEXT NOT NULL,
    move_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (war_room_id, round_number)
);

CREATE TABLE war_room_reactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    round_id UUID NOT NULL REFERENCES war_room_rounds(id) ON DELETE CASCADE,
    competitor_company_id UUID REFERENCES companies(id),
    competitor_company_name TEXT NOT NULL,
    reaction_type TEXT NOT NULL,
    headline TEXT,
    specific_action TEXT,
    asset_leveraged JSONB,
    rationale TEXT,
    evidence_basis TEXT[] NOT NULL DEFAULT '{}',
    scores JSONB NOT NULL DEFAULT '{}'::jsonb,
    confidence TEXT CHECK (confidence IN ('high', 'medium', 'low')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_war_rooms_owner ON war_rooms (owner_user_id);
CREATE INDEX idx_war_rooms_signal ON war_rooms (source_signal_id) WHERE source_signal_id IS NOT NULL;
CREATE INDEX idx_war_room_rounds_room ON war_room_rounds (war_room_id, round_number);
CREATE INDEX idx_war_room_reactions_round ON war_room_reactions (round_id);
```

### Endpoints (`api/routes/war_room.py`)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/war-rooms` | viewer+ | Create a war room (optionally from a signal) |
| GET | `/war-rooms` | viewer+ | List current user's war rooms |
| GET | `/war-rooms/{id}` | anon | Read a war room with rounds + reactions |
| POST | `/war-rooms/{id}/rounds` | viewer+ | Submit a player move; backend runs reactions; returns full round |
| DELETE | `/war-rooms/{id}` | owner | Soft delete (status='closed') |

A war room is publicly readable (anon GET) so an analyst can share a URL
with their team. Mutations are owner-only. Phase B adds team sharing.

### Reaction engine (`services/war_game_engine.py`)

For each competitor in scope:
1. Build a **dossier** from our DB: drugs they own (most-recent N from
   the `drugs` table joined via OWNS link), trials they sponsor, recent
   market_events involving them. Reuse existing services (`graph.py`
   neighborhood + `metrics.py company_portfolio`).
2. Construct a **prompt** with grounding rules borrowed from
   `specs/test.tsx` `runReactionTurn`:
   - Reaction must cite real assets (NCT/PMID/drug_id)
   - Use enumerated `REACTION_TYPES`
   - Score on the 5 dimensions, conservatively
   - If no asset enables the reaction → `hold_position`
3. Call `LLMSynthesizer` (the existing service) with the prompt.
4. Parse the JSON response → `WarRoomReaction` dict.
5. Persist via the route handler.

The engine is **DB-grounded by construction** — the prompt only sees
entities that exist in our DB. This is the no-fabrication invariant
extended to simulation.

### Frontend

```
frontend/src/
├── pages/CIPage.tsx               — add /ci?room={id} state OR sub-route
├── components/ci/
│   ├── war/
│   │   ├── WarRoomView.tsx        — full screen for an active room
│   │   ├── MoveSelector.tsx       — 8 move types with structured fields
│   │   ├── RoundHistory.tsx       — vertical timeline of rounds + reactions
│   │   ├── ReactionCard.tsx       — competitor name + type + scores + rationale
│   │   ├── ScoreBars.tsx          — 5-dim mini bar chart
│   │   └── EvidenceChips.tsx      — clickable NCT/PMID/drug refs
│   └── SignalDetail.tsx           — add "Simulate in War Room" button
```

The signal-detail "Simulate" button:
1. POST `/war-rooms` with `{source_signal_id, primary_entity_*}`
2. Navigate to `/ci?tab=war&room={id}`
3. WarRoomView loads, MoveSelector pre-suggests a move type based on
   the signal's KBQ tag (e.g., `clinical` → `trial_readout`,
   `m_and_a` → `acquisition`)

## Tests First

### `tests/test_war_room_api.py`
- Module exists + routes registered
- POST creates war room (viewer+), 401 anon
- POST with source_signal_id pulls primary_entity_* from signal
- GET list returns only current user's rooms (viewer+)
- GET detail anon returns full room with rounds + reactions
- GET detail 404 for unknown id
- POST round 401 anon
- POST round 403 for non-owner viewer
- POST round 200 for owner + returns reactions
- POST round increments round_number per room
- DELETE 403 for non-owner, 204 for owner
- Reaction generation called once per competitor (mock the engine)

### `tests/test_war_game_engine.py`
- Engine builds dossiers from the live entity tables (mocked DB)
- Prompt includes grounding rules + dossier
- Falls back to hold_position when LLM returns invalid JSON
- Scores clamped to documented ranges

## Implementation order

1. Spec ✅
2. Tests written (both files), see them fail
3. Migration 045
4. `services/war_game_engine.py` with dossier + LLM prompt + parser
5. `api/routes/war_room.py` + register in app.py
6. Run pytest — green
7. Backend commit
8. Frontend: api wrappers, MoveSelector, ReactionCard, ScoreBars, RoundHistory, WarRoomView
9. Wire SignalDetail → "Simulate" button
10. CIPage routes to WarRoomView when `?room={id}` set
11. vite build clean
12. Frontend commit
13. Push, /debug/migrate, smoke test

## Acceptance — Phase A

- All Phase A tests pass; baseline holds (1869+0 expected)
- After migrate:
  - `POST /war-rooms` (viewer token) creates a room + returns id
  - `POST /war-rooms/{id}/rounds` with `{move_type:"trial_readout", move_payload:{...}}`
    returns reactions with valid scores from at least 2 competitors
  - GET `/war-rooms/{id}` returns the room with rounds + reactions
- /ci page: clicking "Simulate" on any signal opens a war room

## Rollout

1. Local pytest passes
2. Push → Railway redeploys
3. POST /debug/migrate (applies 045)
4. Verify with curl + browser
5. No env var changes (LLM key already set)

## Rollback

- Migration 045 additive — safe to leave applied
- Remove `war_room_route` import in app.py to disable the API
- Hide the Simulate button in SignalDetail

## What this unlocks (Phase B+)

Phase B (~1 week): War room catalog, listing, sharing, comments. Multi-user
collaboration on a hypothesis.

Phase C (~1 week): Decision ledger. A war room round can be promoted to
`decision` status — committed action with owner + target date + expected
outcome (the round's composite score).

Phase D (~2 weeks): Outcome capture flow. At target date, owner records
actual market_share_delta / launch outcome / etc. System computes
prediction error per signal that drove the decision. Feeds into:
- `signal_score_adjustments` table (per rule_version_id, per kbq_tag)
- Quarterly recalibration job updates the rule registry weights
- The flywheel closes — signals get smarter from outcomes

The Phase D loop is the consulting moat. Most pharma CI vendors ship
Phase A and call it AI. ZS's thesis (and ours) is that the value is in
C+D.

## Follow-ups (not in any phase yet)

- Multi-region / multi-payer simulation dimensions
- Probabilistic scoring (Monte Carlo over 100 reaction draws)
- "Replay history" mode — run a past quarter's signals through the
  current scoring rules to validate a rule change
- Brand-team subscription to a war room's outcome — they get notified
  when the decision is committed / outcome recorded
