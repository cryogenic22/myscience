# SPEC-021: Decision Flywheel — CI as a War-Game Cockpit

*Date: 2 May 2026 (last revised 4 May 2026 — Phase D MVP detailed design appended)*
*Status: Phase A + A.5 + B + C shipped & verified on prod. Phase D MVP in build.*

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

## Phase C — Decision Ledger (this sprint, ~1 week)

### Requirement

A war-room round is a hypothesis. The system models reactions, scores
them, the team comments. But there's no moment where someone says
*"we're going to do X by Y date, owned by Z, and we expect outcome W."*
The simulation evaporates. There's no audit trail of decisions, no
deadline that triggers a post-mortem, no anchor for Phase D's outcome
capture. C turns hypothesis into commitment.

### Storage

Migration `049_decisions.sql` (additive, idempotent):

```sql
CREATE TABLE IF NOT EXISTS decisions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Anchor: every decision originates from a war-room round.
    -- ON DELETE SET NULL because we want decisions to survive room
    -- archive/close (the audit trail outlives the room).
    war_room_round_id UUID REFERENCES war_room_rounds(id) ON DELETE SET NULL,
    war_room_id       UUID REFERENCES war_rooms(id)       ON DELETE SET NULL,
    source_signal_id  UUID REFERENCES signals(id)         ON DELETE SET NULL,

    -- Snapshot at promotion time so we have an immutable record even
    -- if the source room is later archived/edited.
    title             TEXT NOT NULL,
    rationale         TEXT,
    move_type         TEXT NOT NULL,
    move_payload_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,

    owner_user_id     UUID REFERENCES users(id) ON DELETE SET NULL,
    owner_display_name TEXT NOT NULL,

    -- The "expected" frame — what we predicted at commit time
    target_metric     TEXT,                          -- "market_share_delta", "trial readout date", free text
    target_value      TEXT,                          -- "+5pp", "Q3 2026", free text
    deadline          DATE,                          -- when we re-check
    confidence_at_commit REAL                        -- snapshotted from the round's reactions
        CHECK (confidence_at_commit IS NULL OR confidence_at_commit BETWEEN 0.0 AND 1.0),

    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'in_progress', 'verified', 'missed', 'cancelled')),

    -- Phase D fields (filled later, but defined now to avoid a follow-on migration)
    actual_outcome    TEXT,
    actual_outcome_recorded_at TIMESTAMPTZ,
    calibration_score REAL                           -- |predicted - actual| normalized 0..1
        CHECK (calibration_score IS NULL OR calibration_score BETWEEN 0.0 AND 1.0),

    notes TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_decisions_owner   ON decisions (owner_user_id, status);
CREATE INDEX IF NOT EXISTS idx_decisions_room    ON decisions (war_room_id) WHERE war_room_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_decisions_round   ON decisions (war_room_round_id) WHERE war_room_round_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_decisions_deadline ON decisions (deadline) WHERE deadline IS NOT NULL AND status IN ('open','in_progress');
```

Why pre-define Phase D's `actual_outcome` columns now: schema migrations
on prod are minor friction but every avoided migration is a deployment
saved. The fields are NULL until D wires them; CHECK constraints are
permissive (allow NULL).

### Endpoints (`api/routes/decisions.py` — new file)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/decisions/from-round/{round_id}` | viewer+ (room owner) | Promote a round to a decision (snapshots round + reactions) |
| GET | `/decisions` | viewer+ | List current user's decisions; filters: `?status=`, `?war_room_id=`, `?overdue=true` |
| GET | `/decisions/{id}` | anon | Read a single decision (shareable like a war room) |
| PATCH | `/decisions/{id}` | owner | Partial update (status, notes, deadline, target_*) |
| DELETE | `/decisions/{id}` | owner | Hard delete (ledger entries should be rare to delete; we offer it for typos) |

