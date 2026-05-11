import { useEffect, useState } from 'react';
import type { Dossier, DossierEntityType } from '../types/dossier';

/**
 * PB-301 — Dossier hook.
 *
 * While BE-6 (`GET /dossier/{type}/{slug}`) is unmerged this returns
 * a mock dossier so the frontend scaffold can be built and reviewed.
 * When BE-6 lands, replace the body of `fetchDossier` with a real
 * `fetch(`${BASE}/dossier/${type}/${slug}`)` call and drop the
 * `is_mock` flag from the returned payload.
 */

export interface UseDossierResult {
  data: Dossier | null;
  error: Error | null;
  isLoading: boolean;
}

const MOCK_FIXTURES: Record<string, Dossier> = {
  'drug/tirzepatide': {
    entity: {
      id: 'ent-tirzepatide',
      slug: 'tirzepatide',
      type: 'drug',
      canonical_name: 'tirzepatide',
      aliases: ['Mounjaro', 'Zepbound', 'LY3298176'],
      external_ids: { rxnorm: '2589007', chembl: 'CHEMBL4297535' },
      primary_attributes: {
        mechanism: 'GIP/GLP-1 dual agonist',
        company: 'Eli Lilly',
        approval_date: '2022-05-13',
      },
      updated_at: '2026-05-09T12:00:00Z',
    },
    synthesis: {
      summary:
        'Tirzepatide is a dual GIP/GLP-1 receptor agonist approved in 2022 for type 2 diabetes (Mounjaro) and chronic weight management (Zepbound). Lilly reported $5.4B in Q1 2026 Mounjaro revenue and Phase 3 SURPASS-PEDS hit its primary endpoint in April 2026.',
      citations: [],
    },
    recent_moves: [],
    evidence: [
      { id: 'ev-1', source_name: 'ClinicalTrials.gov', tier: 'T1', published_at: '2026-04-15', snippet: 'SURPASS-PEDS Phase 3 trial primary endpoint met.' },
      { id: 'ev-2', source_name: 'FDA Orange Book', tier: 'T1', published_at: '2026-03-10', snippet: 'Patent expiry 2036.' },
      { id: 'ev-3', source_name: 'PubMed', tier: 'T3', published_at: '2026-02-20', snippet: 'NEJM publication — SURPASS-1 5-year follow-up.' },
      { id: 'ev-4', source_name: 'SEC EDGAR', tier: 'T2', published_at: '2026-01-30', snippet: 'Lilly Q1 8-K — Mounjaro $5.4B revenue.' },
    ],
    watchers: [],
    watcher_count: 0,
    is_mock: true,
  },
};

function buildMockKey(entityType: DossierEntityType, slug: string): string {
  return `${entityType}/${slug.toLowerCase()}`;
}

async function fetchDossier(
  entityType: DossierEntityType,
  slug: string,
): Promise<Dossier> {
  // TODO(BE-6 / PR #57): swap this for
  //   const res = await fetch(`${BASE}/dossier/${entityType}/${slug}`);
  //   if (!res.ok) {
  //     const err = new Error(`${res.status} ${res.statusText}`) as Error & { status?: number };
  //     err.status = res.status;
  //     throw err;
  //   }
  //   return res.json();
  const key = buildMockKey(entityType, slug);
  const fixture = MOCK_FIXTURES[key];
  if (!fixture) {
    const err = new Error('not found') as Error & { status?: number };
    err.status = 404;
    throw err;
  }
  return fixture;
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
