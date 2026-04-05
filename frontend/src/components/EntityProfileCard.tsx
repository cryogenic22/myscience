import { type ReactNode, useEffect, useState } from 'react';
import {
  CheckCircle,
  ChevronDown,
  ChevronRight,
  Clock,
  Edit3,
  ExternalLink,
  FileText,
  Link,
  MessageSquare,
  Network,
  RefreshCw,
  X,
  Zap,
} from 'lucide-react';
import { api } from '../api';
import type { EntityProfileData } from '../api';
import {
  displayName,
  isUUID,
  ENTITY_TYPE_LABELS,
  FIELD_LABELS,
  SOURCE_LABELS,
} from '../brand';

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

const INTERNAL_FIELDS = new Set([
  '_label', 'content_hash', 'molecule_embedding', 'strategy_embedding',
  'protocol_embedding', 'abstract_embedding', 'scope_note_embedding',
  'label_embedding', 'full_text_embedding', 'id', 'entity_type',
  'created_at', 'updated_at', 'retrieved_at', 'last_verified_at',
  'source_api', 'record_status',
]);

function formatValue(v: unknown): string {
  if (v == null) return '\u2014';
  if (Array.isArray(v)) return v.length > 0 ? v.join(', ') : '\u2014';
  const s = String(v);
  if (!s) return '\u2014';
  if (isUUID(s)) return '\u2014';
  return s;
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

function shortDate(v: string | null): string {
  if (!v) return '\u2014';
  return new Date(v).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

function scoreColor(score: number): string {
  if (score >= 0.7) return 'var(--color-green)';
  if (score >= 0.4) return 'var(--color-amber)';
  return 'var(--color-red)';
}

function scoreBg(score: number): string {
  if (score >= 0.7) return 'var(--color-green-soft)';
  if (score >= 0.4) return 'var(--color-amber-soft)';
  return 'var(--color-red-soft)';
}

/* ── Props ── */

interface EntityProfileCardProps {
  data: EntityProfileData | null;
  isLoading: boolean;
  error: string | null;
  onClose: () => void;
  onAskInChat: (entityName: string) => void;
  onExploreGraph: (entityType: string, entityId: string) => void;
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

/* ── EntityDot ── */

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

/* ── FAIR Score Bar ── */

function ScoreBar({ label, value }: { label: string; value: number }) {
  const pct = Math.round(value * 100);
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '6px' }}>
      <span style={{
        fontSize: '11px',
        color: 'var(--color-ink-3)',
        width: '110px',
        flexShrink: 0,
      }}>
        {label}
      </span>
      <div style={{
        flex: 1,
        height: '6px',
        borderRadius: '3px',
        background: 'var(--color-surface-3)',
        overflow: 'hidden',
      }}>
        <div style={{
          width: `${pct}%`,
          height: '100%',
          borderRadius: '3px',
          background: scoreColor(value),
          transition: 'width 0.4s ease',
        }} />
      </div>
      <span style={{
        fontSize: '11px',
        fontWeight: 600,
        color: scoreColor(value),
        width: '32px',
        textAlign: 'right',
        flexShrink: 0,
      }}>
        {pct}%
      </span>
    </div>
  );
}

/* ── Main Component ── */

