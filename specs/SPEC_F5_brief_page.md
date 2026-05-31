# SPEC F5 — BriefPage (Launch-only) + PriorityMatrix grid

*Bucket 3 (Frontend IA) loop 4. 30 May 2026.*

## Problem
F4 EngagementShell provides the frame; F5 fills the first stage with content. The BriefPage renders the Z4 Business Context Brief plus the Z5 priority matrix as the engagement's scoping artifact. Per Riya's feedback, **situation is Launch-only for the demo** — Defense and LCM tabs would be noise.

## Contract

New component `frontend/src/pages/BriefPage.tsx` (headless — accepts data via props; no API calls).

### Sections (top-to-bottom)
1. **Brief header** — focal asset, situation pill, sign-off state (signed-off date + signer, or "Draft").
2. **Strategic decisions** — the 3–7 decisions the wargame must inform. Each as a card with statement + rationale.
3. **Competitive set** — the threats grouped by `primary` / `secondary` / `watch`. Each threat = entity ref + note.
4. **Priority matrix** — 8 ZS domains × 3 priority levels visualised as a grid. Critical priority gets the orange accent; high gets teal; medium muted.
5. **Success criteria** + **Constraints** — bullet lists, side-by-side.
6. **Footer action row** — sign-off button (disabled if already signed off, primary if draft).

### Props
```typescript
interface Props {
  brief: {
    id: string;
    focalAsset: string;
    situation: 'launch';           // Riya: Launch-only this demo
    strategicDecisions: { statement: string; rationale: string }[];
    competitiveSet: {
      entityRef: string;
      threatLevel: 'primary' | 'secondary' | 'watch';
      note: string;
    }[];
    successCriteria: string[];
    constraints: string[];
    signedOff: boolean;
    signedOffBy?: string | null;
    signedOffAt?: string | null;
  };
  matrix: {
    cells: Record<DossierDomain, Priority>;   // all 8 domains required
  };
  onSignOff: () => void;
  onCellEdit?: (domain: DossierDomain, priority: Priority) => void;
}
```

### Behaviour
- **Launch-only**: situation pill renders 'Launch' (no toggle). If `brief.situation !== 'launch'`, render a "Demo supports Launch only" stub — drift guard.
- **Priority grid**: 4-column-wide table for the 8 domains (2 columns × 4 rows on mobile). Each cell is a button (when `onCellEdit` is set, clicking cycles through critical → high → medium → critical).
- **Empty competitor set** → render an "Awaiting primary research" empty state, not a blank table.
- **Sign-off button**: primary orange if `!signedOff`, disabled with green checkmark if signed off.
- **Theme-aware** via CSS vars.

### Acceptance tests
1. Renders the focal asset + 'Launch' situation pill.
2. Renders ≥ 1 strategic decision (mirrors BCB invariant).
3. Priority matrix renders all 8 domains; critical cells use accent color.
4. Empty competitor set renders the "awaiting primary research" placeholder.
5. Clicking sign-off button fires `onSignOff` when in draft state.
6. Sign-off button is disabled when already signed off.
7. Cell click fires `onCellEdit` with the next priority in cycle.
8. ARIA: main landmark with `aria-label="Brief and Scope"`; matrix is a `<table>` with row/column headers.

## Out of scope
- No API wiring (a routing loop wires).
- No editing of decisions/competitors (read-only this loop; edit is its own loop).
- No real "primary research" trigger — just the empty-state placeholder.

## Files
- NEW `frontend/src/pages/BriefPage.tsx`
- NEW `frontend/__tests__/pages/BriefPage.test.tsx`
