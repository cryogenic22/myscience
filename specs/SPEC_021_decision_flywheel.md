# SPEC-021: Decision Flywheel — CI as a War-Game Cockpit

*Date: 2 May 2026*
*Status: Phase A shipped + strengthenings in progress*

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

## Honest positioning: AI-assisted vs AI-led

This distinction matters for client positioning and for our own engineering
discipline. Per the PD review:

| Phase | Honest classification |
|---|---|
| A — Simulation | **AI-assisted.** Human picks the move, system models reactions. |
| B — Catalog | No AI — pure CRUD. |
| C — Decision Ledger | **AI-assisted.** Human commits, system records with AI-generated context. |
| D — Outcome capture + flywheel | **AI-informed, approaching AI-led** when outcome detection is automated. |
| Future — autonomous moves, multi-round, real-time recalibration | **AI-led.** |

Don't oversell Phase A as "AI-led decision-making." It is "AI-powered
competitive simulation grounded in real market data." That's strong
positioning; it's also accurate.

The infrastructure built in this spec **supports** the upgrade to AI-led
without architectural rework. Each phase increases autonomy on the same
substrate.

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

## PD reviewer strengthenings (incorporated)

Three concrete asks from the design review, all incorporated below and
shipped as a fast follow-up after Phase A:

1. **Numeric confidence calibration.** Reaction `confidence` is a numeric
   `confidence_score` (0.0–1.0); the categorical label (high/medium/low)
   is derived from thresholds (≥0.66 = high, ≥0.33 = medium, else low).
   This makes Phase D's prediction-error computation mathematical, not
   categorical — essential for meaningful weight adjustment.

2. **Post-LLM grounding validation.** Every cited evidence ID
   (NCT/PMID/drug_id/etc.) is verified against the live DB after the LLM
   responds. Hallucinated IDs are stripped and `confidence_score` is
   downgraded by 0.2 per stripped citation (floor 0.0). The reaction is
   tagged `evidence_validated: true|false` so the UI can flag stripped
   citations explicitly. This is the same numeric-grounding pattern as
   the SPEC-015 remediation plan, applied to simulation output.

3. **Dossier coverage awareness.** `build_competitor_dossier` includes a
   `coverage_statement` like *"Showing 3 of ~12 known drugs and 5 of
   ~25 active trials"* derived from `COUNT(*)` queries. The prompt
   includes this so the LLM doesn't reason as if the dossier were
   exhaustive. The UI surfaces it on each reaction card so analysts
   calibrate their trust.

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

## Path from AI-assisted to AI-led (PD review follow-ups)

These move us from "AI augments the analyst" to "AI leads with human
oversight." The architecture supports each one without rework — each is
a new prompt, a new loop, or a new wire, not a new system.

### Autonomous move generation (Phase A.5)
Today: human picks the move type. AI-led: on a signal, the system
generates 2–3 plausible competitive moves the player could make,
simulates reactions for each, and presents a ranked recommendation.
Same engine, same dossier pattern, prompt reversed
("given this signal + player asset dossier, propose 3 high-impact
responses constrained to the 8 move types"). Frontend shifts from
*Pick a move → Simulate* to *Review and approve recommendation*.

### Multi-round forward simulation (Phase B.5)
Today: single round (player moves, competitors react, done). AI-led:
the engine plays N rounds forward — competitor reactions trigger
follow-up moves from the player and other competitors, surfacing
stable equilibria and unstable dynamics. This is where "war game"
becomes literal game theory, not just reaction prediction. Loop the
existing single-round engine, cap depth.

### Automated outcome detection (replaces manual capture in Phase D)
Today (as specified): decision owner manually records actual outcome at
target date. AI-led: the existing DataSteward signal loop watches the
decision's primary entity. When a matching outcome signal appears
(trial status change, FDA action, competitor launch), the system
auto-proposes the post-mortem: *"Your committed decision predicted
Lilly would hold_position. Signal fired 12 days ago shows they
accelerated NCT09876543. Confirm as actual outcome?"* This wires the
decision ledger directly to the signal pipeline and closes the loop
without waiting for a human to remember.

### Continuous (not quarterly) signal-weight recalibration
Today (as specified): batch quarterly recalibration job. AI-led:
every captured outcome immediately adjusts the relevant
`signal_score_adjustments` row. The system maintains a running per-KBQ
accuracy score and surfaces its own confidence trends:
*"Clinical signals: 73% over last 6mo. M&A signals: 41% — consider
reducing weight."* This makes calibration a property of the system,
not an ops task.

### The end state we're building toward

A strategy team configures Market Zero at the start of a quarter
(competitive scope, watched entities, KBQs of interest). At the end of
the quarter they receive a report:

> Here are the 12 competitive moves that occurred this quarter, here's
> how they compared to our simulated predictions, here's how we've
> adjusted our models, and here are the 3 decisions you should
> consider for next quarter.

— with no human manually triggering simulations or recording outcomes
in between. SPEC-021 Phase A is step one of five toward that vision.

## Other follow-ups (not in any phase yet)

- Multi-region / multi-payer simulation dimensions
- Probabilistic scoring (Monte Carlo over 100 reaction draws)
- "Replay history" mode — run a past quarter's signals through the
  current scoring rules to validate a rule change
- Brand-team subscription to a war room's outcome — they get notified
  when the decision is committed / outcome recorded
