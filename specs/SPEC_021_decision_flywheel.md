# SPEC-021: Decision Flywheel — CI as a War-Game Cockpit

*Date: 2 May 2026 (last revised 4 May 2026 — Phase B detailed design appended)*
*Status: Phase A + A.5 shipped & verified on prod. Phase B in build.*

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

## LLM / tools / harness architecture decision

The PD reviewer noted the path from AI-assisted to AI-led is incremental,
not architectural. To make that real, we settled on this combination:

- **LLM call:** `LLMSynthesizer.raw_chat(system, user, max_tokens)` — a
  single thin passthrough that respects the model fallback chain. Used by
  every war-game prompt (reactor + suggester). No streaming, no tool-use
  inside the LLM call — the war-game prompts are *closed-form* (we
  pre-build the dossier, ask one structured question, parse JSON).
- **Tools:** the existing tool layer (`SQLQueryTool`, `MetricsQueryTool`,
  `GraphSearchTool`) is used at *engine-construction time* — the engine
  pre-fetches the dossier from the DB before invoking the LLM. We do
  NOT give the LLM tool-use access during reaction generation. Reasons:
  (a) the war-game LLM should only see what we vetted, (b) tool-use mid-
  prompt makes outputs non-reproducible, (c) latency. Tools are still
  there if a future "deep research" mode wants them.
- **Harness:** `MarketZeroHarness` is reserved for **multi-step
  autonomous loops** (DataSteward, FAIR scoring, etc.). The war-game
  engines are single-step services and don't need a harness session.
  When Phase D adds outcome detection (which IS a multi-step autonomous
  flow), we'll wrap the suggester+reactor through the harness and get
  session tracking, prompt versioning, and budget caps for free.

The contract: every war-game engine is a function with signature
`(db, llm, **structured_inputs) -> structured_output` so the harness
can wrap it as an executor later without changing the service API.

## Phase A.5 — Autonomous Move Suggester

The reviewer's smallest leap toward AI-led: the system proposes the
move, the human approves. Same engine pattern as the reactor, prompt
reversed.

### Player dossier (mirror of `build_competitor_dossier`)
Pulls from the live DB:
- Player's drugs (with mechanism, phase, approval date)
- Active trials sponsored by the player
- Recent market_events affecting the player
- Pipeline-strength metric (from PharmaMetrics)
- Coverage statement so the LLM doesn't reason as if the dossier were
  exhaustive

### Endpoint
`POST /war-rooms/{id}/suggest-moves` (owner). Body optional:
`{n: 3, signal_context: {kbq_tags, headline}}`. Returns N ranked
suggestions, each:
```json
{
  "move_type": "trial_readout",
  "move_payload": {"target_drug": "semaglutide", "trial_id": "NCT...", ...},
  "rationale": "Player has 3 Phase 3 GLP-1 trials reading out in Q3...",
  "expected_impact_score": 0.78,
  "confidence_score": 0.65,
  "evidence_basis": ["NCT04822181", "drug semaglutide"]
}
```

Suggestions persist in `move_suggestions` (migration 047) for audit and
later prompt-version comparison.

### Frontend
`MoveSuggestions` component shows the 3 cards in the war room above the
move selector. Click a card → pre-fills `MoveSelector` (move type +
payload fields) and scrolls to "Run simulation". The human can accept,
edit, or ignore. Clear visual: this is the system suggesting, you
deciding.

### Why this is still AI-assisted, not AI-led
Honest framing: the human still picks among 3 ranked suggestions, sees
why each was suggested, and triggers the simulation. The system is
**proposing**, not **deciding**. To cross to AI-led we need Phases
C+D — autonomous outcome detection + continuous recalibration. A.5 is
the bridge that makes the future autonomous mode possible without
re-platforming.

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

## Phase B — War Room Catalog (this sprint, ~3 days)

### Requirement

A war-room is born and dies in isolation. Users can simulate inside it
(Phase A), and the system can suggest moves (A.5), but they can't see
all their rooms in one place, can't share a room with a teammate, can't
comment on a round, can't rename or archive. Net effect: every
simulation is throwaway, no team workflow forms, the agentic loop never
gets a memory.

### Hardening fixes folded into B (carried over from Phase A audit)

These touch the same code paths Phase B modifies, so they ship together:

