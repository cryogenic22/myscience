import { Info } from 'lucide-react';
import type { GraphEdge, MetricProvenance } from '../../api';
import { SOURCE_LABELS } from '../../brand';

/**
 * D6 — a small "source · as of <date>" caption so metric-card and graph-edge
 * claims are citeable instead of bare prose. Pure inline styles + design
 * tokens (no dynamic Tailwind class names).
 */

export interface ProvenanceFields {
  source?: string;
  asOf?: string | null;
  derivation?: string | null;
  realtimeFallback?: boolean;
}

/** Format an ISO timestamp down to its date portion; pass through if not ISO-ish. */
function fmtDate(iso: string): string {
  const m = iso.match(/^\d{4}-\d{2}-\d{2}/);
  return m ? m[0] : iso;
}

/** Friendly label for a source id (reuse the shared source registry). */
function sourceLabel(source: string): string {
  return SOURCE_LABELS[source] ?? source;
}

/** Pull a caption out of a metric row's `_provenance` block (D6). */
export function metricProvenanceCaption(prov: MetricProvenance | undefined | null): ProvenanceFields | null {
  if (!prov || !prov.source) return null;
  return {
    source: prov.source,
    asOf: prov.computed_at || null,
    derivation: prov.derivation || null,
    realtimeFallback: prov.realtime_fallback,
  };
}

/** Pull a caption out of a graph edge (D6: provenance_source/as_of, with fallback). */
export function graphEdgeProvenanceCaption(edge: GraphEdge): ProvenanceFields | null {
  const source = edge.provenance_source || edge.source || edge.via;
  if (!source) return null;
  return { source, asOf: edge.as_of ?? null };
}

export default function ProvenanceCaption({
  source,
  asOf,
  derivation,
  realtimeFallback,
}: ProvenanceFields) {
  if (!source) return null;

  const title = [
    derivation ? `Derivation: ${derivation}` : null,
    realtimeFallback ? 'Computed live from base tables (materialized view unavailable).' : null,
  ].filter(Boolean).join('\n') || undefined;

  return (
    <span
      data-testid="provenance-caption"
      title={title}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '4px',
        fontSize: '10px',
        color: 'var(--color-ink-4)',
        cursor: derivation ? 'help' : 'default',
      }}
    >
      <Info size={9} style={{ flexShrink: 0, opacity: 0.7 }} />
      <span>
        {sourceLabel(source)}
        {realtimeFallback && <span style={{ color: 'var(--color-amber)' }}> · live</span>}
        {asOf && <> · as of {fmtDate(asOf)}</>}
      </span>
    </span>
  );
}
