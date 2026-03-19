import { useCallback, useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { motion } from 'framer-motion';
import {
  Archive,
  BarChart3,
  Building2,
  Check,
  ChevronDown,
  Dna,
  FlaskConical,
  Globe,
  Bookmark,
  Loader2,
  Network,
  Pill,
  Search,
  Send,
  ShieldCheck,
  SlidersHorizontal,
  Link2,
  Target,
  Users,
  Zap,
} from 'lucide-react';
import ChatMessage, { type Message } from '../components/ChatMessage';
import ConversationSidebar from '../components/ConversationSidebar';
import GraphExplorer from '../components/GraphExplorer';
import WorkspaceRail from '../components/WorkspaceRail';
import DataCatalogPanel from '../components/DataCatalogPanel';
import {
  api,
  type ChatResponse,
  type EntityListItem,
} from '../api';

interface Props {
  onBack: () => void;
  onSearch?: () => void;
  initialTab?: Tab;
  initialQuestion?: string | null;
}

type Tab = 'chat' | 'graph' | 'catalog';

const STARTER_CATEGORIES = [
  {
    label: 'Compare & Analyze',
    icon: 'BarChart3' as const,
    queries: [
      'Compare semaglutide vs tirzepatide',
      'Tabular breakdown of the GLP-1 landscape',
    ],
  },
  {
    label: 'Explore',
    icon: 'Search' as const,
    queries: [
      'What is semaglutide?',
      'Show me Novo Nordisk\'s portfolio',
    ],
  },
  {
    label: 'Deep Dive',
    icon: 'Target' as const,
    queries: [
      'Phase 3 trial analysis for diabetes drugs',
      'Which mechanisms are most crowded?',
    ],
  },
];

const CATEGORY_ICONS: Record<string, typeof BarChart3> = {
  BarChart3,
  Search,
  Target,
};

const SAVED_CONVERSATIONS_KEY = 'signal-atlas-saved-conversations';
const MAX_SAVED_CONVERSATIONS = 16;
const DEFAULT_SCOPE_KEY = 'default';

interface SavedConversation {
  id: string;
  title: string;
  savedAt: string;
  messages?: Array<{
    id: string;
    role: 'user' | 'assistant';
    content: string;
    timestamp: string;
    data?: Message['data'];
    report?: Message['report'];
    webResults?: Message['webResults'];
    reportMeta?: Message['reportMeta'];
    visualizations?: Message['visualizations'];
    tableData?: Message['tableData'];
    personaAnalyses?: Message['personaAnalyses'];
    confidenceAssessment?: Message['confidenceAssessment'];
  }>;
}

export default function IntelligencePage({ onBack, onSearch, initialTab = 'chat', initialQuestion }: Props) {
  const [activeTab, setActiveTab] = useState<Tab>(initialTab);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [suggestions, setSuggestions] = useState<EntityListItem[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [useGraphSignals, setUseGraphSignals] = useState(true);
  const [useMetricsSignals, setUseMetricsSignals] = useState(false);
  const [strictSourceMode, setStrictSourceMode] = useState(true);
  const [useDeepResearch, setUseDeepResearch] = useState(false);
  const [useWebResearch, setUseWebResearch] = useState(false);
  const [runAsyncResearch, setRunAsyncResearch] = useState(false);
  const [useTeamEval, setUseTeamEval] = useState(false);
  const [showModePanel, setShowModePanel] = useState(false);
  const [savedConversations, setSavedConversations] = useState<SavedConversation[]>([]);
  const [showSavedConversations, setShowSavedConversations] = useState(false);
  const [showConversationSidebar, setShowConversationSidebar] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const suggestTimeoutRef = useRef<number>(0);
  const seededQuestionRef = useRef<string | null>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    if (activeTab === 'chat') inputRef.current?.focus();
  }, [activeTab]);

  useEffect(() => {
    if (activeTab !== 'chat') {
      setShowModePanel(false);
    }
  }, [activeTab]);

  useEffect(() => {
    setActiveTab(initialTab);
  }, [initialTab]);

  const toTranscript = useCallback((list: Message[]) => (
    list.map((message) => ({
      id: message.id,
      role: message.role,
      content: message.content,
      timestamp: message.timestamp.toISOString(),
      data: message.data,
      report: message.report,
      webResults: message.webResults,
      reportMeta: message.reportMeta,
      visualizations: message.visualizations,
      tableData: message.tableData,
      personaAnalyses: message.personaAnalyses,
      confidenceAssessment: message.confidenceAssessment,
    }))
  ), []);

  const fromTranscript = useCallback((transcript?: SavedConversation['messages']): Message[] => {
    if (!transcript) return [];
    return transcript.map((message) => ({
      id: message.id,
      role: message.role,
      content: message.content,
      timestamp: new Date(message.timestamp),
      data: message.data,
      report: message.report,
      webResults: message.webResults,
      reportMeta: message.reportMeta,
      visualizations: message.visualizations,
      tableData: message.tableData,
      personaAnalyses: message.personaAnalyses,
      confidenceAssessment: message.confidenceAssessment,
    }));
  }, []);

  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        const response = await api.listChatSessions(DEFAULT_SCOPE_KEY, MAX_SAVED_CONVERSATIONS, 0);
        if (!active) return;
        const mapped: SavedConversation[] = response.sessions.map((session) => ({
          id: session.id,
          title: session.title,
          savedAt: session.updated_at ?? session.created_at ?? new Date().toISOString(),
        }));
        setSavedConversations(mapped);
        localStorage.setItem(SAVED_CONVERSATIONS_KEY, JSON.stringify(mapped));
        return;
      } catch {
        // fallback to local cache if server persistence is not available
      }

      try {
        const raw = localStorage.getItem(SAVED_CONVERSATIONS_KEY);
        if (!raw || !active) return;
        const parsed = JSON.parse(raw) as SavedConversation[];
        if (!Array.isArray(parsed)) return;
        setSavedConversations(parsed);
      } catch {
        if (active) setSavedConversations([]);
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  const persistSavedConversations = useCallback((next: SavedConversation[]) => {
    setSavedConversations(next);
    localStorage.setItem(SAVED_CONVERSATIONS_KEY, JSON.stringify(next));
  }, []);

  const saveCurrentConversation = useCallback(async () => {
    if (messages.length === 0) return;
    const userSeed = messages.find((m) => m.role === 'user')?.content ?? 'Saved conversation';
    const title = userSeed.length > 72 ? `${userSeed.slice(0, 69)}...` : userSeed;
    const transcript = toTranscript(messages);
    const summary = messages.find((m) => m.role === 'assistant' && m.content.trim())?.content.slice(0, 280) ?? '';

    try {
      const response = await api.saveChatSession(
        {
          title,
          transcript,
          summary,
        },
        DEFAULT_SCOPE_KEY,
      );
      const saved: SavedConversation = {
        id: response.session.id,
        title: response.session.title,
        savedAt: response.session.updated_at ?? response.session.created_at ?? new Date().toISOString(),
      };
      const next = [saved, ...savedConversations.filter((item) => item.id !== saved.id)].slice(0, MAX_SAVED_CONVERSATIONS);
      persistSavedConversations(next);
      setShowSavedConversations(true);
      return;
    } catch {
      // fallback to local persistence
    }

    const conversation: SavedConversation = {
      id: crypto.randomUUID(),
      title,
      savedAt: new Date().toISOString(),
      messages: transcript,
    };
    const next = [conversation, ...savedConversations]
      .slice(0, MAX_SAVED_CONVERSATIONS);
    persistSavedConversations(next);
    setShowSavedConversations(true);
  }, [messages, persistSavedConversations, savedConversations, toTranscript]);

  const restoreConversation = useCallback(async (conversation: SavedConversation) => {
    let transcript = conversation.messages;
    if (!transcript) {
      try {
        const response = await api.getChatSession(conversation.id, DEFAULT_SCOPE_KEY);
        transcript = response.session.transcript as SavedConversation['messages'];
      } catch {
        return;
      }
    }
    const restored: Message[] = fromTranscript(transcript);
    setMessages(restored);
    setActiveTab('chat');
    setShowSavedConversations(false);
  }, [fromTranscript]);

  const deleteConversation = useCallback(async (conversationId: string) => {
    try {
      await api.deleteChatSession(conversationId, DEFAULT_SCOPE_KEY);
    } catch {
      // if server delete fails, keep local cleanup behavior
    }
    const next = savedConversations.filter((conversation) => conversation.id !== conversationId);
    persistSavedConversations(next);
  }, [persistSavedConversations, savedConversations]);

  const handleInputChange = useCallback((value: string) => {
    setInput(value);
    clearTimeout(suggestTimeoutRef.current);

    if (value.length < 2) {
      setSuggestions([]);
      setShowSuggestions(false);
      return;
    }

    suggestTimeoutRef.current = window.setTimeout(async () => {
      try {
        const [drugs, companies] = await Promise.all([
          api.listEntities('drug', value, 5).catch(() => ({ results: [] })),
          api.listEntities('company', value, 3).catch(() => ({ results: [] })),
        ]);
        const merged = [
          ...drugs.results.map((result) => ({ ...result, _type: 'drug' })),
          ...companies.results.map((result) => ({ ...result, _type: 'company' })),
        ];
        setSuggestions(merged);
        setShowSuggestions(merged.length > 0);
      } catch {
        setSuggestions([]);
        setShowSuggestions(false);
      }
    }, 250);
  }, []);

  const buildExecutionQuestion = useCallback((question: string): string => {
    const directives: string[] = [];
    if (useGraphSignals) directives.push('Use connected knowledge-graph relationships where relevant.');
    if (useMetricsSignals) directives.push('Include quantitative metrics when available.');
    if (strictSourceMode) directives.push('Prioritize source-backed statements with explicit evidence.');
    if (useDeepResearch) directives.push('Return a decision-support research brief with clear sections.');
    if (useDeepResearch && useWebResearch) directives.push('Include external web context as supplementary evidence.');
    if (directives.length === 0) return question;
    return `${question}\n\nGuidance: ${directives.join(' ')}`;
  }, [useGraphSignals, useMetricsSignals, strictSourceMode, useDeepResearch, useWebResearch]);

  const waitForResearchJob = useCallback(async (jobId: string): Promise<ChatResponse> => {
    const maxAttempts = 120;
    for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
      const response = await api.getResearchJob(jobId, DEFAULT_SCOPE_KEY);
      const job = response.job;
      if (job.status === 'completed') {
        if (job.result_payload) return job.result_payload;
        throw new Error('Research job completed without payload');
      }
      if (job.status === 'failed') {
        throw new Error(job.error_message || 'Research job failed');
      }
      await new Promise((resolve) => setTimeout(resolve, 1500));
    }
    throw new Error('Research job timed out');
  }, []);

  const sendQuery = useCallback(async (question: string) => {
    const trimmed = question.trim();
    if (!trimmed || isLoading) return;
    const executionQuestion = buildExecutionQuestion(trimmed);

    setShowSuggestions(false);
    setShowModePanel(false);
    setActiveTab('chat');

    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: 'user',
      content: trimmed,
      timestamp: new Date(),
    };
    const assistantMsg: Message = {
      id: crypto.randomUUID(),
      role: 'assistant',
      content: '',
      timestamp: new Date(),
      loading: true,
    };

    setMessages((prev) => [...prev, userMsg, assistantMsg]);
    setInput('');
    setIsLoading(true);

    try {
      const chatModes = {
        include_graph: useGraphSignals,
        include_metrics: useMetricsSignals,
        source_strict: strictSourceMode,
        deep_research: useDeepResearch,
        include_web: useDeepResearch && useWebResearch,
        team_eval: useTeamEval,
      };
      // Build compact conversation history from recent messages for follow-up context
      const currentMessages = [...messages, userMsg]; // include the new user message
      const recentMessages = currentMessages.slice(-6); // last 6 messages (3 exchange pairs)
      const conversationHistory = recentMessages.map((m) => ({
        role: m.role,
        content: m.content.slice(0, 500),
        ...(m._sqlContext ? { sql_context: m._sqlContext } : {}),
        ...(m.data?.entity_focus?.length ? {
          entities: (m.data.entity_focus as Array<Record<string, unknown>>)
            .slice(0, 5)
            .map((e) => String(e.title ?? e.label ?? e.entity_id ?? ''))
            .filter(Boolean),
        } : {}),
        ...(m.data?.metrics_context ? {
          metrics_types: Object.values(m.data.metrics_context as Record<string, Record<string, unknown>>)
            .flatMap((v) => Object.keys(v))
            .filter((v, i, a) => a.indexOf(v) === i)
            .slice(0, 5),
        } : {}),
      }));

      let response: ChatResponse;
      if (useDeepResearch && runAsyncResearch) {
        const jobResponse = await api.createResearchJob(executionQuestion, chatModes, DEFAULT_SCOPE_KEY);
        setMessages((prev) =>
          prev.map((message) =>
            message.id === assistantMsg.id
              ? {
                ...message,
                content: `Deep research job queued (${jobResponse.job.id.slice(0, 8)}). Building report...`,
                loading: true,
              }
              : message
          )
        );
        response = await waitForResearchJob(jobResponse.job.id);
      } else {
        // Try streaming first for real-time token display
        let streamComplete = false;
        try {
          await api.chatStream(executionQuestion, chatModes, conversationHistory, {
            onStatus: (statusMsg) => {
              setMessages((prev) =>
                prev.map((m) => m.id === assistantMsg.id ? { ...m, content: statusMsg, loading: true } : m)
              );
            },
            onToken: (text) => {
              setMessages((prev) =>
                prev.map((m) => {
                  if (m.id !== assistantMsg.id) return m;
                  const current = m.loading ? '' : m.content;
                  return { ...m, content: current + text, loading: false };
                })
              );
            },
            onDone: (payload) => {
              response = payload;
              streamComplete = true;
            },
            onError: () => {
              // Will fall back below
            },
          });
        } catch {
          // Fall back to non-streaming
        }

        if (!streamComplete) {
          response = await api.chat(executionQuestion, chatModes, conversationHistory);
        }
      }
      setMessages((prev) =>
        prev.map((message) =>
          message.id === assistantMsg.id
            ? {
              ...message,
              content: response.narrative,
              data: response.data ?? undefined,
              report: response.report,
              webResults: response.web_results,
              reportMeta: response.report_meta,
              visualizations: response.visualizations,
              tableData: response.table_data,
              personaAnalyses: response.persona_analyses,
              confidenceAssessment: response.confidence_assessment,
              _sqlContext: response.sql_meta?.sql,
              followupSuggestions: response.followup_suggestions,
              loading: false,
            }
            : message
        )
      );
    } catch (err) {
      setMessages((prev) =>
        prev.map((message) =>
          message.id === assistantMsg.id
            ? {
              ...message,
              content: `Sorry, I encountered an error: ${err}. Please try rephrasing your question.`,
              loading: false,
            }
            : message
        )
      );
    } finally {
      setIsLoading(false);
    }
  }, [
    isLoading,
    buildExecutionQuestion,
    useGraphSignals,
    useMetricsSignals,
    strictSourceMode,
    useDeepResearch,
    useWebResearch,
    runAsyncResearch,
    useTeamEval,
    waitForResearchJob,
  ]);

  useEffect(() => {
    if (!initialQuestion) return;
    if (seededQuestionRef.current === initialQuestion) return;
    seededQuestionRef.current = initialQuestion;
    void sendQuery(initialQuestion);
  }, [initialQuestion, sendQuery]);

  useEffect(() => {
    if (!useDeepResearch && useWebResearch) {
      setUseWebResearch(false);
    }
    if (!useDeepResearch && runAsyncResearch) {
      setRunAsyncResearch(false);
    }
  }, [useDeepResearch, useWebResearch, runAsyncResearch]);

  // Global keyboard shortcuts
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;
      // Ctrl/Cmd+K → focus chat input
      if (mod && e.key === 'k') {
        e.preventDefault();
        inputRef.current?.focus();
      }
      // Escape → clear suggestions, panels, sidebar
      if (e.key === 'Escape') {
        setShowSuggestions(false);
        setShowModePanel(false);
        setShowConversationSidebar(false);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  const handleEntityClick = useCallback((entityId: string, _entityType: string, label?: string) => {
    const queryTarget = label || entityId;
    void sendQuery(`Tell me about ${queryTarget}`);
  }, [sendQuery]);

  const handleFollowUp = useCallback((question: string) => {
    setInput(question);
    void sendQuery(question);
  }, [sendQuery]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key !== 'Enter' || e.shiftKey) return;
    e.preventDefault();
    void sendQuery(input);
  };

  const entityIcons: Record<string, ReactNode> = {
    drug: <Pill size={14} className="text-blue-600" />,
    company: <Building2 size={14} className="text-amber-600" />,
    trial: <FlaskConical size={14} className="text-teal-600" />,
    mechanism: <Dna size={14} className="text-violet-600" />,
    therapeutic_area: <Target size={14} className="text-rose-600" />,
  };

  const activeModeLabels = [
    useGraphSignals ? 'Graph' : null,
    useMetricsSignals ? 'Metrics' : null,
    strictSourceMode ? 'Source strict' : null,
    useDeepResearch ? 'Deep research' : null,
    useTeamEval ? 'Team eval' : null,
    useWebResearch ? 'Web' : null,
    runAsyncResearch ? 'Async' : null,
  ].filter(Boolean) as string[];

  const activeModeSummary = activeModeLabels.length > 0
    ? `Active: ${activeModeLabels.join(' | ')}`
    : 'No modes selected';

  const modeButtonClass = (active: boolean) => `flex w-full items-center justify-between rounded-md border px-3 py-2 text-[11px] transition-colors ${
    active
      ? 'border-brand/30 bg-blue-50 text-blue-700'
      : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300 hover:bg-slate-50'
  }`;

  const renderModePanel = (placement: 'down' | 'up' = 'down') => (
    <div className={`absolute left-0 z-40 w-[min(92vw,22rem)] max-h-[min(62vh,24rem)] overflow-y-auto rounded-md border border-slate-200 bg-white p-2 shadow-lg ${
      placement === 'up' ? 'bottom-full mb-2' : 'top-full mt-2'
    }`}>
      <div className="mb-1.5 px-1.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">
        Analysis Tools
      </div>
      <div className="space-y-1">
        <button type="button" onClick={() => setUseGraphSignals((prev) => !prev)} className={modeButtonClass(useGraphSignals)}>
          <span className="inline-flex items-center gap-1.5"><Network size={12} />Graph reasoning</span>
          {useGraphSignals && <Check size={12} />}
        </button>
        <button type="button" onClick={() => setUseMetricsSignals((prev) => !prev)} className={modeButtonClass(useMetricsSignals)}>
          <span className="inline-flex items-center gap-1.5"><BarChart3 size={12} />Quant metrics</span>
          {useMetricsSignals && <Check size={12} />}
        </button>
        <button type="button" onClick={() => setStrictSourceMode((prev) => !prev)} className={modeButtonClass(strictSourceMode)}>
          <span className="inline-flex items-center gap-1.5"><Link2 size={12} />Source strict</span>
          {strictSourceMode && <Check size={12} />}
        </button>
        <button type="button" onClick={() => setUseDeepResearch((prev) => !prev)} className={modeButtonClass(useDeepResearch)}>
          <span className="inline-flex items-center gap-1.5"><Bookmark size={12} />Deep research</span>
          {useDeepResearch && <Check size={12} />}
        </button>
        <button type="button" onClick={() => setUseTeamEval((prev) => !prev)} className={modeButtonClass(useTeamEval)}>
          <span className="inline-flex items-center gap-1.5"><Users size={12} />Team eval</span>
          {useTeamEval && <Check size={12} />}
        </button>
        <button
          type="button"
          onClick={() => {
            if (!useDeepResearch) return;
            setUseWebResearch((prev) => !prev);
          }}
          disabled={!useDeepResearch}
          className={`${modeButtonClass(useWebResearch)} disabled:cursor-not-allowed disabled:opacity-45`}
        >
          <span className="inline-flex items-center gap-1.5"><Globe size={12} />Web search</span>
          {useWebResearch && <Check size={12} />}
        </button>
        <button
          type="button"
          onClick={() => {
            if (!useDeepResearch) return;
            setRunAsyncResearch((prev) => !prev);
          }}
          disabled={!useDeepResearch}
          className={`${modeButtonClass(runAsyncResearch)} disabled:cursor-not-allowed disabled:opacity-45`}
        >
          <span className="inline-flex items-center gap-1.5"><Loader2 size={12} />Async job</span>
          {runAsyncResearch && <Check size={12} />}
        </button>
      </div>
      <div className="mt-2 px-1.5 text-[10px] text-slate-400">
        Web and Async are enabled only when Deep research is on.
      </div>
    </div>
  );

  const renderSuggestions = () => (
    showSuggestions && suggestions.length > 0 ? (
      <div className="absolute bottom-full left-0 right-0 z-50 mb-2 overflow-hidden rounded-lg border border-slate-200 bg-white/96 shadow-lg">
        {suggestions.map((item: EntityListItem & { _type?: string }) => (
          <button
            key={item.entity_id}
            onClick={() => {
              setInput(item.label);
              setShowSuggestions(false);
              inputRef.current?.focus();
            }}
            className="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-slate-50"
          >
            <span className="flex-shrink-0 text-slate-400">
              {entityIcons[item._type ?? 'drug']}
            </span>
            <span className="flex-1 truncate text-sm font-medium text-slate-900">{item.label}</span>
            <span className="text-xs capitalize text-slate-400">{(item._type ?? 'drug').replace('_', ' ')}</span>
          </button>
        ))}
      </div>
    ) : null
  );

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.3 }}
      className="workspace-canvas flex h-screen overflow-hidden"
    >
      <WorkspaceRail
        active={activeTab}
        onBack={onBack}
        onSelect={(view) => {
          if (view === 'chat') {
            if (activeTab === 'chat') {
              setShowConversationSidebar((prev) => !prev);
            } else {
              setActiveTab('chat');
            }
            return;
          }
          if (view === 'graph') {
            setActiveTab('graph');
            return;
          }
          if (view === 'catalog') {
            setActiveTab('catalog');
            return;
          }
          onSearch?.();
        }}
      />

      <div className="relative flex min-w-0 flex-1 flex-col">
        <ConversationSidebar
          isOpen={showConversationSidebar}
          onClose={() => setShowConversationSidebar(false)}
          conversations={savedConversations}
          onSelect={(conv) => {
            void restoreConversation(conv);
            setShowConversationSidebar(false);
          }}
          onDelete={(id) => void deleteConversation(id)}
        />

        <header className="shrink-0 border-b border-slate-200/70 bg-white/82 backdrop-blur-md">
          <div className="workspace-shell flex h-10 items-center justify-between px-6">
            <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">
              {activeTab === 'chat'
                ? 'Evidence Workspace'
                : activeTab === 'graph'
                  ? 'Graph Workspace'
                  : 'Data Catalog'}
            </div>
            <div className="flex items-center gap-2">
              {activeTab === 'chat' && (
                <>
                  <button
                    type="button"
                    onClick={() => void saveCurrentConversation()}
                    disabled={messages.length === 0}
                    className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-3 py-1.5 text-[11px] text-slate-600 transition-colors hover:border-slate-300 hover:bg-slate-50 disabled:opacity-40"
                  >
                    <Bookmark size={11} />
                    Save session
                  </button>
                  <button
                    type="button"
                    onClick={() => setShowSavedConversations((prev) => !prev)}
                    className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-3 py-1.5 text-[11px] text-slate-600 transition-colors hover:border-slate-300 hover:bg-slate-50"
                  >
                    <Archive size={11} />
                    Saved {savedConversations.length}
                  </button>
                </>
              )}
              <div className="chip-plain inline-flex items-center gap-1.5 text-[11px] text-slate-600">
                <ShieldCheck size={11} />
                source-backed output
              </div>
            </div>
          </div>
        </header>

        {activeTab === 'graph' ? (
          <div className="min-h-0 flex-1">
            <GraphExplorer />
          </div>
        ) : activeTab === 'catalog' ? (
          <DataCatalogPanel onAskInChat={(q) => {
            setActiveTab('chat');
            setTimeout(() => {
              if (inputRef.current) {
                inputRef.current.value = q;
                inputRef.current.focus();
              }
            }, 100);
          }} />
        ) : (
          <>
            <main className="workspace-canvas flex-1 overflow-y-auto px-6 py-8 sm:px-8">
              <div className="workspace-shell">
                {showSavedConversations && (
                  <div className="mx-auto mb-4 w-full max-w-[90%] rounded-lg border border-slate-200 bg-white/84 p-3.5">
                    <div className="mb-2 flex items-center justify-between">
                      <div className="text-xs font-medium text-slate-600">Saved Conversations</div>
                      <button
                        type="button"
                        onClick={() => setShowSavedConversations(false)}
                        className="text-[11px] text-slate-400 hover:text-slate-600"
                      >
                        Close
                      </button>
                    </div>
                    {savedConversations.length === 0 ? (
                      <div className="rounded-md border border-slate-200 bg-white px-3 py-3 text-xs text-slate-500">
                        No saved sessions yet.
                      </div>
                    ) : (
                      <div className="max-h-56 space-y-2 overflow-y-auto">
                        {savedConversations.map((conversation) => (
                          <div key={conversation.id} className="flex items-center gap-2 rounded-md border border-slate-200 bg-white px-3 py-2">
                            <button
                              type="button"
                              onClick={() => void restoreConversation(conversation)}
                              className="flex-1 truncate text-left text-xs font-medium text-slate-700 hover:text-slate-900"
                            >
                              {conversation.title}
                            </button>
                            <span className="text-[10px] text-slate-400">
                              {new Date(conversation.savedAt).toLocaleDateString()}
                            </span>
                            <button
                              type="button"
                              onClick={() => void deleteConversation(conversation.id)}
                              className="text-[10px] text-slate-400 hover:text-rose-500"
                            >
                              Remove
                            </button>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
                {messages.length === 0 ? (
                  <div className="mx-auto flex min-h-[76vh] w-full max-w-[90%] flex-col items-center justify-center">
                    <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-lg border border-slate-200 bg-white/88">
                      <Zap size={24} className="text-brand" />
                    </div>
                    <div className="text-center">
                      <h2 className="text-[clamp(2.05rem,4.1vw,3.1rem)] font-semibold tracking-tight text-slate-900">
                        Evidence workspace for pharmaceutical intelligence
                      </h2>
                      <p className="mx-auto mt-3 max-w-3xl text-[16px] leading-relaxed text-slate-600">
                        Ask focused questions across drugs, trials, literature, companies, and therapeutic areas with
                        source-grounded context and ontology links.
                      </p>
                    </div>

                    <div className="relative mx-auto mt-7 w-full max-w-[90%]">
                      {renderSuggestions()}

                      <div className="surface-panel rounded-lg px-5 py-5 sm:px-6 sm:py-6">
                        <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">
                          Ask a question
                        </div>
                        <div className="min-h-[62px] px-0 py-2">
                          <input
                            ref={inputRef}
                            value={input}
                            onChange={(e) => handleInputChange(e.target.value)}
                            onKeyDown={handleKeyDown}
                            onBlur={() => setTimeout(() => setShowSuggestions(false), 200)}
                            placeholder="Ask a focused evidence question..."
                            className="block w-full bg-transparent text-[clamp(1.18rem,1.48vw,1.45rem)] font-medium leading-[1.22] tracking-tight text-slate-900 placeholder:text-slate-400 outline-none"
                            disabled={isLoading}
                          />
                        </div>
                        <div className="mt-3 flex flex-wrap items-center justify-between gap-3 border-t border-slate-200/80 pt-3.5">
                          <div className="relative">
                            <button
                              type="button"
                              onClick={() => setShowModePanel((prev) => !prev)}
                              className="inline-flex items-center gap-2 rounded-md border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-600 transition-colors hover:border-slate-300 hover:bg-slate-50"
                            >
                              <SlidersHorizontal size={13} />
                              Modes
                              <span className="rounded-sm bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-500">{activeModeLabels.length}</span>
                              <ChevronDown size={12} className={`${showModePanel ? 'rotate-180' : ''} transition-transform`} />
                            </button>
                            {showModePanel && renderModePanel('down')}
                          </div>
                          <div className="min-w-0 flex-1 truncate text-[11px] text-slate-500">
                            {activeModeSummary}
                          </div>
                          <div className="flex items-center gap-2">
                            {onSearch && (
                              <button
                                type="button"
                                onClick={onSearch}
                                className="btn-secondary inline-flex items-center gap-1.5 whitespace-nowrap rounded-md border border-slate-200 px-3 py-2 text-xs font-medium text-slate-700"
                              >
                                <Search size={12} />
                                Search
                              </button>
                            )}
                            <button
                              onClick={() => void sendQuery(input)}
                              disabled={!input.trim() || isLoading}
                              className="btn-search-gradient inline-flex h-10 shrink-0 items-center justify-center gap-1.5 whitespace-nowrap rounded-md px-4 text-xs font-semibold text-white transition-colors disabled:opacity-30"
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

                    <div className="mx-auto mt-6 grid w-full max-w-[90%] grid-cols-1 gap-4 sm:grid-cols-3">
                      {STARTER_CATEGORIES.map((cat) => {
                        const Icon = CATEGORY_ICONS[cat.icon];
                        return (
                          <div key={cat.label}>
                            <div className="mb-2 flex items-center gap-1.5 text-[11px] font-semibold text-slate-500">
                              {Icon && <Icon size={12} />}
                              {cat.label}
                            </div>
                            <div className="space-y-1.5">
                              {cat.queries.map((query) => (
                                <button
                                  key={query}
                                  type="button"
                                  onClick={() => {
                                    setInput(query);
                                    void sendQuery(query);
                                  }}
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
                    <div className="mt-4 flex items-center gap-1.5 text-[10px] text-slate-400">
                      <ShieldCheck size={10} />
                      Responses are evidence-grounded from linked records. Validate critical decisions against primary sources.
                    </div>
                  </div>
                ) : (
                  <div className="mx-auto w-full max-w-[90%] space-y-6">
                    {messages.map((message) => (
                      <ChatMessage key={message.id} message={message} onEntityClick={handleEntityClick} onFollowUp={handleFollowUp} />
                    ))}
                  </div>
                )}
                <div ref={messagesEndRef} />
              </div>
            </main>

            {messages.length > 0 && (
              <div className="shrink-0 border-t border-slate-200/70 bg-white/76 px-6 py-4 backdrop-blur-md">
                <div className="relative mx-auto w-full max-w-[90%]">
                  {renderSuggestions()}

                  <div className="surface-panel rounded-lg px-4 py-4 transition-all focus-within:ring-2 focus-within:ring-brand/15">
                    <div className="mb-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">
                      Follow-up question
                    </div>
                    <div className="flex items-center gap-3">
                      <input
                        ref={inputRef}
                        value={input}
                        onChange={(e) => handleInputChange(e.target.value)}
                        onKeyDown={handleKeyDown}
                        onBlur={() => setTimeout(() => setShowSuggestions(false), 200)}
                        placeholder="Ask a focused evidence question..."
                        className="flex-1 bg-transparent text-[14px] text-slate-900 placeholder:text-slate-400 outline-none"
                        disabled={isLoading}
                      />
                      {onSearch && (
                        <button
                          type="button"
                          onClick={onSearch}
                          className="btn-secondary inline-flex h-10 shrink-0 items-center justify-center gap-1.5 rounded-md border border-slate-200 px-3 text-xs font-medium text-slate-700"
                        >
                          <Search size={12} />
                          Search
                        </button>
                      )}
                      <button
                        onClick={() => void sendQuery(input)}
                        disabled={!input.trim() || isLoading}
                        className="btn-search-gradient inline-flex h-10 shrink-0 items-center justify-center gap-1.5 rounded-md px-4 text-xs font-semibold text-white transition-colors disabled:opacity-30"
                      >
                        {isLoading ? <Loader2 size={14} className="animate-spin" /> : <><span>Ask</span><Send size={13} /></>}
                      </button>
                    </div>
                    <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-slate-200/80 pt-3">
                      <div className="relative">
                        <button
                          type="button"
                          onClick={() => setShowModePanel((prev) => !prev)}
                          className="inline-flex items-center gap-2 rounded-md border border-slate-200 bg-white px-3 py-1.5 text-[11px] font-medium text-slate-600 transition-colors hover:border-slate-300 hover:bg-slate-50"
                        >
                          <SlidersHorizontal size={12} />
                          Modes
                          <span className="rounded-sm bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-500">{activeModeLabels.length}</span>
                          <ChevronDown size={11} className={`${showModePanel ? 'rotate-180' : ''} transition-transform`} />
                        </button>
                        {showModePanel && renderModePanel('up')}
                      </div>
                      <div className="min-w-0 flex-1 truncate text-[11px] text-slate-500">
                        {activeModeSummary}
                      </div>
                    </div>
                  </div>
                  <div className="mt-2 flex items-center justify-center gap-1.5 text-[10px] text-slate-500">
                    <ShieldCheck size={10} />
                    {useTeamEval
                      ? 'Team eval mode enabled for multi-persona analysis.'
                      : useDeepResearch
                        ? 'Deep research mode enabled with optional web augmentation.'
                        : 'Source-grounded output from linked knowledge graph records.'}
                  </div>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </motion.div>
  );
}

