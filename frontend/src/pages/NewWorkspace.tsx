/**
 * NewWorkspace — Three-zone workspace shell (SPEC-009 Phase 1).
 *
 * Layout: Toolbar (top 48px) + three-zone body:
 *   Left:   DialoguePanel (280px, collapsible)
 *   Center: Graph canvas (fills remaining space)
 *   Right:  InspectorPanel (320px, appears on entity selection)
 */

import { useState, useCallback } from 'react';
import '../newui.css';
import Toolbar from '../components/v2/Toolbar';
import DialoguePanel from '../components/v2/DialoguePanel';
import InspectorPanel from '../components/v2/InspectorPanel';

interface Message {
  role: 'user' | 'assistant';
  content: string;
}

interface SelectedEntity {
  id: string;
  type: string;
  name: string;
  properties?: Record<string, unknown>;
}

export default function NewWorkspace() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [selectedEntity, setSelectedEntity] = useState<SelectedEntity | null>(null);
  const [dialogueCollapsed, setDialogueCollapsed] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  const handleSearch = useCallback((query: string) => {
    // Phase 1: search adds to dialogue as a user message
    setMessages((prev) => [...prev, { role: 'user', content: query }]);
    setIsLoading(true);
    // Simulate response (Phase 2 will wire to API)
    setTimeout(() => {
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: `Searching for "${query}"... (API integration coming in Phase 2)`,
        },
      ]);
      setIsLoading(false);
    }, 800);
  }, []);

  const handleSend = useCallback((message: string) => {
    setMessages((prev) => [...prev, { role: 'user', content: message }]);
    setIsLoading(true);
    // Simulate response (Phase 2 will wire to API)
    setTimeout(() => {
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: `I received your message: "${message}". Chat integration will be connected in Phase 2.`,
        },
      ]);
      setIsLoading(false);
    }, 800);
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
      <Toolbar onSearch={handleSearch} />

      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        <DialoguePanel
          messages={messages}
          onSend={handleSend}
          isLoading={isLoading}
          collapsed={dialogueCollapsed}
          onToggle={() => setDialogueCollapsed(!dialogueCollapsed)}
        />

        {/* Graph Canvas — fills remaining space */}
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
                (e.currentTarget as HTMLElement).style.background = 'rgba(15, 23, 42, 0.95)';
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLElement).style.background = 'rgba(15, 23, 42, 0.85)';
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

          {/* Empty state placeholder for graph */}
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
                opacity: 0.3,
              }}
            >
              Knowledge Graph
            </div>
            <div
              style={{
                fontSize: 'var(--text-sm)',
                color: 'var(--text-inverse)',
                opacity: 0.2,
                maxWidth: 300,
                textAlign: 'center',
                lineHeight: 1.5,
              }}
            >
              Ask a question or search for an entity to see connections
            </div>

            {/* Demo entity selection buttons */}
            <div
              style={{
                display: 'flex',
                gap: 'var(--space-2)',
                marginTop: 'var(--space-4)',
              }}
            >
              {[
                { id: 'demo-1', type: 'drug', name: 'Semaglutide' },
                { id: 'demo-2', type: 'company', name: 'Novo Nordisk' },
                { id: 'demo-3', type: 'trial', name: 'NCT04567890' },
              ].map((demo) => (
                <button
                  key={demo.id}
                  type="button"
                  onClick={() =>
                    setSelectedEntity(
                      selectedEntity?.id === demo.id ? null : demo,
                    )
                  }
                  style={{
                    padding: 'var(--space-2) var(--space-3)',
                    background: selectedEntity?.id === demo.id
                      ? 'rgba(28, 110, 247, 0.2)'
                      : 'rgba(255, 255, 255, 0.06)',
                    border: selectedEntity?.id === demo.id
                      ? '1px solid rgba(28, 110, 247, 0.4)'
                      : '1px solid rgba(255, 255, 255, 0.1)',
                    borderRadius: 'var(--radius-md)',
                    color: 'var(--text-inverse)',
                    fontSize: 'var(--text-xs)',
                    fontFamily: 'var(--font-body)',
                    cursor: 'pointer',
                    transition: `all var(--duration-fast) ease`,
                    opacity: 0.7,
                  }}
                  onMouseEnter={(e) => {
                    (e.currentTarget as HTMLElement).style.opacity = '1';
                    (e.currentTarget as HTMLElement).style.background = 'rgba(255, 255, 255, 0.1)';
                  }}
                  onMouseLeave={(e) => {
                    (e.currentTarget as HTMLElement).style.opacity = '0.7';
                    (e.currentTarget as HTMLElement).style.background =
                      selectedEntity?.id === demo.id
                        ? 'rgba(28, 110, 247, 0.2)'
                        : 'rgba(255, 255, 255, 0.06)';
                  }}
                >
                  {demo.name}
                </button>
              ))}
            </div>
          </div>
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
