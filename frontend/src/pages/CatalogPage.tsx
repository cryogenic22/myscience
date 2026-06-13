/**
 * DataHub · Phase 0 · Lens A (L1b) — CatalogPage container.
 *
 * Wires the headless {@link CatalogHomePage} lens to the existing read-API:
 *   - api.catalogDatasets()       → the source grid (records, FAIR overall, data type, freshness)
 *   - api.catalogPipelineStatus() → the per-source live status verdict (joined by source_key)
 *   - api.datasetProfile(key)     → the drill-in source dossier (schema + coverage)
 *
 * Container state machine mirrors ConnectorsPage / SourcesContainer:
 *   loading → ready (grid) → (select) dossier → error.
 *
 * Source-level data quality comes from D-API-2 (`/catalog/datasets/{key}/fair`):
 * the grid ring uses the dataset's `fair_overall` composite, and the dossier
 * fetches the per-dimension breakdown. It is a derived ingest-health composite,
 * NOT a formal FAIR audit, so the UI labels it "Quality" (per cross-lane review
 * MZ-XR-20260613-004). A profile-load failure surfaces an explicit error+retry
 * dossier (not a silent empty card that looks unprofiled).
 *
 * Styling: the lens owns all visuals (CSS custom properties + inline styles);
 * this container only renders loading / error chrome in the same idiom.
 */
import { useCallback, useEffect, useState } from 'react';
import {
  api,
  type CatalogDataset,
  type DatasetProfile,
  type DatasetFairResponse,
} from '../api';
import {
  CatalogHomePage,
  type CatalogSource,
  type CatalogStatus,
  type QualityBreakdown,
  type SourceDetail,
} from './CatalogHomePage';

/** Pipeline-status verdict strings the backend emits (api.catalogPipelineStatus). */
type PipelineStatusStr = string;

/** Map a connectors/pipeline status string to the lens' CatalogStatus union. */
function toCatalogStatus(status: PipelineStatusStr | undefined): CatalogStatus {
  switch (status) {
    case 'fresh':
    case 'ok':
    case 'stale':
    case 'error':
    case 'never':
      return status;
    default:
      return 'unknown';
  }
}

/**
 * Derive a coarse connector "type" for the grid badge from what this branch's
 * read-API exposes (no connector-type taxonomy endpoint yet — that's L2 / #245).
 * Presentation-only; falls back to the dataset's source_type.
 */
function deriveConnectorType(ds: CatalogDataset): string {
  const key = (ds.source_type || '').toLowerCase();
  if (key.includes('clinical') || key.includes('fda') || key.includes('openfda')) return 'regulatory_api';
  if (key.includes('pubmed') || key.includes('pmc') || key.includes('literature')) return 'scientific_literature';
  if (key.includes('sec') || key.includes('edgar')) return 'corporate_filing';
  if (key.includes('nadac') || key.includes('csv')) return 'csv';
  if (key.includes('mesh') || key.includes('ontology')) return 'ontology';
  return ds.source_type || 'source';
}

function toSource(
  ds: CatalogDataset,
  statusByKey: Map<string, PipelineStatusStr>,
): CatalogSource {
  const key = ds.source_type;
  const records = ds.row_count ?? 0;
  // Status verdict comes from the live pipeline-status feed; absent ⇒ unknown
  // (rows can exist with no scheduled connector, e.g. backfill).
  const status = statusByKey.has(key)
    ? toCatalogStatus(statusByKey.get(key))
    : records > 0
      ? 'unknown'
      : 'never';
  return {
    source_key: key,
    label: ds.dataset_name || key,
    connector_type: deriveConnectorType(ds),
    data_type: ds.entity_type,
    status,
    records,
    // D-API-2 derived quality composite; fall back to the raw quality score,
    // then null (⇒ lens renders the placeholder ring). Never fabricated.
    quality_overall: ds.fair_overall ?? ds.quality_score_avg ?? null,
    freshness_days: ds.freshness_days ?? null,
  };
}

/** Human labels for the D-API-2 quality dimensions (server returns snake_case keys). */
const QUALITY_DIM_LABELS: Record<string, string> = {
  completeness: 'Completeness',
  quality: 'Data quality',
  accessibility: 'Accessibility',
  license_openness: 'License openness',
};

/** Map the D-API-2 FAIR response into the lens' generic QualityBreakdown. */
function toQuality(f: DatasetFairResponse): QualityBreakdown {
  const dimensions = Object.entries(f.by_dimension ?? {}).map(([key, d]) => ({
    key,
    label: QUALITY_DIM_LABELS[key] ?? key.replace(/_/g, ' '),
    value: d.value,
    explanation: d.explanation,
  }));
  return { overall: f.fair_overall, dimensions };
}

