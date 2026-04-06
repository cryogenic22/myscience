import { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowUp, Loader2, Sparkles } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import type { Message } from '../ChatMessage';
import type { GraphNode, GraphEdge } from '../../api';
import NarrativeMessage from './NarrativeMessage';
import QueryProgress from './QueryProgress';

interface ChatPanelProps {
  messages: Message[];
  onSend: (question: string) => void;
  isLoading: boolean;
  queryStatus?: string | null;
  followupSuggestions?: string[];
  onFollowUp?: (q: string) => void;
  onCitationClick?: (index: number) => void;
  onViewInGraph?: (nodes: GraphNode[], edges: GraphEdge[]) => void;
  /** External input to pre-fill (e.g. from graph right-click menu).
   *  Use an object with a seq key to force re-application even for identical text. */
  externalInput?: { text: string; seq: number } | string | null;
}

const STARTER_GROUPS = [
  {
    queries: [
      'What is the GLP-1 competitive landscape?',
      'Compare semaglutide vs tirzepatide',
    ],
  },
  {
    queries: [
      "Show me Novo Nordisk's portfolio",
      'Phase 3 trials for diabetes drugs',
    ],
  },
  {
    queries: [
      'Which mechanisms are most crowded?',
      'SGLT2 inhibitors in heart failure',
    ],
  },
];

export default function ChatPanel({
  messages,
  onSend,
  isLoading,
  queryStatus,
  onFollowUp,
  onCitationClick,
  onViewInGraph,
  externalInput,
}: ChatPanelProps) {
  const [input, setInput] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const isEmpty = messages.length === 0;
  const lastExternalSeqRef = useRef<number>(-1);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => { inputRef.current?.focus(); }, []);

  // Accept external input (e.g. from graph context menu)
  useEffect(() => {
    if (externalInput == null) return;
    const text = typeof externalInput === 'string' ? externalInput : externalInput.text;
    const seq = typeof externalInput === 'string' ? 0 : externalInput.seq;
    if (seq === lastExternalSeqRef.current) return;
    lastExternalSeqRef.current = seq;
    setInput(text);
    // Focus the textarea so user can edit or hit Enter
    requestAnimationFrame(() => inputRef.current?.focus());
  }, [externalInput]);

  const handleSend = useCallback(() => {
    const trimmed = input.trim();
    if (!trimmed || isLoading) return;
    onSend(trimmed);
    setInput('');
    if (inputRef.current) inputRef.current.style.height = 'auto';
  }, [input, isLoading, onSend]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    const el = e.target;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
  };

  const handleFollowUp = useCallback(
    (q: string) => (onFollowUp ?? onSend)(q),
    [onFollowUp, onSend],
  );

  return (
    <div
      className="flex h-full flex-col"
      style={{ background: 'var(--color-surface)' }}
    >
      {/* Messages */}
      <div
        className="flex-1 overflow-y-auto"
        style={{ minHeight: 0 }}
      >
        <div
          className="mx-auto"
          style={{ maxWidth: '680px', padding: '32px 28px' }}
        >
          {isEmpty ? (
            <EmptyState onQuery={(q) => onSend(q)} />
          ) : (
            <div className="space-y-10">
              <AnimatePresence initial={false}>
                {messages.map((message) => (
                  <NarrativeMessage
                    key={message.id}
                    message={message}
                    isUser={message.role === 'user'}
                    onFollowUp={handleFollowUp}
                    onCitationClick={onCitationClick}
                    onViewInGraph={onViewInGraph}
                  />
                ))}
              </AnimatePresence>
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>
      </div>

      {/* Input bar */}
      <div
        style={{ borderTop: '1px solid var(--color-line)', padding: '20px 28px', flexShrink: 0 }}
      >
        <div
          className="mx-auto chat-input-bar"
          style={{ maxWidth: '680px' }}
        >
          <textarea
            ref={inputRef}
            value={input}
            onChange={handleInput}
            onKeyDown={handleKeyDown}
            placeholder={isEmpty
              ? 'Ask about drugs, trials, companies, mechanisms…'
              : 'Follow-up question…'
            }
            rows={1}
            className="input-ghost"
            style={{
              minHeight: '24px',
              maxHeight: '96px',
              resize: 'none',
              fontSize: '14px',
              lineHeight: '1.6',
            }}
            disabled={isLoading}
          />
          <div className="flex items-center justify-between mt-3">
            <p
              style={{
                fontSize: '11px',
                color: 'var(--color-ink-4)',
              }}
            >
              Grounded in knowledge graph · {'{'}⌘ + Enter{'}'} to send
            </p>
            <button
              type="button"
              onClick={handleSend}
              disabled={!input.trim() || isLoading}
              className="btn btn-accent btn-sm"
              style={{
                width: '34px',
                height: '34px',
                padding: 0,
                borderRadius: '10px',
                flexShrink: 0,
              }}
              aria-label="Send"
            >
              {isLoading ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <ArrowUp size={14} />
              )}
            </button>
          </div>
        </div>
        <div className="mx-auto" style={{ maxWidth: '680px' }}>
          <QueryProgress status={queryStatus ?? null} visible={isLoading} />
        </div>
      </div>
    </div>
  );
}

function EmptyState({ onQuery }: { onQuery: (q: string) => void }) {
  return (
    <div
      className="flex min-h-[60vh] flex-col items-center justify-center"
      style={{ paddingTop: '8vh' }}
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
        className="mb-8 flex h-14 w-14 items-center justify-center rounded-2xl"
        style={{
          background: 'var(--color-accent-soft)',
          color: 'var(--color-accent)',
        }}
      >
        <Sparkles size={26} />
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1, duration: 0.5 }}
        className="text-center mb-12"
      >
        <h2
          className="font-display text-[28px] font-light tracking-tight mb-3"
          style={{ color: 'var(--color-ink)' }}
        >
          Pharma Intelligence
        </h2>
        <p
          className="text-[14px] leading-relaxed"
          style={{ color: 'var(--color-ink-3)', maxWidth: '480px' }}
        >
          Evidence-grounded answers across drugs, clinical trials,
          companies, and therapeutic areas.
        </p>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2, duration: 0.5 }}
        className="w-full"
        style={{ maxWidth: '720px' }}
      >
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
          {STARTER_GROUPS.map((group, gi) =>
            group.queries.map((query, qi) => (
              <button
                key={`${gi}-${qi}`}
                type="button"
                onClick={() => onQuery(query)}
                className="group rounded-xl transition-all duration-200"
                style={{
                  background: 'var(--color-surface-2)',
                  fontSize: '13px',
                  color: 'var(--color-ink-3)',
                  lineHeight: 1.5,
                  border: '1px solid transparent',
                  padding: '14px 20px',
                  textAlign: 'center',
                }}
                onMouseEnter={e => {
                  (e.currentTarget as HTMLButtonElement).style.background = 'var(--color-surface)';
                  (e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--color-line)';
                  (e.currentTarget as HTMLButtonElement).style.color = 'var(--color-ink)';
                }}
                onMouseLeave={e => {
                  (e.currentTarget as HTMLButtonElement).style.background = 'var(--color-surface-2)';
                  (e.currentTarget as HTMLButtonElement).style.borderColor = 'transparent';
                  (e.currentTarget as HTMLButtonElement).style.color = 'var(--color-ink-3)';
                }}
              >
                {query}
              </button>
            ))
          )}
        </div>
      </motion.div>
    </div>
  );
}
