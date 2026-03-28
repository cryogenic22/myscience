import { useCallback, useEffect, useState } from 'react';
import {
  ExternalLink,
  Loader2,
  MessageSquare,
  Network,
  FileText,
  ChevronDown,
  ChevronUp,
  ArrowRight,
} from 'lucide-react';
import type { SearchResult, GraphNode, GraphEdge } from '../../api';
import { SOURCE_LABELS, ENTITY_TYPE_LABELS } from '../../brand';
import GraphMini from '../GraphMini';
import {
  type GraphFocus,
  TYPE_CONFIG,
  prettyType,
  truncateValue,
  getResultSnippet,
  getSourcePublicationDate,
  getRelatedDocuments,
} from './search-utils';

/* ── Entity type color map (matches design system CSS variables) ── */

const ENTITY_TYPE_COLORS: Record<string, string> = {
  drug: 'var(--color-drug)',
  company: 'var(--color-company)',
  trial: 'var(--color-trial)',
  mechanism: 'var(--color-mechanism)',
  therapeutic_area: 'var(--color-ta)',
  literature: 'var(--color-literature)',
};

/* ── Summary generators (reuse patterns from EntityDossier) ── */

function str(v: unknown): string {
  if (v == null) return '';
  if (Array.isArray(v)) return v.join(', ');
  return String(v);
}

function generateOneLiner(entityType: string, metadata: Record<string, unknown>, title: string): string {
  switch (entityType) {
    case 'drug': {
      const generic = str(metadata.generic_name);
      const brand = str(metadata.brand_name);
      const supply = str(metadata.supply_status);
      const phase = str(metadata.phase);
      const parts: string[] = [];
      if (brand && generic && brand.toLowerCase() !== generic.toLowerCase()) {
        parts.push(`${brand} (${generic})`);
      } else {
        parts.push(title);
      }
      if (phase) parts.push(`${phase}`);
      if (supply) parts.push(supply.charAt(0).toUpperCase() + supply.slice(1).toLowerCase());
      return parts.join(' \u00b7 ');
    }
    case 'company': {
      const ticker = str(metadata.ticker);
      const region = str(metadata.region || metadata.country);
      const tier = str(metadata.market_cap_tier);
      const parts: string[] = [title];
      if (ticker) parts.push(ticker);
      if (tier) parts.push(tier.charAt(0).toUpperCase() + tier.slice(1));
      if (region) parts.push(region);
      return parts.join(' \u00b7 ');
    }
    case 'trial': {
      const phase = str(metadata.phase);
      const status = str(metadata.status);
      const sponsor = str(metadata.sponsor_name);
      const parts: string[] = [];
      if (phase) parts.push(phase);
      if (status) parts.push(status.charAt(0).toUpperCase() + status.slice(1).toLowerCase());
      if (sponsor) parts.push(`by ${sponsor}`);
      return parts.length > 0 ? parts.join(' \u00b7 ') : title;
    }
    case 'literature': {
      const journal = str(metadata.journal);
      const pubDate = str(metadata.publication_date);
      const parts: string[] = [];
      if (journal) parts.push(journal);
      if (pubDate) {
        const d = new Date(pubDate);
        if (!Number.isNaN(d.getTime())) {
          parts.push(d.toLocaleDateString(undefined, { year: 'numeric', month: 'short' }));
        }
      }
      return parts.length > 0 ? parts.join(' \u00b7 ') : title;
    }
    default: {
      const typeLabel = entityType.replace(/_/g, ' ');
      return `${typeLabel.charAt(0).toUpperCase() + typeLabel.slice(1)}`;
    }
  }
}

/* ── Key metrics by entity type ── */

interface MetricItem {
  label: string;
  value: string;
}