POST `/decisions/from-round/{round_id}` body:
```json
{
  "title": "Accelerate semaglutide MASH expansion",
  "rationale": "Phase 3 readout strong; Lilly's tirzepatide threat real",
  "target_metric": "market_share_delta",
  "target_value": "+3pp by Q4",
  "deadline": "2026-12-31",
  "owner_display_name": "Kapil Pant"  // defaults to current user
}
```

The endpoint pulls the round's `move_type` + `move_payload` and the
mean `confidence_score` of its reactions to snapshot
`confidence_at_commit`. Then inserts the decision row.

PATCH body (all optional):
```json
{
  "status": "in_progress" | "verified" | "missed" | "cancelled",
  "notes": "added context...",
  "deadline": "2027-03-31",
  "target_metric": "...",
  "target_value": "..."
}
```

### Frontend

```
frontend/src/components/ci/decisions/
├── DecisionsTab.tsx           — NEW. New tab on /ci alongside Signals/Rooms
├── DecisionsList.tsx          — NEW. Filter chips (Open/In progress/Verified/Missed/All)
├── DecisionCard.tsx           — NEW. Status pill, deadline countdown, owner, target, link to source room
├── DecisionDetail.tsx         — NEW. Full view with rationale + status changes + audit trail
├── PromoteToDecisionDialog.tsx — NEW. Modal triggered from RoundHistory
└── DeadlineChip.tsx           — NEW. Renders "due in 12d" / "overdue 3d" with color coding
```

`RoundHistory` gets a "Promote to decision" button next to each round
header. Clicking opens `PromoteToDecisionDialog` which pre-fills
title/rationale from the round and lets the user set deadline + target.
On submit → `POST /decisions/from-round/{round_id}` → navigate to the
new decision.

CI page navigation:
```
/ci?tab=signals       (existing)
/ci?tab=rooms         (existing — Phase A/B war rooms)
/ci?tab=decisions     (NEW — Phase C ledger)
```

### Backend → Frontend coverage audit (running)

Cumulative table — bringing C's backend fields into the running audit:

| Backend field | Surface today | Notes |
|---|---|---|
| `decisions.title` | 🛠 NEW C: DecisionCard | |
| `decisions.move_type` + `move_payload_snapshot` | 🛠 NEW C: shown via existing MOVE_TYPE_META icons | |
| `decisions.target_metric` + `target_value` | 🛠 NEW C: DecisionCard "Target: X" line | |
| `decisions.deadline` | 🛠 NEW C: DeadlineChip with color (green > 14d, amber 1-14d, red overdue) | |
| `decisions.status` | 🛠 NEW C: status pill on card | |
| `decisions.confidence_at_commit` | 🛠 NEW C: shown as "Committed at NN% confidence" | |
| `decisions.war_room_id` / `war_room_round_id` | 🛠 NEW C: "From: <war room title>" link | |
| `decisions.source_signal_id` | ⚠ stored, not yet linked back to signal in UI | Phase E: full provenance trail |
| `decisions.actual_outcome` | ⏳ Phase D | |
| `decisions.calibration_score` | ⏳ Phase D | |

### Tests

`tests/test_decisions_api.py` — new file:
- Module exists + routes registered
- POST from-round 401 anon, 403 if user is not the room owner
- POST from-round 200: snapshots `move_type`, `move_payload`, mean `confidence_score`
- POST from-round 404 if round doesn't exist
- POST from-round 400 if `deadline` invalid format or in the past (>1 day past)
- GET list returns only current user's decisions
- GET list filter by status, war_room_id, overdue=true
- GET detail anon returns decision (anon-readable like rooms)
- PATCH 401 anon, 403 non-owner, 200 owner with status transition
- PATCH 400 for invalid status
- DELETE 403 non-owner, 204 owner

### Acceptance — Phase C

