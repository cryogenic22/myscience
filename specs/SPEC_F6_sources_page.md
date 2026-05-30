# SPEC F6 — SourcesPage with named outlets + real article URLs

*Bucket 3 (Frontend IA) loop 5. 30 May 2026.*

## Problem
Riya's catch: the v7 Sources view showed abstract "source classes" without named outlets or article-level links. She named the real industry list: **Fierce Pharma, pharmaphorum, BioPharma Dive, Business Wire, PR Newswire, GlobeNewswire, Eli Lilly press, Drugs.com, iSpot, MM+M.** F6 is the stage-2 page that renders the source register at named-outlet granularity, with each signal-bearing source linking to its real article when available.

## Contract

New component `frontend/src/pages/SourcesPage.tsx` (headless).

### Sections (top-to-bottom)
1. **Header** — engagement scope reminder + completeness ratio (`covered / total`).
2. **Source class grid** — 7 source classes (from `Helix Engine Design` §2.1) as tiles, each showing the named outlets connected vs gaps. Status pill: ✓ connected / ⚠ partial / ✗ gap.
3. **Named outlets table** — every outlet by class, with columns: outlet name, class, access type (free / paid / mixed / internal), refresh cadence, status, **"latest article" link** (clickable when available; muted when absent).
4. **Gap actions** — for sources marked gap, a "Plan primary research" affordance opens the planning interface (stub for this loop).

### Props
```typescript
interface Props {
  scope: { focalAsset: string; engagementName: string };
  classes: {
    id: 'regulatory_api' | 'scientific_literature' | 'corporate_filings'
      | 'corporate_communications' | 'scientific_presentations'
      | 'payer_pricing' | 'internal_documents';
    label: string;
    connected: number;
    total: number;
  }[];
  outlets: {
    id: string;
    name: string;
    classId: string;
    access: 'free' | 'paid' | 'mixed' | 'internal';
    cadence: string;       // human-readable: 'daily', 'weekly', 'on event'
    status: 'connected' | 'partial' | 'gap';
    latestArticle?: { title: string; url: string; publishedAt: string } | null;
  }[];
  onPlanResearch: (outletId: string) => void;
  onOpenArticle: (outletId: string, url: string) => void;
}
```

### Behaviour
- **Source-class tile** colour: connected = green tone, partial = amber, gap = red. Click cycles a filter on the outlets table below.
- **Latest article link** opens the real URL (external; the page just fires `onOpenArticle` and lets the caller decide target).
- **Gap row** gets the "Plan primary research" CTA inline.
- **Empty outlets** for a class → a placeholder row "No outlets configured. Add one →" (stub).
- **ARIA**: `<main aria-label="Sources and Gaps">`, outlets are a `<table>` with column headers.

## Acceptance tests
1. Header shows `engagementName` and completeness `covered/total` (sum across classes).
2. 7 source class tiles render with `data-class` attribute and a status pill.
3. Click on a class tile filters the outlets table to that class (fires internal state).
4. Named outlets table renders all rows with name, class label, access type, cadence, status.
5. Outlet with `latestArticle` renders a clickable link; clicking fires `onOpenArticle(outletId, url)`.
6. Outlet without `latestArticle` renders a muted "—" placeholder, not an empty cell.
7. Gap-status outlets show a "Plan primary research" button; click fires `onPlanResearch(outletId)`.
8. Empty class shows "No outlets configured" placeholder.
9. ARIA: main landmark named "Sources and Gaps"; table has proper column headers.

## Out of scope
- No API wiring.
- No actual research-planning flow (just fire the callback).
- No add-outlet flow (placeholder text only).

## Files
- NEW `frontend/src/pages/SourcesPage.tsx`
- NEW `frontend/__tests__/pages/SourcesPage.test.tsx`
