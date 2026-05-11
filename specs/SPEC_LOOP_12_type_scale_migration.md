# Loop #12 — Type-scale migration (pages + cross-page primitives)

**Status:** Shipped 2026-05-11
**Type:** refactor
**Source:** chained from Loop #11 (the type scale shipped but only the four Loop 6–10 surfaces consumed it)

## Why

The Loop #11 scale was great. The rest of the app still used 406 `text-[Npx]`
arbitrary classes across 56 files, so the inconsistency the user complained
about ("ugly fonts", "squished") persisted on every page that wasn't a
Loop 6–10 surface. This loop migrates the highest-visibility files —
all six top-level pages plus four cross-page primitives — onto the scale.

## What ships

### Token-level

- **Three new size entries** so the codemod can do exact 1:1
  substitutions instead of rounding (which would cause invisible
  visual shifts):
  - `--text-sm-2: 13px` → `mz-text-sm-2`
  - `--text-md-2: 16px` → `mz-text-md-2`
  - `--text-lg-2: 20px` → `mz-text-lg-2`
  - `--text-xl-2: 24px` → `mz-text-xl-2`
- **Scale unbundled** — `mz-text-xl/display/hero` no longer bundle
  `font-family: var(--font-display)`. Sizes are pure size + leading
  + (for big sizes) letter-spacing. Callers explicitly pair them
  with `.font-display` / `.font-mono` to pick the family.

  This makes the codemod safe: rewriting `text-[22px]` to
  `mz-text-xl` no longer silently turns a sans-serif label into a
  serif display heading.

### Codemod

`scripts/migrate_text_sizes.py` — pure-Python substring rewriter.
Conservative size map (`8/9/10/11px → xs`, exact match for the rest),
skips `__tests__`/`test`/`dist`/`node_modules`, idempotent. Run as
`python -m scripts.migrate_text_sizes [PATH ...]`. Default
`frontend/src`. Checked in so future loops can run it.

### Surfaces migrated (10 files, 32 substitutions)

| File | Subs |
|---|---|
| `pages/LandingPage.tsx` | 1 (hero CTA: `lg:text-[84px]` → `mz-text-hero`, hand-migrated) |
| `pages/CIPage.tsx` | 5 |
| `pages/SearchPage.tsx` | 5 |
| `pages/ConnectorsPage.tsx` | 5 |
| `pages/WorkspacePage.tsx` | 0 (no `text-[Npx]` — clean already) |
| `pages/NewWorkspace.tsx` | 0 (no `text-[Npx]` — clean already) |
| `components/primitives/AgentStatusBar.tsx` | 0 (uses Tailwind named sizes) |
| `components/layout/TopBar.tsx` | 2 |
| `components/MetricCard.tsx` | 6 |
| `components/EvidenceCard.tsx` | 8 |

### Regression guard

`__tests__/design-system/loop12-type-scale.test.ts` reads each
migrated file as text and asserts zero `text-\[\d+px\]` matches. If
a future change reintroduces an arbitrary size on these surfaces,
the test fails loudly.

## Quality gate

- `npx tsc --noEmit` → clean
- `npx vitest run --no-file-parallelism` → **359 passing, 22 todo,
  0 failures** (53 files; +10 over Loop #11).
- `python -m scripts.validate_product_backlog` → OK

## Out of scope (filed as Loop #13b follow-up)

~390 `text-[Npx]` occurrences remain across ~46 component files
(deep `ci/*`, `connectors/*`, `chat/*`, `search/*`, `decisions/*`,
`war/*`, etc.). They're tractable with the codemod — most files
just need `python -m scripts.migrate_text_sizes <file>` — but each
needs an eyeball on the diff for context-sensitive sizes. Filed.

## What's next in the chain

Loop #13 — delete the `!important` legacy slate-overrides block
from `index.css` (root cause #8 from the Loop #11 audit). Already
queued in the user-confirmed chain (12 → 13 → 14 → 15).
