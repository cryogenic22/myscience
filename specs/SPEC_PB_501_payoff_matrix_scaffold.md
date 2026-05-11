# PB-501 — Payoff matrix scaffold (Loop #7)

**Status:** Shipped 2026-05-11 (scaffold only — backend composer BE-8 unmerged)
**Type:** feature
**Priority:** high
**Owner:** frontend-claude (scaffold) · backend-claude (BE-8, PR #59)
**Source:** `docs/PRODUCT_BACKLOG.md` PB-501
**Source ref:** `design-review-output/enhancement-backlog.md` E5.S5.1
**Closes:** Phase 5 finding G4 (frontend half).

## Why

E5 is the WOW surface. The 2×2 payoff matrix is the canonical visual:
analyst sees the strategist's recommendation in one glance — green
win, amber neutral, red lose, brand-accent outline on the recommended
cell. The 1,200-Monte-Carlo posterior already lives in
`services/game_theory.py::run_bayesian()`. BE-8 composes it into a
matrix; this loop renders it.

## Scope of this loop

PB-501 only — the matrix view component, mounted above the existing
move-selector flow inside `WarRoomView`.

**Out of scope** (own PB items):
- PB-502 — adversary digital twins side panel
- PB-503 — live cockpit route with strategist thinking-stream
- PB-504 — 5-level authority spectrum
- PB-505 — delegated "run while I sleep"

## What ships

1. **`PayoffMatrix`** component
   (`frontend/src/components/ci/war/PayoffMatrix.tsx`):
   2×2 table with row + col labels, tier-coloured cells, delta% +
   confidence per cell, brand-accent outline + "Recommended" caption
   on the optimal cell, empty-state message when no scenarios exist.
2. **`usePayoffMatrix(roomId)`** hook
   (`frontend/src/hooks/usePayoffMatrix.ts`): mock fixture today;
   one-line swap to `POST /war-rooms/{id}/payoff-matrix` when BE-8
   ships.
3. **Wire-format types** in `src/types/payoff.ts` (`PayoffMatrix`,
   `PayoffRow`, `PayoffCol`, `PayoffCell`, `PayoffOutcome`).
4. **Mount inside `WarRoomView`** via a small `PayoffMatrixSection`
   helper at the bottom of the file — placed directly above
   `MoveSuggestions` so the recommended option is the first thing
   the analyst sees.
5. **Mock-data banner** as in PB-301 — a one-line `role="status"`
   line reads "Showing placeholder data — backend composer (BE-8,
   PR #59) is not yet merged." Banner is gated on
   `data.is_mock === true`.

## Tests

`frontend/__tests__/ci/war/PayoffMatrix.test.tsx` — 9 cases:
- heading
- row + col labels unique
- signed delta% per cell
- confidence % per cell
- `data-outcome` attribute carries tier
- `data-recommended="true"` on the optimal cell
- mock banner present while `is_mock`
- mock banner hidden when `is_mock === false`
- "No scenarios yet" empty state for zero cells

## Quality gate

- `npx tsc --noEmit` → clean
- `npx vitest run --no-file-parallelism` → **317 passing, 22 todo, 0
  failures** (46 files; +9 over Loop #6)

## How to land BE-8 cleanly

When PR #59 merges:
1. Open `src/hooks/usePayoffMatrix.ts`.
2. Replace the body of `fetchPayoffMatrix` with the
   `TODO(BE-8 / PR #59)` block (POST call shown verbatim).
3. Delete the `buildMockMatrix` helper.
4. Drop `is_mock` from `src/types/payoff.ts`. The banner gate in
   `PayoffMatrix.tsx` becomes dead code and can be deleted.