1. **`INSERT … RETURNING id`** — replace title-based read-back races on
   war room create + replace `(war_room_id, round_number)` read-back
   on round insert. Both done via `db.fetch_one("INSERT ... RETURNING id", ...)`.
2. **Tests for `_fetch_competitors` ILIKE fuzzy exclusion** — coverage
   gap identified in audit; add now.

**Audit recommendation overturned on review:** "Wrap submit_round in
BEGIN/COMMIT" was rejected after design check. Two reasons:
(a) production uses `pool_size=5` and the current `db.transaction()`
context manager assumes single-connection mode — it would
AttributeError on `self._conn` in production. Fixing `db.py` for
pool-aware transactions is cross-cutting and out of scope for B.
(b) more importantly, the current "persist what you can, surface
partial failures via `persistence_errors`" behavior is correct, not
buggy. If reaction 3 of 4 fails, we *want* to keep reactions 1, 2, 4
rather than rollback all of them. The response makes the failure
visible to the UI. All-or-nothing would *hide* partial successes from
the user.

Cost guardrails (rate limit + LLM cap) and per-call timeouts deferred
to a "Phase B+ hardening" item; called out separately in `Other
follow-ups` so they aren't lost.

### Storage

Migration `048_war_room_collab.sql` (additive, idempotent):

```sql
ALTER TABLE war_rooms
    ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS war_room_comments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    war_room_id UUID NOT NULL REFERENCES war_rooms(id) ON DELETE CASCADE,
    round_id UUID REFERENCES war_room_rounds(id) ON DELETE SET NULL,
    author_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    author_display_name TEXT NOT NULL,
    body TEXT NOT NULL CHECK (length(body) BETWEEN 1 AND 4000),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    edited_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_war_room_comments_room
    ON war_room_comments (war_room_id, created_at);
CREATE INDEX IF NOT EXISTS idx_war_room_comments_round
    ON war_room_comments (round_id) WHERE round_id IS NOT NULL;
```

`status` already supports `closed` (soft delete). New `archived_at`
distinguishes "user-archived" from "soft-deleted" so the catalog can
show archived rooms in a separate tab without conflating with deletion.

### Endpoints (add to `api/routes/war_room.py`)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/war-rooms` | viewer+ | Existing — extend with `?status=`, `?q=` (title search), `?entity_id=`, `?archived=true|false` |
| PATCH | `/war-rooms/{id}` | owner | `{title?, scenario_question?, status?, archived?: bool}` — partial update |
| GET | `/war-rooms/{id}/comments` | anon | List comments (chronological, optional `?round_id=`) |
| POST | `/war-rooms/{id}/comments` | viewer+ | `{body, round_id?}` — body sanitized server-side |
| PATCH | `/war-rooms/{id}/comments/{cid}` | author | Edit own comment; sets `edited_at` |
| DELETE | `/war-rooms/{id}/comments/{cid}` | author or room owner | Hard delete |

The anon read on detail + comments deliberately keeps the share-by-URL
flow working without auth. PII risk: comments only have
`author_display_name` (not email). Body is server-sanitized to plain
text + safe markdown subset (no script, no html).

### Frontend

```
frontend/src/components/ci/war/
├── WarRoomsList.tsx          — extend: filter chips, search, archived tab
├── WarRoomView.tsx           — add: room actions menu (rename/archive/share),
│                                CommentsPanel, copy-share-URL button
├── CommentsPanel.tsx         — NEW. Threaded by round_id, anon read,
│                                viewer-write inline composer
├── RoomActionsMenu.tsx       — NEW. Rename modal, Archive, Share-URL,
│                                Delete (owner only)
└── ConfidencePill.tsx        — NEW shared. Used by suggester + reactions
                                + (later) decision ledger
```

`ConfidencePill` is the canonical surface for `confidence_score` /
`evidence_validated` / `stripped_citations` so the same trust-signal
shows everywhere reactions or suggestions are rendered. This is the
first piece of the **Phase E coherence kit**.

### Backend → Frontend coverage audit (running spec for Phase E)

Every backend field that exists must have a UI surface OR be on the
explicit deferred list. Updated each phase; the Phase E build closes
remaining gaps.

