import { useEffect, useState } from 'react';
import { BASE } from '../api';
import type {
  Dossier,
  DossierEntityType,
  DossierEvidence,
  EvidenceTier,
} from '../types/dossier';

/**
 * `useDossier(type, slug)` — hits `GET /dossier/{type}/{slug}` and
 * adapts the BE-6 response into the frontend `Dossier` shape.
 */

export interface UseDossierResult {
  data: Dossier | null;
  error: Error | null;
  isLoading: boolean;
}

const KNOWN_EXTERNAL_ID_KEYS = new Set<string>([
  'rxnorm', 'chembl', 'unii', 'inn', 'cas',
  'ndc', 'gtin',
  'nct_id', 'nct',
  'cik', 'lei', 'ticker',
  'mesh_id', 'doi', 'pmid',
  'wikidata',
]);

const VALID_TIERS = new Set<EvidenceTier>(['T1', 'T2', 'T3', 'T4']);

function isScalar(v: unknown): v is string | number {
  return typeof v === 'string' || (typeof v === 'number' && Number.isFinite(v));
}

/**
 * Map the BE-6 wire shape onto the frontend `Dossier` shape.
 *
 * Exposed for unit testing.
 */
export function adaptDossierResponse(wire: any, slug: string): Dossier {
  const entityIn = wire?.entity ?? {};
  const idFields: Record<string, unknown> = entityIn.identity_fields ?? {};

  const externalIds: Record<string, string> = {};
  const primaryAttributes: Record<string, string | number> = {};
  for (const [k, v] of Object.entries(idFields)) {
    if (!isScalar(v)) continue;                                       // drop arrays / nested objects
    if (KNOWN_EXTERNAL_ID_KEYS.has(k.toLowerCase()) || k.endsWith('_id')) {
      externalIds[k] = String(v);
    } else {
      primaryAttributes[k] = v;
    }
  }

  // Some optional fields don't exist on every entity type; keep them
  // out of the attributes block to avoid clutter.
  delete (primaryAttributes as any).created_at;
  delete (primaryAttributes as any).updated_at;
  delete (primaryAttributes as any).description_embedding;

  const synthesisIn = wire?.synthesis ?? null;
  const synthesis = synthesisIn
    ? {
        summary: String(synthesisIn.text_with_citation_marks ?? synthesisIn.summary ?? ''),
        citations: [],
      }
    : null;

  const evidence: DossierEvidence[] = (wire?.evidence_refs ?? []).map((e: any): DossierEvidence => {
    const tier = (typeof e?.source_tier === 'string' && VALID_TIERS.has(e.source_tier as EvidenceTier))
      ? (e.source_tier as EvidenceTier)
      : ('T3' as EvidenceTier);
    return {
      id: String(e?.evidence_id ?? e?.id ?? ''),
      source_name: String(e?.source_name ?? '—'),
      tier,
      published_at: String(e?.published_at ?? ''),
      snippet: String(e?.snippet ?? ''),
    };
  });

  const watchers = (wire?.watching ?? []).map((w: any) => ({
    user_id: String(w?.user_id ?? ''),
    display_name: String(w?.name ?? w?.display_name ?? ''),
    avatar_url: w?.avatar_url ?? null,
  }));

  const updatedAt =
    typeof primaryAttributes.updated_at === 'string'
      ? primaryAttributes.updated_at
      : new Date().toISOString();

  return {
    entity: {
      id: String(entityIn.id ?? ''),
      slug,
      type: entityIn.type as DossierEntityType,
      canonical_name: String(entityIn.name ?? ''),
      aliases: Array.isArray(entityIn.aliases) ? entityIn.aliases.map(String) : [],
      external_ids: externalIds,
      primary_attributes: primaryAttributes,
      updated_at: updatedAt,
    },
    synthesis,
    recent_moves: [],
    evidence,
    watchers,
    watcher_count: watchers.length,
  };
}

async function fetchDossier(
  entityType: DossierEntityType,
  slug: string,
): Promise<Dossier> {
  const res = await fetch(`${BASE}/dossier/${encodeURIComponent(entityType)}/${encodeURIComponent(slug)}`);
  if (!res.ok) {
    const err = new Error(`${res.status} ${res.statusText}`) as Error & { status?: number };
    err.status = res.status;
    throw err;
  }
  const wire = await res.json();
  return adaptDossierResponse(wire, slug);
}

export function useDossier(
  entityType: DossierEntityType | undefined,
  slug: string | undefined,
): UseDossierResult {
  const [data, setData] = useState<Dossier | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(Boolean(entityType && slug));

  useEffect(() => {
    let cancelled = false;
    if (!entityType || !slug) {
      setData(null);
      setError(null);
      setIsLoading(false);
      return;
    }
    setIsLoading(true);
    setError(null);
    fetchDossier(entityType, slug)
      .then((d) => {
        if (!cancelled) {
          setData(d);
          setIsLoading(false);
        }
      })
      .catch((e: Error) => {
        if (!cancelled) {
          setData(null);
          setError(e);
          setIsLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [entityType, slug]);

  return { data, error, isLoading };
}
