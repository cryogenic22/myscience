/**
 * DataHub · Phase 0 · Lens A (L1) — Catalog Home + Source dossier.
 *
 * Screen 1 (Catalog home): a searchable / filterable grid of every connected
 * source — connector type, live status verdict (from connector_health), the
 * kind of data it emits, and a FAIR / quality summary ring. Filter by
 * connector type and status; search by name. Click a card to open the
 * source dossier.
 *
 * Screen 2 (Source dossier): the 5-dimension FAIR breakdown with meters, a
 * schema preview (fields collected), and coverage + freshness for one source.
 *
 * Headless — props in, callbacks out, mirroring SourcesPage. The live wiring
 * (mapping CatalogDataset + pipeline-status + fair_scores onto these props)
 * is L1b; this lens is DB-free and composition-only over existing API shapes.
 *
 * Styling: CSS custom properties + inline styles (no Tailwind color utilities,
 * no dynamically-built class names — the v4 scanner can't see them).
 */
import { useMemo, useState } from 'react';

// ── Public types (shaped to the existing api.ts contracts) ──────────

/** Connector status verdict — mirrors connector_health / pipeline-status. */
export type CatalogStatus = 'fresh' | 'ok' | 'stale' | 'error' | 'never' | 'unknown';

/** The five FAIR dimensions surfaced in the dossier (entity-profile shape). */
export interface FairBreakdown {
  completeness: number;
  source_diversity: number;
  freshness: number;
  link_density: number;
  resolution: number;
  overall: number;
}

/** One row in the catalog grid — a connected source / dataset. */
export interface CatalogSource {
  source_key: string;
  /** Display label (falls back to source_key). */
  label: string;
  /** Connector kind, e.g. "regulatory_api", "rest", "csv". */
  connector_type: string;
  /** The kind of data emitted, e.g. "trial", "company". */
  data_type: string | null;
  status: CatalogStatus;
  records: number;
  /** Overall FAIR / quality score in [0,1], or null while profiling. */
  fair_overall: number | null;
  freshness_days: number | null;
}

/** The drill-in dossier for one source. */
export interface SourceDetail {
  source_key: string;
  label: string;
  connector_type: string;
  schedule: string;
  license: string | null;
  fair: FairBreakdown | null;
  /** Schema preview — the fields this source collects. */
  fields_collected: string[];
  records: number;
  freshness_days: number | null;
  /** Per-entity-type coverage breakdown. */
  coverage: Array<{ entity_type: string; count: number }>;
}

export interface CatalogHomePageProps {
  sources: CatalogSource[];
  /** The open dossier, or null when the grid is shown. */
  selected: SourceDetail | null;
  selectedLoading?: boolean;
  onSelectSource: (sourceKey: string) => void;
  onCloseDetail: () => void;
  onRefresh?: () => void;
}

// ── Tones ───────────────────────────────────────────────────────────

const STATUS_TONE: Record<CatalogStatus, { tone: string; label: string }> = {
  fresh:   { tone: 'var(--color-green, #15803d)', label: 'fresh' },
  ok:      { tone: 'var(--color-green, #15803d)', label: 'ok' },
  stale:   { tone: 'var(--color-amber)',          label: 'stale' },
  error:   { tone: 'var(--color-red)',            label: 'error' },
  never:   { tone: 'var(--color-red)',            label: 'never run' },
  unknown: { tone: 'var(--color-ink-4)',          label: 'unknown' },
};

/** FAIR / quality ring tone by score band. */
function fairTone(score: number | null): string {
  if (score === null) return 'var(--color-line)';
  if (score >= 0.75) return 'var(--color-green, #15803d)';
  if (score >= 0.5) return 'var(--color-amber)';
  return 'var(--color-red)';
}

function fairLabel(score: number | null): string {
  return score === null ? '–' : String(Math.round(score * 100));
}

function freshnessLabel(days: number | null): string {
  if (days === null) return 'unknown';
  if (days <= 0) return 'today';
  if (days === 1) return '1 day';
  if (days < 30) return `${days} days`;
  const months = Math.round(days / 30);
  return months === 1 ? '1 mo' : `${months} mo`;
}

function connectorTypeLabel(key: string): string {
  return key.replace(/_/g, ' ');
}

// ── Atoms ───────────────────────────────────────────────────────────

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        fontFamily: 'var(--font-mono)',
        fontSize: 10.5,
        letterSpacing: '0.16em',
        textTransform: 'uppercase',
        color: 'var(--color-ink-3)',
        marginBottom: 12,
      }}
    >
      {children}
    </div>
  );
}

