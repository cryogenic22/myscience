# SPEC F10 — ScenariosPage (event-triggered + team-moves + decision-options)

*Bucket 3 (Frontend IA) loop 9. 30 May 2026.*

## Problem
v7 scenarios were trend-described narratives ("Strong / Contested / Weak Launch") — too shallow to be defensible. The ZS framework requires every scenario to carry: **trigger event** (concrete, dated, evidenced) → **team-moves** (one per non-focal team, derived from rational interest) → **decision-options** (typically 3 mutually-exclusive paths for the focal team) → **decision-output** (which option the wargame surfaces as defensible and why).

## Contract

New component `frontend/src/pages/ScenariosPage.tsx` (headless).

### The scenario object
```typescript
interface Scenario {
  id: string;
  name: string;                    // 'Lilly Offensive'
  trigger: {
    event: string;                 // 'Lilly launches orforglipron at $200 WAC...'
    date?: string;                 // when (or expected)
    evidence: { factId: string; predicate: string }[];   // grounding
  };
  probability: number;             // prior, 0..1
  probabilityCurrent?: number;     // current, after calibration; null until learn-loop fires
  teamMoves: {
    team: string;                  // 'Lilly' | 'Payer' | 'HCP' etc.
    move: string;                  // 'Aggressive WAC parity + premium specialist rebates'
    rationale: string;             // why this team plays this move
  }[];
  decisionOptions: {
    id: string;
    statement: string;             // 'Hold pricing'
    rationale: string;
    npv5yDkkBn?: number;           // 5-year NPV utility, optional
    recommended?: boolean;
  }[];
  decisionOutput?: string;         // narrative of what wins and why
  blockedByGaps?: string[];        // ids of gaps from F9 that prevent running this
}
```

### Sections
1. **Header** — engagement scope, total scenarios, recommended-output count.
2. **Scenario grid** — cards by probability descending. Each shows: name, **probability dial** (prior vs current if available), trigger event line, team-move count, decision-option count.
3. **Active scenario expansion** — clicking a card opens it inline with full detail:
   - **Trigger** card with event text + date + evidence chips (click → onOpenFact).
   - **Team-moves** list (one per team, with rationale).
   - **Decision-options** grid (typically 3 cards side-by-side), with NPV when present and the recommended option marked.
   - **Decision output** narrative.
   - **Blocked-by-gaps** banner when scenario depends on unresolved gaps.
   - **"Play in War Room →"** CTA (fires `onPlayScenario`).
4. **Footer** — "Mark stage complete" CTA, disabled if any scenario is blocked.

### Props
```typescript
interface Props {
  scope: { engagementName: string; focalAsset: string };
  scenarios: Scenario[];
  activeScenarioId: string | null;
  onSelectScenario: (id: string | null) => void;     // null collapses
  onPlayScenario: (id: string) => void;              // hands off to War Room
  onOpenFact: (factId: string) => void;
  onMarkComplete: () => void;
}
```

### Behaviour
- **Calibration dial**: shows `prior% → current%` if `probabilityCurrent` differs from `probability`; the learn-loop signal in operation.
- **Recommended decision option** gets the accent color + "RECOMMENDED" badge.
- **Blocked scenario** renders dimmed with a banner naming the blocking gaps.
- **Play CTA** disabled when blocked.
- **Mark stage complete** disabled if any scenario has blockedByGaps non-empty.

## Acceptance tests
1. Header shows scenarios count + recommended-output count.
2. Each scenario card shows name, probability, trigger snippet, move/option counts.
3. Probability dial renders prior + current when both present.
4. Clicking a card fires `onSelectScenario(id)`; activeScenarioId param expands that card.
5. Expanded card shows trigger evidence chips, team moves, decision options, decision output.
6. Recommended option has the "RECOMMENDED" badge.
7. Clicking a trigger evidence chip fires `onOpenFact`.
8. "Play in War Room" button fires `onPlayScenario`.
9. Blocked scenario renders dim + blocked banner.
10. "Mark stage complete" disabled if any blocked scenario exists.
11. ARIA: `<main aria-label="Scenarios">`, scenarios are `<ul role="list">`.

## Out of scope
- No actual war-room handoff (just fire callback).
- No probability-adjustment UI.
- No editing of scenario fields.

## Files
- NEW `frontend/src/pages/ScenariosPage.tsx`
- NEW `frontend/__tests__/pages/ScenariosPage.test.tsx`
