import { useMemo, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronDown, ChevronRight, Download, Layers } from 'lucide-react';
import {
  Bar, BarChart, CartesianGrid, Cell, Legend, Pie, PieChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import type { TableData, VisualizationSpec, QueryResponse, EvidenceItem, PersonaAnalysis } from '../../api';
import { DataTable as SortableDataTable, type DataTableColumn } from '../ui/DataTable';

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
  onViewInGraph?: (entity: { id: string; type: string; label: string }) => void;
  onOpenLiterature?: (articleId: string) => void;
}

const INTENT_LABELS: Record<string, string> = {
  landscape: 'Competitive Landscape',
  compare: 'Comparison',
  dossier: 'Entity Profile',
  pipeline: 'Pipeline',
  portfolio: 'Portfolio',
  structured_query: 'Data Query',
  general: 'Analysis',
};

const CHART_COLORS = ['#1C6EF7', '#22C55E', '#0EA5E9', '#F59E0B', '#8B5CF6', '#EF4444'];

const CANVAS_TABS = [
  { key: 'summary', label: 'Summary' },
  { key: 'data', label: 'Data' },
  { key: 'entities', label: 'Entities' },
  { key: 'context', label: 'Context' },
] as const;

type CanvasTabKey = typeof CANVAS_TABS[number]['key'];

