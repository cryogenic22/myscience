# UI Changelog

Append-only log of every frontend surface change. **Antigravity writes; Claude
reads at the start of every session.**

Format per entry: `## YYYY-MM-DD` then sections `### Surfaces`,
`### New components`, `### Backend dependencies` (link to API_CHANGELOG entries
this depends on), `### Open issues`. Omit empty sections.

Screenshots of material visual changes live under `docs/screenshots/`.

---

## 2026-05-11 (Loop #13 — delete the `!important` legacy slate block)

Closes root cause #8 from the Loop #11 audit. The 150-line "LEGACY
COMPATIBILITY" block in `index.css` that mapped Tailwind `slate-*`
classes to design tokens via the high-precedence flag was the
single biggest reason the "ugly + squished" feeling persisted — it
shadowed every design-token utility with hardcoded slate alphas,
making the system unfixable from the token layer.

### What changed

- **244 substitutions across 9 component files**: every Tailwind
  `slate-*` colour class migrated to its design-token equivalent
  (`bg-surface-2`, `text-ink-3`, `border-line`, …). The token
  utilities are not declared in our CSS — Tailwind v4
  auto-generates them from the `@theme` declarations.
- **`index.css`: 165 lines removed**, 45+ `!important` declarations
  gone. The one load-bearing rule (`.workspace-canvas` body font)
  is kept. Production CSS bundle shrank **5 KB** (68 → 63 KB).
- **Heaviest migrators**: `GraphExplorer.tsx` (112), `ChatMessage.tsx`
  (78), `EvidenceCard.tsx` (13), `ConversationSidebar.tsx` (12),
  `MetricCard.tsx` (11).
- **Only remaining `!important` rules** are 7 inside
  `@media (prefers-reduced-motion: reduce)` — WCAG-compliant
  user-preference overrides; intentional.

### Codemod

`scripts/migrate_slate_classes.py` — pure-Python regex rewriter.
Idempotent. Default path `frontend/src`. Skips `__tests__`/`test`/
`dist`. Checked in alongside Loop #12's `migrate_text_sizes.py` so
the design-system migration tooling lives next to the codebase it
maintains.

### Regression guard

`__tests__/design-system/loop13-no-slate.test.ts`:

- One test per `.tsx`/`.ts` file under `src/` (~140 cases) asserts
  zero `slate-*` colour classes.
- One test asserts zero `.text-slate-*` / `.bg-slate-*` selectors
  in `index.css`.
- One test asserts zero `!important` outside the reduced-motion
  block.

### Quality gate

