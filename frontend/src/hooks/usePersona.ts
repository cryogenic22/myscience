import { useCallback, useEffect, useState } from 'react';
import type { LifecycleStage } from '../components/layout/EngagementShell';

/**
 * PB-UX01 — the persona foundation.
 *
 * An engagement is a team sport across four deployment-agnostic personas
 * (jobs-to-be-done, NOT org titles — the same model works whether ZS runs the
 * engagement or the client does it self-service). See
 * docs/ux-analysis-personas-collaboration.html.
 *
 *   KC — Knowledge Curator   builds the intelligence  (brief → sources → dossier → gaps)
 *   SA — Strategy Analyst    turns it into options     (synthesis → scenarios)
 *   DM — Decision Maker      consumes + commits         (scenarios → war-room → decisions)
 *   EL — Engagement Lead     orchestrates all stages
 *
 * The persona does NOT gate access — it sets sensible DEFAULTS (where you land,
 * which stages open at full depth vs a read-only summary, which actions show).
 * Progressive disclosure by role, not access control: any persona can click
 * into any stage; they just won't see edit/commit controls they don't own.
 */

export const PERSONAS = [
  { id: 'KC', label: 'Knowledge Curator', blurb: 'Builds the intelligence — sources, dossier, gaps' },
  { id: 'SA', label: 'Strategy Analyst', blurb: 'Turns intelligence into options — synthesis, scenarios' },
  { id: 'DM', label: 'Decision Maker', blurb: 'Consumes and commits — scenarios, war room' },
  { id: 'EL', label: 'Engagement Lead', blurb: 'Orchestrates the whole engagement' },
] as const;

export type Persona = (typeof PERSONAS)[number]['id'];

const PERSONA_IDS = PERSONAS.map((p) => p.id) as readonly Persona[];

export function isPersona(value: unknown): value is Persona {
  return typeof value === 'string' && (PERSONA_IDS as readonly string[]).includes(value);
}

/** Stages each persona works at FULL depth. Everything else opens as a
 *  read-only summary. EL sees everything at full depth (orchestrator). */
export const PRIMARY_STAGES: Record<Persona, readonly LifecycleStage[]> = {
  KC: ['brief', 'sources', 'dossier', 'gaps'],
  SA: ['synthesis', 'scenarios', 'gaps'],
  DM: ['scenarios', 'workshop'],
  EL: ['brief', 'sources', 'dossier', 'synthesis', 'gaps', 'scenarios', 'workshop'],
};

/** Where each persona prefers to land when opening an engagement. Mapped to
 *  real LIFECYCLE_STAGES (no 'executive-summary' stage exists yet — DM lands on
 *  scenarios, their review entry point; EL lands on brief, the engagement start). */
const DEFAULT_STAGE: Record<Persona, LifecycleStage> = {
  KC: 'dossier',
  SA: 'synthesis',
  DM: 'scenarios',
  EL: 'brief',
};

export type StageDepth = 'full' | 'summary';

export interface PersonaDefaults {
  defaultStage: LifecycleStage;
  primaryStages: readonly LifecycleStage[];
  stageDepth: (stage: LifecycleStage) => StageDepth;
  canSteerAgent: boolean;       // KC / SA drive the agents
  canCommitDecision: boolean;   // DM / EL commit decisions
  canManageTeam: boolean;       // EL manages the engagement team
}

/** Pure: the defaults for a persona. No React — directly unit-testable. */
export function personaDefaults(persona: Persona): PersonaDefaults {
  const primaryStages = PRIMARY_STAGES[persona];
  return {
    defaultStage: DEFAULT_STAGE[persona],
    primaryStages,
    stageDepth: (stage) => (primaryStages.includes(stage) ? 'full' : 'summary'),
    canSteerAgent: persona === 'KC' || persona === 'SA',
    canCommitDecision: persona === 'DM' || persona === 'EL',
    canManageTeam: persona === 'EL',
  };
}

const STORAGE_KEY = 'mz_persona';
// EL is the safe default: a new user sees every stage at full depth, so nothing
// is hidden until they deliberately pick a narrower persona (don't surprise-hide).
const DEFAULT_PERSONA: Persona = 'EL';

export function readPersona(): Persona {
  if (typeof window === 'undefined') return DEFAULT_PERSONA;
  const stored = window.localStorage.getItem(STORAGE_KEY);
  return isPersona(stored) ? stored : DEFAULT_PERSONA;
}

/** Read + set the current persona, persisted to localStorage (mirrors the
 *  mz_auth_role pattern). Returns [persona, setPersona]. */
export function usePersona(): [Persona, (p: Persona) => void] {
  const [persona, setPersonaState] = useState<Persona>(readPersona);

  const setPersona = useCallback((p: Persona) => {
    setPersonaState(p);
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(STORAGE_KEY, p);
    }
  }, []);

  // Pick up changes made in other tabs / components.
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const onStorage = (e: StorageEvent) => {
      if (e.key === STORAGE_KEY && isPersona(e.newValue)) setPersonaState(e.newValue);
    };
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, []);

  return [persona, setPersona];
}
