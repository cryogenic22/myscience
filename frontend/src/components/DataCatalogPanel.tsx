import { useCallback, useEffect, useMemo, useState, useRef } from 'react';
import { LiteratureExplorer } from './LiteratureExplorer';
import { ErrorBoundary } from './ui/ErrorBoundary';
import { displayName, SOURCE_LABELS, ENTITY_TYPE_LABELS } from '../brand';
import {
  CheckCircle,
  ChevronLeft,
  ChevronRight,
  Clock,
  Edit3,
  RefreshCw,
  Search,
  Settings,
  X,
  XCircle,
} from 'lucide-react';
import {
  api,
  type CatalogBrowseResponse,
  type CatalogEntity,
  type CatalogEntityDetail,
  type CatalogStats,
  type ChangeLogEntry,
  type DatasetProfile,
  type HealthData,
  type HITLItem,
} from '../api';
import { Drawer } from './ui/Drawer';
import EntityDossier from './EntityDossier';
import EntityProfileCard from './EntityProfileCard';
import SourceProfileCard from './SourceProfileCard';
import type { EntityProfileData, SourceProfileData } from '../api';

interface Props {
  onAskInChat?: (question: string) => void;
}

/* ── Honest inline load-error banner ──
   Rendered when a fetch fails so a failure is never disguised as an empty
   or still-loading state. Carries role="alert" + a working Retry. */
function InlineLoadError({ message, onRetry, testId }: {
  message: string;
  onRetry: () => void;
  testId?: string;
}) {
  return (
    <div
      role="alert"
      data-testid={testId}
      style={{
        padding: '14px 16px', borderRadius: '12px',
        background: 'var(--color-red-soft)', border: '1px solid var(--color-line)',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        gap: '12px', flexWrap: 'wrap',
      }}
    >
      <span style={{ fontSize: '13px', color: 'var(--color-ink-2)' }}>{message}</span>
      <button
        type="button"
        onClick={onRetry}
        className="btn btn-xs btn-secondary"
        style={{ borderRadius: '6px', flexShrink: 0 }}
      >
        Retry
      </button>
    </div>
  );
}

/* ── Constants ── */

const ENTITY_FILTERS = [
  { key: 'all', label: 'All' },
  { key: 'drug', label: 'Drugs' },
  { key: 'company', label: 'Companies' },
  { key: 'trial', label: 'Trials' },
  { key: 'mechanism', label: 'Mechanisms' },
  { key: 'therapeutic_area', label: 'Therapeutic Areas' },
  { key: 'sources', label: 'Sources' },
];

const SORT_OPTIONS = [
  { key: 'pipeline_score', label: 'Most Connected' },
  { key: 'quality', label: 'Highest FAIR' },
  { key: 'recent', label: 'Recently Updated' },
  { key: 'name', label: 'Name' },
];

const ENTITY_DOT_COLORS: Record<string, string> = {
  drug: 'var(--color-drug)',
  company: 'var(--color-company)',
  trial: 'var(--color-trial)',
  mechanism: 'var(--color-mechanism)',
  therapeutic_area: 'var(--color-ta)',
  article: 'var(--color-literature)',
  literature: 'var(--color-literature)',
};

/* ── Helpers ── */

function fmt(n: number) {
  return new Intl.NumberFormat().format(n);
}

