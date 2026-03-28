import { useCallback, useEffect, useMemo, useState } from 'react';
import { LiteratureExplorer } from './LiteratureExplorer';
import { displayName, isUUID, QUALITY_CHECK_LABELS, SOURCE_LABELS } from '../brand';
import {
  CheckCircle,
  ChevronLeft,
  ChevronRight,
  Clock,
  Database,
  Edit3,
  ExternalLink,
  Globe,
  MessageSquare,
  RefreshCw,
  Search,
  Shield,
  AlertCircle,
  X,
  XCircle,
} from 'lucide-react';
import {
  api,
  type CatalogBrowseResponse,
  type CatalogDataset,
  type CatalogEntity,
  type CatalogEntityDetail,
  type CatalogStats,
  type ChangeLogEntry,
  type DatasetProfile,
  type FieldCompleteness,
  type HealthData,
  type HITLItem,
  type SourceFreshness,
} from '../api';
import { Drawer } from './ui/Drawer';
import EntityDossier from './EntityDossier';

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
  const [tab, setTab] = useState<CatalogTab>('browse');
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
  const [browseSort, setBrowseSort] = useState('pipeline_score');
  const [featured, setFeatured] = useState<CatalogEntity[]>([]);

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [selectedEntity, setSelectedEntity] = useState<{ type: string; id: string } | null>(null);
  const [entityDetail, setEntityDetail] = useState<CatalogEntityDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [litExplorerArticleId, setLitExplorerArticleId] = useState<string | null>(null);

  const [changes, setChanges] = useState<ChangeLogEntry[]>([]);
  const [hitlItems, setHitlItems] = useState<HITLItem[]>([]);

  const [editing, setEditing] = useState<Record<string, string>>({});

  const [dsProfileOpen, setDsProfileOpen] = useState(false);
  const [dsProfile, setDsProfile] = useState<DatasetProfile | null>(null);
  const [dsProfileLoading, setDsProfileLoading] = useState(false);

  const openDatasetProfile = useCallback((sourceKey: string) => {
    setDsProfileOpen(true);
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
      // Map frontend sort values to backend sort parameter
      const sortMap: Record<string, string> = {
        pipeline_score: 'pipeline_score',
        quality: 'quality',
        label: 'name',
        updated: 'recent',
      };
      const res = await api.catalogBrowse(browseType, {
        search: browseSearch || undefined,
        sort: sortMap[browseSort] ?? 'pipeline_score',
        limit: 30,
        offset: browsePage * 30,
      });
      setBrowseData(res);
    } catch { setBrowseData(null); }
    finally { setBrowseLoading(false); }
  }, [browseType, browseSearch, browsePage, browseSort]);

  // Load featured entities (graceful fail if endpoint not available)
  useEffect(() => {
    api.catalogBrowse('drug', { sort: 'pipeline_score', limit: 3 })
      .then(res => setFeatured(res.results))
      .catch(() => setFeatured([]));
  }, []);

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
    // Literature entities open in the dedicated Literature Explorer
    if (type === 'article' || type === 'literature') {
      setLitExplorerArticleId(id);
      return;
    }
    setSelectedEntity({ type, id });
    setDrawerOpen(true);
    setDetailLoading(true);
    setEntityDetail(null);
    api.catalogEntityDetail(type, id)
      .then(setEntityDetail)
      .catch(() => setEntityDetail(null))
      .finally(() => setDetailLoading(false));
  }, []);

  const [adminMode, setAdminMode] = useState(false);

  const TABS: Array<{ key: CatalogTab; label: string }> = adminMode
    ? [
        { key: 'overview', label: 'Overview' },
        { key: 'browse', label: 'Browse' },
        { key: 'changes', label: 'Audit Trail' },
        { key: 'curation', label: 'Curation' },
      ]
    : [
        { key: 'browse', label: 'Library' },
        { key: 'overview', label: 'Data Quality' },
      ];

  return (
    <div
      className="flex h-full flex-col overflow-hidden"
      style={{ background: 'var(--color-bg)' }}
    >
      {/* Top strip */}
      <div
        className="shrink-0 flex items-center justify-between"
        style={{ borderBottom: '1px solid var(--color-line)', background: 'var(--color-surface)', padding: '20px 32px' }}
      >
        <div>
          <h2
            style={{ fontSize: '17px', fontWeight: 600, color: 'var(--color-ink)', letterSpacing: '-0.02em' }}
          >
            {adminMode ? 'Data Catalog — Admin' : 'Entity Library'}
          </h2>
          <p style={{ fontSize: '12px', color: 'var(--color-ink-4)', marginTop: '2px' }}>
            {adminMode ? 'Monitor health, audit changes, and curate the knowledge base' : 'Browse and explore pharma entities'}
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => {
              setAdminMode(!adminMode);
              if (!adminMode) setTab('overview');
              else setTab('browse');
            }}
            className="btn btn-xs"
            style={{
              borderRadius: '6px',
              background: adminMode ? 'var(--color-ink)' : 'var(--color-surface-2)',
              color: adminMode ? 'var(--color-surface)' : 'var(--color-ink-4)',
              border: 'none',
            }}
          >
            {adminMode ? 'Exit Admin' : 'Admin'}
          </button>
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
        className="shrink-0 flex items-center gap-1"
        style={{ padding: '12px 32px', borderBottom: '1px solid var(--color-line)', background: 'var(--color-surface)' }}
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
      <div className="flex-1 overflow-y-auto" style={{ minHeight: 0, maxWidth: '1200px', marginLeft: 'auto', marginRight: 'auto', width: '100%', padding: '24px 32px' }}>
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
                onOpenProfile={openDatasetProfile}
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
                sort={browseSort}
                onSort={s => { setBrowseSort(s); setBrowsePage(0); }}
                featured={featured}
                stats={stats}
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
        subtitle={selectedEntity ? displayName(selectedEntity.type) : undefined}
      >
        {detailLoading ? (
          <div style={{ color: 'var(--color-ink-4)', fontSize: '13px' }}>Loading…</div>
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

      {/* Dataset profile drawer */}
      <Drawer
        isOpen={dsProfileOpen}
        onClose={() => setDsProfileOpen(false)}
        title={dsProfile?.display_name ?? 'Dataset Profile'}
        subtitle={dsProfile?.source_key}
      >
        {dsProfileLoading ? (
          <div style={{ color: 'var(--color-ink-4)', fontSize: '13px' }}>Loading profile…</div>
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
    </div>
  );
}

/* ══ Overview ══ */
function OverviewTab({ health, stats, datasets, onBrowse, onOpenProfile }: {
  health: HealthData | null;
  stats: CatalogStats | null;
  datasets: CatalogDataset[];
  onBrowse: (type: string) => void;
  onOpenProfile: (sourceKey: string) => void;
}) {
  const [completeness, setCompleteness] = useState<Record<string, FieldCompleteness> | null>(null);
  const [freshData, setFreshData] = useState<Record<string, SourceFreshness> | null>(null);
  const [graphSummary, setGraphSummary] = useState<{ link_types: Array<{type: string; count: number}>; total_links: number; total_entities: number; drug_completeness: Record<string, number> } | null>(null);
  const [taCoverage, setTaCoverage] = useState<Array<{id: string; name: string; drug_count: number; linked_drug_count: number; trial_count: number}> | null>(null);
  const [pipelineStatus, setPipelineStatus] = useState<Array<{source_key: string; label: string; schedule: string; last_run: string|null; days_since: number|null; records: number; status: string}> | null>(null);

  useEffect(() => {
    api.catalogCompleteness().then(r => setCompleteness(r.completeness)).catch(() => {});
    api.catalogFreshness().then(r => setFreshData(r.freshness)).catch(() => {});
    api.catalogGraphSummary().then(r => setGraphSummary(r)).catch(() => {});
    api.catalogTaCoverage().then(r => setTaCoverage(r.therapeutic_areas)).catch(() => {});
    api.catalogPipelineStatus().then(r => setPipelineStatus(r.connectors)).catch(() => {});
  }, []);

  const staleCount = freshData ? Object.values(freshData).filter(s => s.stale).length : 0;

  return (
    <div className="space-y-8">
      {/* Stale data alert */}
      {staleCount > 0 && (
        <div
          className="rounded-xl flex items-center gap-3"
          style={{ padding: '12px 20px', background: 'var(--color-amber-soft)', border: '1px solid var(--color-amber)' }}
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
            className="rounded-2xl"
            style={{
              padding: '20px',
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

      {/* ── Data Pipeline Status ── */}
      {pipelineStatus && pipelineStatus.length > 0 && (
        <div className="rounded-2xl overflow-hidden" style={{ background: 'var(--color-surface)', border: '1px solid var(--color-line)' }}>
          <div style={{ padding: '16px 24px', borderBottom: '1px solid var(--color-line)' }}>
            <h3 style={{ fontSize: '14px', fontWeight: 600, color: 'var(--color-ink)' }}>Data Pipeline</h3>
            <p style={{ fontSize: '11px', color: 'var(--color-ink-4)', marginTop: '2px' }}>
              9 connectors collect data from federal registries, literature databases, and regulatory filings
            </p>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '1px', background: 'var(--color-line-2)' }}>
            {pipelineStatus.map(c => {
              const statusIcon = c.status === 'fresh' ? '\u2713' : c.status === 'ok' ? '\u2713' : c.status === 'stale' ? '\u26A0' : '\u2014';
              const statusColor = c.status === 'fresh' ? 'var(--color-green)' : c.status === 'ok' ? 'var(--color-accent)' : c.status === 'stale' ? 'var(--color-amber)' : 'var(--color-ink-4)';
              const statusBg = c.status === 'fresh' ? 'var(--color-green-soft)' : c.status === 'ok' ? 'var(--color-accent-soft)' : c.status === 'stale' ? 'var(--color-amber-soft)' : 'var(--color-surface-2)';
              return (
                <div key={c.source_key} style={{ padding: '14px 18px', background: 'var(--color-surface)', cursor: 'pointer' }} onClick={() => onOpenProfile(c.source_key)}>
                  <div className="flex items-center justify-between">
                    <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--color-ink)' }}>{c.label}</span>
                    <span style={{ fontSize: '10px', fontWeight: 600, padding: '2px 8px', borderRadius: '10px', background: statusBg, color: statusColor }}>
                      {statusIcon} {c.status === 'fresh' ? 'Live' : c.status === 'ok' ? 'OK' : c.status === 'stale' ? 'Stale' : 'Pending'}
                    </span>
                  </div>
                  <div style={{ fontSize: '11px', color: 'var(--color-ink-4)', marginTop: '4px' }}>{c.schedule}</div>
                  <div className="flex items-center gap-3" style={{ marginTop: '6px' }}>
                    <span style={{ fontSize: '11px', color: 'var(--color-ink-3)' }}>{fmt(c.records)} records</span>
                    <span style={{ fontSize: '11px', color: 'var(--color-ink-4)' }}>
                      {c.days_since != null ? `Updated ${c.days_since < 1 ? 'today' : Math.round(c.days_since) + 'd ago'}` : 'Never run'}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ── Knowledge Graph Summary ── */}
      {graphSummary && (
        <div className="rounded-2xl overflow-hidden" style={{ background: 'var(--color-surface)', border: '1px solid var(--color-line)' }}>
          <div style={{ padding: '16px 24px', borderBottom: '1px solid var(--color-line)' }}>
            <h3 style={{ fontSize: '14px', fontWeight: 600, color: 'var(--color-ink)' }}>Knowledge Graph</h3>
            <p style={{ fontSize: '11px', color: 'var(--color-ink-4)', marginTop: '2px' }}>
              {fmt(graphSummary.total_entities)} entities connected by {fmt(graphSummary.total_links)} relationships
            </p>
          </div>
          <div style={{ padding: '16px 24px' }}>
            {/* Link type distribution */}
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginBottom: '16px' }}>
              {graphSummary.link_types.slice(0, 10).map(lt => (
                <span key={lt.type} style={{
                  fontSize: '11px', fontWeight: 500, padding: '4px 10px', borderRadius: '16px',
                  background: 'var(--color-surface-2)', color: 'var(--color-ink-2)',
                  border: '1px solid var(--color-line)',
                }}>
                  {lt.type.replace(/_/g, ' ')} <strong>{fmt(lt.count)}</strong>
                </span>
              ))}
            </div>
            {/* Drug linking completeness */}
            {graphSummary.drug_completeness?.total > 0 && (() => {
              const dc = graphSummary.drug_completeness;
              const bars = [
                { label: 'Company', pct: Math.round((dc.with_company / dc.total) * 100), color: 'var(--color-company)' },
                { label: 'Mechanism', pct: Math.round((dc.with_mechanism / dc.total) * 100), color: 'var(--color-mechanism)' },
                { label: 'Therapy Area', pct: Math.round((dc.with_therapeutic_area / dc.total) * 100), color: 'var(--color-ta)' },
                { label: 'Brand Name', pct: Math.round((dc.with_brand_name / dc.total) * 100), color: 'var(--color-accent)' },
              ];
              return (
                <div>
                  <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--color-ink-3)', marginBottom: '8px' }}>
                    Drug Entity Completeness ({fmt(dc.total)} active drugs)
                  </div>
                  {bars.map(b => (
                    <div key={b.label} className="flex items-center gap-3" style={{ marginBottom: '6px' }}>
                      <span style={{ fontSize: '11px', color: 'var(--color-ink-3)', width: '90px', flexShrink: 0 }}>{b.label}</span>
                      <div style={{ flex: 1, height: '6px', borderRadius: '3px', background: 'var(--color-surface-3)', overflow: 'hidden' }}>
                        <div style={{ width: `${b.pct}%`, height: '100%', borderRadius: '3px', background: b.color, transition: 'width 600ms ease' }} />
                      </div>
                      <span style={{ fontSize: '11px', fontWeight: 600, color: b.pct >= 70 ? 'var(--color-green)' : b.pct >= 40 ? 'var(--color-amber)' : 'var(--color-red)', width: '36px', textAlign: 'right' }}>
                        {b.pct}%
                      </span>
                    </div>
                  ))}
                </div>
              );
            })()}
          </div>
        </div>
      )}

      {/* ── Therapeutic Area Coverage ── */}
      {taCoverage && taCoverage.length > 0 && (
        <div className="rounded-2xl overflow-hidden" style={{ background: 'var(--color-surface)', border: '1px solid var(--color-line)' }}>
          <div style={{ padding: '16px 24px', borderBottom: '1px solid var(--color-line)' }}>
            <h3 style={{ fontSize: '14px', fontWeight: 600, color: 'var(--color-ink)' }}>Therapeutic Area Coverage</h3>
            <p style={{ fontSize: '11px', color: 'var(--color-ink-4)', marginTop: '2px' }}>
              {taCoverage.length} therapeutic areas across Diabetes, Cardiovascular, Obesity, and Metabolic disease
            </p>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: '1px', background: 'var(--color-line-2)' }}>
            {taCoverage.map(ta => {
              const totalDrugs = ta.drug_count + ta.linked_drug_count;
              const hasData = totalDrugs > 0 || ta.trial_count > 0;
              return (
                <div
                  key={ta.id}
                  style={{
                    padding: '12px 16px', background: 'var(--color-surface)',
                    cursor: 'pointer', transition: 'background 120ms',
                    borderLeft: `3px solid ${hasData ? 'var(--color-ta)' : 'var(--color-line)'}`,
                  }}
                  onClick={() => onBrowse('therapeutic_area')}
                  onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = 'var(--color-surface-2)'; }}
                  onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = 'var(--color-surface)'; }}
                >
                  <div style={{ fontSize: '12px', fontWeight: 600, color: hasData ? 'var(--color-ink)' : 'var(--color-ink-4)' }}>
                    {ta.name}
                  </div>
                  <div className="flex items-center gap-3" style={{ marginTop: '4px' }}>
                    {totalDrugs > 0 && (
                      <span style={{ fontSize: '10px', color: 'var(--color-drug)' }}>{totalDrugs} drugs</span>
                    )}
                    {ta.trial_count > 0 && (
                      <span style={{ fontSize: '10px', color: 'var(--color-trial)' }}>{fmt(ta.trial_count)} trials</span>
                    )}
                    {!hasData && (
                      <span style={{ fontSize: '10px', color: 'var(--color-ink-4)' }}>No data yet</span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Completeness bars */}
      {completeness && (
        <div
          className="rounded-2xl overflow-hidden"
          style={{ background: 'var(--color-surface)', border: '1px solid var(--color-line)' }}
        >
          <div style={{ padding: '16px 24px', borderBottom: '1px solid var(--color-line)' }}>
            <h3 style={{ fontSize: '14px', fontWeight: 600, color: 'var(--color-ink)' }}>Field Completeness</h3>
          </div>
          <div className="space-y-4" style={{ padding: '16px 24px' }}>
            {Object.entries(completeness).map(([etype, data]) => (
              <div key={etype}>
                <div className="flex items-center justify-between mb-2">
                  <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--color-ink)' }}>
                    {displayName(etype)}
                  </span>
                  <span style={{ fontSize: '12px', color: 'var(--color-ink-4)' }}>
                    {(data.overall * 100).toFixed(0)}% ({data.total} records)
                  </span>
                </div>
                <div className="flex gap-1.5 flex-wrap">
                  {Object.entries(data.fields).map(([field, score]) => {
                    const label = displayName(field);
                    return (
                      <div
                        key={field}
                        title={`${label}: ${(score * 100).toFixed(0)}%`}
                        className="rounded-lg"
                        style={{
                          padding: '4px 10px',
                          fontSize: '11px',
                          fontWeight: 500,
                          background: score >= 0.7 ? 'var(--color-green-soft)' : score >= 0.4 ? 'var(--color-amber-soft)' : 'var(--color-red-soft)',
                          color: score >= 0.7 ? 'var(--color-green)' : score >= 0.4 ? 'var(--color-amber)' : 'var(--color-red)',
                        }}
                      >
                        {label} {(score * 100).toFixed(0)}%
                      </div>
                    );
                  })}
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
          <div style={{ padding: '16px 24px', borderBottom: '1px solid var(--color-line)' }}>
            <h3 style={{ fontSize: '14px', fontWeight: 600, color: 'var(--color-ink)' }}>Source Freshness</h3>
          </div>
          {Object.entries(freshData).map(([source, info]) => {
            const fresh = info.days_since != null
              ? info.days_since <= 7 ? { label: 'Fresh', color: 'var(--color-green)' }
                : info.days_since <= 30 ? { label: 'Recent', color: 'var(--color-amber)' }
                : { label: 'Stale', color: 'var(--color-red)' }
              : { label: 'Unknown', color: 'var(--color-ink-4)' };
            return (
              <div
                key={source}
                className="catalog-row"
                onClick={() => onOpenProfile(source)}
                style={{ cursor: 'pointer' }}
              >
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: '13px', fontWeight: 500, color: 'var(--color-ink)' }}>
                    {SOURCE_LABELS[source] ?? source.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
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
          style={{ padding: '16px 24px', borderBottom: '1px solid var(--color-line)' }}
        >
          <h3 style={{ fontSize: '14px', fontWeight: 600, color: 'var(--color-ink)' }}>Datasets</h3>
        </div>
        {datasets.map(ds => {
          const fresh = freshness(ds.last_refreshed_at);
          // Map table names → primary source keys for profile lookup
          const TABLE_TO_SOURCE: Record<string, string> = {
            drugs: 'fda_orange_book',
            clinical_trials: 'clinical_trials_gov',
            pubmed_articles: 'pubmed',
            companies: 'sec_edgar',
            market_events: 'openfda_faers',
            therapeutic_areas: 'mesh_ontology',
            mechanisms_of_action: 'mesh_ontology',
          };
          const sourceKey = TABLE_TO_SOURCE[ds.dataset_name] ?? ds.source_type;
          return (
            <div
              key={ds.dataset_name}
              className="catalog-row group"
              onClick={() => onOpenProfile(sourceKey)}
              style={{ cursor: 'pointer' }}
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
              <div className="flex items-center gap-1.5">
                {ds.entity_type && (
                  <button
                    type="button"
                    className="btn-icon opacity-0 group-hover:opacity-100 transition-opacity"
                    style={{ width: '24px', height: '24px' }}
                    title="Browse entities"
                    onClick={e => { e.stopPropagation(); onBrowse(ds.entity_type!); }}
                  >
                    <Database size={12} style={{ color: 'var(--color-ink-4)' }} />
                  </button>
                )}
                <ChevronRight size={14} style={{ color: 'var(--color-ink-4)', flexShrink: 0 }} />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ══ Dataset Profile Card ══ */
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
    <div className="space-y-6">
      {/* Description */}
      <p style={{ fontSize: '13px', lineHeight: 1.6, color: 'var(--color-ink-3)' }}>
        {profile.description}
      </p>

      {/* Source URL */}
      {profile.source_url && (
        <a
          href={profile.source_url}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-2"
          style={{
            fontSize: '12px',
            color: 'var(--color-accent)',
            textDecoration: 'none',
            padding: '8px 12px',
            borderRadius: '8px',
            background: 'var(--color-accent-soft)',
            display: 'inline-flex',
          }}
        >
          <Globe size={13} />
          {profile.source_url.replace(/^https?:\/\//, '').replace(/\/$/, '')}
          <ExternalLink size={11} style={{ opacity: 0.6 }} />
        </a>
      )}

      {/* Live stats row */}
      <div
        className="grid grid-cols-3 gap-3"
      >
        <div
          className="rounded-xl"
          style={{ padding: '14px 16px', background: 'var(--color-surface-2)', border: '1px solid var(--color-line)' }}
        >
          <div style={{ fontSize: '20px', fontWeight: 300, color: 'var(--color-ink)', fontFamily: 'var(--font-display)', letterSpacing: '-0.02em' }}>
            {fmt(profile.records)}
          </div>
          <div style={{ fontSize: '10px', color: 'var(--color-ink-4)', marginTop: '2px', textTransform: 'uppercase', letterSpacing: '0.04em' }}>Records</div>
        </div>
        <div
          className="rounded-xl"
          style={{ padding: '14px 16px', background: 'var(--color-surface-2)', border: '1px solid var(--color-line)' }}
        >
          <div style={{ fontSize: '20px', fontWeight: 300, color: qualityColor, fontFamily: 'var(--font-display)', letterSpacing: '-0.02em' }}>
            {profile.quality_score != null ? `${(profile.quality_score * 100).toFixed(0)}%` : '--'}
          </div>
          <div style={{ fontSize: '10px', color: 'var(--color-ink-4)', marginTop: '2px', textTransform: 'uppercase', letterSpacing: '0.04em' }}>Quality</div>
        </div>
        <div
          className="rounded-xl"
          style={{ padding: '14px 16px', background: 'var(--color-surface-2)', border: '1px solid var(--color-line)' }}
        >
          <div className="flex items-center gap-1.5">
            <span
              className="rounded-full"
              style={{ width: '7px', height: '7px', background: freshnessStyle.color, flexShrink: 0 }}
            />
            <span style={{ fontSize: '14px', fontWeight: 500, color: freshnessStyle.color, textTransform: 'capitalize' }}>
              {profile.freshness}
            </span>
          </div>
          <div style={{ fontSize: '10px', color: 'var(--color-ink-4)', marginTop: '4px', textTransform: 'uppercase', letterSpacing: '0.04em' }}>Freshness</div>
        </div>
      </div>

      {/* Metadata rows */}
      <div
        className="rounded-xl overflow-hidden"
        style={{ border: '1px solid var(--color-line)' }}
      >
        {[
          { label: 'Entity Types', value: profile.entity_types.map(t => displayName(t)).join(', ') },
          { label: 'Collection Method', value: profile.collection_method },
          { label: 'Refresh Schedule', value: profile.refresh_schedule },
          { label: 'Last Refreshed', value: profile.last_refreshed ? shortDate(profile.last_refreshed) : 'Unknown' },
        ].map(({ label, value }) => (
          <div
            key={label}
            className="flex items-start justify-between"
            style={{ padding: '10px 16px', borderBottom: '1px solid var(--color-line)', fontSize: '12px' }}
          >
            <span style={{ color: 'var(--color-ink-4)', flexShrink: 0, minWidth: '130px' }}>{label}</span>
            <span style={{ color: 'var(--color-ink)', textAlign: 'right', fontWeight: 500 }}>{value}</span>
          </div>
        ))}
      </div>

      {/* Fields collected */}
      <div>
        <h4 style={{ fontSize: '12px', fontWeight: 600, color: 'var(--color-ink)', marginBottom: '8px', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
          Fields Collected
        </h4>
        <div className="flex flex-wrap gap-1.5">
          {profile.fields_collected.map(field => (
            <span
              key={field}
              className="rounded-md"
              style={{
                padding: '3px 8px',
                fontSize: '11px',
                fontWeight: 500,
                background: 'var(--color-surface-2)',
                color: 'var(--color-ink-3)',
                border: '1px solid var(--color-line)',
              }}
            >
              {field}
            </span>
          ))}
        </div>
      </div>

      {/* Coverage notes */}
      {profile.coverage_notes && (
        <div
          className="rounded-xl"
          style={{ padding: '12px 16px', background: 'var(--color-surface-2)', border: '1px solid var(--color-line)' }}
        >
          <div className="flex items-start gap-2">
            <Shield size={13} style={{ color: 'var(--color-ink-4)', flexShrink: 0, marginTop: '2px' }} />
            <div>
              <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--color-ink-3)', marginBottom: '3px', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                Coverage Notes
              </div>
              <p style={{ fontSize: '12px', lineHeight: 1.5, color: 'var(--color-ink-3)', margin: 0 }}>
                {profile.coverage_notes}
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ══ Browse ══ */
const SORT_OPTIONS = [
  { value: 'pipeline_score', label: 'Pipeline Score' },
  { value: 'quality', label: 'Quality' },
  { value: 'label', label: 'Name' },
  { value: 'updated', label: 'Recent' },
];

/** Quality indicator: green check >= 80%, amber dot 50-79%, grey text < 50% */
function QualityIndicator({ score }: { score: number }) {
  if (score >= 0.8) {
    return <span className="trust-certified"><CheckCircle size={10} /> Certified</span>;
  }
  if (score >= 0.5) {
    return <span className="trust-warning"><AlertCircle size={10} /> Partial</span>;
  }
  return <span className="trust-unknown">Incomplete</span>;
}

/** Build a context line (line 2) from entity fields, joining with middot */
function entityContextParts(entity: CatalogEntity, browseType: string): string[] {
  const parts: string[] = [];
  if (browseType === 'drug') {
    if (entity.mechanism_name) parts.push(String(entity.mechanism_name));
    else if (entity.mechanism_id && !isUUID(String(entity.mechanism_id))) parts.push(String(entity.mechanism_id));
    if (entity.company_name) parts.push(String(entity.company_name));
    else if (entity.company_id && !isUUID(String(entity.company_id))) parts.push(String(entity.company_id));
    if (entity.therapeutic_area_name) parts.push(String(entity.therapeutic_area_name));
    else if (entity.therapeutic_area) parts.push(String(entity.therapeutic_area));
    else if (entity.therapeutic_area_id && !isUUID(String(entity.therapeutic_area_id))) parts.push(String(entity.therapeutic_area_id));
  } else if (browseType === 'company') {
    if (entity.drug_count != null) parts.push(`${fmt(Number(entity.drug_count))} drugs`);
    if (entity.trial_count != null) parts.push(`${fmt(Number(entity.trial_count))} trials`);
    if (entity.pipeline_score != null) parts.push(`Pipeline ${Number(entity.pipeline_score).toFixed(1)}`);
  } else if (browseType === 'trial') {
    if (entity.drug_name) parts.push(String(entity.drug_name));
    if (entity.sponsor_name) parts.push(String(entity.sponsor_name));
    if (entity.conditions) {
      const cond = String(entity.conditions);
      parts.push(cond.length > 40 ? cond.slice(0, 37) + '...' : cond);
    }
  } else if (browseType === 'mechanism') {
    if (entity.scope_note) {
      const note = String(entity.scope_note);
      parts.push(note.length > 60 ? note.slice(0, 57) + '...' : note);
    }
  }
  return parts;
}

function BrowseTab({ browseType, onTypeChange, search, onSearch, data, loading, page, onPage, onOpen, onAskInChat, sort, onSort, featured, stats }: {
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
  sort: string;
  onSort: (s: string) => void;
  featured: CatalogEntity[];
  stats: CatalogStats | null;
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
            {ENTITY_TYPES.map(opt => {
              const count = stats?.entity_counts?.[opt.value];
              return (
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
                  {count != null && (
                    <span style={{ marginLeft: '4px', fontSize: '10px', opacity: 0.7 }}>
                      {fmt(count)}
                    </span>
                  )}
                </button>
              );
            })}
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

      {/* Featured entities — only shown on first page with no search */}
      {featured.length > 0 && page === 0 && !search && browseType === 'drug' && (
        <div>
          <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--color-amber)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '10px', display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ fontSize: '13px' }}>{'\u2605'}</span> Top by Pipeline Score
          </div>
          <div className="grid gap-3" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))' }}>
            {featured.map(entity => {
              const id = String(entity.id ?? entity._label ?? '');
              const label = String(entity._label ?? entity.generic_name ?? entity.name ?? id);
              const brandName = entity.brand_name ? String(entity.brand_name) : null;
              const q = entity.quality_score != null ? Number(entity.quality_score) : null;
              const phase = entity.phase ? String(entity.phase) : null;
              const contextParts = entityContextParts(entity, 'drug');
              const trialCount = entity.trial_count != null ? Number(entity.trial_count) : null;
              const pipelineScore = entity.pipeline_score != null ? Number(entity.pipeline_score) : null;

              return (
                <div
                  key={id}
                  onClick={() => id && onOpen('drug', id)}
                  className="featured-card"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5" style={{ minWidth: 0 }}>
                      <span
                        style={{ width: '6px', height: '6px', borderRadius: '50%', flexShrink: 0, background: 'var(--color-drug)' }}
                      />
                      <span className="truncate" style={{ fontSize: '13px', fontWeight: 600, color: 'var(--color-ink)' }}>
                        {label}
                      </span>
                    </div>
                    {phase && (
                      <span style={{
                        fontSize: '10px', fontWeight: 500, flexShrink: 0, marginLeft: '6px',
                        color: phase.includes('4') ? 'var(--color-green)' : phase.includes('3') ? 'var(--color-accent)' : 'var(--color-ink-4)',
                      }}>
                        {phase}
                      </span>
                    )}
                  </div>
                  {brandName && (
                    <div style={{ fontSize: '11px', color: 'var(--color-ink-4)', marginTop: '2px' }}>
                      {brandName}
                    </div>
                  )}
                  {contextParts.length > 0 && (
                    <div style={{ fontSize: '11px', color: 'var(--color-ink-3)', marginTop: '4px' }}>
                      {contextParts.join(' · ')}
                    </div>
                  )}
                  <div className="flex items-center gap-3" style={{ marginTop: '8px' }}>
                    {trialCount != null && (
                      <span style={{ fontSize: '10px', color: 'var(--color-ink-4)' }}>{fmt(trialCount)} trials</span>
                    )}
                    {pipelineScore != null && (
                      <span style={{ fontSize: '10px', color: 'var(--color-ink-4)' }}>Score {pipelineScore.toFixed(1)}</span>
                    )}
                    {q != null && <QualityIndicator score={q} />}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Results */}
      <div
        className="rounded-2xl overflow-hidden"
        style={{ background: 'var(--color-surface)', border: '1px solid var(--color-line)' }}
      >
        {loading ? (
          <div className="empty-state">
            <div className="empty-state-icon">{'\u23F3'}</div>
            <div className="empty-state-title">Loading entities...</div>
            <div className="empty-state-hint">Fetching from knowledge graph</div>
          </div>
        ) : !data || data.results.length === 0 ? (
          <div className="empty-state">
            <div className="empty-state-icon">{'\uD83D\uDD0D'}</div>
            <div className="empty-state-title">No entities found</div>
            <div className="empty-state-hint">{search ? `No results for "${search}". Try a different term.` : 'Try selecting a different entity type or adjusting filters.'}</div>
          </div>
        ) : (
          <>
            <div
              className="flex items-center justify-between"
              style={{ padding: '10px 24px', borderBottom: '1px solid var(--color-line)' }}
            >
              <div className="flex items-center gap-3">
                <span style={{ fontSize: '12px', color: 'var(--color-ink-4)' }}>
                  {fmt(data.total)} results
                </span>
                {/* Sort dropdown */}
                <div className="flex items-center gap-1">
                  <span style={{ fontSize: '11px', color: 'var(--color-ink-4)' }}>Sort:</span>
                  <select
                    value={sort}
                    onChange={e => onSort(e.target.value)}
                    style={{
                      fontSize: '11px',
                      fontWeight: 500,
                      color: 'var(--color-ink)',
                      background: 'var(--color-surface-2)',
                      border: '1px solid var(--color-line)',
                      borderRadius: '6px',
                      padding: '3px 8px',
                      cursor: 'pointer',
                      outline: 'none',
                    }}
                  >
                    {SORT_OPTIONS.map(opt => (
                      <option key={opt.value} value={opt.value}>{opt.label}</option>
                    ))}
                  </select>
                </div>
              </div>
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
              const q = entity.quality_score != null ? Number(entity.quality_score) : null;

              // Type-specific fields
              const brandName = entity.brand_name ? String(entity.brand_name) : null;
              const phase = entity.phase ? String(entity.phase) : null;
              const trialStatus = entity.status ? String(entity.status) : null;
              const ticker = entity.ticker ? String(entity.ticker) : null;
              const trialCount = entity.trial_count != null ? Number(entity.trial_count) : null;
              const enrollment = entity.enrollment_target != null ? Number(entity.enrollment_target) : null;

              // Phase badge colours
              const phaseColor = phase?.includes('4') || phase?.toLowerCase().includes('approved')
                ? 'var(--color-green)' : phase?.includes('3') ? 'var(--color-accent)'
                : phase?.includes('2') ? 'var(--color-amber)' : 'var(--color-ink-4)';

              // Trial status colours
              const statusColor = trialStatus === 'COMPLETED' ? 'var(--color-green)'
                : trialStatus === 'RECRUITING' || trialStatus === 'ACTIVE_NOT_RECRUITING' ? 'var(--color-accent)'
                : trialStatus === 'TERMINATED' || trialStatus === 'WITHDRAWN' ? 'var(--color-red)'
                : 'var(--color-ink-4)';

              // Context line parts (line 2)
              const contextParts = entityContextParts(entity, browseType);

              // Entity dot color
              const dotColor = browseType === 'drug' ? 'var(--color-drug)' : browseType === 'company' ? 'var(--color-company)'
                : browseType === 'trial' ? 'var(--color-trial)' : browseType === 'mechanism' ? 'var(--color-mechanism)'
                : browseType === 'therapeutic_area' ? 'var(--color-ta)' : 'var(--color-ink-4)';

              return (
                <div
                  key={id}
                  className="catalog-row group"
                  data-type={browseType}
                  onClick={() => id && onOpen(browseType, id)}
                  style={{ borderLeftColor: dotColor }}
                >
                  {/* Entity type indicator */}
                  <span
                    style={{
                      width: '8px', height: '8px', borderRadius: '50%', flexShrink: 0,
                      background: dotColor, marginTop: '5px', alignSelf: 'flex-start',
                      boxShadow: `0 0 0 3px color-mix(in srgb, ${dotColor} 15%, transparent)`,
                    }}
                  />

                  <div style={{ flex: 1, minWidth: 0 }}>
                    {/* Line 1: name + brand + right-aligned phase/ticker */}
                    <div className="flex items-center gap-2">
                      <span
                        className="truncate"
                        style={{ fontSize: '13px', fontWeight: 500, color: 'var(--color-ink)' }}
                      >
                        {label}
                      </span>
                      {brandName && (
                        <span style={{ fontSize: '11px', color: 'var(--color-ink-4)', flexShrink: 0 }}>
                          ({brandName})
                        </span>
                      )}
                      {/* Right-aligned badges */}
                      <span style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '6px', flexShrink: 0 }}>
                        {ticker && (
                          <span className="badge badge-neutral" style={{ fontSize: '10px' }}>
                            {ticker}
                          </span>
                        )}
                        {phase && (
                          <span className={`phase-badge ${phase.includes('4') ? 'phase-4' : phase.includes('3') ? 'phase-3' : phase.includes('2') ? 'phase-2' : 'phase-1'}`}>
                            {phase.includes('4') ? '\u2713 ' : ''}{phase}
                          </span>
                        )}
                        {browseType === 'trial' && trialStatus && (
                          <span style={{ fontSize: '10px', fontWeight: 500, color: statusColor, textTransform: 'capitalize' }}>
                            {trialStatus.toLowerCase().replace(/_/g, ' ')}
                          </span>
                        )}
                      </span>
                    </div>
                    {/* Line 2: context parts + trial count + quality */}
                    <div className="flex items-center gap-1.5" style={{ marginTop: '2px' }}>
                      {contextParts.length > 0 && (
                        <span style={{ fontSize: '11px', color: 'var(--color-ink-3)' }}>
                          {contextParts.join(' · ')}
                        </span>
                      )}
                      {trialCount != null && (
                        <span style={{ fontSize: '10px', color: 'var(--color-ink-4)' }}>
                          {contextParts.length > 0 ? ' · ' : ''}{fmt(trialCount)} trials
                        </span>
                      )}
                      {browseType === 'trial' && enrollment != null && enrollment > 0 && (
                        <span style={{ fontSize: '10px', color: 'var(--color-ink-4)' }}>
                          {contextParts.length > 0 || trialCount != null ? ' · ' : ''}{fmt(enrollment)} enrolled
                        </span>
                      )}
                      {/* Quality indicator — right-aligned */}
                      {q != null && (
                        <span style={{ marginLeft: 'auto' }}>
                          <QualityIndicator score={q} />
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
        <div className="text-center" style={{ padding: '48px 0', color: 'var(--color-ink-4)', fontSize: '13px' }}>No changes recorded.</div>
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
            className="rounded-lg"
            style={{ padding: '6px 12px', background: 'var(--color-surface)', border: '1px solid var(--color-line)', fontSize: '12px' }}
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
        <div className="text-center" style={{ padding: '48px 0', color: 'var(--color-ink-4)', fontSize: '13px' }}>
          No pending reviews.
        </div>
      )}
      {sorted.map(item => (
        <div
          key={item.id}
          className="rounded-2xl"
          style={{
            padding: '20px',
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

/* EntityDetailDrawer replaced by EntityDossier component (Sprint 5) */