export default function CanvasPanel({
  intent,
  data,
  tableData,
  visualizations,
  confidence,
  loading,
  personaAnalyses,
  confidenceAssessment,
  onViewInGraph,
}: CanvasPanelProps) {
  const hasTable = Boolean(tableData && tableData.rows.length > 0);
  const hasViz = Boolean(visualizations && visualizations.length > 0);
  const hasEntities = Boolean(data?.entity_focus?.length);
  const hasEvidence = Boolean(data?.evidence?.length);
  const hasPersonas = Boolean(personaAnalyses?.length);
  const hasConfDimensions = Boolean(confidenceAssessment?.by_dimension && Object.keys(confidenceAssessment.by_dimension).length > 0);
  const hasContent = hasTable || hasViz || hasEntities || hasEvidence || hasPersonas;

  // Determine which tabs have content
  const visibleTabs = useMemo(() => {
    const tabHasContent: Record<CanvasTabKey, boolean> = {
      summary: hasContent, // Summary always shows if anything is available
      data: hasTable || hasViz,
      entities: hasEntities || hasEvidence,
      context: hasPersonas || hasConfDimensions || Boolean(confidenceAssessment),
    };
    return CANVAS_TABS.filter(t => tabHasContent[t.key]);
  }, [hasContent, hasTable, hasViz, hasEntities, hasEvidence, hasPersonas, hasConfDimensions, confidenceAssessment]);

  const [activeTab, setActiveTab] = useState<CanvasTabKey>('summary');

  // If the active tab is not visible, fall back to the first visible tab
  const currentTab = visibleTabs.some(t => t.key === activeTab)
    ? activeTab
    : visibleTabs[0]?.key ?? 'summary';

  if (loading) return <CanvasLoading />;

  if (!hasContent) {
    return (
      <div
        className="flex h-full flex-col items-center justify-center text-center"
        style={{ padding: '0 32px', background: 'var(--color-surface-2)' }}
      >
        <div
          className="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl"
          style={{ background: 'var(--color-surface-3)', color: 'var(--color-ink-4)' }}
        >
          <Layers size={20} />
        </div>
        <p style={{ fontSize: '13px', fontWeight: 500, color: 'var(--color-ink-3)' }}>
          Data Canvas
        </p>
        <p
          className="mt-1"
          style={{ fontSize: '12px', color: 'var(--color-ink-4)', maxWidth: '220px', lineHeight: 1.5 }}
        >
          Tables, charts, and entities will appear here as you explore.
        </p>
      </div>
    );
  }

  const confValue = confidenceAssessment?.overall ?? confidence;

  return (
    <div
      className="flex h-full flex-col"
      style={{ background: 'var(--color-surface-2)' }}
    >
      {/* Header */}
      <div
        className="shrink-0 flex items-center justify-between"
        style={{ padding: '16px 24px', borderBottom: '1px solid var(--color-line)', background: 'var(--color-surface)' }}
      >
        <div className="flex items-center gap-3" style={{ flex: 1 }}>
          {intent && (
            <span
              style={{
                fontSize: '13px',
                fontWeight: 600,
                color: 'var(--color-ink)',
              }}
            >
              {INTENT_LABELS[intent] ?? intent}
            </span>
          )}
          {confValue != null && (
            <span
              className="badge"
              style={{
                background: confValue > 0.7
                  ? 'var(--color-green-soft)'
                  : confValue > 0.4
                    ? 'var(--color-amber-soft)'
                    : 'var(--color-red-soft)',
                color: confValue > 0.7
                  ? 'var(--color-green)'
                  : confValue > 0.4
                    ? 'var(--color-amber)'
                    : 'var(--color-red)',
              }}
            >
              {Math.round(confValue * 100)}% confidence
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {tableData && tableData.rows.length > 0 && (
            <span style={{ fontSize: '11px', color: 'var(--color-ink-4)' }}>
              {tableData.rows.length} rows
            </span>
          )}
          {onViewInGraph && hasEntities && (data?.entity_focus as Record<string, unknown>[])?.length > 1 && (
            <button
              type="button"
              onClick={() => {
                const first = (data!.entity_focus as Record<string, unknown>[])[0];
                if (first?.entity_id) {
                  onViewInGraph({
                    id: String(first.entity_id),
                    type: String(first.entity_type ?? 'drug'),
                    label: String(first.title ?? first.label ?? ''),
                  });
                }
              }}
              style={{
                fontSize: '11px', fontWeight: 500, color: 'var(--color-accent)',
                background: 'var(--color-accent-soft)', border: 'none', cursor: 'pointer',
                padding: '4px 10px', borderRadius: '6px',
              }}
            >
              Visualise →
            </button>
          )}
        </div>
      </div>

      {/* Tab bar */}
      {visibleTabs.length > 1 && (
        <div
          className="shrink-0 flex items-center gap-1"
          style={{ padding: '12px 24px', borderBottom: '1px solid var(--color-line)', background: 'var(--color-surface)' }}
        >
          {visibleTabs.map(t => (
            <button
              key={t.key}
              type="button"
              onClick={() => setActiveTab(t.key)}
              className="nav-tab"
              style={{
                background: currentTab === t.key ? 'var(--color-surface-2)' : 'transparent',
                color: currentTab === t.key ? 'var(--color-ink)' : 'var(--color-ink-3)',
                fontWeight: currentTab === t.key ? 600 : 400,
              }}
            >
              {t.label}
            </button>
          ))}
        </div>
      )}

      {/* Tab content */}
      <div className="flex-1 overflow-y-auto" style={{ minHeight: 0 }}>
        <AnimatePresence mode="wait">
          <motion.div
            key={`${intent ?? 'default'}-${currentTab}`}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.2 }}
          >
            {currentTab === 'summary' && (
              <SummaryTab
                intent={intent}
                confValue={confValue}
                tableData={hasTable ? tableData! : null}
                visualizations={hasViz ? visualizations! : null}
                entities={hasEntities ? (data!.entity_focus ?? []) as Record<string, unknown>[] : null}
                onViewInGraph={onViewInGraph}
              />
            )}

            {currentTab === 'data' && (
              <DataTab
                tableData={hasTable ? tableData! : null}
                visualizations={hasViz ? visualizations! : null}
                onViewInGraph={onViewInGraph}
              />
            )}

            {currentTab === 'entities' && (
              <EntitiesTab
                entities={hasEntities ? (data!.entity_focus ?? []) as Record<string, unknown>[] : null}
                evidence={hasEvidence ? data!.evidence : null}
                onViewInGraph={onViewInGraph}
              />
            )}

            {currentTab === 'context' && (
              <ContextTab
                confidenceAssessment={confidenceAssessment}
                personaAnalyses={hasPersonas ? personaAnalyses! : null}
              />
            )}
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  );
}

/* ── Row click → entity navigation helper ── */
function makeRowClickHandler(
  onViewInGraph?: (entity: { id: string; type: string; label: string }) => void,
) {
  if (!onViewInGraph) return undefined;
  return (row: Record<string, unknown>) => {
    const id = row.entity_id ?? row.id;
    const type = row.entity_type ?? row.type ?? 'drug';
    const label = row.name ?? row.title ?? row.label ?? row.drug_name ?? row.company_name ?? '';
    if (id) {
      onViewInGraph({ id: String(id), type: String(type), label: String(label) });
    }
  };
}

