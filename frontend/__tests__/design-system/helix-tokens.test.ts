/**
 * D1.5 — lib/helix.ts must use CSS variables, not hardcoded surface
 * colors or unloaded font names.
 *
 * Was the root cause of the "sidebar light, main dark" theme-split:
 * SensingFeed and SignalCard imported HELIX which hardcoded `#0a0b0e`
 * etc, so they ignored the F1 theme toggle even after CIPage's shell
 * started honoring it.
 *
 * Regression net: any future PR that reintroduces a hex code into the
 * HELIX surface palette (or brings back the unloaded font names) fails
 * here before reaching `main`.
 *
 * Semantic colors (category OKLCH values, IMPACT_TONE, etc.) are NOT
 * locked — they're domain-meaning, not theme.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const SRC = readFileSync(
  resolve(__dirname, '../../src/lib/helix.ts'),
  'utf-8',
);

// Strip comments so doc-explanations of the OLD values don't trip the lint.
function stripComments(src: string): string {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/[^\n]*/g, '$1');
}
const CODE = stripComments(SRC);

describe('lib/helix.ts — D1.5 token discipline', () => {
  it('HELIX surface palette uses CSS variables, not hex literals', () => {
    // Find the HELIX = { ... } block and check no hex within.
    const match = CODE.match(/export const HELIX\s*=\s*\{[\s\S]*?\};/);
    expect(match).not.toBeNull();
    const helixBlock = match![0];
    const hexes = helixBlock.match(/#[0-9a-fA-F]{3,8}\b/g) || [];
    expect(hexes).toEqual([]);
  });

  it('HELIX surface palette uses var(--color-*) tokens', () => {
    const match = CODE.match(/export const HELIX\s*=\s*\{[\s\S]*?\};/);
    const helixBlock = match![0];
    // Positive assertion: token references present.
    expect(helixBlock).toMatch(/var\(--color-bg\)/);
    expect(helixBlock).toMatch(/var\(--color-ink\)/);
    expect(helixBlock).toMatch(/var\(--color-surface\)/);
  });

  it('HELIX font references use loaded families only', () => {
    // 'Instrument Serif' is NOT loaded in index.html. Banned.
    expect(CODE).not.toMatch(/'Instrument Serif'/);
    // 'JetBrains Mono' is also NOT loaded — DM Mono is.
    expect(CODE).not.toMatch(/'JetBrains Mono'/);
    // Tokens used instead.
    expect(CODE).toMatch(/var\(--font-display\)/);
    expect(CODE).toMatch(/var\(--font-mono\)/);
  });

  it('semantic CAT_HUE values remain numeric (NOT tokenized)', () => {
    // Category hues are domain semantics — financial=220, governance=200, etc.
    // They should NOT be replaced with CSS variables; they encode meaning.
    expect(CODE).toMatch(/financial:\s*220/);
    expect(CODE).toMatch(/regulatory:\s*45/);
  });
});
