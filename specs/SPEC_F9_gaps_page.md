# SPEC F9 — GapsPage (between Dossier and Scenarios)

*Bucket 3 (Frontend IA) loop 8. 30 May 2026.*

## Problem
Riya's structural correction: **intelligence gaps belong between Dossier and Scenarios, not on the Decisions page as a post-mortem**. After the dossier is assembled and synthesised, the engagement lead reviews what's *missing* — ranked by strategic importance from the Z5 priority matrix — and decides how to address each gap before scenarios are run.

## Contract

New component `frontend/src/pages/GapsPage.tsx` (headless).

### The gap object
```typescript
interface Gap {
  id: string;
  domain: DossierDomain;
  importance: 'critical' | 'high' | 'medium';   // inherits domain's priority
  question: string;                              // the unanswered question
  expectedSourceClass?: string;                  // where it would come from
  remediation: 'primary_research' | 'accept_uncertainty' | 'descope' | 'pending';
  remediationNote?: string;
  blocksScenarios?: string[];                    // scenario IDs that depend on this gap
}
```

### Sections (top-to-bottom)
1. **Header** — total gap count, blocking-count (gaps that block ≥1 scenario), unresolved-count.
2. **Importance filter** — pills for critical / high / medium (multi-select).
3. **Gaps list** — grouped by importance. Each gap = card with:
   - Importance badge (color-coded)
   - Domain pill
   - Question
   - Expected source class (when known)
   - Remediation pill — current state with three action buttons (primary research · accept uncertainty · descope) for pending gaps
   - "Blocks: scenario A, scenario C" line when present
4. **Readiness banner** — if any critical gap is pending, render a banner: "N critical gaps unresolved · workshop readiness blocked". Green calm state when zero critical pending.
5. **Footer** — "Mark stage complete" CTA, disabled if critical gaps unresolved.

### Props
```typescript
interface Props {
  scope: { engagementName: string; focalAsset: string };
  gaps: Gap[];
  onSetRemediation: (gapId: string, remediation: Gap['remediation'], note?: string) => void;
  onMarkComplete: () => void;
}
```

### Behaviour
- **Workshop-blocking rule**: if any critical gap has `remediation === 'pending'`, "Mark stage complete" is disabled and the banner is red.
- **Remediation actions** fire `onSetRemediation` with the new state.
- **Empty gaps** → "All caught — no unresolved gaps" calm state (intentional contrast to F3's "all clear").
- ARIA: `<main aria-label="Intelligence Gaps">`, gap list is `<ul role="list">`.

## Acceptance tests
1. Header shows total/blocking/unresolved counts.
2. Importance filter has 3 pills; clicking filters the list.
3. Each gap card renders importance badge, domain, question, remediation state.
4. Pending gap shows 3 action buttons (primary research / accept uncertainty / descope).
5. Clicking an action button fires `onSetRemediation(gapId, action)`.
6. Critical pending gap → red banner "N critical gaps unresolved".
7. No critical pending → green "ready" banner.
8. "Mark stage complete" disabled when critical-pending > 0.
9. Empty gaps → "All caught" placeholder.
10. ARIA: main + role list.

## Out of scope
- No actual primary-research workflow trigger (just fire the callback).
- No "blocks scenarios" deep link.

## Files
- NEW `frontend/src/pages/GapsPage.tsx`
- NEW `frontend/__tests__/pages/GapsPage.test.tsx`
