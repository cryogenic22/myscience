import { type ReactNode, useState } from 'react';
import {
  ChevronDown,
  ChevronRight,
  RefreshCw,
  X,
} from 'lucide-react';
import type { SourceProfileData } from '../api';
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

        {/* ── Cross-Source Connections ── */}
        {data.cross_source_links.length > 0 && (
          <Section title="Cross-Source Connections" defaultOpen={false}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              {data.cross_source_links.map((link, i) => (
                <div
                  key={`${link.target_source}-${link.link_type}-${i}`}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                    padding: '4px 0',
                    fontSize: '12px',
                  }}
                >
                  <span style={{
                    color: 'var(--color-accent)',
                    fontWeight: 500,
                    flexShrink: 0,
                  }}>
                    {'\u2192'}
                  </span>
                  <span style={{
                    fontWeight: 500,
                    color: 'var(--color-ink)',
                  }}>
                    {SOURCE_LABELS[link.target_source] ?? displayName(link.target_source)}
                  </span>
                  <span style={{
                    fontSize: '10px',
                    fontWeight: 600,
                    color: 'var(--color-ink-4)',
                    background: 'var(--color-surface-3)',
                    padding: '1px 6px',
                    borderRadius: '6px',
                  }}>
                    {displayName(link.link_type)}
                  </span>
                  <span style={{
                    fontSize: '11px',
                    color: 'var(--color-ink-3)',
                    marginLeft: 'auto',
                    flexShrink: 0,
                  }}>
                    {formatNumber(link.count)} links
                  </span>
                </div>
              ))}
            </div>
          </Section>
        )}

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