function shortDate(v: string | null | undefined) {
  if (!v) return '\u2014';
  return new Date(v).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

function fairColor(score: number): string {
  if (score >= 0.7) return 'var(--color-green)';
  if (score >= 0.4) return 'var(--color-amber)';
  return 'var(--color-red)';
}

/* ── Skeleton ── */

function Skeleton({ width, height }: { width?: string; height?: string }) {
  return (
    <div
      style={{
        width: width || '100%',
        height: height || '16px',
        borderRadius: '6px',
        background: 'var(--color-surface-3)',
        animation: 'skeleton-pulse 1.5s ease-in-out infinite',
      }}
    />
  );
}

function SkeletonCard() {
  return (
    <div
      style={{
        padding: '20px',
        borderRadius: '16px',
        background: 'var(--color-surface)',
        border: '1px solid var(--color-line)',
        display: 'flex',
        flexDirection: 'column',
        gap: '12px',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <Skeleton width="10px" height="10px" />
        <Skeleton width="60%" height="16px" />
      </div>
      <Skeleton width="100%" height="4px" />
      <Skeleton width="40%" height="12px" />
    </div>
  );
}

/* ── Entity Card ── */

function entityContextLine(entity: CatalogEntity, entityType: string): string {
  const parts: string[] = [];
  if (entityType === 'drug') {
    if (entity.mechanism_name) parts.push(String(entity.mechanism_name));
    if (entity.company_name) parts.push(String(entity.company_name));
    if (entity.therapeutic_area_name) parts.push(String(entity.therapeutic_area_name));
    else if (entity.therapeutic_area) parts.push(String(entity.therapeutic_area));
  } else if (entityType === 'company') {
    if (entity.ticker) parts.push(String(entity.ticker));
    if (entity.country) parts.push(String(entity.country));
  } else if (entityType === 'trial') {
    if (entity.drug_name) parts.push(String(entity.drug_name));
    if (entity.sponsor_name) parts.push(String(entity.sponsor_name));
    if (entity.phase) parts.push(String(entity.phase));
  } else if (entityType === 'mechanism') {
    if (entity.scope_note) {
      const note = String(entity.scope_note);
      parts.push(note.length > 50 ? note.slice(0, 47) + '...' : note);
    }
  } else if (entityType === 'therapeutic_area') {
    if (entity.scope_note) {
      const note = String(entity.scope_note);
      parts.push(note.length > 50 ? note.slice(0, 47) + '...' : note);
    }
  }
  return parts.join(' \u00B7 ');
}

function entityConnectionSummary(entity: CatalogEntity, entityType: string): string[] {
  const lines: string[] = [];
  if (entityType === 'drug') {
    if (entity.trial_count != null) lines.push(`${fmt(Number(entity.trial_count))} trials`);
    if (entity.company_name) lines.push(`${String(entity.company_name)}`);
  } else if (entityType === 'company') {
    if (entity.drug_count != null) lines.push(`${fmt(Number(entity.drug_count))} drugs`);
    if (entity.trial_count != null) lines.push(`${fmt(Number(entity.trial_count))} trials`);
  } else if (entityType === 'trial') {
    if (entity.enrollment_target != null && Number(entity.enrollment_target) > 0) {
      lines.push(`${fmt(Number(entity.enrollment_target))} enrolled`);
    }
  }
  return lines;
}

function EntityCard({ entity, entityType, onOpen, featured }: {
  entity: CatalogEntity;
  entityType: string;
  onOpen: () => void;
  featured?: boolean;
}) {
  const name = String(entity._label || entity.generic_name || entity.name || entity.title || '');
  const quality = entity.quality_score != null ? Number(entity.quality_score) : null;
  const fairPct = quality != null ? Math.round(quality * 100) : null;
  const fColor = quality != null ? fairColor(quality) : 'var(--color-ink-4)';
  const dotColor = ENTITY_DOT_COLORS[entityType] || 'var(--color-ink-4)';
  const contextLine = entityContextLine(entity, entityType);
  const connections = entityConnectionSummary(entity, entityType);
  const sourceApi = entity.source_api ? String(entity.source_api) : null;
  const phase = entity.phase ? String(entity.phase) : null;
  const brandName = entity.brand_name ? String(entity.brand_name) : null;
  const ticker = entity.ticker ? String(entity.ticker) : null;

  // Descriptor: phase for drugs, ticker for companies
  let descriptor = '';
  if (entityType === 'drug' && phase) descriptor = phase;
  else if (entityType === 'company' && ticker) descriptor = ticker;
  else if (entityType === 'trial' && entity.status) descriptor = String(entity.status).toLowerCase().replace(/_/g, ' ');

  return (
    <div
      onClick={onOpen}
      style={{
        padding: featured ? '24px' : '20px',
        background: 'var(--color-surface)',
        border: '1px solid var(--color-line)',
        borderRadius: '16px',
        cursor: 'pointer',
        transition: 'all 0.15s ease',
        display: 'flex',
        flexDirection: 'column',
        gap: '12px',
      }}
      onMouseEnter={e => {
        e.currentTarget.style.borderColor = 'var(--color-accent)';
        e.currentTarget.style.transform = 'translateY(-1px)';
        e.currentTarget.style.boxShadow = 'var(--shadow-md)';
      }}
      onMouseLeave={e => {
        e.currentTarget.style.borderColor = 'var(--color-line)';
        e.currentTarget.style.transform = 'none';
        e.currentTarget.style.boxShadow = 'none';
      }}
    >
      {/* Row 1: dot + name + type badge */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <span style={{
          width: '10px', height: '10px', borderRadius: '50%',
          background: dotColor, flexShrink: 0,
        }} />
        <span style={{
          fontFamily: 'var(--font-display)', fontSize: featured ? '16px' : '15px',
          fontWeight: 600, color: 'var(--color-ink)',
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1,
        }}>
          {name}
        </span>
        <span style={{
          fontSize: '10px', fontWeight: 500, padding: '2px 8px', borderRadius: '10px',
          background: 'var(--color-surface-2)', color: 'var(--color-ink-4)',
          flexShrink: 0, textTransform: 'capitalize',
        }}>
          {ENTITY_TYPE_LABELS[entityType] || (entityType || 'entity').replace(/_/g, ' ')}
        </span>
      </div>

      {/* Row 2: Descriptor line (brand, phase, ticker) */}
      {(descriptor || brandName) && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
          {descriptor && (
            <span style={{
              fontSize: '11px', fontWeight: 500,
              color: entityType === 'drug' && phase?.includes('4') ? 'var(--color-green)'
                : entityType === 'drug' && phase?.includes('3') ? 'var(--color-accent)'
                : 'var(--color-ink-3)',
            }}>
              {descriptor}
            </span>
          )}
          {brandName && (
            <span style={{ fontSize: '11px', color: 'var(--color-ink-4)' }}>
              {brandName}
            </span>
          )}
        </div>
      )}

      {/* Row 3: Context line */}
      {contextLine && (
        <div style={{
          fontSize: '11px', color: 'var(--color-ink-3)',
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>
          {contextLine}
        </div>
      )}

      {/* Row 4: FAIR score bar */}
      {fairPct != null && (
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
            <span style={{
              fontSize: '10px', color: 'var(--color-ink-4)',
              textTransform: 'uppercase', letterSpacing: '0.04em',
            }}>FAIR Score</span>
            <span style={{ fontSize: '10px', fontWeight: 600, color: fColor }}>{fairPct}%</span>
          </div>
          <div style={{
            height: '4px', borderRadius: '2px',
            background: 'var(--color-surface-3)', overflow: 'hidden',
          }}>
            <div style={{
              height: '100%', width: `${fairPct}%`, borderRadius: '2px',
              background: fColor, transition: 'width 0.3s ease',
            }} />
          </div>
        </div>
      )}

      {/* Row 5: Connection counts */}
      {connections.length > 0 && (
        <div style={{
          display: 'flex', gap: '12px', flexWrap: 'wrap',
          fontSize: '11px', color: 'var(--color-ink-3)',
        }}>
          {connections.map((c, i) => (
            <span key={i}>{c}</span>
          ))}
        </div>
      )}

      {/* Row 6: Source pill */}
      {sourceApi && (
        <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
          <span style={{
            fontSize: '9px', padding: '2px 7px', borderRadius: '8px',
            background: 'var(--color-surface-2)', color: 'var(--color-ink-4)',
          }}>
            {SOURCE_LABELS[sourceApi] || displayName(sourceApi)}
          </span>
        </div>
      )}
    </div>
  );
}

/* ── Source Card (for pipeline connectors) ── */

function SourceCard({ connector, onOpen }: {
  connector: { source_key: string; label: string; schedule: string; last_run: string | null; days_since: number | null; records: number; status: string };
  onOpen: () => void;
}) {
  const statusMap: Record<string, { icon: string; color: string; bg: string; label: string }> = {
    fresh: { icon: '\u2713', color: 'var(--color-green)', bg: 'var(--color-green-soft)', label: 'Live' },
    ok: { icon: '\u2713', color: 'var(--color-accent)', bg: 'var(--color-accent-soft)', label: 'OK' },
    stale: { icon: '\u26A0', color: 'var(--color-amber)', bg: 'var(--color-amber-soft)', label: 'Stale' },
    never: { icon: '\u2014', color: 'var(--color-ink-4)', bg: 'var(--color-surface-2)', label: 'Awaiting' },
  };
  const st = statusMap[connector.status] || statusMap.never;

  return (
    <div
      onClick={onOpen}
      style={{
        padding: '20px',
        background: 'var(--color-surface)',
        border: '1px solid var(--color-line)',
        borderRadius: '16px',
        cursor: 'pointer',
        transition: 'all 0.15s ease',
        display: 'flex',
        flexDirection: 'column',
        gap: '10px',
      }}
      onMouseEnter={e => {
        e.currentTarget.style.borderColor = 'var(--color-accent)';
        e.currentTarget.style.transform = 'translateY(-1px)';
        e.currentTarget.style.boxShadow = 'var(--shadow-md)';
      }}
      onMouseLeave={e => {
        e.currentTarget.style.borderColor = 'var(--color-line)';
        e.currentTarget.style.transform = 'none';
        e.currentTarget.style.boxShadow = 'none';
      }}
    >
      {/* Header: name + status */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: 0, flex: 1 }}>
          <span style={{
            width: '10px', height: '10px', borderRadius: '3px',
            background: 'var(--color-accent)', flexShrink: 0,
          }} />
          <span style={{
            fontFamily: 'var(--font-display)', fontSize: '15px', fontWeight: 600,
            color: 'var(--color-ink)', overflow: 'hidden', textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}>
            {connector.label}
          </span>
        </div>
        <span style={{
          fontSize: '10px', fontWeight: 600, padding: '2px 8px', borderRadius: '10px',
          background: st.bg, color: st.color, flexShrink: 0,
        }}>
          {st.icon} {st.label}
        </span>
      </div>

      {/* Schedule */}
      <div style={{ fontSize: '11px', color: 'var(--color-ink-4)' }}>
        {connector.schedule}
      </div>

      {/* Stats row */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
        <span style={{ fontSize: '11px', color: 'var(--color-ink-3)' }}>
          {fmt(connector.records)} records
        </span>
        <span style={{ fontSize: '11px', color: 'var(--color-ink-4)' }}>
          {connector.days_since != null
            ? `Updated ${connector.days_since < 1 ? 'today' : Math.round(connector.days_since) + 'd ago'}`
            : 'Never run'}
        </span>
      </div>

      {/* Source key pill */}
      <div style={{ display: 'flex', gap: '4px' }}>
        <span style={{
          fontSize: '9px', padding: '2px 7px', borderRadius: '8px',
          background: 'var(--color-surface-2)', color: 'var(--color-ink-4)',
        }}>
          API Source
        </span>
      </div>
    </div>
  );
}

/* ── Supply Chain Flow Strip ── */

function SupplyChainStrip({ pipelineStatus, graphSummary }: {
  pipelineStatus: Array<{ source_key: string; label: string; schedule: string; last_run: string | null; days_since: number | null; records: number; status: string }>;
  graphSummary: { total_links: number; total_entities: number };
}) {
  const stages = [
    {
      value: String(pipelineStatus.length),
      label: 'Sources',
      sub: `${pipelineStatus.filter(c => c.status === 'fresh' || c.status === 'ok').length} active`,
      color: 'var(--color-accent)',
    },
    { value: fmt(pipelineStatus.reduce((s, c) => s + c.records, 0)), label: 'Records', color: 'var(--color-ink)' },
    { value: fmt(graphSummary.total_entities), label: 'Entities', color: 'var(--color-ink)' },
    { value: fmt(graphSummary.total_links), label: 'Connections', color: 'var(--color-green)' },
  ];

  return (
    <div
      style={{
        padding: '20px 24px',
        background: 'var(--color-surface)',
        border: '1px solid var(--color-line)',
        borderRadius: '16px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: '24px',
        flexWrap: 'wrap',
      }}
    >
      {stages.map((stage, i) => (
        <div key={stage.label} style={{ display: 'flex', alignItems: 'center', gap: '24px' }}>
          {i > 0 && <span style={{ color: 'var(--color-ink-4)', fontSize: '16px' }}>{'\u2192'}</span>}
          <div style={{ textAlign: 'center' }}>
            <div style={{
              fontSize: '22px', fontWeight: 300, fontFamily: 'var(--font-display)',
              color: stage.color, letterSpacing: '-0.02em',
            }}>
              {stage.value}
            </div>
            <div style={{
              fontSize: '10px', color: 'var(--color-ink-4)',
              textTransform: 'uppercase', letterSpacing: '0.04em',
            }}>
              {stage.label}
            </div>
            {stage.sub && (
              <div style={{ fontSize: '10px', color: 'var(--color-green)', marginTop: '2px' }}>{stage.sub}</div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

/* ── Admin Panel (Audit Trail + Curation) ── */

function AdminPanel({ onClose }: { onClose: () => void }) {
  const [adminTab, setAdminTab] = useState<'changes' | 'curation'>('curation');
  const [changes, setChanges] = useState<ChangeLogEntry[]>([]);
  const [hitlItems, setHitlItems] = useState<HITLItem[]>([]);
  const [changesError, setChangesError] = useState<string | null>(null);
  const [hitlError, setHitlError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [bulkLoading, setBulkLoading] = useState(false);

  const loadChanges = useCallback(() => {
    setChangesError(null);
    api.catalogChanges({ limit: 40 })
      .then(r => setChanges(r.changes))
      .catch(err => setChangesError(err instanceof Error ? err.message : 'Unable to load audit trail'));
  }, []);

  const loadHitl = useCallback(() => {
    setHitlError(null);
    api.catalogHITL({ status_filter: 'pending', limit: 30 })
      .then(r => setHitlItems(r.items))
      .catch(err => setHitlError(err instanceof Error ? err.message : 'Unable to load curation queue'));
  }, []);

  useEffect(() => { loadChanges(); loadHitl(); }, [loadChanges, loadHitl]);

  const sorted = useMemo(() => {
    const typeOrder: Record<string, number> = { quality_failure: 0, entity_resolution: 1, duplicate_candidate: 2, enrichment_request: 3 };
    return [...hitlItems].sort((a, b) => {
      const ta = typeOrder[a.review_type] ?? 99;
      const tb = typeOrder[b.review_type] ?? 99;
      if (ta !== tb) return ta - tb;
      return b.priority - a.priority;
    });
  }, [hitlItems]);

  const resolveItem = async (id: string, action: string) => {
    await api.catalogResolveHITL(id, action, '');
    setHitlItems(prev => prev.filter(i => i.id !== id));
    setSelected(prev => { const next = new Set(prev); next.delete(id); return next; });
  };

  const bulkResolve = async (action: string) => {
    if (selected.size === 0) return;
    setBulkLoading(true);
    try {
      await api.catalogBulkResolve([...selected], action);
      setHitlItems(prev => prev.filter(i => !selected.has(i.id)));
      setSelected(new Set());
    } finally {
      setBulkLoading(false);
    }
  };

  return (
    <div style={{
      position: 'fixed', top: 0, right: 0, bottom: 0,
      width: 'min(640px, 95vw)', zIndex: 50,
      background: 'var(--color-surface)', borderLeft: '1px solid var(--color-line)',
      boxShadow: 'var(--shadow-lg)', display: 'flex', flexDirection: 'column',
      animation: 'slide-in-right 0.2s ease-out',
    }}>
      {/* Header */}
      <div style={{
        padding: '20px 24px', borderBottom: '1px solid var(--color-line)',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      }}>
        <div>
          <h2 style={{
            fontFamily: 'var(--font-display)', fontSize: '17px', fontWeight: 500,
            color: 'var(--color-ink)', letterSpacing: '-0.02em',
          }}>
            Admin Panel
          </h2>
          <p style={{ fontSize: '11px', color: 'var(--color-ink-4)', marginTop: '2px' }}>
            Audit trail and curation queue
          </p>
        </div>
        <button
          type="button"
          className="btn-icon"
          onClick={onClose}
          aria-label="Close admin"
        >
          <X size={15} />
        </button>
      </div>

      {/* Tab bar */}
      <div style={{
        display: 'flex', gap: '4px', padding: '12px 24px',
        borderBottom: '1px solid var(--color-line)',
      }}>
        {[
          { key: 'curation' as const, label: `Curation (${hitlItems.length})` },
          { key: 'changes' as const, label: 'Audit Trail' },
        ].map(t => (
          <button
            key={t.key}
            type="button"
            onClick={() => setAdminTab(t.key)}
            style={{
              padding: '6px 14px', borderRadius: '8px', border: 'none', cursor: 'pointer',
              fontSize: '12px', fontWeight: adminTab === t.key ? 600 : 400,
              background: adminTab === t.key ? 'var(--color-surface-2)' : 'transparent',
              color: adminTab === t.key ? 'var(--color-ink)' : 'var(--color-ink-3)',
              fontFamily: 'var(--font-body)',
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Body */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '16px 24px' }}>
        {adminTab === 'curation' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {/* Bulk actions */}
            {sorted.length > 0 && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                <button
                  type="button"
                  onClick={() => {
                    if (selected.size === sorted.length) setSelected(new Set());
                    else setSelected(new Set(sorted.map(i => i.id)));
                  }}
                  className="btn btn-xs btn-secondary"
                  style={{ borderRadius: '6px' }}
                >
                  {selected.size === sorted.length ? 'Deselect All' : 'Select All'}
                </button>
                {selected.size > 0 && (
                  <>
                    <span style={{ fontSize: '12px', color: 'var(--color-ink-4)' }}>{selected.size} selected</span>
                    <button
                      type="button"
                      onClick={() => void bulkResolve('approved')}
                      disabled={bulkLoading}
                      className="btn btn-xs"
                      style={{ background: 'var(--color-green-soft)', color: 'var(--color-green)', borderRadius: '6px', display: 'inline-flex', alignItems: 'center', gap: '4px', border: 'none', cursor: 'pointer', fontFamily: 'var(--font-body)' }}
                    >
                      <CheckCircle size={11} /> Approve
                    </button>
                    <button
                      type="button"
                      onClick={() => void bulkResolve('rejected')}
                      disabled={bulkLoading}
                      className="btn btn-xs"
                      style={{ background: 'var(--color-red-soft)', color: 'var(--color-red)', borderRadius: '6px', display: 'inline-flex', alignItems: 'center', gap: '4px', border: 'none', cursor: 'pointer', fontFamily: 'var(--font-body)' }}
                    >
                      <XCircle size={11} /> Reject
                    </button>
                  </>
                )}
              </div>
            )}
            {hitlError && sorted.length === 0 && (
              <InlineLoadError
                testId="admin-hitl-error"
                message={`Couldn't load the curation queue — ${hitlError}`}
                onRetry={loadHitl}
              />
            )}
            {!hitlError && sorted.length === 0 && (
              <div style={{ padding: '48px 0', textAlign: 'center', color: 'var(--color-ink-4)', fontSize: '13px' }}>
                No pending reviews.
              </div>
            )}
            {sorted.map(item => (
              <div
                key={item.id}
                style={{
                  padding: '16px', borderRadius: '12px',
                  background: selected.has(item.id) ? 'var(--color-accent-soft)' : 'var(--color-surface-2)',
                  border: `1px solid ${selected.has(item.id) ? 'var(--color-accent)' : 'var(--color-line)'}`,
                }}
              >
                <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '12px' }}>
                  <div style={{ display: 'flex', alignItems: 'flex-start', gap: '8px', flex: 1, minWidth: 0 }}>
                    <input
                      type="checkbox"
                      checked={selected.has(item.id)}
                      onChange={() => {
                        setSelected(prev => {
                          const next = new Set(prev);
                          if (next.has(item.id)) next.delete(item.id);
                          else next.add(item.id);
                          return next;
                        });
                      }}
                      style={{ marginTop: '3px', accentColor: 'var(--color-accent)' }}
                    />
                    <div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '4px' }}>
                        <span style={{
                          fontSize: '10px', fontWeight: 600, padding: '2px 8px', borderRadius: '8px',
                          background: 'var(--color-amber-soft)', color: 'var(--color-amber)',
                          textTransform: 'capitalize',
                        }}>
                          {(item.review_type ?? '').replace(/_/g, ' ')}
                        </span>
                        <span style={{ fontSize: '11px', color: 'var(--color-ink-4)' }}>{item.entity_type}</span>
                      </div>
                      <p style={{ fontSize: '12px', color: 'var(--color-ink-2)', lineHeight: 1.5, margin: 0 }}>
                        {String(item.payload?.description ?? item.payload?.raw_value ?? item.entity_id)}
                      </p>
                      <div style={{ fontSize: '10px', color: 'var(--color-ink-4)', marginTop: '4px' }}>
                        Priority {item.priority} \u00B7 {shortDate(item.created_at)}
                      </div>
                    </div>
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', flexShrink: 0 }}>
                    <button
                      type="button"
                      onClick={() => void resolveItem(item.id, 'approved')}
                      className="btn btn-xs"
                      style={{ background: 'var(--color-green-soft)', color: 'var(--color-green)', borderRadius: '8px', display: 'inline-flex', alignItems: 'center', gap: '4px', border: 'none', cursor: 'pointer', padding: '4px 10px', fontFamily: 'var(--font-body)', fontSize: '11px' }}
                    >
                      <CheckCircle size={11} /> Approve
                    </button>
                    <button
                      type="button"
                      onClick={() => void resolveItem(item.id, 'rejected')}
                      className="btn btn-xs"
                      style={{ background: 'var(--color-red-soft)', color: 'var(--color-red)', borderRadius: '8px', display: 'inline-flex', alignItems: 'center', gap: '4px', border: 'none', cursor: 'pointer', padding: '4px 10px', fontFamily: 'var(--font-body)', fontSize: '11px' }}
                    >
                      <XCircle size={11} /> Reject
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {adminTab === 'changes' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0' }}>
            {changes.length === 0 ? (
              changesError ? (
                <InlineLoadError
                  testId="admin-changes-error"
                  message={`Couldn't load the audit trail — ${changesError}`}
                  onRetry={loadChanges}
                />
              ) : (
                <div style={{ padding: '48px 0', textAlign: 'center', color: 'var(--color-ink-4)', fontSize: '13px' }}>
                  No changes recorded.
                </div>
              )
            ) : (
              changes.map(ch => (
                <div key={ch.id} style={{
                  display: 'flex', alignItems: 'center', gap: '12px',
                  padding: '10px 0', borderBottom: '1px solid var(--color-line)',
                }}>
                  <div style={{
                    width: '28px', height: '28px', borderRadius: '8px', flexShrink: 0,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    background: ch.change_type === 'manual_edit' ? 'var(--color-accent-soft)'
                      : ch.change_type === 'created' ? 'var(--color-green-soft)' : 'var(--color-surface-2)',
                    color: ch.change_type === 'manual_edit' ? 'var(--color-accent)'
                      : ch.change_type === 'created' ? 'var(--color-green)' : 'var(--color-ink-4)',
                  }}>
                    {ch.change_type === 'manual_edit' ? <Edit3 size={12} /> : <Clock size={12} />}
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{
                      fontSize: '12px', fontWeight: 500, color: 'var(--color-ink)',
                      overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                    }}>
                      {ch.entity_id}
                    </div>
                    <div style={{ fontSize: '11px', color: 'var(--color-ink-4)' }}>
                      {ch.entity_type} \u00B7 {ch.change_type}
                      {ch.changed_fields?.length ? ` \u00B7 ${ch.changed_fields.join(', ')}` : ''}
                    </div>
                  </div>
                  <div style={{ fontSize: '11px', color: 'var(--color-ink-4)', flexShrink: 0 }}>
                    {shortDate(ch.changed_at)}
                  </div>
                </div>
              ))
            )}
          </div>
        )}
      </div>
    </div>
  );
}

/* ══════════════════════════════════════════════════════
   MAIN COMPONENT
   ══════════════════════════════════════════════════════ */

function DataCatalogPanelInner({ onAskInChat }: Props) {
  /* ── State ── */
  const [loading, setLoading] = useState(true);
  const [health, setHealth] = useState<HealthData | null>(null);
  const [stats, setStats] = useState<CatalogStats | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  // Filter + browse state
  const [activeFilter, setActiveFilter] = useState('all');
  const [browseSearch, setBrowseSearch] = useState('');
  const [searchInput, setSearchInput] = useState('');
  const [browseData, setBrowseData] = useState<CatalogBrowseResponse | null>(null);
  const [browseLoading, setBrowseLoading] = useState(false);
  const [browsePage, setBrowsePage] = useState(0);
  const [browseSort, setBrowseSort] = useState('pipeline_score');
  const [featured, setFeatured] = useState<CatalogEntity[]>([]);

  // Pipeline status (for Sources view and supply chain)
  const [pipelineStatus, setPipelineStatus] = useState<Array<{ source_key: string; label: string; schedule: string; last_run: string | null; days_since: number | null; records: number; status: string }> | null>(null);
  const [graphSummary, setGraphSummary] = useState<{ link_types: Array<{ type: string; count: number }>; total_links: number; total_entities: number; drug_completeness: Record<string, number> } | null>(null);
  const [pipelineError, setPipelineError] = useState<string | null>(null);
  const [graphError, setGraphError] = useState<string | null>(null);

  // Entity profile slide-in
  const [selectedEntity, setSelectedEntity] = useState<{ type: string; id: string } | null>(null);
  const [entityProfile, setEntityProfile] = useState<EntityProfileData | null>(null);
  const [profileLoading, setProfileLoading] = useState(false);
  const [profileError, setProfileError] = useState<string | null>(null);
  const [profileOpen, setProfileOpen] = useState(false);

  // Legacy entity drawer
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [entityDetail, setEntityDetail] = useState<CatalogEntityDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [editing, setEditing] = useState<Record<string, string>>({});

  // Literature explorer
  const [litExplorerArticleId, setLitExplorerArticleId] = useState<string | null>(null);

  // Source profile slide-in
  const [srcProfile, setSrcProfile] = useState<SourceProfileData | null>(null);
  const [srcProfileLoading, setSrcProfileLoading] = useState(false);
  const [srcProfileError, setSrcProfileError] = useState<string | null>(null);
  const [srcProfileOpen, setSrcProfileOpen] = useState(false);
  const [srcProfileKey, setSrcProfileKey] = useState<string>('');

  // Legacy dataset profile
  const [dsProfileOpen, setDsProfileOpen] = useState(false);
  const [dsProfile, setDsProfile] = useState<DatasetProfile | null>(null);
  const [dsProfileLoading, setDsProfileLoading] = useState(false);

  // Admin panel
  const [adminOpen, setAdminOpen] = useState(false);

  // Debounce ref for search
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  /* ── Data loading ── */

  const openDatasetProfile = useCallback((sourceKey: string) => {
    setSrcProfileKey(sourceKey);
    setSrcProfileOpen(true);
    setSrcProfileLoading(true);
    setSrcProfileError(null);
    setSrcProfile(null);
    api.sourceProfile(sourceKey)
      .then(setSrcProfile)
      .catch((err) => setSrcProfileError(String(err)))
      .finally(() => setSrcProfileLoading(false));

    setDsProfileOpen(false);
    setDsProfileLoading(true);
    setDsProfile(null);
    api.datasetProfile(sourceKey)
      .then(setDsProfile)
      .catch(() => setDsProfile(null))
      .finally(() => setDsProfileLoading(false));
  }, []);

  const loadOverview = useCallback(async (initial = false) => {
    if (initial) setLoading(true);
    else setRefreshing(true);
    try {
      const [h, s] = await Promise.all([
        api.health(),
        api.catalogStats().catch(() => null),
        api.catalogDatasets().catch(() => ({ datasets: [], count: 0 })),
      ]);
      setHealth(h);
      setStats(s);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { void loadOverview(true); }, [loadOverview]);

  // Load pipeline status and graph summary — a failure must surface an honest
  // error, not silently drop the supply-chain strip (indistinguishable from
  // still-loading).
  const loadPipeline = useCallback(() => {
    setPipelineError(null);
    api.catalogPipelineStatus()
      .then(r => setPipelineStatus(r.connectors))
      .catch(err => setPipelineError(err instanceof Error ? err.message : 'Unable to load pipeline status'));
  }, []);
  const loadGraphSummary = useCallback(() => {
    setGraphError(null);
    api.catalogGraphSummary()
      .then(r => setGraphSummary(r))
      .catch(err => setGraphError(err instanceof Error ? err.message : 'Unable to load graph summary'));
  }, []);
  useEffect(() => { loadPipeline(); loadGraphSummary(); }, [loadPipeline, loadGraphSummary]);

  // Load featured entities
  useEffect(() => {
    api.catalogBrowse('drug', { sort: 'pipeline_score', limit: 3 })
      .then(res => setFeatured(res.results))
      .catch(() => setFeatured([]));
  }, []);

  // Load browse data
  const loadBrowse = useCallback(async () => {
    if (activeFilter === 'sources') return;
    const entityType = activeFilter === 'all' ? 'drug' : activeFilter;
    setBrowseLoading(true);
    try {
      const sortMap: Record<string, string> = {
        pipeline_score: 'pipeline_score',
        quality: 'quality',
        name: 'name',
        recent: 'recent',
      };
      const res = await api.catalogBrowse(entityType, {
        search: browseSearch || undefined,
        sort: sortMap[browseSort] ?? 'pipeline_score',
        limit: 30,
        offset: browsePage * 30,
      });
      setBrowseData(res);
    } catch {
      setBrowseData(null);
    } finally {
      setBrowseLoading(false);
    }
  }, [activeFilter, browseSearch, browsePage, browseSort]);

  useEffect(() => {
    if (activeFilter !== 'sources') void loadBrowse();
  }, [loadBrowse, activeFilter]);

  // When filter changes to "all", also load multiple types for featured
  useEffect(() => {
    if (activeFilter === 'all') {
      // Load 3 featured from drug, company, and mechanism for the "all" view
      Promise.all([
        api.catalogBrowse('drug', { sort: 'pipeline_score', limit: 1 }).catch(() => ({ results: [] })),
        api.catalogBrowse('company', { sort: 'pipeline_score', limit: 1 }).catch(() => ({ results: [] })),
        api.catalogBrowse('mechanism', { sort: 'pipeline_score', limit: 1 }).catch(() => ({ results: [] })),
      ]).then(([drugs, companies, mechanisms]) => {
        const mixed: Array<CatalogEntity & { __type: string }> = [];
        if (drugs.results[0]) mixed.push({ ...drugs.results[0], __type: 'drug' });
        if (companies.results[0]) mixed.push({ ...companies.results[0], __type: 'company' });
        if (mechanisms.results[0]) mixed.push({ ...mechanisms.results[0], __type: 'mechanism' });
        setFeatured(mixed as unknown as CatalogEntity[]);
      });
    } else if (activeFilter !== 'sources') {
      api.catalogBrowse(activeFilter, { sort: 'pipeline_score', limit: 3 })
        .then(res => setFeatured(res.results))
        .catch(() => setFeatured([]));
    }
  }, [activeFilter]);

  /* ── Entity open ── */

  const openEntity = useCallback((type: string, id: string) => {
    if (type === 'article' || type === 'literature') {
      setLitExplorerArticleId(id);
      return;
    }
    setSelectedEntity({ type, id });
    setProfileOpen(true);
    setProfileLoading(true);
    setProfileError(null);
    setEntityProfile(null);
    api.entityProfile(type, id)
      .then(setEntityProfile)
      .catch((err) => setProfileError(String(err)))
      .finally(() => setProfileLoading(false));

    setDrawerOpen(false);
    setDetailLoading(true);
    setEntityDetail(null);
    api.catalogEntityDetail(type, id)
      .then(setEntityDetail)
      .catch(() => setEntityDetail(null))
      .finally(() => setDetailLoading(false));
  }, []);

  /* ── Search debounce ── */
  const handleSearchInput = (value: string) => {
    setSearchInput(value);
    if (searchTimer.current) clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(() => {
      setBrowseSearch(value);
      setBrowsePage(0);
    }, 300);
  };

  const handleSearchSubmit = () => {
    if (searchTimer.current) clearTimeout(searchTimer.current);
    setBrowseSearch(searchInput);
    setBrowsePage(0);
  };

  /* ── Derived ── */
  const totalPages = browseData ? Math.ceil(browseData.total / browseData.limit) : 0;
  const showSources = activeFilter === 'sources';

  /* ── Render ── */
  return (
    <div
      style={{
        display: 'flex', flexDirection: 'column', height: '100%',
        overflow: 'hidden', background: 'var(--color-bg)',
      }}
    >
      {/* ── Header ── */}
      <div
        style={{
          flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          borderBottom: '1px solid var(--color-line)', background: 'var(--color-surface)',
          padding: '20px 32px',
        }}
      >
        <div>
          <h2 style={{
            fontSize: '17px', fontWeight: 600, color: 'var(--color-ink)',
            letterSpacing: '-0.02em', fontFamily: 'var(--font-display)',
          }}>
            Entity Library
          </h2>
          <p style={{ fontSize: '12px', color: 'var(--color-ink-4)', marginTop: '2px' }}>
            Discover, explore, and curate pharma intelligence
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <button
            type="button"
            onClick={() => setAdminOpen(true)}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: '4px',
              padding: '6px 12px', borderRadius: '8px', border: 'none', cursor: 'pointer',
              background: 'var(--color-surface-2)', color: 'var(--color-ink-4)',
              fontSize: '12px', fontWeight: 500, fontFamily: 'var(--font-body)',
            }}
          >
            <Settings size={13} />
            Admin
          </button>
          <span style={{
            padding: '3px 10px', borderRadius: '10px', fontSize: '11px', fontWeight: 500,
            background: health?.status === 'ok' ? 'var(--color-green-soft)' : 'var(--color-surface-2)',
            color: health?.status === 'ok' ? 'var(--color-green)' : 'var(--color-ink-4)',
          }}>
            {health?.status === 'ok' ? 'Online' : health?.status ?? '\u2014'}
          </span>
          <button
            type="button"
            onClick={() => void loadOverview(false)}
            disabled={refreshing}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: '6px',
              padding: '6px 14px', borderRadius: '10px', border: '1px solid var(--color-line)',
              background: 'var(--color-surface)', color: 'var(--color-ink-3)',
              fontSize: '12px', fontWeight: 500, cursor: 'pointer', fontFamily: 'var(--font-body)',
            }}
          >
            <RefreshCw size={12} className={refreshing ? 'animate-spin' : ''} />
            Refresh
          </button>
        </div>
      </div>

      {/* ── Body ── */}
      <div style={{
        flex: 1, overflowY: 'auto', minHeight: 0,
        maxWidth: '1200px', marginLeft: 'auto', marginRight: 'auto',
        width: '100%', padding: '24px 32px',
      }}>
        {loading ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <Skeleton width="100%" height="80px" />
            <div style={{ display: 'flex', gap: '8px' }}>
              {Array.from({ length: 7 }).map((_, i) => (
                <Skeleton key={i} width="80px" height="32px" />
              ))}
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '16px' }}>
              {Array.from({ length: 6 }).map((_, i) => (
                <SkeletonCard key={i} />
              ))}
            </div>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            {/* ── Search Bar ── */}
            <div style={{ position: 'relative' }}>
              <Search
                size={16}
                style={{
                  position: 'absolute', left: '16px', top: '50%',
                  transform: 'translateY(-50%)', color: 'var(--color-ink-4)',
                  pointerEvents: 'none',
                }}
              />
              <input
                value={searchInput}
                onChange={e => handleSearchInput(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') handleSearchSubmit(); }}
                placeholder="Search entities, sources, or ask a question..."
                style={{
                  width: '100%', padding: '14px 16px 14px 44px',
                  borderRadius: '14px', border: '1px solid var(--color-line)',
                  background: 'var(--color-surface)', color: 'var(--color-ink)',
                  fontSize: '14px', fontFamily: 'var(--font-body)', outline: 'none',
                  transition: 'border-color 0.15s ease',
                }}
                onFocus={e => { e.currentTarget.style.borderColor = 'var(--color-accent)'; }}
                onBlur={e => { e.currentTarget.style.borderColor = 'var(--color-line)'; }}
              />
            </div>

            {/* ── Filter Pills ── */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
              {ENTITY_FILTERS.map(f => {
                const isActive = activeFilter === f.key;
                const count = f.key !== 'all' && f.key !== 'sources' && stats?.entity_counts?.[f.key];
                return (
                  <button
                    key={f.key}
                    type="button"
                    onClick={() => { setActiveFilter(f.key); setBrowsePage(0); }}
                    style={{
                      padding: '7px 14px', borderRadius: '10px', border: 'none', cursor: 'pointer',
                      fontSize: '12px', fontWeight: isActive ? 600 : 400,
                      background: isActive ? 'var(--color-ink)' : 'var(--color-surface-2)',
                      color: isActive ? 'var(--color-surface)' : 'var(--color-ink-3)',
                      transition: 'all 0.12s ease', fontFamily: 'var(--font-body)',
                      display: 'inline-flex', alignItems: 'center', gap: '4px',
                    }}
                  >
                    {f.label}
                    {count ? (
                      <span style={{ fontSize: '10px', opacity: 0.7 }}>{fmt(count as number)}</span>
                    ) : null}
                  </button>
                );
              })}
            </div>

            {/* ── Sort + View controls ── */}
            {!showSources && (
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span style={{ fontSize: '11px', color: 'var(--color-ink-4)' }}>Sort:</span>
                  <select
                    value={browseSort}
                    onChange={e => { setBrowseSort(e.target.value); setBrowsePage(0); }}
                    style={{
                      fontSize: '11px', fontWeight: 500, color: 'var(--color-ink)',
                      background: 'var(--color-surface-2)', border: '1px solid var(--color-line)',
                      borderRadius: '8px', padding: '5px 10px', cursor: 'pointer', outline: 'none',
                      fontFamily: 'var(--font-body)',
                    }}
                  >
                    {SORT_OPTIONS.map(opt => (
                      <option key={opt.key} value={opt.key}>{opt.label}</option>
                    ))}
                  </select>
                </div>
                {browseData && (
                  <span style={{ fontSize: '12px', color: 'var(--color-ink-4)' }}>
                    {fmt(browseData.total)} entities
                  </span>
                )}
              </div>
            )}

            {/* ── Supply Chain Flow ── */}
            {pipelineStatus && graphSummary && (
              <SupplyChainStrip pipelineStatus={pipelineStatus} graphSummary={graphSummary} />
            )}
            {(pipelineError || graphError) && !(pipelineStatus && graphSummary) && (
              <InlineLoadError
                testId="pipeline-load-error"
                message={`Couldn't load pipeline status — ${pipelineError ?? graphError}`}
                onRetry={() => { loadPipeline(); loadGraphSummary(); }}
              />
            )}

            {/* ── Sources View ── */}
            {showSources && pipelineStatus && (
              <div>
                <div style={{
                  fontSize: '12px', fontWeight: 600, color: 'var(--color-ink-3)',
                  textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: '12px',
                }}>
                  Data Pipeline \u2014 {pipelineStatus.length} Connectors
                </div>
                <div style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
                  gap: '16px',
                }}>
                  {pipelineStatus.map(c => (
                    <SourceCard
                      key={c.source_key}
                      connector={c}
                      onOpen={() => openDatasetProfile(c.source_key)}
                    />
                  ))}
                </div>
              </div>
            )}

            {/* ── Entity Content ── */}
            {!showSources && (
              <>
                {/* Featured entities — only on first page, no search */}
                {featured.length > 0 && browsePage === 0 && !browseSearch && (
                  <div>
                    <div style={{
                      fontSize: '12px', fontWeight: 600, color: 'var(--color-ink-3)',
                      textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: '12px',
                      display: 'flex', alignItems: 'center', gap: '6px',
                    }}>
                      <span style={{ fontSize: '13px', color: 'var(--color-amber)' }}>{'\u2605'}</span>
                      Featured Entities
                    </div>
                    <div style={{
                      display: 'grid',
                      gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
                      gap: '16px',
                    }}>
                      {featured.map(entity => {
                        const id = String(entity.id ?? entity._label ?? '');
                        // Determine the type — for "all" view, featured may have __type property
                        const eType = String((entity as Record<string, unknown>).__type || activeFilter || 'drug');
                        return (
                          <EntityCard
                            key={id}
                            entity={entity}
                            entityType={eType}
                            onOpen={() => id && openEntity(eType, id)}
                            featured
                          />
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* All entities section header */}
                <div style={{
                  fontSize: '12px', fontWeight: 600, color: 'var(--color-ink-3)',
                  textTransform: 'uppercase', letterSpacing: '0.06em',
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                }}>
                  <span>
                    {activeFilter === 'all' ? 'All Entities' : ENTITY_TYPE_LABELS[activeFilter] || displayName(activeFilter)}
                  </span>
                  {/* Pagination */}
                  {totalPages > 1 && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <button
                        type="button"
                        disabled={browsePage === 0}
                        onClick={() => setBrowsePage(browsePage - 1)}
                        className="btn-icon"
                        style={{ width: '28px', height: '28px', opacity: browsePage === 0 ? 0.3 : 1 }}
                      >
                        <ChevronLeft size={13} />
                      </button>
                      <span style={{ fontSize: '11px', color: 'var(--color-ink-4)', padding: '0 6px' }}>
                        {browsePage + 1} / {totalPages}
                      </span>
                      <button
                        type="button"
                        disabled={browsePage + 1 >= totalPages}
                        onClick={() => setBrowsePage(browsePage + 1)}
                        className="btn-icon"
                        style={{ width: '28px', height: '28px', opacity: browsePage + 1 >= totalPages ? 0.3 : 1 }}
                      >
                        <ChevronRight size={13} />
                      </button>
                    </div>
                  )}
                </div>

                {/* Entity grid */}
                {browseLoading ? (
                  <div style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
                    gap: '16px',
                  }}>
                    {Array.from({ length: 6 }).map((_, i) => (
                      <SkeletonCard key={i} />
                    ))}
                  </div>
                ) : !browseData || browseData.results.length === 0 ? (
                  <div style={{
                    padding: '60px 24px', textAlign: 'center',
                    background: 'var(--color-surface)', borderRadius: '16px',
                    border: '1px solid var(--color-line)',
                  }}>
                    <div style={{ fontSize: '32px', marginBottom: '12px' }}>{'\uD83D\uDD0D'}</div>
                    <div style={{
                      fontSize: '14px', fontWeight: 500, color: 'var(--color-ink)',
                      fontFamily: 'var(--font-display)',
                    }}>
                      No entities found
                    </div>
                    <div style={{ fontSize: '12px', color: 'var(--color-ink-4)', marginTop: '6px' }}>
                      {browseSearch
                        ? `No results for "${browseSearch}". Try a different term.`
                        : 'Try selecting a different entity type or adjusting filters.'}
                    </div>
                  </div>
                ) : (
                  <div style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
                    gap: '16px',
                  }}>
                    {browseData.results.map(entity => {
                      const id = String(entity.id ?? entity.nct_id ?? entity._label ?? '');
                      const eType = activeFilter === 'all' ? 'drug' : activeFilter;
                      return (
                        <EntityCard
                          key={id}
                          entity={entity}
                          entityType={eType}
                          onOpen={() => id && openEntity(eType, id)}
                        />
                      );
                    })}
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </div>

      {/* ── Entity Profile slide-in ── */}
      {profileOpen && selectedEntity && (
        <div
          style={{
            position: 'fixed', top: 0, right: 0, bottom: 0,
            width: 'min(520px, 90vw)', zIndex: 50,
            background: 'var(--color-surface)',
            borderLeft: '1px solid var(--color-line)',
            boxShadow: 'var(--shadow-lg)', overflowY: 'auto',
            animation: 'slide-in-right 0.2s ease-out',
          }}
        >
          <EntityProfileCard
            data={entityProfile}
            isLoading={profileLoading}
            error={profileError}
            onClose={() => { setProfileOpen(false); setSelectedEntity(null); }}
            onAskInChat={(name) => { setProfileOpen(false); onAskInChat?.(`Tell me about ${name}`); }}
            onExploreGraph={() => { setProfileOpen(false); }}
          />
        </div>
      )}

      {/* Legacy entity drawer */}
      <Drawer
        isOpen={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        title={
          entityDetail?.entity?._label as string
          ?? entityDetail?.entity?.generic_name as string
          ?? entityDetail?.entity?.name as string
          ?? 'Entity'
        }
        subtitle={selectedEntity ? displayName(selectedEntity.type) : undefined}
      >
        {detailLoading ? (
          <div style={{ color: 'var(--color-ink-4)', fontSize: '13px' }}>Loading...</div>
        ) : entityDetail ? (
          <EntityDossier
            detail={entityDetail}
            editing={editing}
            onEditField={(f, v) => setEditing(prev => ({ ...prev, [f]: v }))}
            onSave={async () => {
              if (!selectedEntity || !Object.keys(editing).length) return;
              await api.catalogUpdateEntity(selectedEntity.type, selectedEntity.id, editing);
              setEditing({});
            }}
            onAskInChat={onAskInChat}
          />
        ) : (
          <div style={{ color: 'var(--color-ink-4)', fontSize: '13px' }}>Not found.</div>
        )}
      </Drawer>

      {/* Source Profile slide-in */}
      {srcProfileOpen && (
        <div
          style={{
            position: 'fixed', top: 0, right: 0, bottom: 0,
            width: 'min(520px, 90vw)', zIndex: 50,
            background: 'var(--color-surface)',
            borderLeft: '1px solid var(--color-line)',
            boxShadow: 'var(--shadow-lg)', overflowY: 'auto',
            animation: 'slide-in-right 0.2s ease-out',
          }}
        >
          <SourceProfileCard
            data={srcProfile}
            isLoading={srcProfileLoading}
            error={srcProfileError}
            onClose={() => setSrcProfileOpen(false)}
            onRefresh={() => {
              fetch('/steward/refresh', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ source: srcProfileKey }),
              }).catch(() => {});
            }}
          />
        </div>
      )}

      {/* Legacy dataset profile drawer */}
      <Drawer
        isOpen={dsProfileOpen}
        onClose={() => setDsProfileOpen(false)}
        title={dsProfile?.display_name ?? 'Dataset Profile'}
        subtitle={dsProfile?.source_key}
      >
        {dsProfileLoading ? (
          <div style={{ color: 'var(--color-ink-4)', fontSize: '13px' }}>Loading profile...</div>
        ) : dsProfile ? (
          <DatasetProfileCard profile={dsProfile} />
        ) : (
          <div style={{ color: 'var(--color-ink-4)', fontSize: '13px' }}>Profile not available.</div>
        )}
      </Drawer>

      {/* Literature Explorer overlay */}
      {litExplorerArticleId && (
        <LiteratureExplorer
          articleId={litExplorerArticleId}
          onClose={() => setLitExplorerArticleId(null)}
        />
      )}

      {/* Admin panel slide-in */}
      {adminOpen && (
        <AdminPanel onClose={() => setAdminOpen(false)} />
      )}
    </div>
  );
}

/* ── Legacy DatasetProfileCard (kept for drawer fallback) ── */

function DatasetProfileCard({ profile }: { profile: DatasetProfile }) {
  const freshnessStyle = profile.freshness === 'fresh'
    ? { bg: 'var(--color-green-soft)', color: 'var(--color-green)' }
    : profile.freshness === 'recent'
      ? { bg: 'var(--color-amber-soft)', color: 'var(--color-amber)' }
      : profile.freshness === 'stale'
        ? { bg: 'var(--color-red-soft)', color: 'var(--color-red)' }
        : { bg: 'var(--color-surface-2)', color: 'var(--color-ink-4)' };

  const qualityColor = profile.quality_score != null
    ? profile.quality_score >= 0.7 ? 'var(--color-green)'
      : profile.quality_score >= 0.4 ? 'var(--color-amber)'
        : 'var(--color-red)'
    : 'var(--color-ink-4)';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <p style={{ fontSize: '13px', lineHeight: 1.6, color: 'var(--color-ink-3)' }}>
        {profile.description}
      </p>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '12px' }}>
        <div style={{
          padding: '14px 16px', borderRadius: '12px',
          background: 'var(--color-surface-2)', border: '1px solid var(--color-line)',
        }}>
          <div style={{ fontSize: '20px', fontWeight: 300, color: 'var(--color-ink)', fontFamily: 'var(--font-display)', letterSpacing: '-0.02em' }}>
            {fmt(profile.records)}
          </div>
          <div style={{ fontSize: '10px', color: 'var(--color-ink-4)', marginTop: '2px', textTransform: 'uppercase', letterSpacing: '0.04em' }}>Records</div>
        </div>
        <div style={{
          padding: '14px 16px', borderRadius: '12px',
          background: 'var(--color-surface-2)', border: '1px solid var(--color-line)',
        }}>
          <div style={{ fontSize: '20px', fontWeight: 300, color: qualityColor, fontFamily: 'var(--font-display)', letterSpacing: '-0.02em' }}>
            {profile.quality_score != null ? `${(profile.quality_score * 100).toFixed(0)}%` : '--'}
          </div>
          <div style={{ fontSize: '10px', color: 'var(--color-ink-4)', marginTop: '2px', textTransform: 'uppercase', letterSpacing: '0.04em' }}>Quality</div>
        </div>
        <div style={{
          padding: '14px 16px', borderRadius: '12px',
          background: 'var(--color-surface-2)', border: '1px solid var(--color-line)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ width: '7px', height: '7px', borderRadius: '50%', background: freshnessStyle.color, flexShrink: 0 }} />
            <span style={{ fontSize: '14px', fontWeight: 500, color: freshnessStyle.color, textTransform: 'capitalize' }}>
              {profile.freshness}
            </span>
          </div>
          <div style={{ fontSize: '10px', color: 'var(--color-ink-4)', marginTop: '4px', textTransform: 'uppercase', letterSpacing: '0.04em' }}>Freshness</div>
        </div>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0' }}>
        {[
          { label: 'Entity Types', value: profile.entity_types.map(t => displayName(t)).join(', ') },
          { label: 'Collection Method', value: profile.collection_method },
          { label: 'Refresh Schedule', value: profile.refresh_schedule },
          { label: 'Last Refreshed', value: profile.last_refreshed ? shortDate(profile.last_refreshed) : 'Unknown' },
        ].map(({ label, value }) => (
          <div
            key={label}
            style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              padding: '10px 0', borderBottom: '1px solid var(--color-line)', fontSize: '12px',
            }}
          >
            <span style={{ color: 'var(--color-ink-4)' }}>{label}</span>
            <span style={{ color: 'var(--color-ink)', fontWeight: 500 }}>{value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ── Export ── */

export default function DataCatalogPanel(props: Props) {
  return (
    <ErrorBoundary>
      <DataCatalogPanelInner {...props} />
    </ErrorBoundary>
  );
}
