/**
 * PB-IX01 — promote-bridge URL contract.
 *
 * SignalDetail WRITES the promote URL (/ci?tab=engagements&new=1&asset=&
 * seedName=&seedContext=&seedSignalId=); CIPage READS those params and passes
 * them to EngagementsTab. The two live in different files, so a param rename on
 * one side would silently break the bridge with no type error. This static scan
 * pins the contract: every param SignalDetail writes is read by CIPage.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const signalDetail = readFileSync(
  resolve(__dirname, '../../src/components/ci/SignalDetail.tsx'), 'utf-8',
);
const ciPage = readFileSync(
  resolve(__dirname, '../../src/pages/CIPage.tsx'), 'utf-8',
);

// The params SignalDetail puts on the engagement-promote URL.
const PROMOTE_PARAMS = ['new', 'asset', 'seedName', 'seedContext', 'seedSignalId'];

describe('promote-bridge URL contract (PB-IX01)', () => {
  it('SignalDetail writes every promote param', () => {
    for (const p of PROMOTE_PARAMS) {
      expect(signalDetail).toContain(`${p}=`);
    }
    // Dossier + engagement targets both present.
    expect(signalDetail).toContain('tab=dossier');
    expect(signalDetail).toContain('tab=engagements&new=1');
  });

  it('CIPage reads every promote param SignalDetail writes', () => {
    for (const p of PROMOTE_PARAMS) {
      expect(ciPage).toContain(`params.get('${p}')`);
    }
  });

  it('CIPage clears every promote param on consume (no sticky modal)', () => {
    for (const p of PROMOTE_PARAMS) {
      expect(ciPage).toContain(`next.delete('${p}')`);
    }
  });
});
