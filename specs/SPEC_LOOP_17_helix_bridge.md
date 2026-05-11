# Loop #17 — Helix Bridge MVP

**Status:** Shipped 2026-05-11
**Type:** feature (new top-level surface + new backend route)
**Source:** `specs/raw_helix.md` + `specs/helix_proto.tsx` (expert unified-product spec)

## Why

The expert team filed the **MarketZero · Helix** unified product
spec on 2026-05-11. The vision merges our analyst-facing IA with
Helix's architectural backbone: Bridge home, six primary surfaces in
a left sidebar, FRAME AS DECISION verb, cinematic AI Moments, a
pinned Decision Ledger, and a Hybrid theme.

This loop ships the **Bridge MVP** — the first piece of the new IA
— end-to-end with deep backend wiring. The remaining surfaces ship
in Loops #18–#26 (queue documented in PRODUCT_BACKLOG.md). Eight
concrete backend asks (BE-50..57) were filed in
`docs/AGENT_BACKLOG.md` in this same loop so the backend can advance
in parallel.

## What ships

### Frontend — `/bridge` top-level route

`frontend/src/pages/BridgePage.tsx` — a single-file page (~700 LOC)
that composes the Helix shell + 3-zone Bridge:

- **`HelixSidebar`** — left nav: 6 primary (Bridge / Watchlist /
  KBQ Workspace / War Game / Knowledge / Replay) + 2 oversight
  (Reviewer / Agents) + Connectors footer link. Brand line:
  *MarketZero · Helix*.
- **`HelixHeader`** — `11 agents · live` pulse + **Decision Ledger
  pin** + clock + theme toggle.
- **`BridgeModeToggle`** — Live / Today's Digest / This Week
  segmented control. Drives the `since_days` parameter on the
  moments call.
- **`HeroStrip`** — top moment with EV at stake + serif title +
  "Open Moment →" action.
- **`PulseZone`** — wires to `signalsApi.list()`, sorts by
  `impact_score` desc, filterable by the 10 impact-category chips.
  Each row renders a materiality dial (stroke = score/10 × 88) +
  tier badge (Tier 1/2/3 derived from impact_score) + category tag.
- **`TwinZone`** — SVG force-directed graph of the GLP-1 market.
  12 nodes (assets + patients + payers + CMS + FDA), 11 edges
  including ghost (NCD) + future (pipeline). Hover surfaces a
  detail tooltip. Seed data until BE-53 wires the real twin
  posterior; the visual layer is unchanged when that lands.
- **`MomentsZone`** — calls `bridgeApi.moments()` for LLM-
  synthesised cards. Each card shows category tag · urgency
  countdown · serif title · EV at stake · belief Δ bar · 3
  play-kind colour ticks.
- **`DecisionLedgerSlideOver`** — opened by the header pin, jumps
  to the existing decisions tab. Real DecisionFrame data lands via
  BE-51.

### Backend — `POST /bridge/moments`

`api/routes/bridge.py` (~180 LOC):

- Pulls top-N tier-1/tier-2 signals from the last `since_days`
- Groups by first `kbq_tags` entry (impact category)
- Ranks groups by aggregate `impact_score`
- For each top group, calls `LLMSynthesizer.synthesize()` with a
  short TITLE/SUMMARY prompt — falls back to a deterministic
  echo of the top signal's headline when the LLM is disabled or
  fails to parse
- Builds the Moment object: id (stable hash of category +
  signal_ids), priority, EV proxy (sum of impact_score × $50M),
  expiry hours (driven by top signal urgency), delta_belief
  (toy posterior derived from avg impact_score), three plays
  (aggressive/balanced/cautious templated)
- Returns `{ moments: Moment[] }`

The endpoint is **idempotent** (same input → same moment ids) and
fails open (LLM outage → deterministic moments rather than 500).

Registered in `api/app.py` alongside the other route modules.

### Types — `frontend/src/types/helix.ts`

`Moment`, `Play`, `DeltaBelief`, `ImpactCategory`, `ImpactCategoryId`,
`PlayKind`, `MomentsResponse`. Plus helper fns `tierFor()` and
`categoryFor()` that map raw signal fields to the Helix taxonomy.

`IMPACT_CATEGORIES` constant exposes the 10 categories with their
fixed colours (preserved from the prototype).

### Tests

Frontend `__tests__/helix/BridgePage.test.tsx` (9 cases):

- Renders the *MarketZero · Helix* brand line
- All 6 primary nav items render as links
- Both oversight nav items render
- All three zones render with `role="region"` + correct
  `aria-label`s (Pulse / Digital Twin / AI Moments)
- The bridge-mode toggle shows Live / Today / This Week
- Decision Ledger pin renders in the header
- Real signals from the mocked `signalsApi.list()` appear in Pulse
- All 10 impact-category filter chips render
- Hero strip shows the most urgent moment + EV at stake

Backend `tests/test_bridge_moments.py` (5 cases):

- Endpoint exists at `POST /bridge/moments`
- Synthesises one moment per top category (3 signals across 3
  categories → 3 moments)
- `n` caps the count
- `n` outside [1, 5] is rejected (400/422)
- LLM-disabled path returns deterministic moments (no 500)

## Quality gate

- `npx tsc --noEmit` → clean
- `npx vite build` → 63 KB CSS / 1.64 MB JS (unchanged from Loop #15)
- `npx vitest run` → **535 passing, 22 todo, 0 failures** (58
  files; +11 over Loop #16).
- `pytest tests/test_bridge_moments.py tests/test_signals_api.py` →
  25/25
- 3-route HTTP smoke on dev server → all 200

## What's NOT in this loop (filed for follow-ups)

- **Cinematic Moment overlay** (full-screen dark→light hybrid view
  with PlayCards + Monte Carlo distribution + signal chain) → Loop #18
- **FRAME AS DECISION typed modal** + DecisionFrame creation → Loop #19
  (needs BE-51)
- **Watchlist / Reviewer / Agents / War Game / Knowledge / Replay /
  KBQ Workspace** as top-level routes — the sidebar links route to
  `/watchlist`, `/reviewer`, etc. but those pages don't exist yet;
  current `/ci/*` tabs still work. → Loops #20–#26
- **Hybrid theme** that swaps Moment overlay to light mode — Loop #18
- **Real twin posterior state** in TwinZone → wires once BE-53 ships
- **Real Watchlist materiality bonus** → wires once BE-57 ships
- **Real DecisionFrame data in the Ledger slide-over** → wires once
  BE-51 ships

## Reference

Both reference docs are checked in at `specs/`:

- `specs/raw_helix.md` — surface mapping + engineering brief (1,228
  lines)
- `specs/helix_proto.tsx` — the visual reference prototype
  (1,306 lines)

## Backend asks filed in this loop

`docs/AGENT_BACKLOG.md` — BE-50 through BE-57:

| BE | What | Priority | Unblocks |
|----|------|----------|----------|
| 50 | Materiality 6-input formula (closes PB-104b) | urgent | Pulse zone scoring |
| 51 | DecisionFrame object + endpoint | high | FRAME AS DECISION flow (Loop #19) |
| 52 | Moment synthesizer endpoint **(shipped as part of Loop #17)** | — | Moments zone |
| 53 | Digital Twin posterior state + snapshots | medium | Twin zone, Replay |
| 54 | KBQ workflow engine | medium | KBQ Workspace (Loop #26) |
| 55 | Coach observations | medium | Reviewer surface (Loop #21) |
| 56 | Knowledge ingestion pipeline | medium | Knowledge surface (Loop #24) |
| 57 | Watchlist subscriptions + automation | medium | Watchlist surface (Loop #20) |
