# SPEC F3 — Portfolio page (attention-this-week, not vanity)

*Bucket 3 (Frontend IA) loop 2. 30 May 2026.*

## Problem
v7's portfolio dashboard surfaced four vanity KPIs (facts under management, signals processed last 7 days, decisions committed last quarter, scenarios projected). The Anika critique on v4's Engagement view — *"dashboards are for monitoring something that's running; an engagement is being prepared for"* — applies here too. The Portfolio view's lead should be **"what needs your attention this week"**, not a status report.

## Contract

New component `frontend/src/pages/PortfolioPage.tsx` and a `PortfolioBoard` primitive in `frontend/src/components/portfolio/PortfolioBoard.tsx`.

### Information priority (in order)
1. **Attention-this-week panel** at the top. Three buckets:
   - 🔥 Workshops in ≤ 7 days, with readiness % and a "Open" button.
   - ⚠ Stale evidence in committed decisions (cross-engagement count).
   - ❗ Unresolved high-importance gaps (cross-engagement count).
2. **Engagement cards** — one per active engagement. Each card shows: name, focal asset, situation pill (launch/defense/lcm), workshop date with countdown, current stage, readiness bar (a thin segment that fills as stages complete).
3. **Numbers strip** at the bottom — small, terminal-style: total active / archived / decisions committed (last 30d) / facts asserted (last 7d). These are *reference*, not lead.

### Headless component design
`PortfolioBoard` accepts:
```typescript
interface Props {
  attention: {
    upcomingWorkshops: { engagementId, name, daysUntil, readinessPct }[];
    staleEvidenceCount: number;
    unresolvedGapsCount: number;
  };
  engagements: PortfolioEngagement[];
  stats: { activeCount: number; archivedCount: number; decisionsCommitted30d: number; factsAsserted7d: number; };
  onEngagementOpen: (id: string) => void;
  onWorkshopOpen: (id: string) => void;
  onGapsReview: () => void;
  onStaleEvidenceReview: () => void;
}
```

### Behaviour
- **Critical countdown** (≤ 7 days): orange-tinted with `var(--color-accent)` left rail.
- **Soon** (8–30 days): teal-tinted.
- **Beyond 30 days**: muted.
- **Readiness bar** is the count-of-completed-stages / 7.
- **Zero attention** (nothing this week, no stale, no gaps): renders a calm "All clear — review portfolio below" state rather than three empty buckets.
- **Theme-aware** via CSS vars.

## Acceptance tests
1. **Renders three attention buckets when populated**.
2. **Renders calm "All clear" state when all three are zero**.
3. **Critical countdown card uses the accent color**.
4. **Each engagement card has data-engagement-id**.
5. **Clicking an engagement card fires onEngagementOpen with the right id**.
6. **Clicking a workshop's "Open" button fires onWorkshopOpen**.
7. **Stats strip renders all 4 numbers**.
8. **Readiness bar reflects completed stages / 7**.
9. **ARIA**: page has `<main aria-label="Portfolio">`; engagement cards are `<article>`.

## Out of scope (drift guard)
- No real data wiring (a follow-up loop or F4 wires).
- No engagement creation flow yet (separate loop).

## Files
- NEW `frontend/src/components/portfolio/PortfolioBoard.tsx`
- NEW `frontend/__tests__/portfolio/PortfolioBoard.test.tsx`
