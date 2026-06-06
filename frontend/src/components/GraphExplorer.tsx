import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import {
  Building2,
  Compass,
  ExternalLink,
  FileText,
  FlaskConical,
  Link2,
  Loader2,
  Network,
  PanelLeftClose,
  PanelLeftOpen,
  Pill as PillIcon,
  Search,
  ShieldCheck,
  Target,
  Dna,
  Route,
  X,
} from 'lucide-react';
import {
  api,
  type EntityListItem,
  type EntitySummary,
  type GraphEdge,
  type GraphNode,
  type GraphPathResponse,
} from '../api';
import { displayName, LINK_TYPE_LABELS, SOURCE_LABELS, isUUID } from '../brand';
import KnowledgeGraph from './KnowledgeGraph';
import GraphContextMenu from './graph/GraphContextMenu';
import { NODE_COLORS } from './graph/graph-constants';
import { Drawer } from './ui/Drawer';
import ProvenanceCaption, { graphEdgeProvenanceCaption } from './canvas/ProvenanceCaption';

const ENTITY_CONFIG: Record<string, { icon: ReactNode; color: string; label: string }> = {
  drug: { icon: <PillIcon size={14} />, color: NODE_COLORS.drug, label: 'Drug' },
  company: { icon: <Building2 size={14} />, color: NODE_COLORS.company, label: 'Company' },
  trial: { icon: <FlaskConical size={14} />, color: NODE_COLORS.trial, label: 'Trial' },
  mechanism: { icon: <Dna size={14} />, color: NODE_COLORS.mechanism, label: 'Mechanism' },
  therapeutic_area: { icon: <Target size={14} />, color: NODE_COLORS.therapeutic_area, label: 'Therapeutic Area' },
  literature: { icon: <FileText size={14} />, color: NODE_COLORS.literature, label: 'Literature' },
};

const OBJECTIVES = [
  {
    id: 'adjacency',
    label: 'Entity Neighborhood',
    description: 'Inspect direct and second-order relationships around a selected node.',
    preferredTypes: [] as string[],
  },
  {
    id: 'trial_evidence',
    label: 'Trial Evidence Map',
    description: 'Prioritize trial and literature connections for evidence review.',
    preferredTypes: ['trial', 'drug', 'literature'],
  },
  {
    id: 'portfolio',
    label: 'Portfolio Network',
    description: 'Traverse company, drug, and trial connections for portfolio analysis.',
    preferredTypes: ['company', 'drug', 'trial'],
  },
  {
    id: 'mechanism',
    label: 'Mechanism Landscape',
    description: 'Trace mechanism-to-drug and therapeutic area link structure.',
    preferredTypes: ['mechanism', 'therapeutic_area', 'drug'],
  },
] as const;

type ObjectiveId = typeof OBJECTIVES[number]['id'];

interface GraphExplorerProps {
  /** Pre-load this entity on mount (from cross-module navigation) */
  initialEntity?: { id: string; type: string; label: string } | null;
  /** Pre-seed graph with nodes/edges from chat response */
  seedGraph?: { nodes: GraphNode[]; edges: GraphEdge[] } | null;
  /** Callback to inject a question into the chat input */
  onAskInChat?: (question: string) => void;
}

