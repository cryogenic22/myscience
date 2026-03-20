import { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowRight, Loader2, Send, Sparkles, BarChart3, Search, Target } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import type { Message } from '../ChatMessage';
import NarrativeMessage from './NarrativeMessage';

interface ChatPanelProps {
  messages: Message[];
  onSend: (question: string) => void;
  isLoading: boolean;
  followupSuggestions?: string[];
  onFollowUp?: (q: string) => void;
  onCitationClick?: (index: number) => void;
}

const STARTER_CATEGORIES = [
  {
    label: 'Compare & Analyze',
    icon: BarChart3,
    color: 'text-violet-500',
    queries: [
      'Compare semaglutide vs tirzepatide',
      'Tabular breakdown of the GLP-1 landscape',
    ],
  },
  {
    label: 'Explore Entities',
    icon: Search,
    color: 'text-blue-500',
    queries: [
      'What is semaglutide?',
      "Show me Novo Nordisk's portfolio",
    ],
  },
  {
    label: 'Deep Dive',
    icon: Target,
    color: 'text-emerald-500',
    queries: [
      'Phase 3 trial analysis for diabetes drugs',
      'Which mechanisms are most crowded?',
    ],
  },
];

export default function ChatPanel({
  messages,
  onSend,
  isLoading,
  onFollowUp,
  onCitationClick,
}: ChatPanelProps) {
  const [input, setInput] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => { inputRef.current?.focus(); }, []);

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
    // Auto-resize textarea
    const el = e.target;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
  };

  const handleFollowUp = useCallback(
    (q: string) => (onFollowUp ?? onSend)(q),
    [onFollowUp, onSend],
  );

  const isEmpty = messages.length === 0;

  return (
    <div className="flex h-full flex-col">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-2xl px-6 py-8">
          {isEmpty ? (
            <EmptyState onQuery={(q) => { setInput(''); onSend(q); }} />
          ) : (
            <div className="space-y-8">
              <AnimatePresence initial={false}>
                {messages.map((message) => (
                  <NarrativeMessage
                    key={message.id}
                    message={message}
                    isUser={message.role === 'user'}
                    onFollowUp={handleFollowUp}
                    onCitationClick={onCitationClick}
                  />
                ))}
              </AnimatePresence>
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>
      </div>

      {/* Input — matches IE pattern */}
      <div className="shrink-0 px-5 py-4 border-t border-border">
        <div className="mx-auto max-w-2xl">
          <div className="flex items-end gap-2 rounded-xl bg-surface border border-border transition-colors focus-within:border-brand/30">
            <textarea
              ref={inputRef}
              value={input}
              onChange={handleInput}
              onKeyDown={handleKeyDown}
              placeholder={isEmpty ? 'Ask about drugs, trials, companies, mechanisms...' : 'Follow-up question...'}
              rows={1}
              className="flex-1 resize-none bg-transparent px-4 py-3 text-[13px] leading-relaxed text-ink placeholder:text-ink-soft/50 outline-none"
              style={{ minHeight: '44px', maxHeight: '96px' }}
              disabled={isLoading}
            />
            <button
              type="button"
              onClick={handleSend}
              disabled={!input.trim() || isLoading}
              className="mb-1 mr-1 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-brand text-white transition-colors hover:bg-brand-dark disabled:opacity-30"
              aria-label="Send"
            >
              {isLoading ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <Send size={14} />
              )}
            </button>
          </div>
          <p className="mt-2 text-center text-[9px] text-ink-soft/40">
            Powered by Claude {'\u00B7'} Responses are AI-generated and grounded in connected data sources
          </p>
        </div>
      </div>
    </div>
  );
}

function EmptyState({ onQuery }: { onQuery: (q: string) => void }) {
  return (
    <div className="flex min-h-[70vh] flex-col items-center justify-center pt-[10vh]">
      {/* Hero */}
      <div className="relative mb-6">
        <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-brand/10 to-brand/5 ring-1 ring-brand/10">
          <Sparkles size={24} className="text-brand" />
        </div>
        <div className="absolute -right-1 -top-1 h-3 w-3 rounded-full bg-emerald-400 ring-2 ring-white" />
      </div>

      <h2 className="text-xl font-semibold tracking-tight text-slate-900 dark:text-white">
        Pharma Intelligence
      </h2>
      <p className="mt-2 max-w-sm text-center text-[13px] leading-relaxed text-slate-500 dark:text-slate-400">
        Ask evidence-grounded questions across drugs, clinical trials, companies, and therapeutic areas.
      </p>

      {/* Category cards */}
      <div className="mt-8 grid w-full max-w-lg grid-cols-1 gap-3 sm:grid-cols-3">
        {STARTER_CATEGORIES.map((cat) => {
          const Icon = cat.icon;
          return (
            <div key={cat.label} className="space-y-2">
              <div className={`flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide ${cat.color}`}>
                <Icon size={12} />
                {cat.label}
              </div>
              {cat.queries.map((query) => (
                <button
                  key={query}
                  type="button"
                  onClick={() => onQuery(query)}
                  className="group block w-full rounded-xl bg-white px-4 py-3 text-left text-[13px] leading-relaxed text-slate-500 shadow-sm transition-all hover:shadow-md hover:text-slate-700 dark:bg-slate-800/60 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-white"
                >
                  <span className="flex items-center justify-between gap-2">
                    {query}
                    <ArrowRight size={11} className="shrink-0 opacity-0 transition-opacity group-hover:opacity-40" />
                  </span>
                </button>
              ))}
            </div>
          );
        })}
      </div>
    </div>
  );
}