function FairRing({ score }: { score: number | null }) {
  const tone = fairTone(score);
  return (
    <div
      data-fair-ring
      title={score === null ? 'profiling…' : `FAIR ${Math.round(score * 100)}`}
      style={{
        width: 34,
        height: 34,
        borderRadius: '50%',
        display: 'grid',
        placeItems: 'center',
        background: tone,
        color: score === null ? 'var(--color-ink-3)' : '#fff',
        fontSize: 11,
        fontWeight: 800,
        flexShrink: 0,
        border: score === null ? '1px dashed var(--color-line-2, var(--color-line))' : 'none',
      }}
    >
      {fairLabel(score)}
    </div>
  );
}

function StatusBadge({ status }: { status: CatalogStatus }) {
  const { tone, label } = STATUS_TONE[status];
  return (
    <span
      data-status-badge={status}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 5,
        fontFamily: 'var(--font-mono)',
        fontSize: 9.5,
        letterSpacing: '0.14em',
        textTransform: 'uppercase',
        padding: '2px 7px',
        border: `1px solid ${tone}`,
        color: tone,
        fontWeight: 600,
      }}
    >
      <span
        style={{
          width: 6,
          height: 6,
          borderRadius: '50%',
          background: tone,
          flexShrink: 0,
        }}
      />
      {label}
    </span>
  );
}

// ── Source dossier (Screen 2) ───────────────────────────────────────

const FAIR_DIMS: Array<{ key: keyof FairBreakdown; label: string }> = [
  { key: 'completeness', label: 'Completeness' },
  { key: 'source_diversity', label: 'Source diversity' },
  { key: 'freshness', label: 'Freshness' },
  { key: 'link_density', label: 'Link density' },
  { key: 'resolution', label: 'Resolution' },
];

