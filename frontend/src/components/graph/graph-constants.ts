// Single source of truth for all graph visual constants.
// Imported by KnowledgeGraph (the unified graph renderer).

/**
 * Node colors by entity type (designed for dark #0f172a canvas background).
 * Every entity type has a VISUALLY DISTINCT hue — no two share a hex (graph
 * polish #4). The reds/pinks are deliberately split: therapeutic_area=fuchsia,
 * adverse_event=rose, event=red so the three never collide.
 */
export const NODE_COLORS: Record<string, string> = {
  drug: '#3b82f6',
  company: '#f59e0b',
  trial: '#14b8a6',
  therapeutic_area: '#d946ef', // fuchsia (was #f43f5e — collided with adverse_event)
  mechanism: '#a78bfa',
  literature: '#22c55e',
  event: '#ef4444', // red
  investigator: '#06b6d4',
  patent: '#8b5cf6',
  biomarker: '#0891b2',
  adverse_event: '#e11d48', // rose (was #f43f5e — collided with therapeutic_area)
  trial_outcome: '#059669',
  trial_location: '#6366f1',
  drug_label: '#64748b', // slate
  unknown: '#475569', // darker slate (was #64748b — collided with drug_label)
};

/**
 * Edge categories — the SINGLE source of truth for edge color + label + the
 * legend grouping. Edges in the same semantic group share ONE color; different
 * groups have visually distinct colors (graph polish #4). `EDGE_COLORS` and the
 * legend in KnowledgeGraph both DERIVE from this map, so the rendered edge color
 * and the legend swatch can never drift apart, and every link type below is
 * categorised (no uncategorised-grey edges).
 */
export interface EdgeCategory {
  /** Stable key used for the legend toggle state. */
  key: string;
  /** Human-readable legend label. */
  label: string;
  /** One distinct color for every link type in this group. */
  color: string;
  /** The link types that belong to this semantic group. */
  types: string[];
}

export const EDGE_CATEGORY_LIST: EdgeCategory[] = [
  {
    key: 'ownership',
    label: 'Ownership',
    color: '#f59e0b', // amber
    types: ['OWNS', 'MANUFACTURES', 'SPONSORS'],
  },
  {
    key: 'research',
    label: 'Research',
    color: '#14b8a6', // teal
    types: ['INVESTIGATES', 'EVIDENCE_FOR', 'HAS_OUTCOME', 'LED_BY', 'AUTHORED_BY', 'HAS_BIOACTIVITY', 'MENTIONED_IN'],
  },
  {
    key: 'science',
    label: 'Science',
    color: '#a78bfa', // violet
    types: ['TARGETS_MECHANISM', 'IN_THERAPEUTIC_AREA'],
  },
  {
    key: 'regulatory',
    label: 'Regulatory',
    color: '#8b5cf6', // purple
    types: ['HAS_PATENT', 'HAS_MILESTONE', 'HAS_LABEL'],
  },
  {
    key: 'safety',
    label: 'Safety',
    color: '#e11d48', // rose (matches the adverse_event node color)
    types: ['HAS_ADVERSE_EVENT', 'SHORTAGE_AFFECTS'],
  },
  {
    key: 'competition',
    label: 'Competition',
    color: '#f97316', // orange — split out of "safety" so it no longer mis-shares the rose
    types: ['COMPETES_WITH'],
  },
  {
    key: 'geography',
    label: 'Geography',
    color: '#6366f1', // indigo
    types: ['LOCATED_AT'],
  },
];

/** key → category, for O(1) category lookup. */
export const EDGE_CATEGORY_BY_KEY: Record<string, EdgeCategory> = Object.fromEntries(
  EDGE_CATEGORY_LIST.map((cat) => [cat.key, cat]),
);

/** link_type → its owning category, derived from EDGE_CATEGORY_LIST. */
export const EDGE_CATEGORY_BY_TYPE: Record<string, EdgeCategory> = (() => {
  const map: Record<string, EdgeCategory> = {};
  for (const cat of EDGE_CATEGORY_LIST) {
    for (const t of cat.types) map[t] = cat;
  }
  return map;
})();

/**
 * Edge colors by link type — DERIVED from EDGE_CATEGORY_LIST (a link type's
 * color is its category's color). Same group ⇒ same color; different group ⇒
 * different color. Verified no two categories share a hex.
 */
export const EDGE_COLORS: Record<string, string> = Object.fromEntries(
  EDGE_CATEGORY_LIST.flatMap((cat) => cat.types.map((t) => [t, cat.color])),
);

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
  HAS_BIOACTIVITY: 'Bioactivity',
  MENTIONED_IN: 'Mentioned in',
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
  biomarker: 'Biomarker',
  adverse_event: 'Adverse Event',
  trial_outcome: 'Outcome',
  trial_location: 'Location',
  drug_label: 'Label',
  unknown: 'Unknown',
};

/**
 * Exploration lenses — the SINGLE source of truth mapping a lens to the real
 * `link_types` (and optional min_confidence) forwarded to /graph/traverse.
 *
 * Every link type below is drawn from the live edge vocabulary in
 * `EDGE_CATEGORY_LIST` / `EDGE_LABELS` above — no invented types.
 * `linkTypes: null` means "no filter" (the full neighborhood).
 */
export interface GraphLens {
  id: string;
  label: string;
  description: string;
  linkTypes: string[] | null;
}

export const GRAPH_LENSES: GraphLens[] = [
  {
    id: 'neighborhood',
    label: 'Neighborhood',
    description: 'All direct and second-order relationships around the anchor.',
    linkTypes: null,
  },
  {
    id: 'competitive',
    label: 'Competitive',
    description: 'Rival drugs and companies competing in the same space.',
    linkTypes: ['COMPETES_WITH'],
  },
  {
    id: 'evidence',
    // INVESTIGATES / EVIDENCE_FOR / HAS_OUTCOME / LED_BY / AUTHORED_BY are the
    // real "research" edge category in EDGE_CATEGORY_LIST.
    label: 'Evidence',
    description: 'Trial, outcome, and literature evidence linkages.',
    linkTypes: ['INVESTIGATES', 'EVIDENCE_FOR', 'HAS_OUTCOME', 'LED_BY', 'AUTHORED_BY'],
  },
  {
    id: 'regulatory',
    // The real "regulatory" edge category.
    label: 'Regulatory',
    description: 'Patent, milestone, and label (regulatory) linkages.',
    linkTypes: ['HAS_PATENT', 'HAS_MILESTONE', 'HAS_LABEL'],
  },
  {
    id: 'safety',
    // The real "safety" edge types (COMPETES_WITH lives in its own lens above).
    label: 'Safety',
    description: 'Adverse-event and supply-shortage linkages.',
    linkTypes: ['HAS_ADVERSE_EVENT', 'SHORTAGE_AFFECTS'],
  },
];

/** Dark canvas background */
export const GRAPH_BG = '#0f172a';
export const GRAPH_TEXT = '#e2e8f0';
export const GRAPH_TEXT_MUTED = '#94a3b8';
