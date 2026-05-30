# SPEC F8 — SynthesisPage (surfaces Z2 Insight + rejected_insights)

*Bucket 3 (Frontend IA) loop 7. 30 May 2026.*

## Problem
Z2 made the Insight type a structural invariant (refuses to construct without a fact chain). F8 makes that visible: the analyst sees insights with their **strategic frame** and **fact citations chain**, and — critically — sees **rejected insights** with their rejection reasons. The synthesis test is the load-bearing piece of platform credibility; the UI surfaces it as the audit artifact Priya called out.

## Contract

New component `frontend/src/pages/SynthesisPage.tsx` (headless).

### Sections (top-to-bottom)
1. **Header** — engagement scope, total insights count, rejected count, pass-rate.
2. **Strategic-frame filter** — pills for `risk` / `opportunity` / `assumption` / `trigger` (multi-select; default = all).
3. **Insights list** — each insight as a card showing:
   - Strategic-frame badge (color-coded)
   - Domain pill
   - Statement (the claim)
   - Fact-citations chain — expandable; each citation = `factId · predicate · contribution` line
   - "View fact" affordance per citation that fires `onOpenFact(factId)`
   - Rationale (synthesis_test_rationale) — small italic line
4. **Rejected-insights disclosure** (collapsed by default) — each rejected candidate with: statement attempt, rejection reason, derived_from (if any). The audit artifact.
5. **Footer** — "Mark stage complete" CTA.

### Props
```typescript
interface Props {
  scope: { engagementName: string; focalAsset: string };
  insights: Insight[];
  rejectedInsights: RejectedInsight[];
  onOpenFact: (factId: string) => void;
  onMarkComplete: () => void;
}

interface Insight {
  id: string;
  statement: string;
  strategicFrame: 'risk' | 'opportunity' | 'assumption' | 'trigger';
  domain: string;
  derivedFrom: { factId: string; predicate: string; contribution: string }[];
  synthesisTestRationale: string;
  createdAt?: string;
}

interface RejectedInsight {
  id: string;
  candidateStatement: string;
  rejectionReason: string;
  derivedFrom?: { factId: string; predicate: string; contribution: string }[];
}
```

### Behaviour
- **Frame filter**: clicking a frame pill toggles it; "all" resets.
- **Citation chain** is the load-bearing visible artifact: every insight has ≥1 citation rendered, with the contribution text inline. If an insight has zero citations, render `[!] integrity error — should not occur post-Z2` so the violation surfaces (defence in depth — UI mirrors the type invariant).
- **Frame colors**: risk = red-tinted, opportunity = green-tinted, assumption = amber-tinted, trigger = accent-orange.
- **Rejected count** in header is conspicuous (not buried) — the audit point.
- **Empty insights** → "No insights yet — return to Dossier and run synthesis" placeholder.
- **Empty rejected** → "No rejected candidates" line.
- ARIA: `<main aria-label="Synthesis">`, insights are `<ul role="list">`, rejected disclosure is a `<details>`.

## Acceptance tests
1. Header shows insights + rejected counts + pass-rate.
2. 4 frame pills render; clicking toggles selection.
3. Filter narrows the list (e.g. selecting `risk` hides non-risk insights).
4. Each insight card shows statement, frame badge, domain, ≥1 fact citation.
5. Each citation has `data-fact-id` and clicking fires `onOpenFact(factId)`.
6. Insight with empty `derivedFrom` shows the integrity-error marker (defence in depth).
7. Rejected-insights disclosure exists; expanding shows the list with rejection_reason.
8. Empty insights → placeholder.
9. ARIA: main + `<details>` + frame pills with `aria-pressed`.

## Out of scope
- No API.
- No editing of insights or re-running synthesis (deeper loop).

## Files
- NEW `frontend/src/pages/SynthesisPage.tsx`
- NEW `frontend/__tests__/pages/SynthesisPage.test.tsx`
