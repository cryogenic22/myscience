import { motion } from 'framer-motion';
import { ChevronDown, ChevronRight, ExternalLink, Download } from 'lucide-react';
import { useMemo, useRef, useState } from 'react';
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
import type { QueryResponse, EvidenceItem, VisualizationSpec, TableData, PersonaAnalysis } from '../api';
import { api } from '../api';
import EntityCard from './EntityCard';
import MetricCard from './MetricCard';
import EvidenceCard from './EvidenceCard';
import KnowledgeGraph from './KnowledgeGraph';

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  data?: QueryResponse;
  report?: string;
  webResults?: Array<{
    title: string;
    url: string;
    snippet: string;
    source: string;
  }>;
  reportMeta?: {
    web_enabled: boolean;
    generated_at: string;
  };
  visualizations?: VisualizationSpec[];
  tableData?: TableData;
  personaAnalyses?: PersonaAnalysis[];
  confidenceAssessment?: { overall: number; by_dimension: Record<string, number> };
  loading?: boolean;
  /** Stashed SQL from the agent response, used for conversation context in follow-ups */
  _sqlContext?: string;
  followupSuggestions?: string[];
}

interface Props {
  message: Message;
  onEntityClick?: (entityId: string, entityType: string, label?: string) => void;
  onFollowUp?: (question: string) => void;
}

/** Citation tooltip that shows evidence source on hover */
function CitationRef({ index, evidence }: { index: number; evidence?: EvidenceItem[] }) {
  const [show, setShow] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);
  const timeoutRef = useRef<number>(0);

  const item = evidence?.[index - 1]; // citations are 1-based

  const handleEnter = () => {
    clearTimeout(timeoutRef.current);
    setShow(true);
  };
  const handleLeave = () => {
    timeoutRef.current = window.setTimeout(() => setShow(false), 200);
  };

  if (!item) {
    return <sup className="text-[10px] text-slate-400 font-medium">[{index}]</sup>;
  }

  const sourceApi = item.provenance?.source_api as string | undefined;
  const sourceUrl = item.provenance?.source_url as string | undefined;
  const contentPreview = item.content.length > 120 ? item.content.slice(0, 118) + '..' : item.content;

  return (
    <span className="relative inline-block" ref={ref}>
      <sup
        className="text-[10px] font-semibold text-brand-dark cursor-pointer hover:text-brand transition-colors px-px"
        onMouseEnter={handleEnter}
        onMouseLeave={handleLeave}
        onClick={() => setShow(!show)}
      >
        [{index}]
      </sup>
      {show && (
        <div
          className="absolute bottom-full left-1/2 z-50 mb-2 w-72 -translate-x-1/2 rounded-md border border-slate-200 bg-white text-left shadow-lg"
          style={{ padding: '14px' }}
          onMouseEnter={handleEnter}
          onMouseLeave={handleLeave}
        >
          <div className="flex items-center gap-2 mb-1.5">
            <span className="text-[10px] font-medium text-slate-400 uppercase">{item.source}</span>
            <span className="text-[10px] text-slate-300">|</span>
            <span className="text-[10px] text-slate-400 capitalize">{item.entity_type.replace('_', ' ')}</span>
            <span className="ml-auto text-[10px] font-medium text-slate-400">{(item.relevance * 100).toFixed(0)}%</span>
          </div>
          <p className="text-[11px] text-slate-600 leading-relaxed">{contentPreview}</p>
          {(sourceApi || sourceUrl) && (
            <div className="mt-2 flex items-center gap-1.5 rounded-md border border-slate-200 bg-white" style={{ padding: '6px 8px' }}>
              <ExternalLink size={10} className="text-slate-400" />
              {sourceUrl ? (
                <a href={sourceUrl} target="_blank" rel="noopener noreferrer" className="text-[10px] text-brand-dark hover:underline truncate">
                  {sourceApi || sourceUrl}
                </a>
              ) : (
                <span className="text-[10px] text-slate-400">{sourceApi}</span>
              )}
            </div>
          )}
          {/* Arrow */}
          <div className="absolute top-full left-1/2 -mt-1 h-2 w-2 -translate-x-1/2 rotate-45 bg-white" />
        </div>
      )}
    </span>
  );
}