function toDetail(p: DatasetProfile, quality: QualityBreakdown | null): SourceDetail {
  return {
    source_key: p.source_key,
    label: p.display_name || p.source_key,
    connector_type: p.collection_method || 'source',
    schedule: p.refresh_schedule || 'unknown',
    license: null, // DatasetProfile carries no license field on this branch.
    quality,
    fields_collected: p.fields_collected ?? [],
    records: p.records ?? 0,
    // DatasetProfile.freshness is a human label, not a day count — keep the
    // dossier honest by not coercing it into a number.
    freshness_days: null,
    // Per-entity-type counts aren't exposed on the profile (only the type
    // list + a total) — surface coverage as the types this source feeds.
    coverage: [],
  };
}

export default function CatalogPage() {
  const [sources, setSources] = useState<CatalogSource[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selected, setSelected] = useState<SourceDetail | null>(null);
  const [selectedLoading, setSelectedLoading] = useState(false);

  const load = useCallback(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([api.catalogDatasets(), api.catalogPipelineStatus()])
      .then(([datasetsRes, pipelineRes]) => {
        if (cancelled) return;
        const statusByKey = new Map<string, PipelineStatusStr>();
        for (const c of pipelineRes.connectors ?? []) {
          statusByKey.set(c.source_key, c.status);
        }
        const rows = (datasetsRes.datasets ?? []).map((ds) => toSource(ds, statusByKey));
        setSources(rows);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => load(), [load]);

  const openSource = useCallback((sourceKey: string) => {
    setSelected(null);
    setSelectedLoading(true);
    // Fetch the dossier profile + the D-API-2 quality breakdown independently:
    // the profile drives the dossier, the FAIR breakdown is an enhancement that
    // degrades to null on its own without failing the whole view.
    Promise.allSettled([api.datasetProfile(sourceKey), api.datasetFair(sourceKey)])
      .then(([profileRes, fairRes]) => {
        const quality =
          fairRes.status === 'fulfilled' ? toQuality(fairRes.value) : null;
        if (profileRes.status === 'fulfilled') {
          setSelected(toDetail(profileRes.value, quality));
          return;
        }
        // Profile load FAILED — surface an explicit error+retry dossier (with the
        // source key) rather than a silent empty card that reads as "unprofiled
        // but valid" (cross-lane review MZ-XR-20260613-004).
        const reason =
          profileRes.reason instanceof Error
            ? profileRes.reason.message
            : String(profileRes.reason);
        setSelected({
          source_key: sourceKey,
          label: sourceKey,
          connector_type: 'source',
          schedule: 'unknown',
          license: null,
          quality,
          loadError: reason,
          fields_collected: [],
          records: 0,
          freshness_days: null,
          coverage: [],
        });
        if (typeof console !== 'undefined') {
          console.warn(`datasetProfile(${sourceKey}) failed:`, profileRes.reason);
        }
      })
      .finally(() => setSelectedLoading(false));
  }, []);

  const closeDetail = useCallback(() => {
    setSelected(null);
    setSelectedLoading(false);
  }, []);

  if (loading) {
    return (
      <div
        data-testid="catalog-loading"
        style={{
          padding: 'var(--space-7, 40px)',
          color: 'var(--color-ink-3)',
          fontFamily: 'var(--font-mono)',
          fontSize: 12,
        }}
      >
        Loading catalog…
      </div>
    );
  }

  if (error) {
    return (
      <div data-testid="catalog-error" style={{ padding: 'var(--space-7, 40px)' }}>
        <p
          style={{
            margin: '0 0 8px',
            color: 'var(--color-red)',
            fontFamily: 'var(--font-mono)',
            fontSize: 13,
          }}
        >
          Catalog unavailable — {error}
        </p>
        <button
          type="button"
          onClick={load}
          style={{
            padding: '8px 14px',
            fontFamily: 'var(--font-mono)',
            fontSize: 12,
            border: '1px solid var(--color-line)',
            borderRadius: 8,
            cursor: 'pointer',
            background: 'var(--color-surface-2)',
            color: 'var(--color-ink)',
          }}
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <CatalogHomePage
      sources={sources}
      selected={selected}
      selectedLoading={selectedLoading}
      onSelectSource={openSource}
      onCloseDetail={closeDetail}
      onRefresh={load}
    />
  );
}
