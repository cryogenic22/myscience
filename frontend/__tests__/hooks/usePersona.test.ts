import { describe, it, expect, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import {
  personaDefaults,
  usePersona,
  readPersona,
  isPersona,
  PERSONAS,
  PRIMARY_STAGES,
} from '../../src/hooks/usePersona';

beforeEach(() => {
  window.localStorage.clear();
});

describe('personaDefaults (pure)', () => {
  it('lands each persona on its default stage', () => {
    expect(personaDefaults('KC').defaultStage).toBe('dossier');
    expect(personaDefaults('SA').defaultStage).toBe('synthesis');
    expect(personaDefaults('DM').defaultStage).toBe('scenarios');
    expect(personaDefaults('EL').defaultStage).toBe('brief');
  });

  it('opens primary stages at full depth, others as summary', () => {
    const kc = personaDefaults('KC');
    expect(kc.stageDepth('dossier')).toBe('full');     // KC primary
    expect(kc.stageDepth('scenarios')).toBe('summary'); // not KC's
    const sa = personaDefaults('SA');
    expect(sa.stageDepth('scenarios')).toBe('full');
    expect(sa.stageDepth('sources')).toBe('summary');
  });

  it('EL sees every stage at full depth (orchestrator)', () => {
    const el = personaDefaults('EL');
    for (const s of PRIMARY_STAGES.EL) expect(el.stageDepth(s)).toBe('full');
    expect(el.stageDepth('workshop')).toBe('full');
  });

  it('gates actions by persona role (defaults, not access control)', () => {
    expect(personaDefaults('KC').canSteerAgent).toBe(true);
    expect(personaDefaults('DM').canSteerAgent).toBe(false);
    expect(personaDefaults('DM').canCommitDecision).toBe(true);
    expect(personaDefaults('KC').canCommitDecision).toBe(false);
    expect(personaDefaults('EL').canManageTeam).toBe(true);
    expect(personaDefaults('SA').canManageTeam).toBe(false);
  });
});

describe('isPersona / readPersona', () => {
  it('validates persona ids', () => {
    expect(isPersona('KC')).toBe(true);
    expect(isPersona('nope')).toBe(false);
    expect(isPersona(null)).toBe(false);
  });

  it('defaults to EL when nothing stored (safe: hides nothing)', () => {
    expect(readPersona()).toBe('EL');
  });

  it('reads a valid stored persona, ignores garbage', () => {
    window.localStorage.setItem('mz_persona', 'SA');
    expect(readPersona()).toBe('SA');
    window.localStorage.setItem('mz_persona', 'garbage');
    expect(readPersona()).toBe('EL');
  });
});

describe('usePersona', () => {
  it('starts from the stored persona and persists changes', () => {
    window.localStorage.setItem('mz_persona', 'KC');
    const { result } = renderHook(() => usePersona());
    expect(result.current[0]).toBe('KC');

    act(() => result.current[1]('DM'));
    expect(result.current[0]).toBe('DM');
    expect(window.localStorage.getItem('mz_persona')).toBe('DM');
  });
});

describe('PERSONAS catalog', () => {
  it('has the four personas with labels', () => {
    expect(PERSONAS.map((p) => p.id)).toEqual(['KC', 'SA', 'DM', 'EL']);
    expect(PERSONAS.every((p) => p.label && p.blurb)).toBe(true);
  });
});
