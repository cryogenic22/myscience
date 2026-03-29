/**
 * NewWorkspace — Three-zone workspace shell (SPEC-009 Phase 5).
 *
 * Layout: Toolbar (top 48px) + full-width graph canvas with overlays:
 *   Left:   DialoguePanel (380px glass overlay, collapsible)
 *   Center: Graph canvas (fills entire space) or CurateView
 *   Right:  InspectorPanel (360px glass overlay, on entity selection)
 *
 * Phase 5: Glass overlay dialogue, Curate lens, keyboard shortcuts,
 *          responsive auto-collapse, slide animations.
 */

import { useState, useCallback, useRef, useEffect } from 'react';
import '../newui.css';
import Toolbar from '../components/v2/Toolbar';
import DialoguePanel from '../components/v2/DialoguePanel';
import InspectorPanel from '../components/v2/InspectorPanel';
import CurateView from '../components/v2/CurateView';
import KnowledgeGraph from '../components/KnowledgeGraph';
import { api } from '../api';
import type { ChatResponse, GraphNode, GraphEdge, CatalogEntityDetail, SearchSuggestion } from '../api';
import { useDebounce } from '../hooks/useDebounce';

/** V2 message shape for the new workspace dialogue */
export interface V2Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  loading?: boolean;
  entityMentions?: Array<{ entityId: string; entityType: string; name: string }>;
  followupSuggestions?: string[];
  chatResponse?: ChatResponse;
}

/** Priority order for entity types — higher priority types kept first when capping nodes */
const TYPE_PRIORITY: Record<string, number> = {
  drug: 10, company: 9, mechanism: 8, therapeutic_area: 7,
  trial: 6, event: 5, patent: 4, biomarker: 4,
  investigator: 3, adverse_event: 2, literature: 1,
  trial_location: 0, trial_outcome: 0,
};

const MAX_GRAPH_NODES = 40;

/** Filter graph to keep the most meaningful nodes, capped at MAX_GRAPH_NODES */
function filterGraphData(data: { nodes: GraphNode[]; edges: GraphEdge[] }, centerId?: string) {
  if (data.nodes.length <= MAX_GRAPH_NODES) return data;

  // Score each node: priority by type + bonus for being the center
  const scored = data.nodes.map(n => ({
    node: n,
    score: (TYPE_PRIORITY[n.entity_type] ?? 1) + (n.entity_id === centerId ? 100 : 0),
  }));
  scored.sort((a, b) => b.score - a.score);
  const kept = new Set(scored.slice(0, MAX_GRAPH_NODES).map(s => s.node.entity_id));

  const filteredNodes = data.nodes.filter(n => kept.has(n.entity_id));
  const filteredEdges = data.edges.filter(e => kept.has(e.source_id) && kept.has(e.target_id));
  return { nodes: filteredNodes, edges: filteredEdges };
}

/** Extract entity mentions from a ChatResponse for display in the dialogue */
function extractEntityMentions(
  response: ChatResponse,
): Array<{ entityId: string; entityType: string; name: string }> {
  if (!response.data?.entity_focus) return [];
  return (response.data.entity_focus as Array<Record<string, unknown>>)
    .map((ef) => ({
      entityId: String(ef.entity_id || ef.id || ''),
      entityType: String(ef.entity_type || 'drug'),
      name: String(ef.label || ef.generic_name || ef.name || ''),
    }))
    .filter((m) => m.name.length > 0);
}

/* ── Lens type ───────────────────────────────────────── */

type Lens = 'explore' | 'curate';

/* ── Pipeline / graph summary types for curate lens ── */

interface PipelineConnector {
  source_key: string;
  label: string;
  schedule: string;
  last_run: string | null;
  days_since: number | null;
  records: number;
  status: string;
}

interface GraphSummary {
  link_types: Array<{ type: string; count: number }>;
  total_links: number;
  total_entities: number;
  drug_completeness: Record<string, number>;
}

