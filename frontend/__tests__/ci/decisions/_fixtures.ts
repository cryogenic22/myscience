/**
 * Shared fixtures for SPEC_030 Decision Workspace v2 tests.
 *
 * Pattern: factory functions returning fully-typed objects with sane
 * defaults. Each accepts a Partial override so individual tests can
 * mutate just what they need without re-spelling the rest of the shape.
 *
 * The shapes here MUST match `frontend/src/api.ts` (the typed client
 * contract) which in turn must match `schema/openapi.json`. If a test
 * fails because a field shape changed, update both files together.
 */

import type {
  DecisionBrief,
  DecisionBriefOption,
  BriefStateLogEntry,
  BriefState,
  TriggerKind,
  EvidenceRef,
} from '../../../src/api';

let __counter = 0;
const nextId = (prefix: string) => `${prefix}-${(++__counter).toString(36).padStart(3, '0')}`;

export function makeOption(overrides: Partial<DecisionBriefOption> = {}): DecisionBriefOption {
  return {
    option_id: nextId('opt'),
    brief_id: 'b-001',
    ordinal: 1,
    label: 'Accelerate Phase III readout',
    description: 'Pull readout window forward by 8 weeks',
    predicted_outcome: 'Expect 8–12% share gain over 18 months',
    cost_estimate: '$5M incremental, 4-month delay',
    risk_notes: 'Lower data quality if final dataset thin',
    created_at: new Date('2026-05-09T10:00:00Z').toISOString(),
    ...overrides,
  };
}

export function makeStateLogEntry(overrides: Partial<BriefStateLogEntry> = {}): BriefStateLogEntry {
  return {
    log_id: nextId('log'),
    brief_id: 'b-001',
    from_state: null,
    to_state: 'draft' as BriefState,
    actor_user_id: 'user-001',
    reason: null,
    transitioned_at: new Date('2026-05-09T10:00:00Z').toISOString(),
    ...overrides,
  };
}

export function makeEvidenceRef(overrides: Partial<EvidenceRef> = {}): EvidenceRef {
  return {
    type: 'signal',
    id: nextId('s'),
    snapshot_at: new Date('2026-05-09T10:00:00Z').toISOString(),
    ...overrides,
  };
}

export function makeBrief(overrides: Partial<DecisionBrief> = {}): DecisionBrief {
  const brief: DecisionBrief = {
    brief_id: 'b-001',
    question: 'Should we accelerate Phase III readout in 2L NSCLC?',
    trigger_kind: 'manual' as TriggerKind,
    trigger_signal_ids: [],
    trigger_metadata: {},
    stakeholders: ['commercial', 'medical', 'rd'],
    time_horizon_days: 14,
    evidence_refs: [makeEvidenceRef()],
    constraints: [],
    success_criteria: 'Readout meets primary endpoint, p<0.05',
    confidence_to_proceed: 0.65,
    state: 'draft',
    owner_user_id: 'user-001',
    war_room_id: null,
    decision_id: null,
    archived_at: null,
    created_at: new Date('2026-05-09T10:00:00Z').toISOString(),
    updated_at: new Date('2026-05-09T10:00:00Z').toISOString(),
    options: [],
    state_log: [makeStateLogEntry()],
    ...overrides,
  };
  return brief;
}

/**
 * Set of canonical brief states for parametric tests.
 * `it.each(ALL_STATES)('renders for state %s', (s) => ...)` over this list
 * to assert every state renders without crashing.
 */
export const ALL_STATES: BriefState[] = [
  'draft',
  'human_review',
  'simulation_pending',
  'simulation_complete',
  'decision_pending',
  'committed',
  'in_review',
  'closed',
];

/**
 * Light + dark theme application for snapshot tests. Use as:
 *   beforeEach(() => applyTheme('light'));
 *   beforeEach(() => applyTheme('dark'));
 */
export function applyTheme(theme: 'light' | 'dark'): void {
  if (typeof document === 'undefined') return;
  if (theme === 'dark') {
    document.documentElement.classList.add('dark');
  } else {
    document.documentElement.classList.remove('dark');
  }
}

/**
 * Reset auth token shape used by route guards. Tests that exercise
 * uploader-only mutations call setRole('uploader'); viewer-only flows
 * use 'viewer'; auth-failure paths use null.
 */
export function setRole(role: 'viewer' | 'uploader' | 'enterprise' | null): void {
  if (typeof window === 'undefined') return;
  if (role) {
    window.localStorage.setItem('mz_auth_token', `test-token-${role}`);
    window.localStorage.setItem('mz_auth_role', role);
  } else {
    window.localStorage.removeItem('mz_auth_token');
    window.localStorage.removeItem('mz_auth_role');
  }
}