| Backend field | Surface today | Notes |
|---|---|---|
| `war_rooms.status` | ✅ pill in WarRoomView header | |
| `war_rooms.archived_at` | 🛠 NEW in B (catalog tab) | |
| `war_rooms.scenario_question` | ✅ subtitle in WarRoomView | |
| `war_rooms.primary_entity_name` | ✅ subject line | |
| `war_rooms.source_signal_id` | ⚠ stored, not linked back to signal in UI | Phase E: "Born from signal X" trail |
| `war_room_rounds.move_payload` | ✅ shown in RoundHistory | |
| `war_room_reactions.reaction_type` | ✅ ReactionCard | |
| `war_room_reactions.scores` | ✅ ScoreBars | |
| `war_room_reactions.confidence_score` | 🛠 NEW B: ConfidencePill in RoundHistory | suggester already shows |
| `war_room_reactions.evidence_validated` | 🛠 NEW B: warning chip in RoundHistory | |
| `war_room_reactions.stripped_citations` | 🛠 NEW B: tooltip on warning chip | |
| `war_room_reactions.evidence_basis` | ✅ EvidenceChips | |
| `war_room_reactions.rationale` | ✅ ReactionCard | |
| Dossier `coverage_statement` | ⚠ in prompt, not surfaced in UI | Phase E: "based on N of M known assets" footer per reaction |
| `move_suggestions.rule_version_id` | ⚠ logged, not shown | Phase E: prompt-version diff view |
| Backend → frontend share-URL flow | 🛠 NEW B: explicit "Copy share URL" | already works via anon GET |

Anything marked ⚠ is explicitly deferred to Phase E so we don't lose
sight of it. Anything 🛠 ships in B.

### Tests

`tests/test_war_room_api.py` — extend:
- PATCH 401 anon, 403 non-owner, 200 owner with `{title}` and with `{archived: true}`
- GET `/war-rooms?status=closed&q=test&archived=true` returns filtered set
- GET `/war-rooms/{id}/comments` anon returns ordered list
- POST comment 401 anon, 200 viewer with sanitization (script tags stripped)
- POST comment with `body=""` → 422; body 4001 chars → 422
- PATCH comment by author 200, by other viewer 403, sets `edited_at`
- DELETE comment by author 204, by room owner 204, by stranger 403
- Comments survive room soft-close (status='closed') but cascade on hard delete

Hardening tests:
- `_fetch_competitors` ILIKE fuzzy exclusion when `player_company_id` is NULL
- Round insert + reaction insert wrapped in transaction: simulate reaction-3-of-4
  raising → assert *all 3 prior reactions roll back* (no partial persistence)
- `INSERT … RETURNING id` returns id on first call (no second SELECT)

### Acceptance — Phase B

- All Phase B tests pass; baseline holds (≥1920 → ≥1920 + N new tests, 0 regressions)
- After migrate:
  - `PATCH /war-rooms/{id}` (owner token) renames + archives
  - `POST /war-rooms/{id}/comments` (viewer token) creates a comment
  - `GET /war-rooms/{id}` includes `comments` array on the response
  - `GET /war-rooms?archived=true` lists only archived rooms
  - `GET /war-rooms?q=tirzepatide` substring-matches title
- /ci war room view: rename, archive, copy share URL, post comment, see
  confidence pill on every reaction, see warning chip when evidence stripped

### What this unlocks

C (Decision Ledger) sits cleanly on top: the "Promote round → decision"
button is just another room action, the decision references
`war_room_round_id`, the comments thread carries forward as decision
context. Without B's catalog + room-actions chrome, C has nowhere to
hang its UI.

## Other follow-ups (not in any phase yet)

- Multi-region / multi-payer simulation dimensions
- Probabilistic scoring (Monte Carlo over 100 reaction draws)
- "Replay history" mode — run a past quarter's signals through the
  current scoring rules to validate a rule change
- Brand-team subscription to a war room's outcome — they get notified
  when the decision is committed / outcome recorded
- **Phase B+ hardening:** per-user rate limit on rounds + suggest, daily
  LLM call cap, per-reaction LLM wall-clock timeout (deferred from
  Phase A audit; do before public demo)
- **Phase E — Agentic CI Workspace** (after D ships): tie everything
  into one coherent surface — inbox of "what to war-game now,"
  active-rooms strip with live confidence summaries, decision ledger
  with deadline countdowns, outcome stream with auto-detected matches,
  system-self-narrative ("watching N signals, M rooms active, K
  decisions pending recalibration"). Closes the running coverage-audit
  gaps from each phase.
