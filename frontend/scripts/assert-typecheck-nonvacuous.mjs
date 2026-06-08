#!/usr/bin/env node
/**
 * No-vacuous-green guard — runtime half (harness, Step 0).
 *
 * Runs the real typecheck config and asserts it actually collected product
 * source files. A typecheck that compiles ZERO files exits 0 and reads as
 * "green" while checking nothing (root tsconfig.json is `files: []`). This
 * fails closed if that ever happens again.
 *
 * Usage (CI Lane-1 gate): node scripts/assert-typecheck-nonvacuous.mjs
 * Exit 0 = >0 product files were type-checked; exit 1 = vacuous / error.
 */
import { execSync } from 'node:child_process';

const CONFIG = 'tsconfig.app.json';

let out = '';
try {
  // --listFilesOnly prints every file the project would compile, one per line.
  // shell:true so `npx` resolves on Windows (npx.cmd) and POSIX CI alike.
  out = execSync(`npx tsc -p ${CONFIG} --listFilesOnly`, {
    encoding: 'utf-8',
    stdio: ['ignore', 'pipe', 'inherit'],
    shell: true,
  });
} catch (err) {
  // tsc returns non-zero on type errors; --listFilesOnly still prints the list
  // to stdout, so capture it. A genuinely broken invocation (no stdout) fails.
  out = err.stdout?.toString() ?? '';
  if (!out.trim()) {
    console.error('assert-typecheck-nonvacuous: tsc produced no file list — invocation broken.');
    process.exit(1);
  }
}

const productFiles = out
  .split('\n')
  .map((l) => l.trim())
  .filter(Boolean)
  .filter((l) => !l.includes('node_modules'))
  .filter((l) => !l.endsWith('.d.ts'));

if (productFiles.length === 0) {
  console.error(
    `assert-typecheck-nonvacuous: VACUOUS GREEN — ${CONFIG} type-checked 0 product files. ` +
      'The typecheck is not actually checking the app.',
  );
  process.exit(1);
}

console.log(`assert-typecheck-nonvacuous: OK — ${productFiles.length} product files type-checked.`);
process.exit(0);
