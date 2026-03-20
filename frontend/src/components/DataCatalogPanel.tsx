import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  CheckCircle,
  ChevronLeft,
  ChevronRight,
  Clock,
  Database,
  Edit3,
  MessageSquare,
  RefreshCw,
  Search,
  Shield,
  X,
  XCircle,
} from 'lucide-react';
import {
  api,
  type CatalogBrowseResponse,
  type CatalogDataset,
  type CatalogEntityDetail,
  type CatalogStats,
  type ChangeLogEntry,
  type EntityLink,
  type FieldCompleteness,
  type HealthData,
  type HITLItem,
  type SourceFreshness,
} from '../api';
import { Drawer } from './ui/Drawer';

interface Props {
  onAskInChat?: (question: string) => void;
}

type CatalogTab = 'overview' | 'browse' | 'changes' | 'curation';

const ENTITY_TYPES = [
  { value: 'drug', label: 'Drugs' },
  { value: 'company', label: 'Companies' },
  { value: 'trial', label: 'Trials' },
  { value: 'therapeutic_area', label: 'Therapeutic Areas' },
  { value: 'mechanism', label: 'Mechanisms' },
  { value: 'article', label: 'Articles' },
];

function fmt(n: number) {
  return new Intl.NumberFormat().format(n);
}

function freshness(date: string | null | undefined): { label: string; color: string } {
  if (!date) return { label: 'Unknown', color: 'var(--color-ink-4)' };
  const days = Math.floor((Date.now() - new Date(date).getTime()) / 86_400_000);
  if (days <= 7) return { label: 'Fresh', color: 'var(--color-green)' };
  if (days <= 30) return { label: 'Recent', color: 'var(--color-amber)' };
  return { label: 'Stale', color: 'var(--color-red)' };
}

