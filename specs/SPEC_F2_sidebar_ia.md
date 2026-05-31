# SPEC F2 — Engagement-spine sidebar IA

*Bucket 3 (Frontend IA) loop 1. 30 May 2026.*

## Problem
The current `/ci` IA is a flat tab-set (Inbox / Digest / Signals / Watchlist / Rooms / Decisions / Insights / Reviewer). The v7 design canon's commitment is engagement-as-spine: **Portfolio → Active Engagement (7 stages) → Other Engagements**. Without this IA, every stage UI built later (F3 dashboard, F4 stepper, F5–F12) feels bolted onto the wrong shape.

## Contract

New component `frontend/src/components/layout/EngagementSidebar.tsx`:

```
┌────────────────────────────┐
│  HOME · Portfolio   📊     │   ← pinned at top
├────────────────────────────┤
│  ACTIVE ENGAGEMENT          │   ← header
│  CagriSema Pre-Launch       │   ← engagement name + ZS-orange dot
│   01 Brief                  │   ← 7 stages, one per row,
│   02 Sources                │     current stage highlighted
│  ▶ 03 Dossier (current)     │     completed stages get ✓
│   04 Synthesis              │     skip-ahead is disabled
│   05 Gaps                   │     back-track is enabled (visible cursor)
│   06 Scenarios              │
│   07 Workshop               │
├────────────────────────────┤
│  OTHER ENGAGEMENTS    ▾     │   ← collapsed by default
└────────────────────────────┘
```

### Key behaviours
- **Portfolio link** at top always navigates to `/ci/portfolio`.
- **Active engagement** shows the user's currently-selected engagement (the v7 design canon's "active engagement" concept). If none selected, this section shows an "Open an engagement" empty state.
- **7 stages** render with: stage number (01–07), label, state glyph (✓ complete, ▶ current, blank = future). Click navigates to `/ci/engagements/:id/:stage`.
- **Skip-ahead is visually disabled** — clicking a stage > current+1 doesn't navigate (the FSM in Z3 would reject; the UI reflects that by not letting the user try).
- **Back-track is enabled** — earlier stages are clickable, showing a small "←" cursor on hover.
- **Other engagements** is a collapsed disclosure showing engagement cards with name + workshop date.
- **ZS theme aware** — uses `var(--color-accent)` / `var(--color-ink-3)` etc. so it renders correctly under any of the three themes (zs / dark / light).
- **Headless data** — accepts engagement data via props; no direct API calls (F3/F4 wire it).

### Mapping stage strings to LifecycleStage
Mirrors the Z3 enum verbatim — same 7 strings, same order.

## Acceptance tests
1. **Renders 7 stage rows** with correct numbering 01–07.
2. **Current stage gets the `▶ data-current=true` marker**.
3. **Completed stages get a `✓ data-complete=true` marker**.
4. **Skip-ahead disabled** — clicking a future stage > current+1 does NOT fire onStageSelect.
5. **Back-track enabled** — clicking a past stage DOES fire onStageSelect.
6. **Portfolio link fires onPortfolioSelect**.
7. **Empty state** when no active engagement.
8. **ARIA** — sidebar is `<nav>` with `aria-label="Engagement navigation"`; stage list is `<ol>`; current stage has `aria-current="step"`.

## Out of scope (drift guard)
- No API wiring (F3 wires).
- No real routing transitions; component takes callbacks (`onStageSelect`, `onPortfolioSelect`).
- No re-skinning of the existing `/ci` page yet — that's F4.

## Files
- NEW `frontend/src/components/layout/EngagementSidebar.tsx`
- NEW `frontend/__tests__/layout/EngagementSidebar.test.tsx`