export default function GraphExplorer({ initialEntity, seedGraph, onAskInChat }: GraphExplorerProps = {}) {
  const [railCollapsed, setRailCollapsed] = useState(false);
  const [objective, setObjective] = useState<ObjectiveId>('adjacency');
  const [entityLookupQuery, setEntityLookupQuery] = useState('');
  const [suggestions, setSuggestions] = useState<(EntityListItem & { _type: string })[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [hops, setHops] = useState(2);
  const [nodeTypeFilter, setNodeTypeFilter] = useState<string>('all');
  const [linkTypeFilter, setLinkTypeFilter] = useState<string>('all');
  const [selectedEntity, setSelectedEntity] = useState<{ id: string; type: string; label: string } | null>(null);
  const [graphData, setGraphData] = useState<{ nodes: GraphNode[]; edges: GraphEdge[] } | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [entitySummary, setEntitySummary] = useState<EntitySummary | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [graphError, setGraphError] = useState<string | null>(null);
  const [quickNodeInsight, setQuickNodeInsight] = useState<NodeInsight | null>(null);
  const [showDemoBanner, setShowDemoBanner] = useState(!initialEntity);
  const [contextMenu, setContextMenu] = useState<{
    node: GraphNode;
    position: { x: number; y: number };
  } | null>(null);
  const suggestTimeoutRef = useRef<number>(0);

  // Path-finding mode state
  const [pathMode, setPathMode] = useState(false);
  const [pathFromQuery, setPathFromQuery] = useState('');
  const [pathToQuery, setPathToQuery] = useState('');
  const [pathFromEntity, setPathFromEntity] = useState<{ id: string; type: string; label: string } | null>(null);
  const [pathToEntity, setPathToEntity] = useState<{ id: string; type: string; label: string } | null>(null);
  const [pathFromSuggestions, setPathFromSuggestions] = useState<(EntityListItem & { _type: string })[]>([]);
  const [pathToSuggestions, setPathToSuggestions] = useState<(EntityListItem & { _type: string })[]>([]);
  const [showPathFromSuggestions, setShowPathFromSuggestions] = useState(false);
  const [showPathToSuggestions, setShowPathToSuggestions] = useState(false);
  const [pathLoading, setPathLoading] = useState(false);
  const [pathError, setPathError] = useState<string | null>(null);
  const [pathResult, setPathResult] = useState<GraphPathResponse | null>(null);
  const pathFromTimeoutRef = useRef<number>(0);
  const pathToTimeoutRef = useRef<number>(0);

  const autoLoadedRef = useRef(false);

  // Seed graph from chat response (overrides other init modes)
  useEffect(() => {
    if (!seedGraph || seedGraph.nodes.length === 0) return;
    setGraphData({ nodes: seedGraph.nodes, edges: seedGraph.edges });
    setShowDemoBanner(false);
    setGraphError(null);
    // Select the first node as the focal entity
    const focal = seedGraph.nodes[0];
    if (focal) {
      setSelectedEntity({ id: focal.entity_id, type: focal.entity_type, label: focal.label });
    }
    autoLoadedRef.current = true;
  }, [seedGraph]);

  // Auto-load: initialEntity prop (cross-module nav) or semaglutide demo on first visit
  useEffect(() => {
    if (autoLoadedRef.current) return;
    autoLoadedRef.current = true;

    if (initialEntity) {
      // Cross-module navigation — load the requested entity
      void loadGraph(initialEntity.id, initialEntity.type, initialEntity.label, 2);
      return;
    }

    // Demo mode — pre-render semaglutide neighbourhood
    void (async () => {
      try {
        const res = await api.listEntities('drug', 'semaglutide', 5);
        // Pick the best match — prefer exact "semaglutide" over combo drugs
        const best = res.results.find(r => r.label.toLowerCase() === 'semaglutide')
          ?? res.results.find(r => r.label.toLowerCase().startsWith('semaglutide'))
          ?? res.results[0];
        if (best) {
          void loadGraph(best.entity_id, 'drug', best.label, 1);
        }
      } catch { /* silently fail — empty state is still fine */ }
    })();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const activeObjective = useMemo(
    () => OBJECTIVES.find((item) => item.id === objective) ?? OBJECTIVES[0],
    [objective],
  );

  const handleLookupChange = useCallback((value: string) => {
    setEntityLookupQuery(value);
    clearTimeout(suggestTimeoutRef.current);
    if (value.length < 2) {
      setSuggestions([]);
      setShowSuggestions(false);
      return;
    }
    suggestTimeoutRef.current = window.setTimeout(async () => {
      try {
        const [drugs, companies, trials, mechanisms, therapeuticAreas] = await Promise.all([
          api.listEntities('drug', value, 4),
          api.listEntities('company', value, 4),
          api.listEntities('trial', value, 4),
          api.listEntities('mechanism', value, 3),
          api.listEntities('therapeutic_area', value, 3),
        ]);
        const all = [
          ...drugs.results.map((result) => ({ ...result, _type: 'drug' })),
          ...companies.results.map((result) => ({ ...result, _type: 'company' })),
          ...trials.results.map((result) => ({ ...result, _type: 'trial' })),
          ...mechanisms.results.map((result) => ({ ...result, _type: 'mechanism' })),
          ...therapeuticAreas.results.map((result) => ({ ...result, _type: 'therapeutic_area' })),
        ];
        setSuggestions(all.slice(0, 12));
        setShowSuggestions(all.length > 0);
      } catch {
        setSuggestions([]);
        setShowSuggestions(false);
      }
    }, 220);
  }, []);

  const loadGraph = useCallback(async (
    entityId: string,
    entityType: string,
    label: string,
    traversalHops = hops,
    options?: { openDetails?: boolean },
  ) => {
    setSelectedEntity({ id: entityId, type: entityType, label });
    setEntityLookupQuery(label);
    setShowSuggestions(false);
    setShowDemoBanner(false);
    setIsLoading(true);
    setSummaryLoading(true);
    if (options?.openDetails) setDrawerOpen(true);
    setEntitySummary(null);
    setLinkTypeFilter('all');
    setNodeTypeFilter('all');
    setGraphError(null);

    try {
      const [graph, summary] = await Promise.all([
        api.traverse(entityType, entityId, traversalHops),
        api.entitySummary(entityType, entityId).catch(() => null),
      ]);
      setGraphData(graph);
      setEntitySummary(summary);
    } catch (err) {
      console.error('Graph traversal failed:', err);
      setGraphData(null);
      setEntitySummary(null);
      setGraphError(err instanceof Error ? err.message : 'Unable to load graph data');
    } finally {
      setIsLoading(false);
      setSummaryLoading(false);
    }
  }, [hops]);

  const handleNodeClick = useCallback((node: GraphNode) => {
    setContextMenu(null);
    if (graphData) {
      setQuickNodeInsight(buildNodeInsight(node, graphData));
    }
    void loadGraph(node.entity_id, node.entity_type, node.label, hops);
  }, [graphData, hops, loadGraph]);

  const handleNodeContextMenu = useCallback((node: GraphNode, position: { x: number; y: number }) => {
    setContextMenu({ node, position });
  }, []);

  const handleContextMenuClose = useCallback(() => {
    setContextMenu(null);
  }, []);

  // -- Path-finding helpers --

  const searchEntitiesForPath = useCallback((
    value: string,
    setSuggestions: (s: (EntityListItem & { _type: string })[]) => void,
    setShowSuggestions: (s: boolean) => void,
    timeoutRef: React.MutableRefObject<number>,
  ) => {
    clearTimeout(timeoutRef.current);
    if (value.length < 2) {
      setSuggestions([]);
      setShowSuggestions(false);
      return;
    }
    timeoutRef.current = window.setTimeout(async () => {
      try {
        const [drugs, companies, trials, mechanisms, therapeuticAreas] = await Promise.all([
          api.listEntities('drug', value, 4),
          api.listEntities('company', value, 4),
          api.listEntities('trial', value, 4),
          api.listEntities('mechanism', value, 3),
          api.listEntities('therapeutic_area', value, 3),
        ]);
        const all = [
          ...drugs.results.map((r) => ({ ...r, _type: 'drug' })),
          ...companies.results.map((r) => ({ ...r, _type: 'company' })),
          ...trials.results.map((r) => ({ ...r, _type: 'trial' })),
          ...mechanisms.results.map((r) => ({ ...r, _type: 'mechanism' })),
          ...therapeuticAreas.results.map((r) => ({ ...r, _type: 'therapeutic_area' })),
        ];
        setSuggestions(all.slice(0, 10));
        setShowSuggestions(all.length > 0);
      } catch {
        setSuggestions([]);
        setShowSuggestions(false);
      }
    }, 220);
  }, []);

  const handlePathFromChange = useCallback((value: string) => {
    setPathFromQuery(value);
    setPathFromEntity(null);
    setPathResult(null);
    setPathError(null);
    searchEntitiesForPath(value, setPathFromSuggestions, setShowPathFromSuggestions, pathFromTimeoutRef);
  }, [searchEntitiesForPath]);

  const handlePathToChange = useCallback((value: string) => {
    setPathToQuery(value);
    setPathToEntity(null);
    setPathResult(null);
    setPathError(null);
    searchEntitiesForPath(value, setPathToSuggestions, setShowPathToSuggestions, pathToTimeoutRef);
  }, [searchEntitiesForPath]);

  const selectPathFrom = useCallback((entity: EntityListItem & { _type: string }) => {
    setPathFromEntity({ id: entity.entity_id, type: entity._type, label: entity.label });
    setPathFromQuery(entity.label);
    setShowPathFromSuggestions(false);
    setPathFromSuggestions([]);
  }, []);

  const selectPathTo = useCallback((entity: EntityListItem & { _type: string }) => {
    setPathToEntity({ id: entity.entity_id, type: entity._type, label: entity.label });
    setPathToQuery(entity.label);
    setShowPathToSuggestions(false);
    setPathToSuggestions([]);
  }, []);

  const executePath = useCallback(async () => {
    if (!pathFromEntity || !pathToEntity) return;
    setPathLoading(true);
    setPathError(null);
    setPathResult(null);
    setGraphData(null);
    setSelectedEntity(null);
    setEntitySummary(null);
    setShowDemoBanner(false);
    try {
      const result = await api.graphPath(
        pathFromEntity.id,
        pathFromEntity.type,
        pathToEntity.id,
        pathToEntity.type,
        4,
      );
      setPathResult(result);
      if (result.path && result.path.length > 0) {
        // Convert path edges into graph nodes + edges for rendering
        const nodeIds = new Set<string>();
        const graphEdges: GraphEdge[] = [];
        for (const pe of result.path) {
          nodeIds.add(pe.source);
          nodeIds.add(pe.target);
          graphEdges.push({
            source_id: pe.source,
            target_id: pe.target,
            link_type: pe.type,
            confidence: pe.confidence,
            via: '',
          });
        }
        // Build minimal nodes — we don't have full metadata so use IDs as labels
        // Try to look up known entities from path from/to
        const graphNodes: GraphNode[] = [...nodeIds].map((nid) => {
          if (nid === pathFromEntity.id) {
            return { entity_id: nid, entity_type: pathFromEntity.type, label: pathFromEntity.label, properties: {} };
          }
          if (nid === pathToEntity.id) {
            return { entity_id: nid, entity_type: pathToEntity.type, label: pathToEntity.label, properties: {} };
          }
          return { entity_id: nid, entity_type: 'unknown', label: nid.slice(0, 8), properties: {} };
        });
        setGraphData({ nodes: graphNodes, edges: graphEdges });
        setSelectedEntity({ id: pathFromEntity.id, type: pathFromEntity.type, label: pathFromEntity.label });
      }
    } catch (err) {
      setPathError(err instanceof Error ? err.message : 'Path query failed');
    } finally {
      setPathLoading(false);
    }
  }, [pathFromEntity, pathToEntity]);

  const clearPathMode = useCallback(() => {
    setPathMode(false);
    setPathFromQuery('');
    setPathToQuery('');
    setPathFromEntity(null);
    setPathToEntity(null);
    setPathFromSuggestions([]);
    setPathToSuggestions([]);
    setShowPathFromSuggestions(false);
    setShowPathToSuggestions(false);
    setPathLoading(false);
    setPathError(null);
    setPathResult(null);
  }, []);

  const nodeMap = useMemo(
    () => new Map((graphData?.nodes ?? []).map((node) => [node.entity_id, node])),
    [graphData?.nodes],
  );

  const availableLinkTypes = useMemo(() => (
    graphData
      ? [...new Set(graphData.edges.map((edge) => edge.link_type))].sort((a, b) => a.localeCompare(b))
      : []
  ), [graphData]);

  const availableNodeTypes = useMemo(() => (
    graphData
      ? [...new Set(graphData.nodes.map((node) => node.entity_type))].sort((a, b) => a.localeCompare(b))
      : []
  ), [graphData]);

  const filteredGraphData = useMemo(() => {
    if (!graphData) return null;

    const linkFilteredEdges = graphData.edges.filter((edge) => (
      linkTypeFilter === 'all' || edge.link_type === linkTypeFilter
    ));

    if (nodeTypeFilter === 'all') {
      return {
        nodes: graphData.nodes,
        edges: linkFilteredEdges,
      };
    }

    const preferredIds = new Set<string>(
      graphData.nodes
        .filter((node) => node.entity_type === nodeTypeFilter)
        .map((node) => node.entity_id),
    );
    if (selectedEntity) preferredIds.add(selectedEntity.id);

    const edges = linkFilteredEdges.filter((edge) => (
      preferredIds.has(edge.source_id) || preferredIds.has(edge.target_id)
    ));
    const nodeIds = new Set<string>(selectedEntity ? [selectedEntity.id] : []);
    edges.forEach((edge) => {
      nodeIds.add(edge.source_id);
      nodeIds.add(edge.target_id);
    });
    const nodes = graphData.nodes.filter((node) => nodeIds.has(node.entity_id));

    return { nodes, edges };
  }, [graphData, linkTypeFilter, nodeTypeFilter, selectedEntity]);

  const edgeRows = useMemo(() => {
    if (!graphData || !selectedEntity) return [];
    return graphData.edges
      .filter((edge) => (
        (edge.source_id === selectedEntity.id || edge.target_id === selectedEntity.id)
        && (linkTypeFilter === 'all' || edge.link_type === linkTypeFilter)
      ))
      .map((edge) => {
        const outgoing = edge.source_id === selectedEntity.id;
        const otherId = outgoing ? edge.target_id : edge.source_id;
        const otherNode = nodeMap.get(otherId);
        return {
          key: `${edge.source_id}-${edge.target_id}-${edge.link_type}`,
          linkType: edge.link_type,
          confidence: edge.confidence,
          via: edge.via || edge.source || 'Knowledge graph linkage',
          provenance: graphEdgeProvenanceCaption(edge),
          direction: outgoing ? 'to' : 'from',
          otherId,
          otherLabel: otherNode?.label ?? otherId,
          otherType: otherNode?.entity_type ?? 'unknown',
        };
      })
      .sort((a, b) => b.confidence - a.confidence);
  }, [graphData, linkTypeFilter, nodeMap, selectedEntity]);

  const highConfidenceRows = useMemo(
    () => edgeRows.filter((row) => row.confidence >= 0.65).slice(0, 8),
    [edgeRows],
  );

  const linkTypeCounts = useMemo(() => {
    const counts = new Map<string, number>();
    (filteredGraphData?.edges ?? []).forEach((edge) => {
      counts.set(edge.link_type, (counts.get(edge.link_type) ?? 0) + 1);
    });
    return [...counts.entries()].sort((a, b) => b[1] - a[1]);
  }, [filteredGraphData?.edges]);

  const sourceDomains = useMemo(() => {
    const domains = new Set<string>();
    edgeRows.forEach((row) => {
      const domain = extractSourceDomain(row.via);
      if (domain) domains.add(domain);
    });
    return domains;
  }, [edgeRows]);

  const edgeDensity = useMemo(() => {
    const nodes = filteredGraphData?.nodes.length ?? 0;
    const edges = filteredGraphData?.edges.length ?? 0;
    if (nodes === 0) return '0.0';
    return (edges / nodes).toFixed(1);
  }, [filteredGraphData]);

  const objectiveTypeHint = useMemo(() => {
    if (!selectedEntity || activeObjective.preferredTypes.length === 0) return null;
    if (activeObjective.preferredTypes.includes(selectedEntity.type)) return null;
    return `Tip: ${activeObjective.label} works best with ${activeObjective.preferredTypes.map(prettyType).join(', ')} anchors.`;
  }, [activeObjective, selectedEntity]);

  const selectedEntityNode = useMemo(() => {
    if (!selectedEntity || !graphData) return null;
    return graphData.nodes.find((node) => node.entity_id === selectedEntity.id) ?? null;
  }, [selectedEntity, graphData]);

  const selectedEntityInsight = useMemo(() => {
    if (!selectedEntityNode || !graphData) return null;
    return buildNodeInsight(selectedEntityNode, graphData);
  }, [selectedEntityNode, graphData]);

  return (
    <div className="workspace-canvas flex h-full w-full min-h-0 flex-col overflow-y-auto lg:flex-row lg:overflow-hidden">
      <aside
        className={`w-full shrink-0 border-b border-line bg-white/58 transition-all duration-200 max-h-[52vh] lg:max-h-none lg:border-b-0 lg:border-r ${
          railCollapsed ? 'lg:w-[66px]' : 'lg:w-[430px]'
        }`}
      >
        <div className="h-full overflow-y-auto" style={{ padding: railCollapsed ? '16px 8px' : '16px' }}>
          {railCollapsed ? (
            <div className="flex h-full flex-col items-center gap-3">
              <button
                type="button"
                onClick={() => setRailCollapsed(false)}
                className="inline-flex h-10 w-10 items-center justify-center rounded-md border border-line bg-white text-ink-3 transition-colors hover:bg-surface-2"
                title="Expand explorer controls"
                aria-label="Expand explorer controls"
              >
                <PanelLeftOpen size={16} />
              </button>
              <button
                type="button"
                onClick={() => {
                  if (!selectedEntityInsight) return;
                  setQuickNodeInsight(selectedEntityInsight);
                }}
                disabled={!selectedEntityInsight}
                className="inline-flex h-10 w-10 items-center justify-center rounded-md border border-line bg-white text-ink-3 transition-colors hover:bg-surface-2 disabled:opacity-35"
                title="Show quick node insight"
                aria-label="Show quick node insight"
              >
                <Compass size={15} />
              </button>
              <button
                type="button"
                onClick={() => setDrawerOpen(true)}
                disabled={!selectedEntity}
                className="inline-flex h-10 w-10 items-center justify-center rounded-md border border-line bg-white text-ink-3 transition-colors hover:bg-surface-2 disabled:opacity-35"
                title="Open full node details"
                aria-label="Open full node details"
              >
                <FileText size={15} />
              </button>
              <div className="mt-auto text-[10px] text-ink-4 [writing-mode:vertical-rl] rotate-180">
                Graph controls
              </div>
            </div>
          ) : (
            <div className="flex flex-col gap-3">
        <div className="card" style={{ padding: '16px' }}>
          <div className="flex items-center justify-between gap-2">
            <div>
              <h3 className="text-[13px] font-semibold text-ink">Graph Explorer</h3>
              <p className="text-[11px] text-ink-3">Traverse linked evidence and provenance from a chosen anchor entity.</p>
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setRailCollapsed(true)}
                className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-line bg-white text-ink-3 transition-colors hover:bg-surface-2"
                title="Collapse explorer controls"
                aria-label="Collapse explorer controls"
              >
                <PanelLeftClose size={14} />
              </button>
              <div className="inline-flex items-center gap-2 rounded-md border border-line bg-white text-[11px] text-ink-3" style={{ padding: '6px 12px' }}>
              <span>Hops</span>
              <select
                value={hops}
                onChange={(event) => setHops(Number(event.target.value))}
                className="bg-transparent text-[11px] font-semibold text-ink outline-none"
              >
                <option value={1}>1</option>
                <option value={2}>2</option>
                <option value={3}>3</option>
              </select>
              </div>
            </div>
          </div>

          <div className="mt-3">
            <div className="mb-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-ink-3">Exploration objective</div>
            <div className="flex flex-wrap gap-1.5">
              {OBJECTIVES.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setObjective(item.id)}
                  className={`rounded-md border text-[11px] transition-colors ${
                    objective === item.id
                      ? 'border-ink bg-ink text-white'
                      : 'border-line bg-white text-ink-3 hover:border-line hover:bg-surface-2'
                  }`}
                  style={{ padding: '6px 12px' }}
                >
                  {item.label}
                </button>
              ))}
            </div>
            <div className="mt-2 text-[11px] text-ink-3">{activeObjective.description}</div>
          </div>

          <div className="mt-4">
            <div className="mb-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-ink-3">Anchor entity</div>
            <div className="relative">
              <Search className="absolute left-3 top-2.5 text-ink-4" size={16} />
              <input
                value={entityLookupQuery}
                onChange={(event) => handleLookupChange(event.target.value)}
                placeholder="Search a drug, trial, company, mechanism, or therapeutic area..."
                className="input-surface h-[48px] w-full rounded-lg text-sm outline-none transition-all focus:ring-2 focus:ring-brand/15"
                style={{ padding: '8px 16px 8px 40px' }}
              />
              {showSuggestions && (
                <div className="animate-fade-in absolute left-0 right-0 top-full mt-2 overflow-hidden rounded-lg border border-line bg-white/96 shadow-xl">
                  {suggestions.map((suggestion) => (
                    <button
                      key={suggestion.entity_id}
                      type="button"
                      onClick={() => void loadGraph(suggestion.entity_id, suggestion._type, suggestion.label)}
                      className="flex w-full items-center gap-3 text-left transition-colors hover:bg-surface-2"
                      style={{ padding: '12px 16px' }}
                    >
                      <span className="rounded-sm bg-surface-3 text-ink-3" style={{ padding: '6px' }}>
                        {ENTITY_CONFIG[suggestion._type]?.icon ?? <Network size={14} />}
                      </span>
                      <div>
                        <div className="text-sm font-medium text-ink">{suggestion.label}</div>
                        <div className="text-xs capitalize text-ink-3">{prettyType(suggestion._type)}</div>
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>
            {objectiveTypeHint && (
              <div className="mt-2 flex items-center gap-1.5 rounded-md border border-amber-200 bg-amber-50 text-[11px] text-amber-700" style={{ padding: '8px 12px' }}>
                <Compass size={12} />
                {objectiveTypeHint}
              </div>
            )}
            {graphError && (
              <div className="mt-2 rounded-md border border-rose-200 bg-rose-50 text-xs text-rose-700" style={{ padding: '8px 12px' }}>
                {graphError}
              </div>
            )}
          </div>

          {/* Path-finding toggle */}
          <div className="mt-3">
            {!pathMode ? (
              <button
                type="button"
                onClick={() => setPathMode(true)}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '6px',
                  padding: '7px 14px',
                  borderRadius: '8px',
                  border: '1px solid var(--color-line, #e2e8f0)',
                  background: 'var(--color-surface, #ffffff)',
                  color: 'var(--color-ink-2, #374151)',
                  fontSize: '12px',
                  fontWeight: 500,
                  cursor: 'pointer',
                  fontFamily: 'inherit',
                  transition: 'border-color 0.15s ease',
                }}
              >
                <Route size={13} />
                Find Path
              </button>
            ) : (
              <div
                style={{
                  padding: '12px',
                  borderRadius: '10px',
                  border: '1px solid var(--color-line, #e2e8f0)',
                  background: 'var(--color-surface, #ffffff)',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '10px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '11px', fontWeight: 600, textTransform: 'uppercase' as const, letterSpacing: '0.14em', color: 'var(--color-ink-3, #6b7280)' }}>
                    <Route size={12} />
                    Path Finder
                  </div>
                  <button
                    type="button"
                    onClick={clearPathMode}
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      width: '22px',
                      height: '22px',
                      borderRadius: '6px',
                      border: '1px solid var(--color-line, #e2e8f0)',
                      background: 'var(--color-surface, #ffffff)',
                      color: 'var(--color-ink-4, #a1a1aa)',
                      cursor: 'pointer',
                      padding: 0,
                      fontSize: '12px',
                    }}
                    title="Close path finder"
                    aria-label="Close path finder"
                  >
                    <X size={12} />
                  </button>
                </div>

                {/* From entity */}
                <div style={{ marginBottom: '8px' }}>
                  <div style={{ fontSize: '10px', fontWeight: 600, color: 'var(--color-ink-3, #6b7280)', marginBottom: '4px' }}>From</div>
                  <div className="relative">
                    <input
                      value={pathFromQuery}
                      onChange={(e) => handlePathFromChange(e.target.value)}
                      placeholder="Search starting entity..."
                      style={{
                        width: '100%',
                        height: '36px',
                        padding: '0 10px',
                        borderRadius: '6px',
                        border: pathFromEntity
                          ? '1.5px solid var(--color-accent, #2563eb)'
                          : '1px solid var(--color-line, #e2e8f0)',
                        background: 'var(--color-surface, #ffffff)',
                        color: 'var(--color-ink, #111827)',
                        fontSize: '12px',
                        outline: 'none',
                        fontFamily: 'inherit',
                      }}
                    />
                    {showPathFromSuggestions && (
                      <div className="animate-fade-in absolute left-0 right-0 top-full mt-1 overflow-hidden rounded-lg border border-line bg-white/96 shadow-xl" style={{ zIndex: 30, maxHeight: '180px', overflowY: 'auto' }}>
                        {pathFromSuggestions.map((s) => (
                          <button
                            key={s.entity_id}
                            type="button"
                            onClick={() => selectPathFrom(s)}
                            className="flex w-full items-center gap-2.5 text-left transition-colors hover:bg-surface-2"
                            style={{ padding: '8px 12px' }}
                          >
                            <span className="rounded-sm bg-surface-3 text-ink-3" style={{ padding: '4px' }}>
                              {ENTITY_CONFIG[s._type]?.icon ?? <Network size={12} />}
                            </span>
                            <div>
                              <div style={{ fontSize: '12px', fontWeight: 500, color: 'var(--color-ink, #111827)' }}>{s.label}</div>
                              <div style={{ fontSize: '10px', color: 'var(--color-ink-4, #a1a1aa)', textTransform: 'capitalize' as const }}>{prettyType(s._type)}</div>
                            </div>
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                </div>

                {/* To entity */}
                <div style={{ marginBottom: '10px' }}>
                  <div style={{ fontSize: '10px', fontWeight: 600, color: 'var(--color-ink-3, #6b7280)', marginBottom: '4px' }}>To</div>
                  <div className="relative">
                    <input
                      value={pathToQuery}
                      onChange={(e) => handlePathToChange(e.target.value)}
                      placeholder="Search target entity..."
                      style={{
                        width: '100%',
                        height: '36px',
                        padding: '0 10px',
                        borderRadius: '6px',
                        border: pathToEntity
                          ? '1.5px solid var(--color-accent, #2563eb)'
                          : '1px solid var(--color-line, #e2e8f0)',
                        background: 'var(--color-surface, #ffffff)',
                        color: 'var(--color-ink, #111827)',
                        fontSize: '12px',
                        outline: 'none',
                        fontFamily: 'inherit',
                      }}
                    />
                    {showPathToSuggestions && (
                      <div className="animate-fade-in absolute left-0 right-0 top-full mt-1 overflow-hidden rounded-lg border border-line bg-white/96 shadow-xl" style={{ zIndex: 30, maxHeight: '180px', overflowY: 'auto' }}>
                        {pathToSuggestions.map((s) => (
                          <button
                            key={s.entity_id}
                            type="button"
                            onClick={() => selectPathTo(s)}
                            className="flex w-full items-center gap-2.5 text-left transition-colors hover:bg-surface-2"
                            style={{ padding: '8px 12px' }}
                          >
                            <span className="rounded-sm bg-surface-3 text-ink-3" style={{ padding: '4px' }}>
                              {ENTITY_CONFIG[s._type]?.icon ?? <Network size={12} />}
                            </span>
                            <div>
                              <div style={{ fontSize: '12px', fontWeight: 500, color: 'var(--color-ink, #111827)' }}>{s.label}</div>
                              <div style={{ fontSize: '10px', color: 'var(--color-ink-4, #a1a1aa)', textTransform: 'capitalize' as const }}>{prettyType(s._type)}</div>
                            </div>
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                </div>

                {/* Action buttons */}
                <div style={{ display: 'flex', gap: '8px' }}>
                  <button
                    type="button"
                    onClick={() => void executePath()}
                    disabled={!pathFromEntity || !pathToEntity || pathLoading}
                    style={{
                      flex: 1,
                      display: 'inline-flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: '5px',
                      height: '32px',
                      borderRadius: '6px',
                      border: 'none',
                      background: (!pathFromEntity || !pathToEntity)
                        ? 'var(--color-ink-4, #a1a1aa)'
                        : 'var(--color-ink, #111827)',
                      color: '#ffffff',
                      fontSize: '11px',
                      fontWeight: 600,
                      cursor: (!pathFromEntity || !pathToEntity) ? 'not-allowed' : 'pointer',
                      opacity: (!pathFromEntity || !pathToEntity) ? 0.5 : 1,
                      fontFamily: 'inherit',
                    }}
                  >
                    {pathLoading ? <Loader2 size={13} className="animate-spin" /> : <Route size={13} />}
                    Show Path
                  </button>
                  <button
                    type="button"
                    onClick={clearPathMode}
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: '4px',
                      height: '32px',
                      padding: '0 12px',
                      borderRadius: '6px',
                      border: '1px solid var(--color-line, #e2e8f0)',
                      background: 'var(--color-surface, #ffffff)',
                      color: 'var(--color-ink-3, #6b7280)',
                      fontSize: '11px',
                      fontWeight: 500,
                      cursor: 'pointer',
                      fontFamily: 'inherit',
                    }}
                  >
                    Clear
                  </button>
                </div>

                {/* Path result info */}
                {pathResult && pathResult.path && (
                  <div
                    style={{
                      marginTop: '8px',
                      padding: '8px 10px',
                      borderRadius: '6px',
                      background: 'var(--color-accent-soft, #eff6ff)',
                      border: '1px solid var(--color-accent, #2563eb)',
                      fontSize: '11px',
                      color: 'var(--color-ink-2, #374151)',
                    }}
                  >
                    Path found: {pathResult.hops ?? pathResult.path.length} hop{(pathResult.hops ?? pathResult.path.length) !== 1 ? 's' : ''}
                  </div>
                )}
                {pathResult && !pathResult.path && (
                  <div
                    style={{
                      marginTop: '8px',
                      padding: '8px 10px',
                      borderRadius: '6px',
                      background: '#fef2f2',
                      border: '1px solid #fecaca',
                      fontSize: '11px',
                      color: '#b91c1c',
                    }}
                  >
                    {pathResult.message || 'No path found between these entities.'}
                  </div>
                )}
                {pathError && (
                  <div
                    style={{
                      marginTop: '8px',
                      padding: '8px 10px',
                      borderRadius: '6px',
                      background: '#fef2f2',
                      border: '1px solid #fecaca',
                      fontSize: '11px',
                      color: '#b91c1c',
                    }}
                  >
                    {pathError}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {graphData && (
          <div className="card animate-slide-in" style={{ padding: '16px' }}>
            <h3 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-ink-3">Graph Summary</h3>
            <div className="mt-3 grid grid-cols-2 gap-2">
              <ControlStat label="Entities found" value={String(filteredGraphData?.nodes.length ?? graphData.nodes.length)} />
              <ControlStat label="Relationships" value={String(filteredGraphData?.edges.length ?? graphData.edges.length)} />
              <ControlStat label="Avg links/node" value={String(edgeDensity)} />
              <ControlStat label="Data sources" value={sourceDomains.size > 0 ? Array.from(sourceDomains).slice(0, 3).map(d => displayName(d)).join(', ') : 'Exploring...'} />
            </div>

            {highConfidenceRows.length > 0 && (
              <div className="mt-3">
                <div className="mb-2 text-[11px] font-semibold text-ink-2">High-confidence neighbors</div>
                <div className="max-h-40 space-y-1.5 overflow-y-auto" style={{ paddingRight: '2px' }}>
                  {highConfidenceRows.map((row) => (
                    <button
                      key={row.key}
                      type="button"
                      onClick={() => void loadGraph(row.otherId, row.otherType, row.otherLabel)}
                      className="flex w-full items-center justify-between gap-2 rounded-md border border-line bg-white text-left text-[11px] transition-colors hover:border-line hover:bg-surface-2"
                      style={{ padding: '8px 12px' }}
                    >
                      <span className="min-w-0">
                        <span className="block truncate font-medium text-ink">{row.otherLabel}</span>
                        <span className="block truncate text-ink-3">{prettyType(row.linkType)} - {prettyType(row.otherType)}</span>
                      </span>
                      <span className="shrink-0 text-ink-3">{(row.confidence * 100).toFixed(0)}%</span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {linkTypeCounts.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-1.5">
                {linkTypeCounts.slice(0, 8).map(([linkType, count]) => (
                  <span key={linkType} className="rounded-sm border border-line bg-white text-[10px] text-ink-3" style={{ padding: '4px 10px' }}>
                    {prettyType(linkType)}: <span className="font-semibold text-ink">{count}</span>
                  </span>
                ))}
              </div>
            )}
          </div>
        )}

        {graphData && (
          <div className="card animate-slide-in" style={{ padding: '16px' }}>
            <h3 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-ink-3">Graph controls</h3>
            <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
              <label className="text-[11px] text-ink-3">
                Node type
                <select
                  value={nodeTypeFilter}
                  onChange={(event) => setNodeTypeFilter(event.target.value)}
                  className="mt-1 h-8 w-full rounded-md border border-line bg-white text-[11px] text-ink-2 outline-none focus:ring-2 focus:ring-brand/10"
                  style={{ padding: '0 10px' }}
                >
                  <option value="all">All node types</option>
                  {availableNodeTypes.map((type) => (
                    <option key={type} value={type}>{prettyType(type)}</option>
                  ))}
                </select>
              </label>
              <label className="text-[11px] text-ink-3">
                Link type
                <select
                  value={linkTypeFilter}
                  onChange={(event) => setLinkTypeFilter(event.target.value)}
                  className="mt-1 h-8 w-full rounded-md border border-line bg-white text-[11px] text-ink-2 outline-none focus:ring-2 focus:ring-brand/10"
                  style={{ padding: '0 10px' }}
                >
                  <option value="all">All links</option>
                  {availableLinkTypes.map((type) => (
                    <option key={type} value={type}>{prettyType(type)}</option>
                  ))}
                </select>
              </label>
            </div>
          </div>
        )}
            </div>
          )}
        </div>
      </aside>

      <div className="relative min-h-[52vh] flex-1 border-t border-line lg:min-h-0 lg:border-t-0">
        {isLoading ? (
          <div className="absolute inset-0 z-10 flex items-center justify-center" style={{ background: 'rgba(15, 23, 42, 0.6)' }}>
            <div style={{
              display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '12px',
              padding: '20px 32px', borderRadius: '12px',
              background: 'rgba(15, 23, 42, 0.9)', backdropFilter: 'blur(8px)',
              border: '1px solid rgba(255,255,255,0.1)',
            }}>
              <Loader2 className="animate-spin" size={24} style={{ color: '#3b82f6' }} />
              <span style={{ fontSize: '13px', color: 'rgba(226, 232, 240, 0.7)', fontFamily: 'var(--font-body, sans-serif)' }}>
                Loading graph...
              </span>
            </div>
          </div>
        ) : filteredGraphData && filteredGraphData.nodes.length > 0 ? (
          <>
            <KnowledgeGraph
              nodes={filteredGraphData.nodes}
              edges={filteredGraphData.edges}
              centerEntityId={selectedEntity?.id}
              onNodeClick={handleNodeClick}
              onNodeContextMenu={onAskInChat ? handleNodeContextMenu : undefined}
            />
            {/* Right-click context menu */}
            {contextMenu && onAskInChat && (
              <GraphContextMenu
                node={contextMenu.node}
                position={contextMenu.position}
                onAskInChat={onAskInChat}
                onClose={handleContextMenuClose}
              />
            )}
            {/* Node count badge */}
            <div
              style={{
                position: 'absolute',
                top: '12px',
                right: '12px',
                padding: '4px 12px',
                borderRadius: '999px',
                background: 'rgba(15, 23, 42, 0.8)',
                backdropFilter: 'blur(6px)',
                border: '1px solid rgba(255,255,255,0.08)',
                fontSize: '11px',
                color: 'rgba(226, 232, 240, 0.6)',
                fontFamily: 'var(--font-mono, monospace)',
                zIndex: 10,
                pointerEvents: 'none',
              }}
            >
              {filteredGraphData.nodes.length} entities · {filteredGraphData.edges.length} connections
            </div>
            {showDemoBanner && !initialEntity && (
              <div
                className="absolute top-4 left-1/2 z-20 -translate-x-1/2 flex items-center gap-3 rounded-xl"
                style={{
                  padding: '10px 20px',
                  background: 'rgba(255,255,255,0.92)',
                  backdropFilter: 'blur(12px)',
                  border: '1px solid var(--color-line)',
                  boxShadow: 'var(--shadow-sm)',
                  fontSize: '13px',
                  color: 'var(--color-ink-2)',
                }}
              >
                <span>Showing <strong style={{ color: 'var(--color-ink)' }}>semaglutide</strong> connections — search any entity to explore</span>
                <button
                  type="button"
                  onClick={() => setShowDemoBanner(false)}
                  style={{
                    background: 'none', border: 'none', cursor: 'pointer',
                    color: 'var(--color-ink-4)', fontSize: '16px', lineHeight: 1,
                  }}
                >
                  ×
                </button>
              </div>
            )}
          </>
        ) : (
          <div className="flex h-full flex-col items-center justify-center text-center" style={{ padding: '0 16px' }}>
            <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-xl border border-line bg-white/88 shadow-sm">
              <Network size={28} className="text-brand" />
            </div>
            <h3 className="text-[15px] font-semibold text-ink">Explore Entity Connections</h3>
            <p className="mt-1 max-w-sm text-[12px] leading-relaxed text-ink-3">
              Search for a drug, company, or therapeutic area to visualize its relationships in the knowledge graph.
            </p>
            <div className="mt-4 flex flex-wrap justify-center gap-2">
              {[
                { label: 'Semaglutide', type: 'drug' },
                { label: 'Novo Nordisk', type: 'company' },
                { label: 'Diabetes Mellitus', type: 'therapeutic_area' },
                { label: 'GLP-1 receptor agonist', type: 'mechanism' },
              ].map((example) => (
                <button
                  key={example.label}
                  type="button"
                  onClick={() => {
                    setEntityLookupQuery(example.label);
                    // Trigger search
                    void (async () => {
                      try {
                        const res = await api.listEntities(example.type, example.label, 1);
                        if (res.results.length > 0) {
                          const r = res.results[0];
                          void loadGraph(r.entity_id, example.type, r.label, hops);
                        }
                      } catch { /* ignore */ }
                    })();
                  }}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-white text-[11px] font-medium text-ink-3 shadow-sm transition-all hover:border-brand/30 hover:shadow-md"
                  style={{ padding: '6px 12px' }}
                >
                  {ENTITY_CONFIG[example.type]?.icon}
                  {example.label}
                </button>
              ))}
            </div>
            <div className="mt-6 grid max-w-lg grid-cols-2 gap-3 text-left">
              {OBJECTIVES.map((obj) => (
                <div key={obj.id} className="rounded-lg border border-line bg-white/80" style={{ padding: '8px 12px' }}>
                  <div className="text-[11px] font-semibold text-ink-2">{obj.label}</div>
                  <div className="mt-0.5 text-[10px] leading-relaxed text-ink-4">{obj.description}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Node insight card moved to bottom-right — now more visible */}
        {quickNodeInsight && (
          <div className="absolute bottom-4 right-4 z-20" style={{ width: 'min(92vw, 340px)' }}>
            <div
              className="rounded-xl"
              style={{
                padding: '16px',
                background: 'rgba(255,255,255,0.96)',
                backdropFilter: 'blur(12px)',
                border: '1px solid var(--color-line)',
                boxShadow: 'var(--shadow-md)',
              }}
            >
              <div className="mb-2 flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="truncate" style={{ fontSize: '13px', fontWeight: 600, color: 'var(--color-ink)' }}>{quickNodeInsight.label}</div>
                  <div style={{ fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--color-ink-4)' }}>
                    {prettyType(quickNodeInsight.type)}
                  </div>
                </div>
                <div className="flex gap-1.5">
                  <button
                    type="button"
                    onClick={() => {
                      if (quickNodeInsight) {
                        void loadGraph(quickNodeInsight.id, quickNodeInsight.type, quickNodeInsight.label, hops, { openDetails: true });
                      }
                    }}
                    style={{
                      fontSize: '10px', fontWeight: 600, color: 'var(--color-accent)',
                      background: 'var(--color-accent-soft)', border: 'none', cursor: 'pointer',
                      padding: '3px 8px', borderRadius: '6px',
                    }}
                  >
                    Dossier
                  </button>
                  <button
                    type="button"
                    onClick={() => setQuickNodeInsight(null)}
                    style={{
                      fontSize: '10px', color: 'var(--color-ink-4)',
                      background: 'var(--color-surface-2)', border: 'none', cursor: 'pointer',
                      padding: '3px 8px', borderRadius: '6px',
                    }}
                  >
                    ×
                  </button>
                </div>
              </div>
              <p style={{ fontSize: '11px', lineHeight: 1.5, color: 'var(--color-ink-3)', marginBottom: '8px' }}>{quickNodeInsight.summary}</p>
              <div className="grid grid-cols-2 gap-1.5" style={{ fontSize: '11px' }}>
                <MiniStat label="Connections" value={String(quickNodeInsight.degree)} />
                <MiniStat label="Relevance" value={`${quickNodeInsight.relevance}%`} />
                <MiniStat label="Avg confidence" value={`${quickNodeInsight.avgConfidence}%`} />
                <MiniStat label="Top relation" value={quickNodeInsight.topRelation} />
              </div>
              <div className="mt-2 flex items-center justify-between gap-2">
                <button
                  type="button"
                  onClick={() => {
                    void loadGraph(quickNodeInsight.id, quickNodeInsight.type, quickNodeInsight.label, hops);
                  }}
                  className="inline-flex items-center gap-1 rounded-sm border border-line bg-white text-[10px] text-ink-3 transition-colors hover:bg-surface-2"
                  style={{ padding: '4px 10px' }}
                >
                  <Network size={11} />
                  Focus node
                </button>
                <button
                  type="button"
                  onClick={() => setDrawerOpen(true)}
                  className="inline-flex items-center gap-1 rounded-sm border border-line bg-white text-[10px] text-ink-3 transition-colors hover:bg-surface-2"
                  style={{ padding: '4px 10px' }}
                >
                  <FileText size={11} />
                  Full details
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      <Drawer
        isOpen={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        title={selectedEntity?.label || 'Entity details'}
        subtitle={selectedEntity?.type ? prettyType(selectedEntity.type) : undefined}
        width="clamp(380px, 35vw, 560px)"
      >
        <div className="space-y-5">
          <section>
            <h4 className="mb-2.5 text-sm font-medium text-ink">Overview</h4>
            <div className="space-y-2 rounded-md border border-line bg-white" style={{ padding: '16px' }}>
              <div className="flex justify-between text-sm">
                <span className="text-ink-3">Type</span>
                <span className="font-medium text-ink">{selectedEntity?.type ? displayName(selectedEntity.type) : 'n/a'}</span>
              </div>
              {entitySummary && (
                <div className="flex justify-between text-sm">
                  <span className="text-ink-3">Connections</span>
                  <span className="font-medium text-ink">{entitySummary.total_connections}</span>
                </div>
              )}
              {entitySummary && Object.keys(entitySummary.connections_by_entity_type || {}).length > 0 && (
                <div className="mt-1 flex flex-wrap gap-1.5">
                  {Object.entries(entitySummary.connections_by_entity_type)
                    .sort(([, a], [, b]) => Number(b) - Number(a))
                    .map(([eType, count]) => (
                      <span key={eType} className="inline-flex items-center gap-1 rounded-full bg-surface-3 text-[10px] font-medium text-ink-3" style={{ padding: '2px 8px' }}>
                        {displayName(eType)} <span className="text-ink-4">{Number(count)}</span>
                      </span>
                    ))}
                </div>
              )}
            </div>
          </section>

          <section>
            <h4 className="mb-2.5 text-sm font-medium text-ink">Relationships</h4>
            <div className="max-h-72 space-y-2 overflow-y-auto">
              {edgeRows.length === 0 && (
                <div className="rounded-md border border-line bg-white text-xs text-ink-3" style={{ padding: '10px 14px' }}>
                  Source data pending — this entity has no linked provenance yet.
                </div>
              )}
              {edgeRows.slice(0, 14).map((row) => (
                <div key={row.key} className="rounded-md border border-line bg-white" style={{ padding: '12px 14px' }}>
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="text-xs font-semibold text-ink">
                        {displayName(row.linkType)} {row.direction} {isUUID(row.otherLabel) ? displayName(row.otherType) : row.otherLabel}
                      </div>
                      <div className="mt-0.5 text-[11px] text-ink-3">{displayName(row.otherType)}</div>
                    </div>
                    <div className="flex shrink-0 items-center gap-1 text-[11px] text-ink-3">
                      <ShieldCheck size={12} />
                      {(row.confidence * 100).toFixed(0)}%
                    </div>
                  </div>
                  {row.via && !isUUID(row.via) && (
                    <div className="mt-2 flex items-start gap-1.5 text-[11px] text-ink-3">
                      <Link2 size={12} className="mt-0.5 shrink-0" />
                      <span className="break-all">{/https?:\/\//.test(row.via) ? row.via : displayName(row.via)}</span>
                    </div>
                  )}
                  {row.provenance && (
                    <div className="mt-1.5">
                      <ProvenanceCaption {...row.provenance} />
                    </div>
                  )}
                </div>
              ))}
            </div>
          </section>

          <section>
            <h4 className="mb-2.5 text-sm font-medium text-ink">Connection breakdown</h4>
            {summaryLoading ? (
              <div className="flex items-center gap-2 rounded-md border border-line bg-white text-xs text-ink-3" style={{ padding: '10px 14px' }}>
                <Loader2 size={12} className="animate-spin" />
                Loading...
              </div>
            ) : entitySummary && Object.keys(entitySummary.connections_by_type).length > 0 ? (
              <div className="space-y-1.5">
                {Object.entries(entitySummary.connections_by_type)
                  .sort(([, a], [, b]) => Number(b) - Number(a))
                  .slice(0, 10)
                  .map(([linkType, count]) => {
                    const total = entitySummary.total_connections || 1;
                    const pct = Math.round((Number(count) / total) * 100);
                    return (
                      <div key={linkType} className="rounded-md border border-line bg-white" style={{ padding: '8px 14px' }}>
                        <div className="flex items-center justify-between text-xs">
                          <span className="text-ink-3">{displayName(linkType)}</span>
                          <span className="font-semibold text-ink">{Number(count)}</span>
                        </div>
                        <div className="mt-1 h-1 w-full rounded-full bg-surface-3">
                          <div className="h-1 rounded-full" style={{ width: `${pct}%`, background: 'var(--color-accent)' }} />
                        </div>
                      </div>
                    );
                  })}
              </div>
            ) : (
              <div className="rounded-md border border-line bg-white text-xs text-ink-3" style={{ padding: '10px 14px' }}>
                No connections found for this entity.
              </div>
            )}
          </section>

          {edgeRows.some((row) => /https?:\/\//.test(row.via)) && (
            <section>
              <h4 className="mb-2.5 text-sm font-medium text-ink">External sources</h4>
              <div className="space-y-1.5">
                {Array.from(new Set(edgeRows.map((row) => extractUrl(row.via)).filter(Boolean) as string[]))
                  .slice(0, 5)
                  .map((url) => (
                    <a
                      key={url}
                      href={url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-2 rounded-md border border-line bg-white text-xs text-ink-3 transition-colors hover:bg-surface-2"
                      style={{ padding: '10px 14px' }}
                    >
                      <ExternalLink size={12} />
                      <span className="truncate">{url}</span>
                    </a>
                  ))}
              </div>
            </section>
          )}
        </div>
      </Drawer>
    </div>
  );
}

function ControlStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-line bg-white" style={{ padding: '10px 12px' }}>
      <div className="text-[10px] uppercase tracking-wide text-ink-3">{label}</div>
      <div className="text-lg font-semibold tracking-tight text-ink">{value}</div>
    </div>
  );
}

function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-sm border border-line bg-white" style={{ padding: '6px 8px' }}>
      <div className="truncate text-[9px] uppercase tracking-wide text-ink-3">{label}</div>
      <div className="truncate text-[11px] font-semibold text-ink">{value}</div>
    </div>
  );
}

function prettyType(raw: string): string {
  return displayName(raw);
}

function extractUrl(text: string): string | null {
  const match = text.match(/https?:\/\/\S+/i);
  return match ? match[0] : null;
}

function extractSourceDomain(text: string): string | null {
  const url = extractUrl(text);
  if (!url) return null;
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return null;
  }
}

interface NodeInsight {
  id: string;
  type: string;
  label: string;
  summary: string;
  degree: number;
  avgConfidence: number;
  maxConfidence: number;
  topRelation: string;
  relevance: number;
}

function buildNodeInsight(node: GraphNode, graph: { nodes: GraphNode[]; edges: GraphEdge[] }): NodeInsight {
  const connectedEdges = graph.edges.filter((edge) => edge.source_id === node.entity_id || edge.target_id === node.entity_id);
  const degree = connectedEdges.length;
  const confidences = connectedEdges.map((edge) => edge.confidence).filter((value) => Number.isFinite(value));
  const avgConfidence = confidences.length > 0
    ? Math.round((confidences.reduce((sum, value) => sum + value, 0) / confidences.length) * 100)
    : 0;
  const maxConfidence = confidences.length > 0
    ? Math.round(Math.max(...confidences) * 100)
    : 0;

  const relationCount = new Map<string, number>();
  connectedEdges.forEach((edge) => {
    relationCount.set(edge.link_type, (relationCount.get(edge.link_type) ?? 0) + 1);
  });
  const topRelationRaw = [...relationCount.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] ?? 'none';
  const topRelation = prettyType(topRelationRaw);

  const degreeScore = Math.min(degree, 20) / 20;
  const relevance = Math.round(Math.min(1, (avgConfidence / 100) * 0.7 + degreeScore * 0.3) * 100);
  const summary = summarizeNodeProperties(node, degree, topRelation, maxConfidence);

  return {
    id: node.entity_id,
    type: node.entity_type,
    label: node.label,
    summary,
    degree,
    avgConfidence,
    maxConfidence,
    topRelation,
    relevance,
  };
}

function summarizeNodeProperties(node: GraphNode, degree: number, topRelation: string, maxConfidence: number): string {
  const safeProps = (node.properties && typeof node.properties === 'object')
    ? node.properties as Record<string, unknown>
    : {};
  const primary = extractPrimaryProperty(safeProps);
  const relationNote = degree > 0
    ? `Most linked through ${topRelation} with up to ${maxConfidence}% confidence.`
    : 'No connected links are currently available in this subgraph.';
  if (primary) return `${primary} ${relationNote}`;
  return `${prettyType(node.entity_type)} node in current graph context. ${relationNote}`;
}

function extractPrimaryProperty(properties: Record<string, unknown>): string | null {
  const keys = ['summary', 'description', 'abstract', 'indication', 'mechanism', 'snippet', 'content', 'title'];
  for (const key of keys) {
    const value = properties[key];
    if (typeof value !== 'string') continue;
    const text = value.trim();
    if (!text || /^https?:\/\//i.test(text)) continue;
    return text.length > 160 ? `${text.slice(0, 158)}..` : text;
  }
  return null;
}

