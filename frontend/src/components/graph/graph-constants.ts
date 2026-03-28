// Single source of truth for all graph visual constants.
// Imported by ModernGraph, GraphMini, and GraphExplorer.

/** Node colors by entity type (designed for dark #0f172a canvas background) */
export const NODE_COLORS: Record<string, string> = {
  drug: '#3b82f6',
  company: '#f59e0b',
  trial: '#14b8a6',
  therapeutic_area: '#f43f5e',
  mechanism: '#a78bfa',
  literature: '#22c55e',
  event: '#ef4444',
  investigator: '#06b6d4',
  patent: '#8b5cf6',
  unknown: '#64748b',
};

/** Edge colors by link type */
export const EDGE_COLORS: Record<string, string> = {
  OWNS: '#f59e0b',
  MANUFACTURES: '#f59e0b',
  SPONSORS: '#14b8a6',
  INVESTIGATES: '#3b82f6',
  EVIDENCE_FOR: '#22c55e',
  TARGETS_MECHANISM: '#a78bfa',
  IN_THERAPEUTIC_AREA: '#f43f5e',
  COMPETES_WITH: '#ef4444',
  HAS_MILESTONE: '#f59e0b',
  HAS_ADVERSE_EVENT: '#ef4444',
  LOCATED_AT: '#64748b',
  HAS_OUTCOME: '#64748b',
  LED_BY: '#06b6d4',
  AUTHORED_BY: '#06b6d4',
  SHORTAGE_AFFECTS: '#ef4444',
  HAS_LABEL: '#64748b',
  HAS_PATENT: '#8b5cf6',
};

/** Human-readable edge labels */
export const EDGE_LABELS: Record<string, string> = {
  OWNS: 'Owns',
  MANUFACTURES: 'Manufactures',
  SPONSORS: 'Sponsors',
  INVESTIGATES: 'Investigates',
  EVIDENCE_FOR: 'Evidence for',
  TARGETS_MECHANISM: 'Targets',
  IN_THERAPEUTIC_AREA: 'In TA',
  COMPETES_WITH: 'Competes with',
  HAS_MILESTONE: 'Milestone',
  HAS_ADVERSE_EVENT: 'Adverse event',
  LOCATED_AT: 'Located at',
  HAS_OUTCOME: 'Outcome',
  LED_BY: 'Led by',
  AUTHORED_BY: 'Authored by',
  SHORTAGE_AFFECTS: 'Shortage',
  HAS_LABEL: 'Label',
  HAS_PATENT: 'Patent',
};

/** Human-readable node type labels */
export const NODE_TYPE_LABELS: Record<string, string> = {
  drug: 'Drug',
  company: 'Company',
  trial: 'Trial',
  therapeutic_area: 'Ther. Area',
  mechanism: 'Mechanism',
  literature: 'Literature',
  event: 'Event',
  investigator: 'Investigator',
  patent: 'Patent',
  unknown: 'Unknown',
};

/** Dark canvas background */
export const GRAPH_BG = '#0f172a';
export const GRAPH_TEXT = '#e2e8f0';
export const GRAPH_TEXT_MUTED = '#94a3b8';
