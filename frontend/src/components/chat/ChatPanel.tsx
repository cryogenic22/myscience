import { useCallback, useEffect, useRef, useState } from 'react';
import { Loader2, Send, Zap, BarChart3, Search, Target } from 'lucide-react';
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

/** Starter categories -- reused from IntelligencePage pattern */
const STARTER_CATEGORIES = [
  {
    label: 'Compare & Analyze',
    icon: BarChart3,
    queries: [
      'Compare semaglutide vs tirzepatide',
      'Tabular breakdown of the GLP-1 landscape',
    ],
  },
  {
    label: 'Explore',
    icon: Search,
    queries: [
      'What is semaglutide?',
      "Show me Novo Nordisk's portfolio",
    ],
  },
  {
    label: 'Deep Dive',
    icon: Target,
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
  const inputRef = useRef<HTMLInputElement>(null);

  // Auto-scroll when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Focus input on mount
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const handleSend = useCallback(() => {
    const trimmed = input.trim();
    if (!trimmed || isLoading) return;
    onSend(trimmed);
    setInput('');
  }, [input, isLoading, onSend]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key !== 'Enter' || e.shiftKey) return;
    e.preventDefault();
    handleSend();
  };

  const handleFollowUp = useCallback(
    (q: string) => {
      if (onFollowUp) {
        onFollowUp(q);
      } else {
        onSend(q);
      }
    },
    [onFollowUp, onSend],
  );

  const handleStarterClick = useCallback(
    (query: string) => {
      setInput('');
      onSend(query);
    },
    [onSend],
  );

  const isEmpty = messages.length === 0;

  return (
    <div className="flex h-full flex-col">
      {/* Messages area */}
      <div className="flex-1 overflow-y-auto px-4 py-6 sm:px-6">
        {isEmpty ? (
          <EmptyState onQuery={handleStarterClick} />
        ) : (
          <div className="space-y-5">
            {messages.map((message) => (
              <NarrativeMessage
                key={message.id}
                message={message}
                isUser={message.role === 'user'}
                onFollowUp={handleFollowUp}
                onCitationClick={onCitationClick}
              />
            ))}
            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {/* Input bar */}
      <div className="shrink-0 border-t border-slate-200/70 bg-white/76 px-4 py-3 backdrop-blur-md">
        <div className="surface-panel rounded-lg px-4 py-3 transition-all focus-within:ring-2 focus-within:ring-brand/15">
          <div className="flex items-center gap-3">
            <input
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={isEmpty ? 'Ask a focused evidence question...' : 'Follow-up question...'}
              className="flex-1 bg-transparent text-[14px] text-slate-900 placeholder:text-slate-400 outline-none"
              disabled={isLoading}
            />
            <button
              type="button"
              onClick={handleSend}
              disabled={!input.trim() || isLoading}
              className="btn-search-gradient inline-flex h-9 shrink-0 items-center justify-center gap-1.5 rounded-md px-3.5 text-xs font-semibold text-white transition-colors disabled:opacity-30"
              aria-label="Send query"
            >
              {isLoading ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <>
                  Ask
                  <Send size={13} />
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

/** Empty state with starter categories */
function EmptyState({ onQuery }: { onQuery: (q: string) => void }) {
  return (
    <div className="flex min-h-full flex-col items-center justify-center px-4">
      <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-lg border border-slate-200 bg-white/88">
        <Zap size={20} className="text-brand" />
      </div>
      <h2 className="text-lg font-semibold tracking-tight text-slate-900">
        Evidence workspace
      </h2>
      <p className="mx-auto mt-1.5 max-w-md text-center text-[13px] leading-relaxed text-slate-500">
        Ask focused questions across drugs, trials, literature, companies, and therapeutic areas.
      </p>

      <div className="mt-6 grid w-full max-w-lg grid-cols-1 gap-4 sm:grid-cols-3">
        {STARTER_CATEGORIES.map((cat) => {
          const Icon = cat.icon;
          return (
            <div key={cat.label}>
              <div className="mb-2 flex items-center gap-1.5 text-[11px] font-semibold text-slate-500">
                <Icon size={12} />
                {cat.label}
              </div>
              <div className="space-y-1.5">
                {cat.queries.map((query) => (
                  <button
                    key={query}
                    type="button"
                    onClick={() => onQuery(query)}
                    className="block w-full rounded-lg border border-slate-200/80 bg-white/80 px-3 py-2 text-left text-[12px] text-slate-600 shadow-sm transition-all hover:border-brand/30 hover:bg-white hover:text-slate-900 hover:shadow-md"
                  >
                    {query}
                  </button>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
