/**
 * No-vacuous-green guard — TypeScript typecheck (harness, Step 0).
 *
 * The literal fake-green this guards: the root `frontend/tsconfig.json` is
 * `{"files": []}` with project references — it type-checks NOTHING. A naive
 * `tsc --noEmit` (no `-p`) resolves to the root config and exits 0 having
 * collected zero files. That is "the build passed" without checking the
 * product (ADR-0003 failure #3 / Amendment-2 "vacuous green").
 *
 * Principle 3 (No vacuous green): a gate that checks nothing must fail closed.
 * The real typecheck MUST target tsconfig.app.json (which `include`s ./src),
 * and the `typecheck` npm script MUST be that. This test is deterministic and
 * DB-/tsc-free so it stays in the Lane-1 PR gate. The CI gate additionally
 * runs `npm run typecheck` and asserts >0 files were collected
 * (frontend/scripts/assert-typecheck-nonvacuous.mjs) — the runtime half.
 *
 * See .claude/rules/conservation-gates.md.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const ROOT = resolve(__dirname, '../..');

/** Parse a tsconfig that may carry // and /* *​/ comments (JSONC). */
function readJsonc(path: string): Record<string, unknown> {
  const raw = readFileSync(resolve(ROOT, path), 'utf-8')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/.*$/gm, '$1');
  return JSON.parse(raw);
}

describe('No vacuous green — frontend typecheck (Step 0)', () => {
  it('root tsconfig.json checks nothing (files: []) — so it must NOT be the typecheck target', () => {
    const root = readJsonc('tsconfig.json');
    // We assert the known-vacuous shape so the guard below is meaningful: if
    // someone makes the root config actually check files, that's fine too, but
    // the typecheck script must still not silently rely on it.
    expect(Array.isArray(root.files)).toBe(true);
    expect((root.files as unknown[]).length).toBe(0);
  });

  it('tsconfig.app.json actually includes the product source (non-empty include)', () => {
    const app = readJsonc('tsconfig.app.json');
    const include = (app.include as string[]) || [];
    expect(include.length).toBeGreaterThan(0);
    expect(include).toContain('src');
  });

  it('the `typecheck` script targets tsconfig.app.json, never the vacuous root', () => {
    const pkg = JSON.parse(readFileSync(resolve(ROOT, 'package.json'), 'utf-8'));
    const script: string = pkg.scripts?.typecheck ?? '';
    expect(script).toMatch(/tsc\b/);
    expect(script).toMatch(/-p\s+tsconfig\.app\.json/);
    // Must not be a bare `tsc --noEmit` that resolves to the root files:[] config.
    expect(script).not.toMatch(/tsc\s+--noEmit\s*$/);
  });
});
