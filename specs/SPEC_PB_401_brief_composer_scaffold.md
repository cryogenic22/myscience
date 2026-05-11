# PB-401 — Brief composer scaffold (Loop #15)

**Status:** Shipped 2026-05-11 (scaffold only — autosave hits a stub; BE-19 unmerged)
**Type:** feature
**Owner:** frontend-claude (scaffold) · backend-claude (BE-19)
**Source:** `docs/PRODUCT_BACKLOG.md` PB-401, `design-review-output/enhancement-backlog.md` E4.S4.1

## Why

PB-401 was deferred at the end of Loop #8 because TipTap requires
new npm dependencies and warrants a focused loop. This loop installs
TipTap and ships the editor surface + a custom citation mark + a
4s-debounced autosave hook. PB-402–405 (AI suggestions / options
grid / sidebar / migration) build on top.

## What ships

### Dependencies

```
@tiptap/react ^3.23.1
@tiptap/starter-kit ^3.23.1
@tiptap/extension-placeholder ^3.23.1
```

Zero production-only vulnerabilities. JS bundle grows 377 KB
(1,263 → 1,640 KB). PB-403 (in-doc options grid) and PB-405
(migration from legacy DecisionWorkspace) will share this bundle.

### New files

- `src/pages/BriefComposerPage.tsx` — mounts the editor with
  StarterKit + Placeholder + CitationMark; renders shared app
  chrome (back button, app name, "Brief" breadcrumb, ThemeToggle,
  Saving / Saved status, Save button); mock-data banner about
  BE-19 below the chrome; editor surface in a 760px column with
  48px panel padding.
- `src/components/briefs/CitationMark.ts` — TipTap inline mark
  that wraps `{{cite:doc_id}}` tokens. Stores `docId` as
  `data-citation` HTML attribute so consumer code (and tests)
  can find it. Renders inside a `<span class="mz-citation">`.
- `src/hooks/useBriefAutosave.ts` — 4s-debounced autosave hook.
  Returns `{ status: 'idle'|'saving'|'saved'|'error', saveNow }`.
  Today the `persistDraft` function is a stub — when BE-19 lands,
  the `TODO(BE-19)` block in the hook shows the exact one-line
  swap.

### Route

`/briefs/new` registered in `App.tsx`. PB-405 (migration) adds
`/briefs/:id`; that's a separate loop.

### Fixture for the citation chip

`/briefs/new?fixture=cite` loads a doc that includes a citation
mark wrapping `[1]` and bound to `data-citation="doc-1"`. The
regression test verifies the chip renders.

## Out of scope (own PB items)

- PB-402 — inline AI suggestions (Strategist + Curator) — depends
  on BE-7 (`/decision-briefs/{id}/suggest`)
- PB-403 — options grid as in-doc primitive — pure FE
- PB-404 — slim sidebar (stakeholders / materiality / state) —
  depends on PB-103 (materiality drawer)
- PB-405 — migration from legacy `DecisionWorkspace.tsx`

## Tests

`__tests__/pages/BriefComposerPage.test.tsx` — 5 cases:

- Renders chrome with the "Brief" breadcrumb + back button
- Mounts a TipTap editor surface (`contenteditable="true"` element
  exists)
- Mock-data banner about BE-19 is visible
- Save button + autosave indicator (`Saved`) are visible
- `/briefs/new?fixture=cite` renders the citation chip with
  `data-citation="doc-1"`

## Quality gate

- `npx tsc --noEmit` → clean
- `npx vite build` → 63.28 KB CSS / 1,640.55 KB JS (gzip:
  12.67 / 472.93 KB). +377 KB JS is the TipTap cost.
- `npx vitest run --no-file-parallelism` → **517 passing, 22 todo,
  0 failures** (56 files; +8 over Loop #14).

## How to land BE-19 cleanly

When PR #46 (BE-19 — `POST /decision-briefs/{id}`) merges:

1. Open `src/hooks/useBriefAutosave.ts`.
2. Replace the body of `persistDraft` with the `TODO(BE-19)` block
   (real fetch shown verbatim).
3. Remove the mock-data banner from `BriefComposerPage.tsx`.