/* ── Summary tab: intent + confidence + first 5 rows + first viz + first 3 entities ── */
function SummaryTab({
  intent,
  confValue,
  tableData,
  visualizations,
  entities,
  onViewInGraph,
}: {
  intent: string | null;
  confValue: number | null | undefined;
  tableData: TableData | null;
  visualizations: VisualizationSpec[] | null;
  entities: Record<string, unknown>[] | null;
  onViewInGraph?: (entity: { id: string; type: string; label: string }) => void;
}) {
  const summaryTable = tableData
    ? { ...tableData, rows: tableData.rows.slice(0, 5) }
    : null;
  const firstViz = visualizations?.find(v => v.data.some(d => Number(d.value) > 0)) ?? null;
  const topEntities = entities?.slice(0, 3) ?? null;

  return (
    <>
      {summaryTable && summaryTable.rows.length > 0 && (
        <Section title="Data">
          <DataTable tableData={summaryTable} onRowClick={makeRowClickHandler(onViewInGraph)} />
        </Section>
      )}
      {firstViz && (
        <Section title="Visualisations">
          <VizCard spec={firstViz} />
        </Section>
      )}
      {topEntities && topEntities.length > 0 && (
        <Section title="Key Entities">
          <EntityGrid entities={topEntities} onViewInGraph={onViewInGraph} />
        </Section>
      )}
    </>
  );
}

/* ── Data tab: full table + all visualizations + CSV export ── */
function DataTab({
  tableData,
  visualizations,
  onViewInGraph,
}: {
  tableData: TableData | null;
  visualizations: VisualizationSpec[] | null;
  onViewInGraph?: (entity: { id: string; type: string; label: string }) => void;
}) {
  return (
    <>
      {tableData && tableData.rows.length > 0 && (
        <Section title="Data">
          <DataTable tableData={tableData} onRowClick={makeRowClickHandler(onViewInGraph)} />
        </Section>
      )}
      {visualizations && visualizations.length > 0 && (
        <Section title="Visualisations">
          <div className="space-y-6">
            {visualizations.filter(v => v.data.some(d => Number(d.value) > 0)).map(spec => (
              <VizCard key={spec.id} spec={spec} />
            ))}
          </div>
        </Section>
      )}
    </>
  );
}

/* ── Entities tab: all entities with expanded properties + evidence list ── */
function EntitiesTab({
  entities,
  evidence,
  onViewInGraph,
}: {
  entities: Record<string, unknown>[] | null;
  evidence: EvidenceItem[] | null;
  onViewInGraph?: (entity: { id: string; type: string; label: string }) => void;
}) {
  return (
    <>
      {entities && entities.length > 0 && (
        <Section title="Key Entities">
          <EntityGrid entities={entities} onViewInGraph={onViewInGraph} />
        </Section>
      )}
      {evidence && evidence.length > 0 && (
        <EvidenceSection evidence={evidence} />
      )}
    </>
  );
}

