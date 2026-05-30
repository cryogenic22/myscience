# SPEC F12 — DecisionsPage + facilitator guide

*Bucket 3 (Frontend IA) loop 11 — closes the v7 IA spine. 30 May 2026.*

## Problem
The engagement ends when decisions are committed. F12 is the engagement's output artifact — a committed-decisions ledger, an intelligence gap log (gaps that were accepted as uncertainty, descoped, or remediated), and the **facilitator guide** that turns the next workshop's 3-session structure into a runnable plan (Think Like Competitor 90min / Prioritise Implications 60min / Risk Mitigation 90min).

## Contract

New component `frontend/src/pages/DecisionsPage.tsx` (headless).

### Sections
1. **Header** — engagement scope, summary counts (committed / contingent / parked).
2. **Decision ledger** — each committed decision as a row with owner, timing, scenario, and the evidence chain (clickable to facts).
3. **Intelligence gap log** — gaps grouped by their final disposition (`primary_research` / `accept_uncertainty` / `descope` / `pending`). `Pending` gets a red tag (shouldn't exist post-workshop).
4. **Facilitator guide** — three workshop sessions side-by-side:
   - Think Like Competitor · 90min · agenda, outputs, escalation triggers
   - Prioritise Implications · 60min · ditto
   - Risk Mitigation · 90min · ditto
5. **Export footer** — "Export PDF + JSON" button (audit-grade artifact) and "Close engagement" CTA.

### The objects
```typescript
interface CommittedDecision {
  id: string;
  statement: string;
  owner: string;
  timing: string;                // 'pre-PDUFA' | 'at launch' | 'first 90 days' etc.
  scenarioId: string;
  scenarioName: string;
  evidenceChain: { factId: string; predicate: string }[];
  disposition: 'committed' | 'contingent' | 'parked';
  rationale: string;
}

interface GapLogEntry {
  id: string;
  importance: 'critical' | 'high' | 'medium';
  question: string;
  disposition: 'primary_research' | 'accept_uncertainty' | 'descope' | 'pending';
  remediationNote?: string;
}

interface FacilitatorSession {
  id: 'think_like_competitor' | 'prioritise_implications' | 'risk_mitigation';
  title: string;
  duration: string;              // '90 min'
  agenda: string[];              // bullet list
  outputs: string[];
  escalationTriggers?: string[];
}
```

### Props
```typescript
interface Props {
  scope: { engagementName: string; focalAsset: string };
  decisions: CommittedDecision[];
  gaps: GapLogEntry[];
  sessions: FacilitatorSession[];
  onOpenFact: (factId: string) => void;
  onExportArtifact: () => void;
  onCloseEngagement: () => void;
}
```

### Behaviour
- **Decision rows** grouped by disposition with a colored left rail (committed = green, contingent = amber, parked = muted).
- **Evidence chips** clickable, fire `onOpenFact`.
- **Gap log pending row** renders a red banner-style row "Pending — should be resolved before close."
- **Close engagement** disabled if any gap is pending OR any decision has disposition='contingent' without an owner.
- **Export PDF + JSON** always enabled (audit artifact for any state).
- ARIA: `<main aria-label="Decisions">`, sessions are `<section aria-labelledby>`.

## Acceptance tests
1. Header shows engagement scope + 3 disposition counts (committed/contingent/parked).
2. Each decision row shows statement, owner, timing, scenario, evidence chips.
3. Clicking an evidence chip fires `onOpenFact`.
4. Decisions grouped by disposition with appropriate left-rail tone.
5. Gap log rendered with disposition badges.
6. Pending gap row gets a red warning style.
7. Facilitator guide renders 3 sessions with title, duration, agenda, outputs.
8. Export button fires `onExportArtifact`.
9. Close engagement disabled when any gap is pending.
10. Close engagement enabled when all gaps resolved.
11. ARIA: main + section aria-labelledby + table semantics on decision ledger.

## Out of scope
- No actual PDF generation (callback only).
- No close-engagement FSM transition (callback only; backend Z3 handles).

## Files
- NEW `frontend/src/pages/DecisionsPage.tsx`
- NEW `frontend/__tests__/pages/DecisionsPage.test.tsx`
