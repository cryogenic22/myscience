/**
 * LandingPage — architecture + D2 border discipline.
 *
 * The page was recoded onto a dedicated stylesheet (styles/landing.css) of
 * semantic classes + design tokens, instead of Tailwind utilities (which
 * generate on demand and can differ between local and Railway builds — the
 * root cause of the page rendering fine locally yet collapsing in prod).
 *
 * These checks pin that contract: no Tailwind border utilities in the TSX, no
 * hard 1px borders in the stylesheet (separation via tone + shadow), the
 * stylesheet is built on the design tokens, and the three CTA actions remain.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const TSX = readFileSync(resolve(__dirname, '../../src/pages/LandingPage.tsx'), 'utf-8');
const CSS = readFileSync(resolve(__dirname, '../../src/styles/landing.css'), 'utf-8');

function stripComments(src: string): string {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/[^\n]*/g, '$1');
}

const TSX_CODE = stripComments(TSX);

describe('LandingPage — architecture + D2 discipline', () => {
  it('uses the dedicated landing stylesheet (not utility soup)', () => {
    expect(TSX_CODE).toMatch(/import\s+['"]\.\.\/styles\/landing\.css['"]/);
  });

  it('contains no border-r / -l / -t / -b / -x / -y utilities in the TSX', () => {
    expect(TSX_CODE.match(/\bborder-(r|l|t|b|x|y)(?:-\d)?\b/g) || []).toEqual([]);
  });

  it('contains no standalone `border` class in any TSX className', () => {
    const classNameValues = TSX_CODE.match(/className=["'][^"']+["']/g) || [];
    for (const cn of classNameValues) {
      const classes = cn.replace(/^className=["']/, '').replace(/["']$/, '').split(/\s+/);
      expect(classes).not.toContain('border');
    }
  });

  it('the stylesheet declares no hard 1px borders (tone + shadow only)', () => {
    const css = stripComments(CSS);
    expect(css).not.toMatch(/border\s*:\s*[^;]*\b\d+px\b/);
    expect(css).not.toMatch(/border-(top|right|bottom|left|style)\s*:/);
  });

  it('the stylesheet is built on the design tokens', () => {
    expect(CSS).toMatch(/var\(--color-bg\)/);
    expect(CSS).toMatch(/var\(--color-ink\)/);
    expect(CSS).toMatch(/var\(--color-accent\)/);
    expect(CSS).toMatch(/var\(--font-display\)/);
  });

  it('owns its own scroll (avoids the global body overflow clamp)', () => {
    expect(CSS).toMatch(/overflow-y\s*:\s*auto/);
  });

  it('still wires the three CTA actions (no functional regression)', () => {
    expect(TSX_CODE).toMatch(/onEnter/);
    expect(TSX_CODE).toMatch(/onSearch/);
    expect(TSX_CODE).toMatch(/onCI/);
  });
});
