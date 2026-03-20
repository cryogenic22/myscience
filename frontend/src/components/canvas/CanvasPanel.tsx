import { useMemo, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Download, AlertTriangle, BarChart3, ChevronDown, ChevronRight, Layers, Table2 } from 'lucide-react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { TableData, VisualizationSpec, QueryResponse, EvidenceItem, PersonaAnalysis } from '../../api';

interface CanvasPanelProps {
  intent: string | null;
  data: QueryResponse | null;
  tableData: TableData | null;
  visualizations: VisualizationSpec[] | null;
  confidence?: number;
  guardStatus?: string;
  loading?: boolean;
  personaAnalyses?: PersonaAnalysis[];
  confidenceAssessment?: { overall: number; by_dimension: Record<string, number> };
}

const INTENT_LABELS: Record<string, string> = {
  landscape: 'Competitive Landscape',
  compare: 'Head-to-Head Comparison',
  dossier: 'Entity Profile',
  pipeline: 'Pipeline Analysis',
  portfolio: 'Company Portfolio',
  structured_query: 'Data Query',
  general: 'Analysis',
};

export default function CanvasPanel({
  intent,
  data,
  tableData,
  visualizations,
  confidence,
  guardStatus,
  loading,
  personaAnalyses,
  confidenceAssessment,
}: CanvasPanelProps) {
  const hasTable = Boolean(tableData && tableData.rows.length > 0);
  const hasViz = Boolean(visualizations && visualizations.length > 0);
  const hasEntities = Boolean(data?.entity_focus && data.entity_focus.length > 0);
  const hasMetrics = Boolean(data?.metrics_context && Object.keys(data.metrics_context).length > 0);
  const hasEvidence = Boolean(data?.evidence && data.evidence.length > 0);
  const hasPersonaAnalyses = Boolean(personaAnalyses && personaAnalyses.length > 0);
  const hasContent = hasTable || hasViz || hasEntities || hasMetrics || hasEvidence || hasPersonaAnalyses;

  if (loading) {
    return (
      <div className="flex h-full flex-col p-6">
        <div className="mb-4 h-5 w-40 animate-pulse rounded-md bg-slate-200/60 dark:bg-slate-700/40" />
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="rounded-xl bg-white p-5 dark:bg-slate-800/50">
              <div className="mb-3 h-4 w-24 animate-pulse rounded bg-slate-200/60 dark:bg-slate-700/40" />
              <div className="space-y-2">
                <div className="h-3 w-full animate-pulse rounded bg-slate-100 dark:bg-slate-700/30" />
                <div className="h-3 w-4/5 animate-pulse rounded bg-slate-100 dark:bg-slate-700/30" />
                <div className="h-3 w-3/5 animate-pulse rounded bg-slate-100 dark:bg-slate-700/30" />
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (!hasContent) {
    return (
      <div className="flex h-full flex-col items-center justify-center px-8">
        <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-slate-100/80 dark:bg-slate-800/60">
          <Layers size={20} className="text-slate-400 dark:text-slate-500" />
        </div>
        <p className="mt-4 text-[13px] font-medium text-slate-400 dark:text-slate-500">Data Canvas</p>
        <p className="mt-1 max-w-[240px] text-center text-[12px] leading-relaxed text-slate-400/80 dark:text-slate-500/80">
          Tables, charts, and entity details will appear here as you explore.
        </p>
      </div>
    );
  }

  const confValue = confidenceAssessment?.overall ?? confidence;

  return (
    <div className="flex h-full flex-col overflow-y-auto">
      {/* Header strip */}
      <div className="shrink-0 px-6 pt-5 pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            {intent && (
              <h3 className="text-[13px] font-semibold text-slate-700 dark:text-slate-200">
                {INTENT_LABELS[intent] ?? intent}
              </h3>
            )}
            {confValue != null && <ConfidenceBadge value={confValue} />}
          </div>
          {tableData && tableData.rows.length > 0 && (
            <span className="text-[10px] text-slate-400">
              {tableData.rows.length} {tableData.rows.length === 1 ? 'row' : 'rows'}
            </span>
          )}
        </div>

        {guardStatus && guardStatus !== 'ok' && (
          <div className="mt-2.5 flex items-center gap-2 rounded-lg border border-amber-200/60 bg-amber-50/50 px-3 py-2 text-[11px] text-amber-700 dark:border-amber-500/20 dark:bg-amber-900/20 dark:text-amber-400">
            <AlertTriangle size={12} className="shrink-0" />
            <span>Response may contain unverified claims — review with caution</span>
          </div>
        )}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-6 pb-6">
        <AnimatePresence mode="wait">
          <motion.div
            key={intent ?? 'default'}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="space-y-4"
          >
            <IntentRouter
              intent={intent}
              data={data}
              tableData={tableData}
              visualizations={visualizations}
              personaAnalyses={personaAnalyses}
              confidenceAssessment={confidenceAssessment}
            />
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  );
}

