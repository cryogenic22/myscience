import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { motion } from 'framer-motion';
import { Search, X, Loader2, Network } from 'lucide-react';
import { api, type GraphEdge, type GraphNode, type SearchResult } from '../api';
import TopBar from '../components/layout/TopBar';
import type { TopBarTab } from '../components/layout/TopBar';
import SearchFilters, { ResultsToolbar } from '../components/search/SearchFilters';
import SearchResults, { InsightTile } from '../components/search/SearchResults';
import SearchPagination from '../components/search/SearchPagination';
import EntityPreview from '../components/search/EntityPreview';
import {
  type SearchViewMode,
  type SortMode,
  type GraphFocus,
  PAGE_SIZE,
  resultFingerprint,
  toTimestamp,
  safeTileValue,
  normalizeFacetValue,
  extractTherapeuticAreasFromResult,
  getRelatedDocuments,
  prettyType,
} from '../components/search/search-utils';

interface Props {
  onBack: () => void;
  onChat: (prefill?: string) => void;
  onGraph: () => void;
  onCatalog: () => void;
}

export default function SearchPage({ onBack, onChat, onGraph, onCatalog }: Props) {
  /* ── state ─────────────────────────────────────────────── */
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [activeResult, setActiveResult] = useState<SearchResult | null>(null);
  const [activeResultKey, setActiveResultKey] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [activeFilters, setActiveFilters] = useState<string[]>([]);
  const [hasSearched, setHasSearched] = useState(false);
  const [totalResults, setTotalResults] = useState(0);
  const [page, setPage] = useState(1);
  const [viewMode, setViewMode] = useState<SearchViewMode>('cards');
  const [sortMode, setSortMode] = useState<SortMode>('relevance');
  const [linkedGraph, setLinkedGraph] = useState<{ nodes: GraphNode[]; edges: GraphEdge[] } | null>(null);
  const [linkedGraphLoading, setLinkedGraphLoading] = useState(false);
  const [linkedGraphError, setLinkedGraphError] = useState<string | null>(null);
  const [graphFocus, setGraphFocus] = useState<GraphFocus | null>(null);
  const [graphTrail, setGraphTrail] = useState<GraphFocus[]>([]);
  const [edgeTypeFilter, setEdgeTypeFilter] = useState<string>('all');
  const [selectedTherapeuticAreas, setSelectedTherapeuticAreas] = useState<string[]>([]);
  const graphCacheRef = useRef<Map<string, { nodes: GraphNode[]; edges: GraphEdge[] }>>(new Map());
  const inputRef = useRef<HTMLInputElement>(null);

  /* ── callbacks ─────────────────────────────────────────── */
  const toggleFilter = useCallback((type: string) => {
    setActiveFilters((prev) =>
      prev.includes(type) ? prev.filter((item) => item !== type) : [...prev, type],
    );
  }, []);

  const toggleTherapeuticArea = useCallback((ta: string) => {
    setSelectedTherapeuticAreas((prev) =>
      prev.includes(ta) ? prev.filter((item) => item !== ta) : [...prev, ta],
    );
  }, []);

  const doSearch = useCallback(
    async (searchQuery?: string, nextPage = 1) => {
      const q = (searchQuery ?? query).trim();
      if (!q || isLoading) return;
      const safePage = Math.max(1, nextPage);
      const offset = (safePage - 1) * PAGE_SIZE;

      setIsLoading(true);
      setHasSearched(true);

      try {
        const response = await api.search(
          q,
          activeFilters.length > 0 ? activeFilters : undefined,
          PAGE_SIZE,
          offset,
        );
        setResults(response.results);
        setTotalResults(response.total);
        setPage(safePage);
        const first = response.results[0] ?? null;
        setActiveResult(first);
        setActiveResultKey(first ? resultFingerprint(first) : null);
      } catch (err) {
        console.error('Search failed:', err);
        setResults([]);
        setTotalResults(0);
        setPage(1);
        setActiveResult(null);
        setActiveResultKey(null);
      } finally {
        setIsLoading(false);
      }
    },
    [query, activeFilters, isLoading],
  );

  const selectResult = useCallback((result: SearchResult) => {
    setActiveResult(result);
    setActiveResultKey(resultFingerprint(result));
    if (typeof window !== 'undefined' && window.innerWidth < 1024) {
      window.requestAnimationFrame(() => {
        document
          .getElementById('search-result-inspector')
          ?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      });
    }
  }, []);

  const focusGraphNode = useCallback((node: GraphFocus) => {
    setGraphFocus((prev) => {
      if (prev?.id === node.id && prev.type === node.type) return prev;
      return node;
    });
    setGraphTrail((prev) => {
      const existing = prev.findIndex((item) => item.id === node.id && item.type === node.type);
      if (existing >= 0) return prev.slice(0, existing + 1);
      const next = [...prev, node];
      return next.slice(Math.max(0, next.length - 10));
    });
    setEdgeTypeFilter('all');
  }, []);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key !== 'Enter') return;
    e.preventDefault();
    void doSearch();
  };

  const openChatWithResult = useCallback(
    (result: SearchResult) => {
      onChat(`Tell me about ${result.title}`);
    },
    [onChat],
  );

  const exploreNode = useCallback(
    (nodeLabel: string) => {
      const nextQuery = nodeLabel.trim();
      if (!nextQuery) return;
      setQuery(nextQuery);
      void doSearch(nextQuery);
    },
    [doSearch],
  );

  const handleGraphNodeSelect = useCallback(
    (node: GraphNode) => {
      focusGraphNode({
        id: node.entity_id,
        type: node.entity_type,
        label: node.label,
      });
    },
    [focusGraphNode],
  );

  const openFocusedNodeInSearch = useCallback(() => {
    if (!graphFocus) return;
    setQuery(graphFocus.label);
    void doSearch(graphFocus.label);
  }, [graphFocus, doSearch]);

  const totalPages = useMemo(() => Math.max(1, Math.ceil(totalResults / PAGE_SIZE)), [totalResults]);

  const goToPage = useCallback(
    (nextPage: number) => {
      if (isLoading || nextPage < 1 || nextPage > totalPages) return;
      void doSearch(undefined, nextPage);
    },
    [isLoading, totalPages, doSearch],
  );

  const handleTabChange = useCallback(
    (tab: TopBarTab) => {
      if (tab === 'chat') { onChat(); return; }
      if (tab === 'graph') { onGraph(); return; }
      if (tab === 'catalog') { onCatalog(); return; }
    },
    [onChat, onGraph, onCatalog],
  );

  /* ── derived data ──────────────────────────────────────── */
  const sortedResults = useMemo(() => {
    const ranked = [...results];
    if (sortMode === 'quality') {
      ranked.sort((a, b) => Number(b.quality_score ?? -1) - Number(a.quality_score ?? -1));
      return ranked;
    }
    if (sortMode === 'recent') {
      ranked.sort((a, b) => {
        const aTs = toTimestamp(a.provenance?.retrieved_at);
        const bTs = toTimestamp(b.provenance?.retrieved_at);
        return bTs - aTs;
      });
      return ranked;
    }
    ranked.sort((a, b) => b.similarity - a.similarity);
    return ranked;
  }, [results, sortMode]);

  const therapeuticAreaOptions = useMemo(() => {
    const seen = new Set<string>();
    const values: string[] = [];
    for (const result of results) {
      for (const ta of extractTherapeuticAreasFromResult(result)) {
        const normalized = normalizeFacetValue(ta);
        if (!normalized || seen.has(normalized)) continue;
        seen.add(normalized);
        values.push(ta);
      }
    }
    return values.sort((a, b) => a.localeCompare(b));
  }, [results]);

  const visibleResults = useMemo(() => {
    if (selectedTherapeuticAreas.length === 0) return sortedResults;
    const selected = new Set(selectedTherapeuticAreas.map((value) => normalizeFacetValue(value)));
    return sortedResults.filter((result) =>
      extractTherapeuticAreasFromResult(result)
        .map((value) => normalizeFacetValue(value))
        .some((value) => selected.has(value)),
    );
  }, [sortedResults, selectedTherapeuticAreas]);

  const resultTypeCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const result of visibleResults) {
      counts.set(result.entity_type, (counts.get(result.entity_type) ?? 0) + 1);
    }
    return counts;
  }, [visibleResults]);

  const uniqueSources = useMemo(() => {
    const set = new Set<string>();
    for (const result of results) {
      const source = result.provenance?.source_api;
      if (source) set.add(String(source));
    }
    return set.size;
  }, [results]);

  const resultInsights = useMemo(() => {
    if (visibleResults.length === 0) {
      return { avgSimilarity: 0, avgQuality: null as number | null, highConfidence: 0, topSource: 'N/A', sourceBacked: 0 };
    }
    const avgSimilarity = Math.round(
      (visibleResults.reduce((sum, item) => sum + item.similarity, 0) / visibleResults.length) * 100,
    );
    const qualityValues = visibleResults
      .map((item) => item.quality_score)
      .filter((value): value is number => typeof value === 'number');
    const avgQuality =
      qualityValues.length > 0
        ? Math.round((qualityValues.reduce((sum, value) => sum + value, 0) / qualityValues.length) * 100)
        : null;
    const highConfidence = visibleResults.filter((item) => item.similarity >= 0.75).length;
    const sourceCount = new Map<string, number>();
    for (const result of visibleResults) {
      const source = String(result.provenance?.source_api ?? 'unknown source');
      sourceCount.set(source, (sourceCount.get(source) ?? 0) + 1);
    }
    const topSource = [...sourceCount.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] ?? 'N/A';
    const sourceBacked = visibleResults.filter((result) => getRelatedDocuments(result).length > 0).length;
    return { avgSimilarity, avgQuality, highConfidence, topSource, sourceBacked };
  }, [visibleResults]);

  const edgeTypeOptions = useMemo(() => {
    if (!linkedGraph) return [];
    return [...new Set(linkedGraph.edges.map((edge) => edge.link_type))].sort((a, b) =>
      a.localeCompare(b),
    );
  }, [linkedGraph]);

  const filteredGraphEdges = useMemo(() => {
    if (!linkedGraph) return [];
    if (edgeTypeFilter === 'all') return linkedGraph.edges;
    return linkedGraph.edges.filter((edge) => edge.link_type === edgeTypeFilter);
  }, [linkedGraph, edgeTypeFilter]);

  const filteredGraphNodes = useMemo(() => {
    if (!linkedGraph) return [];
    if (edgeTypeFilter === 'all') return linkedGraph.nodes;
    const ids = new Set<string>();
    if (graphFocus) ids.add(graphFocus.id);
    for (const edge of filteredGraphEdges) {
      ids.add(edge.source_id);
      ids.add(edge.target_id);
    }
    return linkedGraph.nodes.filter((node) => ids.has(node.entity_id));
  }, [linkedGraph, filteredGraphEdges, graphFocus, edgeTypeFilter]);

  const linkedNeighbors = useMemo(() => {
    if (!graphFocus || !linkedGraph) return [];
    const nodeById = new Map(linkedGraph.nodes.map((node) => [node.entity_id, node]));
    const rows = filteredGraphEdges
      .filter((edge) => edge.source_id === graphFocus.id || edge.target_id === graphFocus.id)
      .map((edge) => {
        const outgoing = edge.source_id === graphFocus.id;
        const otherId = outgoing ? edge.target_id : edge.source_id;
        const other = nodeById.get(otherId);
        return {
          key: `${otherId}-${edge.link_type}-${edge.confidence}`,
          id: otherId,
          type: other?.entity_type ?? 'unknown',
          label: other?.label ?? otherId,
          nodeType: other?.entity_type ?? 'unknown',
          relation: prettyType(edge.link_type),
          confidence: Math.round(edge.confidence * 100),
        };
      })
      .sort((a, b) => b.confidence - a.confidence);

    const deduped = new Map<string, (typeof rows)[number]>();
    for (const row of rows) {
      const key = `${row.label.toLowerCase()}-${row.relation}`;
      if (!deduped.has(key)) deduped.set(key, row);
    }
    return [...deduped.values()];
  }, [graphFocus, linkedGraph, filteredGraphEdges]);

  const activeVisibleIndex = useMemo(() => {
    if (!activeResultKey) return -1;
    return visibleResults.findIndex((result) => resultFingerprint(result) === activeResultKey);
  }, [visibleResults, activeResultKey]);

  const selectAdjacentResult = useCallback(
    (delta: number) => {
      if (visibleResults.length === 0) return;
      const current = activeVisibleIndex >= 0 ? activeVisibleIndex : 0;
      const nextIndex = Math.min(Math.max(current + delta, 0), visibleResults.length - 1);
      const nextResult = visibleResults[nextIndex];
      if (nextResult) selectResult(nextResult);
    },
    [visibleResults, activeVisibleIndex, selectResult],
  );

  /* ── effects ───────────────────────────────────────────── */
  useEffect(() => {
    if (!activeFilters.includes('therapeutic_area')) {
      setSelectedTherapeuticAreas([]);
    }
  }, [activeFilters]);

  useEffect(() => {
    const allowed = new Set(therapeuticAreaOptions.map((value) => normalizeFacetValue(value)));
    setSelectedTherapeuticAreas((prev) => {
      const next = prev.filter((value) => allowed.has(normalizeFacetValue(value)));
      return next.length === prev.length ? prev : next;
    });
  }, [therapeuticAreaOptions]);

  useEffect(() => {
    if (visibleResults.length === 0) {
      setActiveResult(null);
      setActiveResultKey(null);
      return;
    }
    const hasActive = activeResultKey
      ? visibleResults.some((result) => resultFingerprint(result) === activeResultKey)
      : false;
    if (!hasActive) {
      const first = visibleResults[0];
      setActiveResult(first);
      setActiveResultKey(resultFingerprint(first));
    }
  }, [visibleResults, activeResultKey]);

  useEffect(() => {
    if (!activeResult) {
      setGraphFocus(null);
      setGraphTrail([]);
      setEdgeTypeFilter('all');
      return;
    }
    const root: GraphFocus = {
      id: activeResult.entity_id,
      type: activeResult.entity_type,
      label: activeResult.title,
    };
    setGraphFocus(root);
    setGraphTrail([root]);
    setEdgeTypeFilter('all');
  }, [activeResult]);

  useEffect(() => {
    if (!graphFocus) {
      setLinkedGraph(null);
      setLinkedGraphError(null);
      setLinkedGraphLoading(false);
      return;
    }
    const cacheKey = `${graphFocus.type}:${graphFocus.id}`;
    const cached = graphCacheRef.current.get(cacheKey);
    if (cached) {
      setLinkedGraph(cached);
      setLinkedGraphError(null);
      setLinkedGraphLoading(false);
      return;
    }
    let canceled = false;
    setLinkedGraphLoading(true);
    setLinkedGraphError(null);
    void api
      .traverse(graphFocus.type, graphFocus.id, 2)
      .then((graph) => {
        if (canceled) return;
        graphCacheRef.current.set(cacheKey, graph);
        setLinkedGraph(graph);
      })
      .catch((err) => {
        if (canceled) return;
        setLinkedGraph(null);
        setLinkedGraphError(err instanceof Error ? err.message : 'Unable to load linked graph');
      })
      .finally(() => {
        if (!canceled) setLinkedGraphLoading(false);
      });
    return () => {
      canceled = true;
    };
  }, [graphFocus]);

  /* ── render ────────────────────────────────────────────── */
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.25 }}
      className="flex h-screen flex-col overflow-hidden"
      style={{ background: 'var(--color-bg)' }}
    >
      <TopBar
        onBack={onBack}
        activeTab="search"
        onTabChange={handleTabChange}
        breadcrumb="Search Workspace"
      />

      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        {/* Search area */}
        <div
          className={`shrink-0 ${hasSearched ? '' : 'flex flex-1 items-center justify-center'}`}
          style={{ minHeight: hasSearched ? undefined : 0 }}
        >
          <div
            className="mx-auto w-full"
            style={{ maxWidth: hasSearched ? '1360px' : '820px', padding: hasSearched ? '24px 24px 0' : '0 24px' }}
          >
            {/* Logo / title — Google-style, above the search bar */}
            {!hasSearched && (
              <div className="mb-10 text-center">
                <h1
                  className="font-display"
                  style={{
                    fontSize: '56px',
                    fontWeight: 300,
                    letterSpacing: '-0.03em',
                    color: 'var(--color-ink)',
                    lineHeight: 1.1,
                  }}
                >
                  Market Zero
                </h1>
                <p
                  className="mt-3 text-[14px]"
                  style={{ color: 'var(--color-ink-4)' }}
                >
                  Pharmaceutical intelligence search
                </p>
              </div>
            )}

            {/* Search input — Google-style, big rounded pill */}
            <div className="relative">
              <div
                className="flex items-center rounded-full"
                style={{
                  height: hasSearched ? '48px' : '56px',
                  background: 'var(--color-surface)',
                  boxShadow: hasSearched ? 'var(--shadow-xs)' : 'var(--shadow-sm)',
                  transition: 'box-shadow 200ms, height 200ms',
                  paddingLeft: '20px',
                  paddingRight: '8px',
                }}
                onMouseEnter={(e) => { if (!hasSearched) e.currentTarget.style.boxShadow = 'var(--shadow-md)'; }}
                onMouseLeave={(e) => { if (!hasSearched) e.currentTarget.style.boxShadow = 'var(--shadow-sm)'; }}
              >
                <Search size={18} style={{ color: 'var(--color-ink-4)', flexShrink: 0 }} />
                <input
                  ref={inputRef}
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Search drugs, trials, companies, mechanisms..."
                  className="flex-1 bg-transparent focus:outline-none"
                  style={{
                    fontSize: hasSearched ? '14px' : '16px',
                    color: 'var(--color-ink)',
                    padding: '0 16px',
                    height: '100%',
                    border: 'none',
                  }}
                  autoFocus
                />
                {query && (
                  <button
                    type="button"
                    onClick={() => {
                      setQuery('');
                      inputRef.current?.focus();
                    }}
                    className="rounded-full transition-colors"
                    style={{ padding: '8px', color: 'var(--color-ink-4)', flexShrink: 0 }}
                    aria-label="Clear search"
                  >
                    <X size={16} />
                  </button>
                )}
              </div>
            </div>

            {/* Action buttons — Google-style, centered below with spacing */}
            {!hasSearched && (
              <div className="mt-8 flex items-center justify-center gap-3">
                <button
                  type="button"
                  onClick={() => void doSearch()}
                  disabled={!query.trim() || isLoading}
                  className="rounded-lg text-[13px] font-medium transition-all disabled:opacity-30"
                  style={{
                    padding: '0 20px',
                    height: '38px',
                    color: 'var(--color-ink-2)',
                    background: 'var(--color-surface-2)',
                  }}
                >
                  {isLoading ? <Loader2 size={14} className="animate-spin" /> : 'Search'}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    const lucky = 'semaglutide competitive landscape';
                    setQuery(lucky);
                    void doSearch(lucky);
                  }}
                  className="rounded-lg text-[13px] font-medium transition-all"
                  style={{
                    padding: '0 20px',
                    height: '38px',
                    color: 'var(--color-ink-2)',
                    background: 'var(--color-surface-2)',
                  }}
                >
                  I'm Feeling Lucky
                </button>
              </div>
            )}

            {/* Searched state: inline search button */}
            {hasSearched && (
              <div className="mt-3 flex items-center justify-between">
                <div
                  className="text-[12px]"
                  style={{ color: 'var(--color-ink-3)' }}
                >
                  {totalResults > 0
                    ? selectedTherapeuticAreas.length > 0
                      ? `${visibleResults.length} of ${totalResults} results`
                      : `${totalResults} results`
                    : ''}
                </div>
              </div>
            )}

            {/* Filters — below buttons in empty state, below input when searched */}
            <div className={hasSearched ? 'mt-3' : 'mt-10'}>
              <SearchFilters
                activeTypes={activeFilters}
                onTypeToggle={toggleFilter}
                sortMode={sortMode}
                onSortChange={setSortMode}
                viewMode={viewMode}
                onViewChange={setViewMode}
                therapeuticAreaOptions={therapeuticAreaOptions}
                selectedTherapeuticAreas={selectedTherapeuticAreas}
                onTherapeuticAreaToggle={toggleTherapeuticArea}
                onClearTherapeuticAreas={() => setSelectedTherapeuticAreas([])}
              />
            </div>

            {/* Result count — only when searched */}
            {hasSearched && totalResults > 0 && (
              <div
                className="mt-3 text-[12px]"
                style={{ color: 'var(--color-ink-3)' }}
              >
                {selectedTherapeuticAreas.length > 0
                  ? `${visibleResults.length} of ${totalResults} results`
                  : `${totalResults} results`}
              </div>
            )}
          </div>
        </div>

        {/* Results area */}
        <main className="flex-1 overflow-y-auto" style={{ padding: '0 24px 32px' }}>
          <div className="mx-auto max-w-[1360px]" style={{ paddingTop: '24px' }}>
            {/* Loading / empty states */}
            {(isLoading || (hasSearched && visibleResults.length === 0)) && (
              <SearchResults
                results={[]}
                viewMode={viewMode}
                activeResultKey={null}
                onEntityClick={selectResult}
                isLoading={isLoading}
                hasSearched={hasSearched}
                query={query}
                totalResults={totalResults}
                visibleCount={visibleResults.length}
              />
            )}

            {/* Results grid */}
            {!isLoading && hasSearched && visibleResults.length > 0 && (
              <div className="space-y-4">
                <section className="card" style={{ padding: '24px' }}>
                  <ResultsToolbar
                    resultTypeCounts={resultTypeCounts}
                    highConfidenceCount={resultInsights.highConfidence}
                    viewMode={viewMode}
                    onViewChange={setViewMode}
                    sortMode={sortMode}
                    onSortChange={setSortMode}
                  />

                  <div className="mt-2 flex items-center justify-end">
                    <SearchPagination
                      page={page}
                      totalPages={totalPages}
                      onPageChange={goToPage}
                      disabled={isLoading}
                    />
                  </div>

                  <div className="mt-4 grid grid-cols-2 gap-2 md:grid-cols-4">
                    <InsightTile label="Avg relevance" value={`${resultInsights.avgSimilarity}%`} />
                    <InsightTile
                      label="Avg quality"
                      value={
                        resultInsights.avgQuality !== null
                          ? `${resultInsights.avgQuality}%`
                          : 'N/A'
                      }
                    />
                    <InsightTile
                      label="Top source"
                      value={safeTileValue(resultInsights.topSource)}
                    />
                    <InsightTile
                      label="Source-backed"
                      value={`${resultInsights.sourceBacked}/${visibleResults.length}`}
                    />
                  </div>
                </section>

                <div
                  className={`grid grid-cols-1 gap-6 ${
                    viewMode === 'list'
                      ? 'xl:grid-cols-[minmax(0,0.92fr)_minmax(640px,1.08fr)] 2xl:grid-cols-[minmax(0,0.95fr)_minmax(700px,1.05fr)]'
                      : 'xl:grid-cols-[minmax(0,1.08fr)_minmax(600px,0.92fr)] 2xl:grid-cols-[minmax(0,1.12fr)_minmax(660px,0.98fr)]'
                  }`}
                >
                  <SearchResults
                    results={visibleResults}
                    viewMode={viewMode}
                    activeResultKey={activeResultKey}
                    onEntityClick={selectResult}
                    isLoading={false}
                    hasSearched={true}
                    query={query}
                    totalResults={totalResults}
                    visibleCount={visibleResults.length}
                  />
                  <EntityPreview
                    result={activeResult}
                    activeResultIndex={activeVisibleIndex}
                    totalVisibleResults={visibleResults.length}
                    onPrevResult={() => selectAdjacentResult(-1)}
                    onNextResult={() => selectAdjacentResult(1)}
                    onAskInChat={openChatWithResult}
                    onExploreNode={exploreNode}
                    linkedGraphLoading={linkedGraphLoading}
                    linkedGraphError={linkedGraphError}
                    linkedNeighbors={linkedNeighbors}
                    linkedGraphNodes={filteredGraphNodes}
                    linkedGraphEdges={filteredGraphEdges}
                    graphFocus={graphFocus}
                    graphTrail={graphTrail}
                    edgeTypeFilter={edgeTypeFilter}
                    edgeTypeOptions={edgeTypeOptions}
                    onEdgeTypeFilterChange={setEdgeTypeFilter}
                    onGraphNodeSelect={handleGraphNodeSelect}
                    onGraphTrailJump={focusGraphNode}
                    onGraphNeighborFocus={(neighbor) =>
                      focusGraphNode({
                        id: neighbor.id,
                        type: neighbor.type,
                        label: neighbor.label,
                      })
                    }
                    onOpenFocusedNodeInSearch={openFocusedNodeInSearch}
                  />
                </div>
              </div>
            )}

            {!hasSearched && <div className="h-10" />}
          </div>
        </main>
      </div>
    </motion.div>
  );
}