export default function NewWorkspace() {
  const [messages, setMessages] = useState<V2Message[]>([]);
  const [graphData, setGraphData] = useState<{
    nodes: GraphNode[];
    edges: GraphEdge[];
  } | null>(null);
  const [selectedEntity, setSelectedEntity] = useState<GraphNode | null>(null);
  const [dialogueCollapsed, setDialogueCollapsed] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [queryStatus, setQueryStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Inspector state
  const [inspectorDetail, setInspectorDetail] = useState<CatalogEntityDetail | null>(null);
  const [inspectorLoading, setInspectorLoading] = useState(false);
  const [inspectorError, setInspectorError] = useState<string | null>(null);

  // Search typeahead state
  const [searchValue, setSearchValue] = useState('');
  const [suggestions, setSuggestions] = useState<SearchSuggestion[]>([]);
  const [suggestionsLoading, setSuggestionsLoading] = useState(false);
  const debouncedSearch = useDebounce(searchValue, 300);

  // Lens state (explore vs curate)
  const [lens, setLens] = useState<Lens>('explore');

  // Curate lens data
  const [pipelineStatus, setPipelineStatus] = useState<PipelineConnector[] | null>(null);
  const [graphSummary, setGraphSummary] = useState<GraphSummary | null>(null);

  // Fetch curate data when lens switches to 'curate'
  useEffect(() => {
    if (lens !== 'curate') return;
    api.catalogPipelineStatus()
      .then((r) => setPipelineStatus(r.connectors))
      .catch(() => {});
    api.catalogGraphSummary()
      .then((r) => setGraphSummary(r))
      .catch(() => {});
  }, [lens]);

  // Fetch suggestions when debounced search changes
  useEffect(() => {
    if (debouncedSearch.length < 2) { setSuggestions([]); return; }
    setSuggestionsLoading(true);
    api.searchSuggest(debouncedSearch, 8)
      .then(r => setSuggestions(r.suggestions))
      .catch(() => setSuggestions([]))
      .finally(() => setSuggestionsLoading(false));
  }, [debouncedSearch]);

  // Keyboard shortcuts: Cmd+K search, Cmd+/ toggle dialogue, Escape close inspector
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        document.querySelector<HTMLInputElement>('[data-search-input]')?.focus();
      }
      if ((e.metaKey || e.ctrlKey) && e.key === '/') {
        e.preventDefault();
        setDialogueCollapsed((prev) => !prev);
      }
      if (e.key === 'Escape') {
        if (selectedEntity) setSelectedEntity(null);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [selectedEntity]);

  // Responsive: auto-collapse dialogue on narrow viewports
  useEffect(() => {
    const mq = window.matchMedia('(max-width: 1024px)');
    const handleChange = (e: MediaQueryListEvent | MediaQueryList) => {
      if (e.matches) setDialogueCollapsed(true);
    };
    handleChange(mq); // check on mount
    mq.addEventListener('change', handleChange);
    return () => mq.removeEventListener('change', handleChange);
  }, []);

  // Seed graph on mount — show a few entities so the canvas isn't empty
  useEffect(() => {
    api.searchSuggest('drug', 6)
      .then(r => {
        if (r.suggestions?.length) {
          const firstEntity = r.suggestions[0];
          return api.traverse(firstEntity.entity_type, firstEntity.entity_id, 1);
        }
        return null;
      })
      .then(result => {
        if (result && result.nodes?.length && !graphData) {
          setGraphData(filterGraphData({ nodes: result.nodes, edges: result.edges }));
        }
      })
      .catch(() => {}); // silent — seed graph is optional
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Fetch entity detail when selectedEntity changes
  useEffect(() => {
    if (!selectedEntity) {
      setInspectorDetail(null);
      setInspectorError(null);
      return;
    }

    const controller = new AbortController();
    setInspectorLoading(true);
    setInspectorError(null);

    api
      .catalogEntityDetail(selectedEntity.entity_type, selectedEntity.entity_id)
      .then((detail) => {
        if (!controller.signal.aborted) setInspectorDetail(detail);
      })
      .catch((err) => {
        if (!controller.signal.aborted) setInspectorError(String(err));
      })
      .finally(() => {
        if (!controller.signal.aborted) setInspectorLoading(false);
      });

    return () => controller.abort();
  }, [selectedEntity?.entity_id, selectedEntity?.entity_type]);

  // Explore neighborhood: fetch and merge graph data
  const handleExplore = useCallback(
    async (entityType: string, entityId: string) => {
      try {
        const result = await api.traverse(entityType, entityId, 2);
        // Merge with existing graph data (deduplicate)
        setGraphData((prev) => {
          if (!prev) return { nodes: result.nodes, edges: result.edges };
          const nodeMap = new Map(prev.nodes.map((n) => [n.entity_id, n]));
          result.nodes.forEach((n) => nodeMap.set(n.entity_id, n));
          const edgeSet = new Set(
            prev.edges.map((e) => `${e.source_id}-${e.target_id}-${e.link_type}`),
          );
          const newEdges = result.edges.filter(
            (e) => !edgeSet.has(`${e.source_id}-${e.target_id}-${e.link_type}`),
          );
          return {
            nodes: Array.from(nodeMap.values()),
            edges: [...prev.edges, ...newEdges],
          };
        });
        // Center on the explored entity
        const found = result.nodes.find((n) => n.entity_id === entityId);
        if (found) setSelectedEntity(found);
      } catch (err) {
        console.error('Explore failed:', err);
      }
    },
    [],
  );

  const handleSend = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || isLoading) return;

      // Abort previous in-flight request
      abortRef.current?.abort();
      abortRef.current = new AbortController();

      // Create user + placeholder assistant messages
      const userMsg: V2Message = {
        id: crypto.randomUUID(),
        role: 'user',
        content: trimmed,
        timestamp: new Date(),
      };
      const assistantMsg: V2Message = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: '',
        timestamp: new Date(),
        loading: true,
      };

      setMessages((prev) => [...prev, userMsg, assistantMsg]);
      setIsLoading(true);
      setQueryStatus('Understanding query...');
      setError(null);

      // Build conversation history from recent messages (last 6, truncated)
      const history = messages.slice(-6).map((m) => ({
        role: m.role,
        content: m.content.slice(0, 500),
      }));

      const chatModes = {
        include_graph: true,
        include_metrics: true,
        source_strict: true,
      };

      let streamComplete = false;

      // Try streaming first, then fallback to non-streaming
      try {
        let narrative = '';
        let response: ChatResponse | undefined;

        try {
          await api.chatStream(trimmed, chatModes, history, {
            onToken: (token: string) => {
              narrative += token;
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantMsg.id
                    ? { ...m, content: narrative, loading: false }
                    : m,
                ),
              );
            },
            onStatus: (status: string) => {
              setQueryStatus(status);
            },
            onDone: (payload: ChatResponse) => {
              response = payload;
              streamComplete = true;
            },
            onError: () => {
              /* fall through to non-streaming */
            },
          });
        } catch {
          /* fall through to non-streaming fallback */
        }

        // Fallback to non-streaming if stream did not complete
        if (!streamComplete) {
          response = await api.chat(trimmed, chatModes, history);
        }

        if (response) {
          // Extract graph data from response (filtered to top entities)
          if (response.data?.graph_context) {
            const raw = {
              nodes: response.data.graph_context.nodes || [],
              edges: response.data.graph_context.edges || [],
            };
            const centerId = response.data?.entity_focus?.[0]?.entity_id;
            setGraphData(filterGraphData(raw, centerId));
          }

          // Update assistant message with final response
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsg.id
                ? {
                    ...m,
                    content: response!.narrative || narrative || 'No response generated.',
                    loading: false,
                    followupSuggestions: response!.followup_suggestions,
                    chatResponse: response,
                    entityMentions: extractEntityMentions(response!),
                  }
                : m,
            ),
          );
        }
      } catch (err) {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMsg.id
              ? {
                  ...m,
                  content: 'Failed to get response. Please try again.',
                  loading: false,
                }
              : m,
          ),
        );
        setError(String(err));
      } finally {
        setIsLoading(false);
        setQueryStatus(null);
      }
    },
    [messages, isLoading],
  );

  // Derive center entity ID from the latest response's entity focus
  const centerEntityId = (() => {
    // Find the last assistant message with entity mentions
    for (let i = messages.length - 1; i >= 0; i--) {
      const msg = messages[i];
      if (msg.role === 'assistant' && msg.entityMentions?.length) {
        return msg.entityMentions[0].entityId;
      }
    }
    return undefined;
  })();

  // Handle node click from graph — populate inspector
  const handleNodeClick = useCallback((node: GraphNode) => {
    setSelectedEntity(node);
  }, []);

  // Handle entity click from chat mentions or inspector relationships
  const handleEntityClick = useCallback(
    (entityId: string, entityType: string) => {
      // Try to find in current graph first
      const node = graphData?.nodes.find((n) => n.entity_id === entityId);
      if (node) {
        setSelectedEntity(node);
      } else {
        // Entity not in graph yet — fetch its neighborhood
        handleExplore(entityType, entityId);
      }
    },
    [graphData, handleExplore],
  );

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100vh',
        width: '100vw',
        background: 'var(--surface-primary)',
        fontFamily: 'var(--font-body)',
      }}
    >
      <Toolbar
        onSearch={(q) => handleSend(q)}
        onSearchChange={setSearchValue}
        onSearchSelect={(s) => {
          setSuggestions([]);
          setSearchValue('');
          api.traverse(s.entity_type, s.entity_id, 2)
            .then(result => {
              setGraphData(filterGraphData({ nodes: result.nodes, edges: result.edges }, s.entity_id));
              const center = result.nodes.find(n => n.entity_id === s.entity_id);
              if (center) setSelectedEntity(center);
            })
            .catch(err => console.error('Search select failed:', err));
        }}
        suggestions={suggestions}
        suggestionsLoading={suggestionsLoading}
        lens={lens}
        onLensChange={setLens}
      />

      {/* Body: graph fills full width, panels overlay */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden', position: 'relative' }}>
        {/* Graph / CurateView fills FULL width */}
        <div
          style={{
            flex: 1,
            background: 'var(--surface-graph)',
            position: 'relative',
            minWidth: 0,
          }}
        >
          {lens === 'explore' ? (
            <>
              {graphData && graphData.nodes.length > 0 ? (
                <>
                  <KnowledgeGraph
                    nodes={graphData.nodes}
                    edges={graphData.edges}
                    centerEntityId={centerEntityId}
                    onNodeClick={handleNodeClick}
                  />
                  {/* Node count badge — top right of graph */}
                  <div
                    style={{
                      position: 'absolute',
                      top: 'var(--space-3)',
                      right: 'var(--space-3)',
                      padding: 'var(--space-1) var(--space-3)',
                      borderRadius: 'var(--radius-full)',
                      background: 'rgba(15, 23, 42, 0.8)',
                      backdropFilter: 'blur(6px)',
                      border: '1px solid rgba(255,255,255,0.08)',
                      fontSize: 'var(--text-xs)',
                      color: 'rgba(226, 232, 240, 0.6)',
                      fontFamily: 'var(--font-mono)',
                      zIndex: 10,
                      pointerEvents: 'none',
                    }}
                  >
                    {graphData.nodes.length} entities · {graphData.edges.length} connections
                  </div>
                </>
              ) : (
                /* Empty state: calm, inviting */
                <div
                  style={{
                    position: 'absolute',
                    inset: 0,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flexDirection: 'column',
                    gap: 'var(--space-4)',
                  }}
                >
                  <div
                    style={{
                      fontFamily: 'var(--font-display)',
                      fontSize: 'var(--text-2xl)',
                      color: 'var(--text-inverse)',
                      opacity: 0.2,
                    }}
                  >
                    Knowledge Graph
                  </div>
                  <div
                    style={{
                      fontSize: 'var(--text-sm)',
                      color: 'var(--text-inverse)',
                      opacity: 0.15,
                      maxWidth: 300,
                      textAlign: 'center',
                      lineHeight: 1.5,
                    }}
                  >
                    Ask a question or search for an entity to see connections
                  </div>
                </div>
              )}
              {/* Loading overlay on graph during API calls */}
              {isLoading && (
                <div
                  style={{
                    position: 'absolute',
                    top: 'var(--space-3)',
                    left: '50%',
                    transform: 'translateX(-50%)',
                    padding: 'var(--space-2) var(--space-4)',
                    borderRadius: 'var(--radius-full)',
                    background: 'rgba(15, 23, 42, 0.85)',
                    backdropFilter: 'blur(6px)',
                    border: '1px solid rgba(255,255,255,0.08)',
                    fontSize: 'var(--text-xs)',
                    color: 'rgba(226, 232, 240, 0.7)',
                    fontFamily: 'var(--font-body)',
                    zIndex: 15,
                    display: 'flex',
                    alignItems: 'center',
                    gap: 'var(--space-2)',
                    pointerEvents: 'none',
                    animation: 'fade-in var(--duration-normal) var(--ease-out)',
                  }}
                >
                  <span
                    style={{
                      width: '6px',
                      height: '6px',
                      borderRadius: '50%',
                      background: 'var(--accent)',
                      animation: 'pulse-dot 1.2s ease-in-out infinite',
                    }}
                  />
                  {queryStatus || 'Loading...'}
                </div>
              )}
            </>
          ) : (
            <CurateView
              pipelineStatus={pipelineStatus}
              graphSummary={graphSummary}
              onRefreshSource={(src) => {
                fetch('/steward/refresh', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ source: src }),
                }).catch(() => {});
              }}
            />
          )}

          {/* Collapse/expand toggle for dialogue panel (visible when collapsed) */}
          {dialogueCollapsed && (
            <button
              type="button"
              onClick={() => setDialogueCollapsed(false)}
              title="Show dialogue (Ctrl+/)"
              aria-label="Show dialogue"
              style={{
                position: 'absolute',
                top: 'var(--space-3)',
                left: 'var(--space-3)',
                zIndex: 10,
                width: 40,
                height: 40,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                background: 'var(--surface-elevated)',
                boxShadow: 'var(--shadow-md)',
                border: 'none',
                borderRadius: 'var(--radius-full)',
                cursor: 'pointer',
                color: 'var(--text-secondary)',
                transition: `background var(--duration-fast) ease`,
              }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLElement).style.boxShadow = 'var(--shadow-lg)';
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLElement).style.boxShadow = 'var(--shadow-md)';
              }}
            >
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M7.9 20A9 9 0 1 0 4 16.1L2 22Z" />
              </svg>
            </button>
          )}

          {/* Query status overlay */}
          {queryStatus && (
            <div
              style={{
                position: 'absolute',
                top: 'var(--space-3)',
                left: '50%',
                transform: 'translateX(-50%)',
                zIndex: 10,
                padding: 'var(--space-1) var(--space-4)',
                background: 'rgba(15, 23, 42, 0.85)',
                backdropFilter: 'blur(8px)',
                WebkitBackdropFilter: 'blur(8px)',
                border: '1px solid rgba(255, 255, 255, 0.1)',
                borderRadius: 'var(--radius-full)',
                fontSize: 'var(--text-xs)',
                color: 'var(--text-inverse)',
                opacity: 0.8,
              }}
            >
              {queryStatus}
            </div>
          )}

          {/* Error indicator */}
          {error && !isLoading && (
            <div
              style={{
                position: 'absolute',
                bottom: 'var(--space-3)',
                left: '50%',
                transform: 'translateX(-50%)',
                zIndex: 10,
                padding: 'var(--space-1) var(--space-4)',
                background: 'rgba(239, 68, 68, 0.15)',
                border: '1px solid rgba(239, 68, 68, 0.3)',
                borderRadius: 'var(--radius-md)',
                fontSize: 'var(--text-xs)',
                color: '#fca5a5',
                maxWidth: 400,
                textAlign: 'center',
              }}
            >
              Connection issue. Responses may be delayed.
            </div>
          )}
        </div>

        {/* Dialogue overlays the left side */}
        {!dialogueCollapsed && (
          <div
            style={{
              position: 'absolute',
              top: 0,
              left: 0,
              bottom: 0,
              width: 380,
              background: 'var(--surface-glass)',
              backdropFilter: 'blur(12px)',
              WebkitBackdropFilter: 'blur(12px)',
              borderRight: '1px solid rgba(0,0,0,0.06)',
              zIndex: 10,
              display: 'flex',
              flexDirection: 'column',
              boxShadow: 'var(--shadow-lg)',
              animation: 'slide-in-left var(--duration-normal) var(--ease-out)',
            }}
          >
            <DialoguePanel
              messages={messages}
              onSend={handleSend}
              onEntityClick={handleEntityClick}
              isLoading={isLoading}
              collapsed={dialogueCollapsed}
              onToggle={() => setDialogueCollapsed(true)}
            />
          </div>
        )}

        {/* Inspector overlays the right side */}
        {selectedEntity && (
          <div
            style={{
              position: 'absolute',
              top: 0,
              right: 0,
              bottom: 0,
              width: 360,
              background: 'var(--surface-glass)',
              backdropFilter: 'blur(12px)',
              WebkitBackdropFilter: 'blur(12px)',
              borderLeft: '1px solid rgba(0,0,0,0.06)',
              zIndex: 10,
              boxShadow: 'var(--shadow-lg)',
              overflow: 'auto',
              animation: 'slide-in-right var(--duration-normal) var(--ease-out)',
            }}
          >
            <InspectorPanel
              entity={selectedEntity}
              detail={inspectorDetail}
              isLoading={inspectorLoading}
              error={inspectorError}
              onClose={() => setSelectedEntity(null)}
              onExplore={handleExplore}
              onEntityClick={handleEntityClick}
            />
          </div>
        )}
      </div>
    </div>
  );
}
