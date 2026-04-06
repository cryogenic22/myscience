import { type ReactNode, useCallback, useEffect, useState } from 'react';
import {
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  RefreshCw,
  X,
} from 'lucide-react';
import { api } from '../api';
import type {
  SourceProfileData,
  SourceRecordsResponse,
  SourceConnectionsResponse,
} from '../api';
import { displayName, SOURCE_LABELS, ENTITY_TYPE_LABELS } from '../brand';

/* ── Helpers ── */

const ENTITY_COLORS: Record<string, string> = {
  drug: 'var(--color-drug)',
  company: 'var(--color-company)',
  trial: 'var(--color-trial)',
  therapeutic_area: 'var(--color-ta)',
  mechanism: 'var(--color-mechanism)',
  literature: 'var(--color-literature)',
  event: 'var(--color-amber)',
  investigator: 'var(--color-ink-3)',
  patent: 'var(--color-ink-3)',
  biomarker: 'var(--color-green)',
};

function entityColor(type: string): string {
  return ENTITY_COLORS[type] ?? 'var(--color-ink-3)';
}

function relativeTime(dateStr: string): string {
  const now = Date.now();
  const then = new Date(dateStr).getTime();
  const diffMs = now - then;
  const mins = Math.floor(diffMs / 60_000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  const months = Math.floor(days / 30);
  return `${months}mo ago`;
}

function formatNumber(n: number): string {
  return n.toLocaleString();
}

function completenessColor(pct: number): string {
  if (pct >= 70) return 'var(--color-green)';
  if (pct >= 40) return 'var(--color-amber)';
  return 'var(--color-red)';
}

function completenessBg(pct: number): string {
  if (pct >= 70) return 'var(--color-green-soft)';
  if (pct >= 40) return 'var(--color-amber-soft)';
  return 'var(--color-red-soft)';
}

type SourceStatus = 'Live' | 'OK' | 'Stale' | 'Never' | 'Error';

function resolveStatus(status: string): SourceStatus {
  const s = status.toLowerCase();
  if (s === 'live') return 'Live';
  if (s === 'ok') return 'OK';
  if (s === 'stale') return 'Stale';
  if (s === 'never') return 'Never';
  if (s === 'error') return 'Error';
  return 'OK';
}

const STATUS_COLORS: Record<SourceStatus, { dot: string; bg: string; text: string }> = {
  Live:  { dot: 'var(--color-green)', bg: 'var(--color-green-soft)', text: 'var(--color-green)' },
  OK:    { dot: 'var(--color-green)', bg: 'var(--color-green-soft)', text: 'var(--color-green)' },
  Stale: { dot: 'var(--color-amber)', bg: 'var(--color-amber-soft)', text: 'var(--color-amber)' },
  Never: { dot: 'var(--color-red)',   bg: 'var(--color-red-soft)',   text: 'var(--color-red)' },
  Error: { dot: 'var(--color-red)',   bg: 'var(--color-red-soft)',   text: 'var(--color-red)' },
};

function stewardIcon(status: string): { icon: string; color: string } {
  const s = status.toLowerCase();
  if (s === 'completed' || s === 'success' || s === 'done') {
    return { icon: '\u2713', color: 'var(--color-green)' };
  }
  if (s === 'pending' || s === 'warning') {
    return { icon: '\u26A0', color: 'var(--color-amber)' };
  }
  if (s === 'failed' || s === 'error') {
    return { icon: '\u2717', color: 'var(--color-red)' };
  }
  return { icon: '\u2022', color: 'var(--color-ink-3)' };
}

/* ── Props ── */

interface SourceProfileCardProps {
  data: SourceProfileData | null;
  isLoading: boolean;
  error: string | null;
  onClose: () => void;
  onRefresh: () => void;
}

/* ── Skeleton ── */

function Skeleton({ width, height }: { width?: string; height?: string }) {
  return (
    <div
      style={{
        width: width ?? '100%',
        height: height ?? '14px',
        borderRadius: '6px',
        background: 'var(--color-surface-3)',
        animation: 'skeleton-pulse 1.5s ease-in-out infinite',
      }}
    />
  );
}

function SkeletonSection() {
  return (
    <div style={{ marginBottom: '24px' }}>
      <Skeleton width="30%" height="12px" />
      <div style={{ marginTop: '12px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
        <Skeleton width="80%" />
        <Skeleton width="65%" />
        <Skeleton width="50%" />
      </div>
    </div>
  );
}

/* ── Collapsible Section ── */

function Section({
  title,
  defaultOpen = true,
  children,
  badge,
}: {
  title: string;
  defaultOpen?: boolean;
  children: ReactNode;
  badge?: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div style={{ marginBottom: '4px' }}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        style={{
          width: '100%',
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
          padding: '10px 0',
          background: 'none',
          border: 'none',
          cursor: 'pointer',
          borderBottom: open ? '1px solid var(--color-line)' : 'none',
        }}
      >
        {open
          ? <ChevronDown size={13} style={{ color: 'var(--color-ink-4)', flexShrink: 0 }} />
          : <ChevronRight size={13} style={{ color: 'var(--color-ink-4)', flexShrink: 0 }} />}
        <span style={{
          fontSize: '11px',
          fontWeight: 600,
          textTransform: 'uppercase',
          letterSpacing: '0.06em',
          color: 'var(--color-ink-3)',
          flex: 1,
          textAlign: 'left',
        }}>
          {title}
        </span>
        {badge}
      </button>
      {open && (
        <div style={{ padding: '12px 0 8px' }}>
          {children}
        </div>
      )}
    </div>
  );
}

/* ── Entity Dot ── */

function EntityDot({ type, size = 10 }: { type: string; size?: number }) {
  return (
    <span
      style={{
        display: 'inline-block',
        width: `${size}px`,
        height: `${size}px`,
        borderRadius: '50%',
        background: entityColor(type),
        flexShrink: 0,
      }}
    />
  );
}

/* ── Cell rendering utilities ── */

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function formatCellValue(value: unknown): string {
  if (value === null || value === undefined) return '\u2014';
  if (typeof value === 'string') {
    if (UUID_RE.test(value)) return value.slice(0, 8) + '\u2026';
    // ISO date detection
    if (/^\d{4}-\d{2}-\d{2}T/.test(value)) {
      return value.slice(0, 10);
    }
    if (value.length > 80) return value.slice(0, 77) + '\u2026';
    return value;
  }
  if (Array.isArray(value)) {
    if (value.length === 0) return '\u2014';
    const shown = value.slice(0, 3).join(', ');
    return value.length > 3 ? `${shown} (+${value.length - 3})` : shown;
  }
  if (typeof value === 'number') return value.toLocaleString();
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  return String(value);
}

function cellTitle(value: unknown): string | undefined {
  if (typeof value === 'string' && value.length > 80) return value;
  if (typeof value === 'string' && UUID_RE.test(value)) return value;
  return undefined;
}

/* ── Sample Records Table ── */

function SampleRecordsSection({
  sourceKey,
  entityBreakdown,
}: {
  sourceKey: string;
  entityBreakdown: Array<{ entity_type: string; count: number }>;
}) {
  const [data, setData] = useState<SourceRecordsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedType, setSelectedType] = useState<string | undefined>(undefined);
  const [currentOffset, setCurrentOffset] = useState(0);
  const pageSize = 20;

  const fetchRecords = useCallback((entityType?: string, offset = 0) => {
    setLoading(true);
    setError(null);
    api.sourceRecords(sourceKey, {
      entity_type: entityType,
      limit: pageSize,
      offset,
    })
      .then((res) => {
        setData(res);
        setCurrentOffset(offset);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [sourceKey]);

  useEffect(() => {
    fetchRecords(selectedType, 0);
  }, [fetchRecords, selectedType]);

  const hasMultipleTypes = entityBreakdown.length > 1;
  const totalPages = data ? Math.ceil(data.total / pageSize) : 0;
  const currentPage = Math.floor(currentOffset / pageSize) + 1;

  return (
    <div>
      {/* Entity type selector */}
      {hasMultipleTypes && (
        <div style={{
          display: 'flex',
          gap: '6px',
          marginBottom: '10px',
          flexWrap: 'wrap',
        }}>
          {entityBreakdown.map((eb) => (
            <button
              key={eb.entity_type}
              type="button"
              onClick={() => { setSelectedType(eb.entity_type); setCurrentOffset(0); }}
              style={{
                padding: '3px 10px',
                borderRadius: '8px',
                border: '1px solid var(--color-line)',
                background: (selectedType ?? entityBreakdown[0]?.entity_type) === eb.entity_type
                  ? 'var(--color-accent)'
                  : 'var(--color-surface-2)',
                color: (selectedType ?? entityBreakdown[0]?.entity_type) === eb.entity_type
                  ? 'var(--color-surface)'
                  : 'var(--color-ink-2)',
                fontSize: '11px',
                fontWeight: 500,
                cursor: 'pointer',
              }}
            >
              {ENTITY_TYPE_LABELS[eb.entity_type] ?? displayName(eb.entity_type)}
            </button>
          ))}
        </div>
      )}

      {/* Loading / Error */}
      {loading && (
        <div style={{ padding: '16px 0', color: 'var(--color-ink-3)', fontSize: '12px' }}>
          Loading records...
        </div>
      )}
      {error && (
        <div style={{
          padding: '8px 12px',
          borderRadius: '8px',
          background: 'var(--color-red-soft)',
          color: 'var(--color-red)',
          fontSize: '12px',
          marginBottom: '8px',
        }}>
          {error}
        </div>
      )}

      {/* Records table */}
      {!loading && data && data.records.length > 0 && (
        <>
          <div style={{
            overflowX: 'auto',
            borderRadius: '8px',
            border: '1px solid var(--color-line)',
          }}>
            <table style={{
              width: '100%',
              borderCollapse: 'collapse',
              fontSize: '12px',
              fontFamily: 'var(--font-body)',
            }}>
              <thead>
                <tr>
                  {data.columns.map((col) => (
                    <th
                      key={col.name}
                      style={{
                        padding: '6px 10px',
                        textAlign: 'left',
                        fontWeight: 600,
                        fontSize: '10px',
                        textTransform: 'uppercase',
                        letterSpacing: '0.05em',
                        color: 'var(--color-ink-3)',
                        background: 'var(--color-surface-2)',
                        borderBottom: '1px solid var(--color-line)',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {displayName(col.name)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.records.map((record, rowIdx) => (
                  <tr
                    key={rowIdx}
                    style={{
                      background: rowIdx % 2 === 0 ? 'var(--color-surface)' : 'var(--color-surface-2)',
                    }}
                  >
                    {data.columns.map((col) => (
                      <td
                        key={col.name}
                        title={cellTitle(record[col.name])}
                        style={{
                          padding: '5px 10px',
                          color: record[col.name] == null ? 'var(--color-ink-4)' : 'var(--color-ink-2)',
                          borderBottom: '1px solid var(--color-line)',
                          whiteSpace: 'nowrap',
                          maxWidth: '200px',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                        }}
                      >
                        {formatCellValue(record[col.name])}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <div style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            marginTop: '8px',
            fontSize: '11px',
            color: 'var(--color-ink-3)',
          }}>
            <span>
              Showing {currentOffset + 1}\u2013{Math.min(currentOffset + pageSize, data.total)} of {formatNumber(data.total)}
            </span>
            <div style={{ display: 'flex', gap: '4px' }}>
              <button
                type="button"
                disabled={currentOffset === 0}
                onClick={() => fetchRecords(selectedType, Math.max(0, currentOffset - pageSize))}
                style={{
                  padding: '3px 8px',
                  borderRadius: '6px',
                  border: '1px solid var(--color-line)',
                  background: 'var(--color-surface-2)',
                  color: currentOffset === 0 ? 'var(--color-ink-4)' : 'var(--color-ink-2)',
                  cursor: currentOffset === 0 ? 'default' : 'pointer',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '2px',
                  fontSize: '11px',
                  opacity: currentOffset === 0 ? 0.5 : 1,
                }}
              >
                <ChevronLeft size={11} /> Prev
              </button>
              <span style={{ padding: '3px 8px', fontSize: '11px' }}>
                {currentPage} / {totalPages}
              </span>
              <button
                type="button"
                disabled={currentOffset + pageSize >= data.total}
                onClick={() => fetchRecords(selectedType, currentOffset + pageSize)}
                style={{
                  padding: '3px 8px',
                  borderRadius: '6px',
                  border: '1px solid var(--color-line)',
                  background: 'var(--color-surface-2)',
                  color: currentOffset + pageSize >= data.total ? 'var(--color-ink-4)' : 'var(--color-ink-2)',
                  cursor: currentOffset + pageSize >= data.total ? 'default' : 'pointer',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '2px',
                  fontSize: '11px',
                  opacity: currentOffset + pageSize >= data.total ? 0.5 : 1,
                }}
              >
                Next <ChevronRight size={11} />
              </button>
            </div>
          </div>
        </>
      )}

      {/* No records */}
      {!loading && data && data.records.length === 0 && (
        <div style={{ padding: '12px 0', color: 'var(--color-ink-4)', fontSize: '12px' }}>
          No records found for this source.
        </div>
      )}

      {/* Schema info */}
      {!loading && data && data.columns.length > 0 && (
        <div style={{
          marginTop: '10px',
          padding: '8px 12px',
          borderRadius: '8px',
          background: 'var(--color-surface-2)',
          fontSize: '11px',
          color: 'var(--color-ink-3)',
        }}>
          Table: <span style={{ fontWeight: 600, color: 'var(--color-ink-2)' }}>{data.table}</span>
          {' \u00B7 '}
          {data.columns.length} columns
          {' \u00B7 '}
          {formatNumber(data.total)} rows
        </div>
      )}
    </div>
  );
}

/* ── Cross-Source Connections (Enhanced) ── */

function ConnectionsFlowSection({ sourceKey }: { sourceKey: string }) {
  const [data, setData] = useState<SourceConnectionsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    api.sourceConnections(sourceKey)
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [sourceKey]);

  if (loading) {
    return <div style={{ padding: '12px 0', color: 'var(--color-ink-3)', fontSize: '12px' }}>Loading connections...</div>;
  }
  if (error) {
    return (
      <div style={{
        padding: '8px 12px', borderRadius: '8px',
        background: 'var(--color-red-soft)', color: 'var(--color-red)', fontSize: '12px',
      }}>
        {error}
      </div>
    );
  }
  if (!data || data.connections.length === 0) {
    return <div style={{ padding: '12px 0', color: 'var(--color-ink-4)', fontSize: '12px' }}>No cross-source connections found.</div>;
  }

  return (
    <div>
      {/* Summary stats */}
      <div style={{
        display: 'flex', gap: '16px', marginBottom: '12px',
        padding: '8px 12px', borderRadius: '8px', background: 'var(--color-surface-2)',
      }}>
        <div style={{ fontSize: '11px', color: 'var(--color-ink-3)' }}>
          Outgoing: <span style={{ fontWeight: 600, color: 'var(--color-ink-2)' }}>{formatNumber(data.total_outgoing)}</span>
        </div>
        <div style={{ fontSize: '11px', color: 'var(--color-ink-3)' }}>
          Incoming: <span style={{ fontWeight: 600, color: 'var(--color-ink-2)' }}>{formatNumber(data.total_incoming)}</span>
        </div>
      </div>

      {/* Connection rows */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
        {data.connections.map((conn, i) => (
          <div
            key={`${conn.target_source}-${conn.link_type}-${i}`}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              padding: '6px 0',
              fontSize: '12px',
            }}
          >
            {/* Source indicator */}
            <span style={{
              display: 'inline-block',
              width: '8px',
              height: '8px',
              borderRadius: '2px',
              background: 'var(--color-accent)',
              flexShrink: 0,
            }} />

            {/* Arrow */}
            <span style={{ color: 'var(--color-ink-4)', flexShrink: 0 }}>{'\u2192'}</span>

            {/* Target source name */}
            <span style={{
              fontWeight: 500,
              color: 'var(--color-ink)',
              minWidth: '100px',
            }}>
              {SOURCE_LABELS[conn.target_source] ?? displayName(conn.target_source)}
            </span>

            {/* Link type pill */}
            <span style={{
              fontSize: '10px',
              fontWeight: 600,
              color: 'var(--color-ink-4)',
              background: 'var(--color-surface-3)',
              padding: '2px 8px',
              borderRadius: '6px',
              whiteSpace: 'nowrap',
            }}>
              {displayName(conn.link_type)}
            </span>

            {/* Count badge */}
            <span style={{
              fontSize: '11px',
              fontWeight: 600,
              color: 'var(--color-accent)',
              marginLeft: 'auto',
              flexShrink: 0,
            }}>
              {formatNumber(conn.count)}
            </span>
          </div>
        ))}
      </div>

      {/* Sample entities chips for connections that have them */}
      {data.connections.some((c) => c.sample_entities?.length) && (
        <div style={{
          marginTop: '10px',
          display: 'flex',
          flexWrap: 'wrap',
          gap: '4px',
        }}>
          {data.connections
            .flatMap((c) => c.sample_entities ?? [])
            .filter((v, i, arr) => arr.indexOf(v) === i)
            .slice(0, 10)
            .map((name) => (
              <span
                key={name}
                style={{
                  fontSize: '10px',
                  color: 'var(--color-ink-3)',
                  background: 'var(--color-surface-3)',
                  padding: '2px 8px',
                  borderRadius: '10px',
                }}
              >
                {name}
              </span>
            ))}
        </div>
      )}
    </div>
  );
}

/* ── Main Component ── */

export default function SourceProfileCard({
  data,
  isLoading,
  error,
  onClose,
  onRefresh,
}: SourceProfileCardProps) {
  /* ── Error state ── */
  if (error) {
    return (
      <div style={{
        padding: '24px',
        background: 'var(--color-surface)',
        borderRadius: '16px',
        boxShadow: 'var(--shadow-sm)',
      }}>
        <div style={{
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          marginBottom: '24px',
        }}>
          <div style={{
            padding: '8px 14px',
            borderRadius: '8px',
            background: 'var(--color-red-soft)',
            color: 'var(--color-red)',
            fontSize: '13px',
          }}>
            {error}
          </div>
          <button
            type="button"
            className="btn-icon"
            onClick={onClose}
            aria-label="Close"
          >
            <X size={15} />
          </button>
        </div>
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          onClick={onRefresh}
          style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}
        >
          <RefreshCw size={12} />
          Retry
        </button>
      </div>
    );
  }

  /* ── Loading state ── */
  if (isLoading || !data) {
    return (
      <div style={{
        padding: '24px',
        background: 'var(--color-surface)',
        borderRadius: '16px',
        boxShadow: 'var(--shadow-sm)',
      }}>
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: '28px',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <Skeleton width="12px" height="12px" />
            <Skeleton width="200px" height="22px" />
          </div>
          <button type="button" className="btn-icon" onClick={onClose} aria-label="Close">
            <X size={15} />
          </button>
        </div>
        <SkeletonSection />
        <SkeletonSection />
        <SkeletonSection />
        <SkeletonSection />
      </div>
    );
  }

  const statusKey = resolveStatus(data.status);
  const statusStyle = STATUS_COLORS[statusKey];
  const sourceLabel = SOURCE_LABELS[data.source_key] ?? data.label;
  const maxEntityCount = Math.max(...data.entity_breakdown.map((e) => e.count), 1);

  return (
    <div style={{
      background: 'var(--color-surface)',
      borderRadius: '16px',
      boxShadow: 'var(--shadow-sm)',
      overflow: 'hidden',
    }}>
      {/* ── Header ── */}
      <div style={{
        padding: '20px 24px',
        borderBottom: '1px solid var(--color-line)',
        display: 'flex',
        alignItems: 'flex-start',
        justifyContent: 'space-between',
        gap: '12px',
      }}>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <span style={{
              display: 'inline-block',
              width: '10px',
              height: '10px',
              borderRadius: '3px',
              background: 'var(--color-accent)',
              flexShrink: 0,
            }} />
            <h2 style={{
              fontFamily: 'var(--font-display)',
              fontSize: '18px',
              fontWeight: 500,
              color: 'var(--color-ink)',
              letterSpacing: '-0.02em',
              lineHeight: 1.3,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}>
              {sourceLabel}
            </h2>
            <span style={{
              fontSize: '11px',
              fontWeight: 500,
              color: 'var(--color-ink-4)',
              background: 'var(--color-surface-2)',
              padding: '2px 8px',
              borderRadius: '8px',
              flexShrink: 0,
            }}>
              API Source
            </span>
          </div>

          {/* Meta row */}
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '14px',
            marginTop: '8px',
            flexWrap: 'wrap',
          }}>
            {/* Status badge */}
            <span style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '5px',
              fontSize: '11px',
              fontWeight: 600,
              color: statusStyle.text,
              background: statusStyle.bg,
              padding: '2px 10px',
              borderRadius: '10px',
            }}>
              <span style={{
                display: 'inline-block',
                width: '6px',
                height: '6px',
                borderRadius: '50%',
                background: statusStyle.dot,
                ...(statusKey === 'Live' ? { animation: 'pulse-dot 2s ease-in-out infinite' } : {}),
              }} />
              {statusKey}
            </span>

            {/* Schedule */}
            <span style={{ fontSize: '12px', color: 'var(--color-ink-3)' }}>
              Schedule: {data.schedule}
            </span>

            {/* Last run */}
            <span style={{ fontSize: '12px', color: 'var(--color-ink-3)' }}>
              Last run: {data.last_run ? relativeTime(data.last_run) : '\u2014'}
            </span>

            {/* Records */}
            <span style={{ fontSize: '12px', color: 'var(--color-ink-3)' }}>
              Records: {formatNumber(data.total_records)}
            </span>
          </div>
        </div>

        <button
          type="button"
          className="btn-icon"
          onClick={onClose}
          aria-label="Close"
          style={{ flexShrink: 0 }}
        >
          <X size={15} />
        </button>
      </div>

      {/* ── Scrollable body ── */}
      <div style={{
        padding: '16px 24px 24px',
        overflowY: 'auto',
        maxHeight: 'calc(100vh - 200px)',
      }}>
        {/* ── Entity Breakdown ── */}
        {data.entity_breakdown.length > 0 && (
          <Section
            title="Entity Breakdown"
            badge={
              <span style={{
                fontSize: '11px',
                fontWeight: 500,
                color: 'var(--color-ink-4)',
                background: 'var(--color-surface-2)',
                padding: '2px 8px',
                borderRadius: '8px',
              }}>
                {data.entity_breakdown.length} types
              </span>
            }
          >
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {data.entity_breakdown.map((item) => {
                const barPct = Math.round((item.count / maxEntityCount) * 100);
                return (
                  <div
                    key={item.entity_type}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '10px',
                    }}
                  >
                    <EntityDot type={item.entity_type} size={8} />
                    <span style={{
                      fontSize: '12px',
                      color: 'var(--color-ink-2)',
                      width: '80px',
                      flexShrink: 0,
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}>
                      {ENTITY_TYPE_LABELS[item.entity_type] ?? displayName(item.entity_type)}
                    </span>
                    <span style={{
                      fontSize: '11px',
                      fontWeight: 600,
                      color: 'var(--color-ink-2)',
                      width: '52px',
                      textAlign: 'right',
                      flexShrink: 0,
                    }}>
                      {formatNumber(item.count)}
                    </span>
                    <div style={{
                      flex: 1,
                      height: '6px',
                      borderRadius: '3px',
                      background: 'var(--color-surface-3)',
                      overflow: 'hidden',
                    }}>
                      <div style={{
                        width: `${barPct}%`,
                        height: '100%',
                        borderRadius: '3px',
                        background: entityColor(item.entity_type),
                        transition: 'width 0.4s ease',
                      }} />
                    </div>
                  </div>
                );
              })}
            </div>
          </Section>
        )}

        {/* ── Field Completeness ── */}
        {data.field_completeness.length > 0 && (
          <Section
            title="Field Completeness"
            badge={
              <span style={{
                fontSize: '12px',
                fontWeight: 700,
                color: completenessColor(
                  Math.round(
                    data.field_completeness.reduce((sum, f) => sum + f.pct, 0) /
                    data.field_completeness.length
                  )
                ),
                background: completenessBg(
                  Math.round(
                    data.field_completeness.reduce((sum, f) => sum + f.pct, 0) /
                    data.field_completeness.length
                  )
                ),
                padding: '2px 10px',
                borderRadius: '10px',
              }}>
                {Math.round(
                  data.field_completeness.reduce((sum, f) => sum + f.pct, 0) /
                  data.field_completeness.length
                )}% avg
              </span>
            }
          >
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              {data.field_completeness.map((field) => (
                <div
                  key={field.field}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '10px',
                  }}
                >
                  <span style={{
                    fontSize: '11px',
                    color: 'var(--color-ink-3)',
                    width: '110px',
                    flexShrink: 0,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}>
                    {displayName(field.field)}
                  </span>
                  <div style={{
                    flex: 1,
                    height: '6px',
                    borderRadius: '3px',
                    background: 'var(--color-surface-3)',
                    overflow: 'hidden',
                  }}>
                    <div style={{
                      width: `${field.pct}%`,
                      height: '100%',
                      borderRadius: '3px',
                      background: completenessColor(field.pct),
                      transition: 'width 0.4s ease',
                    }} />
                  </div>
                  <span style={{
                    fontSize: '11px',
                    fontWeight: 600,
                    color: completenessColor(field.pct),
                    width: '32px',
                    textAlign: 'right',
                    flexShrink: 0,
                  }}>
                    {Math.round(field.pct)}%
                  </span>
                </div>
              ))}
            </div>
          </Section>
        )}

        {/* ── Steward Activity ── */}
        {data.steward_actions.length > 0 && (
          <Section title="Steward Activity" defaultOpen={true}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              {data.steward_actions.map((act, i) => {
                const { icon, color } = stewardIcon(act.status);
                return (
                  <div
                    key={`${act.action}-${i}`}
                    style={{
                      display: 'flex',
                      alignItems: 'flex-start',
                      gap: '8px',
                      padding: '4px 0',
                      fontSize: '12px',
                    }}
                  >
                    <span style={{
                      color,
                      fontWeight: 600,
                      flexShrink: 0,
                      width: '16px',
                      textAlign: 'center',
                    }}>
                      {icon}
                    </span>
                    <span style={{
                      color: 'var(--color-ink-2)',
                      flex: 1,
                      minWidth: 0,
                    }}>
                      {act.action}
                    </span>
                    <span style={{
                      fontSize: '10px',
                      color: 'var(--color-ink-4)',
                      flexShrink: 0,
                      whiteSpace: 'nowrap',
                    }}>
                      {relativeTime(act.timestamp)}
                    </span>
                  </div>
                );
              })}
            </div>
          </Section>
        )}

        {/* ── Sample Records (Data Explorer) ── */}
        <Section title="Sample Records" defaultOpen={false}>
          <SampleRecordsSection
            sourceKey={data.source_key}
            entityBreakdown={data.entity_breakdown}
          />
        </Section>

        {/* ── Cross-Source Connections (Enhanced) ── */}
        <Section title="Cross-Source Connections" defaultOpen={false}>
          <ConnectionsFlowSection sourceKey={data.source_key} />
        </Section>

        {/* ── Actions ── */}
        <div style={{
          display: 'flex',
          gap: '8px',
          flexWrap: 'wrap',
          paddingTop: '16px',
          borderTop: '1px solid var(--color-line)',
          marginTop: '8px',
        }}>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={onRefresh}
            style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}
          >
            <RefreshCw size={12} />
            Refresh Now
          </button>
        </div>
      </div>
    </div>
  );
}
