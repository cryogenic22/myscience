# SPEC F4 — EngagementPage with 7-stage stepper

*Bucket 3 (Frontend IA) loop 3. 30 May 2026.*

## Problem
F2 (sidebar) and F3 (portfolio) deliver pieces. F4 is the *frame* that mounts them together — the top-level page shell that gives the v7 engagement-spine IA its shape. Stage-page content (F5 Brief, F6 Sources, …) renders inside this shell.

## Contract

`EngagementShell` component in `frontend/src/components/layout/EngagementShell.tsx`:

```
┌──────────┬──────────────────────────────────────────────┐
│ Sidebar  │  ┌─────────────────────────────────────────┐ │
│ (F2)     │  │ Engagement Header                       │ │
│          │  │ CagriSema Pre-Launch · launch · 4 days  │ │
│          │  └─────────────────────────────────────────┘ │
│          │  ┌─────────────────────────────────────────┐ │
│          │  │ Stepper · 01 02 ●03 04 05 06 07         │ │
│          │  └─────────────────────────────────────────┘ │
│          │  ┌─────────────────────────────────────────┐ │
│          │  │                                         │ │
│          │  │  Stage content (F5-F12 mount here)      │ │
│          │  │                                         │ │
│          │  └─────────────────────────────────────────┘ │
└──────────┴──────────────────────────────────────────────┘
```

### Props
```typescript
interface Props {
  activeEngagement: ActiveEngagement | null;
  otherEngagements: OtherEngagement[];
  currentStage: LifecycleStage;          // mirrors the URL
  onPortfolioSelect: () => void;
  onEngagementSelect: (id: string) => void;
  onStageSelect: (engagementId: string, stage: LifecycleStage) => void;
  children: React.ReactNode;             // stage content
}
```

### Stage indicators (horizontal stepper)
Mirrors the sidebar's vertical list but as a horizontal dot rail at the top of the content area. 7 dots, numbered 01–07. Current stage gets the accent fill. Complete stages get `✓`. Future stages are outlined.

### Behaviour
- **Engagement header** shows: name, situation pill, focal asset, days-until-workshop with status tone (orange ≤7d / teal ≤30d / muted >30d / "n/a" if no date).
- **Stepper** is a thin row above the content. Stage labels render as tooltips on hover.
- **Stage content** renders `props.children` — no opinion about what mounts. F5+ each provide a stage page that the routing layer wires.
- If `activeEngagement` is null: render an empty state with a "Return to Portfolio" link.
- **ARIA**: shell is `<div role="region" aria-label="Engagement workspace">`; stepper is `<ol aria-label="Lifecycle progress">` with `aria-current="step"`.

## Acceptance tests
1. **Renders sidebar + header + stepper + content when an engagement is active**.
2. **Empty state when no engagement**, with "Return to Portfolio" link.
3. **Header shows days-until-workshop with critical-window styling for ≤7d**.
4. **Stepper has 7 dots, current is marked aria-current="step"**, complete dots get `data-complete`.
5. **Clicking a stepper dot follows the FSM** — back-track / forward-by-one fire, skip-ahead doesn't.
6. **Stage content renders inside the content slot**.

## Out of scope (drift guard)
- No actual routing (consumer wires routes).
- No per-stage content (F5–F12).
- No real data API (consumer passes props).

## Files
- NEW `frontend/src/components/layout/EngagementShell.tsx`
- NEW `frontend/__tests__/layout/EngagementShell.test.tsx`