/* ── Context tab: provenance + confidence by dimension + personas ── */
function ContextTab({
  confidenceAssessment,
  personaAnalyses,
}: {
  confidenceAssessment?: { overall: number; by_dimension: Record<string, number> };
  personaAnalyses: PersonaAnalysis[] | null;
}) {
  const hasDimensions = Boolean(
    confidenceAssessment?.by_dimension && Object.keys(confidenceAssessment.by_dimension).length > 0,
  );

  return (
    <>
      {confidenceAssessment && (
        <Section title="Provenance">
          <div
            className="rounded-xl"
            style={{ padding: '16px', background: 'var(--color-surface)', border: '1px solid var(--color-line)' }}
          >
            <div className="flex items-center gap-3 mb-3">
              <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--color-ink)' }}>
                Overall Confidence
              </span>
              <span
                className="badge"
                style={{
                  background: confidenceAssessment.overall >= 0.7
                    ? 'var(--color-green-soft)'
                    : confidenceAssessment.overall >= 0.4
                      ? 'var(--color-amber-soft)'
                      : 'var(--color-red-soft)',
                  color: confidenceAssessment.overall >= 0.7
                    ? 'var(--color-green)'
                    : confidenceAssessment.overall >= 0.4
                      ? 'var(--color-amber)'
                      : 'var(--color-red)',
                }}
              >
                {Math.round(confidenceAssessment.overall * 100)}%
              </span>
            </div>
            {hasDimensions && (
              <div className="space-y-2">
                {Object.entries(confidenceAssessment.by_dimension).map(([dim, val]) => (
                  <div key={dim} className="flex items-center gap-3">
                    <span
                      style={{
                        fontSize: '12px',
                        color: 'var(--color-ink-3)',
                        minWidth: '90px',
                        maxWidth: '35%',
                        textTransform: 'capitalize',
                      }}
                    >
                      {dim.replace(/_/g, ' ')}
                    </span>
                    <div
                      className="flex-1 h-1.5 rounded-full overflow-hidden"
                      style={{ background: 'var(--color-surface-3)' }}
                    >
                      <div
                        className="h-full rounded-full transition-all"
                        style={{
                          width: `${Math.round(val * 100)}%`,
                          background: val >= 0.7
                            ? 'var(--color-green)'
                            : val >= 0.4
                              ? 'var(--color-amber)'
                              : 'var(--color-red)',
                        }}
                      />
                    </div>
                    <span style={{ fontSize: '11px', color: 'var(--color-ink-4)', width: '32px', textAlign: 'right' }}>
                      {Math.round(val * 100)}%
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </Section>
      )}

      {personaAnalyses && personaAnalyses.length > 0 && (
        <Section title="Team Evaluation">
          <div className="space-y-1">
            {personaAnalyses.map(pa => <PersonaRow key={pa.persona} analysis={pa} />)}
          </div>
        </Section>
      )}
    </>
  );
}

/* ── Shared section wrapper ── */
function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div
      className="canvas-section"
      style={{ padding: '24px' }}
    >
      <div
        className="text-label mb-4"
      >
        {title}
      </div>
      {children}
    </div>
  );
}

/* ── Loading skeleton ── */
function CanvasLoading() {
  return (
    <div
      className="flex h-full flex-col"
      style={{ background: 'var(--color-surface-2)', padding: '24px', gap: '16px' }}
    >
      {[80, 60, 100, 45].map((w, i) => (
        <div
          key={i}
          className="rounded-xl"
          style={{
            height: '12px',
            width: `${w}%`,
            background: 'var(--color-surface-3)',
            animation: 'pulse-dot 1.5s ease-in-out infinite',
            animationDelay: `${i * 0.1}s`,
          }}
        />
      ))}
    </div>
  );
}

/* ── DataTable ── */
function exportCsv(columns: TableData['columns'], rows: TableData['rows'], title: string) {
  const header = columns.map(c => `"${c.label.replace(/"/g, '""')}"`).join(',');
  const body = rows.map(row =>
    columns.map(c => {
      const val = row[c.key];
      return val == null ? '' : `"${String(val).replace(/"/g, '""')}"`;
    }).join(',')
  ).join('\n');
  const blob = new Blob([`${header}\n${body}`], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${title.replace(/[^a-zA-Z0-9_-]/g, '_')}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

function DataTable({
  tableData,
  onRowClick,
}: {
  tableData: TableData;
  onRowClick?: (row: Record<string, unknown>) => void;
}) {
  const [showAll, setShowAll] = useState(false);
  const display = showAll ? tableData.rows : tableData.rows.slice(0, 12);

  const columns: DataTableColumn[] = tableData.columns.map((col) => ({
    key: col.key,
    label: col.label,
    sortable: true,
    align: col.type === 'number' ? 'right' as const : 'left' as const,
  }));

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        {tableData.title && (
          <span style={{ fontSize: '13px', fontWeight: 500, color: 'var(--color-ink-2)' }}>
            {tableData.title}
          </span>
        )}
        <button
          type="button"
          onClick={() => exportCsv(tableData.columns, tableData.rows, tableData.title || 'data')}
          className="btn btn-ghost btn-xs flex items-center gap-1"
        >
          <Download size={11} />
          CSV
        </button>
      </div>

      <SortableDataTable
        columns={columns}
        rows={display}
        onRowClick={onRowClick}
        maxHeight={showAll ? '600px' : '320px'}
      />

      {tableData.rows.length > 12 && !showAll && (
        <button
          type="button"
          onClick={() => setShowAll(true)}
          className="mt-2"
          style={{ fontSize: '12px', color: 'var(--color-accent)', background: 'none', border: 'none', cursor: 'pointer' }}
        >
          Show all {tableData.rows.length} rows
        </button>
      )}
    </div>
  );
}

/* ── Visualisation card ── */
function VizCard({ spec }: { spec: VisualizationSpec }) {
  return (
    <div>
      <p
        className="mb-3"
        style={{ fontSize: '13px', fontWeight: 500, color: 'var(--color-ink-2)' }}
      >
        {spec.title}
      </p>
      <div style={{ height: '220px' }}>
        <ResponsiveContainer width="100%" height="100%">
          {spec.type === 'donut' ? (
            <PieChart>
              <Pie
                data={spec.data}
                dataKey="value"
                nameKey="label"
                innerRadius={50}
                outerRadius={80}
                paddingAngle={2}
                stroke="none"
              >
                {spec.data.map((_, index) => (
                  <Cell key={index} fill={CHART_COLORS[index % CHART_COLORS.length]} />
                ))}
              </Pie>
              <Tooltip formatter={(v: number) => [`${v.toLocaleString()} ${spec.value_unit ?? ''}`.trim(), '']} />
              <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: '11px' }} />
            </PieChart>
          ) : (
            <BarChart data={spec.data} margin={{ top: 4, right: 8, left: 0, bottom: 16 }}>
              <CartesianGrid vertical={false} strokeDasharray="3 3" stroke="var(--color-line)" />
              <XAxis
                dataKey="label"
                tick={{ fill: 'var(--color-ink-4)', fontSize: 10 }}
                axisLine={false}
                tickLine={false}
                angle={-20}
                textAnchor="end"
              />
              <YAxis
                tick={{ fill: 'var(--color-ink-4)', fontSize: 10 }}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip formatter={(v: number) => [`${v.toLocaleString()} ${spec.value_unit ?? ''}`.trim(), '']} />
              <Bar dataKey="value" radius={[4, 4, 0, 0]} fill="var(--color-accent)" />
            </BarChart>
          )}
        </ResponsiveContainer>
      </div>
    </div>
  );
}

/* ── Entity grid ── */
const ENTITY_DOTS: Record<string, string> = {
  drug: 'var(--color-drug)',
  company: 'var(--color-company)',
  trial: 'var(--color-trial)',
  therapeutic_area: 'var(--color-ta)',
  mechanism: 'var(--color-mechanism)',
  literature: 'var(--color-literature)',
};

function EntityGrid({ entities, onViewInGraph }: { entities: Record<string, unknown>[]; onViewInGraph?: (entity: { id: string; type: string; label: string }) => void }) {
  return (
    <div className="grid grid-cols-1 gap-2">
      {entities.map((e, i) => {
        const label = String(e.title ?? e.label ?? e.entity_id ?? 'Unknown');
        const type = String(e.entity_type ?? 'drug');
        const conns = e.total_connections as number | undefined;
        return (
          <div
            key={i}
            className="rounded-xl"
            style={{
              padding: '16px',
              background: 'var(--color-surface)',
              border: '1px solid var(--color-line)',
            }}
          >
            <div className="flex items-center gap-2.5">
              <span
                className="h-2 w-2 rounded-full shrink-0"
                style={{ background: ENTITY_DOTS[type] ?? 'var(--color-ink-4)' }}
              />
              <span
                className="truncate"
                style={{ fontSize: '13px', fontWeight: 600, color: 'var(--color-ink)' }}
              >
                {label}
              </span>
              <span
                className="ml-auto shrink-0"
                style={{ fontSize: '11px', color: 'var(--color-ink-4)', textTransform: 'capitalize' }}
              >
                {type.replace('_', ' ')}
              </span>
            </div>
            <div className="mt-2 flex items-center gap-2" style={{ paddingLeft: '16px' }}>
              {onViewInGraph && e.entity_id && (
                <button
                  type="button"
                  onClick={() => onViewInGraph({ id: String(e.entity_id), type, label })}
                  style={{
                    fontSize: '11px', color: 'var(--color-accent)', background: 'none',
                    border: 'none', cursor: 'pointer', padding: 0, fontWeight: 500,
                  }}
                >
                  View in Graph →
                </button>
              )}
            </div>
            {conns != null && (
              <div
                className="mt-1"
                style={{ paddingLeft: '16px', fontSize: '11px', color: 'var(--color-ink-4)' }}
              >
                {conns} connections
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

/* ── Evidence section ── */
function EvidenceSection({ evidence }: { evidence: EvidenceItem[] }) {
  const [open, setOpen] = useState(false);
  const shown = open ? evidence.slice(0, 8) : evidence.slice(0, 2);

  return (
    <div
      className="canvas-section"
      style={{ padding: '24px' }}
    >
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className="flex items-center gap-2 mb-3"
        style={{
          background: 'none',
          border: 'none',
          cursor: 'pointer',
          color: 'var(--color-ink-3)',
          fontSize: '11px',
          fontWeight: 600,
          letterSpacing: '0.08em',
          textTransform: 'uppercase',
        }}
      >
        {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        {evidence.length} Evidence Sources
      </button>
      <div className="space-y-2">
        {shown.map((ev, i) => (
          <div
            key={i}
            className="rounded-xl"
            style={{
              padding: '12px',
              background: 'var(--color-surface)',
              border: '1px solid var(--color-line)',
              fontSize: '12px',
            }}
          >
            <div className="flex items-center gap-2 mb-1">
              <span
                className="badge badge-neutral"
                style={{ fontSize: '10px' }}
              >
                {ev.source}
              </span>
              <span style={{ color: 'var(--color-ink-4)', fontSize: '10px', textTransform: 'capitalize' }}>
                {ev.entity_type.replace('_', ' ')}
              </span>
              <span
                className="ml-auto"
                style={{ fontSize: '10px', color: 'var(--color-ink-4)' }}
              >
                {(ev.relevance * 100).toFixed(0)}%
              </span>
            </div>
            <p
              className="line-clamp-2"
              style={{ color: 'var(--color-ink-3)', lineHeight: 1.5 }}
            >
              {ev.content}
            </p>
          </div>
        ))}
      </div>
      {evidence.length > 2 && (
        <button
          type="button"
          onClick={() => setOpen(o => !o)}
          className="mt-2"
          style={{ fontSize: '12px', color: 'var(--color-accent)', background: 'none', border: 'none', cursor: 'pointer' }}
        >
          {open ? 'Show less' : `Show ${evidence.length - 2} more`}
        </button>
      )}
    </div>
  );
}

/* ── Persona row ── */
function PersonaRow({ analysis }: { analysis: PersonaAnalysis }) {
  const [open, setOpen] = useState(false);
  const conf = Math.round(analysis.confidence * 100);
  const confColor = conf >= 70 ? 'var(--color-green)' : conf >= 40 ? 'var(--color-amber)' : 'var(--color-red)';

  return (
    <div
      className="rounded-xl overflow-hidden"
      style={{ border: '1px solid var(--color-line)' }}
    >
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className="flex w-full items-center gap-3"
        style={{
          padding: '12px 16px',
          background: 'var(--color-surface)',
          cursor: 'pointer',
          border: 'none',
        }}
      >
        {open ? <ChevronDown size={13} style={{ color: 'var(--color-ink-4)' }} /> : <ChevronRight size={13} style={{ color: 'var(--color-ink-4)' }} />}
        <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--color-ink)', flex: 1, textAlign: 'left' }}>
          {analysis.display_name}
        </span>
        <div className="flex items-center gap-2">
          <div
            className="rounded-full overflow-hidden"
            style={{ width: '48px', height: '4px', background: 'var(--color-surface-3)' }}
          >
            <div style={{ width: `${conf}%`, height: '100%', background: confColor, borderRadius: '999px' }} />
          </div>
          <span style={{ fontSize: '11px', color: 'var(--color-ink-3)', fontWeight: 500 }}>{conf}%</span>
        </div>
      </button>

      {open && (
        <div
          style={{ padding: '0 16px 16px', background: 'var(--color-surface)', borderTop: '1px solid var(--color-line)' }}
        >
          <ul className="mt-3 space-y-1">
            {analysis.key_findings.slice(0, 3).map((f, i) => (
              <li
                key={i}
                className="flex items-start gap-2"
                style={{ fontSize: '12px', color: 'var(--color-ink-3)', lineHeight: 1.5 }}
              >
                <span style={{ marginTop: '2px', color: 'var(--color-accent)' }}>·</span>
                {f}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
