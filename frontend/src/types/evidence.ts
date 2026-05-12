/**
 * Loop #19 — Evidence document metadata as surfaced to /ci.
 *
 * Mirrors what `POST /evidence/by-ids` returns for each requested
 * evidence_id. All fields except `evidence_id` are optional so the UI
 * can degrade gracefully when a backend join misses.
 */
export type EvidenceTier = 'tier_1' | 'tier_2' | 'tier_3' | 'unknown';

export interface EvidenceDocument {
  evidence_id: string;
  source_id?: string;
  source_url?: string | null;
  source_tier?: EvidenceTier | string | null;
  retrieved_at?: string | null;
  snippet?: string | null;
  confidence?: number | null;
}

export interface EvidenceBatchResponse {
  documents: EvidenceDocument[];
  missing_ids: string[];
}
