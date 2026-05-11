/**
 * Loop #13 — Regression guards: no Tailwind `slate-*` classes anywhere
 * under `src/` and no `!important` rules in `index.css`.
 *
 * These guards close out root cause #8 from the Loop #11 audit
 * (the legacy `!important` slate-overrides block). If a future
 * change reintroduces either, the test fails loudly.
 */

import { describe, it, expect } from 'vitest';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';

const SRC = join(__dirname, '..', '..', 'src');

function walkTsx(root: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(root)) {
    const p = join(root, entry);
    const s = statSync(p);
    if (s.isDirectory()) {
      if (['node_modules', 'test', '__tests__'].includes(entry)) continue;
      out.push(...walkTsx(p));
    } else if (p.endsWith('.tsx') || p.endsWith('.ts')) {
      out.push(p);
    }
  }
  return out;
}

const SLATE_RE = /(?:^|[\s"'`{])(bg|text|border|hover:bg|hover:text|hover:border|divide|placeholder:text)-slate-\d+(?:\/\d+)?(?=[\s"'`}])/g;

describe('Loop #13 — no Tailwind slate-* in src/', () => {
  for (const path of walkTsx(SRC)) {
    const rel = path.slice(SRC.length + 1).replace(/\\/g, '/');
    it(`${rel} uses design-token classes, not slate-*`, () => {
      const text = readFileSync(path, 'utf8');
      const hits = text.match(SLATE_RE) ?? [];
      expect(hits, `Found ${hits.length} slate-* occurrences: ${hits.slice(0, 5).join(' / ')}${hits.length > 5 ? ' …' : ''}`).toEqual([]);
    });
  }
});

describe('Loop #13 — index.css cleanup', () => {
  it('contains no `.text-slate-*` / `.bg-slate-*` / `.border-slate-*` selector overrides', () => {
    const path = join(SRC, 'index.css');
    const text = readFileSync(path, 'utf8');
    const hits = text.match(/\.(?:text|bg|border|hover\\:bg|hover\\:text|hover\\:border|divide|placeholder\\:text)-slate-\d+/g) ?? [];
    expect(hits, `Found ${hits.length} legacy slate selectors: ${hits.slice(0, 5).join(' / ')}`).toEqual([]);
  });

  it('the only `!important` declarations are inside the `prefers-reduced-motion` block (WCAG)', () => {
    const path = join(SRC, 'index.css');
    const text = readFileSync(path, 'utf8');
    // Strip the reduced-motion block before counting.
    const stripped = text.replace(
      /@media \(prefers-reduced-motion: reduce\) \{[\s\S]*?\n\}/g,
      '',
    );
    const hits = stripped.match(/!important/g) ?? [];
    expect(
      hits,
      `Found ${hits.length} !important outside the reduced-motion block — should be 0`,
    ).toEqual([]);
  });
});
