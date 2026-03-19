import { useCallback, useEffect, useRef, useState } from 'react';
import { motion } from 'framer-motion';
import type { Message } from '../components/ChatMessage';
import type { ChatResponse, QueryResponse, TableData, VisualizationSpec, PersonaAnalysis } from '../api';
import { api } from '../api';
import TopBar from '../components/layout/TopBar';
import WorkspaceLayout from '../components/layout/WorkspaceLayout';
import ChatPanel from '../components/chat/ChatPanel';
import CanvasPanel from '../components/canvas/CanvasPanel';
import GraphExplorer from '../components/GraphExplorer';
import DataCatalogPanel from '../components/DataCatalogPanel';

type Tab = 'chat' | 'graph' | 'catalog';

interface WorkspacePageProps {
  onBack: () => void;
  onSearch?: () => void;
  initialQuestion?: string | null;
  initialTab?: Tab;
}

/** Latest structured data from the most recent assistant response, displayed in the canvas panel. */
interface CanvasState {
  intent: string | null;
  data: QueryResponse | null;
  tableData: TableData | null;
  visualizations: VisualizationSpec[] | null;
  confidence: number | undefined;
  guardStatus: string | undefined;
  personaAnalyses: PersonaAnalysis[] | undefined;
  confidenceAssessment: { overall: number; by_dimension: Record<string, number> } | undefined;
}

const EMPTY_CANVAS: CanvasState = {
  intent: null,
  data: null,
  tableData: null,
  visualizations: null,
  confidence: undefined,
  guardStatus: undefined,
  personaAnalyses: undefined,
  confidenceAssessment: undefined,
};

