# Loop #13 — Delete the `!important` legacy slate block

**Status:** Shipped 2026-05-11
**Type:** refactor
**Source:** root cause #8 from the Loop #11 audit; chained from Loop #12

## Why

`index.css` shipped a ~150-line "LEGACY COMPATIBILITY" block that
mapped Tailwind `slate-*` / `bg-white/N` / `shadow-N` / `brand-*`
classes to design tokens via `!important`. CLAUDE.md memory says
**do not use `!important`** because it makes the system unfixable
from the token layer. The block was the single biggest reason the
"ugly + squished" feeling persisted even after the Loop #11 token
work: every design-token utility was being shadowed by these
hardcoded slate values.

## What ships

### Codemod

`scripts/migrate_slate_classes.py` — pure-Python regex rewriter
that maps every Tailwind `slate-*` color class onto the
design-token equivalent that Tailwind v4 auto-generates from the
`@theme` declarations in `index.css`. Mapping:

| Slate | → | Token utility |
|---|---|---|
| `bg-slate-50` (+ alpha variants) | → | `bg-surface-2` |
| `bg-slate-100` | → | `bg-surface-3` |
| `bg-slate-900` | → | `bg-ink` |
| `text-slate-900/800` | → | `text-ink` |
| `text-slate-700` | → | `text-ink-2` |
| `text-slate-600/500` | → | `text-ink-3` |
| `text-slate-400/300` | → | `text-ink-4` |
| `border-slate-100/200/300/700` (+ alpha) | → | `border-line` |
| `border-slate-900` | → | `border-ink` |
| `hover:bg-slate-50/100` | → | `hover:bg-surface-2` |
| `hover:bg-white` | → | `hover:bg-surface` |
| `hover:text-slate-900` | → | `hover:text-ink` |
| `hover:text-slate-600/700` | → | `hover:text-ink-2` |
| `hover:text-slate-300` | → | `hover:text-ink-4` |
| `hover:border-slate-300` | → | `hover:border-line` |
| `divide-slate-200/70` | → | `divide-line` |
| `placeholder:text-slate-400` | → | `placeholder:text-ink-4` |

Idempotent. Skips `__tests__`/`test`/`dist`/`node_modules`.

### Surfaces migrated (244 substitutions across 9 files)

| File | Substitutions |
|---|---|
| `components/GraphExplorer.tsx` | 112 |
| `components/ChatMessage.tsx` | 78 |
| `components/EvidenceCard.tsx` | 13 |
| `components/ConversationSidebar.tsx` | 12 |
| `components/MetricCard.tsx` | 11 |
| `components/EntityCard.tsx` | 8 |
| `components/ui/Pill.tsx` | 5 |
| `components/KnowledgeGraph.tsx` | 3 |
| `components/SuggestedQueries.tsx` | 2 |

### `index.css` cleanup

Lines 733–898 (the entire "LEGACY COMPATIBILITY" section) deleted.
The one rule still load-bearing — body font on `.workspace-canvas`
— kept. Net change:

- **165 lines removed**
- **45+ `!important` declarations removed**
- **5 KB smaller production CSS bundle** (68 KB → 62 KB)
- **Only `!important` remaining**: 7 inside the
  `@media (prefers-reduced-motion: reduce)` block (WCAG-compliant
  user-preference overrides; intentional).

## Tailwind v4 auto-generation

The token utilities (`bg-surface-2`, `text-ink-3`, `border-line`,
etc.) are not declared anywhere in our CSS — Tailwind v4
auto-generates them from the `@theme` color tokens. Verified by
greping `dist/assets/index-*.css`:

```css
.border-line{border-color:var(--color-line)}
.bg-surface-2{background-color:var(--color-surface-2)}
.text-ink{color:var(--color-ink)}
.text-ink-2{color:var(--color-ink-2)}
.text-ink-3{color:var(--color-ink-3)}
.text-ink-4{color:var(--color-ink-4)}
```

## Regression guards

`__tests__/design-system/loop13-no-slate.test.ts`:

- Per-file test: every `.tsx` / `.ts` under `src/` asserts zero
  `(bg|text|border|hover:bg|hover:text|hover:border|divide|placeholder:text)-slate-N`
  occurrences. (~140 individual test cases.)
- `index.css` test 1: zero `.text-slate-*`/`.bg-slate-*`/
  `.border-slate-*` selector overrides.
- `index.css` test 2: zero `!important` outside the
  `prefers-reduced-motion` block.

## Quality gate

- `npx tsc --noEmit` → clean
- `npx vite build` → 62.93 KB CSS (was 68.08 KB), 1,263.49 KB JS
- `npx vitest run --no-file-parallelism` → **503 passing, 22 todo,
  0 failures** (54 files; +144 from the per-file Loop #13 test
  + +10 over Loop #12).
- 6-route HTTP smoke on dev server → all 200