export default function EntityProfileCard({
  data,
  isLoading,
  error,
  onClose,
  onAskInChat,
  onExploreGraph,
}: EntityProfileCardProps) {
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
          onClick={() => window.location.reload()}
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

  const entityName = String(
    data.identity._label ?? data.identity.generic_name ?? data.identity.name ?? data.identity.title ?? 'Unknown'
  );
  const entityId = String(data.identity.id ?? '');
  const typeLabel = ENTITY_TYPE_LABELS[data.entity_type] ?? displayName(data.entity_type);
  const overallPct = Math.round(data.fair_scores.overall * 100);

  /* ── Activity feed state ── */
  const [activityEvents, setActivityEvents] = useState<
    Array<{event_type: string; description: string; source: string; timestamp: string; details: Record<string, unknown>}>
  >([]);
  const [activityTotal, setActivityTotal] = useState(0);

  useEffect(() => {
    if (!entityId || !data.entity_type) return;
    let cancelled = false;
    api.entityEvents(data.entity_type, entityId, 10)
      .then((res) => {
        if (!cancelled) {
          setActivityEvents(res.events);
          setActivityTotal(res.total);
        }
      })
      .catch(() => {
        /* graceful degradation — section simply stays empty */
      });
    return () => { cancelled = true; };
  }, [data.entity_type, entityId]);

  /* ── Identity fields (filter internal) ── */
  const identityEntries = Object.entries(data.identity)
    .filter(([k]) => !INTERNAL_FIELDS.has(k))
    .filter(([, v]) => {
      if (v == null || v === '' || v === 'null') return false;
      if (typeof v === 'string' && isUUID(v)) return false;
      return true;
    });

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
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', minWidth: 0, flex: 1 }}>
          <EntityDot type={data.entity_type} size={12} />
          <div style={{ minWidth: 0, flex: 1 }}>
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
              {entityName}
            </h2>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '4px' }}>
              <span style={{
                fontSize: '11px',
                fontWeight: 600,
                color: entityColor(data.entity_type),
                background: `color-mix(in srgb, ${entityColor(data.entity_type)} 10%, transparent)`,
                padding: '2px 8px',
                borderRadius: '10px',
              }}>
                {typeLabel}
              </span>
              {data.stats.influence_score != null && (
                <span style={{
                  fontSize: '11px',
                  fontWeight: 500,
                  color: 'var(--color-ink-4)',
                }}>
                  Influence: {Math.round(data.stats.influence_score * 100)}
                </span>
              )}
            </div>
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
        {/* ── FAIR Score ── */}
        <Section title="FAIR Score" badge={
          <span style={{
            fontSize: '12px',
            fontWeight: 700,
            color: scoreColor(data.fair_scores.overall),
            background: scoreBg(data.fair_scores.overall),
            padding: '2px 10px',
            borderRadius: '10px',
          }}>
            {overallPct}%
          </span>
        }>
          <ScoreBar label="Completeness" value={data.fair_scores.completeness} />
          <ScoreBar label="Link Density" value={data.fair_scores.link_density} />
          <ScoreBar label="Source Diversity" value={data.fair_scores.source_diversity} />
          <ScoreBar label="Freshness" value={data.fair_scores.freshness} />
          <ScoreBar label="Resolution" value={data.fair_scores.resolution} />

          {/* AI Readiness */}
          <div style={{
            display: 'flex',
            gap: '8px',
            flexWrap: 'wrap',
            marginTop: '12px',
          }}>
            <AiReadinessBadge label="Embedding" ready={data.ai_readiness.has_embedding} />
            <AiReadinessBadge label="Linked" ready={data.ai_readiness.is_linked} />
            <AiReadinessBadge label="Resolved" ready={data.ai_readiness.is_resolved} />
          </div>
        </Section>

        {/* ── Identity ── */}
        {identityEntries.length > 0 && (
          <Section title="Identity">
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'minmax(100px, 35%) 1fr',
              gap: '2px 12px',
            }}>
              {identityEntries.map(([key, val]) => (
                <div key={key} style={{ display: 'contents' }}>
                  <span style={{
                    paddingTop: '5px',
                    fontSize: '12px',
                    color: 'var(--color-ink-4)',
                  }}>
                    {FIELD_LABELS[key] ?? displayName(key)}
                  </span>
                  <span style={{
                    paddingTop: '5px',
                    fontSize: '12px',
                    color: 'var(--color-ink-2)',
                    wordBreak: 'break-word',
                  }}>
                    {key === 'source_authority' || key === 'source_api'
                      ? (SOURCE_LABELS[String(val)] ?? formatValue(val))
                      : formatValue(val)}
                  </span>
                </div>
              ))}
            </div>
          </Section>
        )}

        {/* ── Connections ── */}
        {data.connections.length > 0 && (
          <Section
            title="Connections"
            badge={
              <span style={{
                fontSize: '11px',
                fontWeight: 500,
                color: 'var(--color-ink-4)',
                background: 'var(--color-surface-2)',
                padding: '2px 8px',
                borderRadius: '8px',
              }}>
                {data.stats.total_connections} total
              </span>
            }
          >
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {data.connections.map((conn) => (
                <div
                  key={conn.entity_type}
                  style={{
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: '8px',
                    padding: '6px 0',
                  }}
                >
                  <EntityDot type={conn.entity_type} size={8} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <span style={{
                        fontSize: '12px',
                        fontWeight: 500,
                        color: 'var(--color-ink)',
                      }}>
                        {ENTITY_TYPE_LABELS[conn.entity_type] ?? displayName(conn.entity_type)}
                      </span>
                      <span style={{
                        fontSize: '10px',
                        fontWeight: 600,
                        color: 'var(--color-ink-4)',
                        background: 'var(--color-surface-3)',
                        padding: '1px 6px',
                        borderRadius: '6px',
                      }}>
                        {conn.count}
                      </span>
                    </div>
                    {conn.sample_labels.length > 0 && (
                      <div style={{
                        fontSize: '11px',
                        color: 'var(--color-ink-3)',
                        marginTop: '2px',
                        lineHeight: 1.5,
                      }}>
                        {conn.sample_labels.slice(0, 3).join(', ')}
                        {conn.sample_labels.length > 3 && (
                          <span style={{ color: 'var(--color-ink-4)' }}>
                            {' '}+{conn.sample_labels.length - 3} more
                          </span>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </Section>
        )}

        {/* ── Evidence Trail ── */}
        {data.evidence.length > 0 && (
          <Section title="Evidence Trail" defaultOpen={false}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              {data.evidence.map((ev, i) => (
                <div
                  key={`${ev.entity_id}-${i}`}
                  style={{
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: '8px',
                    padding: '6px 8px',
                    borderRadius: '8px',
                    transition: 'background 150ms',
                  }}
                  onMouseEnter={(e) => {
                    (e.currentTarget as HTMLElement).style.background = 'var(--color-surface-2)';
                  }}
                  onMouseLeave={(e) => {
                    (e.currentTarget as HTMLElement).style.background = 'transparent';
                  }}
                >
                  <FileText
                    size={13}
                    style={{ color: 'var(--color-ink-4)', marginTop: '1px', flexShrink: 0 }}
                  />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{
                      fontSize: '12px',
                      color: 'var(--color-ink)',
                      fontWeight: 500,
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}>
                      {ev.title}
                    </div>
                    <div style={{
                      display: 'flex',
                      gap: '8px',
                      alignItems: 'center',
                      marginTop: '2px',
                    }}>
                      <span style={{
                        fontSize: '10px',
                        color: 'var(--color-ink-4)',
                        textTransform: 'capitalize',
                      }}>
                        {ev.type}
                      </span>
                      {ev.date && (
                        <span style={{ fontSize: '10px', color: 'var(--color-ink-4)' }}>
                          {shortDate(ev.date)}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </Section>
        )}

        {/* ── Provenance ── */}
        {data.provenance.length > 0 && (
          <Section title="Provenance" defaultOpen={false}>
            <div style={{
              display: 'flex',
              flexWrap: 'wrap',
              gap: '6px',
            }}>
              {data.provenance.map((src) => (
                <span
                  key={src}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '4px',
                    fontSize: '11px',
                    fontWeight: 500,
                    color: 'var(--color-ink-2)',
                    background: 'var(--color-surface-2)',
                    padding: '3px 10px',
                    borderRadius: '8px',
                  }}
                >
                  <ExternalLink size={10} style={{ color: 'var(--color-ink-4)' }} />
                  {SOURCE_LABELS[src] ?? displayName(src)}
                </span>
              ))}
            </div>
          </Section>
        )}

        {/* ── Recent Changes ── */}
        {data.recent_changes.length > 0 && (
          <Section title="Recent Changes" defaultOpen={false}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              {data.recent_changes.map((ch, i) => (
                <div
                  key={`${ch.field}-${i}`}
                  style={{
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: '8px',
                    fontSize: '12px',
                    padding: '4px 0',
                  }}
                >
                  <span style={{
                    fontWeight: 500,
                    color: 'var(--color-ink)',
                    flexShrink: 0,
                  }}>
                    {FIELD_LABELS[ch.field] ?? displayName(ch.field)}
                  </span>
                  <span style={{ color: 'var(--color-ink-3)', flex: 1, minWidth: 0 }}>
                    <span style={{ color: 'var(--color-red)', textDecoration: 'line-through' }}>
                      {ch.old_value ?? 'null'}
                    </span>
                    {' \u2192 '}
                    <span style={{ color: 'var(--color-green)' }}>
                      {ch.new_value ?? 'null'}
                    </span>
                  </span>
                  <span style={{
                    fontSize: '10px',
                    color: 'var(--color-ink-4)',
                    flexShrink: 0,
                    whiteSpace: 'nowrap',
                  }}>
                    {relativeTime(ch.changed_at)}
                  </span>
                </div>
              ))}
            </div>
          </Section>
        )}

        {/* ── Recent Activity ── */}
        <Section
          title="Recent Activity"
          badge={
            activityTotal > 0 ? (
              <span style={{
                fontSize: '11px',
                fontWeight: 500,
                color: 'var(--color-ink-4)',
                background: 'var(--color-surface-2)',
                padding: '2px 8px',
                borderRadius: '8px',
              }}>
                {activityTotal} total
              </span>
            ) : undefined
          }
        >
          {activityEvents.length === 0 ? (
            <div style={{
              fontSize: '12px',
              color: 'var(--color-ink-4)',
              padding: '8px 0',
              fontStyle: 'italic',
            }}>
              No recent activity
            </div>
          ) : (
            <div style={{
              display: 'flex',
              flexDirection: 'column',
              gap: '0',
              borderLeft: '2px solid var(--color-line)',
              marginLeft: '6px',
              paddingLeft: '14px',
            }}>
              {activityEvents.map((evt, i) => (
                <div
                  key={`activity-${evt.event_type}-${i}`}
                  style={{
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: '8px',
                    padding: '6px 0',
                    position: 'relative',
                  }}
                >
                  {/* Timeline dot */}
                  <span style={{
                    position: 'absolute',
                    left: '-20px',
                    top: '9px',
                    width: '8px',
                    height: '8px',
                    borderRadius: '50%',
                    background: 'var(--color-surface)',
                    border: '2px solid var(--color-line)',
                    flexShrink: 0,
                  }} />
                  <ActivityIcon eventType={evt.event_type} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{
                      fontSize: '12px',
                      color: 'var(--color-ink)',
                      fontWeight: 500,
                      lineHeight: 1.4,
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}>
                      {evt.description}
                    </div>
                    <div style={{
                      display: 'flex',
                      gap: '8px',
                      alignItems: 'center',
                      marginTop: '2px',
                    }}>
                      <span style={{
                        fontSize: '10px',
                        color: 'var(--color-ink-4)',
                      }}>
                        {evt.source}
                      </span>
                      {evt.timestamp && (
                        <span style={{ fontSize: '10px', color: 'var(--color-ink-4)' }}>
                          {relativeTime(evt.timestamp)}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
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
            onClick={() => onAskInChat(entityName)}
            style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}
          >
            <MessageSquare size={12} />
            Ask in Chat
          </button>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={() => onExploreGraph(data.entity_type, entityId)}
            style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}
          >
            <Network size={12} />
            Explore Graph
          </button>
        </div>
      </div>
    </div>
  );
}

/* ── Sub-components ── */

function ActivityIcon({ eventType }: { eventType: string }) {
  const iconStyle = { color: 'var(--color-ink-4)', marginTop: '1px', flexShrink: 0 } as const;
  const size = 13;
  switch (eventType) {
    case 'field_change':
      return <Edit3 size={size} style={iconStyle} />;
    case 'steward_action':
      return <CheckCircle size={size} style={iconStyle} />;
    case 'market_event':
      return <Zap size={size} style={iconStyle} />;
    case 'new_connection':
      return <Link size={size} style={iconStyle} />;
    default:
      return <Clock size={size} style={iconStyle} />;
  }
}

function AiReadinessBadge({ label, ready }: { label: string; ready: boolean }) {
  return (
    <span style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: '4px',
      fontSize: '11px',
      fontWeight: 500,
      color: ready ? 'var(--color-green)' : 'var(--color-red)',
      background: ready ? 'var(--color-green-soft)' : 'var(--color-red-soft)',
      padding: '2px 8px',
      borderRadius: '10px',
    }}>
      {ready ? '\u2713' : '\u2717'} {label}
    </span>
  );
}