function SourceDossier({
  detail,
  loading,
  onClose,
}: {
  detail: SourceDetail | null;
  loading: boolean;
  onClose: () => void;
}) {
  return (
    <section
      data-source-dossier={detail?.source_key ?? ''}
      aria-label="Source dossier"
      style={{
        background: 'var(--color-surface)',
        border: '1px solid var(--color-line)',
        borderRadius: 14,
        padding: '20px 22px',
      }}
    >
      {/* Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          gap: 12,
          paddingBottom: 14,
          borderBottom: '1px solid var(--color-line)',
        }}
      >
        <div style={{ minWidth: 0 }}>
          <h2
            style={{
              fontFamily: 'var(--font-display)',
              fontSize: 20,
              fontWeight: 500,
              color: 'var(--color-ink)',
              letterSpacing: '-0.02em',
              margin: 0,
            }}
          >
            {detail ? detail.label : 'Loading…'}
          </h2>
          {detail && (
            <div
              style={{
                marginTop: 6,
                display: 'flex',
                gap: 14,
                flexWrap: 'wrap',
                fontFamily: 'var(--font-mono)',
                fontSize: 11,
                color: 'var(--color-ink-3)',
                letterSpacing: '0.04em',
              }}
            >
              <span>{connectorTypeLabel(detail.connector_type)}</span>
              <span>schedule: {detail.schedule}</span>
              <span>license: {detail.license ?? '—'}</span>
              <span>records: {detail.records.toLocaleString()}</span>
              <span>freshness: {freshnessLabel(detail.freshness_days)}</span>
            </div>
          )}
        </div>
        <button
          type="button"
          data-action="close-dossier"
          onClick={onClose}
          aria-label="Close dossier"
          style={{
            background: 'transparent',
            border: '1px solid var(--color-line)',
            borderRadius: 8,
            color: 'var(--color-ink-3)',
            cursor: 'pointer',
            padding: '4px 10px',
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            flexShrink: 0,
          }}
        >
          ← Back to catalog
        </button>
      </div>

      {loading || !detail ? (
        <div
          style={{
            padding: '24px 0',
            color: 'var(--color-ink-3)',
            fontSize: 13,
          }}
        >
          Loading profile…
        </div>
      ) : (
        <div style={{ paddingTop: 16, display: 'flex', flexDirection: 'column', gap: 22 }}>
          {/* FAIR breakdown */}
          <div>
            <SectionLabel>
              FAIR profile{detail.fair ? ` · overall ${detail.fair.overall.toFixed(2)}` : ' · profiling'}
            </SectionLabel>
            {detail.fair ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {FAIR_DIMS.map((dim) => {
                  const v = detail.fair![dim.key];
                  const pct = Math.round(v * 100);
                  return (
                    <div
                      key={dim.key}
                      data-fair-dim={dim.key}
                      style={{ display: 'flex', alignItems: 'center', gap: 10 }}
                    >
                      <span
                        style={{
                          fontSize: 12,
                          color: 'var(--color-ink-2)',
                          width: 130,
                          flexShrink: 0,
                        }}
                      >
                        {dim.label}
                      </span>
                      <span
                        style={{
                          fontFamily: 'var(--font-mono)',
                          fontSize: 11,
                          fontWeight: 600,
                          color: 'var(--color-ink-2)',
                          width: 40,
                          textAlign: 'right',
                          flexShrink: 0,
                        }}
                      >
                        {v.toFixed(2)}
                      </span>
                      <div
                        style={{
                          flex: 1,
                          height: 6,
                          borderRadius: 3,
                          background: 'var(--color-surface-3)',
                          overflow: 'hidden',
                        }}
                      >
                        <div
                          style={{
                            width: `${pct}%`,
                            height: '100%',
                            borderRadius: 3,
                            background: fairTone(v),
                          }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div style={{ color: 'var(--color-ink-4)', fontSize: 13, fontStyle: 'italic' }}>
                FAIR profile pending — this source has not been scored yet.
              </div>
            )}
          </div>

          {/* Schema preview */}
          <div>
            <SectionLabel>Schema preview · {detail.fields_collected.length} fields</SectionLabel>
            {detail.fields_collected.length === 0 ? (
              <div style={{ color: 'var(--color-ink-4)', fontSize: 13, fontStyle: 'italic' }}>
                No schema recorded.
              </div>
            ) : (
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {detail.fields_collected.map((f) => (
                  <span
                    key={f}
                    data-schema-field={f}
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: 11,
                      color: 'var(--color-ink-2)',
                      background: 'var(--color-surface-2)',
                      border: '1px solid var(--color-line)',
                      borderRadius: 6,
                      padding: '3px 8px',
                    }}
                  >
                    {f}
                  </span>
                ))}
              </div>
            )}
          </div>

          {/* Coverage */}
          <div>
            <SectionLabel>Coverage by type</SectionLabel>
            {detail.coverage.length === 0 ? (
              <div style={{ color: 'var(--color-ink-4)', fontSize: 13, fontStyle: 'italic' }}>
                No coverage recorded.
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {detail.coverage.map((c) => (
                  <div
                    key={c.entity_type}
                    data-coverage-row={c.entity_type}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      fontSize: 12.5,
                      color: 'var(--color-ink-2)',
                    }}
                  >
                    <span>{c.entity_type}</span>
                    <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>
                      {c.count.toLocaleString()}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  );
}

// ── Catalog grid (Screen 1) ─────────────────────────────────────────

const ALL_TYPES = '__all__';
const ALL_STATUS = '__all__';

export function CatalogHomePage(props: CatalogHomePageProps) {
  const { sources, selected, selectedLoading, onSelectSource, onCloseDetail, onRefresh } = props;
  const [query, setQuery] = useState('');
  const [typeFilter, setTypeFilter] = useState<string>(ALL_TYPES);
  const [statusFilter, setStatusFilter] = useState<string>(ALL_STATUS);

  const connectorTypes = useMemo(() => {
    const set = new Set(sources.map((s) => s.connector_type));
    return Array.from(set).sort();
  }, [sources]);

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return sources.filter((s) => {
      if (typeFilter !== ALL_TYPES && s.connector_type !== typeFilter) return false;
      if (statusFilter !== ALL_STATUS && s.status !== statusFilter) return false;
      if (q) {
        const hay = `${s.label} ${s.source_key} ${s.data_type ?? ''}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [sources, query, typeFilter, statusFilter]);

  // When a source is selected, show the dossier (Screen 2).
  if (selected || selectedLoading) {
    return (
      <main
        role="main"
        aria-label="Data catalog"
        style={{
          padding: '24px 28px 40px',
          background: 'var(--color-bg)',
          fontFamily: 'var(--font-body)',
          minHeight: '100%',
        }}
      >
        <SourceDossier detail={selected} loading={!!selectedLoading} onClose={onCloseDetail} />
      </main>
    );
  }

  return (
    <main
      role="main"
      aria-label="Data catalog"
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 22,
        padding: '24px 28px 40px',
        background: 'var(--color-bg)',
        color: 'var(--color-ink-2)',
        fontFamily: 'var(--font-body)',
        minHeight: '100%',
      }}
    >
      {/* Header */}
      <header
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: 8,
          paddingBottom: 18,
          borderBottom: '1px solid var(--color-divider, var(--color-line))',
        }}
      >
        <div
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 10.5,
            letterSpacing: '0.18em',
            textTransform: 'uppercase',
            color: 'var(--color-ink-3)',
          }}
        >
          DataHub · Catalog
        </div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 16, flexWrap: 'wrap' }}>
          <h1
            style={{
              fontFamily: 'var(--font-display)',
              fontSize: 30,
              fontWeight: 400,
              color: 'var(--color-ink)',
              letterSpacing: '-0.014em',
              margin: 0,
            }}
          >
            Every source, at a glance
          </h1>
          <span
            style={{
              marginLeft: 'auto',
              fontFamily: 'var(--font-mono)',
              fontSize: 12,
              color: 'var(--color-ink-2)',
              letterSpacing: '0.04em',
            }}
          >
            <strong style={{ color: 'var(--color-ink)' }}>{sources.length}</strong> sources
          </span>
          {onRefresh && (
            <button
              type="button"
              data-action="refresh-catalog"
              onClick={onRefresh}
              style={{
                background: 'transparent',
                border: '1px solid var(--color-line)',
                borderRadius: 8,
                color: 'var(--color-ink-3)',
                cursor: 'pointer',
                padding: '4px 10px',
                fontFamily: 'var(--font-mono)',
                fontSize: 11,
              }}
            >
              Refresh
            </button>
          )}
        </div>
      </header>

      {/* Controls */}
      <section style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
        <input
          type="search"
          aria-label="Search sources"
          placeholder="Search sources, datasets, entities…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          style={{
            flex: '1 1 260px',
            minWidth: 200,
            padding: '8px 12px',
            border: '1px solid var(--color-line)',
            borderRadius: 8,
            background: 'var(--color-surface)',
            color: 'var(--color-ink)',
            fontFamily: 'var(--font-body)',
            fontSize: 13,
          }}
        />
        <select
          aria-label="Filter by connector type"
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          style={{
            padding: '8px 12px',
            border: '1px solid var(--color-line)',
            borderRadius: 8,
            background: 'var(--color-surface)',
            color: 'var(--color-ink-2)',
            fontFamily: 'var(--font-mono)',
            fontSize: 12,
          }}
        >
          <option value={ALL_TYPES}>All connector types</option>
          {connectorTypes.map((t) => (
            <option key={t} value={t}>
              {connectorTypeLabel(t)}
            </option>
          ))}
        </select>
        <select
          aria-label="Filter by status"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          style={{
            padding: '8px 12px',
            border: '1px solid var(--color-line)',
            borderRadius: 8,
            background: 'var(--color-surface)',
            color: 'var(--color-ink-2)',
            fontFamily: 'var(--font-mono)',
            fontSize: 12,
          }}
        >
          <option value={ALL_STATUS}>All statuses</option>
          {(Object.keys(STATUS_TONE) as CatalogStatus[]).map((s) => (
            <option key={s} value={s}>
              {STATUS_TONE[s].label}
            </option>
          ))}
        </select>
      </section>

      {/* Grid */}
      <section>
        <SectionLabel>
          {visible.length === sources.length
            ? `${sources.length} connected sources`
            : `${visible.length} of ${sources.length} sources`}
        </SectionLabel>
        {visible.length === 0 ? (
          <div
            data-empty-state
            style={{
              padding: 18,
              border: '1px dashed var(--color-line-2, var(--color-line))',
              color: 'var(--color-ink-3)',
              fontSize: 13.5,
              fontStyle: 'italic',
            }}
          >
            No sources match this filter.
          </div>
        ) : (
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))',
              gap: 12,
            }}
          >
            {visible.map((s) => (
              <div
                key={s.source_key}
                data-source-card={s.source_key}
                role="button"
                tabIndex={0}
                onClick={() => onSelectSource(s.source_key)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    onSelectSource(s.source_key);
                  }
                }}
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 12,
                  padding: '14px 16px',
                  background: 'var(--color-surface)',
                  border: '1px solid var(--color-line)',
                  borderRadius: 12,
                  cursor: 'pointer',
                  transition: 'border-color 80ms ease',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 10 }}>
                  <div style={{ minWidth: 0 }}>
                    <div
                      style={{
                        fontFamily: 'var(--font-display)',
                        fontSize: 15,
                        fontWeight: 500,
                        color: 'var(--color-ink)',
                        lineHeight: 1.3,
                      }}
                    >
                      {s.label}
                    </div>
                    <div
                      style={{
                        marginTop: 4,
                        fontFamily: 'var(--font-mono)',
                        fontSize: 10.5,
                        letterSpacing: '0.04em',
                        color: 'var(--color-ink-3)',
                        textTransform: 'uppercase',
                      }}
                    >
                      {connectorTypeLabel(s.connector_type)}
                      {s.data_type ? ` · ${s.data_type}` : ''}
                    </div>
                  </div>
                  <FairRing score={s.fair_overall} />
                </div>

                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: 8,
                    flexWrap: 'wrap',
                  }}
                >
                  <StatusBadge status={s.status} />
                  <span
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: 11,
                      color: 'var(--color-ink-3)',
                    }}
                  >
                    {s.records.toLocaleString()} rows · {freshnessLabel(s.freshness_days)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}

export default CatalogHomePage;
