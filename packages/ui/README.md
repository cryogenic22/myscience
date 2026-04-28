# @pulse/ui

Shared component primitives for PulseAction.AI apps.

## Install (workspace)

```ts
// package.json of any app
"dependencies": { "@pulse/ui": "workspace:*", "@pulse/design-tokens": "workspace:*" }
```

## Use

```tsx
import { Card, Pill, ScoreTile, KbqTag, CitationPill } from '@pulse/ui';
import '@pulse/ui/styles.css'; // imports tokens too
```

## Develop

```bash
pnpm --filter @pulse/ui storybook       # http://localhost:6006
pnpm --filter @pulse/ui test            # vitest run
pnpm --filter @pulse/ui build           # tsc --noEmit
```

## Rules

- Every primitive has: a `.tsx` file, a `.stories.tsx`, and a `.test.tsx`.
- Every primitive imports tokens via CSS variables — never hard-coded color/font/spacing.
- Public API surface lives in `src/index.ts`. Don't deep-import from app code.
- Storybook is the canonical docs surface. Stories must show: default, primary variants, gallery (when multiple options exist), interactive states.

## Phase 0 / M0 set

- `<Card>` — universal composition primitive (flat | elevated | interactive)
- `<Pill>` — small label (tone × size, subtle option)
- `<KbqTag>` — KBQ membership marker
- `<CitationPill>` — inline source citation `[edgar:0]` style
- `<ScoreTile>` — one big number + short label (Apple Health/Oura "score" pattern)

## Phase 1 backlog

`<SignalCard>` · `<EvidenceStack>` · `<ConflictBadge>` · `<EntityChip>` ·
`<TimeRangeSelector>` · `<CommandPalette>` · `<KeyboardHint>` · `<DataTable>` ·
`<Sheet>` · `<EmptyState>` · `<FreshnessIndicator>`