function extractKeyMetrics(
  entityType: string,
  metadata: Record<string, unknown>,
  neighborsByType: Record<string, number>,
  totalConnections: number,
): MetricItem[] {
  const metrics: MetricItem[] = [];

  switch (entityType) {
    case 'drug': {
      const trials = neighborsByType['trial'] ?? 0;
      const pubs = neighborsByType['literature'] ?? 0;
      if (trials > 0) metrics.push({ label: 'Trials', value: String(trials) });
      if (pubs > 0) metrics.push({ label: 'Publications', value: String(pubs) });
      if (totalConnections > 0) metrics.push({ label: 'Connections', value: String(totalConnections) });
      const phase = str(metadata.phase);
      if (phase && metrics.length < 3) metrics.push({ label: 'Phase', value: phase });
      break;
    }
    case 'company': {
      const drugs = neighborsByType['drug'] ?? 0;
      const trials = neighborsByType['trial'] ?? 0;
      if (drugs > 0) metrics.push({ label: 'Drugs', value: String(drugs) });
      if (trials > 0) metrics.push({ label: 'Trials', value: String(trials) });
      if (totalConnections > 0) metrics.push({ label: 'Connections', value: String(totalConnections) });
      break;
    }
    case 'trial': {
      const phase = str(metadata.phase);
      const enrollment = str(metadata.enrollment_target);
      const status = str(metadata.status);
      if (phase) metrics.push({ label: 'Phase', value: phase });
      if (enrollment && enrollment !== '0') metrics.push({ label: 'Enrollment', value: enrollment });
      if (status) metrics.push({ label: 'Status', value: status.charAt(0).toUpperCase() + status.slice(1).toLowerCase() });
      break;
    }
    default: {
      if (totalConnections > 0) metrics.push({ label: 'Connections', value: String(totalConnections) });
      break;
    }
  }

  return metrics.slice(0, 4);
}

/* ── Relative time helper ── */

function relativeTime(dateStr: string): string {
  const now = Date.now();
  const then = new Date(dateStr).getTime();
  if (Number.isNaN(then)) return dateStr;
  const diffMs = now - then;
  const diffMins = Math.floor(diffMs / 60000);
  if (diffMins < 1) return 'just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.floor(diffHours / 24);
  if (diffDays < 30) return `${diffDays}d ago`;
  const diffMonths = Math.floor(diffDays / 30);
  if (diffMonths < 12) return `${diffMonths}mo ago`;
  return `${Math.floor(diffMonths / 12)}y ago`;
}

/* ── Section header ── */

function SectionHeader({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      fontSize: '11px',
      fontWeight: 600,
      textTransform: 'uppercase' as const,
      letterSpacing: '0.08em',
      color: 'var(--color-ink-4)',
      marginBottom: '10px',
    }}>
      {children}
    </div>
  );
}

/* ── Props ── */

interface EntityPreviewProps {
  result: SearchResult | null;
  activeResultIndex: number;
  totalVisibleResults: number;
  onPrevResult: () => void;
  onNextResult: () => void;
  onAskInChat: (result: SearchResult) => void;
  onExploreNode: (nodeLabel: string) => void;
  linkedGraphLoading: boolean;
  linkedGraphError: string | null;
  linkedNeighbors: Array<{
    key: string;
    id: string;
    type: string;
    label: string;
    nodeType: string;
    relation: string;
    confidence: number;
  }>;
  linkedGraphNodes: GraphNode[];
  linkedGraphEdges: GraphEdge[];
  graphFocus: GraphFocus | null;
  graphTrail: GraphFocus[];
  edgeTypeFilter: string;
  edgeTypeOptions: string[];
  onEdgeTypeFilterChange: (value: string) => void;
  onGraphNodeSelect: (node: GraphNode) => void;
  onGraphTrailJump: (node: GraphFocus) => void;
  onGraphNeighborFocus: (node: { id: string; type: string; label: string }) => void;
  onOpenFocusedNodeInSearch: () => void;
  onClose?: () => void;
}