/** Render markdown-like text with inline citation support: **bold**, *italic*, [N] citations, and paragraph breaks. */
function RichText({ text, evidence }: { text: string; evidence?: EvidenceItem[] }) {
  const paragraphs = text.split(/\n{2,}/);

  return (
    <>
      {paragraphs.map((para, pi) => (
        <p key={pi} className={pi > 0 ? 'mt-2.5' : ''}>
          {para.split(/(\*\*[^*]+\*\*|\*[^*]+\*|\[\d+\])/).map((segment, si) => {
            if (segment.startsWith('**') && segment.endsWith('**')) {
              return <strong key={si} className="font-semibold text-slate-800">{segment.slice(2, -2)}</strong>;
            }
            if (segment.startsWith('*') && segment.endsWith('*') && !segment.startsWith('**')) {
              return <em key={si}>{segment.slice(1, -1)}</em>;
            }
            // Citation marker [N]
            const citationMatch = segment.match(/^\[(\d+)\]$/);
            if (citationMatch) {
              const idx = parseInt(citationMatch[1], 10);
              return <CitationRef key={si} index={idx} evidence={evidence} />;
            }
            return segment.split('\n').map((line, li) => (
              <span key={`${si}-${li}`}>
                {li > 0 && <br />}
                {line}
              </span>
            ));
          })}
        </p>
      ))}
    </>
  );
}

