/**
 * Dark-mode token discipline — the primary chat + graph flow must not paint
 * with light-only Tailwind color literals.
 *
 * `bg-white` stays pure white in dark mode (dark mode inverts `--color-surface`
 * to a dark value, but `bg-white` doesn't participate) → white panels float over
 * a dark UI. `text-white` paired with `bg-ink` is worse: `--color-ink` inverts to
 * a LIGHT grey in dark mode, so white text on it becomes invisible.
 *
 * The fix is the token utility (`bg-surface` / `text-surface`), which is white in
 * light mode (identical render) and correctly dark in dark mode. This guard is a
 * regression net: any future PR that reintroduces these literals into the fixed
 * surfaces fails here before `main`. Mirrors __tests__/design-system/helix-tokens.
 *
 * NOT locked here (deliberately out of scope — need visual judgment): the
 * GraphExplorer / KnowledgeGraph dark-slate `rgba(...)` HUD overlays, and
 * `text-white` on accent-colored backgrounds (e.g. WorkspaceRail logo) where
 * white is correct in both themes.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const FILES = [
  'src/components/ChatMessage.tsx',
  'src/components/EntityCard.tsx',
  'src/components/MetricCard.tsx',
  'src/components/EvidenceCard.tsx',
  'src/components/ui/Pill.tsx',
  'src/components/ConversationSidebar.tsx',
  'src/components/graph/EntitySearch.tsx',
  'src/components/SuggestedQueries.tsx',
  'src/components/GraphExplorer.tsx',
];

// Strip comments so a doc-explanation naming the old class can't trip the lint.
function stripComments(src: string): string {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/[^\n]*/g, '$1');
}

// `bg-white`, `bg-white/58`, `text-white`, `text-white/40`, incl. variant
// prefixes like `hover:bg-white`. Word boundary avoids matching `bg-white...`
// that isn't a color class (there are none, but be precise).
const LIGHT_ONLY = /\b(?:bg|text)-white(?:\/\d+)?\b/g;

describe('dark-mode token discipline (chat + graph flow)', () => {
  for (const rel of FILES) {
    it(`${rel} uses surface/ink tokens, not bg-white/text-white literals`, () => {
      const code = stripComments(readFileSync(resolve(__dirname, '../../', rel), 'utf-8'));
      const hits = code.match(LIGHT_ONLY) ?? [];
      expect(hits).toEqual([]);
    });
  }

  it('the fixed surfaces reference the theme tokens (swap direction is correct)', () => {
    const chat = readFileSync(resolve(__dirname, '../../src/components/ChatMessage.tsx'), 'utf-8');
    // The user bubble kept bg-ink but its text must be the inverting token.
    expect(chat).toMatch(/bg-ink[^"'`]*text-surface|text-surface[^"'`]*bg-ink/);
    expect(chat).toMatch(/\bbg-surface\b/);
  });
});