- `npx tsc --noEmit` → clean
- `npx vite build` → 62.93 KB CSS (–5 KB), 1.26 MB JS
- `npx vitest run --no-file-parallelism` → **503 passing, 22 todo,
  0 failures** (54 files; +144 from per-file Loop #13 tests +10
  over Loop #12).
- 6-route HTTP smoke on dev server → all 200

### Spec

`specs/SPEC_LOOP_13_delete_legacy_slate.md` — Status: **Shipped 2026-05-11**.

---

## 2026-05-11 (Loop #12 — type-scale migration: pages + visible primitives)

Loop #11 shipped the type scale; this loop puts it to work. Migrated
all six top-level page files plus four cross-page primitives. The
remaining ~46 deep component files keep their `text-[Npx]` for now
(filed as Loop #13b follow-up; the codemod is checked in and ready).

### Scale changes

- Added `mz-text-sm-2` (13px), `mz-text-md-2` (16px),
  `mz-text-lg-2` (20px), `mz-text-xl-2` (24px) so the codemod can
  do exact 1:1 substitutions instead of rounding.
- `mz-text-xl/display/hero` no longer bundle `font-family:
  var(--font-display)`. Scale classes are now pure size + leading
  + (for big sizes) letter-spacing. Callers pair them with
  `font-display` / `font-mono` to pick the family explicitly. This
  makes the codemod safe.

### Surfaces touched

| File | Substitutions |
|---|---|
| `pages/LandingPage.tsx` | 1 (hero CTA → `mz-text-hero`) |
| `pages/CIPage.tsx` | 5 |
| `pages/SearchPage.tsx` | 5 |
| `pages/ConnectorsPage.tsx` | 5 |
| `pages/WorkspacePage.tsx`, `NewWorkspace.tsx` | 0 (already clean) |
| `components/layout/TopBar.tsx` | 2 |
| `components/MetricCard.tsx` | 6 |
| `components/EvidenceCard.tsx` | 8 |
| `components/primitives/AgentStatusBar.tsx` | 0 (Tailwind named sizes) |

32 substitutions across 10 files in total.

### Codemod

`scripts/migrate_text_sizes.py` — pure-Python idempotent substring
rewriter. Run as `python -m scripts.migrate_text_sizes [PATH ...]`.
Default path `frontend/src`. Skips `__tests__`/`test`/`dist`. Checked
in so Loop #13b can finish the deep-component migration in one
command.

### Drive-by

`DossierPage.CenteredMessage` (the loading / error / 404 panel) now
declares `font-display` explicitly — its `mz-text-xl` heading would
have silently lost the display font when the scale unbundled.

### Quality gate

- `npx tsc --noEmit` → clean
- `npx vitest run --no-file-parallelism` → **359 passing, 22 todo,
  0 failures** (53 files; +10 over Loop #11).

### Regression guard

`__tests__/design-system/loop12-type-scale.test.ts` reads the 10
migrated files as text and asserts zero `text-[Npx]` remains. If a
future change reintroduces an arbitrary size on any of these
surfaces, the test fails loudly.

### Spec

`specs/SPEC_LOOP_12_type_scale_migration.md` — Status: **Shipped 2026-05-11**.

---

## 2026-05-11 (Loop #11 — design system fixup)

User feedback: "the whole UI is looking quite ugly with font types
and the borders across feeling squished." Audited the cascade and
found eight root causes spanning `index.html`, `index.css`, and the
four surfaces I shipped in Loops 6–10. Six of the eight are fixed
in this loop; the remaining two are filed for separate follow-ups.

### Six fixes

| # | Fix |
|---|---|
| A | **Fraunces canonical.** Was `--font-display: 'Syne', 'Fraunces', …`; now `'Fraunces', Georgia, …`. Syne dropped from `index.html`. Every `font-serif` (which resolves to Georgia) in my recent surfaces migrated to `font-display` (the new utility that resolves to `--font-display`). |
| B | **Borderless surfaces.** Dropped `1px solid var(--color-line)` from DossierPage column dividers, PayoffMatrix outer card, and the war-room Strategy group. Spotify/Oura model: background-elevation tiers (`--color-bg` → `--color-surface` → `--color-surface-2`) do the separation. `--color-divider` reserved for the one place we need a horizontal rule (app top-bar / body boundary). |
| C | **Spacing scaled up.** Padding/gap bumped to token values (24px panel pad, 16px gap, 32px between major sections). Border-radius normalised to `--radius-card`/`--radius-panel`/`--radius-pill`. |
| D | **Type scale.** New `mz-text-xs/sm/base/md/lg/xl/display/hero` utilities replace ad-hoc `text-[10px]…text-[28px]`. The big-heading utilities (`xl/display/hero`) bundle font-display + display line-height + negative letter-spacing; smaller utilities are pure size and compose with any font family. |
| E | **No more global tracking squeeze.** Removed `letter-spacing: -0.01em` from `html`. Tracking now only on display headings via the scale. |
| F | **Regression guards.** `__tests__/design-system/loop11-regression.test.tsx` pins down: H1 must use `font-display`, PayoffMatrix must not ship a `1px solid` border, DossierPage H1 must use the `mz-text-display` scale class. |

### Surfaces touched

- `pages/DossierPage.tsx` — H1 uses Fraunces; left+right rails on
  surface-2 tier; synthesis on surface; 32px header padding; 70ch
  measure on the synthesis paragraph.
- `components/ci/war/PayoffMatrix.tsx` — borderless; cells have
  `border-spacing: 8px` for air; recommended cell uses
  `inset box-shadow` not `border` so no layout shift; numbers
  rendered in Fraunces.
- `components/ci/war/WarRoomView.tsx` Strategy group — borderless,
  sits on surface-2, 24px padding, `--radius-panel` corners.
- `components/primitives/AgentIdentityStrip.tsx` — `text-[10/12px]`
  → `mz-text-xs/sm`; tighter tracking on the role line.

### Quality gate

- `npx tsc --noEmit` → clean
- `npx vitest run --no-file-parallelism` → **349 passing, 22 todo,
  0 failures** (52 files; +4 over Loop #10).
- `python -m scripts.validate_product_backlog` → OK

### Out of scope (filed)

- The 50-line `!important` legacy Tailwind-slate override block in
  `index.css` (root cause #8) — needs coordinated TSX migration.
- Migrating every component in the codebase to the type scale —
  only the four surfaces I shipped in Loops 6–10 are migrated here.
- Hover-bloom elevation shadows (Spotify pattern) — separate
  primitive.

### Spec

`specs/SPEC_LOOP_11_design_system_fixup.md` — Status: **Shipped 2026-05-11**.

---

## 2026-05-11 (Loop #10 — UI integration pass)

Targeted polish so Loops 5–9's surfaces read as one app, not five
strangers.

### Four changes

- **CI cockpit sidebar** — retired the legacy `AgentStatusBar`
  mount. The named-agent strip from Loop #8 is the canonical
  identity surface now; the static "Flywheel Active · 4 Agents
  Active" label was redundant.
- **`DossierPage` shared chrome** — added the 52px app header bar
  used by `ConnectorsPage` (back button → `/ci`, `PRODUCT_NAME`,
  vertical separator, "Dossier" breadcrumb, right-aligned
  `ThemeToggle`). Inner entity-name header demoted from `<header>`
  to `<div>` so AT announce one banner per page.
- **War-room Strategy group** — payoff matrix + autonomous move
  suggestions + move selector consolidated into one bordered
  `<section aria-label="Strategy">` with an uppercase heading and a
  caption ("Strategist · payoff matrix · move"). `PayoffMatrix`
  dropped its own outer card border so it integrates as a
  sub-section.
- **Strategist tint on the recommended payoff cell** — caption
  reads "Strategist recommends" (not generic "Recommended") with
  the violet `AGENTS.strategist.rgb` and a matching cell border, so
  the eye reads recommended → Strategist rather than recommended →
  generic accent.

### Drive-by

`src/test/setup.ts` gained a `window.matchMedia` shim so any test
mounting `ThemeProvider` works in jsdom. Side benefit: closed the
intermittent flake in `DecisionWorkspace.test.tsx` cmd+enter test
that surfaced in Loops 8–9.

### Quality gate

- `npx tsc --noEmit` → clean
- `npx vitest run --no-file-parallelism` → **345 passing, 22 todo,
  0 failures** (51 files; +6 over Loop #9; the previously-flaky
  cmd+enter test now passes consistently).
- `python -m scripts.validate_product_backlog` → OK

### Out of scope (filed for follow-ups)

- Sentinel tint on signal cards · Curator tint on evidence rows
- Cockpit-style chrome on `/search`, `/workspace`, `/newui`
- Replacing `AgentStatusBar` in `LandingPage` + `SensingFeed`
  (different status semantics, not the cockpit redundancy)

### Spec

`specs/SPEC_LOOP_10_ui_integration.md` — Status: **Shipped
2026-05-11**.

---

## 2026-05-11 (Loop #9 — swap PB-301 + PB-501 from mock to live BE)

Backend trio (BE-3 PR #50, BE-6 PR #57, BE-8 PR #59) merged earlier
today. Loop #9 pointed the two scaffold-loop hooks at their real
endpoints and dropped the "Showing placeholder data — backend
composer not yet merged" banners.

### Surfaces

- **`/dossier/:entityType/:slug`** — `useDossier` now hits
  `GET /dossier/{type}/{slug}` (the BE-6 composer). The component
  shape is unchanged; an adapter (`adaptDossierResponse`) maps the
  backend response onto the frontend `Dossier` type. Banner removed.
- **War room payoff matrix** — `usePayoffMatrix` now POSTs to
  `/war-rooms/{id}/payoff-matrix` (the BE-8 composer) with default
  `our_moves: ['launch_q3', 'wait_q4']` × `adversary_states:
  ['defend', 'cede']` and `samples: 1200`. `adaptPayoffResponse`
  reshapes the backend's 2D `cells[][]` + index-pair recommendation
  into the flat frontend shape and derives win/neutral/lose outcome
  tiers from `delta_pct`. Banner removed.

### New adapter functions

```
src/hooks/useDossier.ts          + adaptDossierResponse(wire, slug)
src/hooks/usePayoffMatrix.ts     + adaptPayoffResponse(wire, roomId,
                                                       ourMoves, adversaryStates)
```

Both exported for unit testing.

### Types

`Dossier` and `PayoffMatrix` lose the frontend-only `is_mock` field;
the banner gates in `DossierPage.tsx` and `PayoffMatrix.tsx` are gone.

### Tests

- 8 new cases in `__tests__/hooks/useDossier.adapter.test.ts`
  (entity name/slug, identity-field partitioning, synthesis
  null/text, evidence rename + tier default, watcher count).
- 7 new cases in `__tests__/hooks/usePayoffMatrix.adapter.test.ts`
  (2D→flat reshape, row/col labels, recommended pair, outcome
  derivation, null recommended, dimension validation).
- 3 banner-related tests removed from existing
  `DossierPage.test.tsx` + `PayoffMatrix.test.tsx`; all remaining
  tests still pass.

### Why BE-3 didn't trigger a swap

BE-3 added an `agent` field on `/agent/events` to unblock PB-202
(live activity feed), not PB-201. The agent identity strip from
Loop #8 is a static surface and was already correct.

### Quality gate

- `npx tsc --noEmit` → clean
- `npx vitest run --no-file-parallelism` → **339 passing, 22 todo,
  0 failures attributable to this loop** (50 files; +2 over Loop #8).
- `python -m scripts.validate_product_backlog` → OK

### Spec

`specs/SPEC_LOOP_9_swap_mocks_to_real.md` — Status: **Shipped
2026-05-11**.

---

## 2026-05-11 (PB-201 — Agent identity strip; Loop #8 closed)

The three named agents are now visible across the CI cockpit
sidebar. Replaces the opaque "Flywheel Active · 4 Agents Active"
label with three glyphs the analyst can address by name:

- **Sentinel** (SE · teal · *Sense*) — the watchdog
- **Strategist** (ST · violet · *Frame · Simulate*) — the planner
- **Curator** (CU · green · *Learn · Recalibrate*) — the librarian

Phase 8 verification mandates the noun form; aria-labels and
visible role lines use nouns throughout.

### Surfaces

- **CI cockpit sidebar** — `<AgentIdentityStrip />` now sits above
  the legacy `AgentStatusBar` in the global telemetry footer of
  `CIPage`. Three glyphs in fixed order, each with name + role.
  Strip wraps gracefully on narrower viewports via `flex-wrap`.

### New primitives

```
frontend/src/components/primitives/
├── AgentGlyph.tsx          — 28×28 tinted badge + 2-letter mark
│                              + optional status dot
└── AgentIdentityStrip.tsx  — fixed-order row of 3 agents +
                                 role="group" / aria-label
```

`AgentGlyph` exports the canonical `AGENTS` metadata map so other
surfaces (workspace chat, war rooms, dossier) can consume the same
names + roles + tints.

### Tests

- `AgentGlyph.test.tsx` — 7 cases (SE/ST/CU letters + aria-labels,
  noun-form guard, `showLabel` on/off, `status` dot).
- `AgentIdentityStrip.test.tsx` — 4 cases (fixed order, names
  visible, role lines, `role="group"` with aria-label).

### Out of scope (own PB items)

- PB-202 — live activity feed via `GET /agents/stream` SSE (BE-4)
- PB-203 — addressable nudges per agent
- PB-204 — failed / paused state visibility

When PB-202 lands and SSE wires real per-agent state, the legacy
`AgentStatusBar` "X Agents Active" label can be retired in favour
of `AgentIdentityStrip` with live statuses.

### Why this loop pivoted from PB-401

PB-401 (TipTap brief composer) needs ~10 transitive packages
installed + custom-mark TDD — too large for a continuation pass.
PB-201 is similarly-sized to Loops 5–7 and keeps the rhythm.

### Quality gate

- `npx tsc --noEmit` → clean
- `npx vitest run --no-file-parallelism` → **328 passing, 22 todo,
  0 failures** (48 files; +11 over Loop #7)

### Spec

`specs/SPEC_PB_201_agent_identity_strip.md` — Status: **Shipped
2026-05-11**.

---

## 2026-05-11 (PB-501 — Payoff matrix scaffold; Loop #7 closed)

First WOW-surface visual of E5. A 2×2 payoff matrix renders inside
each war room above the move-selector flow: tier-coloured cells
(win green / neutral amber / lose red), delta% + confidence per
cell, brand-accent outline + "Recommended" caption on the optimal
cell.

### Surfaces

- **`PayoffMatrix`** component
  (`frontend/src/components/ci/war/PayoffMatrix.tsx`) renders a
  `<table>` with row + col labels, one cell per (row, col) pair,
  tier-coloured background, signed delta%, integer confidence%,
  recommended outline. Empty state ("No scenarios yet — add
  adversary moves and your options to populate the matrix.")
  when the matrix has no rows or cols.
- **`WarRoomView`** mounts the matrix above `MoveSuggestions` so
  the recommended option is the first thing the analyst sees.
- **Mock-data banner** at the top of the matrix card reads
  "Showing placeholder data — backend composer (BE-8, PR #59) is
  not yet merged" while `data.is_mock === true`.

### New files

```
frontend/src/components/ci/war/PayoffMatrix.tsx  — 2×2 grid
frontend/src/hooks/usePayoffMatrix.ts             — fetch hook
                                                    (mock today)
frontend/src/types/payoff.ts                       — wire-format DTOs
frontend/__tests__/ci/war/PayoffMatrix.test.tsx   — 9 cases
```

### Out of scope (own PB items)

- PB-502 — adversary twins posterior side panel
- PB-503 — full live cockpit route with thinking-stream
- PB-504 — 5-level authority spectrum
- PB-505 — delegated "run while I sleep"

### Quality gate

- `npx tsc --noEmit` → clean
- `npx vitest run --no-file-parallelism` → **317 passing, 22 todo,
  0 failures** (46 files; +9 over Loop #6)

### Spec

`specs/SPEC_PB_501_payoff_matrix_scaffold.md` — Status: **Shipped
2026-05-11**.

---

## 2026-05-11 (PB-301 — Entity dossier scaffold; Loop #6 closed)

First shippable surface of E3 (the spine). New route
`/dossier/:entityType/:slug` renders a three-column scaffold
(identity rail · synthesis main · evidence pile) so analysts can
preview the experience while the backend composer (BE-6, PR #57)
finishes review.

### Surfaces

- **New route** `/dossier/:entityType/:slug` for entity types
  `drug`, `company`, `mechanism`, `trial`, `therapeutic_area`.
- **`DossierPage`** component renders:
  - Header — entity name (Fraunces 28px), type chip, last-updated
    timestamp.
  - Left rail — aliases, external IDs (e.g. `rxnorm`, `chembl`),
    primary attributes; collapsed sections hide when empty.
  - Synthesis main — serif 16px paragraph from
    `services/llm.py::synthesize_dossier()` or a "Synthesis
    pending" italic placeholder.
  - Evidence pile — up to three rows (source · tier · date ·
    2-line snippet) with a "+N more" affordance when more exist.
- **Mock-data banner** — top `role="status"` line reads "Showing
  placeholder data — backend composer (BE-6, PR #57) is not yet
  merged" while `data.is_mock === true`. Banner disappears
  automatically once BE-6 lands and the field is dropped.

### New files

```
frontend/src/pages/DossierPage.tsx          — three-column scaffold
frontend/src/hooks/useDossier.ts             — fetch hook (mock today,
                                                real fetch in 1 line)
frontend/src/types/dossier.ts                — wire-format DTOs
frontend/__tests__/pages/DossierPage.test.tsx — 9 cases
```

### Out of scope (own PB items)

- PB-302 — inline citations in synthesis (blocked by PB-603)
- PB-303 — recent-moves timeline
- PB-304 — full EvidenceCard pile (blocked by PB-101)
- PB-305 — watching analysts + add-to-watchlist (blocked by PB-102)

### Quality gate

- `npx tsc --noEmit` → clean
- `npx vitest run --no-file-parallelism` → **308 passing, 22 todo,
  0 failures** (45 files; +9 over Loop #5)
- `python -m scripts.validate_product_backlog` → OK

### Spec

`specs/SPEC_PB_301_dossier_scaffold.md` — Status: **Shipped
2026-05-11**.

---

## 2026-05-11 (PB-104 — Multi-select KBQ chips; Loop #5 closed)

Two-hour bug fix from the design-review heuristic findings (H2,
high). The Signals DB KBQ chip filter went from single-select to
additive multi-select with URL persistence.

### Surfaces

- **`SignalsTab`** — clicking a KBQ chip now toggles its membership
  in the filter set instead of clearing all other selections. The
  "All" chip clears the array (active iff no chips are selected).
  Selection is mirrored to `?kbq=financial,regulatory` in the URL
  via `useSearchParams` so it survives reload and shareable links.
- **`KBQFilter`** primitive — props changed from
  `selected: string | null` to `selected: string[]` and
  `onSelect: (next: string[]) => void`. Adds `aria-pressed` per
  chip and `role="group"` on the container so screen readers track
  multi-select state correctly.

### Backend (additive, non-breaking)

`GET /signals?kbq=financial,regulatory` now accepts a comma-separated
list of KBQ tags and returns any signal whose `kbq_tags` overlaps any
of them (PG `&&` array-overlap). Whitespace and duplicates are
stripped. An empty-after-strip CSV is treated as no filter. The
single-value form (`?kbq=clinical`) is unchanged.

### Tests

- `frontend/__tests__/ci/KBQFilter.test.tsx` — 7 cases (empty state,
  multi-select active state, additive add, remove, "All" clears,
  aria-pressed).
- `tests/test_signals_api.py` — 3 new cases (CSV any-of match,
  whitespace stripping, empty-after-strip no-op). Pre-existing
  single-value test still passes.
- Full vitest run after the change: **299 passing, 22 todo, 0
  failures** (44 files).

### Quality gate

- `npx tsc --noEmit` → clean
- `npx vitest run --no-file-parallelism` → 299 / 0 / 22 todo
- `python -m pytest tests/test_signals_api.py -v` → 20 / 20
- `python -m pytest tests/test_product_backlog.py -v` → 14 / 14
- `python -m scripts.validate_product_backlog` → OK
  (regenerator now idempotent after fixing duplicate `## Currently
  in flight` section bug)

### Spec

`specs/SPEC_PB_104_multiselect_kbq_chips.md` — Status: **Shipped
2026-05-11**.

---

## 2026-05-09 (SPEC-042 — Centralized Product Backlog + repo doc cleanup; Loop #3 closed)

Pure docs / process loop. **No code surfaces touched, no API changes, no
frontend behavioral changes.** Shipped because the planning surface had
fragmented across 4 partially-overlapping backlog files and the repo
had accumulated 158 stale .md documents. Result: a single canonical
product backlog + a clean docs tree.

### What shipped

- **`docs/PRODUCT_BACKLOG.md`** — 76 PB-NNN items consolidated from
  `BACKLOG.md`, `ROADMAP.md`, `docs/backlog.md`, and the open asks in
  `docs/AGENT_BACKLOG.md`. Front-of-file dashboard with status counts
  (regenerable via `--regenerate-summary`). 7-state taxonomy:
  `proposed | triaged | blocked | in-progress | shipped | archived | wontfix`.
- **`scripts/validate_product_backlog.py`** — schema validator + dashboard
  regenerator. Exits 0 if every PB item has all required fields, IDs are
  unique, cross-references resolve.
- **`scripts/migrate_legacy_backlogs.py`** — one-shot migration helper
  (idempotent; re-runnable). Pure functions; library tests cover Phase
  skipping + agent-ask filtering.
- **`tests/test_product_backlog.py`** — 14 pytest cases covering schema,
  uniqueness, cross-refs, dashboard regeneration, migration, archive
  redirects.
- **`docs/archive/`** new directory tree with 158 archived files across
  6 categories (brainstorms, communications, reports, benchmarks,
  superseded-specs, legacy-backlogs). Each archived file has a 1-line
  redirect header at its original path pointing readers at the canonical
  successor.

### What got archived

| Category | Count | What |
|---|---|---|
| `brainstorms/` | 7 | Pre-Phase F vision rough drafts (Feb–Mar 2026) |
| `communications/` | 2 | `dev_2_lead.md`, `comp_intelligence.md` |
| `reports/` | 7 | One-time test/analysis reports |
| `benchmarks/` | 98 | Auto-generated `benchmark/reports/eval-*.md` |
| `superseded-specs/` | 40 | SPEC_001–SPEC_018 series + drafts (HARNESS_AUDIT, SESSION_REPORT, EXECUTION_PLAN, etc.) |
| `legacy-backlogs/` | 4 | `BACKLOG.md`, `ROADMAP.md`, `docs/backlog.md`, `docs/product_backlog_research_and_intelligence.md` |
| **Total** | **158** | |

### What stayed put (active)

- `CLAUDE.md`, `AGENTS.md`, `lead_notes_4_dev.md` (strategic, still
  referenced)
- `docs/AGENT_BACKLOG.md`, `docs/UI_CHANGELOG.md`, `docs/API_CHANGELOG.md`
- `feedback/*` (cron-managed)
- `frontend/README.md`, `harness/*`, `.claude/*`
- All current specs `SPEC_019` and newer (47 specs remain at `specs/`)
- `specs/CI_Agent_Reimagined_Spec.md` (north-star)
- `specs/SPEC_021_decision_flywheel.md` (still useful context)

### Quality gate

- `python -m scripts.validate_product_backlog` — clean
- `python -m pytest tests/test_product_backlog.py -v` — **14/14**

### Stage 5 red-team / Stage 6 fix-all

- 0 blockers
- 3 majors filed; 2 closed in Stage 6 (`AGENTS.md:211` redirect, `MEMORY.md`
  pointer); **M3 deferred by design** — the 74 migrated items need a
  triage pass to demote already-shipped items to `Status: shipped` and
  collapse duplicates. That's the next loop.

### Spec

`specs/SPEC_042_centralized_product_backlog.md` — Status: **Shipped
2026-05-09**.

### What's next

Per the user's directive ("then follow the rigor of working on the loop
step by step through the backlog"), Loop #4 begins by triaging the
74 unfiltered PB-rows: collapsing duplicates, demoting already-shipped
items to `Status: shipped` with the closing commit SHA, and assigning
`Owner` + `Priority` per remaining item. After triage, work begins on
the highest-priority `triaged` item.

---

## 2026-05-09 (SPEC-041 — User Feedback Loop; Loop #2 closed)

In-app feedback widget visible on every authenticated surface.
Captures bugs / issues / enhancements / features / data-quality /
data-request submissions, auto-attaches a privacy-filtered diagnostic
bundle (recent console errors + failed-fetch metadata + viewport +
theme + density + route), supports paste / drag screenshots, and
persists submissions to the existing `feedback_entries` table.
Triage runs on a 45-minute cron via three new slash commands.

### Surfaces

- **Floating "Feedback" pill** — bottom-right on every authenticated
  surface, bottom-LEFT on `/workspace` to clear the chat send button
  (Q4 sign-off). Hidden on `/`, `/login`, and when
  `localStorage.mz_feedback_disabled === 'true'`. Click dispatches
  `mz:open-feedback`.
- **Chat-style submission panel** — opens on `mz:open-feedback`.
  State machine: `greeting → category_selected →
  description_provided → priority_selected → confirmed →
  submitted | error`. 6 categories (bug / issue / enhancement /
  feature / data_quality / data_request). Esc closes; sessionStorage
  preserves the in-progress draft so an accidental Esc does not lose
  work. Tab is trapped inside the dialog (WCAG 2.4.3); initial focus
  lands on close button.
- **PII-filtered diagnostics** — `installDiagnostics()` runs once at
  App mount, wrapping `console.error` + `globalThis.fetch` (and
  `window.error` / `unhandledrejection`). URL search params with
  sensitive names (`token`, `api_key`, `authorization`, etc.) are
  redacted; bodies have JWTs and 32+-char alphanumeric runs scrubbed
  before truncation to 500 chars. Ring buffers cap at 50 entries each
  (FIFO eviction). Cleared after a successful submit.

### New components

```
frontend/src/components/feedback/
├── FeedbackButton.tsx       — floating pill (route-aware, theme-aware)
└── FeedbackWidget.tsx       — chat panel + state machine + draft persistence

frontend/src/lib/
└── diagnostics.ts            — install / collect / clear + PII redaction
```

`frontend/src/api.ts` extended with SPEC_041 types
(`FeedbackCategory`, `FeedbackPriority`, `FeedbackStatus`,
`FeedbackEntry`, `FeedbackCreateBody`, `FeedbackDiagnosticContext`,
`FeedbackEntityContext`, `FeedbackAttachment`,
`FeedbackListResponse`, `FeedbackStatsResponse`) +
`feedbackApi` (`submit` / `list` / `update` / `stats` / `remove`).

### Repo-level new files

```
feedback/
├── live_user_feedback.md   — append-only chronological tracker
├── backlog.jsonl            — machine-readable mirror of the queue
├── sync.sh                   — pulls /feedback?status=new and updates above
├── README.md                 — operator runbook for the loop
└── .gitignore                — ignores screenshots/* + .paused

.claude/commands/
├── triage-feedback.md       — assessment-only slash command
├── process-feedback.md      — full Ralph Loop on Implement items
└── feedback-cron.md          — 45-min cron entry point (sync → triage → safe-fix)
```

### Backend (no new tables — extended existing)

- New endpoint `DELETE /feedback/{id}` (returns 204) for privacy /
  GDPR retraction. Migration 020_feedback_entries.sql + the rest of
  the routes were shipped previously — this loop is purely
  additive.
- `tests/test_feedback_api.py` extended with 2 tests for
  `TestDeleteFeedback`.

### Cron + autonomous triage

- 45-minute cron (registered per-user via the `schedule` skill) runs
  `/feedback-cron`. Auto-fix gate per Q2 sign-off (SPEC_041 §8.1):
  ```
  verdict == 'Implement'
  && category == 'bug'
  && scope_estimate == 'S'
  && labels excludes any of: api, schema, auth, security
  ```
  Items inside the gate get shipped under `chore(feedback-cron):
  <id> <title>` commits (one per item, individually pushed for audit
  + revert friendliness). Items outside the gate stay `triaged` for
  human-driven `/process-feedback`. Pause via
  `touch feedback/.paused`.

### Quality gate

- `npx tsc --noEmit` → clean
- `npx vitest run --no-file-parallelism` → **43 files, 292 tests
  passing, 22 it.todo, zero failures, zero regressions** (was 256
  pre-loop)
- `python -m pytest tests/test_feedback_api.py -v` → **14/14**

### Stage 5 red-team / Stage 6 fix-all

4 majors filed in §13a; all 4 closed:
- M1 (PII filter on diagnostics)
- M2 (focus trap inside widget)
- M3 (sessionStorage draft persistence)
- M4 (`DELETE /feedback/{id}` endpoint + `feedbackApi.remove`)

15 minors + 5 nits deferred to AGENT_BACKLOG with reasons.

### Open issues / follow-ups

- **Admin retraction UI** for `DELETE /feedback/{id}` — currently
  only slash commands call it. Filed.
- **Vitest parallel-mode flakes** in 3 pre-existing primitive tests
  — not introduced by this loop. Filed.
- **15-minor backlog** under `[FRONTEND] SPEC-041 deferred items`.

### Spec

`specs/SPEC_041_user_feedback_loop.md` — Status: **Shipped
2026-05-09**. Loop #2 of the SPEC-029 reskin program is now closed.

---

## 2026-05-09 (SPEC-030 — Decision Workspace v2; Loop #1 closed)

First mini-spec under the SPEC-029 reskin program; first frontend loop
delivered through the 7-stage Ralph Loop process documented in
`docs/runbooks/RALPH_LOOP.md`. Stage 1 (SPEC) → Stage 7 (DEPLOY) all
gates passed.

### Surfaces

- **`/ci?tab=decisions`** — replaces legacy `DecisionsTab` with new
  `BriefsTab` consuming `GET /decision-briefs` (cursor-paginated).
  Linear-style row anatomy: state-glyph + question (truncate-on-row,
  full-on-hover) + meta (trigger / horizon / option count / evidence
  refs). Keyboard: `j/k` navigate, `return` open, `n` new brief,
  `?` keyboard help, `esc` close any modal.
- **`/ci/decisions/:id`** — replaces legacy `DecisionDetailPage` with
  new 5-panel `DecisionWorkspace` (Brief / Evidence / Simulation /
  Recommendation / Reasoning Trace drawer). Reads `mz_density`
  (default `spacious`); compact mode halves `--space-*` tokens via
  `[data-density="compact"]` scope. Keyboard: `t` trace toggle,
  `g e/s/r` focus a panel, `cmd+enter` advance state, `esc` close.
- **`/ci/legacy-decisions/:id`** — explicit legacy escape hatch for
  the SPEC-021 `DecisionDetailPage` (committed → outcome capture flow).
  Reachable directly or via `localStorage.mz_legacy_decisions === 'true'`
  globally.

### State machine — first-class affordances

All 8 SPEC-023 brief states render with shape-glyph + color-token +
state-aware affordance per SPEC-030 §8.3:
`draft → human_review → simulation_pending → simulation_complete →
decision_pending → committed → in_review → closed`. New chip palette
in `--color-state-*` tokens (light + dark, AA-contrast verified).

### New components

```
frontend/src/components/ci/decisions/
├── BriefsTab.tsx              — list view (Linear-style)
├── DecisionWorkspace.tsx      — 5-panel composite
├── BriefPanel.tsx             — top: question + state chip + options
├── EvidencePanel.tsx          — left: refs grouped by type
├── SimulationPanel.tsx        — center: scenario / Monte Carlo /
│                                war-game (SPEC-032 placeholder)
├── RecommendationPanel.tsx    — right: top option + counter +
│                                rank disclaimer + commit CTA
├── ReasoningTraceDrawer.tsx   — Sentry-style timeline drawer
├── StateMachineChip.tsx       — pill + popover; nextForwardTransition
│                                helper; STATE_META + ALLOWED_TRANSITIONS
├── BriefEditableField.tsx     — Stripe-style inline-edit primitive
└── OptionEditor.tsx           — modal: add/edit/delete option
```

`frontend/src/api.ts` extended with `decisionBriefsApi` (list, get,
create, patch, archive, addOption, removeOption, transition) +
all SPEC-023 types (`BriefState`, `EvidenceRef`, `DecisionBrief`,
`DecisionBriefList`, etc.).

### Design tokens added

`frontend/src/index.css`: state-machine palette
(`--color-state-{draft,review,sim,decide,committed,review-out,closed}`),
density tokens (`--space-panel-pad/-gap/-row-gap`), per-panel shadow
(`--shadow-workspace-panel`), `[data-density="compact"]` halving
scope. Global `@media (prefers-reduced-motion: reduce)` block
neutralizes animation/transition durations and decorative transforms.

### Quality gate (Stage 4 + 6 + 7)

- `npm run build` → clean (1.23 MB JS / 67 KB CSS, 1m02s)
- `npx tsc --noEmit` → clean
- `npx vitest run` → **39 test files, 256 cases passing, 19 it.todo,
  zero failures, zero regressions** (was 240 before Stage 5; +16
  regression cases added in Stage 6)

### Stage 5 red-team / Stage 6 fix-all

13 actionable findings (5 blockers, 8 majors). Closed in Stage 6:
- All 5 blockers: contrast tokens (light + dark), Tab-reachable list
  rows, keyboard-activatable inline edit, forward-only `cmd+enter`.
- 7 of 8 majors: `prefers-reduced-motion`, save-error inline alerts,
  `simulation_complete` copy fix, announce-storm suppressed, drawer
  focus trap, 401 → `mz:auth-expired` event + redirect, "Top option"
  / "Counter option" labels with rank disclaimer.
- 1 major deferred (#12 Drawer primitive reuse — anti-slop, filed in
  AGENT_BACKLOG with reason).
- 12 minor + 5 nit items deferred to AGENT_BACKLOG with one-liner
  reasons.

### Backend dependencies

- `GET /decision-briefs` (list, cursor pagination)
- `GET /decision-briefs/{brief_id}` (full)
- `POST /decision-briefs` (create draft)
- `PATCH /decision-briefs/{brief_id}` (edit; draft/human_review only)
- `DELETE /decision-briefs/{brief_id}` (archive)
- `POST /decision-briefs/{brief_id}/options` (add)
- `DELETE /decision-briefs/{brief_id}/options/{id}` (remove)
- `POST /decision-briefs/{brief_id}/transitions` (advance state)

All shipped by backend Claude on 2026-05-09 (SPEC-023). See
`docs/API_CHANGELOG.md` for the corresponding entry.

### Backend asks (filed in `docs/AGENT_BACKLOG.md`)

- `[BACKEND]` `POST /decisions/from-brief?brief_id={id}` — mints a
  `decision_id` on commit (Q2 sign-off). Until shipped, "Commit
  decision" button renders disabled with tooltip.
- `[BACKEND]` `materiality_factors` JSONB shape on `/signals` items.
- `[BACKEND]` War-game adversary preview helper (SPEC-032).
- `[BACKEND]` Decision calibration time-series endpoint.

### Open issues / follow-ups

- **`/login` surface for `?session=expired` banner.** `App.tsx` now
  redirects on 401 but landing-page banner is the missing piece.
  Filed.
- **Lighthouse a11y on changed surfaces (light + dark, ≥95).** Stage
  5 environment had no headless Chromium; deferred to a deploy gate
  follow-up. Filed.
- **12 minor + 5 nit red-team items** — see `[FRONTEND] SPEC-030
  deferred items` in AGENT_BACKLOG.

### Spec

`specs/SPEC_030_decision_workspace_v2.md` — Status: **Shipped
2026-05-09**. Closes Loop #1 of SPEC-029. Loop #2 (SPEC-032
War-Game Multi-Adversary UI) opens next.

---

## 2026-05-09

### Surfaces
- **AGENTS.md protocol adopted.** All UI changes from this date forward will
  be logged here.

### Backend dependencies
- See `docs/API_CHANGELOG.md` for the corresponding entry.

### Open issues
- **InboxTab login wall** (filed in `docs/AGENT_BACKLOG.md`). First PR target
  for Antigravity to validate the workflow end-to-end. (RESOLVED)

## 2026-05-09 (Inbox Login Wall Fix)

### Surfaces
- **CIPage**: Default tab for unauthenticated users is now `digest` (which works without auth).
- **InboxTab**: Replaced the login-wall message with a real login CTA + button that routes to `/login`.

## 2026-05-09 (Phase 1 Cockpit Primitives)

### New components
- `MetricRing`: SVG progress indicator with semantic thresholds.
- `Sparkline`: Minimalist SVG line chart for trend visualization.
- `HeroCard`: Elevated component wrapper using Phase F shadows.
- `Timeline`: Vertical chronological list with `framer-motion`.
- `AgentStatusBar`: Live telemetry ticker indicating agent loops.

### Surfaces
- `index.css`: Added Phase F dark theme tokens (`#0d1117`, `#161b22`, etc.) and `Syne` / `DM Mono` typography.

## 2026-05-09 (Phase 2-4 Cockpit Primitives)

### New components
- `ConfidenceBadge`: A primitive to display explicit uncertainty bands and scores.
- `EvidenceAffordance`: A primitive to render deep-linkable evidence chains with source/passage visibility.
- `DisagreementPanel`: A surface for side-by-side agent/source conflict resolution.

### Surfaces
- **Sensing Feed**: Implemented `SensingFeed` as the new Always-On continuous feed.
- **InboxTab**: Replaced the default layout entirely with `SensingFeed`.

## 2026-05-09 (SPEC-023 Sign-off & Main Shell Upgrade)

### Surfaces
- **LandingPage**: Full visual overhaul using Phase F Cockpit design. Added dark glassmorphic components, `AgentStatusBar` telemetry, and dynamic background.
- **CIPage**: Redesigned the main application shell. Replaced horizontal topbar with a dark high-density sidebar. Added global agent telemetry monitoring the Flywheel.

### Cross-Cutting
- Signed off `SPEC_023_decision_briefs.md` for the backend data contract.
