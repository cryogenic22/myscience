/**
 * Tailwind v4 prod-safety guard.
 *
 * v4 auto-detects which files to scan for class names by walking up from the
 * Git root and honouring .gitignore. Railway/Nixpacks builds WITHOUT a .git
 * directory, so that heuristic under-scans and utility classes silently no-op
 * in production (they work locally, where .git is present). `index.css` pins
 * explicit `@source` globs so scanning is deterministic everywhere.
 *
 * This test fails if those globs are removed — preventing a regression that
 * only manifests after deploy. Also guards against dynamically-built class
 * names, which the scanner cannot see regardless of @source.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { globSync } from 'node:fs';

const SRC_DIR = resolve(__dirname, '../../src');
const INDEX_CSS = readFileSync(resolve(SRC_DIR, 'index.css'), 'utf-8');

describe('Tailwind v4 — deterministic source scanning (prod safety)', () => {
  it('index.css imports tailwind', () => {
    expect(INDEX_CSS).toMatch(/@import\s+["']tailwindcss["']/);
  });

  it('index.css declares explicit @source globs (do not remove)', () => {
    const sources = INDEX_CSS.match(/@source\s+["'][^"']+["']/g) || [];
    expect(sources.length).toBeGreaterThanOrEqual(1);
    // must cover the component source tree
    expect(INDEX_CSS).toMatch(/@source\s+["']\.\/\*\*\/\*\.\{[^}]*tsx[^}]*\}["']/);
  });
});

describe('Tailwind — no dynamically-built class names', () => {
  // The v4 scanner only sees literal strings; `text-${x}` never generates.
  it('no template-literal tailwind utilities inside className', () => {
    const files = globSync('**/*.{ts,tsx}', { cwd: SRC_DIR });
    const offenders: string[] = [];
    // Only className values matter — `key`/`id`/style strings are not scanned by
    // Tailwind. Capture className="…" and className={`…`} values, then flag a
    // utility prefix followed by an interpolation within them.
    const classNameAttr = /class(?:Name)?\s*=\s*(?:"[^"]*"|'[^']*'|\{`[^`]*`\}|\{[^}]*\})/g;
    const dynUtil = /\b(?:bg|text|border|p|px|py|m|mx|my|w|h|gap|grid-cols|flex|max-w|min-w|rounded)-\$\{/;
    for (const f of files) {
      const body = readFileSync(resolve(SRC_DIR, f), 'utf-8');
      for (const m of body.match(classNameAttr) || []) {
        if (dynUtil.test(m)) { offenders.push(`${f}: ${m.slice(0, 80)}`); break; }
      }
    }
    expect(offenders).toEqual([]);
  });
});
