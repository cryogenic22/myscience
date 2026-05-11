/**
 * Dossier wire types — aligned with BE-6 (`GET /dossier/{type}/{slug}`),
 * shipped 2026-05-11 in PR #57.
 *
 * The hook (`useDossier`) adapts the backend response into this shape
 * so the component layer (`DossierPage`) stays stable across future
 * BE iterations.
 */

export type DossierEntityType =
  | 'drug'
  | 'company'
  | 'mechanism'
  | 'trial'
  | 'therapeutic_area';

export type EvidenceTier = 'T1' | 'T2' | 'T3' | 'T4';

export interface DossierEntity {
  id: string;
  /** URL slug — supplied by the route, not the backend. */
  slug: string;
  type: DossierEntityType;
  canonical_name: string;
  aliases: string[];
  external_ids: Record<string, string>;
  primary_attributes: Record<string, string | number>;
  updated_at: string;
}

export interface DossierSynthesis {
  summary: string;
  citations: Array<{ marker: string; evidence_id: string }>;
}

export interface DossierEvidence {
  id: string;
  source_name: string;
  tier: EvidenceTier;
  published_at: string;
  snippet: string;
}

export interface DossierRecentMove {
  id: string;
  kind: 'signal' | 'state_transition';
  occurred_at: string;
  headline: string;
}

export interface DossierWatcher {
  user_id: string;
  display_name: string;
  avatar_url: string | null;
}

export interface Dossier {
  entity: DossierEntity;
  synthesis: DossierSynthesis | null;
  recent_moves: DossierRecentMove[];
  evidence: DossierEvidence[];
  watchers: DossierWatcher[];
  watcher_count: number;
}
