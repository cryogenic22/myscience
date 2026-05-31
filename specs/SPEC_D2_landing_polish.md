# SPEC D2 — Landing page polish

*Loop D, Increment 2. User feedback after D1/D1.5: "main landing page is
still constrained around buttons. look at the buttons and text boxes
with borders." This loop applies the D1 discipline to the landing.*

## Problem

LandingPage already uses CSS variables (`var(--color-bg)` etc.) — token
discipline is in place. The visible "constrained" feeling comes from
**borders everywhere**:

| Where | Pattern |
|---|---|
| Sticky header | `border-b` separating from hero |
| Hero "INTELLIGENCE PLATFORM" badge | `border` + `borderColor: var(--color-accent-soft)` |
| Metrics strip | `border-y` (top + bottom) wrapping the whole strip |
| Each metric column | `border-r` between cells |
| Each pillar card | `border` class **plus** `boxShadow: var(--shadow-md)` |
| Footer | `border-t` |

Every visible region is fenced. Spotify/Gemini/Helix-three-zeta separate
via tone-shift + spacing + shadow — never 1px lines.

## Decision

Strip the borders. Replace each with the appropriate token-driven idiom:

1. **Header** — drop `border-b`. The `var(--color-surface)` background
   already tone-shifts from the page bg; the backdrop-blur + sticky
   behavior already differentiates it on scroll.
2. **Hero badge** — drop `border` class + `borderColor`. Keep the
   accent-soft background; that's enough indication. Soft pill.
3. **Metrics strip** — drop `border-y` and the per-column `border-r`.
   Separation via `var(--color-surface-2)` tone-shift from the page bg.
   Internal columns separated by spacing (no lines).
4. **Pillar cards** — drop the `border` class. Keep `boxShadow` (soften
   to `var(--shadow-sm)`). Shadow alone = floating-card idiom.
5. **Footer** — drop `border-t`. Just spacing.

Buttons stay pill-shaped (already good); soften their shadows and bring
the secondary "Launch CI Cockpit" button to a less-dominant color (the
solid orange is loud against a cream page).

## Acceptance test

Single static lint in `__tests__/pages/LandingPage.migration.test.ts`:

```ts
test('acceptance — LandingPage has zero hard borders', () => {
  // No border-r, border-l, border-t, border-b, border-x, border-y utilities.
  expect(CODE).not.toMatch(/\bborder-(r|l|t|b|x|y)\b/);
  // No standalone `border` class (the implicit 1px-solid pattern).
  // (className context must be exact — avoid matching "border-radius" etc.)
  expect(CODE).not.toMatch(/className=["'][^"']*\bborder\b[^-]/);
  // No `borderColor` inline style anywhere (implies a border is drawn).
  expect(CODE).not.toMatch(/borderColor\s*:/);
});
```

## Out of scope (Loop D3+)

- WorkspacePage, BridgePage, DossierPage migration (own loop)
- A reusable `Card` primitive (deferred — Loop D3 if a second card surface
  appears that wants the same shape)
- Animation tuning (Framer Motion stays as-is)
- Stats text scaling (the 4xl/5xl on metrics is fine)

## Red-team checklist

1. **Lint guard** — the acceptance test is a regression net; any future
   PR that adds `border-*` utility or `borderColor` inline fails.
2. **No behaviour change** — onEnter/onSearch/onCI still wired; Counter
   animations still work; useHealthStats still drives metrics.
3. **Theme compatibility** — `var(--color-surface)` and
   `var(--color-surface-2)` already redefined in all 3 themes (dark/zs/
   light), so the tone-shift works across them.

## File plan

| File | Why |
|---|---|
| `specs/SPEC_D2_landing_polish.md` | This SPEC |
| `frontend/src/pages/LandingPage.tsx` | Border-strip refactor |
| `frontend/__tests__/pages/LandingPage.migration.test.ts` | Lint regression net |