export default function ChatMessage({ message, onEntityClick, onFollowUp }: Props) {
  const isUser = message.role === 'user';

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="flex justify-center"
    >
      <div className="w-full max-w-[90%]">
        {isUser ? (
          <div className="ml-auto max-w-[82%] rounded-md bg-slate-900 text-[13px] text-white shadow-sm" style={{ padding: '12px 16px' }}>
            {message.content}
          </div>
        ) : (
          <div className="mr-auto max-w-[92%] space-y-3">
            {message.loading ? (
              <LoadingIndicator />
            ) : (
              <>
                {/* Narrative text - tighter font, relaxed leading, with inline citations */}
                <div className="text-[14px] leading-relaxed text-slate-700" style={{ padding: '0 4px' }}>
                  <RichText text={message.content} evidence={message.data?.evidence} />
                </div>

                {/* Rich data cards */}
                {(message.data || message.report || (message.visualizations?.length ?? 0) > 0 || message.tableData || message.personaAnalyses) && (
                  <ResponseCards
                    data={message.data}
                    report={message.report}
                    reportMeta={message.reportMeta}
                    webResults={message.webResults}
                    visualizations={message.visualizations}
                    tableData={message.tableData}
                    personaAnalyses={message.personaAnalyses}
                    confidenceAssessment={message.confidenceAssessment}
                    onEntityClick={onEntityClick}
                  />
                )}

                {/* Follow-up suggestions */}
                {onFollowUp && message.followupSuggestions && message.followupSuggestions.length > 0 && (
                  <div className="flex flex-wrap gap-2" style={{ paddingTop: '4px' }}>
                    {message.followupSuggestions.map((q) => (
                      <button
                        key={q}
                        type="button"
                        onClick={() => onFollowUp(q)}
                        className="rounded-md border border-slate-200 bg-white text-[11px] text-slate-600 transition-colors hover:border-slate-300 hover:bg-slate-50 hover:text-slate-900"
                        style={{ padding: '6px 12px' }}
                      >
                        {q}
                      </button>
                    ))}
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </div>
    </motion.div>
  );
}

function LoadingIndicator() {
  return (
    <div className="rounded-md border border-slate-200/70 bg-white/78" style={{ padding: '16px' }}>
      <div className="flex items-center gap-3">
        <div className="flex gap-1">
          <div className="h-1.5 w-1.5 rounded-full bg-brand animate-bounce" style={{ animationDelay: '0ms' }} />
          <div className="h-1.5 w-1.5 rounded-full bg-brand animate-bounce" style={{ animationDelay: '150ms' }} />
          <div className="h-1.5 w-1.5 rounded-full bg-brand animate-bounce" style={{ animationDelay: '300ms' }} />
        </div>
        <span className="text-xs text-slate-400">Analyzing knowledge graph...</span>
      </div>
    </div>
  );
}

function ResponseCards({
  data,
  report,
  reportMeta,
  webResults,
  visualizations,
  tableData,
  personaAnalyses,
  confidenceAssessment,
  onEntityClick,
}: {
  data?: QueryResponse;
  report?: string;
  reportMeta?: {
    web_enabled: boolean;
    generated_at: string;
  };
  webResults?: Array<{
    title: string;
    url: string;
    snippet: string;
    source: string;
  }>;
  visualizations?: VisualizationSpec[];
  tableData?: TableData;
  personaAnalyses?: PersonaAnalysis[];
  confidenceAssessment?: { overall: number; by_dimension: Record<string, number> };
  onEntityClick?: (id: string, type: string, label?: string) => void;
}) {
  const [showEvidence, setShowEvidence] = useState(() => Boolean(personaAnalyses && personaAnalyses.length > 0));
  const [showAllEvidence, setShowAllEvidence] = useState(false);
  const [showGraph, setShowGraph] = useState(false);
  const [showReport, setShowReport] = useState(true);

  const hasTableData = Boolean(tableData && tableData.rows.length > 0);
  const hasPersonaAnalyses = Boolean(personaAnalyses && personaAnalyses.length > 0);
  const hasGraph = Boolean(data?.graph_context
    && Array.isArray(data.graph_context.nodes)
    && data.graph_context.nodes.length > 0);
  const hasMetrics = Boolean(data?.metrics_context && Object.keys(data.metrics_context).length > 0);
  const hasEntities = Boolean(data?.entity_focus && data.entity_focus.length > 0);
  const hasEvidence = Boolean(data?.evidence && data.evidence.length > 0);
  const hasVisualizations = Boolean(visualizations && visualizations.length > 0);
  const hasReport = Boolean(report && report.trim().length > 0);
  const shouldOpenGraphByDefault = useMemo(() => shouldPreferGraphView(data), [data]);

  const dedupedEntities = useMemo(() => dedupeEntityFocus(data?.entity_focus ?? []).slice(0, 4), [data?.entity_focus]);
  const dedupedMetricRows = useMemo(() => dedupeMetricsContext(data?.metrics_context ?? {}).slice(0, 6), [data?.metrics_context]);
  const reportTitle = useMemo(() => {
    if (!report) return 'deep-research-report';
    const first = report.split('\n').find((line) => line.trim().length > 0) ?? 'deep-research-report';
    return first.replace(/^#+\s*/, '').slice(0, 80) || 'deep-research-report';
  }, [report]);

  const downloadReport = async (format: 'md' | 'txt' | 'json') => {
    if (!report) return;
    try {
      const { blob, filename } = await api.exportReport(report, reportTitle, format);
      downloadBlob(blob, filename);
      return;
    } catch {
      const fallbackContent = format === 'md' ? `# ${reportTitle}\n\n${report}` : report;
      const mime = format === 'json' ? 'application/json' : 'text/plain;charset=utf-8';
      const blob = new Blob([fallbackContent], { type: mime });
      downloadBlob(blob, `${reportTitle}.${format}`);
    }
  };

  // Evidence source summary for collapsed view
  const evidenceSummary = useMemo(() => {
    if (!data?.evidence?.length) return '';
    const bySource: Record<string, number> = {};
    for (const ev of data.evidence) {
      const src = ev.source || 'other';
      bySource[src] = (bySource[src] || 0) + 1;
    }
    const parts = Object.entries(bySource).map(([k, v]) => `${k}: ${v}`);
    return parts.join(', ');
  }, [data?.evidence]);

  return (
    <div className="space-y-1">
      {/* ── 1. Data Table (most direct answer) ── */}
      {hasTableData && tableData && <DataTable tableData={tableData} />}

      {/* ── 2. Charts (always visible, no collapse wrapper) ── */}
      {hasVisualizations && (
        <div className="grid grid-cols-1 gap-3" style={{ paddingTop: '8px' }}>
          {(visualizations ?? []).map((viz) => (
            <VisualizationCard key={viz.id} spec={viz} />
          ))}
        </div>
      )}

      {/* ── 3. Entities + Metrics (combined row) ── */}
      {(hasEntities || hasMetrics) && (
        <div className="border-t border-slate-100 mt-2" style={{ paddingTop: '12px' }}>
          <div className="mb-2 text-[11px] font-medium text-slate-400">Key Entities & Metrics</div>
          <div className="grid grid-cols-1 gap-2 lg:grid-cols-2">
            {hasEntities && (
              <div className="space-y-2">
                {dedupedEntities.map((ef: Record<string, unknown>, i: number) => (
                  <EntityCard
                    key={i}
                    entityType={String(ef.entity_type ?? 'drug')}
                    label={String(ef.title ?? ef.label ?? ef.entity_id ?? 'Unknown')}
                    properties={ef.metadata as Record<string, unknown> ?? {}}
                    connections={ef.total_connections as number | undefined}
                    onClick={onEntityClick ? () => onEntityClick(String(ef.entity_id), String(ef.entity_type), String(ef.title ?? ef.label ?? '')) : undefined}
                  />
                ))}
              </div>
            )}
            {hasMetrics && (
              <div className="space-y-2">
                {dedupedMetricRows.map((row) => (
                  <MetricCard
                    key={row.id}
                    type={row.type}
                    data={row.data}
                    entityName={row.entityName}
                  />
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── 4. Knowledge Graph (collapsible) ── */}
      {hasGraph && data && (
        <div className="border-t border-slate-100 mt-2" style={{ paddingTop: '12px' }}>
          <button
            onClick={() => setShowGraph(!showGraph)}
            className="mb-2 flex items-center gap-1.5 text-[11px] font-medium text-slate-400 transition-colors hover:text-slate-600"
          >
            {showGraph ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
            Knowledge Graph ({data.graph_context.nodes.length} nodes, {data.graph_context.edges.length} edges)
            {shouldOpenGraphByDefault && (
              <span className="ml-1 text-[10px] uppercase tracking-wide text-slate-300">recommended</span>
            )}
          </button>
          {showGraph && (
            <KnowledgeGraph
              nodes={data.graph_context.nodes}
              edges={data.graph_context.edges}
              centerEntityId={data.entity_focus?.[0]?.entity_id as string | undefined}
              compact
            />
          )}
        </div>
      )}

      {/* ── 5. Evidence (collapsed by default, compact summary) ── */}
      {hasEvidence && data && (
        <div className="border-t border-slate-100 mt-2" style={{ paddingTop: '12px' }}>
          <button
            onClick={() => setShowEvidence(!showEvidence)}
            className="mb-2 flex items-center gap-1.5 text-[11px] font-medium text-slate-400 transition-colors hover:text-slate-600"
          >
            {showEvidence ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
            <span>Based on {data.evidence.length} evidence sources</span>
            {evidenceSummary && (
              <span className="text-[10px] text-slate-300">({evidenceSummary})</span>
            )}
          </button>
          {showEvidence && (
            <div className="max-h-[min(24rem,45vh)] space-y-1.5 overflow-y-auto">
              {data.evidence.slice(0, 5).map((ev, i) => (
                <EvidenceCard
                  key={i}
                  index={i + 1}
                  source={ev.source}
                  entityType={ev.entity_type}
                  content={ev.content}
                  relevance={ev.relevance}
                  provenance={ev.provenance}
                />
              ))}
              {data.evidence.length > 5 && !showAllEvidence && (
                <button
                  type="button"
                  onClick={() => setShowAllEvidence(true)}
                  className="text-[11px] text-brand-dark hover:underline"
                >
                  Show {data.evidence.length - 5} more sources
                </button>
              )}
              {showAllEvidence && data.evidence.slice(5, 10).map((ev, i) => (
                <EvidenceCard
                  key={i + 5}
                  index={i + 6}
                  source={ev.source}
                  entityType={ev.entity_type}
                  content={ev.content}
                  relevance={ev.relevance}
                  provenance={ev.provenance}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── 6. Deep Research Brief (collapsible, keeps border) ── */}
      {hasReport && (
        <div className="border-t border-slate-100 mt-2" style={{ paddingTop: '12px' }}>
          <button
            onClick={() => setShowReport(!showReport)}
            className="mb-2 flex w-full items-center gap-1.5 text-left text-[11px] font-medium text-slate-400 transition-colors hover:text-slate-600"
          >
            {showReport ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
            Deep Research Brief
            {reportMeta?.generated_at && (
              <span className="ml-auto text-[10px] text-slate-300">
                {new Date(reportMeta.generated_at).toLocaleString()}
              </span>
            )}
          </button>
          {showReport && (
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => void downloadReport('md')}
                  className="inline-flex items-center gap-1 rounded-md border border-slate-200 bg-white text-[10px] font-medium text-slate-600 transition-colors hover:bg-slate-50" style={{ padding: '4px 10px' }}
                >
                  <Download size={10} />
                  Markdown
                </button>
                <button
                  type="button"
                  onClick={() => void downloadReport('txt')}
                  className="inline-flex items-center gap-1 rounded-md border border-slate-200 bg-white text-[10px] font-medium text-slate-600 transition-colors hover:bg-slate-50" style={{ padding: '4px 10px' }}
                >
                  <Download size={10} />
                  Text
                </button>
              </div>
              <div className="max-h-[min(28rem,50vh)] overflow-y-auto rounded-md border border-slate-200/60 bg-slate-50/40 text-[12px] leading-relaxed whitespace-pre-line text-slate-600" style={{ padding: '10px 12px' }}>
                {report}
              </div>
              {webResults && webResults.length > 0 && (
                <div className="space-y-1.5">
                  <div className="text-[11px] font-medium text-slate-500">External references</div>
                  {webResults.slice(0, 4).map((item, idx) => (
                    <a
                      key={`${item.url}-${idx}`}
                      href={item.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="block rounded-md border border-slate-200/60 text-[11px] text-slate-600 transition-colors hover:bg-slate-50" style={{ padding: '8px 10px' }}
                    >
                      <div className="font-medium text-slate-700">{item.title}</div>
                      {item.snippet && <div className="mt-0.5 line-clamp-2 text-slate-500">{item.snippet}</div>}
                    </a>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* ── 7. Persona Analyses (collapsible) ── */}
      {hasPersonaAnalyses && personaAnalyses && (
        <div className="border-t border-slate-100 mt-2" style={{ paddingTop: '12px' }}>
          {confidenceAssessment && (
            <div className="mb-2 flex items-center gap-3">
              <span className="text-[11px] font-medium text-slate-400">Team Confidence</span>
              <div className="flex-1 h-1.5 rounded-full bg-slate-100 overflow-hidden">
                <div
                  className="h-full rounded-full transition-all"
                  style={{
                    width: `${Math.round(confidenceAssessment.overall * 100)}%`,
                    backgroundColor: confidenceAssessment.overall >= 0.7 ? '#22c55e' : confidenceAssessment.overall >= 0.4 ? '#f59e0b' : '#ef4444',
                  }}
                />
              </div>
              <span className="text-[11px] font-semibold text-slate-700">
                {Math.round(confidenceAssessment.overall * 100)}%
              </span>
            </div>
          )}
          {(data?.evidence?.length ?? 0) > 0 && (
            <div className="mb-2 text-[10px] text-slate-400">
              Citations like <span className="font-semibold text-slate-600">[1]</span> refer to evidence sources above.
            </div>
          )}
          <div className="space-y-2">
            {personaAnalyses.map((pa) => (
              <PersonaCard key={pa.persona} analysis={pa} evidence={data?.evidence ?? []} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function exportCsv(columns: TableData['columns'], rows: TableData['rows'], title: string) {
  const header = columns.map((c) => `"${c.label.replace(/"/g, '""')}"`).join(',');
  const body = rows.map((row) =>
    columns.map((c) => {
      const val = row[c.key];
      if (val == null) return '';
      const str = String(val).replace(/"/g, '""');
      return `"${str}"`;
    }).join(','),
  ).join('\n');
  const csv = `${header}\n${body}`;
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
  const date = new Date().toISOString().slice(0, 10);
  const filename = `${title.replace(/[^a-zA-Z0-9_-]/g, '_')}-${date}.csv`;
  downloadBlob(blob, filename);
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
      const sa = String(va);
      const sb = String(vb);
      return sortAsc ? sa.localeCompare(sb) : sb.localeCompare(sa);
    });
  }, [tableData.rows, sortCol, sortAsc]);

  const displayRows = showAll ? sortedRows : sortedRows.slice(0, 15);

  return (
    <div style={{ paddingTop: '4px' }}>
      <div className="mb-2 flex items-center justify-between">
        {tableData.title && (
          <div className="text-[12px] font-medium text-slate-700">{tableData.title}</div>
        )}
        <button
          type="button"
          onClick={() => exportCsv(tableData.columns, sortedRows, tableData.title || 'export')}
          className="inline-flex items-center gap-1 rounded-md border border-slate-200 bg-white text-[10px] font-medium text-slate-500 transition-colors hover:bg-slate-50 hover:text-slate-700"
          style={{ padding: '4px 8px' }}
          title="Download CSV"
        >
          <Download size={10} />
          CSV
        </button>
      </div>
      <div className="max-h-80 overflow-auto rounded-md border border-slate-200/60">
        <table className="min-w-full text-[12px]" style={{ tableLayout: 'auto' }}>
          <thead className="sticky top-0 bg-white z-10">
            <tr className="border-b border-slate-200">
              {tableData.columns.map((col) => (
                <th
                  key={col.key}
                  onClick={() => handleSort(col.key)}
                  className={`cursor-pointer whitespace-nowrap text-left font-medium text-slate-500 hover:text-slate-700 select-none ${col.type === 'number' ? 'text-right' : ''}`}
                  style={{ padding: '6px 12px' }}
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
              <tr key={i} className="border-b border-slate-100 hover:bg-slate-50/50">
                {tableData.columns.map((col, ci) => (
                  <td
                    key={col.key}
                    title={row[col.key] != null ? String(row[col.key]) : undefined}
                    className={`whitespace-nowrap text-slate-600 ${col.type === 'number' ? 'text-right tabular-nums' : ''} ${ci === 0 ? 'font-medium text-slate-700' : ''}`}
                    style={{ padding: '6px 12px' }}
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


function PersonaCard({ analysis, evidence }: { analysis: PersonaAnalysis; evidence?: EvidenceItem[] }) {
  const [expanded, setExpanded] = useState(false);

  const confidenceColor = analysis.confidence >= 0.7
    ? 'bg-green-500'
    : analysis.confidence >= 0.4
      ? 'bg-amber-500'
      : 'bg-red-500';

  return (
    <div style={{ padding: '8px 4px' }}>
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center gap-2 text-left"
      >
        {expanded ? <ChevronDown size={14} className="text-slate-400" /> : <ChevronRight size={14} className="text-slate-400" />}
        <span className="text-xs font-semibold text-slate-700">{analysis.display_name}</span>
        <div className="ml-auto flex items-center gap-2">
          <div className="flex items-center gap-1.5">
            <div className={`h-1.5 w-8 rounded-full bg-slate-100 overflow-hidden`}>
              <div
                className={`h-full rounded-full ${confidenceColor}`}
                style={{ width: `${Math.round(analysis.confidence * 100)}%` }}
              />
            </div>
            <span className="text-[10px] text-slate-400">{Math.round(analysis.confidence * 100)}%</span>
          </div>
        </div>
      </button>

      {/* Key findings always visible */}
      {analysis.key_findings.length > 0 && (
        <ul className="mt-2 ml-5 space-y-0.5">
          {analysis.key_findings.slice(0, 3).map((finding, i) => (
            <li key={i} className="text-[11px] text-slate-600 list-disc">
              <RichText text={finding} evidence={evidence} />
            </li>
          ))}
        </ul>
      )}

      {/* Data gaps */}
      {analysis.data_gaps.length > 0 && (
        <div className="mt-1.5 ml-5 flex flex-wrap gap-1">
          {analysis.data_gaps.map((gap, i) => (
            <span key={i} className="rounded-sm bg-amber-50 text-[10px] text-amber-700 border border-amber-200/50" style={{ padding: '2px 6px' }}>
              {gap}
            </span>
          ))}
        </div>
      )}

      {/* Full analysis (expandable) */}
      {expanded && (
        <div className="mt-2.5 ml-5 rounded-md border border-slate-200/60 bg-slate-50/50 text-[11px] leading-relaxed text-slate-600" style={{ padding: '8px 12px' }}>
          <RichText text={analysis.analysis} evidence={evidence} />
        </div>
      )}
    </div>
  );
}


function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function shouldPreferGraphView(data?: QueryResponse): boolean {
  if (!data?.graph_context || data.graph_context.nodes.length === 0) return false;
  const summary = data.provenance_summary as Record<string, unknown> | undefined;
  if (!summary) return false;
  if (summary.graph_recommended === true) return true;
  if (summary.graph_primary === true) return true;
  return false;
}

function VisualizationCard({ spec }: { spec: VisualizationSpec }) {
  const colors = ['#1f6cf2', '#22c55e', '#0ea5e9', '#f59e0b', '#8b5cf6', '#ef4444'];
  const hasData = spec.data.some((point) => Number(point.value) > 0);

  if (!hasData) {
    return null;
  }

  return (
    <div style={{ padding: '4px' }}>
      <div className="mb-2 text-[11px] font-medium text-slate-600">{spec.title}</div>
      <div className="w-full" style={{ minHeight: 220, height: 'clamp(220px, 24vw, 300px)' }}>
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
                {spec.data.map((entry, index) => (
                  <Cell key={`${entry.label}-${index}`} fill={colors[index % colors.length]} />
                ))}
              </Pie>
              <Tooltip
                formatter={(value: number) => [`${value.toLocaleString()} ${spec.value_unit ?? ''}`.trim(), '']}
              />
              <Legend
                iconType="circle"
                iconSize={8}
                wrapperStyle={{ fontSize: '11px', color: '#64748b' }}
              />
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
              <Legend
                iconType="rect"
                iconSize={8}
                wrapperStyle={{ fontSize: '11px', color: '#64748b' }}
                formatter={() => spec.value_unit || 'Value'}
              />
              <Bar dataKey="value" radius={[6, 6, 0, 0]} fill="#1f6cf2" name={spec.value_unit || 'Value'} />
            </BarChart>
          )}
        </ResponsiveContainer>
      </div>
    </div>
  );
}

type MetricType = 'pipeline' | 'success_rate' | 'evidence' | 'competitive' | 'portfolio';

interface MetricRow {
  id: string;
  type: MetricType;
  data: Record<string, unknown>;
  entityName?: string;
}

function dedupeEntityFocus(entityFocus: Record<string, unknown>[]): Record<string, unknown>[] {
  const grouped = new Map<string, Record<string, unknown>>();
  for (const entity of entityFocus) {
    const label = String(entity.title ?? entity.label ?? entity.entity_id ?? '');
    const key = canonicalEntityKey(label);
    const existing = grouped.get(key);
    if (!existing) {
      grouped.set(key, entity);
      continue;
    }
    const currentConnections = Number(entity.total_connections ?? 0);
    const existingConnections = Number(existing.total_connections ?? 0);
    if (currentConnections > existingConnections) grouped.set(key, entity);
  }
  return [...grouped.values()];
}

function dedupeMetricsContext(metricsContext: Record<string, unknown>): MetricRow[] {
  const grouped = new Map<string, MetricRow>();
  const validTypes: MetricType[] = ['pipeline', 'success_rate', 'evidence', 'competitive', 'portfolio'];

  for (const [entityKey, metrics] of Object.entries(metricsContext)) {
    const metricGroup = metrics as Record<string, Record<string, unknown>>;
    for (const [metricTypeRaw, metricData] of Object.entries(metricGroup)) {
      if (!metricData || typeof metricData !== 'object') continue;
      if (!validTypes.includes(metricTypeRaw as MetricType)) continue;
      const metricType = metricTypeRaw as MetricType;
      const entityName = resolveMetricEntityName(entityKey, metricData);
      const dedupeKey = `${metricType}|${canonicalEntityKey(entityName ?? entityKey)}`;

      const candidate: MetricRow = {
        id: `${dedupeKey}|${entityKey}`,
        type: metricType,
        data: metricData,
        entityName,
      };

      const existing = grouped.get(dedupeKey);
      if (!existing) {
        grouped.set(dedupeKey, candidate);
        continue;
      }
      grouped.set(dedupeKey, preferMetricRow(existing, candidate));
    }
  }

  return [...grouped.values()];
}

function resolveMetricEntityName(entityKey: string, metricData: Record<string, unknown>): string | undefined {
  const resolved = String(
    metricData.drug_name
    ?? metricData.mechanism_name
    ?? metricData.company_name
    ?? (entityKey.length < 36 ? entityKey : '')
    ?? ''
  ).trim();
  return resolved || undefined;
}

function preferMetricRow(existing: MetricRow, candidate: MetricRow): MetricRow {
  const existingScore = metricPriorityScore(existing.type, existing.data);
  const candidateScore = metricPriorityScore(candidate.type, candidate.data);
  if (candidateScore > existingScore) return candidate;
  return existing;
}

function metricPriorityScore(type: MetricType, metricData: Record<string, unknown>): number {
  const richness: number = Object.values(metricData).reduce<number>((score, value) => (value !== null && value !== undefined ? score + 1 : score), 0);
  if (type === 'pipeline') {
    return richness + Number(metricData.total_trials ?? metricData.active_trials ?? 0) * 5 + Number(metricData.pipeline_score ?? 0);
  }
  if (type === 'success_rate') {
    return richness + Number(metricData.total ?? 0) * 5 + Number(metricData.success_rate ?? 0) * 100;
  }
  if (type === 'evidence') {
    return richness + Number(metricData.total_articles ?? 0) * 5 + Number(metricData.weighted_score ?? 0);
  }
  if (type === 'competitive') {
    return richness + Number(metricData.trial_count ?? 0) * 5 + Number(metricData.total_pipeline_score ?? 0);
  }
  return richness + Number(metricData.pipeline_score_total ?? 0);
}

function canonicalEntityKey(raw: string): string {
  return raw
    .toLowerCase()
    .replace(/sodium[-\s]*glucose[-\s]*cotransporter[-\s]*2/g, 'sglt2')
    .replace(/sglt[\s-]*2/g, 'sglt2')
    .replace(/\binhibitors?\b/g, 'inhibitor')
    .replace(/[^a-z0-9]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

