# SPEC F7 — DossierPage with 8 ZS domains + visual elements

*Bucket 3 (Frontend IA) loop 6. 30 May 2026.*

## Problem
F7 is stage 3 of the engagement lifecycle — the dossier itself. Per Riya's feedback: each ZS domain should render with the priority pill from the Z5 matrix, a small set of typed facts (with fact-class glyphs ◇/◆/◈/✦), and a visual element where one belongs (patient-journey flow for Disease & Patient, side-by-side competitor table for Competitive, payer landscape grid for Pricing & Access). The dossier is **a read** of the underlying facts, not a static document.

## Contract

New component `frontend/src/pages/DossierPage.tsx` (headless).

### Page structure
1. **Header** — stage label, focal asset, completeness summary, last refresh.
2. **Domain TOC** — horizontal row of 8 small chips (one per ZS domain), each with the priority pill, fact count, and "✓ complete" / "◇ in progress" / "✗ gap" state. Click jumps to the domain section.
3. **Domain sections** (8 stacked) — each with:
   - Sticky sub-header: domain title, priority pill, fact count.
   - **Visual element** for the visual-eligible domains:
     - `disease_and_patient` → patient-journey flow (4 stages: At-risk → Seeking care → Diagnosed → On therapy)
     - `competitive` → side-by-side competitor table
     - `pricing_and_access` → payer-landscape grid
   - **Facts list** — each fact rendered with its class glyph + claim + source pill.
4. **Footer** — "Mark stage complete →" CTA.

### Props
```typescript
interface Props {
  scope: { focalAsset: string; engagementName: string };
  domains: DomainView[];           // length 8
  onJumpToDomain: (domain: DossierDomain) => void;
  onOpenFact: (factId: string) => void;
  onMarkComplete: () => void;
}

interface DomainView {
  domain: DossierDomain;          // one of the 8
  priority: 'critical' | 'high' | 'medium';
  state: 'complete' | 'in_progress' | 'gap';
  facts: { id: string; claim: string; factClass: 'reference'|'corporate'|'signal'|'inferred'; sourceLabel: string }[];
  // Visual data (only present for visual-eligible domains)
  patientJourney?: { stage: string; count: number; note: string }[]; // 4 entries
  competitors?: { name: string; benchmark: string; status: string }[];
  payers?: { name: string; tier: string; restriction: string }[];
}
```

### Behaviour
- **Fact-class glyphs**: ◇ reference (teal), ◆ corporate (orange), ◈ signal (sage/green), ✦ inferred (rose). Inline before the claim text.
- **Empty domain** → "No facts yet — return to Sources stage" placeholder.
- **Patient journey** renders as a 4-stage horizontal flow with arrows between stages.
- **Competitor table** — 3-4 rows side-by-side.
- **Payer landscape** — small grid of (payer × tier × restriction) cells.
- ARIA: `<main aria-label="Dossier">`, each domain section is `<section aria-labelledby="domain-X">`.

## Acceptance tests
1. Renders 8 domain TOC chips with priority pills + fact counts.
2. Clicking a TOC chip fires `onJumpToDomain` with the right enum.
3. Each domain section shows its title + priority pill + facts.
4. **Disease & Patient** domain renders the 4-stage patient journey flow when `patientJourney` is provided.
5. **Competitive** domain renders the competitor table when `competitors` is provided.
6. **Pricing & Access** domain renders the payer landscape when `payers` is provided.
7. Each fact gets its class glyph (◇/◆/◈/✦) based on `factClass`.
8. Clicking a fact fires `onOpenFact(factId)`.
9. Empty domain shows the "return to Sources" placeholder.
10. "Mark stage complete" CTA fires `onMarkComplete`.
11. ARIA: main landmark, sections with `aria-labelledby`.

## Out of scope
- No API.
- No editing (read-only this loop).
- No live fact-refresh chips (F12 / spine Phase B wires those).

## Files
- NEW `frontend/src/pages/DossierPage.tsx`
- NEW `frontend/__tests__/pages/DossierPage.test.tsx`
