/**
 * PB-301 — Dossier scaffold types.
 *
 * The frontend shape mirrors the contract the backend composer
 * (`GET /dossier/{type}/{slug}` — AGENT_BACKLOG#BE-6, PR #57) is
 * expected to honour. While BE-6 is unmerged the `useDossier` hook
 * returns mock data with `is_mock: true` so callers can render a
 * "placeholder data" notice.
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
  slug: string;
  type: DossierEntityType;
  canonical_name: string;
  aliases: string[];
  external_ids: Record<string, string>;
  primary_attributes: Record<string, string | number | null>;
  updated_at: string;
}

export interface DossierSynthesis {
  /** Markdown summary. For PB-302, citations are inline markers. */
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
  /**
   * Frontend-only flag. Set to `true` while the data is supplied by
   * the mock generator. Remove the banner once BE-6 lands and this
   * field is dropped from the wire format.
   */
  is_mock?: boolean;
}
