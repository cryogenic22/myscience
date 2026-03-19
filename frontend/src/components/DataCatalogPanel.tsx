import { useCallback, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import {
  AlertTriangle,
  BookOpen,
  Check,
  ChevronLeft,
  ChevronRight,
  Clock,
  Database,
  Dna,
  Edit3,
  ExternalLink,
  FileText,
  Link2,
  MessageSquare,
  Plus,
  RefreshCw,
  Search,
  Server,
  Shield,
  Tag,
  Target,
  X,
} from 'lucide-react';
import {
  api,
  type CatalogBrowseResponse,
  type CatalogDataset,
  type CatalogEntity,
  type CatalogEntityDetail,
  type CatalogStats,
  type ChangeLogEntry,
  type HITLItem,
  type HealthData,
} from '../api';
import { Drawer } from './ui/Drawer';

interface Props {
  onAskInChat?: (question: string) => void;
}

type CatalogTab = 'overview' | 'browse' | 'changes' | 'quality' | 'curation';

const ENTITY_TYPE_OPTIONS = [
  { value: 'drug', label: 'Drugs', icon: '💊' },
  { value: 'company', label: 'Companies', icon: '🏢' },
  { value: 'trial', label: 'Clinical Trials', icon: '🔬' },
  { value: 'therapeutic_area', label: 'Therapeutic Areas', icon: '🎯' },
  { value: 'mechanism', label: 'Mechanisms', icon: '🧬' },
  { value: 'article', label: 'PubMed Articles', icon: '📄' },
];

const TABLE_LABELS: Record<string, string> = {
  drugs: 'Drugs',
  clinical_trials: 'Clinical Trials',
  pubmed_articles: 'PubMed Articles',
  companies: 'Companies',
  market_events: 'Market Events',
  entity_links: 'Entity Links',
  mechanisms_of_action: 'Mechanisms',
  therapeutic_areas: 'Therapeutic Areas',
  patents: 'Patents',
};

const SOURCE_LABELS: Record<string, string> = {
  clinical_trials_gov: 'ClinicalTrials.gov',
  pubmed: 'PubMed',
  fda_orange_book: 'FDA Orange Book',
  dailymed: 'DailyMed',
  open_targets: 'Open Targets',
  chembl: 'ChEMBL',
  rxnorm: 'RxNorm',
  mesh: 'MeSH',
};

function freshnessDot(lastRetrieved: string | null | undefined): { color: string; label: string } {
  if (!lastRetrieved) return { color: 'bg-slate-300', label: 'Unknown' };
  const days = Math.floor((Date.now() - new Date(lastRetrieved).getTime()) / 86_400_000);
  if (days <= 7) return { color: 'bg-emerald-500', label: 'Fresh' };
  if (days <= 30) return { color: 'bg-amber-400', label: 'Recent' };
  return { color: 'bg-red-400', label: 'Stale' };
}

function fmt(value: number): string {
  return new Intl.NumberFormat().format(value);
}

function formatDateTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, { month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function formatDateShort(value: string | null | undefined): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

const STATUS_COLORS: Record<string, string> = {
  active: 'bg-emerald-100 text-emerald-700',
  stale: 'bg-amber-100 text-amber-700',
  withdrawn: 'bg-red-100 text-red-700',
  superseded: 'bg-slate-100 text-slate-600',
  pending: 'bg-amber-100 text-amber-700',
  approved: 'bg-emerald-100 text-emerald-700',
  rejected: 'bg-red-100 text-red-700',
  deferred: 'bg-slate-100 text-slate-600',
};

export default function DataCatalogPanel({ onAskInChat }: Props) {
  const [tab, setTab] = useState<CatalogTab>('overview');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [health, setHealth] = useState<HealthData | null>(null);
  const [stats, setStats] = useState<CatalogStats | null>(null);
  const [datasets, setDatasets] = useState<CatalogDataset[]>([]);
  const [refreshing, setRefreshing] = useState(false);

  // Browse state
  const [browseType, setBrowseType] = useState('drug');
  const [browseSearch, setBrowseSearch] = useState('');
  const [browseData, setBrowseData] = useState<CatalogBrowseResponse | null>(null);
  const [browseLoading, setBrowseLoading] = useState(false);
  const [browsePage, setBrowsePage] = useState(0);
  const [selectedEntity, setSelectedEntity] = useState<{ type: string; id: string } | null>(null);
  const [entityDetail, setEntityDetail] = useState<CatalogEntityDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // Changes state
  const [changes, setChanges] = useState<ChangeLogEntry[]>([]);
  const [changesTotal, setChangesTotal] = useState(0);
  const [changesLoading, setChangesLoading] = useState(false);

  // HITL / Curation state
  const [hitlItems, setHitlItems] = useState<HITLItem[]>([]);
  const [hitlTotal, setHitlTotal] = useState(0);
  const [hitlLoading, setHitlLoading] = useState(false);
  const [enrichScope, setEnrichScope] = useState('');
  const [enrichDesc, setEnrichDesc] = useState('');
  const [enrichType, setEnrichType] = useState('therapeutic_area');
  const [enrichSubmitting, setEnrichSubmitting] = useState(false);
  const [enrichMessage, setEnrichMessage] = useState<string | null>(null);

  // Edit state
  const [editing, setEditing] = useState<Record<string, string>>({});
  const [editSaving, setEditSaving] = useState(false);

  // Drawer
  const [drawerOpen, setDrawerOpen] = useState(false);

  // ── Data loading ──

  const loadOverview = useCallback(async (initial = false) => {
    if (initial) setLoading(true);
    else setRefreshing(true);
    setError(null);
    try {
      const [healthRes, statsRes, datasetsRes] = await Promise.all([
        api.health(),
        api.catalogStats().catch(() => null),
        api.catalogDatasets().catch(() => ({ datasets: [], count: 0 })),
      ]);
      setHealth(healthRes);
      setStats(statsRes);
      setDatasets(datasetsRes.datasets);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load catalog');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void loadOverview(true);
  }, [loadOverview]);

  const loadBrowse = useCallback(async () => {
    setBrowseLoading(true);
    try {
      const res = await api.catalogBrowse(browseType, {
        search: browseSearch || undefined,
        limit: 30,
        offset: browsePage * 30,
      });
      setBrowseData(res);
    } catch {
      setBrowseData(null);
    } finally {
      setBrowseLoading(false);
    }
  }, [browseType, browseSearch, browsePage]);

  useEffect(() => {
    if (tab === 'browse') void loadBrowse();
  }, [tab, loadBrowse]);

  const loadEntityDetail = useCallback(async (type: string, id: string) => {
    setDetailLoading(true);
    setEntityDetail(null);
    try {
      const detail = await api.catalogEntityDetail(type, id);
      setEntityDetail(detail);
    } catch {
      setEntityDetail(null);
    } finally {
      setDetailLoading(false);
    }
  }, []);

  const openEntity = useCallback((type: string, id: string) => {
    setSelectedEntity({ type, id });
    setDrawerOpen(true);
    setEditing({});
    void loadEntityDetail(type, id);
  }, [loadEntityDetail]);

  const loadChanges = useCallback(async () => {
    setChangesLoading(true);
    try {
      const res = await api.catalogChanges({ limit: 50 });
      setChanges(res.changes);
      setChangesTotal(res.total);
    } catch {
      setChanges([]);
    } finally {
      setChangesLoading(false);
    }
  }, []);

  useEffect(() => {
    if (tab === 'changes') void loadChanges();
  }, [tab, loadChanges]);

  const loadHITL = useCallback(async () => {
    setHitlLoading(true);
    try {
      const res = await api.catalogHITL({ status_filter: 'pending', limit: 50 });
      setHitlItems(res.items);
      setHitlTotal(res.total);
    } catch {
      setHitlItems([]);
    } finally {
      setHitlLoading(false);
    }
  }, []);

  useEffect(() => {
    if (tab === 'curation') void loadHITL();
  }, [tab, loadHITL]);

  // ── Actions ──

  const handleRefreshViews = async () => {
    setRefreshing(true);
    try {
      await api.catalogRefreshViews();
      await loadOverview(false);
    } finally {
      setRefreshing(false);
    }
  };

  const handleSaveEdit = async () => {
    if (!selectedEntity || !entityDetail || Object.keys(editing).length === 0) return;
    setEditSaving(true);
    try {
      await api.catalogUpdateEntity(selectedEntity.type, selectedEntity.id, editing, 'Manual edit from catalog');
      setEditing({});
      void loadEntityDetail(selectedEntity.type, selectedEntity.id);
    } finally {
      setEditSaving(false);
    }
  };

  const handleEnrich = async () => {
    if (!enrichScope.trim()) return;
    setEnrichSubmitting(true);
    setEnrichMessage(null);
    try {
      const res = await api.catalogEnrich(enrichType, enrichScope, enrichDesc);
      setEnrichMessage(res.message);
      setEnrichScope('');
      setEnrichDesc('');
      void loadHITL();
    } catch (err) {
      setEnrichMessage(err instanceof Error ? err.message : 'Failed to submit request');
    } finally {
      setEnrichSubmitting(false);
    }
  };

  const handleResolveHITL = async (id: string, action: string) => {
    try {
      await api.catalogResolveHITL(id, action, '');
      void loadHITL();
    } catch { /* ignore */ }
  };

  // ── Computed ──

  const sourceRows = useMemo(
    () => [...(health?.source_coverage ?? [])].sort((a, b) => Number(b.records) - Number(a.records)),
    [health?.source_coverage],
  );

  const statusLabel = health?.status ?? 'unknown';

  const TABS: Array<{ key: CatalogTab; label: string; icon: ReactNode }> = [
    { key: 'overview', label: 'Overview', icon: <Database size={13} /> },
    { key: 'browse', label: 'Browse Entities', icon: <Search size={13} /> },
    { key: 'changes', label: 'Audit Trail', icon: <Clock size={13} /> },
    { key: 'quality', label: 'Quality', icon: <Shield size={13} /> },
    { key: 'curation', label: 'Curation', icon: <Plus size={13} /> },
  ];

  return (
    <main className="workspace-canvas flex-1 overflow-y-auto px-6 py-6 sm:px-8">
      <div className="workspace-shell space-y-4">
        {/* Header */}
        <section className="surface-panel rounded-xl px-5 py-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold tracking-tight text-slate-900">Data Catalog</h2>
              <p className="mt-0.5 text-[12px] text-slate-500">
                Browse, search, inspect metadata, and curate the knowledge base.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <span className={`inline-flex items-center gap-1.5 text-[11px] ${statusLabel === 'ok' ? 'text-emerald-600' : 'text-amber-600'}`}>
                <Server size={10} />
                <span className="font-medium capitalize">{statusLabel}</span>
              </span>
              <button
                type="button"
                onClick={() => void handleRefreshViews()}
                className="btn-secondary inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium"
                disabled={refreshing}
              >
                <RefreshCw size={11} className={refreshing ? 'animate-spin' : ''} />
                Refresh
              </button>
            </div>
          </div>

          {/* Tab bar */}
          <div className="mt-3 flex gap-1 border-t border-slate-100 pt-3">
            {TABS.map((t) => (
              <button
                key={t.key}
                type="button"
                onClick={() => setTab(t.key)}
                className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-all ${
                  tab === t.key
                    ? 'bg-brand text-white shadow-sm'
                    : 'text-slate-500 hover:bg-slate-100 hover:text-slate-800'
                }`}
              >
                {t.icon}
                {t.label}
              </button>
            ))}
          </div>
        </section>

        {loading ? (
          <section className="surface-panel rounded-xl px-6 py-8 text-sm text-slate-500">
            Loading catalog...
          </section>
        ) : error ? (
          <section className="surface-panel rounded-xl bg-rose-50 px-6 py-4 text-sm text-rose-700">
            {error}
          </section>
        ) : (
          <>
            {tab === 'overview' && (
              <OverviewTab
                health={health}
                stats={stats}
                datasets={datasets}
                sourceRows={sourceRows}
                onBrowse={(type) => { setBrowseType(type); setTab('browse'); }}
                onAskInChat={onAskInChat}
              />
            )}
            {tab === 'browse' && (
              <BrowseTab
                browseType={browseType}
                onTypeChange={(t) => { setBrowseType(t); setBrowsePage(0); }}
                search={browseSearch}
                onSearchChange={setBrowseSearch}
                data={browseData}
                loading={browseLoading}
                page={browsePage}
                onPageChange={setBrowsePage}
                onOpenEntity={openEntity}
                onAskInChat={onAskInChat}
              />
            )}
            {tab === 'changes' && (
              <ChangesTab changes={changes} total={changesTotal} loading={changesLoading} />
            )}
            {tab === 'quality' && (
              <QualityTab stats={stats} datasets={datasets} onOpenEntity={openEntity} />
            )}
            {tab === 'curation' && (
              <CurationTab
                hitlItems={hitlItems}
                hitlTotal={hitlTotal}
                hitlLoading={hitlLoading}
                enrichType={enrichType}
                enrichScope={enrichScope}
                enrichDesc={enrichDesc}
                enrichSubmitting={enrichSubmitting}
                enrichMessage={enrichMessage}
                onEnrichTypeChange={setEnrichType}
                onEnrichScopeChange={setEnrichScope}
                onEnrichDescChange={setEnrichDesc}
                onEnrich={handleEnrich}
                onResolve={handleResolveHITL}
              />
            )}
          </>
        )}

        {/* Entity Detail Drawer */}
        <Drawer
          isOpen={drawerOpen}
          onClose={() => { setDrawerOpen(false); setSelectedEntity(null); }}
          title={entityDetail?.entity?._label as string ?? entityDetail?.entity?.generic_name as string ?? entityDetail?.entity?.name as string ?? 'Entity Detail'}
          subtitle={selectedEntity ? `${selectedEntity.type} / ${selectedEntity.id}` : undefined}
          width="clamp(400px, 50vw, 720px)"
        >
          {detailLoading ? (
            <div className="text-sm text-slate-500 py-4">Loading detail...</div>
          ) : entityDetail ? (
            <EntityDetailContent
              detail={entityDetail}
              editing={editing}
              editSaving={editSaving}
              onEditField={(field, value) => setEditing((prev) => ({ ...prev, [field]: value }))}
              onSave={handleSaveEdit}
              onCancelEdit={() => setEditing({})}
              onAskInChat={onAskInChat}
            />
          ) : (
            <div className="text-sm text-slate-500 py-4">Entity not found.</div>
          )}
        </Drawer>
      </div>
    </main>
  );
}


// ═══════════════════════════════════════════
//  Overview Tab
// ═══════════════════════════════════════════

function OverviewTab({
  health, stats, datasets, sourceRows, onBrowse, onAskInChat,
}: {
  health: HealthData | null;
  stats: CatalogStats | null;
  datasets: CatalogDataset[];
  sourceRows: HealthData['source_coverage'] extends (infer T)[] ? T[] : never[];
  onBrowse: (type: string) => void;
  onAskInChat?: (question: string) => void;
}) {
  return (
    <>
      {/* Stat cards */}
      <section className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <StatCard icon={<Database size={14} />} label="Total Records" value={fmt(health?.total_records ?? 0)} />
        <StatCard icon={<BookOpen size={14} />} label="Sources" value={fmt(sourceRows.length)} />
        <StatCard icon={<Target size={14} />} label="Quality Avg" value={stats?.quality?.avg_score != null ? `${(Number(stats.quality.avg_score) * 100).toFixed(0)}%` : '—'} />
        <StatCard icon={<AlertTriangle size={14} />} label="Quality Issues" value={fmt(stats?.quality?.failures ?? 0)} />
        <StatCard icon={<Shield size={14} />} label="Pending Reviews" value={fmt(stats?.hitl?.pending ?? 0)} />
        <StatCard icon={<Clock size={14} />} label="Recent Changes" value={fmt(stats?.changes?.recent_changes ?? 0)} />
      </section>

      {/* Datasets table */}
      <section className="surface-panel rounded-xl px-5 py-4">
        <h3 className="text-[13px] font-semibold text-slate-900">Datasets</h3>
        <p className="mt-0.5 text-[11px] text-slate-400">Click any dataset to browse its entities.</p>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-[12px]">
            <thead>
              <tr className="border-b border-slate-100 text-left text-[10px] font-medium uppercase tracking-wider text-slate-400">
                <th className="pb-2 pr-4">Dataset</th>
                <th className="pb-2 pr-4">Records</th>
                <th className="pb-2 pr-4">Quality</th>
                <th className="pb-2 pr-4">Freshness</th>
                <th className="pb-2 pr-4">Last Updated</th>
                <th className="pb-2" />
              </tr>
            </thead>
            <tbody>
              {datasets.map((ds) => {
                const freshness = freshnessDot(ds.last_refreshed_at);
                const label = TABLE_LABELS[ds.dataset_name] ?? ds.dataset_name.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
                return (
                  <tr
                    key={ds.dataset_name}
                    className="border-b border-slate-50 hover:bg-slate-50/60 cursor-pointer transition-colors"
                    onClick={() => ds.entity_type && onBrowse(ds.entity_type)}
                  >
                    <td className="py-2.5 pr-4">
                      <div className="font-medium text-slate-800">{label}</div>
                      {ds.description && <div className="text-[10px] text-slate-400 mt-0.5">{ds.description}</div>}
                    </td>
                    <td className="py-2.5 pr-4 font-semibold tabular-nums text-slate-900">{fmt(ds.row_count)}</td>
                    <td className="py-2.5 pr-4">
                      {ds.quality_score_avg != null ? (
                        <span className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-medium ${
                          ds.quality_score_avg >= 0.7 ? 'bg-emerald-100 text-emerald-700' :
                          ds.quality_score_avg >= 0.4 ? 'bg-amber-100 text-amber-700' :
                          'bg-red-100 text-red-700'
                        }`}>
                          {(ds.quality_score_avg * 100).toFixed(0)}%
                        </span>
                      ) : <span className="text-slate-300">—</span>}
                    </td>
                    <td className="py-2.5 pr-4">
                      <span className="inline-flex items-center gap-1.5">
                        <span className={`h-2 w-2 rounded-full ${freshness.color}`} />
                        <span className="text-slate-600">{freshness.label}</span>
                      </span>
                    </td>
                    <td className="py-2.5 pr-4 text-slate-500">{formatDateShort(ds.last_refreshed_at)}</td>
                    <td className="py-2.5">
                      {ds.entity_type && (
                        <ChevronRight size={14} className="text-slate-300" />
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      {/* Sources */}
      <section className="surface-panel rounded-xl px-5 py-4">
        <h3 className="text-[13px] font-semibold text-slate-900">Data Sources & Freshness</h3>
        <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {sourceRows.map((row: Record<string, unknown>) => {
            const freshness = freshnessDot(row.last_retrieved as string);
            const humanName = SOURCE_LABELS[row.source as string] || String(row.source);
            return (
              <div key={String(row.source)} className="rounded-lg bg-white/90 px-3 py-2.5 shadow-sm">
                <div className="flex items-center justify-between text-[12px]">
                  <div className="flex items-center gap-2">
                    <span className={`h-2 w-2 shrink-0 rounded-full ${freshness.color}`} />
                    <span className="font-medium text-slate-800">{humanName}</span>
                  </div>
                  <span className="font-semibold tabular-nums text-slate-900">{fmt(Number(row.records))}</span>
                </div>
                <div className="mt-1 text-[10px] text-slate-400">
                  {freshness.label} — {row.last_retrieved ? formatDateTime(String(row.last_retrieved)) : 'unknown'}
                </div>
              </div>
            );
          })}
        </div>
      </section>
    </>
  );
}


// ═══════════════════════════════════════════
//  Browse Tab
// ═══════════════════════════════════════════

function BrowseTab({
  browseType, onTypeChange, search, onSearchChange, data, loading, page, onPageChange, onOpenEntity, onAskInChat,
}: {
  browseType: string;
  onTypeChange: (t: string) => void;
  search: string;
  onSearchChange: (s: string) => void;
  data: CatalogBrowseResponse | null;
  loading: boolean;
  page: number;
  onPageChange: (p: number) => void;
  onOpenEntity: (type: string, id: string) => void;
  onAskInChat?: (q: string) => void;
}) {
  const [searchInput, setSearchInput] = useState(search);

  const handleSearch = () => {
    onSearchChange(searchInput);
    onPageChange(0);
  };

  const totalPages = data ? Math.ceil(data.total / data.limit) : 0;

  return (
    <>
      {/* Controls */}
      <section className="surface-panel rounded-xl px-5 py-4">
        <div className="flex flex-wrap items-end gap-3">
          {/* Type selector */}
          <div>
            <label className="text-[10px] font-medium uppercase tracking-wider text-slate-400">Entity Type</label>
            <div className="mt-1 flex gap-1">
              {ENTITY_TYPE_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => onTypeChange(opt.value)}
                  className={`rounded-lg px-2.5 py-1.5 text-xs font-medium transition-all ${
                    browseType === opt.value
                      ? 'bg-brand text-white shadow-sm'
                      : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                  }`}
                >
                  <span className="mr-1">{opt.icon}</span>
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          {/* Search */}
          <div className="flex-1 min-w-[200px]">
            <label className="text-[10px] font-medium uppercase tracking-wider text-slate-400">Search</label>
            <div className="mt-1 flex gap-1.5">
              <input
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                placeholder={`Search ${ENTITY_TYPE_OPTIONS.find((o) => o.value === browseType)?.label ?? ''}...`}
                className="input-surface h-8 flex-1 rounded-lg px-3 text-xs text-slate-900 placeholder:text-slate-400 outline-none focus:ring-2 focus:ring-brand/15"
              />
              <button
                type="button"
                onClick={handleSearch}
                className="btn-secondary inline-flex h-8 items-center gap-1 rounded-lg px-3 text-xs font-medium"
              >
                <Search size={12} />
                Search
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* Results */}
      <section className="surface-panel rounded-xl px-5 py-4">
        {loading ? (
          <div className="py-6 text-center text-sm text-slate-500">Loading...</div>
        ) : !data || data.results.length === 0 ? (
          <div className="py-6 text-center text-sm text-slate-400">No entities found.</div>
        ) : (
          <>
            <div className="flex items-center justify-between mb-3">
              <span className="text-[11px] text-slate-500">
                Showing {data.offset + 1}–{Math.min(data.offset + data.limit, data.total)} of {fmt(data.total)}
              </span>
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  disabled={page === 0}
                  onClick={() => onPageChange(page - 1)}
                  className="rounded p-1 text-slate-400 hover:bg-slate-100 disabled:opacity-30"
                >
                  <ChevronLeft size={14} />
                </button>
                <span className="text-[11px] text-slate-500 px-1">
                  Page {page + 1} of {totalPages}
                </span>
                <button
                  type="button"
                  disabled={page + 1 >= totalPages}
                  onClick={() => onPageChange(page + 1)}
                  className="rounded p-1 text-slate-400 hover:bg-slate-100 disabled:opacity-30"
                >
                  <ChevronRight size={14} />
                </button>
              </div>
            </div>

            <div className="space-y-1">
              {data.results.map((entity) => {
                const id = String(entity[data.editable_fields.length > 0 ? 'id' : 'nct_id'] ?? entity.id ?? entity.nct_id ?? entity._label);
                const label = String(entity._label ?? entity.generic_name ?? entity.name ?? entity.title ?? entity.nct_id ?? id);
                const status = String(entity.record_status ?? '');
                const quality = entity.quality_score != null ? Number(entity.quality_score) : null;

                return (
                  <div
                    key={id}
                    className="group flex items-center gap-3 rounded-lg bg-white/90 px-3 py-2.5 shadow-sm hover:bg-slate-50 cursor-pointer transition-colors"
                    onClick={() => openEntityFromRow(browseType, entity, onOpenEntity)}
                  >
                    <div className="min-w-0 flex-1">
                      <div className="font-medium text-slate-800 text-[12px] truncate">{label}</div>
                      <div className="flex items-center gap-2 mt-0.5 text-[10px] text-slate-400">
                        {status && (
                          <span className={`rounded px-1.5 py-0.5 font-medium ${STATUS_COLORS[status] ?? 'bg-slate-100 text-slate-500'}`}>
                            {status}
                          </span>
                        )}
                        {quality != null && (
                          <span>Quality: {(quality * 100).toFixed(0)}%</span>
                        )}
                        {entity.source_api && <span>Source: {SOURCE_LABELS[String(entity.source_api)] ?? String(entity.source_api)}</span>}
                      </div>
                    </div>
                    <div className="flex items-center gap-1.5 shrink-0">
                      {onAskInChat && (
                        <button
                          type="button"
                          onClick={(e) => { e.stopPropagation(); onAskInChat(`Tell me about ${label}`); }}
                          className="opacity-0 group-hover:opacity-100 transition-opacity rounded-md bg-brand/10 px-2 py-1 text-[10px] font-medium text-brand-dark hover:bg-brand/20"
                        >
                          <MessageSquare size={10} className="inline mr-1" />
                          Ask
                        </button>
                      )}
                      <ChevronRight size={14} className="text-slate-300" />
                    </div>
                  </div>
                );
              })}
            </div>
          </>
        )}
      </section>
    </>
  );
}

function openEntityFromRow(entityType: string, entity: CatalogEntity, onOpen: (type: string, id: string) => void) {
  const id = String(entity.id ?? entity.nct_id ?? entity._label ?? '');
  if (id) onOpen(entityType, id);
}


// ═══════════════════════════════════════════
//  Entity Detail (Drawer content)
// ═══════════════════════════════════════════

function EntityDetailContent({
  detail, editing, editSaving, onEditField, onSave, onCancelEdit, onAskInChat,
}: {
  detail: CatalogEntityDetail;
  editing: Record<string, string>;
  editSaving: boolean;
  onEditField: (field: string, value: string) => void;
  onSave: () => void;
  onCancelEdit: () => void;
  onAskInChat?: (q: string) => void;
}) {
  const entity = detail.entity;
  const editable = new Set(detail.editable_fields);
  const hasEdits = Object.keys(editing).length > 0;

  // Separate fields into key info and metadata
  const SKIP_FIELDS = new Set(['_label', 'content_hash', 'molecule_embedding', 'strategy_embedding', 'protocol_embedding', 'abstract_embedding', 'scope_note_embedding', 'label_embedding', 'full_text_embedding']);

  return (
    <div className="space-y-5">
      {/* Properties */}
      <div>
        <h4 className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 mb-2">Properties</h4>
        <div className="space-y-1">
          {Object.entries(entity).filter(([k]) => !SKIP_FIELDS.has(k)).map(([key, value]) => {
            const isEditable = editable.has(key);
            const isEditing = key in editing;
            const displayVal = Array.isArray(value) ? value.join(', ') : String(value ?? '—');

            return (
              <div key={key} className="flex items-start gap-2 rounded-lg px-2 py-1.5 hover:bg-slate-50">
                <span className="w-36 shrink-0 text-[11px] font-medium text-slate-500 pt-0.5">{key.replace(/_/g, ' ')}</span>
                {isEditing ? (
                  <input
                    value={editing[key]}
                    onChange={(e) => onEditField(key, e.target.value)}
                    className="flex-1 rounded border border-brand/30 px-2 py-0.5 text-[12px] text-slate-900 outline-none focus:ring-1 focus:ring-brand/30"
                    autoFocus
                  />
                ) : (
                  <div className="flex-1 text-[12px] text-slate-800 break-all">
                    {key === 'record_status' && value ? (
                      <span className={`inline-block rounded px-1.5 py-0.5 font-medium ${STATUS_COLORS[String(value)] ?? 'bg-slate-100'}`}>
                        {displayVal}
                      </span>
                    ) : displayVal}
                  </div>
                )}
                {isEditable && !isEditing && (
                  <button
                    type="button"
                    onClick={() => onEditField(key, String(value ?? ''))}
                    className="shrink-0 rounded p-1 text-slate-300 hover:text-brand-dark hover:bg-brand/10 transition-colors"
                    title={`Edit ${key}`}
                  >
                    <Edit3 size={11} />
                  </button>
                )}
              </div>
            );
          })}
        </div>

        {hasEdits && (
          <div className="mt-3 flex items-center gap-2 border-t border-slate-100 pt-3">
            <button
              type="button"
              onClick={onSave}
              disabled={editSaving}
              className="inline-flex items-center gap-1.5 rounded-lg bg-brand px-3 py-1.5 text-xs font-medium text-white shadow-sm hover:bg-brand-dark disabled:opacity-50"
            >
              <Check size={12} />
              {editSaving ? 'Saving...' : 'Save Changes'}
            </button>
            <button
              type="button"
              onClick={onCancelEdit}
              className="rounded-lg px-3 py-1.5 text-xs font-medium text-slate-500 hover:bg-slate-100"
            >
              Cancel
            </button>
          </div>
        )}
      </div>

      {/* Quality Results */}
      {detail.quality_results.length > 0 && (
        <div>
          <h4 className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 mb-2">
            <Shield size={11} className="inline mr-1" />
            Quality Checks ({detail.quality_results.length})
          </h4>
          <div className="space-y-1">
            {detail.quality_results.map((qr, i) => (
              <div key={i} className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-[11px]">
                {qr.passed ? (
                  <Check size={12} className="text-emerald-500 shrink-0" />
                ) : (
                  <X size={12} className="text-red-400 shrink-0" />
                )}
                <span className="font-medium text-slate-700">{qr.rule_name}</span>
                <span className={`ml-auto rounded px-1.5 py-0.5 text-[10px] font-medium ${
                  qr.severity === 'critical' ? 'bg-red-100 text-red-700' :
                  qr.severity === 'warning' ? 'bg-amber-100 text-amber-700' :
                  'bg-slate-100 text-slate-500'
                }`}>
                  {qr.severity}
                </span>
                <span className="tabular-nums text-slate-500">{(qr.score * 100).toFixed(0)}%</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Links */}
      {detail.links.length > 0 && (
        <div>
          <h4 className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 mb-2">
            <Link2 size={11} className="inline mr-1" />
            Relationships ({detail.links.length})
          </h4>
          <div className="space-y-1 max-h-48 overflow-y-auto">
            {detail.links.map((link, i) => (
              <div key={i} className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-[11px] hover:bg-slate-50">
                <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-600">{link.link_type}</span>
                <span className="text-slate-500">{link.source_entity_type}</span>
                <span className="text-slate-300">→</span>
                <span className="text-slate-500">{link.target_entity_type}</span>
                <span className="ml-auto text-[10px] tabular-nums text-slate-400">{(link.confidence * 100).toFixed(0)}%</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Aliases */}
      {detail.aliases.length > 0 && (
        <div>
          <h4 className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 mb-2">
            <Tag size={11} className="inline mr-1" />
            Aliases ({detail.aliases.length})
          </h4>
          <div className="flex flex-wrap gap-1.5">
            {detail.aliases.map((alias, i) => (
              <span key={i} className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2.5 py-1 text-[11px] text-slate-700">
                {alias.alias_text}
                {alias.verified && <Check size={10} className="text-emerald-500" />}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Tags */}
      {detail.tags.length > 0 && (
        <div>
          <h4 className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 mb-2">Tags</h4>
          <div className="flex flex-wrap gap-1.5">
            {detail.tags.map((tag, i) => (
              <span key={i} className="inline-flex items-center rounded-full bg-brand/10 px-2.5 py-1 text-[11px] text-brand-dark">
                <span className="font-medium">{tag.tag_name}:</span>
                <span className="ml-1">{tag.tag_value}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Change Log */}
      {detail.change_log.length > 0 && (
        <div>
          <h4 className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 mb-2">
            <Clock size={11} className="inline mr-1" />
            Change History ({detail.change_log.length})
          </h4>
          <div className="space-y-1.5 max-h-40 overflow-y-auto">
            {detail.change_log.map((ch) => (
              <div key={ch.id} className="rounded-lg bg-slate-50 px-2.5 py-1.5 text-[11px]">
                <div className="flex items-center gap-2">
                  <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${
                    ch.change_type === 'manual_edit' ? 'bg-brand/10 text-brand-dark' :
                    ch.change_type === 'insert' ? 'bg-emerald-100 text-emerald-700' :
                    'bg-slate-100 text-slate-600'
                  }`}>{ch.change_type}</span>
                  <span className="text-slate-400">{formatDateShort(ch.changed_at)}</span>
                </div>
                {ch.changed_fields?.length > 0 && (
                  <div className="mt-0.5 text-slate-500">Fields: {ch.changed_fields.join(', ')}</div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Ask in Chat */}
      {onAskInChat && (
        <div className="border-t border-slate-100 pt-3">
          <button
            type="button"
            onClick={() => {
              const label = String(entity._label ?? entity.generic_name ?? entity.name ?? entity.title ?? '');
              onAskInChat(`Tell me about ${label}`);
            }}
            className="inline-flex items-center gap-1.5 rounded-lg bg-brand/10 px-3 py-1.5 text-xs font-medium text-brand-dark hover:bg-brand/20"
          >
            <MessageSquare size={12} />
            Explore in Chat
          </button>
        </div>
      )}
    </div>
  );
}


// ═══════════════════════════════════════════
//  Changes Tab
// ═══════════════════════════════════════════

function ChangesTab({ changes: _initial, total: _initTotal, loading: initLoading }: { changes: ChangeLogEntry[]; total: number; loading: boolean }) {
  const [changes, setChanges] = useState<Array<ChangeLogEntry & { entity_label?: string }>>(_initial as Array<ChangeLogEntry & { entity_label?: string }>);
  const [total, setTotal] = useState(_initTotal);
  const [loading, setLoading] = useState(initLoading);
  const [filterType, setFilterType] = useState<string>('');
  const [filterChangeType, setFilterChangeType] = useState<string>('');
  const [summary, setSummary] = useState<Array<Record<string, unknown>>>([]);
  const [page, setPage] = useState(0);
  const pageSize = 30;

  const loadChanges = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.catalogChanges({
        entity_type: filterType || undefined,
        limit: pageSize,
        offset: page * pageSize,
      }) as { changes: Array<ChangeLogEntry & { entity_label?: string }>; total: number; summary?: Array<Record<string, unknown>> };
      setChanges(res.changes);
      setTotal(res.total);
      if (res.summary) setSummary(res.summary);
    } catch { /* ignore */ }
    setLoading(false);
  }, [filterType, page]);

  useEffect(() => { void loadChanges(); }, [loadChanges]);

  const CHANGE_TYPE_LABELS: Record<string, string> = {
    created: 'New record created by ETL pipeline',
    updated: 'Record updated with new data',
    manual_edit: 'Manually edited by user',
    merged: 'Records merged during deduplication',
  };

  // Group summary by entity_type
  const typeSummary = useMemo(() => {
    const map: Record<string, number> = {};
    for (const s of summary) {
      const t = String(s.entity_type ?? '');
      map[t] = (map[t] ?? 0) + Number(s.cnt ?? 0);
    }
    return Object.entries(map).sort((a, b) => b[1] - a[1]);
  }, [summary]);

  const totalPages = Math.ceil(total / pageSize);

  return (
    <>
      {/* Summary cards */}
      <section className="surface-panel rounded-xl px-5 py-4">
        <h3 className="text-[13px] font-semibold text-slate-900">Change Summary</h3>
        <p className="mt-0.5 text-[11px] text-slate-400">
          {fmt(total)} total changes recorded. Filter by entity type to focus on specific areas.
        </p>
        {typeSummary.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => { setFilterType(''); setPage(0); }}
              className={`rounded-lg px-2.5 py-1 text-[11px] font-medium ${
                !filterType ? 'bg-brand text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
            >
              All ({fmt(total)})
            </button>
            {typeSummary.map(([type, count]) => (
              <button
                key={type}
                type="button"
                onClick={() => { setFilterType(type); setPage(0); }}
                className={`rounded-lg px-2.5 py-1 text-[11px] font-medium ${
                  filterType === type ? 'bg-brand text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                }`}
              >
                {type} ({fmt(count)})
              </button>
            ))}
          </div>
        )}
      </section>

      {/* Changes list */}
      <section className="surface-panel rounded-xl px-5 py-4">
        <div className="flex items-center justify-between mb-3">
          <span className="text-[11px] text-slate-500">
            {loading ? 'Loading...' : `Showing ${page * pageSize + 1}–${Math.min((page + 1) * pageSize, total)} of ${fmt(total)}`}
          </span>
          <div className="flex items-center gap-1">
            <button type="button" disabled={page === 0} onClick={() => setPage(page - 1)} className="rounded p-1 text-slate-400 hover:bg-slate-100 disabled:opacity-30"><ChevronLeft size={14} /></button>
            <span className="text-[11px] text-slate-500 px-1">Page {page + 1}/{totalPages || 1}</span>
            <button type="button" disabled={page + 1 >= totalPages} onClick={() => setPage(page + 1)} className="rounded p-1 text-slate-400 hover:bg-slate-100 disabled:opacity-30"><ChevronRight size={14} /></button>
          </div>
        </div>

        {changes.length === 0 ? (
          <div className="py-6 text-center text-sm text-slate-400">No changes recorded{filterType ? ` for ${filterType}` : ''}.</div>
        ) : (
          <div className="space-y-1.5">
            {changes.map((ch) => (
              <div key={ch.id} className="flex items-start gap-3 rounded-lg bg-white/90 px-3 py-2.5 shadow-sm text-[12px]">
                <div className={`mt-0.5 shrink-0 rounded p-1 ${
                  ch.change_type === 'manual_edit' ? 'bg-brand/10 text-brand-dark' :
                  ch.change_type === 'created' ? 'bg-emerald-100 text-emerald-700' :
                  ch.change_type === 'updated' ? 'bg-amber-100 text-amber-700' :
                  'bg-slate-100 text-slate-500'
                }`}>
                  {ch.change_type === 'manual_edit' ? <Edit3 size={12} /> :
                   ch.change_type === 'created' ? <Plus size={12} /> :
                   <RefreshCw size={12} />}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-medium text-slate-800 truncate max-w-[300px]">
                      {ch.entity_label ?? ch.entity_id}
                    </span>
                    <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-500">{ch.entity_type}</span>
                    <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${
                      ch.change_type === 'created' ? 'bg-emerald-100 text-emerald-700' :
                      ch.change_type === 'manual_edit' ? 'bg-brand/10 text-brand-dark' :
                      'bg-slate-100 text-slate-500'
                    }`}>{ch.change_type}</span>
                  </div>
                  <div className="mt-0.5 text-[10px] text-slate-400">
                    {CHANGE_TYPE_LABELS[ch.change_type] ?? ch.change_type}
                    {ch.changed_fields?.length > 0 && ` — fields: ${ch.changed_fields.join(', ')}`}
                  </div>
                </div>
                <span className="shrink-0 text-[10px] text-slate-400 whitespace-nowrap">{formatDateShort(ch.changed_at)}</span>
              </div>
            ))}
          </div>
        )}
      </section>
    </>
  );
}


// ═══════════════════════════════════════════
//  Quality Tab
// ═══════════════════════════════════════════

function QualityTab({ stats, datasets, onOpenEntity }: { stats: CatalogStats | null; datasets: CatalogDataset[]; onOpenEntity?: (type: string, id: string) => void }) {
  const [qualityData, setQualityData] = useState<{
    summary: Array<Record<string, unknown>>;
    rules: Array<Record<string, unknown>>;
    top_failures: Array<Record<string, unknown>>;
    worst_entities: Array<Record<string, unknown>>;
  } | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.catalogQuality().then((d) => setQualityData(d as typeof qualityData)).catch(() => setQualityData(null)).finally(() => setLoading(false));
  }, []);

  const RULE_EXPLANATIONS: Record<string, string> = {
    drug_completeness_core: 'Drug records missing key fields like brand name, company, or mechanism',
    drug_company_link: 'Drugs not linked to any company — can\'t track who makes them',
    drug_cross_source: 'Drugs only found in one source — less trustworthy without cross-validation',
    trial_completeness: 'Trials missing enrollment, dates, or phase information',
    trial_drug_link: 'Trials not linked to any drug entity',
    literature_completeness: 'Articles missing DOI, journal, or mesh terms',
    company_completeness: 'Companies missing region, ticker, or CIK identifiers',
  };

  if (loading) return <div className="surface-panel rounded-xl px-6 py-8 text-sm text-slate-500">Loading quality data...</div>;

  return (
    <>
      {/* Quality by type */}
      <section className="surface-panel rounded-xl px-5 py-4">
        <h3 className="text-[13px] font-semibold text-slate-900">Quality Scorecard</h3>
        <p className="mt-0.5 text-[11px] text-slate-400">
          Average data quality score per entity type. Higher is better — scores below 70% need attention.
        </p>
        {qualityData?.summary && qualityData.summary.length > 0 ? (
          <div className="mt-3 space-y-2">
            {qualityData.summary.map((row, i) => {
              const avgScore = Number(row.avg_score ?? 0);
              const failed = Number(row.rules_failed ?? 0);
              const assessed = Number(row.entities_assessed ?? 0);
              return (
                <div key={i} className="rounded-lg bg-white/90 px-3 py-2.5 shadow-sm text-[12px]">
                  <div className="flex items-center gap-3">
                    <span className="w-24 shrink-0 font-medium text-slate-800">{String(row.entity_type)}</span>
                    <div className="flex-1 h-2 rounded-full bg-slate-100 overflow-hidden">
                      <div
                        className={`h-full rounded-full ${avgScore >= 0.7 ? 'bg-emerald-400' : avgScore >= 0.4 ? 'bg-amber-400' : 'bg-red-400'}`}
                        style={{ width: `${avgScore * 100}%` }}
                      />
                    </div>
                    <span className="w-12 text-right font-semibold tabular-nums">{(avgScore * 100).toFixed(0)}%</span>
                  </div>
                  <div className="mt-1 flex items-center gap-3 text-[10px] text-slate-400 pl-[6.5rem]">
                    <span>{fmt(assessed)} entities assessed</span>
                    {failed > 0 && <span className="text-red-500">{fmt(failed)} rule failures</span>}
                    <span className="text-emerald-500">{fmt(Number(row.rules_passed ?? 0))} passed</span>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="py-4 text-sm text-slate-400">No quality assessments available.</div>
        )}
      </section>

      {/* Top failing rules — actionable */}
      {qualityData?.top_failures && qualityData.top_failures.length > 0 && (
        <section className="surface-panel rounded-xl px-5 py-4">
          <h3 className="text-[13px] font-semibold text-slate-900">Top Issues to Fix</h3>
          <p className="mt-0.5 text-[11px] text-slate-400">
            Most common quality failures. Fixing these will improve the overall data quality score.
          </p>
          <div className="mt-3 space-y-2">
            {qualityData.top_failures.map((f, i) => {
              const ruleName = String(f.rule_name ?? '');
              const count = Number(f.failure_count ?? 0);
              const severity = String(f.severity ?? 'info');
              return (
                <div key={i} className="rounded-lg bg-white/90 px-3 py-3 shadow-sm">
                  <div className="flex items-center gap-2 text-[12px]">
                    <span className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium ${
                      severity === 'critical' ? 'bg-red-100 text-red-700' :
                      severity === 'warning' ? 'bg-amber-100 text-amber-700' :
                      'bg-slate-100 text-slate-500'
                    }`}>{severity}</span>
                    <span className="font-medium text-slate-800">{ruleName.replace(/_/g, ' ')}</span>
                    <span className="ml-auto rounded bg-red-50 px-1.5 py-0.5 text-[10px] font-semibold text-red-600 tabular-nums">
                      {fmt(count)} affected
                    </span>
                  </div>
                  <div className="mt-1 text-[11px] text-slate-500">
                    {RULE_EXPLANATIONS[ruleName] ?? `${String(f.rule_type ?? '')} check on ${String(f.entity_type ?? '')} entities`}
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* Worst entities — click to inspect */}
      {qualityData?.worst_entities && qualityData.worst_entities.length > 0 && (
        <section className="surface-panel rounded-xl px-5 py-4">
          <h3 className="text-[13px] font-semibold text-slate-900">Entities Needing Attention</h3>
          <p className="mt-0.5 text-[11px] text-slate-400">
            Entities with the most quality issues. Click to inspect and fix.
          </p>
          <div className="mt-3 space-y-1">
            {qualityData.worst_entities.map((e, i) => {
              const label = String(e.entity_label ?? e.entity_id ?? '');
              const score = Number(e.avg_score ?? 0);
              const failures = Number(e.failures ?? 0);
              const failingRules = (e.failing_rules as string[]) ?? [];
              return (
                <div
                  key={i}
                  className="group flex items-center gap-3 rounded-lg bg-white/90 px-3 py-2 shadow-sm text-[12px] hover:bg-slate-50 cursor-pointer transition-colors"
                  onClick={() => onOpenEntity?.(String(e.entity_type), String(e.entity_id))}
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-slate-800 truncate max-w-[300px]">{label}</span>
                      <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-500">{String(e.entity_type)}</span>
                    </div>
                    <div className="mt-0.5 text-[10px] text-slate-400">
                      Failing: {failingRules.map((r) => r.replace(/_/g, ' ')).join(', ')}
                    </div>
                  </div>
                  <span className="shrink-0 text-red-500 text-[10px] font-medium">{failures} issues</span>
                  <span className={`shrink-0 w-10 text-right font-semibold tabular-nums ${
                    score >= 0.7 ? 'text-emerald-600' : score >= 0.4 ? 'text-amber-600' : 'text-red-600'
                  }`}>{(score * 100).toFixed(0)}%</span>
                  <ChevronRight size={14} className="text-slate-300 shrink-0" />
                </div>
              );
            })}
          </div>
        </section>
      )}
    </>
  );
}


// ═══════════════════════════════════════════
//  Curation Tab
// ═══════════════════════════════════════════

function CurationTab({
  hitlItems, hitlTotal, hitlLoading,
  enrichType, enrichScope, enrichDesc, enrichSubmitting, enrichMessage,
  onEnrichTypeChange, onEnrichScopeChange, onEnrichDescChange, onEnrich, onResolve,
}: {
  hitlItems: Array<HITLItem & { entity_label?: string; description?: string }>;
  hitlTotal: number;
  hitlLoading: boolean;
  enrichType: string;
  enrichScope: string;
  enrichDesc: string;
  enrichSubmitting: boolean;
  enrichMessage: string | null;
  onEnrichTypeChange: (t: string) => void;
  onEnrichScopeChange: (s: string) => void;
  onEnrichDescChange: (d: string) => void;
  onEnrich: () => void;
  onResolve: (id: string, action: string) => void;
}) {
  const [filterType, setFilterType] = useState<string>('');
  const [filterReview, setFilterReview] = useState<string>('');

  // Group by review type for summary
  const reviewTypeCounts = useMemo(() => {
    const map: Record<string, number> = {};
    for (const item of hitlItems) {
      map[item.review_type] = (map[item.review_type] ?? 0) + 1;
    }
    return Object.entries(map).sort((a, b) => b[1] - a[1]);
  }, [hitlItems]);

  const filtered = useMemo(() => {
    let items = hitlItems;
    if (filterType) items = items.filter((i) => i.entity_type === filterType);
    if (filterReview) items = items.filter((i) => i.review_type === filterReview);
    return items;
  }, [hitlItems, filterType, filterReview]);

  const REVIEW_TYPE_LABELS: Record<string, { label: string; color: string; explanation: string }> = {
    entity_resolution: {
      label: 'Unresolved Entity',
      color: 'bg-amber-100 text-amber-700',
      explanation: 'System couldn\'t match this to a known entity — confirm or create new',
    },
    quality_failure: {
      label: 'Quality Issue',
      color: 'bg-red-100 text-red-700',
      explanation: 'Data quality check failed — review and fix the data',
    },
    enrichment_request: {
      label: 'Enrichment Request',
      color: 'bg-brand/10 text-brand-dark',
      explanation: 'User-requested data curation',
    },
    duplicate_candidate: {
      label: 'Possible Duplicate',
      color: 'bg-purple-100 text-purple-700',
      explanation: 'Two records may refer to the same entity — merge or keep separate',
    },
  };

  return (
    <>
      {/* Enrichment request */}
      <section className="surface-panel rounded-xl px-5 py-4">
        <h3 className="text-[13px] font-semibold text-slate-900">Request Data Curation</h3>
        <p className="mt-0.5 text-[11px] text-slate-400">
          Add a new therapeutic area, expand mechanism coverage, or request data for a specific entity.
        </p>
        <div className="mt-3 space-y-3">
          <div className="flex flex-wrap gap-3">
            <div>
              <label className="text-[10px] font-medium uppercase tracking-wider text-slate-400">Type</label>
              <select
                value={enrichType}
                onChange={(e) => onEnrichTypeChange(e.target.value)}
                className="mt-1 block h-8 rounded-lg border border-slate-200 bg-white px-2.5 text-xs text-slate-800 outline-none focus:ring-2 focus:ring-brand/15"
              >
                {ENTITY_TYPE_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>
            <div className="flex-1 min-w-[200px]">
              <label className="text-[10px] font-medium uppercase tracking-wider text-slate-400">Scope</label>
              <input
                value={enrichScope}
                onChange={(e) => onEnrichScopeChange(e.target.value)}
                placeholder="e.g., Oncology, GLP-1 receptor agonist, Novo Nordisk..."
                className="mt-1 input-surface h-8 w-full rounded-lg px-3 text-xs text-slate-900 placeholder:text-slate-400 outline-none focus:ring-2 focus:ring-brand/15"
              />
            </div>
          </div>
          <div>
            <label className="text-[10px] font-medium uppercase tracking-wider text-slate-400">Description (optional)</label>
            <input
              value={enrichDesc}
              onChange={(e) => onEnrichDescChange(e.target.value)}
              placeholder="What data should be curated..."
              className="mt-1 input-surface h-8 w-full rounded-lg px-3 text-xs text-slate-900 placeholder:text-slate-400 outline-none focus:ring-2 focus:ring-brand/15"
            />
          </div>
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={onEnrich}
              disabled={!enrichScope.trim() || enrichSubmitting}
              className="inline-flex items-center gap-1.5 rounded-lg bg-brand px-4 py-1.5 text-xs font-medium text-white shadow-sm hover:bg-brand-dark disabled:opacity-50"
            >
              <Plus size={12} />
              {enrichSubmitting ? 'Submitting...' : 'Submit Request'}
            </button>
            {enrichMessage && (
              <span className="text-[11px] text-emerald-600 font-medium">{enrichMessage}</span>
            )}
          </div>
        </div>
      </section>

      {/* Review Queue */}
      <section className="surface-panel rounded-xl px-5 py-4">
        <h3 className="text-[13px] font-semibold text-slate-900">Review Queue ({fmt(hitlTotal)} pending)</h3>
        <p className="mt-0.5 text-[11px] text-slate-400">
          Items the system flagged for human review. Read the description, then approve, reject, or defer.
        </p>

        {/* Filters */}
        <div className="mt-3 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => setFilterReview('')}
            className={`rounded-lg px-2.5 py-1 text-[11px] font-medium ${
              !filterReview ? 'bg-brand text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
            }`}
          >
            All types
          </button>
          {reviewTypeCounts.map(([type, count]) => {
            const meta = REVIEW_TYPE_LABELS[type];
            return (
              <button
                key={type}
                type="button"
                onClick={() => setFilterReview(type)}
                className={`rounded-lg px-2.5 py-1 text-[11px] font-medium ${
                  filterReview === type ? 'bg-brand text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                }`}
              >
                {meta?.label ?? type} ({count})
              </button>
            );
          })}
        </div>

        {hitlLoading ? (
          <div className="py-6 text-center text-sm text-slate-500">Loading...</div>
        ) : filtered.length === 0 ? (
          <div className="py-6 text-center text-sm text-slate-400">No items match the current filter.</div>
        ) : (
          <div className="mt-3 space-y-2">
            {filtered.slice(0, 30).map((item) => {
              const meta = REVIEW_TYPE_LABELS[item.review_type] ?? { label: item.review_type, color: 'bg-slate-100 text-slate-600', explanation: '' };
              const rawValue = item.payload?.raw_value as string | undefined;
              const source = item.payload?.source_type as string | undefined;

              return (
                <div key={item.id} className="rounded-lg bg-white/90 px-4 py-3 shadow-sm">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      {/* Type badge + entity */}
                      <div className="flex items-center gap-2 text-[12px] flex-wrap">
                        <span className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium ${meta.color}`}>
                          {meta.label}
                        </span>
                        <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-500">{item.entity_type}</span>
                      </div>

                      {/* Human-readable description */}
                      <div className="mt-1.5 text-[12px] text-slate-700 leading-relaxed">
                        {item.description ?? meta.explanation}
                      </div>

                      {/* Extra context for entity_resolution */}
                      {item.review_type === 'entity_resolution' && rawValue && (
                        <div className="mt-1.5 rounded-md bg-slate-50 px-3 py-2 text-[11px]">
                          <div className="flex items-center gap-2">
                            <span className="text-slate-400">Raw value:</span>
                            <span className="font-medium text-slate-800">"{rawValue}"</span>
                          </div>
                          {source && (
                            <div className="flex items-center gap-2 mt-0.5">
                              <span className="text-slate-400">Source:</span>
                              <span className="text-slate-600">{SOURCE_LABELS[source] ?? source}</span>
                            </div>
                          )}
                        </div>
                      )}

                      <div className="mt-1 text-[10px] text-slate-400">
                        Priority {item.priority} · {formatDateShort(item.created_at)}
                      </div>
                    </div>

                    {/* Actions */}
                    <div className="flex flex-col gap-1 shrink-0">
                      <button
                        type="button"
                        onClick={() => onResolve(item.id, 'approved')}
                        className="rounded-md bg-emerald-100 px-3 py-1.5 text-[11px] font-medium text-emerald-700 hover:bg-emerald-200 transition-colors"
                      >
                        Approve
                      </button>
                      <button
                        type="button"
                        onClick={() => onResolve(item.id, 'rejected')}
                        className="rounded-md bg-red-100 px-3 py-1.5 text-[11px] font-medium text-red-700 hover:bg-red-200 transition-colors"
                      >
                        Reject
                      </button>
                      <button
                        type="button"
                        onClick={() => onResolve(item.id, 'deferred')}
                        className="rounded-md bg-slate-100 px-3 py-1.5 text-[11px] font-medium text-slate-600 hover:bg-slate-200 transition-colors"
                      >
                        Defer
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
            {filtered.length > 30 && (
              <div className="text-center text-[11px] text-slate-400 py-2">
                Showing 30 of {fmt(filtered.length)} items. Use filters to narrow down.
              </div>
            )}
          </div>
        )}
      </section>
    </>
  );
}


// ═══════════════════════════════════════════
//  Shared Components
// ═══════════════════════════════════════════

function StatCard({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
  return (
    <div className="surface-panel rounded-xl px-4 py-3">
      <div className="inline-flex h-6 w-6 items-center justify-center rounded-lg bg-brand/10 text-brand-dark">{icon}</div>
      <div className="mt-1.5 text-[10px] font-medium uppercase tracking-wide text-slate-400">{label}</div>
      <div className="mt-0.5 text-lg font-semibold tracking-tight text-slate-900">{value}</div>
    </div>
  );
}