- All Phase C tests pass; baseline holds (1980 → 1980 + N)
- After migrate:
  - Promote a round to decision → row in `decisions` table with
    `confidence_at_commit` snapshotted from the round's reactions
  - Decision survives war room archive/close (FK is SET NULL, not CASCADE)
  - GET `/decisions?overdue=true` lists only past-deadline open decisions
  - PATCH status open → in_progress → verified persists state
- /ci page: new "Decisions" tab; promote button visible in RoundHistory; deadline chips render

### What this unlocks (Phase D)

D is the outcome capture loop. It needs a stable identifier for "the
thing we committed to" — that's `decisions.id`. D reads
`decisions WHERE status IN ('open','in_progress')`, watches DataSteward
signals for outcome matches, proposes a status update + actual_outcome
to the owner, computes `calibration_score`, writes back. Without C's
ledger, D has nothing to learn from.

## Phase D — Outcome Capture + Flywheel Closure (MVP, this sprint)

### Requirement

A decision sits in the ledger with a deadline and an expected outcome.
When reality moves — a competitor announces, a trial reads out, an FDA
action lands — those signals are already flowing into our `signals`
table from the DataSteward pipeline. But there's no link between
*"signal X just landed"* and *"this decision predicted that."* So the
predicted-vs-actual loop never closes, the system never learns, and
the moat that distinguishes us from "vendors stopping at simulation"
doesn't form. **D wires that link.**

### Honest scope split

The full D vision is large (auto-detection scheduler + weight
recalibration + per-rule learning ledger). This phase ships **D MVP**:
the matcher + the human-in-the-loop capture surface. Once that loop is
proven against real signals on prod, **D Phase 2** layers the
autonomous batch detection + signal-weight feedback on top of it.

| | D MVP (this sprint) | D Phase 2 (later) |
|---|---|---|
| Matching | On-demand: user clicks "Detect outcome" on a decision | Background scheduler runs hourly across all open decisions |
| Capture | Owner picks one of N candidate signals; system writes `actual_outcome` + `calibration_score` | Same, plus auto-propose via Slack/email when high-confidence match found |
| Learning | `signal_score_adjustments` table populated; visible in Recalibration tab | Quarterly batch updates `intelligence_rules.yaml` weights |
| Positioning | **AI-informed** — system suggests, human decides | **Approaching AI-led** — system flags, human confirms |

### Matching design (`services/outcome_detector.py`)

Given a decision with `move_type`, `primary_entity_id`, and `created_at`,
score each candidate signal in `signals` table on three dimensions:

1. **Entity overlap** (0.0–0.5):
   - `1.0` weight if `signal.primary_entity_id == decision.primary_entity_id` (via war_room)
   - `0.5` weight if signal's `primary_entity_id` ∈ `related_entity_ids` of any other signal pointing at the decision's entity
   - `0.0` otherwise
2. **KBQ overlap** (0.0–0.3): mapped from `move_type`:
   - `trial_readout` → `{clinical}`
   - `new_indication` → `{clinical, regulatory}`
   - `label_expansion` → `{regulatory}`
   - `price_cut` → `{pricing_access}`
   - `acquisition` → `{m_and_a, strategic}`
   - `formulation_switch` → `{product}`
   - `geo_expansion` → `{strategic}`
   - `segment_pivot` → `{strategic, product}`
   - Score = `0.3 * len(intersect) / len(expected_kbqs)`
3. **Temporal proximity** (0.0–0.2): higher score for signals landing
   between `decision.created_at` and `decision.deadline + 30 days`
   - In window: `0.2`
   - Within 60 days outside window: `0.1`
   - Else: `0.0`

Composite **match_score** = sum (0.0–1.0). Threshold for surfacing as
candidate: `≥ 0.4`. Top N by score, capped at 5.

Signals tied to the same source as the decision (`source_signal_id`)
are excluded — that's the seed signal, not an outcome.

### Calibration scoring (`services/outcome_detector.calibrate`)

