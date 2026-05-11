/**
 * Loop #12 — Type-scale regression guards for the migrated surfaces.
 *
 * Each test reads a TSX file as a string and asserts no
 * `text-[Npx]` arbitrary-size class remains. If a future change
 * reintroduces one in the migrated set, the test fails loudly.
 *
 * Component files outside this set still use text-[Npx]; that's
 * filed as a separate follow-up loop and intentionally not
 * asserted here.
 */

import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const SRC = join(__dirname, '..', '..', 'src');

const MIGRATED_FILES = [
  'pages/LandingPage.tsx',
  'pages/CIPage.tsx',
  'pages/WorkspacePage.tsx',
  'pages/SearchPage.tsx',
  'pages/ConnectorsPage.tsx',
  'pages/NewWorkspace.tsx',
  'components/primitives/AgentStatusBar.tsx',
  'components/layout/TopBar.tsx',
  'components/MetricCard.tsx',
  'components/EvidenceCard.tsx',
];

const TEXT_BRACKET_RE = /text-\[\d+px\]/g;

describe('Loop #12 — type-scale migration: zero text-[Npx] in migrated surfaces', () => {
  for (const rel of MIGRATED_FILES) {
    it(`${rel} uses the mz-text-* scale, not text-[Npx]`, () => {
      const path = join(SRC, rel);
      const text = readFileSync(path, 'utf8');
      const hits = text.match(TEXT_BRACKET_RE) ?? [];
      expect(hits, `Found ${hits.length} text-[Npx] occurrences: ${hits.join(', ')}`).toEqual([]);
    });
  }
});
