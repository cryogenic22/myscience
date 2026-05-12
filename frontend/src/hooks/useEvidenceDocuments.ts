/**
 * Loop #19 — Resolve a batch of evidence ids to display metadata.
 *
 * Caches by sorted-id key for the lifetime of the page so flipping
 * between signal detail panels doesn't re-fetch the same set.
 */
import { useEffect, useState } from 'react';
import { evidenceApi } from '../api';
import type { EvidenceDocument } from '../types/evidence';

const cache = new Map<string, EvidenceDocument[]>();

function cacheKey(ids: readonly string[]): string {
  return [...ids].sort().join('|');
}

export interface UseEvidenceDocumentsResult {
  documents: EvidenceDocument[];
  loading: boolean;
  error: string | null;
}

export function useEvidenceDocuments(
  ids: readonly string[],
): UseEvidenceDocumentsResult {
  const key = cacheKey(ids);
  const [documents, setDocuments] = useState<EvidenceDocument[]>(
    () => cache.get(key) ?? [],
  );
  const [loading, setLoading] = useState<boolean>(!cache.has(key) && ids.length > 0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (ids.length === 0) {
      setDocuments([]);
      setLoading(false);
      return;
    }
    if (cache.has(key)) {
      setDocuments(cache.get(key)!);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    evidenceApi
      .byIds([...ids])
      .then((res) => {
        if (cancelled) return;
        cache.set(key, res.documents);
        setDocuments(res.documents);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(String(e?.message ?? e));
        setDocuments([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [key, ids]);

  return { documents, loading, error };
}