export default function EntityPreview({
  result,
  activeResultIndex,
  totalVisibleResults,
  onPrevResult,
  onNextResult,
  onAskInChat,
  onExploreNode,
  linkedGraphLoading,
  linkedGraphError,
  linkedNeighbors,
  linkedGraphNodes,
  linkedGraphEdges,
  graphFocus,
  graphTrail,
  edgeTypeFilter,
  edgeTypeOptions,
  onEdgeTypeFilterChange,
  onGraphNodeSelect,
  onGraphTrailJump,
  onGraphNeighborFocus,
  onOpenFocusedNodeInSearch,
}: EntityPreviewProps) {
  const [neighborCursor, setNeighborCursor] = useState(0);
  const [connectionsExpanded, setConnectionsExpanded] = useState(false);
  const [graphExpanded, setGraphExpanded] = useState(true);

  useEffect(() => {
    setNeighborCursor(0);
  }, [graphFocus?.id, edgeTypeFilter, linkedNeighbors.length]);

  useEffect(() => {
    if (!result) {
      setConnectionsExpanded(false);
      setGraphExpanded(false);
      return;
    }
    setConnectionsExpanded(false);
    setGraphExpanded(true);
  }, [result?.entity_id, result?.entity_type]);

  const handleNeighborKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLDivElement>) => {
      if (linkedNeighbors.length === 0) return;
      if (event.key === 'ArrowDown') {
        event.preventDefault();
        setNeighborCursor((prev) => Math.min(prev + 1, linkedNeighbors.length - 1));
        return;
      }
      if (event.key === 'ArrowUp') {
        event.preventDefault();
        setNeighborCursor((prev) => Math.max(prev - 1, 0));
        return;
      }
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        const target = linkedNeighbors[neighborCursor];
        if (target) onGraphNeighborFocus({ id: target.id, type: target.type, label: target.label });
      }
    },
    [linkedNeighbors, neighborCursor, onGraphNeighborFocus],
  );

  /* ── Empty state ── */

  if (!result) {
    return (
      <aside
        id="search-result-inspector"
        className="h-fit lg:sticky lg:top-4 lg:max-h-[calc(100vh-5rem)] lg:overflow-y-auto"
        style={{
          padding: '32px 24px',
          background: 'var(--color-surface)',
          borderRadius: '12px',
        }}
      >
        <div style={{
          fontSize: '15px',
          fontWeight: 600,
          color: 'var(--color-ink)',
          marginBottom: '8px',
        }}>
          Entity Profile
        </div>
        <p style={{
          fontSize: '13px',
          color: 'var(--color-ink-3)',
          lineHeight: 1.5,
        }}>
          Select a result to view its profile, connections, and evidence.
        </p>
      </aside>
    );
  }

  /* ── Derived data ── */

  const entityColor = ENTITY_TYPE_COLORS[result.entity_type] ?? 'var(--color-ink-3)';
  const cfg = TYPE_CONFIG[result.entity_type] ?? {
    color: 'var(--color-ink-3)',
    bgVar: 'rgba(148, 163, 184, 0.08)',
    label: result.entity_type,
  };
  const typeLabel = ENTITY_TYPE_LABELS[result.entity_type] ?? prettyType(result.entity_type);
  const sourceApi = String(result.provenance?.source_api ?? 'unknown');
  const sourceLabel = SOURCE_LABELS[sourceApi] ?? sourceApi;
  const sourceUrl = result.provenance?.source_url ? String(result.provenance.source_url) : null;
  const retrievedAt = result.provenance?.retrieved_at ? String(result.provenance.retrieved_at) : null;
  const sourcePublishedAt = getSourcePublicationDate(result.metadata);
  const previewSnippet = getResultSnippet(result);
  const relatedDocuments = getRelatedDocuments(result);

  // Build connection counts by type
  const neighborsByType: Record<string, number> = {};
  for (const n of linkedNeighbors) {
    neighborsByType[n.nodeType] = (neighborsByType[n.nodeType] || 0) + 1;
  }
  const totalConnections = linkedNeighbors.length;

  const connectionGroups = Object.entries(neighborsByType)
    .map(([type, count]) => ({ type, count, label: ENTITY_TYPE_LABELS[type] ?? prettyType(type) }))
    .sort((a, b) => b.count - a.count);

  const oneLiner = generateOneLiner(result.entity_type, result.metadata ?? {}, result.title);
  const keyMetrics = extractKeyMetrics(result.entity_type, result.metadata ?? {}, neighborsByType, totalConnections);

  // Top 3 connections to show as clickable links
  const topConnections = linkedNeighbors.slice(0, connectionsExpanded ? 12 : 3);

  // Literature-type results from neighbors
  const literatureNeighbors = linkedNeighbors
    .filter((n) => n.nodeType === 'literature')
    .slice(0, 3);

  return (
    <aside
      id="search-result-inspector"
      className="h-fit lg:sticky lg:top-4 lg:max-h-[calc(100vh-5rem)] lg:overflow-y-auto"
      style={{
        background: 'var(--color-surface)',
        borderRadius: '12px',
        overflow: 'hidden',
      }}
    >
      {/* ── Header section ── */}
      <div style={{
        padding: '24px 24px 20px',
        borderBottom: '1px solid var(--color-line)',
      }}>
        {/* Navigation */}
        {totalVisibleResults > 1 && (
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            marginBottom: '16px',
          }}>
            <button
              type="button"
              onClick={onPrevResult}
              disabled={activeResultIndex <= 0}
              style={{
                fontSize: '11px',
                padding: '4px 12px',
                borderRadius: '6px',
                border: '1px solid var(--color-line)',
                background: 'var(--color-bg)',
                color: 'var(--color-ink-2)',
                cursor: activeResultIndex <= 0 ? 'default' : 'pointer',
                opacity: activeResultIndex <= 0 ? 0.4 : 1,
              }}
            >
              Prev
            </button>
            <span style={{ fontSize: '11px', color: 'var(--color-ink-3)' }}>
              {Math.max(activeResultIndex + 1, 1)} of {totalVisibleResults}
            </span>
            <button
              type="button"
              onClick={onNextResult}
              disabled={activeResultIndex < 0 || activeResultIndex >= totalVisibleResults - 1}
              style={{
                fontSize: '11px',
                padding: '4px 12px',
                borderRadius: '6px',
                border: '1px solid var(--color-line)',
                background: 'var(--color-bg)',
                color: 'var(--color-ink-2)',
                cursor: activeResultIndex >= totalVisibleResults - 1 ? 'default' : 'pointer',
                opacity: activeResultIndex >= totalVisibleResults - 1 ? 0.4 : 1,
              }}
            >
              Next
            </button>
          </div>
        )}

        {/* Entity name */}
        <h3 style={{
          fontSize: '18px',
          fontWeight: 600,
          color: 'var(--color-ink)',
          lineHeight: 1.3,
          margin: 0,
        }}>
          {result.title}
        </h3>

        {/* Entity type badge */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          marginTop: '8px',
        }}>
          <span style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '6px',
            fontSize: '11px',
            fontWeight: 600,
            textTransform: 'uppercase' as const,
            letterSpacing: '0.04em',
            color: entityColor,
            background: cfg.bgVar,
            padding: '3px 10px',
            borderRadius: '12px',
          }}>
            <span style={{
              width: '6px',
              height: '6px',
              borderRadius: '50%',
              background: entityColor,
            }} />
            {typeLabel}
          </span>
          <span style={{
            fontSize: '11px',
            color: 'var(--color-ink-4)',
          }}>
            {sourceLabel}
          </span>
        </div>

        {/* One-line summary */}
        {oneLiner && oneLiner !== result.title && (
          <p style={{
            fontSize: '13px',
            color: 'var(--color-ink-2)',
            marginTop: '10px',
            lineHeight: 1.5,
          }}>
            {oneLiner}
          </p>
        )}
      </div>

      {/* ── Key metrics strip ── */}
      {keyMetrics.length > 0 && (
        <div style={{
          display: 'grid',
          gridTemplateColumns: `repeat(${Math.min(keyMetrics.length, 4)}, 1fr)`,
          padding: '16px 24px',
          borderBottom: '1px solid var(--color-line)',
          gap: '4px',
        }}>
          {keyMetrics.map((m) => (
            <div key={m.label} style={{ textAlign: 'center' }}>
              <div style={{
                fontSize: '18px',
                fontWeight: 700,
                color: 'var(--color-ink)',
                lineHeight: 1.2,
              }}>
                {m.value}
              </div>
              <div style={{
                fontSize: '10px',
                fontWeight: 500,
                textTransform: 'uppercase' as const,
                letterSpacing: '0.06em',
                color: 'var(--color-ink-4)',
                marginTop: '2px',
              }}>
                {m.label}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ── Snippet / Description ── */}
      {previewSnippet && (
        <div style={{
          padding: '16px 24px',
          borderBottom: '1px solid var(--color-line)',
        }}>
          <p style={{
            fontSize: '13px',
            lineHeight: 1.6,
            color: 'var(--color-ink-2)',
            margin: 0,
          }}>
            {previewSnippet}
          </p>
        </div>
      )}

      {/* ── Connections section (progressive disclosure) ── */}
      {!linkedGraphLoading && totalConnections > 0 && (
        <div style={{
          padding: '16px 24px',
          borderBottom: '1px solid var(--color-line)',
        }}>
          <SectionHeader>
            Connections ({totalConnections})
          </SectionHeader>

          {/* Connection type summary pills */}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginBottom: '12px' }}>
            {connectionGroups.map((g) => {
              const gColor = ENTITY_TYPE_COLORS[g.type] ?? 'var(--color-ink-3)';
              const gCfg = TYPE_CONFIG[g.type];
              return (
                <span
                  key={g.type}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '5px',
                    fontSize: '11px',
                    fontWeight: 500,
                    color: 'var(--color-ink-2)',
                    background: gCfg?.bgVar ?? 'var(--color-surface-2)',
                    padding: '3px 10px',
                    borderRadius: '12px',
                  }}
                >
                  <span style={{
                    fontWeight: 700,
                    color: gColor,
                  }}>
                    {g.count}
                  </span>
                  {g.label}{g.count !== 1 ? 's' : ''}
                </span>
              );
            })}
          </div>

          {/* Top connections as clickable items */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            {topConnections.map((neighbor) => {
              const nColor = ENTITY_TYPE_COLORS[neighbor.nodeType] ?? 'var(--color-ink-4)';
              return (
                <button
                  key={neighbor.key}
                  type="button"
                  onClick={() =>
                    onGraphNeighborFocus({ id: neighbor.id, type: neighbor.type, label: neighbor.label })
                  }
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '10px',
                    padding: '8px 12px',
                    borderRadius: '8px',
                    background: 'var(--color-bg)',
                    border: 'none',
                    cursor: 'pointer',
                    textAlign: 'left' as const,
                    width: '100%',
                    transition: 'background 150ms',
                  }}
                  onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--color-surface-2)'; }}
                  onMouseLeave={(e) => { e.currentTarget.style.background = 'var(--color-bg)'; }}
                >
                  <span style={{
                    width: '6px',
                    height: '6px',
                    borderRadius: '50%',
                    background: nColor,
                    flexShrink: 0,
                  }} />
                  <span style={{ flex: 1, minWidth: 0 }}>
                    <span style={{
                      display: 'block',
                      fontSize: '13px',
                      fontWeight: 500,
                      color: 'var(--color-ink)',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap' as const,
                    }}>
                      {neighbor.label}
                    </span>
                    <span style={{
                      display: 'block',
                      fontSize: '11px',
                      color: 'var(--color-ink-4)',
                    }}>
                      {neighbor.relation}
                    </span>
                  </span>
                  <ArrowRight size={12} style={{ color: 'var(--color-ink-4)', flexShrink: 0 }} />
                </button>
              );
            })}
          </div>

          {/* Expand / collapse */}
          {totalConnections > 3 && (
            <button
              type="button"
              onClick={() => setConnectionsExpanded((prev) => !prev)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
                fontSize: '12px',
                fontWeight: 500,
                color: 'var(--color-accent)',
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                padding: '8px 0 0',
              }}
            >
              {connectionsExpanded ? (
                <>
                  <ChevronUp size={14} />
                  Show fewer
                </>
              ) : (
                <>
                  <ChevronDown size={14} />
                  Show all {totalConnections} connections
                </>
              )}
            </button>
          )}
        </div>
      )}

      {/* ── Loading state for connections ── */}
      {linkedGraphLoading && (
        <div style={{
          padding: '16px 24px',
          borderBottom: '1px solid var(--color-line)',
        }}>
          <SectionHeader>Connections</SectionHeader>
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            fontSize: '12px',
            color: 'var(--color-ink-3)',
          }}>
            <Loader2 size={12} className="animate-spin" />
            Loading connections...
          </div>
        </div>
      )}

      {/* ── Graph visualization (collapsed by default, expandable) ── */}
      {!linkedGraphLoading && !linkedGraphError && linkedGraphNodes.length > 0 && (
        <div style={{
          padding: '16px 24px',
          borderBottom: '1px solid var(--color-line)',
        }}>
          <button
            type="button"
            onClick={() => setGraphExpanded((prev) => !prev)}
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              width: '100%',
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              padding: 0,
              marginBottom: graphExpanded ? '12px' : 0,
            }}
          >
            <span style={{
              fontSize: '11px',
              fontWeight: 600,
              textTransform: 'uppercase' as const,
              letterSpacing: '0.08em',
              color: 'var(--color-ink-4)',
            }}>
              Knowledge Graph
            </span>
            {graphExpanded ? (
              <ChevronUp size={14} style={{ color: 'var(--color-ink-4)' }} />
            ) : (
              <ChevronDown size={14} style={{ color: 'var(--color-ink-4)' }} />
            )}
          </button>

          {graphExpanded && (
            <>
              {/* Graph trail breadcrumbs */}
              {graphTrail.length > 1 && (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px', marginBottom: '8px' }}>
                  {graphTrail.map((node, index) => (
                    <button
                      key={`${node.type}-${node.id}`}
                      type="button"
                      onClick={() => onGraphTrailJump(node)}
                      style={{
                        maxWidth: '140px',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap' as const,
                        fontSize: '10px',
                        padding: '3px 10px',
                        borderRadius: '10px',
                        border: graphFocus?.id === node.id && graphFocus.type === node.type
                          ? '1px solid var(--color-accent)'
                          : '1px solid var(--color-line)',
                        background: graphFocus?.id === node.id && graphFocus.type === node.type
                          ? 'var(--color-accent-soft)'
                          : 'var(--color-bg)',
                        color: graphFocus?.id === node.id && graphFocus.type === node.type
                          ? 'var(--color-ink)'
                          : 'var(--color-ink-3)',
                        cursor: 'pointer',
                      }}
                    >
                      {index + 1}. {node.label}
                    </button>
                  ))}
                </div>
              )}

              {/* Edge type filter */}
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                <span style={{ fontSize: '10px', color: 'var(--color-ink-4)' }}>Filter</span>
                <select
                  value={edgeTypeFilter}
                  onChange={(e) => onEdgeTypeFilterChange(e.target.value)}
                  style={{
                    fontSize: '10px',
                    padding: '4px 8px',
                    borderRadius: '6px',
                    border: '1px solid var(--color-line)',
                    background: 'var(--color-bg)',
                    color: 'var(--color-ink-2)',
                    outline: 'none',
                  }}
                >
                  <option value="all">All link types</option>
                  {edgeTypeOptions.map((type) => (
                    <option key={type} value={type}>
                      {prettyType(type)}
                    </option>
                  ))}
                </select>
              </div>

              {/* Graph mini visualization */}
              <div style={{
                borderRadius: '8px',
                overflow: 'hidden',
                border: '1px solid var(--color-line)',
                background: 'var(--color-bg)',
              }}>
                <GraphMini
                  nodes={linkedGraphNodes}
                  edges={linkedGraphEdges}
                  centerEntityId={graphFocus?.id ?? result.entity_id}
                  height={200}
                  onNodeClick={onGraphNodeSelect}
                />
              </div>

              {/* Neighbor list (keyboard navigable) */}
              <div
                tabIndex={0}
                onKeyDown={handleNeighborKeyDown}
                style={{
                  maxHeight: '200px',
                  overflowY: 'auto',
                  marginTop: '8px',
                  outline: 'none',
                }}
              >
                {linkedNeighbors.slice(0, 12).map((neighbor, index) => (
                  <button
                    key={neighbor.key}
                    type="button"
                    onClick={() =>
                      onGraphNeighborFocus({ id: neighbor.id, type: neighbor.type, label: neighbor.label })
                    }
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      gap: '8px',
                      width: '100%',
                      padding: '6px 10px',
                      borderRadius: '6px',
                      border: 'none',
                      background: index === neighborCursor ? 'var(--color-accent-soft)' : 'transparent',
                      cursor: 'pointer',
                      textAlign: 'left' as const,
                    }}
                  >
                    <span style={{ minWidth: 0 }}>
                      <span style={{
                        display: 'block',
                        fontSize: '12px',
                        fontWeight: 500,
                        color: 'var(--color-ink)',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap' as const,
                      }}>
                        {neighbor.label}
                      </span>
                      <span style={{
                        display: 'block',
                        fontSize: '10px',
                        color: 'var(--color-ink-4)',
                      }}>
                        {neighbor.relation} \u00b7 {prettyType(neighbor.nodeType)}
                      </span>
                    </span>
                  </button>
                ))}
              </div>
            </>
          )}
        </div>
      )}

      {/* ── Recent evidence (literature neighbors) ── */}
      {literatureNeighbors.length > 0 && (
        <div style={{
          padding: '16px 24px',
          borderBottom: '1px solid var(--color-line)',
        }}>
          <SectionHeader>Recent Evidence</SectionHeader>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {literatureNeighbors.map((pub) => (
              <div
                key={pub.key}
                style={{
                  padding: '8px 12px',
                  borderRadius: '8px',
                  background: 'var(--color-bg)',
                }}
              >
                <div style={{
                  fontSize: '13px',
                  fontWeight: 500,
                  color: 'var(--color-ink)',
                  lineHeight: 1.4,
                  display: '-webkit-box',
                  WebkitLineClamp: 2,
                  WebkitBoxOrient: 'vertical' as const,
                  overflow: 'hidden',
                }}>
                  {pub.label}
                </div>
                <div style={{
                  fontSize: '11px',
                  color: 'var(--color-ink-4)',
                  marginTop: '2px',
                }}>
                  {pub.relation}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Related documents (external links) ── */}
      {relatedDocuments.length > 0 && (
        <div style={{
          padding: '16px 24px',
          borderBottom: '1px solid var(--color-line)',
        }}>
          <SectionHeader>Source Documents</SectionHeader>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            {relatedDocuments.slice(0, 3).map((link) => (
              <a
                key={link}
                href={link}
                target="_blank"
                rel="noopener noreferrer"
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  padding: '6px 10px',
                  borderRadius: '6px',
                  fontSize: '12px',
                  color: 'var(--color-ink-2)',
                  textDecoration: 'none',
                  transition: 'background 150ms',
                }}
                onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--color-bg)'; }}
                onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; }}
              >
                <ExternalLink size={12} style={{ flexShrink: 0, color: 'var(--color-ink-4)' }} />
                <span style={{
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap' as const,
                }}>
                  {truncateValue(link, 60)}
                </span>
              </a>
            ))}
          </div>
        </div>
      )}

      {/* ── Provenance footer ── */}
      <div style={{
        padding: '12px 24px',
        borderBottom: '1px solid var(--color-line)',
        display: 'flex',
        flexWrap: 'wrap',
        gap: '12px',
        fontSize: '11px',
        color: 'var(--color-ink-4)',
      }}>
        <span>Source: {sourceLabel}</span>
        {sourcePublishedAt && (
          <span>Published: {new Date(sourcePublishedAt).toLocaleDateString(undefined, { year: 'numeric', month: 'short' })}</span>
        )}
        {retrievedAt && (
          <span>Indexed {relativeTime(retrievedAt)}</span>
        )}
      </div>

      {/* ── Action buttons ── */}
      <div style={{
        padding: '16px 24px 24px',
        display: 'flex',
        flexDirection: 'column',
        gap: '8px',
      }}>
        <button
          type="button"
          onClick={() => onAskInChat(result)}
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '8px',
            width: '100%',
            padding: '10px 16px',
            borderRadius: '8px',
            fontSize: '13px',
            fontWeight: 600,
            color: '#fff',
            background: 'var(--color-accent)',
            border: 'none',
            cursor: 'pointer',
            transition: 'opacity 150ms',
          }}
          onMouseEnter={(e) => { e.currentTarget.style.opacity = '0.9'; }}
          onMouseLeave={(e) => { e.currentTarget.style.opacity = '1'; }}
        >
          <MessageSquare size={14} />
          Ask in Chat
        </button>

        <div style={{ display: 'flex', gap: '8px' }}>
          <button
            type="button"
            onClick={onOpenFocusedNodeInSearch}
            style={{
              flex: 1,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '6px',
              padding: '8px 12px',
              borderRadius: '8px',
              fontSize: '12px',
              fontWeight: 500,
              color: 'var(--color-ink-2)',
              background: 'var(--color-bg)',
              border: '1px solid var(--color-line)',
              cursor: 'pointer',
              transition: 'background 150ms',
            }}
            onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--color-surface-2)'; }}
            onMouseLeave={(e) => { e.currentTarget.style.background = 'var(--color-bg)'; }}
          >
            <Network size={12} />
            Explore in Graph
          </button>
          {sourceUrl && (
            <a
              href={sourceUrl}
              target="_blank"
              rel="noopener noreferrer"
              style={{
                flex: 1,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '6px',
                padding: '8px 12px',
                borderRadius: '8px',
                fontSize: '12px',
                fontWeight: 500,
                color: 'var(--color-ink-2)',
                background: 'var(--color-bg)',
                border: '1px solid var(--color-line)',
                cursor: 'pointer',
                textDecoration: 'none',
                transition: 'background 150ms',
              }}
              onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--color-surface-2)'; }}
              onMouseLeave={(e) => { e.currentTarget.style.background = 'var(--color-bg)'; }}
            >
              <FileText size={12} />
              View Source
            </a>
          )}
        </div>
      </div>
    </aside>
  );
}