/* ── Intent router ── */

function IntentRouter({
  intent,
  data,
  tableData,
  visualizations,
  personaAnalyses,
  confidenceAssessment,
}: {
  intent: string | null;
  data: QueryResponse | null;
  tableData: TableData | null;
  visualizations: VisualizationSpec[] | null;
  personaAnalyses?: PersonaAnalysis[];
  confidenceAssessment?: { overall: number; by_dimension: Record<string, number> };
}) {
  const hasTable = Boolean(tableData && tableData.rows.length > 0);
  const hasViz = Boolean(visualizations && visualizations.length > 0);

  switch (intent) {
    case 'landscape':
      return (
        <>
          {hasTable && tableData && <DataTable tableData={tableData} />}
          {hasViz && <VisualizationGrid specs={visualizations!} />}
          <EvidenceSection data={data} />
        </>
      );

    case 'compare':
      return (
        <>
          {hasTable && tableData && <DataTable tableData={tableData} />}
          <EntitySection data={data} />
          <EvidenceSection data={data} />
        </>
      );

    case 'dossier':
      return (
        <>
          <EntitySection data={data} />
          <MetricsSection data={data} />
          {hasTable && tableData && <DataTable tableData={tableData} />}
          {hasViz && <VisualizationGrid specs={visualizations!} />}
          <EvidenceSection data={data} />
        </>
      );

    case 'pipeline':
      return (
        <>
          {hasTable && tableData && <DataTable tableData={tableData} />}
          {hasViz && <VisualizationGrid specs={visualizations!} />}
          <MetricsSection data={data} />
          <EvidenceSection data={data} />
        </>
      );

    case 'portfolio':
      return (
        <>
          <MetricsSection data={data} />
          <EntitySection data={data} />
          {hasTable && tableData && <DataTable tableData={tableData} />}
          {hasViz && <VisualizationGrid specs={visualizations!} />}
          <EvidenceSection data={data} />
        </>
      );

    default:
      return (
        <>
          {hasTable && tableData && <DataTable tableData={tableData} />}
          {hasViz && <VisualizationGrid specs={visualizations!} />}
          {personaAnalyses && personaAnalyses.length > 0 && (
            <PersonaSection
              analyses={personaAnalyses}
              evidence={data?.evidence}
              confidenceAssessment={confidenceAssessment}
            />
          )}
          <EntitySection data={data} />
          <MetricsSection data={data} />
          <EvidenceSection data={data} />
        </>
      );
  }
}

/* ── Shared sub-components ── */

function EmptyCanvas() {
  return (
    <div className="flex h-full flex-col items-center justify-center px-6 text-center">
      <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-xl bg-slate-100/60">
        <Layers size={20} className="text-slate-300" />
      </div>
      <p className="text-[13px] font-medium text-slate-400">
        Ask a question to see data here
      </p>
      <p className="mt-1 text-[11px] text-slate-300">
        Tables, charts, and entities will appear in this panel
      </p>
    </div>
  );
}

function SkeletonCards() {
  return (
    <div className="space-y-3">
      {[1, 2, 3].map((i) => (
        <div key={i} className="animate-pulse rounded-xl bg-white p-4">
          <div className="mb-3 h-3 w-1/3 rounded bg-slate-100" />
          <div className="space-y-2">
            <div className="h-2.5 w-full rounded bg-slate-100" />
            <div className="h-2.5 w-5/6 rounded bg-slate-100" />
            <div className="h-2.5 w-2/3 rounded bg-slate-100" />
          </div>
        </div>
      ))}
    </div>
  );
}

