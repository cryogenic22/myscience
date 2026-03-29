/**
 * DialoguePanel — left panel for chat interaction.
 * Scrollable message list + fixed input at bottom.
 * Supports V2Message (rich) and legacy {role, content} formats.
 *
 * Phase 5: Renders directly without Panel wrapper — the parent
 * overlay div handles positioning, backdrop-filter, and width.
 */

import { useState, useCallback, useRef, useEffect } from 'react';
import Button from './Button';
import RichNarrative, { type EntityMentionData } from './RichNarrative';

/* ── V2 message type ───────────────────────────────────── */

export interface V2Message {
  id?: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp?: Date;
  loading?: boolean;
  entityMentions?: EntityMentionData[];
  followupSuggestions?: string[];
}

interface DialoguePanelProps {
  messages: V2Message[];
  onSend: (message: string) => void;
  onEntityClick?: (entityId: string, entityType: string) => void;
  isLoading?: boolean;
  collapsed?: boolean;
  onToggle?: () => void;
}

/* ── Helpers ───────────────────────────────────────────── */

function relativeTime(date: Date): string {
  const seconds = Math.floor((Date.now() - date.getTime()) / 1000);
  if (seconds < 60) return 'just now';
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return date.toLocaleDateString();
}

interface NormalizedMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  loading?: boolean;
  entityMentions?: EntityMentionData[];
  followupSuggestions?: string[];
}

function normalizeMessages(messages: V2Message[]): NormalizedMessage[] {
  return messages.map((m, i) => ({
    id: m.id || `msg-${i}`,
    role: m.role,
    content: m.content,
    timestamp: m.timestamp || new Date(),
    loading: m.loading,
    entityMentions: m.entityMentions,
    followupSuggestions: m.followupSuggestions,
  }));
}

/* ── Component ─────────────────────────────────────────── */

