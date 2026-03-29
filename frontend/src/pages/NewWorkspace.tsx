/**
 * NewWorkspace — Three-zone workspace shell (SPEC-009 Phase 2).
 *
 * Layout: Toolbar (top 48px) + three-zone body:
 *   Left:   DialoguePanel (280px, collapsible)
 *   Center: Graph canvas (fills remaining space) — ModernGraph
 *   Right:  InspectorPanel (320px, appears on entity selection)
 *
 * Phase 2: Real chat API integration (streaming + fallback),
 *          graph rendering from API response, follow-up suggestions.
 */

import { useState, useCallback, useRef } from 'react';
import '../newui.css';
import Toolbar from '../components/v2/Toolbar';
import DialoguePanel from '../components/v2/DialoguePanel';
import InspectorPanel from '../components/v2/InspectorPanel';
import ModernGraph from '../components/ModernGraph';
import { api } from '../api';
import type { ChatResponse, GraphNode, GraphEdge } from '../api';

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
  const [selectedEntity, setSelectedEntity] = useState<{
    id: string;
    type: string;
    name: string;
    properties?: Record<string, unknown>;
  } | null>(null);
  const [dialogueCollapsed, setDialogueCollapsed] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [queryStatus, setQueryStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

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
    setSelectedEntity({
      id: node.entity_id,
      type: node.entity_type,
      name: node.label,
      properties: node.properties,
    });
  }, []);

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
      <Toolbar onSearch={(q) => handleSend(q)} />

      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        <DialoguePanel
          messages={messages}
          onSend={handleSend}
          isLoading={isLoading}
          queryStatus={queryStatus}
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
            onClose={() => setSelectedEntity(null)}
          />
        )}
      </div>
    </div>
  );
}
