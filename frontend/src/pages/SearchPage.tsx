import { cloneElement, isValidElement, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { motion } from 'framer-motion';
import {
  Search,
  Pill,
  Building2,
  FlaskConical,
  Dna,
  Target,
  BookOpen,
  Filter,
  X,
  Loader2,
  ChevronRight,
  ShieldCheck,
  Clock3,
  ExternalLink,
  MessageSquare,
  Network,
} from 'lucide-react';
import { api, type GraphEdge, type GraphNode, type SearchResult } from '../api';
import GraphMini from '../components/GraphMini';
import WorkspaceRail from '../components/WorkspaceRail';

interface Props {
  onBack: () => void;
  onChat: (prefill?: string) => void;
  onGraph: () => void;
  onCatalog: () => void;
}

type SearchViewMode = 'cards' | 'grid' | 'list';
type SortMode = 'relevance' | 'quality' | 'recent';
type GraphFocus = { id: string; type: string; label: string };

const ENTITY_TYPES = [
  { key: 'drug', label: 'Drugs', icon: <Pill size={14} /> },
  { key: 'trial', label: 'Trials', icon: <FlaskConical size={14} /> },
  { key: 'literature', label: 'Literature', icon: <BookOpen size={14} /> },
  { key: 'company', label: 'Companies', icon: <Building2 size={14} /> },
  { key: 'therapeutic_area', label: 'Therapeutic Areas', icon: <Target size={14} /> },
] as const;

const TYPE_CONFIG: Record<string, { color: string; bg: string; icon: ReactNode; label: string }> = {
  drug: { color: '#2563eb', bg: 'bg-blue-50', icon: <Pill size={20} />, label: 'Drug' },
  trial: { color: '#0d9488', bg: 'bg-teal-50', icon: <FlaskConical size={20} />, label: 'Trial' },
  literature: { color: '#16a34a', bg: 'bg-green-50', icon: <BookOpen size={20} />, label: 'Literature' },
  company: { color: '#d97706', bg: 'bg-amber-50', icon: <Building2 size={20} />, label: 'Company' },
  mechanism: { color: '#7c3aed', bg: 'bg-violet-50', icon: <Dna size={20} />, label: 'Mechanism' },
  therapeutic_area: { color: '#e11d48', bg: 'bg-rose-50', icon: <Target size={20} />, label: 'Therapeutic Area' },
};

const FILTER_CONFIG: Record<string, { activeBg: string; activeText: string }> = {
  drug: { activeBg: 'bg-blue-50', activeText: 'text-blue-700' },
  trial: { activeBg: 'bg-teal-50', activeText: 'text-teal-700' },
  literature: { activeBg: 'bg-green-50', activeText: 'text-green-700' },
  company: { activeBg: 'bg-amber-50', activeText: 'text-amber-700' },
  therapeutic_area: { activeBg: 'bg-rose-50', activeText: 'text-rose-700' },
};

const VIEW_OPTIONS: Array<{ value: SearchViewMode; label: string }> = [
  { value: 'cards', label: 'Cards' },
  { value: 'grid', label: 'Grid' },
  { value: 'list', label: 'List' },
];

const SORT_OPTIONS: Array<{ value: SortMode; label: string }> = [
  { value: 'relevance', label: 'Best match' },
  { value: 'quality', label: 'Highest quality' },
  { value: 'recent', label: 'Most recent' },
];
const PAGE_SIZE = 30;

export default function SearchPage({ onBack, onChat, onGraph, onCatalog }: Props) {
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

  const toggleFilter = useCallback((type: string) => {
    setActiveFilters((prev) => (prev.includes(type) ? prev.filter((item) => item !== type) : [...prev, type]));
  }, []);

  const toggleTherapeuticArea = useCallback((ta: string) => {
    setSelectedTherapeuticAreas((prev) => (
      prev.includes(ta) ? prev.filter((item) => item !== ta) : [...prev, ta]
    ));
  }, []);

  const doSearch = useCallback(async (searchQuery?: string, nextPage = 1) => {
    const q = (searchQuery ?? query).trim();
    if (!q || isLoading) return;
    const safePage = Math.max(1, nextPage);
    const offset = (safePage - 1) * PAGE_SIZE;

    setIsLoading(true);
    setHasSearched(true);

    try {
      const response = await api.search(q, activeFilters.length > 0 ? activeFilters : undefined, PAGE_SIZE, offset);
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
  }, [query, activeFilters, isLoading]);

  const selectResult = useCallback((result: SearchResult) => {
    setActiveResult(result);
    setActiveResultKey(resultFingerprint(result));
    if (typeof window !== 'undefined' && window.innerWidth < 1024) {
      window.requestAnimationFrame(() => {
        document.getElementById('search-result-inspector')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
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

  const sortedResults = useMemo(() => {
    const ranked = [...results];
    if (sortMode === 'quality') {
      ranked.sort((a, b) => (Number(b.quality_score ?? -1) - Number(a.quality_score ?? -1)));
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
    return sortedResults.filter((result) => (
      extractTherapeuticAreasFromResult(result)
        .map((value) => normalizeFacetValue(value))
        .some((value) => selected.has(value))
    ));
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

    void api.traverse(graphFocus.type, graphFocus.id, 2)
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

  const resultInsights = useMemo(() => {
    if (visibleResults.length === 0) {
      return {
        avgSimilarity: 0,
        avgQuality: null as number | null,
        highConfidence: 0,
        topSource: 'N/A',
        sourceBacked: 0,
      };
    }

    const avgSimilarity = Math.round((visibleResults.reduce((sum, item) => sum + item.similarity, 0) / visibleResults.length) * 100);
    const qualityValues = visibleResults
      .map((item) => item.quality_score)
      .filter((value): value is number => typeof value === 'number');
    const avgQuality = qualityValues.length > 0
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

    return {
      avgSimilarity,
      avgQuality,
      highConfidence,
      topSource,
      sourceBacked,
    };
  }, [visibleResults]);

  const edgeTypeOptions = useMemo(() => {
    if (!linkedGraph) return [];
    return [...new Set(linkedGraph.edges.map((edge) => edge.link_type))].sort((a, b) => a.localeCompare(b));
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

    const deduped = new Map<string, typeof rows[number]>();
    for (const row of rows) {
      const key = `${row.label.toLowerCase()}-${row.relation}`;
      if (!deduped.has(key)) deduped.set(key, row);
    }
    return [...deduped.values()];
  }, [graphFocus, linkedGraph, filteredGraphEdges]);

  const openChatWithResult = useCallback((result: SearchResult) => {
    onChat(`Tell me about ${result.title}`);
  }, [onChat]);

  const exploreNode = useCallback((nodeLabel: string) => {
    const nextQuery = nodeLabel.trim();
    if (!nextQuery) return;
    setQuery(nextQuery);
    void doSearch(nextQuery);
  }, [doSearch]);

  const handleGraphNodeSelect = useCallback((node: GraphNode) => {
    focusGraphNode({
      id: node.entity_id,
      type: node.entity_type,
      label: node.label,
    });
  }, [focusGraphNode]);

  const openFocusedNodeInSearch = useCallback(() => {
    if (!graphFocus) return;
    setQuery(graphFocus.label);
    void doSearch(graphFocus.label);
  }, [graphFocus, doSearch]);

  const totalPages = useMemo(() => Math.max(1, Math.ceil(totalResults / PAGE_SIZE)), [totalResults]);

  const goToPage = useCallback((nextPage: number) => {
    if (isLoading || nextPage < 1 || nextPage > totalPages) return;
    void doSearch(undefined, nextPage);
  }, [isLoading, totalPages, doSearch]);

  const activeVisibleIndex = useMemo(() => {
    if (!activeResultKey) return -1;
    return visibleResults.findIndex((result) => resultFingerprint(result) === activeResultKey);
  }, [visibleResults, activeResultKey]);

  const selectAdjacentResult = useCallback((delta: number) => {
    if (visibleResults.length === 0) return;
    const current = activeVisibleIndex >= 0 ? activeVisibleIndex : 0;
    const nextIndex = Math.min(Math.max(current + delta, 0), visibleResults.length - 1);
    const nextResult = visibleResults[nextIndex];
    if (nextResult) selectResult(nextResult);
  }, [visibleResults, activeVisibleIndex, selectResult]);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.25 }}
      className="workspace-canvas flex h-screen overflow-hidden"
    >
      <WorkspaceRail
        active="search"
        onBack={onBack}
        onSelect={(view) => {
          if (view === 'chat') {
            onChat();
            return;
          }
          if (view === 'graph') {
            onGraph();
            return;
          }
          if (view === 'catalog') {
            onCatalog();
          }
        }}
      />

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="shrink-0 border-b border-slate-200/70 bg-white/82 backdrop-blur-md">
          <div className="workspace-shell flex h-10 items-center justify-between px-6">
            <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">
              Search Workspace
            </div>
            <div className="inline-flex items-center gap-1.5 px-1 py-1 text-[11px] text-slate-600">
              <Network size={11} />
              ontology-aware retrieval
            </div>
          </div>
        </header>

        <div className={`workspace-canvas shrink-0 ${hasSearched ? 'pb-6 pt-6' : 'flex min-h-[68vh] items-center py-14'}`}>
          <div className="workspace-shell px-6">
            <div className="mx-auto w-full max-w-[1360px]">
              <div className="mb-8 text-center">
                <h1 className="text-[clamp(2.1rem,3.9vw,3.05rem)] font-semibold tracking-tight text-slate-900">
                  Search the Knowledge Graph
                </h1>
                <p className="mx-auto mt-3 max-w-3xl text-[16px] leading-relaxed text-slate-500">
                  Search with natural language, verify source trails, and follow connected nodes before opening deeper analysis.
                </p>
              </div>

            <div className="surface-panel rounded-lg px-6 py-6 sm:px-8 sm:py-8">
              <div className="mb-5 flex flex-wrap items-center justify-between gap-2.5 text-[12px] text-slate-600">
                <span className="chip-plain inline-flex items-center gap-1">
                  <Network size={11} />
                  Connected sources: {Math.max(uniqueSources, 0)}
                </span>
                {hasSearched && (
                  <span className="chip-plain inline-flex items-center gap-1">
                    Results: {selectedTherapeuticAreas.length > 0 ? `${visibleResults.length}/${totalResults}` : totalResults}
                  </span>
                )}
              </div>

              <div className="relative">
                <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">
                  Search query
                </div>
                <input
                  ref={inputRef}
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="e.g. semaglutide, heart failure SGLT2, empagliflozin trials, Novo Nordisk portfolio"
                  className="input-surface h-[74px] w-full rounded-lg pl-6 pr-[12.5rem] text-[18px] font-medium text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-4 focus:ring-brand/15 sm:pr-52"
                  autoFocus
                />
                <div className="absolute inset-y-0 right-0 flex items-center gap-2 pr-4">
                  {query && (
                    <button
                      onClick={() => {
                        setQuery('');
                        inputRef.current?.focus();
                      }}
                      className="rounded-md p-2.5 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600"
                      aria-label="Clear search"
                    >
                      <X size={18} />
                    </button>
                  )}
                  <button
                    onClick={() => void doSearch()}
                    disabled={!query.trim() || isLoading}
                    className="btn-search-gradient flex h-10 shrink-0 items-center gap-2 rounded-md px-5 text-sm font-semibold text-white transition-colors disabled:opacity-30"
                  >
                    {isLoading ? <Loader2 size={16} className="animate-spin" /> : <Search size={16} />}
                    Search
                  </button>
                </div>
              </div>

              <div className="mt-6 flex flex-wrap items-center justify-between gap-2.5">
                <div className="inline-flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">
                  <Filter size={14} />
                  Filters
                </div>
                <div className="flex flex-wrap items-center justify-end gap-2">
                  {ENTITY_TYPES.map((entityType) => {
                    const active = activeFilters.includes(entityType.key);
                    const cfg = FILTER_CONFIG[entityType.key];
                    return (
                      <button
                        key={entityType.key}
                        onClick={() => toggleFilter(entityType.key)}
                        className={`flex items-center gap-1.5 rounded-md border px-4 py-2 text-xs font-medium transition-all ${
                          active
                            ? `${cfg.activeBg} ${cfg.activeText} border-brand/25`
                            : 'border-slate-200 text-slate-500 hover:border-slate-300 hover:bg-white'
                        }`}
                      >
                        {entityType.icon}
                        {entityType.label}
                      </button>
                    );
                  })}
                  {activeFilters.length > 0 && (
                    <button
                      onClick={() => setActiveFilters([])}
                      className="rounded-md border border-slate-200 px-4 py-2 text-xs font-medium text-slate-500 transition-colors hover:border-slate-300 hover:bg-white hover:text-slate-700"
                    >
                      Clear all
                    </button>
                  )}
                </div>
              </div>

              {activeFilters.includes('therapeutic_area') && (
                <div className="mt-3 flex flex-wrap items-center justify-center gap-2">
                  <span className="rounded-md border border-rose-200 bg-rose-50 px-3 py-1.5 text-[11px] font-medium text-rose-700">
                    Select TA
                  </span>
                  {therapeuticAreaOptions.length === 0 && (
                    <span className="text-[11px] text-slate-500">No therapeutic-area tags available for this query yet.</span>
                  )}
                  {therapeuticAreaOptions.slice(0, 12).map((ta) => {
                    const active = selectedTherapeuticAreas.includes(ta);
                    return (
                      <button
                        key={ta}
                        type="button"
                        onClick={() => toggleTherapeuticArea(ta)}
                        className={`rounded-md border px-3 py-1.5 text-[11px] font-medium transition-colors ${
                          active
                            ? 'border-rose-200 bg-rose-100 text-rose-800'
                            : 'border-slate-200 text-slate-600 hover:border-slate-300 hover:bg-white'
                        }`}
                      >
                        {ta}
                      </button>
                    );
                  })}
                  {selectedTherapeuticAreas.length > 0 && (
                    <button
                      type="button"
                      onClick={() => setSelectedTherapeuticAreas([])}
                      className="rounded-md border border-slate-200 px-3 py-1.5 text-[11px] font-medium text-slate-500 transition-colors hover:border-slate-300 hover:bg-white hover:text-slate-700"
                    >
                      Clear TA
                    </button>
                  )}
                </div>
              )}

              <div className="mt-6 flex flex-wrap items-center justify-between gap-3 text-xs text-slate-500">
                <div>
                  Press <kbd className="rounded-md border border-slate-200 bg-white px-2.5 py-1 text-[10px] font-mono text-slate-500">Enter</kbd> to search
                </div>
                {hasSearched && totalResults > 0 && (
                  <div className="font-medium text-slate-600">
                    {selectedTherapeuticAreas.length > 0 ? `${visibleResults.length} shown` : `${totalResults} results`}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>

      <main className="workspace-canvas flex-1 overflow-y-auto px-6 pb-8">
        <div className="workspace-shell pt-6">
          {isLoading && (
            <div className="flex items-center justify-center py-20">
              <div className="animate-spin w-6 h-6 border-2 border-brand border-t-transparent rounded-full" />
              <span className="ml-3 text-sm text-slate-500">Searching knowledge graph...</span>
            </div>
          )}

          {!isLoading && hasSearched && results.length === 0 && (
            <div className="text-center py-20">
              <div className="mb-4 inline-flex h-16 w-16 items-center justify-center rounded-md border border-slate-200 bg-white/80">
                <Search size={28} className="text-slate-400" />
              </div>
              <p className="text-sm font-medium text-slate-700">No results found for "{query}"</p>
              <p className="text-xs text-slate-400 mt-1">Try broader keywords or remove filters.</p>
            </div>
          )}

          {!isLoading && hasSearched && results.length > 0 && visibleResults.length === 0 && (
            <div className="text-center py-16">
              <p className="text-sm font-medium text-slate-700">No results match the selected therapeutic areas.</p>
              <p className="mt-1 text-xs text-slate-500">Try different TA chips or clear the TA filter.</p>
            </div>
          )}

          {!isLoading && hasSearched && visibleResults.length > 0 && (
            <div className="space-y-4">
              <section className="card p-6">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex flex-wrap items-center gap-2">
                    {Array.from(resultTypeCounts.entries()).map(([type, count]) => (
                    <span key={type} className="chip-plain text-[11px] text-slate-500">
                      {prettyType(type)}: <span className="font-semibold text-slate-700">{count}</span>
                    </span>
                  ))}
                  <span className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-[11px] text-emerald-700">
                      {resultInsights.highConfidence} high-confidence
                    </span>
                  </div>

                  <div className="flex flex-wrap items-center gap-2">
                    <div className="inline-flex items-center rounded-md border border-slate-200 bg-white p-1">
                      {VIEW_OPTIONS.map((option) => (
                        <button
                          key={option.value}
                          type="button"
                          onClick={() => setViewMode(option.value)}
                          className={`rounded-md px-3 py-1.5 text-xs transition-colors ${
                            viewMode === option.value
                              ? 'bg-brand/10 font-semibold text-slate-900'
                              : 'text-slate-500 hover:bg-slate-50'
                          }`}
                        >
                          {option.label}
                        </button>
                      ))}
                    </div>
                    <select
                      value={sortMode}
                      onChange={(e) => setSortMode(e.target.value as SortMode)}
                      className="rounded-md border border-slate-200 bg-white px-3.5 py-1.5 text-xs text-slate-600 outline-none focus:ring-2 focus:ring-brand/10"
                      aria-label="Sort results"
                    >
                      {SORT_OPTIONS.map((option) => (
                        <option key={option.value} value={option.value}>{option.label}</option>
                      ))}
                    </select>
                    {totalPages > 1 && (
                      <div className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-1.5 py-1">
                        <button
                          type="button"
                          onClick={() => goToPage(page - 1)}
                          disabled={page <= 1 || isLoading}
                          className="rounded-md px-3 py-1 text-xs text-slate-600 transition-colors hover:bg-slate-50 disabled:opacity-40"
                        >
                          Prev
                        </button>
                        <span className="px-1 text-[11px] text-slate-500">Page {page}/{totalPages}</span>
                        <button
                          type="button"
                          onClick={() => goToPage(page + 1)}
                          disabled={page >= totalPages || isLoading}
                          className="rounded-md px-3 py-1 text-xs text-slate-600 transition-colors hover:bg-slate-50 disabled:opacity-40"
                        >
                          Next
                        </button>
                      </div>
                    )}
                  </div>
                </div>

                <div className="mt-4 grid grid-cols-2 gap-2 md:grid-cols-4">
                  <InsightTile label="Avg relevance" value={`${resultInsights.avgSimilarity}%`} />
                  <InsightTile
                    label="Avg quality"
                    value={resultInsights.avgQuality !== null ? `${resultInsights.avgQuality}%` : 'N/A'}
                  />
                  <InsightTile label="Top source" value={safeTileValue(resultInsights.topSource)} />
                  <InsightTile label="Source-backed" value={`${resultInsights.sourceBacked}/${visibleResults.length}`} />
                </div>
              </section>

              <div className={`grid grid-cols-1 gap-6 ${
                viewMode === 'list'
                  ? 'xl:grid-cols-[minmax(0,0.92fr)_minmax(640px,1.08fr)] 2xl:grid-cols-[minmax(0,0.95fr)_minmax(700px,1.05fr)]'
                  : 'xl:grid-cols-[minmax(0,1.08fr)_minmax(600px,0.92fr)] 2xl:grid-cols-[minmax(0,1.12fr)_minmax(660px,0.98fr)]'
              }`}>
                <div className={viewMode === 'grid' ? 'grid grid-cols-1 gap-3 md:grid-cols-2' : viewMode === 'list' ? 'overflow-hidden rounded-md border border-slate-200/75 bg-white/78 divide-y divide-slate-200/70' : 'space-y-3'}>
                  {visibleResults.map((result, index) => (
                    <SearchResultCard
                      key={`${resultFingerprint(result)}-${index}`}
                      result={result}
                      active={activeResultKey === resultFingerprint(result)}
                      onSelect={() => selectResult(result)}
                      mode={viewMode}
                    />
                  ))}
                </div>
                <ResultInspector
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
                  onGraphNeighborFocus={(neighbor) => focusGraphNode({ id: neighbor.id, type: neighbor.type, label: neighbor.label })}
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

function SearchResultCard({
  result,
  active,
  onSelect,
  mode,
}: {
  result: SearchResult;
  active: boolean;
  onSelect: () => void;
  mode: SearchViewMode;
}) {
  const cfg = TYPE_CONFIG[result.entity_type] ?? {
    color: '#94a3b8',
    bg: 'bg-slate-100',
    icon: <Search size={20} />,
    label: result.entity_type,
  };
  const sourceApi = String(result.provenance?.source_api ?? 'unknown source');
  const retrievedAt = result.provenance?.retrieved_at ? String(result.provenance.retrieved_at) : null;
  const sourcePublishedAt = getSourcePublicationDate(result.metadata);
  const previewSnippet = getResultSnippet(result);
  const similarity = (result.similarity * 100).toFixed(0);
  const quality = typeof result.quality_score === 'number' ? (result.quality_score * 100).toFixed(0) : null;
  const metadata = Object.entries(result.metadata ?? {})
    .filter(([, value]) => value !== null && value !== undefined && String(value).trim() !== '')
    .slice(0, mode === 'cards' ? 4 : 2);
  const compact = mode === 'list';
  const compactIcon = isValidElement(cfg.icon)
    ? cloneElement(cfg.icon, { size: 16 } as { size: number })
    : cfg.icon;

  if (compact) {
    return (
      <button
        type="button"
        onClick={onSelect}
        className={`group relative w-full text-left transition-colors ${
          active ? 'bg-brand/5' : 'bg-transparent hover:bg-slate-50/85'
        }`}
      >
        <span
          className={`absolute inset-y-0 left-0 w-[2px] bg-brand transition-opacity ${
            active ? 'opacity-100' : 'opacity-0 group-hover:opacity-60'
          }`}
          aria-hidden
        />
        <div className="flex items-start gap-3 px-4 py-3.5">
          <div
            className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-sm ${cfg.bg}`}
            style={{ color: cfg.color }}
          >
            {compactIcon}
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <h3 className="truncate text-[14px] font-semibold text-slate-900">{result.title}</h3>
                <div className="mt-1 flex flex-wrap items-center gap-1.5">
                  <span
                    className={`inline-flex items-center gap-1 rounded-sm px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide ${cfg.bg}`}
                    style={{ color: cfg.color }}
                  >
                    {cfg.label}
                  </span>
                  <span className="chip-plain max-w-[12rem] truncate text-[11px] text-slate-500">{sourceApi}</span>
                </div>
              </div>
              <div className="shrink-0 text-right">
                <div className="text-[12px] font-semibold text-slate-900">{similarity}%</div>
                <div className="text-[10px] uppercase tracking-wide text-slate-500">match</div>
              </div>
            </div>

            {previewSnippet && (
              <p className="mt-2 line-clamp-2 text-[12px] leading-relaxed text-slate-600">
                {previewSnippet}
              </p>
            )}

            <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
              {quality && (
                <span className="inline-flex items-center gap-1 rounded-sm border border-green-200 bg-green-50 px-2.5 py-0.5 text-green-700">
                  quality {quality}%
                </span>
              )}
              {sourcePublishedAt && (
                <span className="inline-flex items-center gap-1 rounded-sm border border-slate-200 bg-white px-2.5 py-0.5">
                  <Clock3 size={11} />
                  Source {formatDate(sourcePublishedAt)}
                </span>
              )}
              {retrievedAt && (
                <span className="inline-flex items-center gap-1 rounded-sm border border-slate-200 bg-white px-2.5 py-0.5">
                  <Clock3 size={11} />
                  Ingested {formatDate(retrievedAt)}
                </span>
              )}
            </div>
          </div>
          <ChevronRight size={16} className={`shrink-0 text-slate-300 transition-transform ${active ? 'translate-x-0.5' : 'group-hover:translate-x-0.5'}`} />
        </div>
      </button>
    );
  }

  return (
    <button
      type="button"
      onClick={onSelect}
      className={`group w-full border border-slate-200/70 bg-white/80 text-left transition-all ${
        mode === 'grid' ? 'min-h-[206px]' : ''
      } ${
        active ? 'border-brand/30 bg-white shadow-sm' : 'hover:border-slate-300 hover:bg-white'
      }`}
    >
      <div className="flex items-start gap-4 p-5">
        <div
          className={`flex shrink-0 items-center justify-center rounded-sm ${cfg.bg} ${mode === 'grid' ? 'h-10 w-10' : 'h-11 w-11'}`}
          style={{ color: cfg.color }}
        >
          {mode === 'grid' ? compactIcon : cfg.icon}
        </div>
        <div className="min-w-0 flex-1">
          <div className="mb-1.5 flex items-center gap-2.5">
            <h3 className="truncate text-[15px] font-semibold text-slate-900">{result.title}</h3>
            <span
              className={`shrink-0 inline-flex items-center gap-1 rounded-sm px-3 py-1 text-[10px] font-medium uppercase tracking-wide ${cfg.bg}`}
              style={{ color: cfg.color }}
            >
              {cfg.label}
            </span>
          </div>

          {previewSnippet && (
            <p className={`leading-relaxed text-slate-600 ${mode === 'grid' ? 'line-clamp-2 text-[12px]' : 'line-clamp-4 text-[13px]'}`}>
              {previewSnippet}
            </p>
          )}

          <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
            <span className="inline-flex items-center gap-1 rounded-sm border border-slate-200 bg-white px-3 py-1">
              <ShieldCheck size={11} />
              {similarity}% match
            </span>
            {quality && (
              <span className="inline-flex items-center gap-1 rounded-sm border border-green-200 bg-green-50 px-3 py-1 text-green-700">
                quality {quality}%
              </span>
            )}
            <span className="chip-plain inline-flex max-w-[12rem] items-center gap-1 truncate px-1 py-1">
              {sourceApi}
            </span>
            {sourcePublishedAt && (
              <span className="inline-flex items-center gap-1 rounded-sm border border-slate-200 bg-white px-3 py-1">
                <Clock3 size={11} />
                Source {formatDate(sourcePublishedAt)}
              </span>
            )}
            {retrievedAt && (
              <span className="inline-flex items-center gap-1 rounded-sm border border-slate-200 bg-white px-3 py-1">
                <Clock3 size={11} />
                Ingested {formatDate(retrievedAt)}
              </span>
            )}
          </div>

          {mode === 'cards' && metadata.length > 0 && (
            <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1">
              {metadata.map(([key, value]) => (
                <span key={key} className="inline-flex items-center text-xs text-slate-500">
                  <span className="font-medium text-slate-600 capitalize">{prettyType(key)}:</span>
                  <span className="ml-1">{truncateValue(value, 34)}</span>
                </span>
              ))}
            </div>
          )}
        </div>
        <div className="shrink-0 pt-1">
          <ChevronRight size={16} className={`text-slate-300 transition-transform ${active ? 'translate-x-0.5' : 'group-hover:translate-x-0.5'}`} />
        </div>
      </div>
    </button>
  );
}

function ResultInspector({
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
}: {
  result: SearchResult | null;
  activeResultIndex: number;
  totalVisibleResults: number;
  onPrevResult: () => void;
  onNextResult: () => void;
  onAskInChat: (result: SearchResult) => void;
  onExploreNode: (nodeLabel: string) => void;
  linkedGraphLoading: boolean;
  linkedGraphError: string | null;
  linkedNeighbors: Array<{ key: string; id: string; type: string; label: string; nodeType: string; relation: string; confidence: number }>;
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
}) {
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

  if (!result) {
    return (
      <aside id="search-result-inspector" className="h-fit card p-6 lg:sticky lg:top-4 lg:max-h-[calc(100vh-5rem)] lg:overflow-y-auto">
        <div className="text-[15px] font-semibold text-slate-900 mb-2">Result Details</div>
        <p className="text-xs text-slate-500">Select a result to inspect its source, quality, and metadata.</p>
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

  const handleNeighborKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
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
  };

  return (
    <aside id="search-result-inspector" className="h-fit card space-y-4 p-6 lg:sticky lg:top-4 lg:max-h-[calc(100vh-5rem)] lg:overflow-y-auto">
      <div>
        <div className="text-[11px] uppercase tracking-[0.14em] text-slate-400 font-semibold">Selected Result</div>
        <h3 className="mt-1 text-[15px] font-semibold text-slate-900 leading-relaxed">{result.title}</h3>
        <div className="mt-1 text-xs text-slate-500 capitalize">{prettyType(result.entity_type)}</div>
        {totalVisibleResults > 1 && (
          <div className="mt-2 flex items-center gap-2">
            <button
              type="button"
              onClick={onPrevResult}
              disabled={activeResultIndex <= 0}
              className="rounded-md border border-slate-200 bg-white px-3 py-1 text-[11px] text-slate-600 transition-colors hover:border-slate-300 hover:bg-slate-50 disabled:opacity-40"
            >
              Prev
            </button>
            <span className="text-[11px] text-slate-500">
              {Math.max(activeResultIndex + 1, 1)} of {totalVisibleResults}
            </span>
            <button
              type="button"
              onClick={onNextResult}
              disabled={activeResultIndex < 0 || activeResultIndex >= totalVisibleResults - 1}
              className="rounded-md border border-slate-200 bg-white px-3 py-1 text-[11px] text-slate-600 transition-colors hover:border-slate-300 hover:bg-slate-50 disabled:opacity-40"
            >
              Next
            </button>
          </div>
        )}
      </div>

      {previewSnippet && (
        <div className="rounded-md border border-slate-200/80 bg-white/74 px-4 py-3 text-xs leading-relaxed text-slate-600">
          {previewSnippet}
        </div>
      )}

      <section>
        <div className="mb-2 flex items-center justify-between gap-2">
          <span className="text-[12px] font-semibold text-slate-800">Database Preview</span>
          <button
            type="button"
            onClick={() => setPreviewModalOpen(true)}
            className="rounded-md border border-slate-200 bg-white px-3 py-1 text-[10px] text-slate-600 transition-colors hover:border-slate-300 hover:bg-slate-50"
          >
            Expand
          </button>
        </div>
        <div className="max-h-96 overflow-y-auto rounded-md border border-slate-200/80 bg-white/74 px-4 py-3 text-xs leading-relaxed text-slate-600">
          {databasePreview}
        </div>
      </section>

      <div className="space-y-1.5">
        <div className="flex items-center justify-between text-xs">
          <span className="text-slate-500 inline-flex items-center gap-1"><ShieldCheck size={12} /> Similarity</span>
          <span className="font-semibold text-slate-900">{similarityPct}%</span>
        </div>
        <div className="h-1.5 rounded-full bg-slate-100 overflow-hidden">
          <div className="h-full bg-brand" style={{ width: `${Math.min(similarityPct, 100)}%` }} />
        </div>
        {qualityPct !== null && (
          <>
            <div className="flex items-center justify-between text-xs">
              <span className="text-slate-500">Quality score</span>
              <span className="font-semibold text-slate-900">{qualityPct}%</span>
            </div>
            <div className="h-1.5 rounded-full bg-slate-100 overflow-hidden">
              <div className="h-full bg-green-500" style={{ width: `${Math.min(qualityPct, 100)}%` }} />
            </div>
          </>
        )}
      </div>

      <section>
        <div className="text-[12px] font-semibold text-slate-800 mb-2">Source Information</div>
        <div className="space-y-1.5 text-xs">
          <div className="flex items-center justify-between gap-4 rounded-md border border-slate-200/80 bg-white/74 px-3.5 py-2.5">
            <span className="text-slate-500">Source API</span>
            <span className="font-medium text-slate-800 truncate">{sourceApi}</span>
          </div>
          {sourcePublishedAt && (
            <div className="flex items-center justify-between gap-4 rounded-md border border-slate-200/80 bg-white/74 px-3.5 py-2.5">
              <span className="text-slate-500">Source publication</span>
              <span className="font-medium text-slate-800">{formatDate(sourcePublishedAt)}</span>
            </div>
          )}
          {retrievedAt && (
            <div className="flex items-center justify-between gap-4 rounded-md border border-slate-200/80 bg-white/74 px-3.5 py-2.5">
              <span className="text-slate-500">Ingested to graph</span>
              <span className="font-medium text-slate-800">{formatDate(retrievedAt)}</span>
            </div>
          )}
          {sourceUrl && (
            <a
              href={sourceUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 rounded-md border border-slate-200/80 bg-white/74 px-3.5 py-2.5 text-slate-600 transition-colors hover:border-slate-300 hover:bg-white"
            >
              <ExternalLink size={12} />
              <span className="truncate">Open Source Document</span>
            </a>
          )}
        </div>
      </section>

      <section>
        <div className="mb-2 flex items-center justify-between gap-2">
          <span className="text-[12px] font-semibold text-slate-800">Linked Intelligence Graph</span>
          {graphFocus && (
            <button
              type="button"
              onClick={onOpenFocusedNodeInSearch}
              className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-[10px] text-slate-600 transition-colors hover:border-slate-300 hover:bg-slate-50"
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
                className={`max-w-[11rem] truncate rounded-md border px-3 py-1 text-[10px] ${
                  graphFocus?.id === node.id && graphFocus.type === node.type
                    ? 'border-brand/30 bg-brand/10 text-slate-900'
                    : 'border-slate-200 bg-white text-slate-500 hover:border-slate-300 hover:bg-slate-50'
                }`}
              >
                {index + 1}. {node.label}
              </button>
            ))}
          </div>
        )}
        <div className="mb-2 flex items-center gap-2">
          <span className="text-[10px] text-slate-500">Edges</span>
          <select
            value={edgeTypeFilter}
            onChange={(e) => onEdgeTypeFilterChange(e.target.value)}
            className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-[10px] text-slate-600 outline-none focus:ring-2 focus:ring-brand/10"
          >
            <option value="all">All link types</option>
            {edgeTypeOptions.map((type) => (
              <option key={type} value={type}>{prettyType(type)}</option>
            ))}
          </select>
        </div>
        {linkedGraphLoading && (
          <div className="flex items-center gap-2 rounded-md border border-slate-200/80 bg-white/74 px-3.5 py-2.5 text-xs text-slate-500">
            <Loader2 size={12} className="animate-spin" />
            Building linked graph...
          </div>
        )}
        {!linkedGraphLoading && linkedGraphError && (
          <div className="rounded-md border border-rose-200 bg-rose-50 px-3.5 py-2.5 text-xs text-rose-700">
            {linkedGraphError}
          </div>
        )}
        {!linkedGraphLoading && !linkedGraphError && linkedGraphNodes.length > 0 && (
          <div className="space-y-2">
            <div className="overflow-hidden rounded-md border border-slate-200/80 bg-white/74">
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
              className="max-h-64 space-y-1.5 overflow-y-auto rounded-md border border-slate-200/80 p-1.5 outline-none focus:bg-brand/5 focus:ring-2 focus:ring-brand/20"
            >
              <div className="mb-1 px-1 text-[10px] text-slate-400">
                Use Up/Down and Enter to navigate neighbors
              </div>
              {linkedNeighbors.slice(0, 12).map((neighbor, index) => (
                <button
                  key={neighbor.key}
                  type="button"
                  onClick={() => onGraphNeighborFocus({ id: neighbor.id, type: neighbor.type, label: neighbor.label })}
                  className={`flex w-full items-center justify-between gap-2 rounded-md border px-3 py-2.5 text-left text-xs transition-colors ${
                    index === neighborCursor
                      ? 'border-brand/30 bg-brand/10 text-slate-900'
                      : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300 hover:bg-slate-50'
                  }`}
                >
                  <span className="min-w-0">
                    <span className="block truncate font-medium text-slate-800">{neighbor.label}</span>
                    <span className="block truncate text-[10px] text-slate-400">
                      {neighbor.relation} - {prettyType(neighbor.nodeType)}
                    </span>
                  </span>
                  <span className="shrink-0 text-[10px] text-slate-500">{neighbor.confidence}%</span>
                </button>
              ))}
            </div>
          </div>
        )}
        {!linkedGraphLoading && !linkedGraphError && linkedGraphNodes.length === 0 && (
          <div className="rounded-md border border-slate-200/80 bg-white/74 px-3.5 py-2.5 text-xs text-slate-500">
            No linked nodes available for this record.
          </div>
        )}
      </section>

      {relatedDocuments.length > 0 && (
        <section>
          <div className="mb-2 text-[12px] font-semibold text-slate-800">Related Documents</div>
          <div className="space-y-1.5">
            {relatedDocuments.slice(0, 4).map((link) => (
              <a
                key={link}
                href={link}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-2 rounded-md border border-slate-200/80 bg-white/74 px-3.5 py-2.5 text-xs text-slate-600 transition-colors hover:border-slate-300 hover:bg-white"
              >
                <ExternalLink size={12} />
                <span className="truncate">{link}</span>
              </a>
            ))}
          </div>
        </section>
      )}

      {relatedNodes.length > 0 && linkedNeighbors.length === 0 && (
        <section>
          <div className="mb-2 text-[12px] font-semibold text-slate-800">Related Graph Nodes</div>
          <div className="flex flex-wrap gap-1.5">
            {relatedNodes.slice(0, 8).map((node) => (
              <button
                key={`${node.key}-${node.value}`}
                type="button"
                onClick={() => onExploreNode(node.value)}
                className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-[11px] text-slate-600 transition-colors hover:border-slate-300 hover:bg-slate-50 hover:text-slate-900"
              >
                {node.label}: {truncateValue(node.value, 30)}
              </button>
            ))}
          </div>
        </section>
      )}

      {metadataRows.length > 0 && (
        <section>
          <div className="text-[12px] font-semibold text-slate-800 mb-2">Metadata</div>
          <div className="space-y-1.5 max-h-56 overflow-y-auto pr-0.5">
            {metadataRows.map(([key, value]) => (
              <div key={key} className="rounded-md border border-slate-200/80 bg-white/74 px-3.5 py-2.5 text-xs">
                <div className="text-slate-500 capitalize">{prettyType(key)}</div>
                <div className="mt-0.5 font-medium text-slate-800 break-words">{String(value)}</div>
              </div>
            ))}
          </div>
        </section>
      )}

      <button
        onClick={() => onAskInChat(result)}
        className="btn-primary inline-flex w-full items-center justify-center gap-2 rounded-md px-3 py-2 text-xs font-medium text-white transition-colors"
      >
        <MessageSquare size={13} />
        Ask In Chat
      </button>

      {previewModalOpen && (
        <div
          className="fixed inset-0 z-[80] flex items-center justify-center bg-slate-900/40 p-4"
          onClick={() => setPreviewModalOpen(false)}
        >
          <div
            className="w-full max-w-5xl rounded-md border border-slate-200 bg-white p-6 shadow-2xl"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="mb-3 flex items-center justify-between gap-3">
              <div>
                <div className="text-sm font-semibold text-slate-900">{result.title}</div>
                <div className="text-xs text-slate-500">Full source preview</div>
              </div>
              <button
                type="button"
                onClick={() => setPreviewModalOpen(false)}
                className="rounded-md border border-slate-200 bg-white p-2 text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-700"
                aria-label="Close preview"
              >
                <X size={14} />
              </button>
            </div>
            <div className="max-h-[80vh] overflow-y-auto rounded-md border border-slate-200 bg-slate-50/80 px-4 py-3 text-sm leading-relaxed text-slate-700">
              {databasePreview}
            </div>
          </div>
        </div>
      )}
    </aside>
  );
}

function InsightTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-slate-200/80 bg-white/74 px-3.5 py-3">
      <div className="text-[10px] font-medium uppercase tracking-wide text-slate-400">{label}</div>
      <div className="mt-1 truncate text-[13px] font-semibold text-slate-900">{value}</div>
    </div>
  );
}

function prettyType(value: string): string {
  return value.replace(/_/g, ' ').toLowerCase();
}

function truncateValue(value: unknown, limit: number): string {
  const asText = String(value);
  return asText.length > limit ? `${asText.slice(0, limit - 2)}..` : asText;
}

function formatDate(value: unknown): string {
  const date = new Date(String(value));
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}

function normalizeFacetValue(value: string): string {
  return value.trim().toLowerCase().replace(/[\s_-]+/g, ' ');
}

function extractTherapeuticAreasFromResult(result: SearchResult): string[] {
  const values: string[] = [];
  if (result.entity_type === 'therapeutic_area') {
    values.push(result.title);
  }
  const keys = ['therapeutic_area', 'therapeutic_area_name', 'therapy_area', 'indication', 'disease_area'];
  for (const key of keys) {
    const raw = result.metadata?.[key];
    if (typeof raw === 'string') {
      const chunks = raw.split(/[;,|]/).map((item) => item.trim()).filter(Boolean);
      values.push(...chunks);
    }
    if (Array.isArray(raw)) {
      values.push(...raw.filter((item): item is string => typeof item === 'string').map((item) => item.trim()).filter(Boolean));
    }
  }
  const deduped = new Map<string, string>();
  for (const value of values) {
    const normalized = normalizeFacetValue(value);
    if (!normalized) continue;
    if (!deduped.has(normalized)) deduped.set(normalized, value);
  }
  return [...deduped.values()];
}

function getResultSnippet(result: SearchResult): string | null {
  const primarySnippet = typeof result.snippet === 'string' ? result.snippet.trim() : '';
  if (primarySnippet && primarySnippet.toLowerCase() !== result.title.trim().toLowerCase()) {
    return truncateValue(primarySnippet, 220);
  }

  const fallbackKeys = ['description', 'summary', 'abstract', 'content', 'text', 'narrative', 'excerpt'];
  for (const key of fallbackKeys) {
    const value = result.metadata?.[key];
    if (typeof value === 'string') {
      const normalized = value.trim();
      if (normalized.length > 18 && !/^https?:\/\//i.test(normalized)) {
        return truncateValue(normalized, 220);
      }
    }
    if (Array.isArray(value)) {
      const merged = value.filter((item): item is string => typeof item === 'string').join(' ').trim();
      if (merged.length > 18) return truncateValue(merged, 220);
    }
  }

  return null;
}

function getSourcePublicationDate(metadata: Record<string, unknown> | undefined): string | null {
  if (!metadata) return null;
  const dateKeys = [
    'publication_date',
    'published_at',
    'published_date',
    'date_published',
    'article_date',
    'source_date',
  ];
  for (const key of dateKeys) {
    const normalized = normalizeDateValue(metadata[key]);
    if (normalized) return normalized;
  }
  return null;
}

function normalizeDateValue(value: unknown): string | null {
  if (typeof value === 'string') {
    const text = value.trim();
    if (!text) return null;
    const timestamp = Date.parse(text);
    return Number.isNaN(timestamp) ? null : text;
  }
  if (typeof value === 'number' && Number.isFinite(value)) {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? null : date.toISOString();
  }
  return null;
}

function resultFingerprint(result: SearchResult): string {
  return [
    result.entity_id,
    result.entity_type,
    result.title,
    result.provenance?.source_api ?? '',
    result.provenance?.retrieved_at ?? '',
    result.similarity.toFixed(6),
  ].join('|');
}

function toTimestamp(value: unknown): number {
  if (!value) return 0;
  const ts = new Date(String(value)).getTime();
  return Number.isNaN(ts) ? 0 : ts;
}

function safeTileValue(value: string): string {
  return truncateValue(value, 26);
}

function extractPreviewContent(result: SearchResult): string {
  const candidates: string[] = [];
  if (result.snippet && result.snippet.trim().length > 0) {
    candidates.push(result.snippet.trim());
  }

  const preferredKeys = ['content', 'abstract', 'summary', 'description', 'text', 'narrative', 'excerpt'];
  for (const key of preferredKeys) {
    const value = result.metadata?.[key];
    if (typeof value === 'string' && value.trim().length > 0 && !/^https?:\/\//i.test(value.trim())) {
      candidates.push(value.trim());
    }
    if (Array.isArray(value)) {
      const merged = value.filter((item): item is string => typeof item === 'string').join(' ');
      if (merged.trim().length > 0) candidates.push(merged.trim());
    }
  }

  for (const value of Object.values(result.metadata ?? {})) {
    if (typeof value !== 'string') continue;
    const text = value.trim();
    if (!text || /^https?:\/\//i.test(text)) continue;
    candidates.push(text);
    if (candidates.length > 5) break;
  }

  const best = candidates.find((item) => item.length > 80) ?? candidates[0] ?? '';
  if (!best) return 'No content preview available in indexed data for this result.';
  return truncateValue(best, 760);
}

function getRelatedDocuments(result: SearchResult): string[] {
  const urls = new Set<string>();
  const sourceUrl = result.provenance?.source_url;
  if (typeof sourceUrl === 'string') {
    extractUrls(sourceUrl, urls);
  }

  for (const value of Object.values(result.metadata ?? {})) {
    if (typeof value === 'string') {
      extractUrls(value, urls);
      continue;
    }
    if (Array.isArray(value)) {
      for (const item of value) {
        if (typeof item === 'string') extractUrls(item, urls);
      }
    }
  }
  return [...urls].slice(0, 6);
}

function getRelatedNodes(result: SearchResult): Array<{ key: string; label: string; value: string }> {
  const preferredKeys = [
    'drug_name',
    'company_name',
    'mechanism_name',
    'therapeutic_area',
    'trial_phase',
    'drug_id',
    'company_id',
    'mechanism_id',
    'therapeutic_area_id',
  ];
  const rows: Array<{ key: string; label: string; value: string }> = [];
  for (const key of preferredKeys) {
    const raw = result.metadata?.[key];
    if (raw === null || raw === undefined) continue;
    const text = String(raw).trim();
    if (!text || /^https?:\/\//i.test(text)) continue;
    rows.push({
      key,
      label: prettyType(key),
      value: text,
    });
  }
  if (rows.length === 0) {
    rows.push({
      key: 'title',
      label: 'entity',
      value: result.title,
    });
  }
  const unique = new Map<string, { key: string; label: string; value: string }>();
  for (const row of rows) {
    const dedupeKey = `${row.key}:${row.value.toLowerCase()}`;
    if (!unique.has(dedupeKey)) unique.set(dedupeKey, row);
  }
  return [...unique.values()];
}

function extractUrls(text: string, into: Set<string>) {
  const matches = text.match(/https?:\/\/[^\s,;]+/gi);
  if (!matches) return;
  for (const match of matches) {
    into.add(match.replace(/[)\].,]+$/, ''));
  }
}
