/**
 * DialoguePanel — left panel for chat interaction.
 * Scrollable message list + fixed input at bottom.
 */

import { useState, useCallback, useRef, useEffect } from 'react';
import Panel from './Panel';
import Button from './Button';

interface Message {
  role: 'user' | 'assistant';
  content: string;
}

interface DialoguePanelProps {
  messages: Message[];
  onSend: (message: string) => void;
  isLoading?: boolean;
  collapsed?: boolean;
  onToggle?: () => void;
}

export default function DialoguePanel({
  messages,
  onSend,
  isLoading,
  collapsed,
  onToggle,
}: DialoguePanelProps) {
  const [inputValue, setInputValue] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

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
    <Panel side="left" width={280} collapsed={collapsed}>
      {/* Toggle button — visible when collapsed */}
      {onToggle && (
        <button
          type="button"
          onClick={onToggle}
          title={collapsed ? 'Show dialogue' : 'Hide dialogue'}
          aria-label={collapsed ? 'Show dialogue' : 'Hide dialogue'}
          style={{
            position: 'absolute',
            top: 'var(--space-3)',
            right: collapsed ? 'auto' : 'var(--space-3)',
            left: collapsed ? 'var(--space-3)' : 'auto',
            zIndex: 10,
            width: 24,
            height: 24,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: 'var(--surface-inset)',
            border: 'none',
            borderRadius: 'var(--radius-sm)',
            cursor: 'pointer',
            color: 'var(--text-tertiary)',
            fontSize: 'var(--text-xs)',
            transition: `background var(--duration-fast) ease`,
          }}
          onMouseEnter={(e) => {
            (e.currentTarget as HTMLElement).style.background = 'var(--border-subtle)';
          }}
          onMouseLeave={(e) => {
            (e.currentTarget as HTMLElement).style.background = 'var(--surface-inset)';
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
            {collapsed ? (
              <>
                <path d="m9 18 6-6-6-6" />
              </>
            ) : (
              <>
                <path d="m15 18-6-6 6-6" />
              </>
            )}
          </svg>
        </button>
      )}

      {/* Header */}
      <div
        style={{
          padding: 'var(--space-3) var(--space-4)',
          borderBottom: '1px solid var(--border-subtle)',
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
          }}
        >
          Dialogue
        </span>
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
        {messages.length === 0 && (
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
                color: 'var(--text-quaternary)',
              }}
            >
              Ask a question about pharma data
            </div>
          </div>
        )}

        {messages.map((msg, i) => (
          <div
            key={i}
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: msg.role === 'user' ? 'flex-end' : 'flex-start',
            }}
          >
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
              {msg.content}
            </div>
          </div>
        ))}

        {isLoading && (
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
                background: 'var(--accent-primary)',
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
          borderTop: '1px solid var(--border-subtle)',
          flexShrink: 0,
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'flex-end',
            gap: 'var(--space-2)',
            background: 'var(--surface-inset)',
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
    </Panel>
  );
}
