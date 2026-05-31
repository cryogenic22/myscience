/**
 * D1 — CIPage migration lint.
 *
 * Static file scan to pin the post-migration contract on CIPage. Avoids
 * the heavy mock setup that rendering the full page would need (every
 * tab pulls in its own data layer). What we actually care about — no hex
 * codes, no theme override, no hard borders — is testable from the
 * source text directly.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const CI_PAGE_PATH = resolve(__dirname, '../../src/pages/CIPage.tsx');
const SOURCE = readFileSync(CI_PAGE_PATH, 'utf-8');

// Strip TypeScript / TSX comments so a "// Loop #16 — fix #5a5f69 leak"
// note doesn't trip the lint. Keep this conservative — only strip
// line and block comments, not strings.
function stripComments(src: string): string {
  return src
    // /* ... */ block comments
    .replace(/\/\*[\s\S]*?\*\//g, '')
    // // ... line comments
    .replace(/(^|[^:])\/\/[^\n]*/g, '$1');
}

const CODE = stripComments(SOURCE);

describe('CIPage migration — D1 contract', () => {
  it('contains zero hardcoded hex color codes', () => {
    // Match #rgb, #rrggbb, #rrggbbaa. Word boundary at end so #FF in
    // numbers isn't matched.
    const matches = CODE.match(/#[0-9a-fA-F]{3,8}\b/g) || [];
    expect(matches).toEqual([]);
  });

  it('does not hardcode data-theme on any element', () => {
    expect(CODE).not.toMatch(/data-theme\s*=/);
  });

  it('does not use border-r / border-l / border-t / border-b utilities', () => {
    // Hard-border anti-pattern from the pre-D1 version.
    const matches = CODE.match(/\bborder-(r|l|t|b)\b/g) || [];
    expect(matches).toEqual([]);
  });

  it('imports the D1 shell primitives', () => {
    // Positive assertion — the migration actually uses them.
    expect(CODE).toMatch(/from\s+['"]\.\.\/components\/layout\/CockpitShell['"]/);
    expect(CODE).toMatch(/from\s+['"]\.\.\/components\/layout\/NavRail['"]/);
    expect(CODE).toMatch(/from\s+['"]\.\.\/components\/layout\/NavRailItem['"]/);
    expect(CODE).toMatch(/from\s+['"]\.\.\/components\/layout\/ContentRegion['"]/);
    expect(CODE).toMatch(/from\s+['"]\.\.\/components\/layout\/CockpitMobileNav['"]/);
  });

  it('uses --font-display / --font-mono tokens, not hardcoded font names', () => {
    // The pre-D1 code referenced 'Instrument Serif' + 'JetBrains Mono'
    // which are not loaded — that's the visual regression that broke
    // sidebar typography.
    expect(CODE).not.toMatch(/'Instrument Serif'/);
    expect(CODE).not.toMatch(/'JetBrains Mono'/);
    // Token-resolved family used instead.
    expect(CODE).toMatch(/var\(--font-display\)/);
    expect(CODE).toMatch(/var\(--font-mono\)/);
  });

  it('D1.5 — agent activity feed is NOT imported into the sidebar', () => {
    // User feedback (post-D1): Sentinel/Strategist/Curator dominated the
    // navigation and added visual weight without earning it. They'll
    // resurface in a dedicated agent surface later. For now: gone from
    // the cockpit sidebar.
    expect(CODE).not.toMatch(/AgentActivityFeed/);
    expect(CODE).not.toMatch(/AgentIdentityStrip/);
    expect(CODE).not.toMatch(/useAgentActivity/);
    expect(CODE).not.toMatch(/CIPageAgentSection/);
  });

  it('preserves all 8 tab behaviours (no functional regression)', () => {
    // Quick smoke — every tab key from the pre-D1 ALL_TABS list still
    // appears in the file. If the refactor accidentally dropped one,
    // this fires before any user reports a missing tab.
    for (const key of ['inbox', 'digest', 'signals', 'watchlist',
                       'rooms', 'decisions', 'insights', 'reviewer']) {
      expect(CODE).toContain(`'${key}'`);
    }
  });
});
