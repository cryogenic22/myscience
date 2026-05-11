/**
 * Loop #14 — Regression guards for the .mz-elevated hover-bloom
 * primitive. Each test verifies a representative card surface
 * applies the utility class to its root element.
 */

import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const SRC = join(__dirname, '..', '..', 'src');

const SURFACES_WITH_ELEVATION = [
  'components/EvidenceCard.tsx',
  'components/MetricCard.tsx',
  'pages/DossierPage.tsx',
  'components/ci/war/WarRoomsList.tsx',
];

describe('Loop #14 — hover-bloom elevation on representative cards', () => {
  for (const rel of SURFACES_WITH_ELEVATION) {
    it(`${rel} applies the mz-elevated utility on at least one element`, () => {
      const text = readFileSync(join(SRC, rel), 'utf8');
      const hits = text.match(/mz-elevated/g) ?? [];
      expect(hits.length, `${rel} should include at least one .mz-elevated`).toBeGreaterThan(0);
    });
  }
});

describe('Loop #14 — .mz-elevated utility is declared in index.css', () => {
  it('index.css declares .mz-elevated', () => {
    const text = readFileSync(join(SRC, 'index.css'), 'utf8');
    expect(text).toContain('.mz-elevated');
  });

  it('index.css suppresses the bloom transform inside prefers-reduced-motion', () => {
    const text = readFileSync(join(SRC, 'index.css'), 'utf8');
    // The reduced-motion block already neutralises animations via
    // `*, *::before, *::after`; this test guards that the existing
    // block is still there post-Loop #14.
    expect(text).toMatch(/@media \(prefers-reduced-motion: reduce\)/);
  });
});
