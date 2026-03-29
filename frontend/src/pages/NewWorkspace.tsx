/**
 * NewWorkspace — Three-zone workspace shell (SPEC-009 Phase 3).
 *
 * Layout: Toolbar (top 48px) + three-zone body:
 *   Left:   DialoguePanel (280px, collapsible)
 *   Center: Graph canvas (fills remaining space) — ModernGraph
 *   Right:  InspectorPanel (320px, appears on entity selection)
 *
 * Phase 3: Inspector with real data — fetches CatalogEntityDetail
 *          when an entity is selected, graph neighborhood exploration,
 *          entity click from chat entity mentions.
 */

import { useState, useCallback, useRef, useEffect } from 'react';
import '../newui.css';
import Toolbar from '../components/v2/Toolbar';
import DialoguePanel from '../components/v2/DialoguePanel';
import InspectorPanel from '../components/v2/InspectorPanel';
import ModernGraph from '../components/ModernGraph';
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

  // Fetch suggestions when debounced search changes
  useEffect(() => {
    if (debouncedSearch.length < 2) { setSuggestions([]); return; }
    setSuggestionsLoading(true);
    api.searchSuggest(debouncedSearch, 8)
      .then(r => setSuggestions(r.suggestions))
      .catch(() => setSuggestions([]))
      .finally(() => setSuggestionsLoading(false));
  }, [debouncedSearch]);

  // Cmd+K / Ctrl+K focuses search input
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        document.querySelector<HTMLInputElement>('[data-search-input]')?.focus();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

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
          // Extract graph data from response
          if (response.data?.graph_context) {
            setGraphData({
              nodes: response.data.graph_context.nodes || [],
              edges: response.data.graph_context.edges || [],
            });
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
              setGraphData({ nodes: result.nodes, edges: result.edges });
              const center = result.nodes.find(n => n.entity_id === s.entity_id);
              if (center) setSelectedEntity(center);
            })
            .catch(err => console.error('Search select failed:', err));
        }}
        suggestions={suggestions}
        suggestionsLoading={suggestionsLoading}
      />

      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        <DialoguePanel
          messages={messages}
          onSend={handleSend}
          onEntityClick={handleEntityClick}
          isLoading={isLoading}
          collapsed={dialogueCollapsed}
          onToggle={() => setDialogueCollapsed(!dialogueCollapsed)}
        />

        {/* Center: Graph Canvas */}
        <div
          style={{
            flex: 1,
            background: 'var(--surface-graph)',
            position: 'relative',
            minWidth: 0,
          }}
        >
          {/* Collapse/expand toggle for dialogue panel (visible when collapsed) */}
          {dialogueCollapsed && (
            <button
              type="button"
              onClick={() => setDialogueCollapsed(false)}
              title="Show dialogue"
              aria-label="Show dialogue"
              style={{
                position: 'absolute',
                top: 'var(--space-3)',
                left: 'var(--space-3)',
                zIndex: 10,
                width: 32,
                height: 32,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                background: 'rgba(15, 23, 42, 0.85)',
                backdropFilter: 'blur(8px)',
                border: '1px solid rgba(255, 255, 255, 0.1)',
                borderRadius: 'var(--radius-md)',
                cursor: 'pointer',
                color: 'var(--text-inverse)',
                transition: `background var(--duration-fast) ease`,
              }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLElement).style.background =
                  'rgba(15, 23, 42, 0.95)';
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLElement).style.background =
                  'rgba(15, 23, 42, 0.85)';
              }}
            >
              <svg
                width="14"
                height="14"
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

          {graphData && graphData.nodes.length > 0 ? (
            <ModernGraph
              nodes={graphData.nodes}
              edges={graphData.edges}
              centerEntityId={centerEntityId}
              onNodeClick={handleNodeClick}
            />
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
        </div>

        {selectedEntity && (
          <InspectorPanel
            entity={selectedEntity}
            detail={inspectorDetail}
            isLoading={inspectorLoading}
            error={inspectorError}
            onClose={() => setSelectedEntity(null)}
            onExplore={handleExplore}
            onEntityClick={handleEntityClick}
          />
        )}
      </div>
    </div>
  );
}