Once an outcome is captured (decision moves to `verified` or `missed`
with `actual_outcome` text), compute a **simple calibration_score**:

- The heuristic is intentionally crude in MVP — text-based, not numeric:
  - `verified` + decision had non-null `confidence_at_commit ≥ 0.5`
    → calibration_score = `confidence_at_commit` (we predicted high
    and were right; full credit)
  - `verified` + low confidence_at_commit → `1 - confidence_at_commit`
    (we hedged but were right; partial credit because we were
    *too* uncertain)
  - `missed` + high confidence_at_commit → `1 - confidence_at_commit`
    (we predicted high and were wrong; large penalty)
  - `missed` + low confidence_at_commit → `confidence_at_commit`
    (we hedged and were wrong; small penalty — we already knew we
    didn't know)

This produces a value in `[0, 1]` where higher = better-calibrated.
Stored on `decisions.calibration_score`.

D Phase 2 will replace this with a richer numeric metric once we have
structured `target_value` parsing (e.g. *"+3pp by Q4"* → numeric ±2pp
delta from actual market_share_delta).

### Storage

Migration `050_signal_score_adjustments.sql`:

```sql
CREATE TABLE IF NOT EXISTS signal_score_adjustments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- What rule version was active when the matched signal fired?
    rule_version_id TEXT NOT NULL,
    -- Which KBQ category does this adjustment apply to?
    kbq_tag TEXT NOT NULL,

    -- Provenance — which decision drove this adjustment?
    decision_id UUID REFERENCES decisions(id) ON DELETE SET NULL,
    matched_signal_id UUID REFERENCES signals(id) ON DELETE SET NULL,

    -- The numbers that drive future weight recalibration (Phase 2)
    calibration_score REAL NOT NULL
        CHECK (calibration_score BETWEEN 0.0 AND 1.0),
    weight_delta_suggested REAL,  -- derived; -0.05 if missed, +0.05 if verified, etc.

    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_signal_adj_rule_kbq
    ON signal_score_adjustments (rule_version_id, kbq_tag);

CREATE INDEX IF NOT EXISTS idx_signal_adj_decision
    ON signal_score_adjustments (decision_id) WHERE decision_id IS NOT NULL;
```

D MVP populates this on every `capture-outcome` call so the data is
ready when D Phase 2's recalibration job ships.

### Endpoints (extend `api/routes/decisions.py`)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/decisions/{id}/suggest-outcome` | owner | Run matcher; return ranked candidate signals |
| POST | `/decisions/{id}/capture-outcome` | owner | Owner picks a signal as the outcome; computes calibration_score, writes to decision + signal_score_adjustments |

`POST /decisions/{id}/suggest-outcome` response:
```json
{
  "decision_id": "...",
  "rule_version_id": "outcome-v1.0.0",
  "candidates": [
    {
      "signal_id": "...",
      "headline": "...",
      "summary": "...",
      "kbq_tags": ["clinical"],
      "created_at": "...",
      "primary_entity_name": "...",
      "match_score": 0.78,
      "match_components": {
        "entity_overlap": 0.5,
        "kbq_overlap": 0.15,
        "temporal_proximity": 0.13
      }
    }
  ],
  "count": 3
}
```

`POST /decisions/{id}/capture-outcome` body:
```json
{
  "signal_id": "...",       // pick from suggested candidates
  "verdict": "verified" | "missed" | "cancelled",
  "actual_outcome": "...",  // required text summary; UI pre-fills from signal.headline
  "notes": "..."            // optional extra context
}
```
Response = updated decision (`status` set, `actual_outcome` populated,
`calibration_score` computed, `actual_outcome_recorded_at` set).

### Frontend

```
frontend/src/components/ci/decisions/
├── OutcomeDetector.tsx       — NEW. Modal: "Detect outcome" button →
│                               candidate signals list with match_score bars
├── CalibrationChip.tsx       — NEW. Renders calibration_score with color
│                               (>0.66 green, >0.33 amber, else red)
└── DecisionCard.tsx          — extend: "Detect outcome" button for
                                in_progress decisions; CalibrationChip when
                                calibration_score is non-null
```

The flow:
1. Decision in `in_progress` state → "Detect outcome" button visible
2. Click → POST `/decisions/{id}/suggest-outcome` → modal shows ranked
   candidate signals (each with headline, kbq tags, match_score bar)
3. Owner picks one → composes `actual_outcome` text (pre-filled with
   signal headline) → picks verdict (`verified`/`missed`)
4. Submit → POST `/decisions/{id}/capture-outcome` → decision updates
   in place with new status + `calibration_score` + `CalibrationChip`

### Backend → Frontend coverage audit (running)

Phase D additions:

| Backend field | Surface today | Notes |
|---|---|---|
| `decisions.actual_outcome` | ✅ already shown in DecisionCard expanded view (built in C, populated in D) | |
| `decisions.calibration_score` | 🛠 NEW D: CalibrationChip on card | |
| `decisions.actual_outcome_recorded_at` | ✅ shown next to actual_outcome label | |
| `signal_score_adjustments` table | ⏳ D Phase 2: Recalibration ledger view | Populated in D MVP, surfaced in Phase E |
| `match_components` per candidate | 🛠 NEW D: tooltip on match_score bar in OutcomeDetector | |

### Tests

`tests/test_outcome_detector.py` — new file:
- `_kbq_for_move`: every move_type maps to ≥1 KBQ
- `_score_temporal`: in-window/near-window/far cases all expected scores
- `_score_kbq`: full overlap, partial overlap, no overlap
- `_score_entity`: same entity / related entity / unrelated
- `match_signals_to_decision`: returns sorted by score, threshold respected, source_signal excluded, capped at 5
- `compute_calibration_score`: all 4 quadrants (verified+high, verified+low, missed+high, missed+low)
- `compute_calibration_score`: NULL confidence_at_commit returns 0.5 (neutral)

Extend `tests/test_decisions_api.py`:
- POST suggest-outcome 401 anon, 403 non-owner
- POST suggest-outcome 200: returns candidates ordered by match_score
- POST suggest-outcome excludes the source_signal_id
- POST capture-outcome 401 anon, 403 non-owner
- POST capture-outcome 200: writes actual_outcome, calibration_score,
  status, AND inserts signal_score_adjustments row
- POST capture-outcome 400 if signal_id not in candidates
- POST capture-outcome 400 for invalid verdict

### Acceptance — Phase D MVP

- All Phase D tests pass; baseline 1982 → 1982 + N
- After migrate (050):
  - For an open decision, POST suggest-outcome returns ranked candidates
    from real signals (or empty array if no matches)
  - Capturing an outcome writes `decisions.actual_outcome` +
    `calibration_score` + appends `signal_score_adjustments`
  - DecisionCard renders CalibrationChip when score is set
- /ci page: "Detect outcome" button on in_progress decisions; modal
  shows ranked candidates; capture writes back

### What this unlocks (D Phase 2 + beyond)

- **D Phase 2:** background scheduler iterates open decisions every
  hour, calls `match_signals_to_decision`, sends notification to owner
  when high-confidence match found (Slack/email), no manual click
- **D Phase 2:** recalibration job aggregates `signal_score_adjustments`
  per `(rule_version_id, kbq_tag)` and adjusts weights in
  `intelligence_rules.yaml` quarterly
- **Phase E (Agentic Workspace):** outcome stream surface that shows
  these matches happening in near-real-time across all decisions

This is the moat: the system that watches for outcomes and updates
its own scoring as predictions land. **Most pharma CI vendors stop at
Phase A** — they show signals, they show competitive landscape, they
don't close the loop. C+D is what makes the platform get smarter every
quarter rather than aging like a deck.

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
