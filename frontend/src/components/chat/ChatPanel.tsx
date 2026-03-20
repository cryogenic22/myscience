import { useCallback, useEffect, useRef, useState } from 'react';
import { Loader2, Send, Sparkles, BarChart3, Search, Target, ArrowRight } from 'lucide-react';
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

      {/* Input */}
      <div className="shrink-0 bg-white/80 backdrop-blur-lg px-6 py-5 dark:bg-slate-900/80">
        <div className="mx-auto max-w-2xl px-1">
          <div className="flex items-end gap-2 rounded-2xl bg-slate-50 px-4 py-3 transition-all focus-within:bg-white focus-within:shadow-lg focus-within:ring-1 focus-within:ring-slate-200/60 dark:bg-slate-800 dark:focus-within:bg-slate-800 dark:focus-within:ring-slate-700">
            <textarea
              ref={inputRef}
              value={input}
              onChange={handleInput}
              onKeyDown={handleKeyDown}
              placeholder={isEmpty ? 'Ask about drugs, trials, companies, mechanisms...' : 'Follow-up question...'}
              rows={1}
              className="flex-1 resize-none bg-transparent text-[14px] leading-relaxed text-slate-800 placeholder:text-slate-400 outline-none dark:text-slate-100"
              style={{ maxHeight: '120px' }}
              disabled={isLoading}
            />
            <button
              type="button"
              onClick={handleSend}
              disabled={!input.trim() || isLoading}
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand text-white transition-all hover:bg-brand-dark disabled:opacity-20 disabled:hover:bg-brand"
              aria-label="Send"
            >
              {isLoading ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <ArrowRight size={15} />
              )}
            </button>
          </div>
          <p className="mt-2 text-center text-[10px] tracking-wide text-slate-400/70 dark:text-slate-500">
            Grounded in ClinicalTrials.gov {'\u00B7'} PubMed {'\u00B7'} FDA Orange Book {'\u00B7'} SEC Edgar
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