export default function WorkspacePage({
  onBack,
  onSearch,
  initialQuestion,
  initialTab = 'chat',
}: WorkspacePageProps) {
  const [activeTab, setActiveTab] = useState<Tab>(initialTab);
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [canvasLoading, setCanvasLoading] = useState(false);
  const [canvas, setCanvas] = useState<CanvasState>(EMPTY_CANVAS);
  const seededQuestionRef = useRef<string | null>(null);

  // Sync tab from parent
  useEffect(() => {
    setActiveTab(initialTab);
  }, [initialTab]);

  // Fire initial question once
  useEffect(() => {
    if (!initialQuestion) return;
    if (seededQuestionRef.current === initialQuestion) return;
    seededQuestionRef.current = initialQuestion;
    void sendQuery(initialQuestion);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialQuestion]);

  // Keyboard shortcut: Cmd+K focus
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        // ChatPanel manages its own inputRef -- switch to chat tab
        setActiveTab('chat');
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  /** Build conversation history for context window. */
  const buildHistory = useCallback(
    (withUserMsg: Message) => {
      const all = [...messages, withUserMsg];
      return all.slice(-6).map((m) => ({
        role: m.role,
        content: m.content.slice(0, 500),
        ...(m._sqlContext ? { sql_context: m._sqlContext } : {}),
        ...(m.data?.entity_focus?.length
          ? {
              entities: (m.data.entity_focus as Array<Record<string, unknown>>)
                .slice(0, 5)
                .map((e) => String(e.title ?? e.label ?? e.entity_id ?? ''))
                .filter(Boolean),
            }
          : {}),
        ...(m.data?.metrics_context
          ? {
              metrics_types: Object.values(m.data.metrics_context as Record<string, Record<string, unknown>>)
                .flatMap((v) => Object.keys(v))
                .filter((v, i, a) => a.indexOf(v) === i)
                .slice(0, 5),
            }
          : {}),
      }));
    },
    [messages],
  );

  /** Core send logic: stream-first with non-streaming fallback. */
  const sendQuery = useCallback(
    async (question: string) => {
      const trimmed = question.trim();
      if (!trimmed || isLoading) return;

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
      setIsLoading(true);
      setCanvasLoading(true);

      try {
        const chatModes = {
          include_graph: true,
          include_metrics: true,
          source_strict: true,
        };
        const conversationHistory = buildHistory(userMsg);
        let response: ChatResponse | undefined;
        let streamComplete = false;

        try {
          await api.chatStream(trimmed, chatModes, conversationHistory, {
            onStatus: (statusMsg) => {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantMsg.id ? { ...m, content: statusMsg, loading: true } : m,
                ),
              );
            },
            onToken: (text) => {
              setMessages((prev) =>
                prev.map((m) => {
                  if (m.id !== assistantMsg.id) return m;
                  const current = m.loading ? '' : m.content;
                  return { ...m, content: current + text, loading: false };
                }),
              );
            },
            onDone: (payload) => {
              response = payload;
              streamComplete = true;
            },
            onError: () => {
              // fall through to non-streaming
            },
          });
        } catch {
          // fall through to non-streaming
        }

        if (!streamComplete) {
          response = await api.chat(trimmed, chatModes, conversationHistory);
        }

        if (response) {
          // Update assistant message with final narrative
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsg.id
                ? {
                    ...m,
                    content: response!.narrative,
                    data: response!.data ?? undefined,
                    report: response!.report,
                    webResults: response!.web_results,
                    reportMeta: response!.report_meta,
                    visualizations: response!.visualizations,
                    tableData: response!.table_data,
                    personaAnalyses: response!.persona_analyses,
                    confidenceAssessment: response!.confidence_assessment,
                    _sqlContext: response!.sql_meta?.sql,
                    followupSuggestions: response!.followup_suggestions,
                    loading: false,
                  }
                : m,
            ),
          );

          // Update canvas with structured data
          setCanvas({
            intent: response.intent ?? null,
            data: response.data ?? null,
            tableData: response.table_data ?? null,
            visualizations: response.visualizations ?? null,
            confidence: response.confidence_assessment?.overall,
            guardStatus: undefined,
            personaAnalyses: response.persona_analyses,
            confidenceAssessment: response.confidence_assessment,
          });
        }
      } catch (err) {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMsg.id
              ? {
                  ...m,
                  content: `Sorry, I encountered an error: ${err}. Please try rephrasing your question.`,
                  loading: false,
                }
              : m,
          ),
        );
      } finally {
        setIsLoading(false);
        setCanvasLoading(false);
      }
    },
    [isLoading, buildHistory],
  );

  const handleFollowUp = useCallback(
    (question: string) => {
      void sendQuery(question);
    },
    [sendQuery],
  );

  const handleTabChange = useCallback((tab: Tab) => {
    setActiveTab(tab);
  }, []);

  /** Compute breadcrumb from the latest entity focus */
  const breadcrumb = (() => {
    if (!canvas.data?.entity_focus?.length) return undefined;
    const names = (canvas.data.entity_focus as Array<Record<string, unknown>>)
      .slice(0, 3)
      .map((e) => String(e.title ?? e.label ?? ''))
      .filter(Boolean);
    if (names.length === 0) return undefined;
    return names.join(' > ');
  })();

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.3 }}
      className="workspace-canvas flex h-screen flex-col overflow-hidden"
    >
      <TopBar
        onBack={onBack}
        onSearch={onSearch}
        activeTab={activeTab}
        onTabChange={handleTabChange}
        breadcrumb={breadcrumb}
      />

      {activeTab === 'graph' ? (
        <div className="min-h-0 flex-1">
          <GraphExplorer />
        </div>
      ) : activeTab === 'catalog' ? (
        <div className="min-h-0 flex-1">
          <DataCatalogPanel
            onAskInChat={(q) => {
              setActiveTab('chat');
              setTimeout(() => void sendQuery(q), 100);
            }}
          />
        </div>
      ) : (
        <WorkspaceLayout
          left={
            <ChatPanel
              messages={messages}
              onSend={sendQuery}
              isLoading={isLoading}
              onFollowUp={handleFollowUp}
            />
          }
          right={
            <CanvasPanel
              intent={canvas.intent}
              data={canvas.data}
              tableData={canvas.tableData}
              visualizations={canvas.visualizations}
              confidence={canvas.confidence}
              guardStatus={canvas.guardStatus}
              loading={canvasLoading}
              personaAnalyses={canvas.personaAnalyses}
              confidenceAssessment={canvas.confidenceAssessment}
            />
          }
          defaultSplit={50}
          minLeft={30}
          minRight={25}
        />
      )}
    </motion.div>
  );
}
