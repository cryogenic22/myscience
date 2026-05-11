# Loop #11 — Design system fixup

**Status:** Shipped 2026-05-11
**Type:** refactor
**Source:** user feedback ("the whole UI is looking quite ugly with font types and the borders across feeling squished")

## Diagnosis (audit summary)

Eight root causes of the "ugly + squished" feeling were identified
across `index.html`, `index.css`, and the four surfaces I shipped in
Loops 6–10:

| # | Root cause | Fix in this loop |
|---|---|---|
| 1 | Tailwind's `font-serif` resolves to Georgia, not Fraunces, and I used it on every recent heading | A — Fraunces canonical + `font-display` utility |
| 2 | `--color-line: rgba(0,0,0,0.06)` makes borders invisible; meanwhile components ship `1px solid var(--color-line)` boxes | B — borderless surfaces, background-elevation tiers |
| 3 | Ad-hoc tight padding (6px / 10px / 12px) ignored the spacing tokens | C — 24px panel pad, 16px gap, 32px between sections |
| 4 | Border-radius mixed across 4 / 6 / 8 / 10 / 12 / 14 / 16 / 18 / 999px | C — `var(--radius-card)` / `var(--radius-panel)` / `var(--radius-pill)` |
| 5 | Font sizes are 12 different arbitrary `text-[Npx]` values | D — `mz-text-xs/sm/base/md/lg/xl/display/hero` scale |
| 6 | Global `letter-spacing: -0.01em` on `html` squeezed body text | E — removed; tracking now only on display headings |
| 7 | Fraunces loaded but referenced by nothing | A — Fraunces becomes the canonical display, Syne dropped |
| 8 | 50+ `!important` Tailwind-slate overrides in `index.css` | **Out of scope** — needs coordinated TSX migration; filed |

## Reference

Three apps cited as aesthetic targets. None of them draw 1px boxes
around panels:

| Pattern | Spotify | Oura | Apple Health |
|---|---|---|---|
| Card separation | Background elevation (3 tiers) | Background elevation (4 tiers) | Background tiers + soft shadows |
| Borders | ~0.06 alpha only on major section breaks | Almost never | Almost never |
| Whitespace | 16–24px between cards | 24–32px panel padding | 16–24px panel padding |
| Hierarchy | Type weight + size | Type + color | Type + chart strokes |

The Loop #11 direction is the hybrid Spotify/Oura model: borderless
panels, background-elevation tiers
(`--color-bg` → `--color-surface` → `--color-surface-2` →
`--color-surface-3`) carry the visual separation, and the explicit
`--color-divider` token is reserved for the one place a horizontal
rule is needed (the app top-bar / body boundary).

## What ships

### Tokens — `frontend/src/index.css`

- Removed the `@import url(.../Syne.../)` line at top — duplicated
  fonts that index.html already loads, and Syne is no longer
  canonical.
- `--font-display: 'Fraunces', Georgia, 'Times New Roman', serif`
  (was `'Syne', 'Fraunces', Georgia, serif`).
- New `--text-xs/sm/base/md/lg/xl/display/hero` size tokens.
- Removed global `letter-spacing: -0.01em` from `html`.
- New utility classes:
  - `.font-display`, `.font-body`, `.font-mono` resolve to the
    `--font-*` variables.
  - `.mz-text-xs/sm/base/md/lg` are pure size+leading; orthogonal to
    font choice.
  - `.mz-text-xl/display/hero` bundle font-display + display
    line-height + negative letter-spacing (convenience for large
    headings).

### Fonts — `frontend/index.html`

- Syne dropped from the Google Fonts URL.
- Fraunces, DM Sans, DM Mono retained.

### Four surfaces migrated

| File | Migration |
|---|---|
| `pages/DossierPage.tsx` | `font-serif` → `font-display mz-text-display` on H1. All inline padding bumped to 24/32/48px tokens. Vertical dividers between columns dropped; left/right rails sit on `--color-surface-2` for tier elevation. Synthesis main keeps `--color-surface`. |
| `components/ci/war/PayoffMatrix.tsx` | `font-serif` → `font-display`. Outer card border dropped (composes inside parent panel). Recommended cell uses `inset box-shadow` instead of `border` — no layout shift on state flip. Cells use `border-collapse: separate; border-spacing: 8px` for air. Padding bumped to 16px. |
| `components/ci/war/WarRoomView.tsx` (Strategy group) | Dropped `1px solid var(--color-line)` outer border; now sits on `--color-surface-2` with `border-radius: var(--radius-panel)` and 24px padding. |
| `components/primitives/AgentIdentityStrip.tsx` | `text-[10px]/text-[12px]` → `mz-text-xs/mz-text-sm`. Tracking tightened. |

## Regression guards

`__tests__/design-system/loop11-regression.test.tsx` — 4 cases:

- DossierPage H1 does **not** use `font-serif` and **does** use `font-display`.
- PayoffMatrix `<h3>` does **not** use `font-serif` and **does** use `font-display`.
- PayoffMatrix root `<section>` ships no `border: 1px solid …` inline style.
- DossierPage H1 uses `mz-text-display` (so future arbitrary `text-[Npx]` regression fails loudly).

## Quality gate

- `npx tsc --noEmit` → clean
- `npx vitest run --no-file-parallelism` → **349 passing, 22 todo,
  0 failures** (52 files; +4 over Loop #10).
- `python -m scripts.validate_product_backlog` → OK

## Out of scope (filed for follow-ups)

- The 50-line `!important` legacy block in `index.css` (root cause #8) — needs a coordinated TSX migration across many files.
- Migrating *every* component in the codebase to the type scale — only the four surfaces I shipped + the surfaces I migrated this loop.
- Replacing `Syne` references in `AgentStatusBar.tsx` and other older components (low priority — those surfaces are scheduled for separate refresh).
- The Spotify/Oura-style elevation-shadow on hover (the "subtle bloom" pattern) — current shadows are static; hover bloom is a separate primitive.