function shortDate(v: string | null | undefined) {
  if (!v) return '—';
  return new Date(v).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

/* ══════════════════════════════════════════════════════ */

export default function DataCatalogPanel({ onAskInChat }: Props) {
  const [tab, setTab] = useState<CatalogTab>('overview');
  const [loading, setLoading] = useState(true);
  const [health, setHealth] = useState<HealthData | null>(null);
  const [stats, setStats] = useState<CatalogStats | null>(null);
  const [datasets, setDatasets] = useState<CatalogDataset[]>([]);
  const [refreshing, setRefreshing] = useState(false);

  const [browseType, setBrowseType] = useState('drug');
  const [browseSearch, setBrowseSearch] = useState('');
  const [browseData, setBrowseData] = useState<CatalogBrowseResponse | null>(null);
  const [browseLoading, setBrowseLoading] = useState(false);
  const [browsePage, setBrowsePage] = useState(0);

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [selectedEntity, setSelectedEntity] = useState<{ type: string; id: string } | null>(null);
  const [entityDetail, setEntityDetail] = useState<CatalogEntityDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const [changes, setChanges] = useState<ChangeLogEntry[]>([]);
  const [hitlItems, setHitlItems] = useState<HITLItem[]>([]);

  const [editing, setEditing] = useState<Record<string, string>>({});

  const loadOverview = useCallback(async (initial = false) => {
    if (initial) setLoading(true);
    else setRefreshing(true);
    try {
      const [h, s, d] = await Promise.all([
        api.health(),
        api.catalogStats().catch(() => null),
        api.catalogDatasets().catch(() => ({ datasets: [], count: 0 })),
      ]);
      setHealth(h);
      setStats(s);
      setDatasets(d.datasets);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { void loadOverview(true); }, [loadOverview]);

  const loadBrowse = useCallback(async () => {
    setBrowseLoading(true);
    try {
      const res = await api.catalogBrowse(browseType, {
        search: browseSearch || undefined, limit: 30, offset: browsePage * 30,
      });
      setBrowseData(res);
    } catch { setBrowseData(null); }
    finally { setBrowseLoading(false); }
  }, [browseType, browseSearch, browsePage]);

  useEffect(() => { if (tab === 'browse') void loadBrowse(); }, [tab, loadBrowse]);

  useEffect(() => {
    if (tab === 'changes') {
      api.catalogChanges({ limit: 40 }).then(r => setChanges(r.changes)).catch(() => {});
    }
    if (tab === 'curation') {
      api.catalogHITL({ status_filter: 'pending', limit: 30 }).then(r => setHitlItems(r.items)).catch(() => {});
    }
  }, [tab]);

  const openEntity = useCallback((type: string, id: string) => {
    setSelectedEntity({ type, id });
    setDrawerOpen(true);
    setDetailLoading(true);
    setEntityDetail(null);
    api.catalogEntityDetail(type, id)
      .then(setEntityDetail)
      .catch(() => setEntityDetail(null))
      .finally(() => setDetailLoading(false));
  }, []);

  const TABS: Array<{ key: CatalogTab; label: string }> = [
    { key: 'overview', label: 'Overview' },
    { key: 'browse', label: 'Browse' },
    { key: 'changes', label: 'Audit Trail' },
    { key: 'curation', label: 'Curation' },
  ];

  return (
    <div
      className="flex h-full flex-col overflow-hidden"
      style={{ background: 'var(--color-bg)' }}
    >
      {/* Top strip */}
      <div
        className="shrink-0 px-8 py-5 flex items-center justify-between"
        style={{ borderBottom: '1px solid var(--color-line)', background: 'var(--color-surface)' }}
      >
        <div>
          <h2
            style={{ fontSize: '17px', fontWeight: 600, color: 'var(--color-ink)', letterSpacing: '-0.02em' }}
          >
            Data Catalog
          </h2>
          <p style={{ fontSize: '12px', color: 'var(--color-ink-4)', marginTop: '2px' }}>
            Browse, inspect, and curate the knowledge base
          </p>
        </div>

        <div className="flex items-center gap-3">
          <span
            className="badge badge-green"
          >
            {health?.status === 'ok' ? 'Online' : health?.status ?? '—'}
          </span>
          <button
            type="button"
            onClick={() => void loadOverview(false)}
            className="btn btn-secondary btn-sm flex items-center gap-1.5"
            disabled={refreshing}
          >
            <RefreshCw size={12} className={refreshing ? 'animate-spin' : ''} />
            Refresh
          </button>
        </div>
      </div>

      {/* Tab bar */}
      <div
        className="shrink-0 flex items-center gap-1 px-8 py-3"
        style={{ borderBottom: '1px solid var(--color-line)', background: 'var(--color-surface)' }}
      >
        {TABS.map(t => (
          <button
            key={t.key}
            type="button"
            onClick={() => setTab(t.key)}
            className="nav-tab"
            style={{
              background: tab === t.key ? 'var(--color-surface-2)' : 'transparent',
              color: tab === t.key ? 'var(--color-ink)' : 'var(--color-ink-3)',
              fontWeight: tab === t.key ? 600 : 400,
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto px-8 py-6" style={{ minHeight: 0 }}>
        {loading ? (
          <div style={{ color: 'var(--color-ink-4)', fontSize: '13px', padding: '24px 0' }}>
            Loading catalog…
          </div>
        ) : (
          <>
            {tab === 'overview' && (
              <OverviewTab
                health={health}
                stats={stats}
                datasets={datasets}
                onBrowse={type => { setBrowseType(type); setTab('browse'); }}
              />
            )}
            {tab === 'browse' && (
              <BrowseTab
                browseType={browseType}
                onTypeChange={t => { setBrowseType(t); setBrowsePage(0); }}
                search={browseSearch}
                onSearch={setBrowseSearch}
                data={browseData}
                loading={browseLoading}
                page={browsePage}
                onPage={setBrowsePage}
                onOpen={openEntity}
                onAskInChat={onAskInChat}
              />
            )}
            {tab === 'changes' && <ChangesTab changes={changes} />}
            {tab === 'curation' && (
              <CurationTab
                items={hitlItems}
                onResolve={async (id, action) => {
                  await api.catalogResolveHITL(id, action, '');
                  setHitlItems(prev => prev.filter(i => i.id !== id));
                }}
              />
            )}
          </>
        )}
      </div>

      {/* Entity drawer */}
      <Drawer
        isOpen={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        title={
          entityDetail?.entity?._label as string
          ?? entityDetail?.entity?.generic_name as string
          ?? entityDetail?.entity?.name as string
          ?? 'Entity'
        }
        subtitle={selectedEntity ? `${selectedEntity.type} · ${selectedEntity.id.slice(0, 12)}…` : undefined}
      >
        {detailLoading ? (
          <div style={{ color: 'var(--color-ink-4)', fontSize: '13px' }}>Loading…</div>
        ) : entityDetail ? (
          <EntityDetailDrawer
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
    </div>
  );
}

/* ══ Overview ══ */
function OverviewTab({ health, stats, datasets, onBrowse }: {
  health: HealthData | null;
  stats: CatalogStats | null;
  datasets: CatalogDataset[];
  onBrowse: (type: string) => void;
}) {
  const [completeness, setCompleteness] = useState<Record<string, FieldCompleteness> | null>(null);
  const [freshData, setFreshData] = useState<Record<string, SourceFreshness> | null>(null);

  useEffect(() => {
    api.catalogCompleteness().then(r => setCompleteness(r.completeness)).catch(() => {});
    api.catalogFreshness().then(r => setFreshData(r.freshness)).catch(() => {});
  }, []);

  const staleCount = freshData ? Object.values(freshData).filter(s => s.stale).length : 0;

  return (
    <div className="space-y-8">
      {/* Stale data alert */}
      {staleCount > 0 && (
        <div
          className="rounded-xl px-5 py-3 flex items-center gap-3"
          style={{ background: 'var(--color-amber-soft)', border: '1px solid var(--color-amber)' }}
        >
          <Clock size={16} style={{ color: 'var(--color-amber)', flexShrink: 0 }} />
          <span style={{ fontSize: '13px', color: 'var(--color-amber)' }}>
            {staleCount} source{staleCount > 1 ? 's' : ''} have not been refreshed in &gt;30 days
          </span>
        </div>
      )}

      {/* Stat row */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
        {[
          { label: 'Records', value: fmt(health?.total_records ?? 0) },
          { label: 'Sources', value: fmt(health?.source_coverage?.length ?? 0) },
          { label: 'Avg Quality', value: stats?.quality?.avg_score != null ? `${(Number(stats.quality.avg_score) * 100).toFixed(0)}%` : '—' },
          { label: 'Issues', value: fmt(stats?.quality?.failures ?? 0) },
          { label: 'Pending HITL', value: fmt(stats?.hitl?.pending ?? 0), urgent: (stats?.hitl?.pending ?? 0) > 100 },
          { label: 'Changes', value: fmt(stats?.changes?.recent_changes ?? 0) },
        ].map(({ label, value, urgent }) => (
          <div
            key={label}
            className="rounded-2xl p-5"
            style={{
              background: 'var(--color-surface)',
              border: `1px solid ${urgent ? 'var(--color-amber)' : 'var(--color-line)'}`,
            }}
          >
            <div style={{ fontSize: '24px', fontWeight: 300, color: urgent ? 'var(--color-amber)' : 'var(--color-ink)', fontFamily: 'var(--font-display)', letterSpacing: '-0.02em' }}>
              {value}
            </div>
            <div style={{ fontSize: '11px', color: 'var(--color-ink-4)', marginTop: '4px' }}>{label}</div>
          </div>
        ))}
      </div>

      {/* Completeness bars */}
      {completeness && (
        <div
          className="rounded-2xl overflow-hidden"
          style={{ background: 'var(--color-surface)', border: '1px solid var(--color-line)' }}
        >
          <div className="px-6 py-4" style={{ borderBottom: '1px solid var(--color-line)' }}>
            <h3 style={{ fontSize: '14px', fontWeight: 600, color: 'var(--color-ink)' }}>Field Completeness</h3>
          </div>
          <div className="px-6 py-4 space-y-4">
            {Object.entries(completeness).map(([etype, data]) => (
              <div key={etype}>
                <div className="flex items-center justify-between mb-2">
                  <span style={{ fontSize: '12px', fontWeight: 500, color: 'var(--color-ink)', textTransform: 'capitalize' }}>
                    {etype.replace(/_/g, ' ')}
                  </span>
                  <span style={{ fontSize: '12px', color: 'var(--color-ink-4)' }}>
                    {(data.overall * 100).toFixed(0)}% ({data.total} records)
                  </span>
                </div>
                <div className="flex gap-1 flex-wrap">
                  {Object.entries(data.fields).map(([field, score]) => (
                    <div
                      key={field}
                      title={`${field}: ${(score * 100).toFixed(0)}%`}
                      className="rounded-md px-2 py-1"
                      style={{
                        fontSize: '10px',
                        background: score >= 0.7 ? 'var(--color-green-soft)' : score >= 0.4 ? 'var(--color-amber-soft)' : 'var(--color-red-soft)',
                        color: score >= 0.7 ? 'var(--color-green)' : score >= 0.4 ? 'var(--color-amber)' : 'var(--color-red)',
                      }}
                    >
                      {field.replace(/_/g, ' ')} {(score * 100).toFixed(0)}%
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Freshness per source */}
      {freshData && Object.keys(freshData).length > 0 && (
        <div
          className="rounded-2xl overflow-hidden"
          style={{ background: 'var(--color-surface)', border: '1px solid var(--color-line)' }}
        >
          <div className="px-6 py-4" style={{ borderBottom: '1px solid var(--color-line)' }}>
            <h3 style={{ fontSize: '14px', fontWeight: 600, color: 'var(--color-ink)' }}>Source Freshness</h3>
          </div>
          {Object.entries(freshData).map(([source, info]) => {
            const fresh = info.days_since != null
              ? info.days_since <= 7 ? { label: 'Fresh', color: 'var(--color-green)' }
                : info.days_since <= 30 ? { label: 'Recent', color: 'var(--color-amber)' }
                : { label: 'Stale', color: 'var(--color-red)' }
              : { label: 'Unknown', color: 'var(--color-ink-4)' };
            return (
              <div key={source} className="catalog-row">
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: '13px', fontWeight: 500, color: 'var(--color-ink)' }}>
                    {source.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
                  </div>
                  <div style={{ fontSize: '11px', color: 'var(--color-ink-4)' }}>
                    {info.entity_type} · {fmt(info.records)} records
                  </div>
                </div>
                <div className="flex items-center gap-1.5" style={{ fontSize: '12px', color: fresh.color }}>
                  <span className="h-1.5 w-1.5 rounded-full" style={{ background: fresh.color }} />
                  {fresh.label}
                </div>
                <div style={{ fontSize: '11px', color: 'var(--color-ink-4)', minWidth: '80px', textAlign: 'right' }}>
                  {info.days_since != null ? `${Math.round(info.days_since)}d ago` : '—'}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Datasets */}
      <div
        className="rounded-2xl overflow-hidden"
        style={{ background: 'var(--color-surface)', border: '1px solid var(--color-line)' }}
      >
        <div
          className="px-6 py-4"
          style={{ borderBottom: '1px solid var(--color-line)' }}
        >
          <h3 style={{ fontSize: '14px', fontWeight: 600, color: 'var(--color-ink)' }}>Datasets</h3>
        </div>
        {datasets.map(ds => {
          const fresh = freshness(ds.last_refreshed_at);
          return (
            <div
              key={ds.dataset_name}
              className="catalog-row"
              onClick={() => ds.entity_type && onBrowse(ds.entity_type)}
              style={{ cursor: ds.entity_type ? 'pointer' : 'default' }}
            >
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: '13px', fontWeight: 500, color: 'var(--color-ink)' }}>
                  {ds.dataset_name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
                </div>
              </div>
              <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--color-ink)', minWidth: '72px', textAlign: 'right' }}>
                {fmt(ds.row_count)}
              </div>
              {ds.quality_score_avg != null && (
                <div
                  className="badge"
                  style={{
                    background: ds.quality_score_avg >= 0.7 ? 'var(--color-green-soft)' : ds.quality_score_avg >= 0.4 ? 'var(--color-amber-soft)' : 'var(--color-red-soft)',
                    color: ds.quality_score_avg >= 0.7 ? 'var(--color-green)' : ds.quality_score_avg >= 0.4 ? 'var(--color-amber)' : 'var(--color-red)',
                    minWidth: '50px',
                    justifyContent: 'center',
                  }}
                >
                  {(ds.quality_score_avg * 100).toFixed(0)}%
                </div>
              )}
              <div
                className="flex items-center gap-1.5"
                style={{ minWidth: '80px', fontSize: '12px', color: fresh.color }}
              >
                <span className="h-1.5 w-1.5 rounded-full" style={{ background: fresh.color }} />
                {fresh.label}
              </div>
              <div style={{ fontSize: '11px', color: 'var(--color-ink-4)', minWidth: '100px', textAlign: 'right' }}>
                {shortDate(ds.last_refreshed_at)}
              </div>
              {ds.entity_type && <ChevronRight size={14} style={{ color: 'var(--color-ink-4)', flexShrink: 0 }} />}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ══ Browse ══ */
function BrowseTab({ browseType, onTypeChange, search, onSearch, data, loading, page, onPage, onOpen, onAskInChat }: {
  browseType: string;
  onTypeChange: (t: string) => void;
  search: string;
  onSearch: (s: string) => void;
  data: CatalogBrowseResponse | null;
  loading: boolean;
  page: number;
  onPage: (p: number) => void;
  onOpen: (type: string, id: string) => void;
  onAskInChat?: (q: string) => void;
}) {
  const [input, setInput] = useState(search);
  const totalPages = data ? Math.ceil(data.total / data.limit) : 0;

  return (
    <div className="space-y-5">
      {/* Controls */}
      <div className="flex flex-wrap items-end gap-4">
        <div>
          <div className="text-label mb-2">Entity Type</div>
          <div className="flex flex-wrap gap-1.5">
            {ENTITY_TYPES.map(opt => (
              <button
                key={opt.value}
                type="button"
                onClick={() => onTypeChange(opt.value)}
                className="btn btn-sm"
                style={{
                  borderRadius: '8px',
                  background: browseType === opt.value ? 'var(--color-ink)' : 'var(--color-surface-2)',
                  color: browseType === opt.value ? 'var(--color-surface)' : 'var(--color-ink-3)',
                  border: 'none',
                }}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>

        <div style={{ flex: 1, minWidth: '240px' }}>
          <div className="text-label mb-2">Search</div>
          <div className="flex gap-2">
            <div className="relative flex-1">
              <Search
                size={14}
                className="absolute"
                style={{ left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--color-ink-4)' }}
              />
              <input
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') { onSearch(input); onPage(0); } }}
                placeholder={`Search ${ENTITY_TYPES.find(o => o.value === browseType)?.label ?? ''}…`}
                className="input-base"
                style={{ paddingLeft: '36px' }}
              />
            </div>
            <button
              type="button"
              onClick={() => { onSearch(input); onPage(0); }}
              className="btn btn-secondary btn-sm"
              style={{ borderRadius: '10px', flexShrink: 0 }}
            >
              Search
            </button>
          </div>
        </div>
      </div>

      {/* Results */}
      <div
        className="rounded-2xl overflow-hidden"
        style={{ background: 'var(--color-surface)', border: '1px solid var(--color-line)' }}
      >
        {loading ? (
          <div className="py-12 text-center" style={{ color: 'var(--color-ink-4)', fontSize: '13px' }}>Loading…</div>
        ) : !data || data.results.length === 0 ? (
          <div className="py-12 text-center" style={{ color: 'var(--color-ink-4)', fontSize: '13px' }}>No entities found.</div>
        ) : (
          <>
            <div
              className="flex items-center justify-between px-6 py-3"
              style={{ borderBottom: '1px solid var(--color-line)' }}
            >
              <span style={{ fontSize: '12px', color: 'var(--color-ink-4)' }}>
                {fmt(data.total)} results
              </span>
              {totalPages > 1 && (
                <div className="flex items-center gap-1">
                  <button type="button" disabled={page === 0} onClick={() => onPage(page - 1)} className="btn-icon" style={{ width: '28px', height: '28px' }}>
                    <ChevronLeft size={13} />
                  </button>
                  <span style={{ fontSize: '11px', color: 'var(--color-ink-4)', padding: '0 8px' }}>
                    {page + 1} / {totalPages}
                  </span>
                  <button type="button" disabled={page + 1 >= totalPages} onClick={() => onPage(page + 1)} className="btn-icon" style={{ width: '28px', height: '28px' }}>
                    <ChevronRight size={13} />
                  </button>
                </div>
              )}
            </div>

            {data.results.map(entity => {
              const id = String(entity.id ?? entity.nct_id ?? entity._label ?? '');
              const label = String(entity._label ?? entity.generic_name ?? entity.name ?? entity.title ?? id);
              const status = String(entity.record_status ?? '');
              const q = entity.quality_score != null ? Number(entity.quality_score) : null;

              return (
                <div
                  key={id}
                  className="catalog-row group"
                  onClick={() => id && onOpen(browseType, id)}
                >
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div
                      className="truncate"
                      style={{ fontSize: '13px', fontWeight: 500, color: 'var(--color-ink)' }}
                    >
                      {label}
                    </div>
                    <div className="flex items-center gap-2 mt-0.5">
                      {status && (
                        <span
                          className="badge badge-neutral"
                          style={{ fontSize: '10px', textTransform: 'capitalize' }}
                        >
                          {status}
                        </span>
                      )}
                      {q != null && (
                        <span style={{ fontSize: '11px', color: 'var(--color-ink-4)' }}>
                          Quality {(q * 100).toFixed(0)}%
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                    {onAskInChat && (
                      <button
                        type="button"
                        onClick={e => { e.stopPropagation(); onAskInChat(`Tell me about ${label}`); }}
                        className="btn btn-xs"
                        style={{
                          background: 'var(--color-accent-soft)',
                          color: 'var(--color-accent)',
                          borderRadius: '6px',
                        }}
                      >
                        <MessageSquare size={10} />
                        Ask
                      </button>
                    )}
                    <ChevronRight size={13} style={{ color: 'var(--color-ink-4)' }} />
                  </div>
                </div>
              );
            })}
          </>
        )}
      </div>
    </div>
  );
}

/* ══ Changes ══ */
function ChangesTab({ changes }: { changes: ChangeLogEntry[] }) {
  return (
    <div
      className="rounded-2xl overflow-hidden"
      style={{ background: 'var(--color-surface)', border: '1px solid var(--color-line)' }}
    >
      {changes.length === 0 ? (
        <div className="py-12 text-center" style={{ color: 'var(--color-ink-4)', fontSize: '13px' }}>No changes recorded.</div>
      ) : (
        changes.map(ch => (
          <div key={ch.id} className="catalog-row">
            <div
              className="shrink-0 h-7 w-7 rounded-lg flex items-center justify-center"
              style={{
                background: ch.change_type === 'manual_edit' ? 'var(--color-accent-soft)'
                  : ch.change_type === 'created' ? 'var(--color-green-soft)'
                    : 'var(--color-surface-2)',
                color: ch.change_type === 'manual_edit' ? 'var(--color-accent)'
                  : ch.change_type === 'created' ? 'var(--color-green)'
                    : 'var(--color-ink-4)',
              }}
            >
              {ch.change_type === 'manual_edit' ? <Edit3 size={12} /> : <Clock size={12} />}
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div
                className="truncate"
                style={{ fontSize: '13px', fontWeight: 500, color: 'var(--color-ink)' }}
              >
                {ch.entity_id}
              </div>
              <div style={{ fontSize: '11px', color: 'var(--color-ink-4)' }}>
                {ch.entity_type} · {ch.change_type}
                {ch.changed_fields?.length ? ` · ${ch.changed_fields.join(', ')}` : ''}
              </div>
            </div>
            <div style={{ fontSize: '11px', color: 'var(--color-ink-4)', flexShrink: 0 }}>
              {shortDate(ch.changed_at)}
            </div>
          </div>
        ))
      )}
    </div>
  );
}

/* ══ Curation ══ */
function CurationTab({ items, onResolve }: {
  items: HITLItem[];
  onResolve: (id: string, action: string) => Promise<void>;
}) {
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [bulkLoading, setBulkLoading] = useState(false);

  // Sort: quality_failure first, then entity_resolution, then by priority desc
  const sorted = useMemo(() => {
    const typeOrder: Record<string, number> = { quality_failure: 0, entity_resolution: 1, duplicate_candidate: 2, enrichment_request: 3 };
    return [...items].sort((a, b) => {
      const ta = typeOrder[a.review_type] ?? 99;
      const tb = typeOrder[b.review_type] ?? 99;
      if (ta !== tb) return ta - tb;
      return b.priority - a.priority;
    });
  }, [items]);

  const toggleSelect = (id: string) => {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleAll = () => {
    if (selected.size === sorted.length) setSelected(new Set());
    else setSelected(new Set(sorted.map(i => i.id)));
  };

  const bulkResolve = async (action: string) => {
    if (selected.size === 0) return;
    setBulkLoading(true);
    try {
      await api.catalogBulkResolve([...selected], action);
      for (const id of selected) {
        await onResolve(id, action);
      }
      setSelected(new Set());
    } finally {
      setBulkLoading(false);
    }
  };

  // Stats
  const queueStats = useMemo(() => {
    const byType: Record<string, number> = {};
    for (const item of items) {
      byType[item.review_type] = (byType[item.review_type] || 0) + 1;
    }
    return byType;
  }, [items]);

  return (
    <div className="space-y-4">
      {/* Queue metrics */}
      <div className="flex flex-wrap gap-3">
        {Object.entries(queueStats).map(([type, count]) => (
          <div
            key={type}
            className="rounded-lg px-3 py-1.5"
            style={{ background: 'var(--color-surface)', border: '1px solid var(--color-line)', fontSize: '12px' }}
          >
            <span style={{ color: 'var(--color-ink-3)', textTransform: 'capitalize' }}>
              {type.replace(/_/g, ' ')}
            </span>
            <span style={{ color: 'var(--color-ink)', fontWeight: 600, marginLeft: '6px' }}>{count}</span>
          </div>
        ))}
      </div>

      {/* Bulk actions */}
      {sorted.length > 0 && (
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={toggleAll}
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
                className="btn btn-xs flex items-center gap-1"
                style={{ background: 'var(--color-green-soft)', color: 'var(--color-green)', borderRadius: '6px' }}
              >
                <CheckCircle size={11} />
                Approve All
              </button>
              <button
                type="button"
                onClick={() => void bulkResolve('rejected')}
                disabled={bulkLoading}
                className="btn btn-xs flex items-center gap-1"
                style={{ background: 'var(--color-red-soft)', color: 'var(--color-red)', borderRadius: '6px' }}
              >
                <XCircle size={11} />
                Reject All
              </button>
            </>
          )}
        </div>
      )}

      {sorted.length === 0 && (
        <div className="py-12 text-center" style={{ color: 'var(--color-ink-4)', fontSize: '13px' }}>
          No pending reviews.
        </div>
      )}
      {sorted.map(item => (
        <div
          key={item.id}
          className="rounded-2xl p-5"
          style={{
            background: selected.has(item.id) ? 'var(--color-accent-soft)' : 'var(--color-surface)',
            border: `1px solid ${selected.has(item.id) ? 'var(--color-accent)' : 'var(--color-line)'}`,
          }}
        >
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-start gap-3" style={{ flex: 1, minWidth: 0 }}>
              <input
                type="checkbox"
                checked={selected.has(item.id)}
                onChange={() => toggleSelect(item.id)}
                style={{ marginTop: '4px', accentColor: 'var(--color-accent)' }}
              />
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <span
                    className="badge badge-amber"
                    style={{ fontSize: '10px', textTransform: 'capitalize' }}
                  >
                    {item.review_type.replace(/_/g, ' ')}
                  </span>
                  <span style={{ fontSize: '11px', color: 'var(--color-ink-4)' }}>
                    {item.entity_type}
                  </span>
                </div>
                <p style={{ fontSize: '13px', color: 'var(--color-ink-2)', lineHeight: 1.5 }}>
                  {String(item.payload?.description ?? item.payload?.raw_value ?? item.entity_id)}
                </p>
                <div style={{ fontSize: '11px', color: 'var(--color-ink-4)', marginTop: '6px' }}>
                  Priority {item.priority} · {shortDate(item.created_at)}
                </div>
              </div>
            </div>
            <div className="flex flex-col gap-1.5 shrink-0">
              <button
                type="button"
                onClick={() => void onResolve(item.id, 'approved')}
                className="btn btn-xs flex items-center gap-1"
                style={{ background: 'var(--color-green-soft)', color: 'var(--color-green)', borderRadius: '8px' }}
              >
                <CheckCircle size={11} />
                Approve
              </button>
              <button
                type="button"
                onClick={() => void onResolve(item.id, 'rejected')}
                className="btn btn-xs flex items-center gap-1"
                style={{ background: 'var(--color-red-soft)', color: 'var(--color-red)', borderRadius: '8px' }}
              >
                <XCircle size={11} />
                Reject
              </button>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

/* ══ Entity Detail ══ */
const SKIP = new Set(['_label', 'content_hash', 'molecule_embedding', 'strategy_embedding', 'protocol_embedding', 'abstract_embedding', 'scope_note_embedding', 'label_embedding', 'full_text_embedding']);

function EntityDetailDrawer({ detail, editing, onEditField, onSave, onAskInChat }: {
  detail: CatalogEntityDetail;
  editing: Record<string, string>;
  onEditField: (f: string, v: string) => void;
  onSave: () => Promise<void>;
  onAskInChat?: (q: string) => void;
}) {
  const entity = detail.entity;
  const editable = new Set(detail.editable_fields);
  const hasEdits = Object.keys(editing).length > 0;
  const [saving, setSaving] = useState(false);

  const save = async () => {
    setSaving(true);
    try { await onSave(); } finally { setSaving(false); }
  };

  return (
    <div className="space-y-6">
      {/* Properties */}
      <section>
        <div className="text-label mb-4">Properties</div>
        <div className="space-y-1">
          {Object.entries(entity)
            .filter(([k]) => !SKIP.has(k))
            .map(([key, val]) => {
              const isEditing = key in editing;
              const display = Array.isArray(val) ? val.join(', ') : String(val ?? '—');
              return (
                <div
                  key={key}
                  className="flex items-start gap-3 rounded-xl px-3 py-2.5"
                  style={{ background: isEditing ? 'var(--color-accent-soft)' : 'transparent' }}
                >
                  <span
                    className="shrink-0 pt-0.5"
                    style={{ fontSize: '12px', color: 'var(--color-ink-4)', width: '140px', textTransform: 'capitalize' }}
                  >
                    {key.replace(/_/g, ' ')}
                  </span>
                  {isEditing ? (
                    <input
                      value={editing[key]}
                      onChange={e => onEditField(key, e.target.value)}
                      className="input-base flex-1"
                      style={{ padding: '4px 8px', fontSize: '12px', borderRadius: '6px' }}
                      autoFocus
                    />
                  ) : (
                    <span
                      style={{ fontSize: '12px', color: 'var(--color-ink-2)', flex: 1, wordBreak: 'break-word' }}
                    >
                      {display}
                    </span>
                  )}
                  {editable.has(key) && !isEditing && (
                    <button
                      type="button"
                      onClick={() => onEditField(key, String(val ?? ''))}
                      className="shrink-0 opacity-0 hover:opacity-100 transition-opacity"
                      style={{ color: 'var(--color-ink-4)', background: 'none', border: 'none', cursor: 'pointer', padding: '2px' }}
                    >
                      <Edit3 size={11} />
                    </button>
                  )}
                </div>
              );
            })}
        </div>
        {hasEdits && (
          <div className="flex items-center gap-2 mt-4 pt-4" style={{ borderTop: '1px solid var(--color-line)' }}>
            <button
              type="button"
              onClick={() => void save()}
              disabled={saving}
              className="btn btn-accent btn-sm"
            >
              {saving ? 'Saving…' : 'Save Changes'}
            </button>
          </div>
        )}
      </section>

      {/* Quality */}
      {detail.quality_results.length > 0 && (
        <section>
          <div className="text-label mb-3">Quality Checks</div>
          <div className="space-y-1">
            {detail.quality_results.map((qr, i) => (
              <div key={i} className="flex items-center gap-2 py-1.5" style={{ fontSize: '12px' }}>
                {qr.passed
                  ? <CheckCircle size={13} style={{ color: 'var(--color-green)', flexShrink: 0 }} />
                  : <X size={13} style={{ color: 'var(--color-red)', flexShrink: 0 }} />
                }
                <span style={{ flex: 1, color: 'var(--color-ink-2)' }}>{qr.rule_name}</span>
                <span
                  className="badge badge-neutral"
                  style={{ fontSize: '10px', textTransform: 'capitalize' }}
                >
                  {qr.severity}
                </span>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Related entities */}
      {detail.links.length > 0 && (
        <section>
          <div className="text-label mb-3">Related Entities ({detail.links.length})</div>
          <div className="space-y-1">
            {detail.links.slice(0, 20).map((link: EntityLink, i: number) => {
              const isSrc = link.source_entity_id === String(entity.id ?? '');
              const relatedId = isSrc ? link.target_entity_id : link.source_entity_id;
              const relatedType = isSrc ? link.target_entity_type : link.source_entity_type;
              return (
                <div key={i} className="flex items-center gap-2 py-1.5" style={{ fontSize: '12px' }}>
                  <span
                    className="badge badge-neutral"
                    style={{ fontSize: '9px', textTransform: 'uppercase', minWidth: '60px', justifyContent: 'center' }}
                  >
                    {link.link_type}
                  </span>
                  <span style={{ color: 'var(--color-ink-2)', flex: 1 }}>
                    {relatedType}: {relatedId.slice(0, 12)}...
                  </span>
                  <span style={{ color: 'var(--color-ink-4)' }}>
                    {(link.confidence * 100).toFixed(0)}%
                  </span>
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* Data provenance */}
      {(entity.source_api || entity.retrieved_at) && (
        <section>
          <div className="text-label mb-3">Data Provenance</div>
          <div className="space-y-1" style={{ fontSize: '12px' }}>
            {entity.source_api && (
              <div className="flex gap-2">
                <span style={{ color: 'var(--color-ink-4)', width: '80px' }}>Source</span>
                <span style={{ color: 'var(--color-ink-2)' }}>{String(entity.source_api)}</span>
              </div>
            )}
            {entity.retrieved_at && (
              <div className="flex gap-2">
                <span style={{ color: 'var(--color-ink-4)', width: '80px' }}>Retrieved</span>
                <span style={{ color: 'var(--color-ink-2)' }}>{shortDate(String(entity.retrieved_at))}</span>
              </div>
            )}
            {entity.content_hash && (
              <div className="flex gap-2">
                <span style={{ color: 'var(--color-ink-4)', width: '80px' }}>Hash</span>
                <span style={{ color: 'var(--color-ink-4)', fontFamily: 'monospace', fontSize: '10px' }}>
                  {String(entity.content_hash).slice(0, 16)}...
                </span>
              </div>
            )}
          </div>
        </section>
      )}

      {/* Change history */}
      {detail.change_log.length > 0 && (
        <section>
          <div className="text-label mb-3">Change History</div>
          <div className="space-y-2">
            {detail.change_log.slice(0, 10).map((ch, i) => (
              <div key={i} className="flex items-start gap-2" style={{ fontSize: '11px' }}>
                <div
                  className="shrink-0 h-2 w-2 rounded-full mt-1.5"
                  style={{ background: ch.change_type === 'manual_edit' ? 'var(--color-accent)' : 'var(--color-ink-4)' }}
                />
                <div>
                  <span style={{ color: 'var(--color-ink-2)' }}>{ch.change_type}</span>
                  {ch.changed_fields?.length > 0 && (
                    <span style={{ color: 'var(--color-ink-4)' }}> · {ch.changed_fields.join(', ')}</span>
                  )}
                  <div style={{ color: 'var(--color-ink-4)' }}>{shortDate(ch.changed_at)}</div>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Actions */}
      <div className="flex flex-wrap gap-2" style={{ paddingTop: '16px', borderTop: '1px solid var(--color-line)' }}>
        {onAskInChat && (
          <button
            type="button"
            onClick={() => {
              const label = String(entity._label ?? entity.generic_name ?? entity.name ?? '');
              onAskInChat(`Tell me about ${label}`);
            }}
            className="btn btn-secondary btn-sm flex items-center gap-2"
          >
            <MessageSquare size={13} />
            Explore in Chat
          </button>
        )}
        <button
          type="button"
          onClick={() => {
            const etype = detail.entity_type;
            const eid = String(entity.id ?? '');
            api.catalogRunEnrichment(etype, 1).catch(() => {});
          }}
          className="btn btn-secondary btn-sm flex items-center gap-2"
        >
          <RefreshCw size={13} />
          Request AI Enrichment
        </button>
      </div>
    </div>
  );
}