function ConfidenceBadge({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color = value > 0.7
    ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
    : value > 0.4
      ? 'bg-amber-50 text-amber-700 border-amber-200'
      : 'bg-rose-50 text-rose-700 border-rose-200';

  return (
    <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold ${color}`}>
      {pct}% confidence
    </span>
  );
}

/* ── DataTable (extracted from ChatMessage.tsx pattern) ── */

function exportCsv(columns: TableData['columns'], rows: TableData['rows'], title: string) {
  const header = columns.map((c) => `"${c.label.replace(/"/g, '""')}"`).join(',');
  const body = rows
    .map((row) =>
      columns
        .map((c) => {
          const val = row[c.key];
          if (val == null) return '';
          return `"${String(val).replace(/"/g, '""')}"`;
        })
        .join(','),
    )
    .join('\n');
  const csv = `${header}\n${body}`;
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
  const date = new Date().toISOString().slice(0, 10);
  const filename = `${title.replace(/[^a-zA-Z0-9_-]/g, '_')}-${date}.csv`;
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function DataTable({ tableData }: { tableData: TableData }) {
  const [sortCol, setSortCol] = useState<string | null>(null);
  const [sortAsc, setSortAsc] = useState(true);
  const [showAll, setShowAll] = useState(false);

  const handleSort = (key: string) => {
    if (sortCol === key) {
      setSortAsc(!sortAsc);
    } else {
      setSortCol(key);
      setSortAsc(true);
    }
  };

  const sortedRows = useMemo(() => {
    if (!sortCol) return tableData.rows;
    return [...tableData.rows].sort((a, b) => {
      const va = a[sortCol];
      const vb = b[sortCol];
      if (va == null && vb == null) return 0;
      if (va == null) return 1;
      if (vb == null) return -1;
      if (typeof va === 'number' && typeof vb === 'number') {
        return sortAsc ? va - vb : vb - va;
      }
      return sortAsc
        ? String(va).localeCompare(String(vb))
        : String(vb).localeCompare(String(va));
    });
  }, [tableData.rows, sortCol, sortAsc]);

  const displayRows = showAll ? sortedRows : sortedRows.slice(0, 15);

  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Table2 size={13} className="text-slate-400" />
          {tableData.title && (
            <span className="text-[12px] font-medium text-slate-700">{tableData.title}</span>
          )}
        </div>
        <button
          type="button"
          onClick={() => exportCsv(tableData.columns, sortedRows, tableData.title || 'export')}
          className="inline-flex items-center gap-1 rounded-md bg-slate-50 px-2.5 py-1 text-[10px] font-medium text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600"
          title="Download CSV"
        >
          <Download size={10} />
          CSV
        </button>
      </div>
      <div className="max-h-96 overflow-auto rounded-xl bg-white">
        <table className="min-w-full text-[12px]" style={{ tableLayout: 'auto' }}>
          <thead className="sticky top-0 z-10 bg-white">
            <tr className="border-b border-slate-100/60">
              {tableData.columns.map((col) => (
                <th
                  key={col.key}
                  onClick={() => handleSort(col.key)}
                  className={`cursor-pointer whitespace-nowrap px-3 py-1.5 text-left font-medium text-slate-500 hover:text-slate-700 select-none ${
                    col.type === 'number' ? 'text-right' : ''
                  }`}
                >
                  {col.label}
                  {sortCol === col.key && (
                    <span className="ml-0.5">{sortAsc ? '\u25B2' : '\u25BC'}</span>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {displayRows.map((row, i) => (
              <tr key={i} className="border-b border-slate-50 hover:bg-slate-50/40 transition-colors">
                {tableData.columns.map((col, ci) => (
                  <td
                    key={col.key}
                    title={row[col.key] != null ? String(row[col.key]) : undefined}
                    className={`px-3 py-1.5 whitespace-nowrap text-slate-600 ${
                      col.type === 'number' ? 'text-right tabular-nums' : ''
                    } ${ci === 0 ? 'font-medium text-slate-700' : ''}`}
                  >
                    {row[col.key] != null ? String(row[col.key]) : '-'}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {sortedRows.length > 15 && !showAll && (
        <button
          type="button"
          onClick={() => setShowAll(true)}
          className="mt-1.5 text-[10px] text-brand-dark hover:underline"
        >
          Show all {sortedRows.length} rows
        </button>
      )}
    </div>
  );
}

/* ── Visualizations ── */

const CHART_COLORS = ['#1f6cf2', '#22c55e', '#0ea5e9', '#f59e0b', '#8b5cf6', '#ef4444'];

function VisualizationGrid({ specs }: { specs: VisualizationSpec[] }) {
  const filtered = specs.filter((s) => s.data.some((d) => Number(d.value) > 0));
  if (filtered.length === 0) return null;

  return (
    <div className="grid grid-cols-1 gap-3">
      {filtered.map((viz) => (
        <VisualizationCard key={viz.id} spec={viz} />
      ))}
    </div>
  );
}

function VisualizationCard({ spec }: { spec: VisualizationSpec }) {
  return (
    <div className="rounded-xl bg-white p-4">
      <div className="mb-2 flex items-center gap-2">
        <BarChart3 size={13} className="text-slate-400" />
        <span className="text-[11px] font-medium text-slate-600">{spec.title}</span>
      </div>
      <div className="w-full" style={{ minHeight: 200, height: 'clamp(200px, 22vw, 280px)' }}>
        <ResponsiveContainer width="100%" height="100%">
          {spec.type === 'donut' ? (
            <PieChart>
              <Pie
                data={spec.data}
                dataKey="value"
                nameKey="label"
                innerRadius={45}
                outerRadius={72}
                paddingAngle={2}
                stroke="none"
              >
                {spec.data.map((entry, index) => (
                  <Cell key={`${entry.label}-${index}`} fill={CHART_COLORS[index % CHART_COLORS.length]} />
                ))}
              </Pie>
              <Tooltip
                formatter={(value: number) => [`${value.toLocaleString()} ${spec.value_unit ?? ''}`.trim(), '']}
              />
              <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: '11px', color: '#64748b' }} />
            </PieChart>
          ) : (
            <BarChart data={spec.data} margin={{ top: 6, right: 10, left: 0, bottom: 20 }}>
              <CartesianGrid vertical={false} strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="label" tick={{ fill: '#64748b', fontSize: 10 }} axisLine={false} tickLine={false} angle={-20} textAnchor="end" />
              <YAxis tick={{ fill: '#64748b', fontSize: 10 }} axisLine={false} tickLine={false} />
              <Tooltip
                formatter={(value: number) => [`${value.toLocaleString()} ${spec.value_unit ?? ''}`.trim(), '']}
                labelFormatter={(label: string) => `${label}`}
              />
              <Legend iconType="rect" iconSize={8} wrapperStyle={{ fontSize: '11px', color: '#64748b' }} formatter={() => spec.value_unit || 'Value'} />
              <Bar dataKey="value" radius={[6, 6, 0, 0]} fill="#1f6cf2" name={spec.value_unit || 'Value'} />
            </BarChart>
          )}
        </ResponsiveContainer>
      </div>
    </div>
  );
}

/* ── Entity section ── */

function EntitySection({ data }: { data: QueryResponse | null }) {
  const entities = data?.entity_focus;
  if (!entities || entities.length === 0) return null;

  const deduped = dedupeByLabel(entities).slice(0, 6);

  return (
    <div>
      <div className="mb-2 text-[11px] font-medium text-slate-400">Key Entities</div>
      <div className="grid grid-cols-1 gap-2 lg:grid-cols-2">
        {deduped.map((entity, i) => {
          const label = String(entity.title ?? entity.label ?? entity.entity_id ?? 'Unknown');
          const entityType = String(entity.entity_type ?? 'drug');
          const connections = entity.total_connections as number | undefined;
          const metadata = (entity.metadata ?? {}) as Record<string, unknown>;
          const topProps = Object.entries(metadata).slice(0, 4);

          return (
            <div key={i} className="rounded-xl bg-white px-4 py-3">
              <div className="flex items-center gap-2 mb-1.5">
                <span className={`h-2 w-2 rounded-full ${entityTypeColor(entityType)}`} />
                <span className="text-[12px] font-semibold text-slate-800 truncate">{label}</span>
                <span className="ml-auto text-[10px] text-slate-400 capitalize">{entityType.replace('_', ' ')}</span>
              </div>
              {topProps.length > 0 && (
                <div className="space-y-0.5">
                  {topProps.map(([k, v]) => (
                    <div key={k} className="flex items-baseline gap-2 text-[11px]">
                      <span className="text-slate-400 capitalize">{k.replace(/_/g, ' ')}:</span>
                      <span className="text-slate-600 truncate">{String(v ?? '-')}</span>
                    </div>
                  ))}
                </div>
              )}
              {connections != null && connections > 0 && (
                <div className="mt-1.5 text-[10px] text-slate-400">{connections} connections</div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function entityTypeColor(type: string): string {
  const map: Record<string, string> = {
    drug: 'bg-blue-500',
    company: 'bg-amber-500',
    trial: 'bg-teal-500',
    therapeutic_area: 'bg-rose-500',
    mechanism: 'bg-violet-500',
    literature: 'bg-green-500',
  };
  return map[type] ?? 'bg-slate-400';
}

/* ── Metrics section ── */

function MetricsSection({ data }: { data: QueryResponse | null }) {
  const metrics = data?.metrics_context;
  if (!metrics || Object.keys(metrics).length === 0) return null;

  const tiles = extractMetricTiles(metrics);
  if (tiles.length === 0) return null;

  return (
    <div>
      <div className="mb-2 text-[11px] font-medium text-slate-400">Metrics</div>
      <div className="grid grid-cols-2 gap-2 lg:grid-cols-3">
        {tiles.slice(0, 6).map((tile) => (
          <div key={tile.label} className="rounded-xl bg-white px-4 py-3 text-center">
            <div className="text-[16px] font-bold text-slate-800 tabular-nums">{tile.value}</div>
            <div className="mt-0.5 text-[10px] text-slate-400 leading-tight">{tile.label}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

interface MetricTile {
  label: string;
  value: string;
}

function extractMetricTiles(metricsContext: Record<string, unknown>): MetricTile[] {
  const tiles: MetricTile[] = [];
  const seen = new Set<string>();

  for (const [entityKey, metricsObj] of Object.entries(metricsContext)) {
    if (!metricsObj || typeof metricsObj !== 'object') continue;
    const group = metricsObj as Record<string, Record<string, unknown>>;

    for (const [metricType, metricData] of Object.entries(group)) {
      if (!metricData || typeof metricData !== 'object') continue;
      const entityName =
        String(metricData.drug_name ?? metricData.company_name ?? metricData.mechanism_name ?? entityKey).trim();

      const scorePairs: Array<[string, string]> = [];
      if (metricType === 'pipeline' && metricData.pipeline_score != null) {
        scorePairs.push([`${entityName} Pipeline`, String(metricData.pipeline_score)]);
      }
      if (metricType === 'success_rate' && metricData.success_rate != null) {
        scorePairs.push([`${entityName} Success`, `${Math.round(Number(metricData.success_rate) * 100)}%`]);
      }
      if (metricType === 'evidence' && metricData.total_articles != null) {
        scorePairs.push([`${entityName} Articles`, String(metricData.total_articles)]);
      }
      if (metricType === 'competitive' && metricData.trial_count != null) {
        scorePairs.push([`${entityName} Trials`, String(metricData.trial_count)]);
      }
      if (metricType === 'portfolio' && metricData.drug_count != null) {
        scorePairs.push([`${entityName} Drugs`, String(metricData.drug_count)]);
      }

      for (const [label, value] of scorePairs) {
        const key = label.toLowerCase();
        if (!seen.has(key)) {
          seen.add(key);
          tiles.push({ label, value });
        }
      }
    }
  }
  return tiles;
}

/* ── Evidence section ── */

function EvidenceSection({ data }: { data: QueryResponse | null }) {
  const [expanded, setExpanded] = useState(false);
  const evidence = data?.evidence;
  if (!evidence || evidence.length === 0) return null;

  const shown = expanded ? evidence.slice(0, 10) : evidence.slice(0, 3);

  return (
    <div>
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="mb-2 flex items-center gap-1.5 text-[11px] font-medium text-slate-400 transition-colors hover:text-slate-600"
      >
        {expanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        {evidence.length} evidence sources
      </button>
      <div className="space-y-1.5">
        {shown.map((ev, i) => (
          <EvidenceRow key={i} item={ev} index={i + 1} />
        ))}
        {!expanded && evidence.length > 3 && (
          <button
            type="button"
            onClick={() => setExpanded(true)}
            className="text-[10px] text-brand-dark hover:underline"
          >
            Show {evidence.length - 3} more
          </button>
        )}
      </div>
    </div>
  );
}

function EvidenceRow({ item, index }: { item: EvidenceItem; index: number }) {
  const preview = item.content.length > 160 ? item.content.slice(0, 157) + '...' : item.content;
  return (
    <div className="rounded-xl bg-white px-4 py-3">
      <div className="flex items-center gap-2 mb-1">
        <span className="text-[10px] font-semibold text-slate-400">[{index}]</span>
        <span className="text-[10px] font-medium text-slate-400 uppercase">{item.source}</span>
        <span className="text-[10px] text-slate-300">|</span>
        <span className="text-[10px] text-slate-400 capitalize">{item.entity_type.replace('_', ' ')}</span>
        <span className="ml-auto text-[10px] tabular-nums text-slate-400">{(item.relevance * 100).toFixed(0)}%</span>
      </div>
      <p className="text-[11px] leading-relaxed text-slate-600">{preview}</p>
    </div>
  );
}

/* ── Persona section ── */

function PersonaSection({
  analyses,
  evidence,
  confidenceAssessment,
}: {
  analyses: PersonaAnalysis[];
  evidence?: EvidenceItem[];
  confidenceAssessment?: { overall: number; by_dimension: Record<string, number> };
}) {
  return (
    <div>
      <div className="mb-2 text-[11px] font-medium text-slate-400">Team Evaluation</div>

      {confidenceAssessment && (
        <div className="mb-3 flex items-center gap-3 rounded-xl bg-white px-4 py-3">
          <span className="text-[11px] text-slate-500">Overall confidence</span>
          <div className="flex-1 h-1.5 rounded-full bg-slate-100 overflow-hidden">
            <div
              className="h-full rounded-full transition-all"
              style={{
                width: `${Math.round(confidenceAssessment.overall * 100)}%`,
                backgroundColor: confidenceAssessment.overall >= 0.7 ? '#22c55e' : confidenceAssessment.overall >= 0.4 ? '#f59e0b' : '#ef4444',
              }}
            />
          </div>
          <span className="text-[11px] font-semibold text-slate-700 tabular-nums">
            {Math.round(confidenceAssessment.overall * 100)}%
          </span>
        </div>
      )}

      <div className="space-y-2">
        {analyses.map((pa) => (
          <PersonaCard key={pa.persona} analysis={pa} evidence={evidence} />
        ))}
      </div>
    </div>
  );
}

function PersonaCard({ analysis, evidence }: { analysis: PersonaAnalysis; evidence?: EvidenceItem[] }) {
  const [expanded, setExpanded] = useState(false);
  const confidenceColor = analysis.confidence >= 0.7
    ? 'bg-green-500'
    : analysis.confidence >= 0.4
      ? 'bg-amber-500'
      : 'bg-red-500';

  return (
    <div className="rounded-xl bg-white px-4 py-3">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center gap-2 text-left"
      >
        {expanded ? <ChevronDown size={13} className="text-slate-400" /> : <ChevronRight size={13} className="text-slate-400" />}
        <span className="text-[12px] font-semibold text-slate-700">{analysis.display_name}</span>
        <div className="ml-auto flex items-center gap-1.5">
          <div className="h-1.5 w-8 rounded-full bg-slate-100 overflow-hidden">
            <div className={`h-full rounded-full ${confidenceColor}`} style={{ width: `${Math.round(analysis.confidence * 100)}%` }} />
          </div>
          <span className="text-[10px] tabular-nums text-slate-400">{Math.round(analysis.confidence * 100)}%</span>
        </div>
      </button>

      {analysis.key_findings.length > 0 && (
        <ul className="mt-1.5 ml-5 space-y-0.5">
          {analysis.key_findings.slice(0, 3).map((finding, i) => (
            <li key={i} className="text-[11px] text-slate-600 list-disc">{finding}</li>
          ))}
        </ul>
      )}

      {analysis.data_gaps.length > 0 && (
        <div className="mt-1.5 ml-5 flex flex-wrap gap-1">
          {analysis.data_gaps.map((gap, i) => (
            <span key={i} className="rounded-sm bg-amber-50 px-1.5 py-0.5 text-[10px] text-amber-700 border border-amber-200/50">
              {gap}
            </span>
          ))}
        </div>
      )}

      {expanded && (
        <div className="mt-2 ml-5 rounded-lg bg-slate-50/80 px-4 py-2.5 text-[11px] leading-relaxed text-slate-500">
          {analysis.analysis}
        </div>
      )}
    </div>
  );
}

/* ── Helpers ── */

function dedupeByLabel(entities: Record<string, unknown>[]): Record<string, unknown>[] {
  const seen = new Map<string, Record<string, unknown>>();
  for (const entity of entities) {
    const label = String(entity.title ?? entity.label ?? entity.entity_id ?? '').toLowerCase().trim();
    if (!seen.has(label)) {
      seen.set(label, entity);
    }
  }
  return [...seen.values()];
}
