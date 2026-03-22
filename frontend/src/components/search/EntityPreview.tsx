import { useCallback, useEffect, useState } from 'react';
import {
  ShieldCheck,
  ExternalLink,
  Loader2,
  MessageSquare,
  X,
} from 'lucide-react';
import type { SearchResult, GraphNode, GraphEdge } from '../../api';
import GraphMini from '../GraphMini';
import {
  type GraphFocus,
  prettyType,
  truncateValue,
  formatDate,
  getResultSnippet,
  getSourcePublicationDate,
  extractPreviewContent,
  getRelatedDocuments,
  getRelatedNodes,
} from './search-utils';

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
  const [previewModalOpen, setPreviewModalOpen] = useState(false);

  useEffect(() => {
    setNeighborCursor(0);
  }, [graphFocus?.id, edgeTypeFilter, linkedNeighbors.length]);

  useEffect(() => {
    if (!result) {
      setPreviewModalOpen(false);
      return;
    }
    setPreviewModalOpen(false);
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

  if (!result) {
    return (
      <aside
        id="search-result-inspector"
        className="h-fit card p-6 lg:sticky lg:top-4 lg:max-h-[calc(100vh-5rem)] lg:overflow-y-auto"
      >
        <div className="text-[15px] font-semibold mb-2" style={{ color: 'var(--color-ink)' }}>
          Result Details
        </div>
        <p className="text-xs" style={{ color: 'var(--color-ink-3)' }}>
          Select a result to inspect its source, quality, and metadata.
        </p>
      </aside>
    );
  }

  const sourceApi = String(result.provenance?.source_api ?? 'unknown source');
  const sourceUrl = result.provenance?.source_url ? String(result.provenance.source_url) : null;
  const retrievedAt = result.provenance?.retrieved_at ? String(result.provenance.retrieved_at) : null;
  const sourcePublishedAt = getSourcePublicationDate(result.metadata);
  const previewSnippet = getResultSnippet(result);
  const similarityPct = Math.round(result.similarity * 100);
  const qualityPct = typeof result.quality_score === 'number' ? Math.round(result.quality_score * 100) : null;
  const metadataRows = Object.entries(result.metadata ?? {})
    .filter(([, value]) => value !== null && value !== undefined && String(value).trim() !== '');
  const relatedDocuments = getRelatedDocuments(result);
  const relatedNodes = getRelatedNodes(result);
  const databasePreview = extractPreviewContent(result);

  return (
    <aside
      id="search-result-inspector"
      className="h-fit card space-y-4 p-6 lg:sticky lg:top-4 lg:max-h-[calc(100vh-5rem)] lg:overflow-y-auto"
    >
      {/* Header */}
      <div>
        <div
          className="text-[11px] uppercase tracking-[0.14em] font-semibold"
          style={{ color: 'var(--color-ink-4)' }}
        >
          Selected Result
        </div>
        <h3
          className="mt-1 text-[15px] font-semibold leading-relaxed"
          style={{ color: 'var(--color-ink)' }}
        >
          {result.title}
        </h3>
        <div className="mt-1 text-xs capitalize" style={{ color: 'var(--color-ink-3)' }}>
          {prettyType(result.entity_type)}
        </div>
        {totalVisibleResults > 1 && (
          <div className="mt-2 flex items-center gap-2">
            <button
              type="button"
              onClick={onPrevResult}
              disabled={activeResultIndex <= 0}
              className="rounded-md px-3 py-1 text-[11px] transition-colors disabled:opacity-40"
              style={{
                border: '1px solid var(--color-line)',
                background: 'var(--color-surface)',
                color: 'var(--color-ink-2)',
              }}
            >
              Prev
            </button>
            <span className="text-[11px]" style={{ color: 'var(--color-ink-3)' }}>
              {Math.max(activeResultIndex + 1, 1)} of {totalVisibleResults}
            </span>
            <button
              type="button"
              onClick={onNextResult}
              disabled={activeResultIndex < 0 || activeResultIndex >= totalVisibleResults - 1}
              className="rounded-md px-3 py-1 text-[11px] transition-colors disabled:opacity-40"
              style={{
                border: '1px solid var(--color-line)',
                background: 'var(--color-surface)',
                color: 'var(--color-ink-2)',
              }}
            >
              Next
            </button>
          </div>
        )}
      </div>

      {/* Snippet */}
      {previewSnippet && (
        <div
          className="rounded-md px-4 py-3 text-xs leading-relaxed"
          style={{
            border: '1px solid var(--color-line)',
            background: 'var(--color-surface)',
            color: 'var(--color-ink-2)',
          }}
        >
          {previewSnippet}
        </div>
      )}

      {/* Database preview */}
      <section>
        <div className="mb-2 flex items-center justify-between gap-2">
          <span className="text-[12px] font-semibold" style={{ color: 'var(--color-ink)' }}>
            Database Preview
          </span>
          <button
            type="button"
            onClick={() => setPreviewModalOpen(true)}
            className="rounded-md px-3 py-1 text-[10px] transition-colors"
            style={{
              border: '1px solid var(--color-line)',
              background: 'var(--color-surface)',
              color: 'var(--color-ink-2)',
            }}
          >
            Expand
          </button>
        </div>
        <div
          className="max-h-96 overflow-y-auto rounded-md px-4 py-3 text-xs leading-relaxed"
          style={{
            border: '1px solid var(--color-line)',
            background: 'var(--color-surface)',
            color: 'var(--color-ink-2)',
          }}
        >
          {databasePreview}
        </div>
      </section>

      {/* Similarity / Quality bars */}
      <div className="space-y-1.5">
        <div className="flex items-center justify-between text-xs">
          <span className="inline-flex items-center gap-1" style={{ color: 'var(--color-ink-3)' }}>
            <ShieldCheck size={12} /> Similarity
          </span>
          <span className="font-semibold" style={{ color: 'var(--color-ink)' }}>
            {similarityPct}%
          </span>
        </div>
        <div
          className="h-1.5 rounded-full overflow-hidden"
          style={{ background: 'var(--color-surface-3)' }}
        >
          <div
            className="h-full rounded-full"
            style={{
              width: `${Math.min(similarityPct, 100)}%`,
              background: 'var(--color-accent)',
            }}
          />
        </div>
        {qualityPct !== null && (
          <>
            <div className="flex items-center justify-between text-xs">
              <span style={{ color: 'var(--color-ink-3)' }}>Quality score</span>
              <span className="font-semibold" style={{ color: 'var(--color-ink)' }}>
                {qualityPct}%
              </span>
            </div>
            <div
              className="h-1.5 rounded-full overflow-hidden"
              style={{ background: 'var(--color-surface-3)' }}
            >
              <div
                className="h-full rounded-full"
                style={{
                  width: `${Math.min(qualityPct, 100)}%`,
                  background: 'var(--color-green)',
                }}
              />
            </div>
          </>
        )}
      </div>

      {/* Source information */}
      <section>
        <div className="text-[12px] font-semibold mb-2" style={{ color: 'var(--color-ink)' }}>
          Source Information
        </div>
        <div className="space-y-1.5 text-xs">
          <div
            className="flex items-center justify-between gap-4 rounded-md px-3.5 py-2.5"
            style={{
              border: '1px solid var(--color-line)',
              background: 'var(--color-surface)',
            }}
          >
            <span style={{ color: 'var(--color-ink-3)' }}>Source API</span>
            <span className="font-medium truncate" style={{ color: 'var(--color-ink)' }}>
              {sourceApi}
            </span>
          </div>
          {sourcePublishedAt && (
            <div
              className="flex items-center justify-between gap-4 rounded-md px-3.5 py-2.5"
              style={{
                border: '1px solid var(--color-line)',
                background: 'var(--color-surface)',
              }}
            >
              <span style={{ color: 'var(--color-ink-3)' }}>Source publication</span>
              <span className="font-medium" style={{ color: 'var(--color-ink)' }}>
                {formatDate(sourcePublishedAt)}
              </span>
            </div>
          )}
          {retrievedAt && (
            <div
              className="flex items-center justify-between gap-4 rounded-md px-3.5 py-2.5"
              style={{
                border: '1px solid var(--color-line)',
                background: 'var(--color-surface)',
              }}
            >
              <span style={{ color: 'var(--color-ink-3)' }}>Ingested to graph</span>
              <span className="font-medium" style={{ color: 'var(--color-ink)' }}>
                {formatDate(retrievedAt)}
              </span>
            </div>
          )}
          {sourceUrl && (
            <a
              href={sourceUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 rounded-md px-3.5 py-2.5 transition-colors"
              style={{
                border: '1px solid var(--color-line)',
                background: 'var(--color-surface)',
                color: 'var(--color-ink-2)',
              }}
            >
              <ExternalLink size={12} />
              <span className="truncate">Open Source Document</span>
            </a>
          )}
        </div>
      </section>

      {/* Linked Intelligence Graph */}
      <section>
        <div className="mb-2 flex items-center justify-between gap-2">
          <span className="text-[12px] font-semibold" style={{ color: 'var(--color-ink)' }}>
            Linked Intelligence Graph
          </span>
          {graphFocus && (
            <button
              type="button"
              onClick={onOpenFocusedNodeInSearch}
              className="rounded-md px-3 py-1.5 text-[10px] transition-colors"
              style={{
                border: '1px solid var(--color-line)',
                background: 'var(--color-surface)',
                color: 'var(--color-ink-2)',
              }}
            >
              Open In Results
            </button>
          )}
        </div>
        {graphTrail.length > 0 && (
          <div className="mb-2 flex flex-wrap items-center gap-1">
            {graphTrail.map((node, index) => (
              <button
                key={`${node.type}-${node.id}`}
                type="button"
                onClick={() => onGraphTrailJump(node)}
                className="max-w-[11rem] truncate rounded-md px-3 py-1 text-[10px]"
                style={{
                  border:
                    graphFocus?.id === node.id && graphFocus.type === node.type
                      ? '1px solid var(--color-accent)'
                      : '1px solid var(--color-line)',
                  background:
                    graphFocus?.id === node.id && graphFocus.type === node.type
                      ? 'var(--color-accent-soft)'
                      : 'var(--color-surface)',
                  color:
                    graphFocus?.id === node.id && graphFocus.type === node.type
                      ? 'var(--color-ink)'
                      : 'var(--color-ink-3)',
                }}
              >
                {index + 1}. {node.label}
              </button>
            ))}
          </div>
        )}
        <div className="mb-2 flex items-center gap-2">
          <span className="text-[10px]" style={{ color: 'var(--color-ink-3)' }}>
            Edges
          </span>
          <select
            value={edgeTypeFilter}
            onChange={(e) => onEdgeTypeFilterChange(e.target.value)}
            className="rounded-md px-3 py-1.5 text-[10px] outline-none"
            style={{
              border: '1px solid var(--color-line)',
              background: 'var(--color-surface)',
              color: 'var(--color-ink-2)',
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
        {linkedGraphLoading && (
          <div
            className="flex items-center gap-2 rounded-md px-3.5 py-2.5 text-xs"
            style={{
              border: '1px solid var(--color-line)',
              background: 'var(--color-surface)',
              color: 'var(--color-ink-3)',
            }}
          >
            <Loader2 size={12} className="animate-spin" />
            Building linked graph...
          </div>
        )}
        {!linkedGraphLoading && linkedGraphError && (
          <div
            className="rounded-md px-3.5 py-2.5 text-xs"
            style={{
              border: '1px solid rgba(192, 57, 43, 0.25)',
              background: 'var(--color-red-soft)',
              color: 'var(--color-red)',
            }}
          >
            {linkedGraphError}
          </div>
        )}
        {!linkedGraphLoading && !linkedGraphError && linkedGraphNodes.length > 0 && (
          <div className="space-y-2">
            <div
              className="overflow-hidden rounded-md"
              style={{
                border: '1px solid var(--color-line)',
                background: 'var(--color-surface)',
              }}
            >
              <GraphMini
                nodes={linkedGraphNodes}
                edges={linkedGraphEdges}
                centerEntityId={graphFocus?.id ?? result.entity_id}
                height={220}
                onNodeClick={onGraphNodeSelect}
              />
            </div>
            <div
              tabIndex={0}
              onKeyDown={handleNeighborKeyDown}
              className="max-h-64 space-y-1.5 overflow-y-auto rounded-md p-1.5 outline-none"
              style={{ border: '1px solid var(--color-line)' }}
            >
              <div className="mb-1 px-1 text-[10px]" style={{ color: 'var(--color-ink-4)' }}>
                Use Up/Down and Enter to navigate neighbors
              </div>
              {linkedNeighbors.slice(0, 12).map((neighbor, index) => (
                <button
                  key={neighbor.key}
                  type="button"
                  onClick={() =>
                    onGraphNeighborFocus({ id: neighbor.id, type: neighbor.type, label: neighbor.label })
                  }
                  className="flex w-full items-center justify-between gap-2 rounded-md px-3 py-2.5 text-left text-xs transition-colors"
                  style={{
                    border:
                      index === neighborCursor
                        ? '1px solid var(--color-accent)'
                        : '1px solid var(--color-line)',
                    background:
                      index === neighborCursor ? 'var(--color-accent-soft)' : 'var(--color-surface)',
                    color: index === neighborCursor ? 'var(--color-ink)' : 'var(--color-ink-2)',
                  }}
                >
                  <span className="min-w-0">
                    <span className="block truncate font-medium" style={{ color: 'var(--color-ink)' }}>
                      {neighbor.label}
                    </span>
                    <span className="block truncate text-[10px]" style={{ color: 'var(--color-ink-4)' }}>
                      {neighbor.relation} - {prettyType(neighbor.nodeType)}
                    </span>
                  </span>
                  <span className="shrink-0 text-[10px]" style={{ color: 'var(--color-ink-3)' }}>
                    {neighbor.confidence}%
                  </span>
                </button>
              ))}
            </div>
          </div>
        )}
        {!linkedGraphLoading && !linkedGraphError && linkedGraphNodes.length === 0 && (
          <div
            className="rounded-md px-3.5 py-2.5 text-xs"
            style={{
              border: '1px solid var(--color-line)',
              background: 'var(--color-surface)',
              color: 'var(--color-ink-3)',
            }}
          >
            No linked nodes available for this record.
          </div>
        )}
      </section>

      {/* Related documents */}
      {relatedDocuments.length > 0 && (
        <section>
          <div className="mb-2 text-[12px] font-semibold" style={{ color: 'var(--color-ink)' }}>
            Related Documents
          </div>
          <div className="space-y-1.5">
            {relatedDocuments.slice(0, 4).map((link) => (
              <a
                key={link}
                href={link}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-2 rounded-md px-3.5 py-2.5 text-xs transition-colors"
                style={{
                  border: '1px solid var(--color-line)',
                  background: 'var(--color-surface)',
                  color: 'var(--color-ink-2)',
                }}
              >
                <ExternalLink size={12} />
                <span className="truncate">{link}</span>
              </a>
            ))}
          </div>
        </section>
      )}

      {/* Related graph nodes */}
      {relatedNodes.length > 0 && linkedNeighbors.length === 0 && (
        <section>
          <div className="mb-2 text-[12px] font-semibold" style={{ color: 'var(--color-ink)' }}>
            Related Graph Nodes
          </div>
          <div className="flex flex-wrap gap-1.5">
            {relatedNodes.slice(0, 8).map((node) => (
              <button
                key={`${node.key}-${node.value}`}
                type="button"
                onClick={() => onExploreNode(node.value)}
                className="rounded-md px-3 py-1.5 text-[11px] transition-colors"
                style={{
                  border: '1px solid var(--color-line)',
                  background: 'var(--color-surface)',
                  color: 'var(--color-ink-2)',
                }}
              >
                {node.label}: {truncateValue(node.value, 30)}
              </button>
            ))}
          </div>
        </section>
      )}

      {/* Metadata */}
      {metadataRows.length > 0 && (
        <section>
          <div className="text-[12px] font-semibold mb-2" style={{ color: 'var(--color-ink)' }}>
            Metadata
          </div>
          <div className="space-y-1.5 max-h-56 overflow-y-auto pr-0.5">
            {metadataRows.map(([key, value]) => (
              <div
                key={key}
                className="rounded-md px-3.5 py-2.5 text-xs"
                style={{
                  border: '1px solid var(--color-line)',
                  background: 'var(--color-surface)',
                }}
              >
                <div className="capitalize" style={{ color: 'var(--color-ink-3)' }}>
                  {prettyType(key)}
                </div>
                <div className="mt-0.5 font-medium break-words" style={{ color: 'var(--color-ink)' }}>
                  {String(value)}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Ask in Chat button */}
      <button
        onClick={() => onAskInChat(result)}
        className="btn-primary inline-flex w-full items-center justify-center gap-2 rounded-md px-3 py-2 text-xs font-medium transition-colors"
        style={{ color: '#fff' }}
      >
        <MessageSquare size={13} />
        Ask In Chat
      </button>

      {/* Expanded preview modal */}
      {previewModalOpen && (
        <div
          className="fixed inset-0 z-[80] flex items-center justify-center p-4"
          style={{ background: 'rgba(10, 10, 11, 0.4)' }}
          onClick={() => setPreviewModalOpen(false)}
        >
          <div
            className="w-full max-w-5xl rounded-md p-6"
            style={{
              border: '1px solid var(--color-line)',
              background: 'var(--color-surface)',
              boxShadow: 'var(--shadow-xl)',
            }}
            onClick={(event) => event.stopPropagation()}
          >
            <div className="mb-3 flex items-center justify-between gap-3">
              <div>
                <div className="text-sm font-semibold" style={{ color: 'var(--color-ink)' }}>
                  {result.title}
                </div>
                <div className="text-xs" style={{ color: 'var(--color-ink-3)' }}>
                  Full source preview
                </div>
              </div>
              <button
                type="button"
                onClick={() => setPreviewModalOpen(false)}
                className="rounded-md p-2 transition-colors"
                style={{
                  border: '1px solid var(--color-line)',
                  background: 'var(--color-surface)',
                  color: 'var(--color-ink-3)',
                }}
                aria-label="Close preview"
              >
                <X size={14} />
              </button>
            </div>
            <div
              className="max-h-[80vh] overflow-y-auto rounded-md px-4 py-3 text-sm leading-relaxed"
              style={{
                border: '1px solid var(--color-line)',
                background: 'var(--color-surface-2)',
                color: 'var(--color-ink-2)',
              }}
            >
              {databasePreview}
            </div>
          </div>
        </div>
      )}
    </aside>
  );
}
