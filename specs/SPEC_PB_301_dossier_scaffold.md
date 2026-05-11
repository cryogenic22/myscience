# PB-301 — Entity dossier scaffold (Loop #6)

**Status:** Shipped 2026-05-11 (scaffold only — backend composer BE-6 unmerged)
**Type:** feature
**Priority:** high
**Owner:** frontend-claude (this scaffold) · backend-claude (BE-6, PR #57)
**Source:** `docs/PRODUCT_BACKLOG.md` PB-301
**Source ref:** `design-review-output/enhancement-backlog.md` E3.S3.1
**Closes:** Phase 5 finding G1 (frontend half).

## Why now

E3 is the spine surface — the dossier is where signals, briefs,
war-rooms, and the graph all converge on a single entity. The frontend
scaffold can ship ahead of the backend so that when BE-6 (PR #57)
merges, the swap is a one-line change in `useDossier.fetchDossier`.

## Scope of this loop

PB-301 only — the three-column shell + loading/error/404 states.

**Out of scope** (own PB items):
- PB-302 — inline citation rendering in synthesis (depends on PB-603 CitationChip)
- PB-303 — recent-moves timeline (depends on PB-301)
- PB-304 — evidence pile with full evidence cards (depends on PB-101 + PB-301)
- PB-305 — watching analysts + add-to-watchlist (depends on PB-301 + PB-102)

## What ships

1. **Route** `/dossier/:entityType/:slug` registered in `App.tsx`.
   `entityType ∈ {drug, company, mechanism, trial, therapeutic_area}`;
   anything else renders an "Unknown entity type" placeholder.
2. **`DossierPage` component** with three columns:
   - `aside[aria-label="Identity"]` — left rail: aliases, external
     IDs, primary attributes.
   - `main[aria-label="Synthesis"]` — center: serif-headlined
     synthesis paragraph or a "Synthesis pending" italic note.
   - `aside[aria-label="Evidence"]` — right pile: up to three
     evidence rows (source name + tier label + date + 2-line
     snippet) + a "+N more" button when more exist.
3. **`useDossier(entityType, slug)` hook** in `src/hooks/useDossier.ts`.
   Returns `{ data, error, isLoading }`. Currently a mock generator
   keyed by `<type>/<slug>` (only `drug/tirzepatide` is seeded). When
   BE-6 lands the body of `fetchDossier` swaps to a real fetch.
4. **Wire-format types** in `src/types/dossier.ts` (`Dossier`,
   `DossierEntity`, `DossierSynthesis`, `DossierEvidence`,
   `DossierRecentMove`, `DossierWatcher`, `EvidenceTier`,
   `DossierEntityType`).
5. **Mock-data notice** — a one-line `role="status"` banner above
   the header reading "Showing placeholder data — backend composer
   (BE-6, PR #57) is not yet merged." Banner is gated on
   `data.is_mock === true`; drop the `is_mock` field from the wire
   format when BE-6 ships and the banner disappears automatically.

## Tests

`frontend/__tests__/pages/DossierPage.test.tsx` — 9 cases:
- loading state
- error state
- 404 state (`status === 404`)
- entity name + type badge in header
- aliases + external IDs in identity rail
- synthesis summary in center column
- 3 evidence rows + "+N more" affordance when 4 exist
- mock banner present while `is_mock`
- "Synthesis pending" copy when synthesis is null

## Quality gate

- `npx tsc --noEmit` → clean
- `npx vitest run --no-file-parallelism` → **308 passing, 22 todo, 0 failures**
  (45 files; +9 over Loop #5)

## How to land BE-6 cleanly

When PR #57 merges:
1. Open `src/hooks/useDossier.ts`.
2. Replace the body of `fetchDossier` with the call documented in
   the `TODO(BE-6 / PR #57)` block.
3. Delete the `MOCK_FIXTURES` constant + `buildMockKey` helper.
4. Drop `is_mock` from `src/types/dossier.ts`. The banner gate in
   `DossierPage.tsx` becomes dead code and can be deleted.
5. Add an integration test that hits the live endpoint (against a
   mocked DB) verifying the wire format.