export default function DialoguePanel({
  messages,
  onSend,
  onEntityClick,
  isLoading,
  collapsed,
  onToggle,
}: DialoguePanelProps) {
  const [inputValue, setInputValue] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const normalized = normalizeMessages(messages);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages.length]);

  const handleSend = useCallback(() => {
    const trimmed = inputValue.trim();
    if (trimmed && !isLoading) {
      onSend(trimmed);
      setInputValue('');
      // Reset textarea height
      if (inputRef.current) {
        inputRef.current.style.height = 'auto';
      }
    }
  }, [inputValue, isLoading, onSend]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend],
  );

  const handleInput = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInputValue(e.target.value);
    // Auto-resize textarea
    const el = e.target;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 120) + 'px';
  }, []);

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        overflow: 'hidden',
      }}
    >
      {/* Header with collapse toggle */}
      <div
        style={{
          padding: 'var(--space-3) var(--space-4)',
          borderBottom: '1px solid var(--surface-secondary)',
          display: 'flex',
          alignItems: 'center',
          gap: 'var(--space-2)',
          flexShrink: 0,
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
          style={{ color: 'var(--text-tertiary)', flexShrink: 0 }}
        >
          <path d="M7.9 20A9 9 0 1 0 4 16.1L2 22Z" />
        </svg>
        <span
          style={{
            fontSize: 'var(--text-sm)',
            fontWeight: 500,
            color: 'var(--text-primary)',
            flex: 1,
          }}
        >
          Dialogue
        </span>
        {onToggle && (
          <button
            type="button"
            onClick={onToggle}
            title="Hide dialogue"
            aria-label="Hide dialogue"
            style={{
              width: 24,
              height: 24,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              background: 'transparent',
              border: 'none',
              borderRadius: 'var(--radius-sm)',
              cursor: 'pointer',
              color: 'var(--text-tertiary)',
              flexShrink: 0,
              transition: `color var(--duration-fast) ease`,
            }}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLElement).style.color = 'var(--text-secondary)';
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLElement).style.color = 'var(--text-tertiary)';
            }}
          >
            <svg
              width="12"
              height="12"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="m15 18-6-6 6-6" />
            </svg>
          </button>
        )}
      </div>

      {/* Messages */}
      <div
        style={{
          flex: 1,
          overflowY: 'auto',
          padding: 'var(--space-4)',
          display: 'flex',
          flexDirection: 'column',
          gap: 'var(--space-4)',
        }}
      >
        {normalized.length === 0 && (
          <div
            style={{
              flex: 1,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexDirection: 'column',
              gap: 'var(--space-2)',
              textAlign: 'center',
              padding: 'var(--space-6)',
            }}
          >
            <div
              style={{
                fontSize: 'var(--text-sm)',
                color: 'var(--text-tertiary)',
              }}
            >
              Ask a question about pharma data
            </div>
          </div>
        )}

        {normalized.map((msg, i) => (
          <div
            key={msg.id}
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: msg.role === 'user' ? 'flex-end' : 'flex-start',
            }}
          >
            {/* Message bubble / narrative */}
            <div
              style={{
                maxWidth: '90%',
                padding: 'var(--space-2) var(--space-3)',
                borderRadius:
                  msg.role === 'user'
                    ? 'var(--radius-lg) var(--radius-lg) var(--space-1) var(--radius-lg)'
                    : 'var(--radius-lg) var(--radius-lg) var(--radius-lg) var(--space-1)',
                background:
                  msg.role === 'user' ? 'var(--accent-soft)' : 'var(--surface-primary)',
                fontSize: 'var(--text-sm)',
                lineHeight: 1.5,
                color: 'var(--text-primary)',
                wordBreak: 'break-word',
              }}
            >
              {/* Loading state */}
              {msg.loading ? (
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 'var(--space-1)',
                    padding: 'var(--space-1) 0',
                  }}
                >
                  {[0, 1, 2].map((dot) => (
                    <span
                      key={dot}
                      style={{
                        display: 'inline-block',
                        width: 6,
                        height: 6,
                        borderRadius: 'var(--radius-full)',
                        background: 'var(--accent)',
                        opacity: 0.6,
                        animation: `pulse-dot 1.4s ease-in-out ${dot * 0.2}s infinite`,
                      }}
                    />
                  ))}
                </div>
              ) : msg.role === 'assistant' ? (
                <RichNarrative
                  text={msg.content}
                  entityMentions={msg.entityMentions}
                  onEntityClick={onEntityClick}
                />
              ) : (
                msg.content
              )}
            </div>

            {/* Timestamp */}
            <div
              style={{
                fontSize: 'var(--text-xs)',
                color: 'var(--text-tertiary)',
                marginTop: 'var(--space-1)',
                paddingLeft: msg.role === 'user' ? 0 : 'var(--space-1)',
                paddingRight: msg.role === 'user' ? 'var(--space-1)' : 0,
              }}
            >
              {relativeTime(msg.timestamp)}
            </div>

            {/* Follow-up suggestions — shown after last assistant message, not loading */}
            {msg.role === 'assistant' &&
              i === normalized.length - 1 &&
              msg.followupSuggestions &&
              msg.followupSuggestions.length > 0 &&
              !isLoading && (
                <div
                  style={{
                    display: 'flex',
                    flexWrap: 'wrap',
                    gap: 'var(--space-2)',
                    padding: 'var(--space-2) 0',
                    marginTop: 'var(--space-2)',
                  }}
                >
                  {msg.followupSuggestions.slice(0, 4).map((s, si) => (
                    <button
                      key={si}
                      onClick={() => onSend(s)}
                      style={{
                        fontSize: 'var(--text-xs)',
                        padding: 'var(--space-1) var(--space-3)',
                        borderRadius: 'var(--radius-full)',
                        border: '1px solid var(--text-tertiary)',
                        background: 'transparent',
                        color: 'var(--text-secondary)',
                        cursor: 'pointer',
                        transition: 'all var(--duration-fast)',
                        whiteSpace: 'nowrap',
                        fontFamily: 'var(--font-body)',
                      }}
                      onMouseEnter={(e) => {
                        (e.target as HTMLElement).style.borderColor = 'var(--accent)';
                        (e.target as HTMLElement).style.color = 'var(--accent)';
                      }}
                      onMouseLeave={(e) => {
                        (e.target as HTMLElement).style.borderColor = 'var(--text-tertiary)';
                        (e.target as HTMLElement).style.color = 'var(--text-secondary)';
                      }}
                    >
                      {s}
                    </button>
                  ))}
                </div>
              )}
          </div>
        ))}

        {/* Global loading indicator (when no loading message is present) */}
        {isLoading && !normalized.some((m) => m.loading) && (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 'var(--space-2)',
              padding: 'var(--space-2) var(--space-3)',
              color: 'var(--text-tertiary)',
              fontSize: 'var(--text-sm)',
            }}
          >
            <span
              style={{
                display: 'inline-block',
                width: 6,
                height: 6,
                borderRadius: 'var(--radius-full)',
                background: 'var(--accent)',
                animation: 'pulse-dot 1.4s ease-in-out infinite',
              }}
            />
            Thinking...
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <div
        style={{
          padding: 'var(--space-3)',
          borderTop: '1px solid var(--surface-secondary)',
          flexShrink: 0,
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'flex-end',
            gap: 'var(--space-2)',
            background: 'var(--surface-secondary)',
            borderRadius: 'var(--radius-md)',
            padding: 'var(--space-2) var(--space-3)',
          }}
        >
          <textarea
            ref={inputRef}
            value={inputValue}
            onChange={handleInput}
            onKeyDown={handleKeyDown}
            placeholder="Ask anything..."
            rows={1}
            style={{
              flex: 1,
              border: 'none',
              background: 'transparent',
              fontFamily: 'var(--font-body)',
              fontSize: 'var(--text-sm)',
              color: 'var(--text-primary)',
              resize: 'none',
              outline: 'none',
              lineHeight: 1.5,
              maxHeight: 120,
              minHeight: 20,
            }}
          />
          <Button
            variant="accent"
            size="sm"
            onClick={handleSend}
            disabled={!inputValue.trim() || isLoading}
            title="Send message"
            aria-label="Send message"
            icon={
              <svg
                width="12"
                height="12"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="m5 12 7-7 7 7" />
                <path d="M12 19V5" />
              </svg>
            }
            style={{
              width: 28,
              height: 28,
              padding: 0,
              borderRadius: 'var(--radius-sm)',
              flexShrink: 0,
            }}
          />
        </div>
      </div>
    </div>
  );
}
