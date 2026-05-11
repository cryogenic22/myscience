/**
 * Loop #17 — Helix shared types (Bridge / Moments / Twin / Decisions).
 *
 * Mirrors the backend POST /bridge/moments wire format and the
 * Helix prototype shape from `specs/helix_proto.tsx`.
 */

export type ImpactCategoryId =
  | 'financial' | 'governance' | 'strategic' | 'clinical' | 'product'
  | 'regulatory' | 'ma' | 'access' | 'ai' | 'esg';

export interface ImpactCategory {
  id: ImpactCategoryId;
  label: string;
  color: string;
}

export const IMPACT_CATEGORIES: ImpactCategory[] = [
  { id: 'financial',  label: 'Financial',         color: '#60a5fa' },
  { id: 'governance', label: 'Governance',        color: '#94a3b8' },
  { id: 'strategic',  label: 'Strategic',         color: '#a78bfa' },
  { id: 'clinical',   label: 'Clinical',          color: '#5eead4' },
  { id: 'product',    label: 'Product',           color: '#fb923c' },
  { id: 'regulatory', label: 'Regulatory',        color: '#fbbf24' },
  { id: 'ma',         label: 'M&A',               color: '#f472b6' },
  { id: 'access',     label: 'Pricing & Access',  color: '#34d399' },
  { id: 'ai',         label: 'AI & Digital',      color: '#818cf8' },
  { id: 'esg',        label: 'ESG & Supply',      color: '#fb7185' },
];

export type PlayKind = 'aggressive' | 'balanced' | 'cautious';

export interface Play {
  id: string;
  label: string;
  ev: number;
  ev_var: number;
  prob_success: number;
  kind: PlayKind;
}

export interface DeltaBelief {
  from: number;
  to: number;
  label: string;
}

export interface Moment {
  id: string;
  priority: number;
  ev_at_stake_musd: number;
  expires_hours: number;
  title: string;
  summary: string;
  delta_belief: DeltaBelief;
  signal_chain: string[];
  category: ImpactCategoryId | string;
  plays: Play[];
}

export interface MomentsResponse {
  moments: Moment[];
}

/** Map an impact_score (0–10) to its Helix tier classification. */
export function tierFor(impact_score: number | null | undefined): 1 | 2 | 3 {
  const s = Number(impact_score ?? 0);
  if (s >= 7) return 1;
  if (s >= 4) return 2;
  return 3;
}

/** Map a Signal.kbq_tags[0] to an ImpactCategory (default: strategic). */
export function categoryFor(kbq_tags: string[] | null | undefined): ImpactCategory {
  const first = (kbq_tags ?? [])[0]?.toLowerCase();
  return IMPACT_CATEGORIES.find((c) => c.id === first) ?? IMPACT_CATEGORIES[2]; // strategic
}
