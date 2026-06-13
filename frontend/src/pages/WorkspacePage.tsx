import { useCallback, useEffect, useRef, useState } from 'react';
import { motion } from 'framer-motion';
import type { Message } from '../components/ChatMessage';
import type { ChatResponse, QueryResponse, TableData, VisualizationSpec, PersonaAnalysis, GraphNode, GraphEdge } from '../api';
import { api } from '../api';
import TopBar from '../components/layout/TopBar';
import WorkspaceLayout from '../components/layout/WorkspaceLayout';
import ChatPanel from '../components/chat/ChatPanel';
import CanvasPanel from '../components/canvas/CanvasPanel';
import GraphExplorer from '../components/GraphExplorer';
import DataCatalogPanel from '../components/DataCatalogPanel';
import { LiteratureExplorer } from '../components/LiteratureExplorer';
import { IntelligenceFeed } from '../components/intelligence/IntelligenceFeed';
import { ErrorBoundary } from '../components/ui/ErrorBoundary';

type Tab = 'chat' | 'graph' | 'catalog' | 'feed';

interface WorkspacePageProps {
  onBack: () => void;
  onSearch?: () => void;
  onCI?: () => void;
  onDataHub?: () => void;
  initialQuestion?: string | null;
  initialTab?: Tab;
}

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
  intent: null, data: null, tableData: null, visualizations: null,
  confidence: undefined, guardStatus: undefined,
  personaAnalyses: undefined, confidenceAssessment: undefined,
};

