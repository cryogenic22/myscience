/**
 * D2 — LandingPage migration lint.
 *
 * Pin the post-D2 contract: no border-r/l/t/b/x/y utilities, no
 * standalone `border` class, no `borderColor` inline. Spotify/Gemini-
 * style surface separation only.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const SRC = readFileSync(
  resolve(__dirname, '../../src/pages/LandingPage.tsx'),
  'utf-8',
);

function stripComments(src: string): string {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, '')
    // Only strip // comments NOT preceded by : (URLs etc.)
    .replace(/(^|[^:])\/\/[^\n]*/g, '$1');
}

const CODE = stripComments(SRC);

describe('LandingPage — D2 border discipline', () => {
  it('contains no border-r / border-l / border-t / border-b / border-x / border-y utilities', () => {
    const matches = CODE.match(/\bborder-(r|l|t|b|x|y)(?:-\d)?\b/g) || [];
    expect(matches).toEqual([]);
  });

  it('contains no standalone `border` class in any className', () => {
    // Look for "border" as a class word (not "border-radius" or "border-foo-bar")
    // inside className="..." or className={...}.
    const classNameValues = CODE.match(/className=["'][^"']+["']/g) || [];
    for (const cn of classNameValues) {
      // Strip the className=" wrapper and split by whitespace.
      const inner = cn.replace(/^className=["']/, '').replace(/["']$/, '');
      const classes = inner.split(/\s+/);
      expect(classes).not.toContain('border');
    }
  });

  it('contains no `borderColor` inline style anywhere', () => {
    expect(CODE).not.toMatch(/borderColor\s*:/);
  });

  it('contains no `border-style` or border:1px inline', () => {
    expect(CODE).not.toMatch(/border\s*:\s*['"]?\s*1px/);
    expect(CODE).not.toMatch(/borderStyle\s*:/);
  });

  it('still uses CSS variables for surface/text/accent', () => {
    expect(CODE).toMatch(/var\(--color-bg\)/);
    expect(CODE).toMatch(/var\(--color-ink\)/);
    expect(CODE).toMatch(/var\(--color-accent\)/);
  });

  it('still exports the three CTA actions (no functional regression)', () => {
    expect(CODE).toMatch(/onEnter/);
    expect(CODE).toMatch(/onSearch/);
    expect(CODE).toMatch(/onCI/);
  });
});
