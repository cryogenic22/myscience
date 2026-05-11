# Loop #14 — Hover-bloom elevation primitive (`.mz-elevated`)

**Status:** Shipped 2026-05-11
**Type:** feature (design-system primitive)
**Source:** chained from Loop #13 — closes the Spotify/Oura "subtle bloom on hover" pattern referenced in the Loop #11 reference table.

## Why

Loops 11–13 made the surfaces consistent (Fraunces canonical, type
scale applied, no `!important` legacy block). The last visible
piece of the "Spotify/Oura aesthetic target" was the hover bloom —
cards lift a few pixels and pick up a soft shadow on hover. This
loop adds the primitive and applies it to four representative card
surfaces.

## What ships

### Primitive — `index.css`

```css
.mz-elevated {
  transition: transform 220ms var(--motion-out, …),
              box-shadow 220ms var(--motion-out, …);
  will-change: transform;
}
.mz-elevated:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
}
.mz-elevated:active {
  transform: translateY(-1px);
  box-shadow: var(--shadow-sm);
}
```

The existing `@media (prefers-reduced-motion: reduce)` block in
`index.css` neutralises `transition-duration` to `0.001ms` on every
element — so the lift is suppressed automatically for users with
that preference. No extra rule needed.

### Applied to four card surfaces

| File | Card surface |
|---|---|
| `components/EvidenceCard.tsx` | Workspace canvas evidence card |
| `components/MetricCard.tsx` | Workspace metric card |
| `pages/DossierPage.tsx` | Evidence pile rows (right rail) — also wrapped each row in a tinted `--color-surface` background with `var(--radius-card)` corners so the bloom has something to lift |
| `components/ci/war/WarRoomsList.tsx` | Room cards in the war-rooms list |

## Regression guards

`__tests__/design-system/loop14-elevation.test.ts` — 6 cases:

- Each of the 4 surfaces includes the `mz-elevated` class on at
  least one element.
- `index.css` declares `.mz-elevated`.
- `index.css` still has the `@media (prefers-reduced-motion: reduce)`
  block (Loop #14 didn't accidentally remove the WCAG override).

## Quality gate

- `npx tsc --noEmit` → clean
- `npx vitest run --no-file-parallelism` → **509 passing, 22 todo,
  0 failures** (55 files; +6 over Loop #13).
- Bundle size unchanged within rounding (62.93 KB CSS).

## Out of scope (filed)

- Apply `.mz-elevated` to the remaining card-like surfaces across
  the app (signal cards in `SignalsListPanel`, brief cards in
  `BriefsTab`, decision cards in `DecisionsTab`, dossier related
  entities, etc.). Mechanical — can be a quick follow-up loop.
- Loop #15 — PB-401 TipTap brief composer (the last item in the
  user-confirmed 12 → 13 → 14 → 15 chain).