export default function WorkspacePage({
  onBack,
  onSearch,
  onCI,
  onDataHub,
  initialQuestion,
  initialTab = 'chat',
}: WorkspacePageProps) {
  const [activeTab, setActiveTab] = useState<Tab>(initialTab);
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [canvasLoading, setCanvasLoading] = useState(false);
  const [canvas, setCanvas] = useState<CanvasState>(EMPTY_CANVAS);
  const [graphEntity, setGraphEntity] = useState<{ id: string; type: string; label: string } | null>(null);
  const [seedGraph, setSeedGraph] = useState<{ nodes: GraphNode[]; edges: GraphEdge[] } | null>(null);
  const [litExplorerArticleId, setLitExplorerArticleId] = useState<string | null>(null);
  const [chatExternalInput, setChatExternalInput] = useState<{ text: string; seq: number } | null>(null);
  const chatExternalSeqRef = useRef(0);
  const seededQuestionRef = useRef<string | null>(null);

  useEffect(() => { setActiveTab(initialTab); }, [initialTab]);

  useEffect(() => {
    if (!initialQuestion) return;
    if (seededQuestionRef.current === initialQuestion) return;
    seededQuestionRef.current = initialQuestion;
    void sendQuery(initialQuestion);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialQuestion]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setActiveTab('chat');
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  const buildHistory = useCallback(
    (withUserMsg: Message) => {
      const all = [...messages, withUserMsg];
      return all.slice(-6).map(m => ({
        role: m.role,
        content: m.content.slice(0, 500),
        ...(m._sqlContext ? { sql_context: m._sqlContext } : {}),
        ...(m.data?.entity_focus?.length
          ? { entities: (m.data.entity_focus as Array<Record<string, unknown>>)
              .slice(0, 5).map(e => String(e.title ?? e.label ?? '')).filter(Boolean) }
          : {}),
      }));
    },
    [messages],
  );

  const sendQuery = useCallback(
    async (question: string) => {
      const trimmed = question.trim();
      if (!trimmed || isLoading) return;
      setActiveTab('chat');

      const userMsg: Message = {
        id: crypto.randomUUID(), role: 'user', content: trimmed, timestamp: new Date(),
      };
      const assistantMsg: Message = {
        id: crypto.randomUUID(), role: 'assistant', content: '', timestamp: new Date(), loading: true,
      };

      setMessages(prev => [...prev, userMsg, assistantMsg]);
      setIsLoading(true);
      setCanvasLoading(true);

      try {
        const chatModes = { include_graph: true, include_metrics: true, source_strict: true };
        const conversationHistory = buildHistory(userMsg);
        let response: ChatResponse | undefined;
        let streamComplete = false;

        try {
          await api.chatStream(trimmed, chatModes, conversationHistory, {
            onStatus: statusMsg => {
              setMessages(prev => prev.map(m =>
                m.id === assistantMsg.id ? { ...m, content: statusMsg, loading: true } : m
              ));
            },
            onToken: text => {
              setMessages(prev => prev.map(m => {
                if (m.id !== assistantMsg.id) return m;
                const current = m.loading ? '' : m.content;
                return { ...m, content: current + text, loading: false };
              }));
            },
            onDone: payload => { response = payload; streamComplete = true; },
            onError: () => {},
          });
        } catch { /* fall through */ }

        if (!streamComplete) {
          response = await api.chat(trimmed, chatModes, conversationHistory);
        }

        if (response) {
          setMessages(prev => prev.map(m =>
            m.id === assistantMsg.id
              ? {
                  ...m,
                  content: response!.narrative,
                  data: response!.data ?? undefined,
                  intent: response!.intent ?? undefined,
                  report: response!.report,
                  webResults: response!.web_results,
                  visualizations: response!.visualizations,
                  tableData: response!.table_data,
                  personaAnalyses: response!.persona_analyses,
                  confidenceAssessment: response!.confidence_assessment,
                  _sqlContext: response!.sql_meta?.sql,
                  followupSuggestions: response!.followup_suggestions,
                  loading: false,
                }
              : m
          ));

          // Only update canvas if response has structured data — otherwise keep previous
          const hasNewData = response.data || response.table_data || response.visualizations || response.persona_analyses;
          if (hasNewData) {
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
        }
      } catch (err) {
        setMessages(prev => prev.map(m =>
          m.id === assistantMsg.id
            ? { ...m, content: `Error: ${err}. Please rephrase your question.`, loading: false }
            : m
        ));
      } finally {
        setIsLoading(false);
        setCanvasLoading(false);
      }
    },
    [isLoading, buildHistory],
  );

  const handleAskInChat = useCallback((question: string) => {
    chatExternalSeqRef.current += 1;
    setChatExternalInput({ text: question, seq: chatExternalSeqRef.current });
    setActiveTab('chat');
  }, []);

  const breadcrumb = (() => {
    if (!canvas.data?.entity_focus?.length) return undefined;
    const names = (canvas.data.entity_focus as Array<Record<string, unknown>>)
      .slice(0, 3).map(e => String(e.title ?? e.label ?? '')).filter(Boolean);
    return names.length ? names.join(' › ') : undefined;
  })();

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.25 }}
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100vh',
        overflow: 'hidden',
        background: 'var(--color-bg)',
      }}
    >
      <TopBar
        onBack={onBack}
        onSearch={onSearch}
        onCI={onCI}
        onDataHub={onDataHub}
        activeTab={activeTab}
        onTabChange={tab => {
          if (tab === 'search') { onSearch?.(); return; }
          setActiveTab(tab as Tab);
        }}
        breadcrumb={breadcrumb}
      />

      {activeTab === 'graph' ? (
        <div style={{ flex: 1, minHeight: 0, overflow: 'hidden', padding: '0 16px' }}>
          <ErrorBoundary onRetry={() => setActiveTab('graph')}>
            <GraphExplorer initialEntity={graphEntity} seedGraph={seedGraph} onAskInChat={handleAskInChat} />
          </ErrorBoundary>
        </div>
      ) : activeTab === 'catalog' ? (
        <div style={{ flex: 1, minHeight: 0, overflow: 'hidden' }}>
          <ErrorBoundary onRetry={() => setActiveTab('catalog')}>
            <DataCatalogPanel
              onAskInChat={q => {
                setActiveTab('chat');
                setTimeout(() => void sendQuery(q), 50);
              }}
            />
          </ErrorBoundary>
        </div>
      ) : activeTab === 'feed' ? (
        <div style={{ flex: 1, minHeight: 0, overflow: 'hidden' }}>
          <ErrorBoundary onRetry={() => setActiveTab('feed')}>
            <IntelligenceFeed onAskInChat={handleAskInChat} />
          </ErrorBoundary>
        </div>
      ) : (
        <WorkspaceLayout
          left={
            <ErrorBoundary>
              <ChatPanel
                messages={messages}
                onSend={sendQuery}
                isLoading={isLoading}
                onFollowUp={q => void sendQuery(q)}
                onViewInGraph={(nodes, edges) => {
                  setSeedGraph({ nodes, edges });
                  setGraphEntity(null);
                  setActiveTab('graph');
                }}
                externalInput={chatExternalInput}
              />
            </ErrorBoundary>
          }
          right={
            <ErrorBoundary>
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
                onViewInGraph={(entity) => {
                  setGraphEntity(entity);
                  setActiveTab('graph');
                }}
                onOpenLiterature={(articleId) => setLitExplorerArticleId(articleId)}
              />
            </ErrorBoundary>
          }
          defaultSplit={50}
          minLeft={32}
          minRight={28}
        />
      )}
      {/* Literature Explorer overlay */}
      {litExplorerArticleId && (
        <LiteratureExplorer
          articleId={litExplorerArticleId}
          onClose={() => setLitExplorerArticleId(null)}
        />
      )}
    </motion.div>
  );
}
