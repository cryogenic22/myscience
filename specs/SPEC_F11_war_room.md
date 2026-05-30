# SPEC F11 — WarRoomPage (3-mode toggle)

*Bucket 3 (Frontend IA) loop 10 — the largest single surface in the v7 IA. 30 May 2026.*

## Problem
The war room is where the engagement's preparation pays out. v7 surfaced three first-class modes:
- **Guided**: human drives the focal team (Novo); agents project counter-moves with confidence + rationale.
- **Autonomous**: agents drive all sides; user watches the simulation; narration streams.
- **Game-theoretic**: payoff matrix with the Nash equilibrium cell highlighted; Monte Carlo summary.

All three share **one Scenario state model** (set in F10), so mid-session switching is legitimate. The deep-teal accent `[data-warroom="active"]` kicks in (the ZS theme's mode-shift signal — you're in the simulation now).

## Contract

New component `frontend/src/pages/WarRoomPage.tsx` (headless).

### Top-level structure
```
┌────────────────────────────────────────────────────────────┐
│ Header — engagement, scenario name, trigger event, mode    │
├────────────────────────────────────────────────────────────┤
│ Mode tablist — Guided · Autonomous · Game-theoretic        │
├────────────────────────────────────────────────────────────┤
│                                                            │
│ Active mode panel (one of three)                           │
│                                                            │
├────────────────────────────────────────────────────────────┤
│ Footer — Mark stage complete                               │
└────────────────────────────────────────────────────────────┘
```

The root carries `data-warroom="active"` so the ZS theme swaps `--color-accent` to the deep teal.

### Guided mode panel
- **Round counter** at the top.
- **Available Novo moves** (passed via props) as buttons. Click → `onPlayMove(moveId)`.
- **Move ledger**: each played move as a row (team / move / round / rationale chip).
- **Projected counter-moves** (other teams' agents) — confidence percentage + rationale.
- **"Commit turn" CTA** at the bottom to advance to the next round.

### Autonomous mode panel
- **State**: `idle | running | paused | complete`.
- **Controls**: Play / Step / Reset / Pause buttons (enabled per state).
- **Narration stream**: list of narration lines (one per simulated move).
- **Progress indicator** when running.

### Game-theoretic mode panel
- **Payoff matrix** as a `<table>` — rows = Novo's strategic options, columns = Lilly's responses, cells = 5y NPV utility (DKK bn). The Nash cell has `data-nash="true"` and accent styling.
- **Strategy labels** on rows + columns.
- **Monte Carlo summary** (optional): N runs, mean Novo NPV, p10–p90 range.

### Props
```typescript
interface Props {
  scope: { engagementName: string; focalAsset: string };
  scenario: ScenarioContext;            // id, name, trigger event
  mode: 'guided' | 'autonomous' | 'game_theoretic';
  onModeChange: (m: WarRoomMode) => void;
  onMarkComplete: () => void;

  // Guided
  guidedRound: number;
  availableNovoMoves: { id: string; type: string; statement: string }[];
  guidedLedger: { team: string; move: string; round: number; rationale: string }[];
  projectedCounterMoves: { team: string; move: string; confidence: number; rationale: string }[];
  onPlayMove: (moveId: string) => void;
  onCommitTurn: () => void;

  // Autonomous
  autonomousState: 'idle' | 'running' | 'paused' | 'complete';
  autonomousNarration: string[];
  onAutonomousStart: () => void;
  onAutonomousStep: () => void;
  onAutonomousPause: () => void;
  onAutonomousReset: () => void;

  // Game-theoretic
  payoffMatrix: {
    rowsLabel: string;                // 'Novo'
    colsLabel: string;                // 'Lilly'
    rows: string[];                   // Novo strategies
    cols: string[];                   // Lilly responses
    cells: number[][];                // NPV utility per (row, col)
    nash: [number, number];           // [rowIdx, colIdx]
  };
  monteCarlo?: {
    runs: number;
    meanNovoNPV: number;
    p10: number;
    p90: number;
  };
}
```

### Behaviour
- **Mode toggle** uses `role="tablist"` with `role="tab"` children; panels are `role="tabpanel"` named by `aria-labelledby`.
- **Deep-teal accent** via `data-warroom="active"` on the root element. The ZS theme handles the rest.
- **Game-theoretic Nash cell** is visually distinguished (background + border + label "★ Nash equilibrium").
- **Autonomous controls** enable per state:
  - `idle` / `complete` → Play, Reset enabled.
  - `running` → Pause, Step, Reset enabled.
  - `paused` → Play, Step, Reset enabled.
- **Empty narration in autonomous** → "Press play to begin simulation" placeholder.
- **Empty ledger in guided** → "Pick a move to begin Round 1" placeholder.

## Acceptance tests
1. Renders 3 mode tabs with `aria-selected`.
2. Default mode renders the matching panel.
3. Clicking a mode tab fires `onModeChange`.
4. Root has `data-warroom="active"`.
5. Guided: available moves render as buttons; clicking fires `onPlayMove(moveId)`.
6. Guided: ledger rows show team + move + round.
7. Guided: projected counter-moves show confidence percentage.
8. Guided: "Commit turn" fires `onCommitTurn`.
9. Autonomous: Play button fires `onAutonomousStart` when idle.
10. Autonomous: Pause button fires `onAutonomousPause` when running.
11. Autonomous: narration lines render.
12. Game-theoretic: payoff matrix renders all (row × col) cells with utility values.
13. Game-theoretic: Nash cell has `data-nash="true"`.
14. Game-theoretic: Monte Carlo summary visible when provided.
15. Footer Mark stage complete CTA fires `onMarkComplete`.
16. ARIA: main with `aria-label="War Room"`, tablist with 3 tabs, panel with aria-labelledby.

## Out of scope
- No actual agent execution (callbacks only; backend wiring is W2–W4).
- No flywheel chips wired to live events (W5).
- No saving the simulation state (separate concern).

## Files
- NEW `frontend/src/pages/WarRoomPage.tsx`
- NEW `frontend/__tests__/pages/WarRoomPage.test.tsx`
