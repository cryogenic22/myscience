// In dev mode (vite dev server), proxy rewrites /api -> /
// In production (served from FastAPI), call routes directly
export const BASE = import.meta.env.DEV ? '/api' : '';

// PB-UX04 — the scenario API contract IS the ScenariosPage `Scenario`
// interface (the backend serialises to it exactly, per services/scenarios.py).
// Type-only import → erased at build, no runtime/layering cost, no duplication.
import type { Scenario } from './pages/ScenariosPage';
// PB-UX06 — synthesis API contract IS the SynthesisPage types (backend
// serialises to them exactly, per services/insights.py).
import type { Insight, RejectedInsight } from './pages/SynthesisPage';

export interface SourceCoverageItem {
  source: string;
  records: number;
  total_records?: number | null;
  last_pull_records?: number | null;
  last_retrieved?: string | null;
}

export interface HealthData {
  status: string;
  database: string;
  tables: Record<string, number | string>;
  services: string[];
  total_records?: number;
  source_coverage?: SourceCoverageItem[];
  last_updated?: string;
}

export interface PipelineMetric {
  drug_id: string;
  drug_name: string;
  p1_count: number;
  p2_count: number;
  p3_count: number;
  p4_count: number;
  pipeline_score: number;
  active_pipeline_score: number;
}

export interface SuccessRateMetric {
  drug_id: string;
  drug_name: string;
  total: number;
  completed: number;
  terminated: number;
  success_rate: number;
}

export interface EvidenceMetric {
  drug_id: string;
  drug_name: string;
  total_articles: number;
  recent_count: number;
  weighted_score: number;
}

export interface CompetitiveSegment {
  mechanism_id: string;
  mechanism_name: string;
  therapeutic_area: string;
  drug_count: number;
  trial_count: number;
  active_trial_count: number;
  top_drug: string;
  total_pipeline_score: number;
}

export interface PortfolioMetric {
  company_id: string;
  company_name: string;
  drug_count: number;
  trial_count: number;
  active_trial_count: number;
  article_count: number;
  ta_count: number;
  pipeline_score_total: number;
}

export interface EntitySummary {
  entity: Record<string, unknown>;
  connections_by_type: Record<string, number>;
  connections_by_entity_type: Record<string, number>;
  total_connections: number;
}

export interface TherapeuticAreaItem {
  id: string;
  name: string;
  mesh_id?: string | null;
  drug_count: number;
  trial_count: number;
}

// ── Literature Explorer types ──

export interface LiteratureSection {
  id: string;
  title: string;
  level: number;
  content: string;
  children: LiteratureSection[];
}

export interface LiteratureCrossLinks {
  drugs: Array<{ id: string; name: string; link_type: string }>;
  trials: Array<{ id: string; title: string; link_type: string }>;
  mechanisms: Array<{ id: string; name: string }>;
}

export interface LiteratureDocument {
  article_id: string;
  pmid: string;
  pmc_id: string | null;
  title: string;
  journal: string | null;
  publication_date: string | null;
  authors: string[];
  mesh_terms: string[];
  article_type: string | null;
  is_protocol: boolean;
  is_systematic_review: boolean;
  has_full_text: boolean;
  full_text_source: string | null;
  sections: LiteratureSection[];
  cross_links: LiteratureCrossLinks;
  external_urls: { pubmed: string | null; pmc: string | null; pdf: string | null };
}

export interface SimilarArticle {
  article_id: string;
  pmid: string;
  title: string;
  journal: string | null;
  publication_date: string | null;
  similarity: number;
}

export interface SearchResult {
  entity_id: string;
  entity_type: string;
  title: string;
  snippet: string;
  similarity: number;
  metadata: Record<string, unknown>;
  provenance?: Record<string, unknown>;
  quality_score?: number | null;
  /** Enriched search: connection counts by entity type (e.g. {trial: 12, company: 3}) */
  connection_counts?: Record<string, number>;
  /** Enriched search: entity influence score (0-1) */
  influence_score?: number;
}

export interface SearchSuggestion {
  entity_id: string;
  entity_type: string;
  label: string;
  similarity: number;
}

export interface GraphNode {
  entity_id: string;
  entity_type: string;
  label: string;
  properties: Record<string, unknown>;
}

export interface GraphEdge {
  source_id: string;
  target_id: string;
  link_type: string;
  confidence: number;
  via: string;
  source?: string;
  /** D6 — where this edge came from + the as-of date, so edge claims are citeable. */
  provenance_source?: string | null;
  as_of?: string | null;
}

export interface GraphPathEdge {
  source: string;
  target: string;
  type: string;
  confidence: number;
}

export interface GraphPathResponse {
  path: GraphPathEdge[] | null;
  hops?: number;
  message?: string;
}

export interface EvidenceItem {
  source: string;
  entity_type: string;
  entity_id: string;
  content: string;
  relevance: number;
  provenance: Record<string, unknown>;
}

export interface QueryResponse {
  question: string;
  evidence: EvidenceItem[];
  graph_context: {
    nodes: GraphNode[];
    edges: GraphEdge[];
    node_count: number;
    edge_count: number;
  };
  metrics_context: Record<string, unknown>;
  entity_focus: Record<string, unknown>[];
  provenance_summary: Record<string, unknown>;
  /** DI-3 — structured decomposition (entities × dimensions, grounded cells). */
  decomposition_matrix?: DecompositionMatrix;
  /** H1 / MZ-XR-002 — honest coverage limits for not-ingested / thin sources the
   *  question implicates (so the UI shows them as first-class rows, not buried in
   *  prose). */
  limitations?: string[];
  /** Source-specific review flags behind the limitations (e.g. NO_PAYER_SOURCE,
   *  NADAC_NO_ROWS, EMA_PRODUCT_INFO_NOT_INGESTED). */
  review_flags?: string[];
}

/* ── DI-3 decomposition matrix (entities × dimensions, grounded cells) ── */

/** Coverage of a single cell / dimension: enough facts, some, or none. */
export type CoverageState = 'covered' | 'thin' | 'gap';

/** A single grounded fact inside a matrix cell — citeable. */
export interface MatrixFact {
  id: string;
  predicate: string;
  claim: string;
  /** Helix fact-class (R/C/S/I/X); maps onto the FactClassGlyph palette. */
  fact_class: string;
  source_label: string;
  source_url?: string | null;
  confidence?: number | null;
}

export interface MatrixDimension {
  key: string;
  label: string;
  sub_question: string;
  routes: string[];
  required: boolean;
  weight: number;
}

export interface MatrixCell {
  dimension: string;
  entity_id: string;
  sub_question: string;
  coverage: CoverageState;
  facts: MatrixFact[];
  routes_executed: string[];
  routes_skipped: string[];
}

export interface DecompositionMatrix {
  playbook_id: string;
  intent: string;
  entities: Array<{ entity_id: string; entity_type?: string; label: string }>;
  dimensions: MatrixDimension[];
  cells: MatrixCell[];
  coverage_summary: Record<string, CoverageState>;
  gaps: string[];
  synthesis: Record<string, unknown>;
}

/** D6 — provenance block stamped onto every materialized-view metric row. */
export interface MetricProvenance {
  source: string;
  derivation: string;
  computed_at: string;
  record_basis?: number | null;
  realtime_fallback?: boolean;
}

export interface VisualizationPoint {
  label: string;
  value: number;
}

export interface VisualizationSpec {
  id: string;
  type: 'bar' | 'donut' | 'line';
  title: string;
  value_unit?: string;
  data: VisualizationPoint[];
  recommended?: boolean;
  display_priority?: 'low' | 'medium' | 'high';
  reasoning_role?: 'context' | 'evidence' | 'support';
}

export interface EntityListItem {
  entity_id: string;
  label: string;
  [key: string]: unknown;
}

export interface CompareResponse {
  entities: Record<string, unknown>[];
  metrics_comparison: Record<string, unknown>;
  shared_connections: unknown[];
  unique_connections: Record<string, unknown[]>;
}

export interface TableData {
  columns: Array<{ key: string; label: string; type: 'text' | 'number' | 'date' }>;
  rows: Array<Record<string, unknown>>;
  title?: string;
}

export interface PersonaAnalysis {
  persona: string;
  display_name: string;
  analysis: string;
  confidence: number;
  key_findings: string[];
  data_gaps: string[];
}

export interface ChatResponse {
  narrative: string;
  intent: string;
  data: QueryResponse | null;
  report?: string;
  web_results?: Array<{
    title: string;
    url: string;
    snippet: string;
    source: string;
  }>;
  report_meta?: {
    web_enabled: boolean;
    generated_at: string;
  };
  visualizations?: VisualizationSpec[];
  table_data?: TableData;
  persona_analyses?: PersonaAnalysis[];
  confidence_assessment?: { overall: number; by_dimension: Record<string, number> };
  sql_meta?: { sql?: string };
  followup_suggestions?: string[];
}

export interface ChatModeFlags {
  include_graph?: boolean;
  include_metrics?: boolean;
  source_strict?: boolean;
  deep_research?: boolean;
  include_web?: boolean;
  team_eval?: boolean;
}

export interface ChatSessionSummary {
  id: string;
  scope_key: string;
  title: string;
  summary: string;
  created_at: string | null;
  updated_at: string | null;
}

export interface ChatSessionDetail extends ChatSessionSummary {
  transcript: Array<{
    id: string;
    role: 'user' | 'assistant';
    content: string;
    timestamp?: string | null;
    data?: QueryResponse;
    report?: string;
    webResults?: ChatResponse['web_results'];
    reportMeta?: ChatResponse['report_meta'];
    visualizations?: VisualizationSpec[];
  }>;
}

// ── Catalog types ──

export interface CatalogDataset {
  dataset_name: string;
  source_type: string;
  entity_type: string | null;
  table_name: string;
  row_count: number;
  last_refreshed_at: string | null;
  refresh_frequency?: string | null;
  license_name?: string | null;
  quality_score_avg: number | null;
  completeness_pct?: number | null;
  freshness_days?: number | null;
  description?: string;
  /** Derived ingest-health composite in [0,1] (D-API-2). null while unprofiled. */
  fair_overall?: number | null;
}

/** One dimension of the D-API-2 derived data-quality composite. */
export interface DatasetFairDimension {
  value: number | null;
  weight: number;
  explanation: string;
}

/** GET /catalog/datasets/{key}/fair — derived ingest-health composite + breakdown.
 *  Explicitly NOT a formal FAIR audit (see `note`); dimensions are null when the
 *  underlying metric is absent. */
export interface DatasetFairResponse {
  source_key: string;
  /** The composite dataset actually scored — equals source_key for a composite
   *  hit, or the resolved primary dataset when a bare source_type was passed. */
  dataset_name?: string;
  fair_overall: number | null;
  by_dimension: Record<string, DatasetFairDimension>;
  freshness_days: number | null;
  note: string;
}

export interface DatasetProfile {
  source_key: string;
  display_name: string;
  description: string;
  source_url: string | null;
  entity_types: string[];
  refresh_schedule: string;
  collection_method: string;
  fields_collected: string[];
  coverage_notes: string;
  records: number;
  quality_score: number | null;
  last_refreshed: string | null;
  freshness: string;
}

export interface CatalogEntity {
  _label: string;
  [key: string]: unknown;
}

export interface CatalogBrowseResponse {
  entity_type: string;
  results: CatalogEntity[];
  total: number;
  limit: number;
  offset: number;
  editable_fields: string[];
}

export interface QualityResult {
  rule_id: string;
  rule_name: string;
  rule_type: string;
  severity: string;
  passed: boolean;
  score: number;
  details: Record<string, unknown> | null;
}

export interface ChangeLogEntry {
  id: number;
  entity_type: string;
  entity_id: string;
  change_type: string;
  changed_fields: string[];
  old_content_hash?: string;
  new_content_hash?: string;
  etl_run_id?: string;
  changed_at: string;
}

export interface EntityLink {
  source_entity_id: string;
  source_entity_type: string;
  target_entity_id: string;
  target_entity_type: string;
  link_type: string;
  confidence: number;
  provenance_source: string;
  source_label?: string;
  target_label?: string;
}

export interface EntityTag {
  tag_name: string;
  tag_value: string;
  created_by: string;
  created_at: string;
}

export interface EntityAlias {
  alias_text: string;
  source_type: string;
  confidence: number;
  verified: boolean;
}

export interface CatalogEntityDetail {
  entity: Record<string, unknown>;
  entity_type: string;
  quality_results: QualityResult[];
  change_log: ChangeLogEntry[];
  links: EntityLink[];
  tags: EntityTag[];
  aliases: EntityAlias[];
  editable_fields: string[];
}

export interface HITLItem {
  id: string;
  review_type: string;
  entity_type: string;
  entity_id: string;
  priority: number;
  status: string;
  payload: Record<string, unknown>;
  assigned_to: string | null;
  created_at: string;
  resolved_at: string | null;
}

export interface CatalogStats {
  entity_counts: Record<string, number>;
  quality: { assessed?: number; avg_score?: number; failures?: number };
  hitl: { total?: number; pending?: number; approved?: number; rejected?: number };
  changes: { total_changes?: number; recent_changes?: number };
}

export interface FieldCompleteness {
  total: number;
  fields: Record<string, number>;
  overall: number;
}

export interface SourceFreshness {
  entity_type: string;
  records: number;
  latest: string | null;
  days_since: number | null;
  stale: boolean;
}

export interface ResearchJob {
  id: string;
  scope_key: string;
  question: string;
  options: Record<string, unknown>;
  status: 'queued' | 'running' | 'completed' | 'failed';
  error_message?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  completed_at?: string | null;
  result_payload?: ChatResponse;
}

// ── Intelligence Feed types ──

export interface IntelligenceFeedItem {
  event_id: string;
  event_type: string;
  event_date: string | null;
  description: string;
  source_url: string | null;
  source_tier: string;
  trust_score: number;
  primary_entity_name: string | null;
  primary_entity_type: string | null;
  severity: string;
  impact_count: number;
  max_impact_magnitude: number;
  status: string;
  created_at: string;
}

export interface FeedSummary {
  total_unread: number;
  critical_count: number;
  high_count: number;
  since_hours: number;
}

// ── Source Profile types ──

export interface SourceProfileData {
  source_key: string;
  label: string;
  schedule: string;
  status: string;
  last_run: string | null;
  days_since: number | null;
  total_records: number;
  entity_breakdown: Array<{ entity_type: string; count: number }>;
  field_completeness: Array<{ field: string; filled: number; total: number; pct: number }>;
  steward_actions: Array<{ action: string; status: string; timestamp: string }>;
  cross_source_links: Array<{ target_source: string; link_type: string; count: number }>;
}

// ── Source Explorer types ──

export interface SourceRecordColumn {
  name: string;
  type: string;
}

export interface SourceRecordsResponse {
  source_key: string;
  entity_type: string;
  table: string;
  columns: SourceRecordColumn[];
  records: Record<string, unknown>[];
  total: number;
  limit: number;
  offset: number;
}

export interface SourceConnection {
  target_source: string;
  link_type: string;
  count: number;
  sample_entities?: string[];
}

export interface SourceConnectionsResponse {
  source_key: string;
  connections: SourceConnection[];
  total_outgoing: number;
  total_incoming: number;
}

// ── Entity Profile types ──

export interface EntityProfileData {
  identity: Record<string, unknown>;
  entity_type: string;
  fair_scores: {
    completeness: number;
    link_density: number;
    source_diversity: number;
    freshness: number;
    resolution: number;
    overall: number;
  };
  ai_readiness: {
    has_embedding: boolean;
    is_linked: boolean;
    is_resolved: boolean;
  };
  connections: Array<{
    entity_type: string;
    count: number;
    sample_labels: string[];
  }>;
  evidence: Array<{
    title: string;
    type: string;
    date: string | null;
    entity_id: string;
  }>;
  provenance: string[];
  recent_changes: Array<{
    field: string;
    old_value: string | null;
    new_value: string | null;
    changed_at: string;
  }>;
  stats: {
    total_connections: number;
    influence_score: number | null;
  };
}

// ── API Calls ──

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

export const api = {
  health: () => get<HealthData>('/health'),

  // Metrics
  pipeline: (params?: { drug_id?: string; therapeutic_area?: string; limit?: number }) =>
    get<PipelineMetric[]>(`/metrics/pipeline?${qs(params)}`),
  successRate: (params?: { drug_id?: string; limit?: number }) =>
    get<SuccessRateMetric[]>(`/metrics/success-rate?${qs(params)}`),
  evidence: (params?: { drug_id?: string; limit?: number }) =>
    get<EvidenceMetric[]>(`/metrics/evidence?${qs(params)}`),
  competitive: (params?: { therapeutic_area_id?: string; mechanism_id?: string; limit?: number }) =>
    get<CompetitiveSegment[]>(`/metrics/competitive?${qs(params)}`),
  portfolio: (params?: { company_id?: string; limit?: number }) =>
    get<PortfolioMetric[]>(`/metrics/portfolio?${qs(params)}`),

  // Search
  search: (query: string, entityTypes?: string[], limit?: number, offset?: number) =>
    post<{ results: SearchResult[]; total: number; limit: number; offset: number }>('/search', {
      query,
      entity_types: entityTypes,
      limit: limit ?? 10,
      offset: offset ?? 0,
    }),
  searchSuggest: (q: string, limit?: number) =>
    get<{ suggestions: SearchSuggestion[] }>(`/search/suggest?q=${encodeURIComponent(q)}&limit=${limit ?? 8}`),

  // Graph
  traverse: (
    entityType: string,
    entityId: string,
    hops?: number,
    opts?: { linkTypes?: string[]; minConfidence?: number; maxNodes?: number },
  ) => {
    const params: Record<string, unknown> = {
      hops: hops ?? 2,
      max_nodes: opts?.maxNodes ?? 50,
    };
    if (opts?.linkTypes && opts.linkTypes.length > 0) params.link_types = opts.linkTypes.join(',');
    if (opts?.minConfidence !== undefined) params.min_confidence = opts.minConfidence;
    return get<{ nodes: GraphNode[]; edges: GraphEdge[] }>(
      `/graph/traverse/${entityType}/${encodeURIComponent(entityId)}?${qs(params)}`
    );
  },
  entitySummary: (entityType: string, entityId: string) =>
    get<EntitySummary>(`/graph/summary/${entityType}/${encodeURIComponent(entityId)}`),
  graphPath: (
    sourceId: string,
    sourceType: string,
    targetId: string,
    targetType: string,
    maxHops?: number,
  ) => get<GraphPathResponse>(`/graph/path?${qs({
    source_id: sourceId,
    source_type: sourceType,
    target_id: targetId,
    target_type: targetType,
    max_hops: maxHops ?? 4,
  })}`),

  // Query (GraphRAG)
  query: (question: string, entityHints?: string[]) =>
    post<QueryResponse>('/query', { question, entity_hints: entityHints ?? [] }),
  dossier: (entityId: string, entityType: string) =>
    post<QueryResponse>('/query/dossier', { entity_id: entityId, entity_type: entityType }),
  compare: (entityIds: string[], entityType: string) =>
    post<CompareResponse>('/query/compare', { entity_ids: entityIds, entity_type: entityType }),

  // Entities
  listEntities: (entityType: string, search?: string, limit?: number) =>
    get<{ entity_type: string; results: EntityListItem[]; count: number }>(
      `/entities/${entityType}?${qs({ search, limit: limit ?? 50 })}`
    ),
  therapeuticAreas: () =>
    get<{ therapeutic_areas: TherapeuticAreaItem[]; total: number }>('/therapeutic-areas'),

  // Chat (orchestration)
  chat: (question: string, modes?: ChatModeFlags, conversationHistory?: Array<{role: string; content: string; sql_context?: string; entities?: string[]; metrics_types?: string[]}>) =>
    post<ChatResponse>('/chat', {
      question,
      include_graph: modes?.include_graph ?? true,
      include_metrics: modes?.include_metrics ?? true,
      source_strict: modes?.source_strict ?? true,
      deep_research: modes?.deep_research ?? false,
      include_web: modes?.include_web ?? false,
      team_eval: modes?.team_eval ?? false,
      ...(conversationHistory && conversationHistory.length > 0 ? { conversation_history: conversationHistory } : {}),
    }),

  /** C2 — record a thumbs up/down on a chat answer (the training signal). */
  chatFeedback: (params: {
    question: string;
    rating: 1 | -1;
    sessionId?: string;
    comment?: string;
    intent?: string;
    answerExcerpt?: string;
  }) =>
    post<{ feedback: { id: string; rating: number } }>('/chat/feedback', {
      question: params.question,
      rating: params.rating,
      session_id: params.sessionId,
      comment: params.comment,
      intent: params.intent,
      answer_excerpt: params.answerExcerpt,
    }),

  /** Streaming chat via SSE. Calls onToken for each synthesis chunk, onStatus for progress, onDone with full payload. */
  chatStream: async (
    question: string,
    modes: ChatModeFlags | undefined,
    conversationHistory: Array<{role: string; content: string; sql_context?: string; entities?: string[]; metrics_types?: string[]}> | undefined,
    callbacks: {
      onStatus?: (message: string) => void;
      onToken?: (text: string) => void;
      onDone?: (payload: ChatResponse) => void;
      onError?: (message: string) => void;
    },
  ) => {
    const resp = await fetch(`${BASE}/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        question,
        include_graph: modes?.include_graph ?? true,
        include_metrics: modes?.include_metrics ?? true,
        source_strict: modes?.source_strict ?? true,
        ...(conversationHistory?.length ? { conversation_history: conversationHistory } : {}),
      }),
    });
    if (!resp.ok || !resp.body) {
      callbacks.onError?.(`Stream failed: ${resp.status}`);
      return;
    }
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    let eventType = '';  // persists across chunks — SSE event/data may span TCP segments
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const lines = buffer.split('\n');
      buffer = lines.pop() ?? '';

      for (const line of lines) {
        if (line.startsWith('event: ')) {
          eventType = line.slice(7).trim();
        } else if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6));
            if (eventType === 'status') callbacks.onStatus?.(data.message);
            else if (eventType === 'token') callbacks.onToken?.(data.text);
            else if (eventType === 'done') callbacks.onDone?.(data as ChatResponse);
            else if (eventType === 'error') callbacks.onError?.(data.message);
          } catch { /* skip malformed events */ }
          eventType = '';
        }
      }
    }
  },
  createResearchJob: (question: string, modes?: ChatModeFlags, scopeKey?: string) =>
    post<{ job: ResearchJob }>('/chat/research-jobs', {
      question,
      scope_key: scopeKey ?? 'default',
      include_graph: modes?.include_graph ?? true,
      include_metrics: modes?.include_metrics ?? true,
      source_strict: modes?.source_strict ?? true,
      include_web: modes?.include_web ?? false,
    }),
  getResearchJob: (jobId: string, scopeKey?: string) =>
    get<{ job: ResearchJob }>(`/chat/research-jobs/${encodeURIComponent(jobId)}?${qs({ scope_key: scopeKey ?? 'default' })}`),
  listResearchJobs: (scopeKey?: string, limit?: number, offset?: number) =>
    get<{ jobs: ResearchJob[]; count: number; limit: number; offset: number }>(
      `/chat/research-jobs?${qs({ scope_key: scopeKey ?? 'default', limit: limit ?? 20, offset: offset ?? 0 })}`
    ),
  listChatSessions: (scopeKey?: string, limit?: number, offset?: number) =>
    get<{ sessions: ChatSessionSummary[]; count: number; limit: number; offset: number }>(
      `/chat/sessions?${qs({ scope_key: scopeKey ?? 'default', limit: limit ?? 20, offset: offset ?? 0 })}`
    ),
  saveChatSession: (
    payload: {
      title: string;
      transcript: ChatSessionDetail['transcript'];
      session_id?: string;
      summary?: string;
    },
    scopeKey?: string
  ) =>
    post<{ session: ChatSessionSummary }>('/chat/sessions', {
      scope_key: scopeKey ?? 'default',
      ...payload,
    }),
  getChatSession: (sessionId: string, scopeKey?: string) =>
    get<{ session: ChatSessionDetail }>(
      `/chat/sessions/${encodeURIComponent(sessionId)}?${qs({ scope_key: scopeKey ?? 'default' })}`
    ),
  deleteChatSession: (sessionId: string, scopeKey?: string) =>
    fetch(`${BASE}/chat/sessions/${encodeURIComponent(sessionId)}?${qs({ scope_key: scopeKey ?? 'default' })}`, {
      method: 'DELETE',
    }).then(async (res) => {
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      return (await res.json()) as { ok: boolean; session_id: string };
    }),
  // Catalog
  catalogStats: () => get<CatalogStats>('/catalog/stats'),
  catalogDatasets: () => get<{ datasets: CatalogDataset[]; count: number }>('/catalog/datasets'),
  datasetProfile: (sourceKey: string) =>
    get<DatasetProfile>(`/catalog/datasets/${encodeURIComponent(sourceKey)}/profile`),
  datasetFair: (sourceKey: string) =>
    get<DatasetFairResponse>(`/catalog/datasets/${encodeURIComponent(sourceKey)}/fair`),
  catalogBrowse: (entityType: string, params?: {
    search?: string; status?: string; quality_min?: number;
    sort?: string; sort_by?: string; sort_dir?: string; limit?: number; offset?: number;
  }) => get<CatalogBrowseResponse>(`/catalog/entities/${entityType}?${qs(params)}`),
  catalogEntityDetail: (entityType: string, entityId: string) =>
    get<CatalogEntityDetail>(`/catalog/entities/${entityType}/${encodeURIComponent(entityId)}`),
  catalogUpdateEntity: (entityType: string, entityId: string, fields: Record<string, unknown>, reason?: string) =>
    fetch(`${BASE}/catalog/entities/${entityType}/${encodeURIComponent(entityId)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ fields, reason: reason ?? '' }),
    }).then(async (res) => {
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      return res.json() as Promise<{ ok: boolean; entity_id: string; updated_fields: string[] }>;
    }),
  catalogAddTag: (entityType: string, entityId: string, tagName: string, tagValue: string) =>
    post<{ ok: boolean }>(`/catalog/entities/${entityType}/${encodeURIComponent(entityId)}/tags`, {
      tag_name: tagName, tag_value: tagValue,
    }),
  catalogChanges: (params?: { entity_type?: string; entity_id?: string; limit?: number; offset?: number }) =>
    get<{ changes: ChangeLogEntry[]; total: number }>(`/catalog/changes?${qs(params)}`),
  catalogHITL: (params?: { status_filter?: string; entity_type?: string; limit?: number; offset?: number }) =>
    get<{ items: HITLItem[]; total: number }>(`/catalog/hitl?${qs(params)}`),
  catalogResolveHITL: (reviewId: string, action: string, notes?: string) =>
    post<{ ok: boolean }>(`/catalog/hitl/${encodeURIComponent(reviewId)}/resolve`, {
      action, resolution_notes: notes ?? '',
    }),
  catalogEnrich: (entityType: string, scope: string, description?: string) =>
    post<{ ok: boolean; review_id: string; message: string }>('/catalog/enrich', {
      entity_type: entityType, scope, description: description ?? '',
    }),
  catalogRefreshViews: () => post<{ ok: boolean; views: Record<string, string> }>('/catalog/refresh-views', {}),
  catalogQuality: (entityType?: string) =>
    get<{ summary: Array<Record<string, unknown>>; rules: Array<Record<string, unknown>> }>(
      `/catalog/quality?${qs({ entity_type: entityType })}`
    ),
  catalogCompleteness: (entityType?: string) =>
    get<{ completeness: Record<string, FieldCompleteness> }>(
      `/catalog/completeness?${qs({ entity_type: entityType })}`
    ),
  catalogFreshness: () =>
    get<{ freshness: Record<string, SourceFreshness> }>('/catalog/freshness'),
  catalogGraphSummary: () =>
    get<{ link_types: Array<{type: string; count: number}>; total_links: number; total_entities: number; drug_completeness: Record<string, number> }>('/catalog/graph-summary'),
  catalogTaCoverage: () =>
    get<{ therapeutic_areas: Array<{id: string; name: string; drug_count: number; linked_drug_count: number; trial_count: number}> }>('/catalog/ta-coverage'),
  catalogPipelineStatus: () =>
    get<{ connectors: Array<{source_key: string; label: string; schedule: string; last_run: string|null; days_since: number|null; records: number; status: string}> }>('/catalog/pipeline-status'),
  catalogBulkUpdate: (entityType: string, entityIds: string[], fields: Record<string, unknown>, reason?: string) =>
    post<{ ok: boolean; updated: number }>(`/catalog/bulk-update?entity_type=${encodeURIComponent(entityType)}`, {
      entity_ids: entityIds, fields, reason: reason ?? '',
    }),
  catalogBulkResolve: (reviewIds: string[], action: string, notes?: string) =>
    post<{ ok: boolean; resolved: number }>('/catalog/bulk-resolve', {
      review_ids: reviewIds, action, resolution_notes: notes ?? '',
    }),
  catalogRunEnrichment: (entityType?: string, maxEntities?: number) =>
    post<{ ok: boolean; results: Record<string, unknown> }>('/catalog/run-enrichment', {
      entity_type: entityType ?? 'drug', max_entities: maxEntities ?? 50,
    }),

  // Entity Profile
  entityProfile: (entityType: string, entityId: string) =>
    get<EntityProfileData>(`/catalog/entity-profile/${entityType}/${encodeURIComponent(entityId)}`),

  // Entity Activity Feed
  entityEvents: (entityType: string, entityId: string, limit?: number) =>
    get<{events: Array<{event_type: string; description: string; source: string; timestamp: string; details: Record<string, unknown>}>; total: number}>(
      `/catalog/entity-events/${entityType}/${encodeURIComponent(entityId)}?limit=${limit ?? 10}`
    ),

  // Source Profile
  sourceProfile: (sourceKey: string) =>
    get<SourceProfileData>(`/catalog/source-profile/${encodeURIComponent(sourceKey)}`),

  // Source Explorer — records + connections
  sourceRecords: (sourceKey: string, params?: { entity_type?: string; limit?: number; offset?: number }) =>
    get<SourceRecordsResponse>(
      `/catalog/sources/${encodeURIComponent(sourceKey)}/records?${qs(params)}`
    ),
  sourceConnections: (sourceKey: string) =>
    get<SourceConnectionsResponse>(
      `/catalog/sources/${encodeURIComponent(sourceKey)}/connections`
    ),

  // Steward
  stewardStatus: () =>
    get<{ total_actions: number; last_7_days: { completed: number }; last_completed_run: string | null }>('/steward/status'),
  stewardActions: (params?: { limit?: number }) =>
    get<{ actions: Array<{ action_type: string; entity_type: string; details: string; completed_at: string }> }>(`/steward/actions?${qs(params)}`),

  // Literature Explorer
  literatureDocument: (articleId: string) =>
    get<LiteratureDocument>(`/literature/${encodeURIComponent(articleId)}/document`),
  literatureSimilar: (articleId: string, limit?: number) =>
    get<{similar: SimilarArticle[]}>(`/literature/${encodeURIComponent(articleId)}/similar?limit=${limit ?? 5}`),
  literatureSummary: (articleId: string) =>
    get<{summary: string | null; generated: boolean}>(`/literature/${encodeURIComponent(articleId)}/summary`),

  // Intelligence Feed
  intelligenceFeed: (params?: {limit?: number; offset?: number; severity?: string}) =>
    get<{items: IntelligenceFeedItem[]; total: number}>(`/intelligence/feed?${qs(params)}`),
  intelligenceFeedSummary: (sinceHours?: number) =>
    get<FeedSummary>(`/intelligence/feed/summary?since_hours=${sinceHours ?? 24}`),
  intelligenceEventDetail: (eventId: string) =>
    get<{event: Record<string, unknown>; assessments: Record<string, unknown>[]}>(`/intelligence/feed/${encodeURIComponent(eventId)}`),
  intelligenceDismiss: (eventId: string) =>
    post<{ok: boolean}>(`/intelligence/feed/${encodeURIComponent(eventId)}/dismiss`, {}),

  exportReport: (report: string, title: string, format: 'md' | 'txt' | 'json' = 'md') =>
    fetch(`${BASE}/chat/export/report`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ report, title, format }),
    }).then(async (res) => {
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      const blob = await res.blob();
      const disposition = res.headers.get('Content-Disposition') ?? '';
      return { blob, filename: filenameFromDisposition(disposition) };
    }),
};

function qs(params?: Record<string, unknown>): string {
  if (!params) return '';
  return Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== null)
    .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`)
    .join('&');
}

function filenameFromDisposition(disposition: string): string {
  const match = disposition.match(/filename=\"?([^\";]+)\"?/i);
  return match?.[1] ?? 'report.md';
}

// ────────────────────────────────────────────────────────────────────
// SPEC-019 — Connector management API
// ────────────────────────────────────────────────────────────────────

export interface ConnectorSummary {
  source_key: string;
  label: string;
  schedule: string;
  enabled: boolean;
  auto_approve_runs: boolean;
  manual_only: boolean;
  notes: string | null;
  connection_status: 'connected' | 'available' | 'disabled';
  last_run: { status: string; completed_at: string | null; records_inserted: number | null } | null;
  description: string | null;
  license: string | null;
}

export interface ConnectorDetail extends ConnectorSummary {
  license_url: string | null;
  api_base_url: string | null;
  config: {
    enabled: boolean;
    auto_approve_runs: boolean;
    manual_only: boolean;
    notes: string | null;
  };
  recent_runs: Array<{
    status: string;
    started_at: string | null;
    completed_at: string | null;
    records_inserted: number | null;
  }>;
}

export interface HealthCheckResponse {
  source_key: string;
  healthy: boolean;
  message: string;
  response_time_ms: number | null;
  checked_at: string | null;
}

function authHeaders(): Record<string, string> {
  if (typeof window === 'undefined') return {};
  const tok = window.localStorage.getItem('mz_auth_token');
  return tok ? { Authorization: `Bearer ${tok}` } : {};
}

export const connectorsApi = {
  list: (): Promise<{ connectors: ConnectorSummary[] }> =>
    fetch(`${BASE}/connectors`).then((r) => {
      if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
      return r.json();
    }),

  detail: (key: string): Promise<ConnectorDetail> =>
    fetch(`${BASE}/connectors/${encodeURIComponent(key)}`).then((r) => {
      if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
      return r.json();
    }),

  healthCheck: (key: string): Promise<HealthCheckResponse> =>
    fetch(`${BASE}/connectors/${encodeURIComponent(key)}/health-check`, {
      method: 'POST',
      headers: { ...authHeaders() },
    }).then(async (r) => {
      if (!r.ok) throw new Error(`${r.status}: ${await r.text().catch(() => r.statusText)}`);
      return r.json();
    }),

  updateConfig: (
    key: string,
    body: { enabled?: boolean; auto_approve_runs?: boolean; manual_only?: boolean; notes?: string | null },
  ): Promise<ConnectorDetail['config'] & { source_key: string }> =>
    fetch(`${BASE}/connectors/${encodeURIComponent(key)}/config`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify(body),
    }).then(async (r) => {
      if (!r.ok) throw new Error(`${r.status}: ${await r.text().catch(() => r.statusText)}`);
      return r.json();
    }),

  triggerRun: (key: string): Promise<{ source_key: string; queued: boolean; triggered_by: string; detail: unknown }> =>
    fetch(`${BASE}/connectors/${encodeURIComponent(key)}/run`, {
      method: 'POST',
      headers: { ...authHeaders() },
    }).then(async (r) => {
      if (!r.ok) throw new Error(`${r.status}: ${await r.text().catch(() => r.statusText)}`);
      return r.json();
    }),
};

// ────────────────────────────────────────────────────────────────────
// SPEC-020 — Signals + Watchlist API (CI surface)
// ────────────────────────────────────────────────────────────────────

export type ConfidenceTier = 'confirmed' | 'reported' | 'inferred' | 'disputed';
export type ImpactTier = 'high' | 'medium' | 'low';
export type SignalStatus = 'candidate' | 'reviewed' | 'shipped' | 'superseded' | 'retracted';

export interface Signal {
  id: string;
  event_id: string | null;
  kbq_tags: string[];
  headline: string;
  summary: string | null;
  direction: 'positive' | 'negative' | 'neutral' | 'mixed' | null;
  confidence_tier: ConfidenceTier;
  trust_score: number | null;
  impact_tier: ImpactTier;
  impact_score: number | null;
  rule_version_id: string | null;
  primary_entity_type: string | null;
  primary_entity_id: string | null;
  primary_entity_name: string | null;
  related_entity_ids: string[];
  evidence_document_ids: string[];
  /** Loop #20 — Per-signal materiality breakdown (when scored). */
  materiality_factors?: import('./types/materiality').MaterialityFactors | null;
  status: SignalStatus;
  superseded_by: string | null;
  supersedence_reason: string | null;
  created_at: string | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
  shipped_at: string | null;
  /** PB-SL05 — facts this signal feeds (forward provenance), on detail only. */
  linked_facts?: SignalLinkedFact[];
}

/** A fact a signal produces/relates to (signal_facts edge). */
export interface SignalLinkedFact {
  role: string;
  fact_id: string;
  predicate: string;
  fact_class: string | null;
  claim: string | null;
  confidence: number | null;
  source_id: string | null;
  source_url: string | null;
}

export interface SignalsListParams {
  /** A single status, or 'all' to drop the default reviewed/shipped filter
      (reveals auto-minted candidate fact-signals). PB-SL08. */
  status?: SignalStatus | 'all';
  impact?: ImpactTier;
  confidence?: ConfidenceTier;
  /** PB-SL08 — only signals created within the last N days. */
  since_days?: number;
  /** PB-104 — pass multiple values; serialized to `kbq=a,b,c` on the wire. */
  kbq?: string[];
  entity_type?: string;
  entity_id?: string;
  limit?: number;
  offset?: number;
}

export const signalsApi = {
  list: (params: SignalsListParams = {}): Promise<{ signals: Signal[]; count: number; limit: number; offset: number }> => {
    const { kbq, ...rest } = params;
    const wire: Record<string, unknown> = { ...rest };
    if (kbq && kbq.length > 0) wire.kbq = kbq.join(',');
    const qsStr = qs(wire);
    const url = `${BASE}/signals${qsStr ? `?${qsStr}` : ''}`;
    return fetch(url).then((r) => {
      if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
      return r.json();
    });
  },

  detail: (id: string): Promise<Signal> =>
    fetch(`${BASE}/signals/${encodeURIComponent(id)}`).then((r) => {
      if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
      return r.json();
    }),

  review: (id: string, status: 'reviewed' | 'shipped' | 'retracted'): Promise<{ id: string; status: string }> =>
    fetch(`${BASE}/signals/${encodeURIComponent(id)}/review`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ status }),
    }).then(async (r) => {
      if (!r.ok) throw new Error(`${r.status}: ${await r.text().catch(() => r.statusText)}`);
      return r.json();
    }),
};

// Loop #17 — Helix Bridge endpoints.
export const bridgeApi = {
  moments: (n: number = 3, sinceDays: number = 7): Promise<{ moments: import('./types/helix').Moment[] }> =>
    fetch(`${BASE}/bridge/moments`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ n, since_days: sinceDays }),
    }).then(async (r) => {
      if (!r.ok) throw new Error(`${r.status}: ${await r.text().catch(() => r.statusText)}`);
      return r.json();
    }),
};

export interface KbqItem {
  claim: string;
  /** PB-SL11 — 'signal' (curated) or 'fact' (the underlying ledger). */
  source?: 'signal' | 'fact';
  /** null for fact items (they carry fact_id instead). */
  signal_id: string | null;
  fact_id?: string | null;
  /** PB-SL11 — fact_class for the glyph on fact items. */
  fact_class?: string | null;
  evidence_ids: string[];
  impact_tier: 'high' | 'medium' | 'low' | null;
  confidence_tier: string | null;
  date: string | null;
  /** PB-SL11 — provenance for fact items (source registry id + URL). */
  source_label?: string | null;
  source_url?: string | null;
}
export interface KbqView {
  kbq: number;
  title: string;
  status: 'fresh' | 'insufficient';
  items: KbqItem[];
}
export interface EntityKbqs {
  entity: { type: string; id: string; name?: string | null };
  kbqs: KbqView[];
  completeness: number;
  /** PB-SL10 — echoed back when fetched via the by-asset query surface. */
  asset?: string;
}

export const kbqApi = {
  forEntity: (entityType: string, entityId: string): Promise<EntityKbqs> =>
    fetch(`${BASE}/entities/${encodeURIComponent(entityType)}/${encodeURIComponent(entityId)}/kbq`)
      .then(async (r) => {
        if (!r.ok) throw new Error(`${r.status}: ${await r.text().catch(() => r.statusText)}`);
        return r.json();
      }),
  /** PB-SL10 — resolve a typed asset → 8 KBQs (the query surface).
   *  Mounted at /kbq (NOT /entities/kbq, which the /entities/{entity_type}
   *  route would shadow). */
  byAsset: (asset: string): Promise<EntityKbqs> =>
    fetch(`${BASE}/kbq?asset=${encodeURIComponent(asset)}`)
      .then(async (r) => {
        if (!r.ok) throw new Error(`${r.status}: ${await r.text().catch(() => r.statusText)}`);
        return r.json();
      }),
};

export const agentsApi = {
  activity: (): Promise<import('./types/agents').AgentActivityResponse> =>
    fetch(`${BASE}/agents/activity`).then(async (r) => {
      if (!r.ok) throw new Error(`${r.status}: ${await r.text().catch(() => r.statusText)}`);
      return r.json();
    }),

  /** PB-203 — the nudge intents available for one agent (static registry). */
  intents: (agent: string): Promise<import('./types/agents').AgentIntentsResponse> =>
    fetch(`${BASE}/agents/${encodeURIComponent(agent)}/intents`).then(async (r) => {
      if (!r.ok) throw new Error(`${r.status}: ${await r.text().catch(() => r.statusText)}`);
      return r.json();
    }),

  /** PB-203 — queue a nudge for an agent. Requires uploader role. */
  nudge: (
    agent: string,
    body: { intent: string; target?: Record<string, unknown>; note?: string },
  ): Promise<{ nudge: import('./types/agents').NudgeRecord }> =>
    fetch(`${BASE}/agents/${encodeURIComponent(agent)}/nudge`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify(body),
    }).then(async (r) => {
      if (!r.ok) throw new Error(`${r.status}: ${await r.text().catch(() => r.statusText)}`);
      return r.json();
    }),
};

export const evidenceApi = {
  byIds: (
    ids: string[],
  ): Promise<import('./types/evidence').EvidenceBatchResponse> =>
    fetch(`${BASE}/evidence/by-ids`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ ids }),
    }).then(async (r) => {
      if (!r.ok) throw new Error(`${r.status}: ${await r.text().catch(() => r.statusText)}`);
      return r.json();
    }),
};

export interface WatchlistEntry {
  id: string;
  user_id: string;
  entity_type: string;
  entity_id: string;
  label: string | null;
  created_at: string | null;
}

export const watchlistApi = {
  list: (): Promise<{ entries: WatchlistEntry[] }> =>
    fetch(`${BASE}/watchlist`, { headers: { ...authHeaders() } }).then(async (r) => {
      if (!r.ok) throw new Error(`${r.status}: ${await r.text().catch(() => r.statusText)}`);
      return r.json();
    }),

  add: (body: { entity_type: string; entity_id: string; label?: string }): Promise<WatchlistEntry> =>
    fetch(`${BASE}/watchlist`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify(body),
    }).then(async (r) => {
      if (!r.ok) throw new Error(`${r.status}: ${await r.text().catch(() => r.statusText)}`);
      return r.json();
    }),

  remove: (id: string): Promise<void> =>
    fetch(`${BASE}/watchlist/${encodeURIComponent(id)}`, {
      method: 'DELETE',
      headers: { ...authHeaders() },
    }).then(async (r) => {
      if (!r.ok && r.status !== 204) throw new Error(`${r.status}: ${await r.text().catch(() => r.statusText)}`);
    }),
};

// ────────────────────────────────────────────────────────────────────
// SPEC-021 — War Room API (decision flywheel Phase A)
// ────────────────────────────────────────────────────────────────────

export type MoveType =
  | 'price_cut' | 'new_indication' | 'label_expansion' | 'trial_readout'
  | 'acquisition' | 'formulation_switch' | 'geo_expansion' | 'segment_pivot';

export type ReactionType =
  | 'match_price' | 'counter_launch' | 'accelerate_trial' | 'seek_partnership'
  | 'attack_label' | 'hold_position' | 'exit_segment' | 'differentiate';

export type GamePhase = 'prelaunch' | 'launch' | 'postlaunch';

export interface WarRoomReaction {
  id: string | null;
  round_id: string;
  competitor_company_id: string | null;
  competitor_company_name: string;
  reaction_type: ReactionType;
  headline: string | null;
  specific_action: string | null;
  asset_leveraged: { id?: string; name?: string; rationale?: string } | null;
  rationale: string | null;
  evidence_basis: string[];
  stripped_citations?: string[];           // PD strengthening: hallucinated IDs
  evidence_validated?: boolean;            // false if anything was stripped
  scores: {
    market_share_delta?: number;
    time_to_execute_months?: number;
    capex_required_musd?: number;
    regulatory_risk?: number;
    payer_acceptance?: number;
  };
  confidence_score?: number | null;        // numeric (0..1) — primary
  confidence: 'high' | 'medium' | 'low' | null;  // categorical (derived)
  created_at: string | null;
}

export interface WarRoomRound {
  id: string;
  war_room_id: string;
  round_number: number;
  player_company_id: string | null;
  player_company_name: string | null;
  move_type: MoveType;
  move_payload: Record<string, unknown>;
  notes: string | null;
  created_at: string | null;
  reactions: WarRoomReaction[];
}

// UX12/UX13 — engagement deliverable exports (printable HTML → browser PDF).
// The endpoints are Bearer-auth'd, so a plain <a href> would 401; fetch with
// the auth header, then open the rendered HTML as a blob in a new tab.
export type EngagementExportKind = 'brief' | 'dossier' | 'deck';

export const engagementExportApi = {
  open: async (eid: string, kind: EngagementExportKind): Promise<void> => {
    const res = await fetch(
      `${BASE}/engagements/${encodeURIComponent(eid)}/export/${kind}.html`,
      { headers: { ...authHeaders() } },
    );
    if (!res.ok) throw new Error(`${res.status}: ${await res.text().catch(() => res.statusText)}`);
    const blobUrl = URL.createObjectURL(await res.blob());
    window.open(blobUrl, '_blank');
  },
};

// W1 / IX04a — the war room's scenario mode. Values match
// services/scenario_state.py::ScenarioMode.
export type WarRoomMode = 'guided' | 'autonomous' | 'game_theoretic';

// PB-H13 — autonomous play transcript.
export interface AutoplayRound {
  round: number;
  our_move: string;
  reactions: WarRoomReaction[];
  narration: string;
}
export interface AutoplayResult {
  mode: string;
  war_room_id: string;
  rounds: AutoplayRound[];
  narration: string[];
  summary: { rounds_played: number; moves: string[]; total_reactions: number };
}

export interface WarRoom {
  id: string;
  title: string;
  owner_user_id: string | null;
  scenario_question: string | null;
  primary_entity_type: string | null;
  primary_entity_id: string | null;
  primary_entity_name: string | null;
  source_signal_id: string | null;
  game_phase: GamePhase;
  status: 'draft' | 'active' | 'closed';
  mode?: WarRoomMode;                             // IX04a — guided default
  mode_changed_at?: string | null;
  archived_at: string | null;                     // Phase B
  created_at: string | null;
  updated_at: string | null;
  rounds?: WarRoomRound[];
  comments?: WarRoomComment[];                    // Phase B (in detail)
}

export interface WarRoomComment {
  id: string;
  war_room_id: string;
  round_id: string | null;
  author_user_id: string | null;
  author_display_name: string;
  body: string;
  created_at: string | null;
  edited_at: string | null;
}

export interface WarRoomListFilters {
  status?: 'active' | 'closed';
  archived?: boolean;
  q?: string;
  entity_id?: string;
}

export const warRoomApi = {
  create: (body: {
    title: string;
    scenario_question?: string;
    primary_entity_type?: string;
    primary_entity_id?: string;
    primary_entity_name?: string;
    source_signal_id?: string;
    game_phase?: GamePhase;
  }): Promise<WarRoom> =>
    fetch(`${BASE}/war-rooms`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify(body),
    }).then(async (r) => {
      if (!r.ok) throw new Error(`${r.status}: ${await r.text().catch(() => r.statusText)}`);
      return r.json();
    }),

  list: (filters: WarRoomListFilters = {}): Promise<{ war_rooms: WarRoom[] }> => {
    const qs = new URLSearchParams();
    if (filters.status) qs.set('status', filters.status);
    if (filters.archived !== undefined) qs.set('archived', String(filters.archived));
    if (filters.q) qs.set('q', filters.q);
    if (filters.entity_id) qs.set('entity_id', filters.entity_id);
    const tail = qs.toString() ? `?${qs.toString()}` : '';
    return fetch(`${BASE}/war-rooms${tail}`, { headers: { ...authHeaders() } }).then(async (r) => {
      if (!r.ok) throw new Error(`${r.status}: ${await r.text().catch(() => r.statusText)}`);
      return r.json();
    });
  },

  patch: (id: string, body: {
    title?: string;
    scenario_question?: string;
    status?: 'active' | 'closed';
    archived?: boolean;
  }): Promise<WarRoom> =>
    fetch(`${BASE}/war-rooms/${encodeURIComponent(id)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify(body),
    }).then(async (r) => {
      if (!r.ok) throw new Error(`${r.status}: ${await r.text().catch(() => r.statusText)}`);
      return r.json();
    }),

  // IX04a — switch the room's scenario mode (owner-only, idempotent).
  setMode: (id: string, mode: WarRoomMode): Promise<{
    war_room_id: string; mode: WarRoomMode; round_count: number; mode_changed_at: string | null;
  }> =>
    fetch(`${BASE}/war-rooms/${encodeURIComponent(id)}/mode`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ mode }),
    }).then(async (r) => {
      if (!r.ok) throw new Error(`${r.status}: ${await r.text().catch(() => r.statusText)}`);
      return r.json();
    }),

  // PB-H13 — run an autonomous N-round campaign (owner-only). Ephemeral
  // transcript; adversary reactions are DB-grounded server-side.
  runAutonomous: (id: string, body: { rounds?: number; our_moves?: string[]; player_company_name?: string } = {}): Promise<AutoplayResult> =>
    fetch(`${BASE}/war-rooms/${encodeURIComponent(id)}/run-autonomous`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify(body),
    }).then(async (r) => {
      if (!r.ok) throw new Error(`${r.status}: ${await r.text().catch(() => r.statusText)}`);
      return r.json();
    }),

  listComments: (id: string, roundId?: string):
    Promise<{ war_room_id: string; comments: WarRoomComment[]; count: number }> => {
    const tail = roundId ? `?round_id=${encodeURIComponent(roundId)}` : '';
    return fetch(`${BASE}/war-rooms/${encodeURIComponent(id)}/comments${tail}`).then(async (r) => {
      if (!r.ok) throw new Error(`${r.status}: ${await r.text().catch(() => r.statusText)}`);
      return r.json();
    });
  },

  createComment: (id: string, body: { body: string; round_id?: string }):
    Promise<WarRoomComment> =>
    fetch(`${BASE}/war-rooms/${encodeURIComponent(id)}/comments`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify(body),
    }).then(async (r) => {
      if (!r.ok) throw new Error(`${r.status}: ${await r.text().catch(() => r.statusText)}`);
      return r.json();
    }),

  patchComment: (id: string, commentId: string, body: { body: string }):
    Promise<WarRoomComment> =>
    fetch(`${BASE}/war-rooms/${encodeURIComponent(id)}/comments/${encodeURIComponent(commentId)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify(body),
    }).then(async (r) => {
      if (!r.ok) throw new Error(`${r.status}: ${await r.text().catch(() => r.statusText)}`);
      return r.json();
    }),

  deleteComment: (id: string, commentId: string): Promise<void> =>
    fetch(`${BASE}/war-rooms/${encodeURIComponent(id)}/comments/${encodeURIComponent(commentId)}`, {
      method: 'DELETE',
      headers: { ...authHeaders() },
    }).then(async (r) => {
      if (!r.ok && r.status !== 204) {
        throw new Error(`${r.status}: ${await r.text().catch(() => r.statusText)}`);
      }
    }),

  detail: (id: string): Promise<WarRoom> =>
    fetch(`${BASE}/war-rooms/${encodeURIComponent(id)}`).then((r) => {
      if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
      return r.json();
    }),

  submitRound: (id: string, body: {
    move_type: MoveType;
    move_payload?: Record<string, unknown>;
    notes?: string;
    player_company_id?: string;
    player_company_name?: string;
  }): Promise<WarRoomRound> =>
    fetch(`${BASE}/war-rooms/${encodeURIComponent(id)}/rounds`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify(body),
    }).then(async (r) => {
      if (!r.ok) throw new Error(`${r.status}: ${await r.text().catch(() => r.statusText)}`);
      return r.json();
    }),

  remove: (id: string): Promise<void> =>
    fetch(`${BASE}/war-rooms/${encodeURIComponent(id)}`, {
      method: 'DELETE',
      headers: { ...authHeaders() },
    }).then(async (r) => {
      if (!r.ok && r.status !== 204) {
        throw new Error(`${r.status}: ${await r.text().catch(() => r.statusText)}`);
      }
    }),

  suggestMoves: (id: string, body: { n?: number; signal_context?: Record<string, unknown> } = {}):
    Promise<{ war_room_id: string; suggestions: MoveSuggestion[]; count: number; rule_version_id: string }> =>
    fetch(`${BASE}/war-rooms/${encodeURIComponent(id)}/suggest-moves`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify(body),
    }).then(async (r) => {
      if (!r.ok) throw new Error(`${r.status}: ${await r.text().catch(() => r.statusText)}`);
      return r.json();
    }),
};

// ────────────────────────────────────────────────────────────────────
// SPEC-021 Phase E — Inbox aggregator + DecisionDetail bundle
// ────────────────────────────────────────────────────────────────────

export interface InboxProposal {
  proposal_id: string;
  decision_id: string;
  decision_title: string;
  decision_status: string;
  matched_signal_id: string;
  signal_headline: string | null;
  signal_summary: string | null;
  signal_kbq_tags: string[];
  signal_entity: string | null;
  match_score: number;
  match_components: { entity_overlap: number; kbq_overlap: number; temporal_proximity: number };
  proposed_at: string | null;
}

export interface InboxOverdue {
  id: string;
  title: string;
  deadline: string | null;
  days_overdue: number | null;
  status: string;
  war_room_id: string | null;
  target_metric: string | null;
  target_value: string | null;
  confidence_at_commit: number | null;
}

export interface InboxHighImpactSignal {
  id: string;
  headline: string;
  summary: string | null;
  kbq_tags: string[];
  primary_entity_id: string | null;
  primary_entity_type: string | null;
  primary_entity_name: string | null;
  impact_tier: string | null;
  trust_score: number | null;
  created_at: string | null;
}

export interface InboxCalibrationSummary {
  last_30d_mean: number | null;
  verified_count: number;
  missed_count: number;
  total: number;
}

export interface InboxResponse {
  pending_proposals: InboxProposal[];
  overdue_decisions: InboxOverdue[];
  high_impact_signals: InboxHighImpactSignal[];
  calibration_summary: InboxCalibrationSummary;
}

export const inboxApi = {
  get: (): Promise<InboxResponse> =>
    fetch(`${BASE}/inbox`, { headers: { ...authHeaders() } }).then(async (r) => {
      if (!r.ok) throw new Error(`${r.status}: ${await r.text().catch(() => r.statusText)}`);
      return r.json();
    }),
};

export interface InsightsCalibrationBucket {
  month: string;
  total: number;
  mean_score: number | null;
  verified: number;
  missed: number;
}

export interface InsightsOutcomeEvent {
  event_type: 'capture' | 'proposal';
  decision_id: string | null;
  decision_title: string | null;
  decision_status: string | null;
  detail_text: string | null;
  detail_score: number | null;
  proposal_id: string | null;
  signal_id: string | null;
  signal_headline: string | null;
  event_at: string | null;
}

export interface InsightsResponse {
  calibration_trend: InsightsCalibrationBucket[];
  outcome_stream: InsightsOutcomeEvent[];
  summary: InboxCalibrationSummary;
}

export const insightsApi = {
  get: (): Promise<InsightsResponse> =>
    fetch(`${BASE}/insights`, { headers: { ...authHeaders() } }).then(async (r) => {
      if (!r.ok) throw new Error(`${r.status}: ${await r.text().catch(() => r.statusText)}`);
      return r.json();
    }),
};

export interface DecisionFullBundle extends Decision {
  war_room: {
    id: string;
    title: string;
    primary_entity_name: string | null;
    primary_entity_id: string | null;
    primary_entity_type: string | null;
    source_signal_id: string | null;
    status: string;
    archived_at: string | null;
  } | null;
  source_signal: {
    id: string;
    headline: string;
    summary: string | null;
    kbq_tags: string[];
    primary_entity_name: string | null;
    confidence_tier: string | null;
    impact_tier: string | null;
    created_at: string | null;
  } | null;
  comments: WarRoomComment[];
  pending_proposals: Array<{
    id: string;
    matched_signal_id: string;
    match_score: number;
    match_components: { entity_overlap: number; kbq_overlap: number; temporal_proximity: number };
    proposed_at: string | null;
    signal_headline: string | null;
    signal_summary: string | null;
    signal_kbq_tags: string[];
    signal_entity: string | null;
  }>;
}


// ────────────────────────────────────────────────────────────────────
// SPEC-021 Phase C — Decision Ledger
// ────────────────────────────────────────────────────────────────────

export type DecisionStatus = 'open' | 'in_progress' | 'verified' | 'missed' | 'cancelled';

export interface Decision {
  id: string;
  war_room_round_id: string | null;
  war_room_id: string | null;
  source_signal_id: string | null;
  title: string;
  rationale: string | null;
  move_type: MoveType;
  move_payload_snapshot: Record<string, unknown>;
  owner_user_id: string | null;
  owner_display_name: string;
  target_metric: string | null;
  target_value: string | null;
  deadline: string | null;
  confidence_at_commit: number | null;
  status: DecisionStatus;
  actual_outcome: string | null;
  actual_outcome_recorded_at: string | null;
  calibration_score: number | null;
  notes: string | null;
  created_at: string | null;
  updated_at: string | null;
  // Computed at read time
  overdue: boolean;
  days_to_deadline: number | null;
}

export interface DecisionListFilters {
  status?: DecisionStatus;
  war_room_id?: string;
  overdue?: boolean;
}

export const decisionsApi = {
  promoteRound: (roundId: string, body: {
    title: string;
    rationale?: string;
    target_metric?: string;
    target_value?: string;
    deadline?: string;
    owner_display_name?: string;
  }): Promise<Decision> =>
    fetch(`${BASE}/decisions/from-round/${encodeURIComponent(roundId)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify(body),
    }).then(async (r) => {
      if (!r.ok) throw new Error(`${r.status}: ${await r.text().catch(() => r.statusText)}`);
      return r.json();
    }),

  list: (filters: DecisionListFilters = {}): Promise<{ decisions: Decision[] }> => {
    const qs = new URLSearchParams();
    if (filters.status) qs.set('status', filters.status);
    if (filters.war_room_id) qs.set('war_room_id', filters.war_room_id);
    if (filters.overdue !== undefined) qs.set('overdue', String(filters.overdue));
    const tail = qs.toString() ? `?${qs.toString()}` : '';
    return fetch(`${BASE}/decisions${tail}`, { headers: { ...authHeaders() } }).then(async (r) => {
      if (!r.ok) throw new Error(`${r.status}: ${await r.text().catch(() => r.statusText)}`);
      return r.json();
    });
  },

  detail: (id: string): Promise<Decision> =>
    fetch(`${BASE}/decisions/${encodeURIComponent(id)}`).then((r) => {
      if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
      return r.json();
    }),

  patch: (id: string, body: {
    status?: DecisionStatus;
    notes?: string;
    deadline?: string;        // empty string clears
    target_metric?: string;
    target_value?: string;
    actual_outcome?: string;
  }): Promise<Decision> =>
    fetch(`${BASE}/decisions/${encodeURIComponent(id)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify(body),
    }).then(async (r) => {
      if (!r.ok) throw new Error(`${r.status}: ${await r.text().catch(() => r.statusText)}`);
      return r.json();
    }),

  remove: (id: string): Promise<void> =>
    fetch(`${BASE}/decisions/${encodeURIComponent(id)}`, {
      method: 'DELETE',
      headers: { ...authHeaders() },
    }).then(async (r) => {
      if (!r.ok && r.status !== 204) {
        throw new Error(`${r.status}: ${await r.text().catch(() => r.statusText)}`);
      }
    }),

  // Phase E — single-call detail bundle
  detailFull: (id: string): Promise<DecisionFullBundle> =>
    fetch(`${BASE}/decisions/${encodeURIComponent(id)}/full`).then((r) => {
      if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
      return r.json();
    }),

  // Phase D2 — outcome proposal confirm/dismiss
  confirmProposal: (decisionId: string, proposalId: string, body?: {
    actual_outcome?: string;
    verdict?: 'verified' | 'missed' | 'cancelled';
    notes?: string;
  }): Promise<Decision> =>
    fetch(`${BASE}/decisions/${encodeURIComponent(decisionId)}/proposals/${encodeURIComponent(proposalId)}/confirm`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify(body || {}),
    }).then(async (r) => {
      if (!r.ok) throw new Error(`${r.status}: ${await r.text().catch(() => r.statusText)}`);
      return r.json();
    }),

  dismissProposal: (decisionId: string, proposalId: string): Promise<void> =>
    fetch(`${BASE}/decisions/${encodeURIComponent(decisionId)}/proposals/${encodeURIComponent(proposalId)}/dismiss`, {
      method: 'POST',
      headers: { ...authHeaders() },
    }).then(async (r) => {
      if (!r.ok && r.status !== 204) {
        throw new Error(`${r.status}: ${await r.text().catch(() => r.statusText)}`);
      }
    }),

  // Phase D MVP — outcome detection + capture
  suggestOutcome: (id: string):
    Promise<{ decision_id: string; rule_version_id: string; candidates: OutcomeCandidate[]; count: number }> =>
    fetch(`${BASE}/decisions/${encodeURIComponent(id)}/suggest-outcome`, {
      method: 'POST',
      headers: { ...authHeaders() },
    }).then(async (r) => {
      if (!r.ok) throw new Error(`${r.status}: ${await r.text().catch(() => r.statusText)}`);
      return r.json();
    }),

  captureOutcome: (id: string, body: {
    signal_id: string;
    verdict: 'verified' | 'missed' | 'cancelled';
    actual_outcome: string;
    notes?: string;
  }): Promise<Decision> =>
    fetch(`${BASE}/decisions/${encodeURIComponent(id)}/capture-outcome`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify(body),
    }).then(async (r) => {
      if (!r.ok) throw new Error(`${r.status}: ${await r.text().catch(() => r.statusText)}`);
      return r.json();
    }),
};

export interface OutcomeCandidate {
  signal_id: string;
  headline: string;
  summary: string | null;
  kbq_tags: string[];
  created_at: string;
  primary_entity_name: string | null;
  primary_entity_id: string | null;
  rule_version_id: string;
  confidence_tier: string | null;
  trust_score: number | null;
  impact_tier: string | null;
  match_score: number;
  match_components: {
    entity_overlap: number;
    kbq_overlap: number;
    temporal_proximity: number;
  };
}

export interface MoveSuggestion {
  move_type: MoveType;
  move_payload: Record<string, string>;
  rationale: string;
  expected_impact_score: number;       // 0..1
  confidence_score: number;            // 0..1
  confidence: 'high' | 'medium' | 'low';
  evidence_basis: string[];
  stripped_citations: string[];
  evidence_validated: boolean;
}

export const MOVE_TYPE_META: Record<MoveType, { label: string; icon: string; desc: string; fields: string[] }> = {
  price_cut:          { label: 'Price Cut',            icon: '💵', desc: 'Reduce list/net price on a product',         fields: ['target_drug', 'discount_pct', 'geography', 'timing'] },
  new_indication:     { label: 'New Indication',       icon: '🎯', desc: 'Pursue a new indication approval',           fields: ['target_drug', 'indication', 'phase', 'timing'] },
  label_expansion:    { label: 'Label Expansion',      icon: '📋', desc: 'Expand existing label',                      fields: ['target_drug', 'expansion', 'evidence_source', 'timing'] },
  trial_readout:      { label: 'Pivotal Trial Readout',icon: '📊', desc: 'Announce Phase 3 results',                   fields: ['target_drug', 'trial_id', 'endpoint', 'timing'] },
  acquisition:        { label: 'Acquisition',          icon: '🤝', desc: 'M&A or in-licensing',                        fields: ['asset', 'deal_size', 'indication', 'timing'] },
  formulation_switch: { label: 'Formulation Switch',   icon: '💊', desc: 'Launch new formulation',                     fields: ['target_drug', 'new_formulation', 'advantage', 'timing'] },
  geo_expansion:      { label: 'Geographic Expansion', icon: '🌍', desc: 'Enter new geography',                        fields: ['target_drug', 'region', 'approach', 'timing'] },
  segment_pivot:      { label: 'Segment Pivot',        icon: '🎯', desc: 'Shift between patient segments',             fields: ['target_drug', 'from_segment', 'to_segment', 'timing'] },
};

export const REACTION_TYPE_META: Record<ReactionType, { label: string; color: string }> = {
  match_price:        { label: 'Match Price',          color: '#F59E0B' },
  counter_launch:     { label: 'Counter-Launch',       color: '#DC2626' },
  accelerate_trial:   { label: 'Accelerate Trial',     color: '#7C3AED' },
  seek_partnership:   { label: 'Seek Partnership',     color: '#16A34A' },
  attack_label:       { label: 'Attack Label',         color: '#B91C1C' },
  hold_position:      { label: 'Hold Position',        color: '#71717A' },
  exit_segment:       { label: 'Exit Segment',         color: '#52525B' },
  differentiate:      { label: 'Differentiate',        color: '#2563EB' },
};

// ────────────────────────────────────────────────────────────────────
// SPEC-023 — Decision Briefs (consumed by SPEC-030 Decision Workspace v2)
// ────────────────────────────────────────────────────────────────────

export type BriefState =
  | 'draft'
  | 'human_review'
  | 'simulation_pending'
  | 'simulation_complete'
  | 'decision_pending'
  | 'committed'
  | 'in_review'
  | 'closed';

export type TriggerKind = 'manual' | 'threshold' | 'cluster' | 'calendar';

export type EvidenceRefType = 'kbq_view' | 'signal' | 'entity' | 'document';

export interface EvidenceRef {
  type: EvidenceRefType;
  id: string;
  snapshot_at?: string;
}

export interface DecisionBriefOption {
  option_id: string;
  brief_id: string;
  ordinal: number;
  label: string;
  description: string | null;
  predicted_outcome: string | null;
  cost_estimate: string | null;
  risk_notes: string | null;
  created_at: string;
}

export interface BriefStateLogEntry {
  log_id: string;
  brief_id: string;
  from_state: string | null;
  to_state: BriefState;
  actor_user_id: string | null;
  reason: string | null;
  transitioned_at: string;
}

export interface DecisionBrief {
  brief_id: string;
  question: string;
  trigger_kind: TriggerKind;
  trigger_signal_ids: string[];
  trigger_metadata: Record<string, unknown>;
  stakeholders: string[];
  time_horizon_days: number | null;
  evidence_refs: EvidenceRef[];
  constraints: string[];
  success_criteria: string | null;
  confidence_to_proceed: number | null;
  state: BriefState;
  owner_user_id: string | null;
  war_room_id: string | null;
  decision_id: string | null;
  archived_at: string | null;
  created_at: string;
  updated_at: string;
  options: DecisionBriefOption[];
  state_log: BriefStateLogEntry[];
}

export interface DecisionBriefListFilters {
  state?: BriefState;
  owner_user_id?: string;
  trigger_kind?: TriggerKind;
  cursor?: string;
  limit?: number;
}

export interface DecisionBriefList {
  briefs: DecisionBrief[];
  next_cursor: string | null;
  count: number;
}

export type DecisionBriefCreateBody = Partial<
  Pick<
    DecisionBrief,
    | 'trigger_kind'
    | 'trigger_signal_ids'
    | 'trigger_metadata'
    | 'stakeholders'
    | 'time_horizon_days'
    | 'evidence_refs'
    | 'constraints'
    | 'success_criteria'
    | 'confidence_to_proceed'
    | 'war_room_id'
  >
> & { question: string };

export type DecisionBriefPatchBody = Partial<
  Pick<
    DecisionBrief,
    | 'question'
    | 'stakeholders'
    | 'time_horizon_days'
    | 'evidence_refs'
    | 'constraints'
    | 'success_criteria'
    | 'confidence_to_proceed'
  >
>;

export type DecisionBriefOptionInput = Pick<
  DecisionBriefOption,
  'label' | 'description' | 'predicted_outcome' | 'cost_estimate' | 'risk_notes'
>;

/**
 * Unwrap a JSON response, throwing on any non-2xx status.
 *
 * NOTE (2026-08-19): the former "hard session-expiry on 401" behaviour (clear token + role,
 * dispatch `mz:auth-expired`, redirect to login) was REMOVED at the owner's request — it bounced
 * anonymous/demo-token visitors across the whole app on a single protected 401. A 401 is now an
 * ordinary error handled locally by each surface. `App.tsx` still listens for `mz:auth-expired`,
 * so restoring the 401 branch below re-enables the old flow if it is ever wanted again.
 */
async function expectJson<T>(r: Response): Promise<T> {
  if (!r.ok) {
    // Hard session-expiry on 401 is DISABLED for now (owner request, 2026-08-19). A 401 no
    // longer clears the stored token, dispatches `mz:auth-expired`, or forces a redirect to the
    // landing page. It is surfaced as an ordinary error so each surface degrades locally (empty
    // state / its own auth-prompt) instead of bouncing the whole app — anonymous visitors and
    // demo-token sessions browse smoothly, with no redirect loop. App.tsx still listens for
    // `mz:auth-expired`, so restoring the old 401 branch here re-enables the behavior.
    const text = await r.text().catch(() => r.statusText);
    throw new Error(`${r.status}: ${text}`);
  }
  return r.json();
}

export const decisionBriefsApi = {
  list: (filters: DecisionBriefListFilters = {}): Promise<DecisionBriefList> => {
    const qs = new URLSearchParams();
    if (filters.state) qs.set('state', filters.state);
    if (filters.owner_user_id) qs.set('owner_user_id', filters.owner_user_id);
    if (filters.trigger_kind) qs.set('trigger_kind', filters.trigger_kind);
    if (filters.cursor) qs.set('cursor', filters.cursor);
    if (filters.limit !== undefined) qs.set('limit', String(filters.limit));
    const url = qs.toString() ? `${BASE}/decision-briefs?${qs}` : `${BASE}/decision-briefs`;
    return fetch(url, { headers: { ...authHeaders() } }).then((r) => expectJson<DecisionBriefList>(r));
  },

  get: (briefId: string): Promise<DecisionBrief> =>
    fetch(`${BASE}/decision-briefs/${encodeURIComponent(briefId)}`, {
      headers: { ...authHeaders() },
    }).then((r) => expectJson<DecisionBrief>(r)),

  create: (body: DecisionBriefCreateBody): Promise<DecisionBrief> =>
    fetch(`${BASE}/decision-briefs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify(body),
    }).then((r) => expectJson<DecisionBrief>(r)),

  patch: (briefId: string, patch: DecisionBriefPatchBody): Promise<DecisionBrief> =>
    fetch(`${BASE}/decision-briefs/${encodeURIComponent(briefId)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify(patch),
    }).then((r) => expectJson<DecisionBrief>(r)),

  archive: (briefId: string): Promise<{ ok: true }> =>
    fetch(`${BASE}/decision-briefs/${encodeURIComponent(briefId)}`, {
      method: 'DELETE',
      headers: { ...authHeaders() },
    }).then((r) => expectJson<{ ok: true }>(r)),

  addOption: (briefId: string, opt: DecisionBriefOptionInput): Promise<DecisionBriefOption> =>
    fetch(`${BASE}/decision-briefs/${encodeURIComponent(briefId)}/options`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify(opt),
    }).then((r) => expectJson<DecisionBriefOption>(r)),

  removeOption: (briefId: string, optionId: string): Promise<{ ok: true }> =>
    fetch(
      `${BASE}/decision-briefs/${encodeURIComponent(briefId)}/options/${encodeURIComponent(optionId)}`,
      { method: 'DELETE', headers: { ...authHeaders() } },
    ).then(async (r) => {
      if (r.status === 204) return { ok: true } as const;
      return expectJson<{ ok: true }>(r);
    }),

  transition: (briefId: string, toState: BriefState, reason?: string): Promise<DecisionBrief> => {
    const body: { to_state: BriefState; reason?: string } = { to_state: toState };
    if (reason !== undefined) body.reason = reason;
    return fetch(`${BASE}/decision-briefs/${encodeURIComponent(briefId)}/transitions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify(body),
    }).then((r) => expectJson<DecisionBrief>(r));
  },
};

// ─── SPEC_041 — User Feedback Loop ──────────────────────────────────

export type FeedbackCategory =
  | 'bug'
  | 'issue'
  | 'enhancement'
  | 'feature'
  | 'data_quality'
  | 'data_request';

export type FeedbackPriority = 'low' | 'medium' | 'high' | 'critical';

export type FeedbackStatus =
  | 'new'
  | 'triaged'
  | 'in_progress'
  | 'resolved'
  | 'rejected';

export interface FeedbackAttachment {
  data: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
}

export interface FeedbackDiagnosticContext {
  errors: Array<{ ts: string; message: string; stack?: string }>;
  failed_requests: Array<{
    ts: string;
    method: string;
    url: string;
    status?: number;
    body?: string;
  }>;
  user_agent: string;
  viewport: { w: number; h: number };
  theme: 'light' | 'dark';
  density?: 'spacious' | 'compact';
  route: string;
}

export interface FeedbackEntityContext {
  brief_id?: string;
  signal_id?: string;
  decision_id?: string;
  entity_type?: string;
  entity_id?: string;
  war_room_id?: string;
}

export interface FeedbackCreateBody {
  category: FeedbackCategory;
  title: string;
  description?: string;
  priority?: FeedbackPriority;
  page_url?: string;
  user_id?: string;
  session_id?: string;
  entity_context?: FeedbackEntityContext;
  diagnostic_context?: FeedbackDiagnosticContext;
  attachments?: FeedbackAttachment[];
}

export interface FeedbackEntry {
  id: string;
  category: FeedbackCategory;
  title: string;
  description?: string;
  priority: FeedbackPriority;
  status: FeedbackStatus;
  resolution?: string;
  resolved_by?: string;
  page_url?: string;
  entity_context?: FeedbackEntityContext;
  diagnostic_context?: FeedbackDiagnosticContext;
  attachments: FeedbackAttachment[];
  steward_action_id?: string;
  created_at: string;
  updated_at: string;
}

export interface FeedbackListFilter {
  status?: FeedbackStatus;
  category?: FeedbackCategory;
  limit?: number;
  offset?: number;
}

export interface FeedbackListResponse {
  items: FeedbackEntry[];
  total: number;
  limit: number;
  offset: number;
}

export interface FeedbackStatsResponse {
  total: number;
  by_category: Record<string, number>;
  by_status: Record<string, number>;
  auto_resolved_by_steward: number;
}

export const feedbackApi = {
  submit: (body: FeedbackCreateBody): Promise<{ feedback: FeedbackEntry }> =>
    fetch(`${BASE}/feedback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify(body),
    }).then((r) => expectJson<{ feedback: FeedbackEntry }>(r)),

  list: (filter: FeedbackListFilter = {}): Promise<FeedbackListResponse> => {
    const qs = new URLSearchParams();
    if (filter.status) qs.set('status', filter.status);
    if (filter.category) qs.set('category', filter.category);
    if (filter.limit !== undefined) qs.set('limit', String(filter.limit));
    if (filter.offset !== undefined) qs.set('offset', String(filter.offset));
    const url = qs.toString() ? `${BASE}/feedback?${qs}` : `${BASE}/feedback`;
    return fetch(url, { headers: { ...authHeaders() } }).then((r) =>
      expectJson<FeedbackListResponse>(r),
    );
  },

  update: (
    id: string,
    patch: {
      status?: FeedbackStatus;
      priority?: FeedbackPriority;
      resolution?: string;
      resolved_by?: string;
    },
  ): Promise<{ feedback: FeedbackEntry }> =>
    fetch(`${BASE}/feedback/${encodeURIComponent(id)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify(patch),
    }).then((r) => expectJson<{ feedback: FeedbackEntry }>(r)),

  stats: (): Promise<FeedbackStatsResponse> =>
    fetch(`${BASE}/feedback/stats`, { headers: { ...authHeaders() } }).then((r) =>
      expectJson<FeedbackStatsResponse>(r),
    ),

  // SPEC_041 Stage 6 fix M4 — hard-delete for PII retraction.
  remove: (id: string): Promise<{ ok: true }> =>
    fetch(`${BASE}/feedback/${encodeURIComponent(id)}`, {
      method: 'DELETE',
      headers: { ...authHeaders() },
    }).then(async (r) => {
      if (r.status === 204) return { ok: true } as const;
      return expectJson<{ ok: true }>(r);
    }),
};

// ── Loop A / B — Engagements (v7 IA spine) ──────────────────────────

export interface EngagementDTO {
  id: string;
  name: string;
  asset: string;
  sponsor: string | null;
  situation: 'launch' | 'defense' | 'lcm';
  workshop_date: string | null;
  stage: 'brief' | 'sources' | 'dossier' | 'synthesis' | 'gaps' | 'scenarios' | 'workshop';
  status: 'draft' | 'active' | 'completed' | 'archived';
  scope: Record<string, unknown>;
  created_by: string;
  created_at: string;
  updated_at: string;
  tenant_scope: string | null;
}

export interface EngagementListResponse {
  engagements: EngagementDTO[];
  count: number;
}

export const engagementsApi = {
  list: (params: { status?: string; situation?: string; limit?: number } = {}):
    Promise<EngagementListResponse> => {
    const qsStr = qs(params as Record<string, unknown>);
    const url = `${BASE}/engagements${qsStr ? `?${qsStr}` : ''}`;
    return fetch(url, { headers: { ...authHeaders() } }).then(async (r) => {
      if (!r.ok) throw new Error(`${r.status}: ${await r.text().catch(() => r.statusText)}`);
      return r.json();
    });
  },

  get: (eid: string, includeBrief = false): Promise<EngagementDTO & { brief?: unknown }> => {
    const q = includeBrief ? '?include_brief=true' : '';
    return fetch(`${BASE}/engagements/${encodeURIComponent(eid)}${q}`, {
      headers: { ...authHeaders() },
    }).then(async (r) => {
      if (!r.ok) throw new Error(`${r.status}: ${await r.text().catch(() => r.statusText)}`);
      return r.json();
    });
  },

  create: (body: {
    name: string; asset: string; situation: string;
    sponsor?: string; scope?: Record<string, unknown>;
  }): Promise<EngagementDTO> =>
    fetch(`${BASE}/engagements`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify(body),
    }).then(async (r) => {
      if (!r.ok) throw new Error(`${r.status}: ${await r.text().catch(() => r.statusText)}`);
      return r.json();
    }),
};

// ── Dossier Knowledge Base (KB2) ──────────────────────────────────
// The persisted, versioned 8-domain dossier. `domains` is the exact shape
// EngagementDossierPage renders (see DomainView in that file).

export interface DossierFactDTO {
  id: string;
  claim: string;
  factClass: 'reference' | 'corporate' | 'signal' | 'inferred';
  sourceLabel: string;
  /** PB-E05: drill-through to the source record (present on most facts). */
  sourceUrl?: string;
}

export interface DossierDomainDTO {
  domain: string;
  priority: 'critical' | 'high' | 'medium';
  state: 'complete' | 'in_progress' | 'gap';
  /** PB-H05: per-domain evidence readiness, 0–1. */
  readiness?: number;
  facts: DossierFactDTO[];
}

export interface DossierSnapshotDTO {
  id: string | null;
  engagement_id: string;
  focal_asset: string;
  version: number | null;
  coverage_score: number;
  /** PB-H05: priority-weighted engagement readiness, 0–1. */
  readiness?: number;
  fact_count: number;
  domains: DossierDomainDTO[];
  assembled_by: string;
  assembled_at: string | null;
  /** L7: how the focal asset resolved (id|exact|alias|normalized|fuzzy|unresolved). */
  resolution?: string;
  /** L7: false when the asset wasn't found — an empty dossier because the name is
   * unknown, NOT because the entity has no data. The UI distinguishes the two. */
  resolved?: boolean;
}

export interface DossierVersionDTO {
  id: string | null;
  version: number | null;
  coverage_score: number;
  fact_count: number;
  assembled_by: string;
  assembled_at: string | null;
}

export interface DossierGapDTO {
  domain: string;
  priority: 'critical' | 'high' | 'medium';
  /** high | medium — derived from priority (benchmark gap importance). */
  importance: string;
  /** human-readable: what is missing. */
  text: string;
  /** how to fill it (domain-appropriate collection method). */
  method: string;
  /** true = some evidence but below threshold (only when include_thin). */
  thin?: boolean;
}

export interface DossierGapsDTO {
  gaps: DossierGapDTO[];
  coverage_score: number;
}

/** A 404 here means "no dossier assembled yet" — callers branch on it. */
export class DossierNotAssembled extends Error {}

export const dossierKbApi = {
  get: (eid: string): Promise<DossierSnapshotDTO> =>
    fetch(`${BASE}/engagements/${encodeURIComponent(eid)}/dossier`, {
      headers: { ...authHeaders() },
    }).then(async (r) => {
      if (r.status === 404) throw new DossierNotAssembled('no dossier assembled yet');
      if (!r.ok) throw new Error(`${r.status}: ${await r.text().catch(() => r.statusText)}`);
      return r.json();
    }),

  assemble: (eid: string): Promise<DossierSnapshotDTO> =>
    fetch(`${BASE}/engagements/${encodeURIComponent(eid)}/dossier/assemble`, {
      method: 'POST',
      headers: { ...authHeaders() },
    }).then(async (r) => {
      if (!r.ok) throw new Error(`${r.status}: ${await r.text().catch(() => r.statusText)}`);
      return r.json();
    }),

  versions: (eid: string): Promise<{ versions: DossierVersionDTO[]; count: number }> =>
    fetch(`${BASE}/engagements/${encodeURIComponent(eid)}/dossier/versions`, {
      headers: { ...authHeaders() },
    }).then(async (r) => {
      if (!r.ok) throw new Error(`${r.status}: ${await r.text().catch(() => r.statusText)}`);
      return r.json();
    }),

  gaps: (eid: string): Promise<DossierGapsDTO> =>
    fetch(`${BASE}/engagements/${encodeURIComponent(eid)}/dossier/gaps`, {
      headers: { ...authHeaders() },
    }).then(async (r) => {
      if (r.status === 404) throw new DossierNotAssembled('no dossier assembled yet');
      if (!r.ok) throw new Error(`${r.status}: ${await r.text().catch(() => r.statusText)}`);
      return r.json();
    }),
};

// ── Scenarios (PB-H09 / PB-UX04) ───────────────────────────────────
// First-class probabilistic futures derived from the dossier. GET returns
// `{scenarios: [], count: 0}` (not 404) when none are derived yet — the
// container treats an empty list as the "not-yet-derived" state.

export interface ScenariosResponse {
  scenarios: Scenario[];
  count: number;
}

export const scenariosApi = {
  get: (eid: string): Promise<ScenariosResponse> =>
    fetch(`${BASE}/engagements/${encodeURIComponent(eid)}/scenarios`, {
      headers: { ...authHeaders() },
    }).then(async (r) => {
      if (!r.ok) throw new Error(`${r.status}: ${await r.text().catch(() => r.statusText)}`);
      return r.json();
    }),

  /**
   * Derive + persist scenarios from the latest dossier (assembling one if
   * needed). `narrative=true` asks the backend to synthesise a grounded
   * decision_output per scenario (PB-H16) — a no-op when the LLM is unset.
   */
  assemble: (eid: string, narrative = true): Promise<ScenariosResponse> =>
    fetch(
      `${BASE}/engagements/${encodeURIComponent(eid)}/scenarios/assemble?narrative=${narrative}`,
      { method: 'POST', headers: { ...authHeaders() } },
    ).then(async (r) => {
      if (!r.ok) throw new Error(`${r.status}: ${await r.text().catch(() => r.statusText)}`);
      return r.json();
    }),
};

// ── Synthesis (PB-UX06) ─────────────────────────────────────────────
// Typed insights derived from the dossier + the rejected-candidate audit
// trail. GET returns empty lists (not 404) when synthesis hasn't run yet —
// the container treats empty insights+rejected as the "not-yet-derived" state.

export interface SynthesisResponse {
  insights: Insight[];
  rejectedInsights: RejectedInsight[];
  passRate: number;
  count: number;
}

export const synthesisApi = {
  get: (eid: string): Promise<SynthesisResponse> =>
    fetch(`${BASE}/engagements/${encodeURIComponent(eid)}/synthesis`, {
      headers: { ...authHeaders() },
    }).then(async (r) => {
      if (!r.ok) throw new Error(`${r.status}: ${await r.text().catch(() => r.statusText)}`);
      return r.json();
    }),

  /**
   * Derive + persist synthesis insights from the latest dossier (assembling
   * one if needed). Each candidate passes the synthesis-test gate; failures
   * are logged to the rejected-candidate audit trail.
   */
  assemble: (eid: string): Promise<SynthesisResponse> =>
    fetch(`${BASE}/engagements/${encodeURIComponent(eid)}/synthesis/assemble`, {
      method: 'POST', headers: { ...authHeaders() },
    }).then(async (r) => {
      if (!r.ok) throw new Error(`${r.status}: ${await r.text().catch(() => r.statusText)}`);
      return r.json();
    }),
};

// ── Sources (PB-UX07) ───────────────────────────────────────────────
// Per-engagement source coverage derived from the dossier snapshot. 404 →
// no dossier yet (DossierNotAssembled, same as the gaps endpoint).

export interface EngagementSourceRow {
  source: string;
  fact_count: number;
  domains: string[];
  classes: Record<string, number>;
}

export interface EngagementSourcesResponse {
  sources: EngagementSourceRow[];
  source_count: number;
  total_facts: number;
  coverage_score: number;
}

export const engagementSourcesApi = {
  get: (eid: string): Promise<EngagementSourcesResponse> =>
    fetch(`${BASE}/engagements/${encodeURIComponent(eid)}/sources`, {
      headers: { ...authHeaders() },
    }).then(async (r) => {
      if (r.status === 404) throw new DossierNotAssembled('no dossier assembled yet');
      if (!r.ok) throw new Error(`${r.status}: ${await r.text().catch(() => r.statusText)}`);
      return r.json();
    }),
};

// ── Standalone dossier (IX-3) ───────────────────────────────────────
// Build an 8-domain dossier for any asset without an engagement (ephemeral
// preview). Same snapshot shape as the engagement dossier.

export const dossierPreviewApi = {
  get: (asset: string): Promise<DossierSnapshotDTO> =>
    fetch(`${BASE}/dossier-preview?asset=${encodeURIComponent(asset)}`, {
      headers: { ...authHeaders() },
    }).then(async (r) => {
      if (!r.ok) throw new Error(`${r.status}: ${await r.text().catch(() => r.statusText)}`);
      return r.json();
    }),
};

// ── Brief (PB-UX-Brief) ─────────────────────────────────────────────
// The Business Context Brief (BCB) for an engagement. get() returns null when
// no brief exists yet (404) — authoring happens in the create-engagement flow.

export interface BCBStrategicDecision { statement: string; rationale: string; }
export interface BCBCompetitorThreat { entity_ref: string; threat_level: string; note: string; }

export interface BusinessContextBriefDTO {
  id: string;
  engagement_id: string;
  focal_asset: string;
  situation: string;
  strategic_decisions: BCBStrategicDecision[];
  competitive_set: BCBCompetitorThreat[];
  success_criteria: string[];
  constraints: string[];
  created_by: string;
  created_at: string | null;
  signed_off: boolean;
  signed_off_by: string | null;
  signed_off_at: string | null;
}

export const engagementBriefApi = {
  get: (eid: string): Promise<BusinessContextBriefDTO | null> =>
    fetch(`${BASE}/engagements/${encodeURIComponent(eid)}/brief`, {
      headers: { ...authHeaders() },
    }).then(async (r) => {
      if (r.status === 404) return null;     // no brief authored yet
      if (!r.ok) throw new Error(`${r.status}: ${await r.text().catch(() => r.statusText)}`);
      return r.json();
    }),
};

// ── Engagement activity timeline (UX11 / L12) ───────────────────────

export interface ActivityItem {
  at: string | null;
  actor: string | null;
  actor_kind: 'human' | 'system';
  kind: 'brief' | 'scenario' | 'insight' | 'gap' | 'dossier';
  summary: string;
  ref_type: string | null;
  ref_id: string | null;
}

export const engagementActivityApi = {
  list: (eid: string, limit = 60): Promise<ActivityItem[]> =>
    fetch(`${BASE}/engagements/${encodeURIComponent(eid)}/activity?limit=${limit}`, {
      headers: { ...authHeaders() },
    }).then(async (r) => {
      if (!r.ok) throw new Error(`${r.status}: ${await r.text().catch(() => r.statusText)}`);
      return (await r.json()).activity ?? [];
    }),
};

// ── Gap remediation persistence (PB-UX05b) ──────────────────────────

export interface GapRemediationDTO {
  gap_domain: string;
  remediation: string;
  note: string | null;
  created_by?: string;
  updated_at?: string | null;
}

export const gapRemediationApi = {
  list: (eid: string): Promise<Record<string, GapRemediationDTO>> =>
    fetch(`${BASE}/engagements/${encodeURIComponent(eid)}/gaps/remediations`, {
      headers: { ...authHeaders() },
    }).then(async (r) => {
      if (!r.ok) throw new Error(`${r.status}: ${await r.text().catch(() => r.statusText)}`);
      return (await r.json()).remediations ?? {};
    }),

  set: (eid: string, gapDomain: string, remediation: string, note?: string): Promise<GapRemediationDTO> =>
    fetch(`${BASE}/engagements/${encodeURIComponent(eid)}/gaps/${encodeURIComponent(gapDomain)}/remediation`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ remediation, note }),
    }).then(async (r) => {
      if (!r.ok) throw new Error(`${r.status}: ${await r.text().catch(() => r.statusText)}`);
      return r.json();
    }),
};

// ── Generic entity comments (PB-UX02) ───────────────────────────────

export interface EntityComment {
  id: string;
  target_type: string;
  target_id: string;
  author_user_id: string | null;
  author_display_name: string;
  body: string;
  mentions: string[];
  created_at: string | null;
  edited_at: string | null;
}

export const commentsApi = {
  list: (targetType: string, targetId: string): Promise<{ comments: EntityComment[]; count: number }> =>
    fetch(`${BASE}/comments?target_type=${encodeURIComponent(targetType)}&target_id=${encodeURIComponent(targetId)}`, {
      headers: { ...authHeaders() },
    }).then(async (r) => {
      if (!r.ok) throw new Error(`${r.status}: ${await r.text().catch(() => r.statusText)}`);
      return r.json();
    }),

  add: (targetType: string, targetId: string, body: string): Promise<EntityComment> =>
    fetch(`${BASE}/comments`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ target_type: targetType, target_id: targetId, body }),
    }).then(async (r) => {
      if (!r.ok) throw new Error(`${r.status}: ${await r.text().catch(() => r.statusText)}`);
      return r.json();
    }),
};

// ── Domain Forge (DF-1/DF-2) ────────────────────────────────────────
// The playable SME elicitation loop: fetch a grounded round, submit a
// constrained pick/rank, get a quality-gated score + whether the dimension was
// PROMOTED (consensus) or FLAGGED (proposal only). Mirrors the /forge contract
// in api/routes/forge.py exactly.

/** One candidate analytical dimension in a round's constrained option set. */
export interface ForgeRoundOption {
  key: string;
  label: string;
  routes: string[];
}

/** A real entity pair the round compares (from the drugs spine). */
export interface ForgeRoundEntity {
  entity_id: string;
  entity_type?: string;
  label: string;
}

export interface ForgeRoundPayload {
  entities: ForgeRoundEntity[];
  options: ForgeRoundOption[];
  instructions: string;
}

/** A persisted Domain Forge round (the prompt + its constrained option set). */
export interface ForgeRound {
  id: string;
  session_id: string;
  round_type: string;
  playbook_id: string;
  intent: string;
  prompt: string;
  payload: ForgeRoundPayload;
  status: 'open' | 'answered' | string;
  created_by: string | null;
  created_at: string | null;
  answered_at?: string | null;
}

/** The dimension the SME's top pick was forged into. */
export interface ForgeElicitedDimension {
  key: string;
  label: string;
  sub_question: string;
  routes: string[];
  required: boolean;
  weight: number;
}

export interface ForgeValidation {
  valid: boolean;
  errors: string[];
}

/** promoted = consensus met + valid → applied to a new playbook version;
 *  flagged = lone / dissenting / invalid → recorded as a proposal only. */
export type ForgeConsensusState = 'promoted' | 'flagged';

export interface ForgeConsensus {
  state: ForgeConsensusState;
  agree_count: number;
  threshold: number;
}

export interface ForgeScore {
  id?: string;
  eval_item_id?: string | null;
  session_id?: string;
  sme_id?: string | null;
  points: number;
  reason: string;
  created_at?: string | null;
}

export interface ForgeEvalItem {
  id: string;
  round_id: string | null;
  session_id: string;
  playbook_id: string;
  intent: string;
  prompt: string;
  answer: { selected?: string[]; ranking?: string[] };
  sme_id: string | null;
  validation: ForgeValidation;
  consensus_state: ForgeConsensusState;
  promoted_version: number | null;
  created_at: string | null;
}

/** The result of submitting an answer — the scored, gated outcome. */
export interface ForgeAnswerResult {
  round_id: string;
  dimension: ForgeElicitedDimension;
  validation: ForgeValidation;
  consensus: ForgeConsensus;
  playbook_version: number | null;
  eval_item: ForgeEvalItem;
  score: ForgeScore;
}

export interface ForgeSessionSummary {
  session_id: string;
  rounds: number;
  rounds_answered: number;
  eval_items: number;
  promoted: number;
  score: number;
}

export const forgeApi = {
  /** Generate a grounded "What matters?" round from real DB entities. */
  createRound: (
    sessionId: string,
    opts: { intent?: string; playbookId?: string; entities?: ForgeRoundEntity[] } = {},
  ): Promise<ForgeRound> =>
    fetch(`${BASE}/forge/rounds`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({
        session_id: sessionId,
        intent: opts.intent ?? 'compare',
        playbook_id: opts.playbookId ?? 'compare.drug_x_drug',
        entities: opts.entities ?? null,
      }),
    }).then(async (r) => {
      if (!r.ok) throw new Error(`${r.status}: ${await r.text().catch(() => r.statusText)}`);
      return r.json();
    }),

  getRound: (roundId: string): Promise<ForgeRound> =>
    fetch(`${BASE}/forge/rounds/${encodeURIComponent(roundId)}`, {
      headers: { ...authHeaders() },
    }).then(async (r) => {
      if (!r.ok) throw new Error(`${r.status}: ${await r.text().catch(() => r.statusText)}`);
      return r.json();
    }),

  /** Submit the SME's constrained answer. `ranking[0]` is the top pick. */
  submitAnswer: (
    roundId: string,
    answer: { selected: string[]; ranking: string[] },
    smeId?: string,
  ): Promise<ForgeAnswerResult> =>
    fetch(`${BASE}/forge/rounds/${encodeURIComponent(roundId)}/answer`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ selected: answer.selected, ranking: answer.ranking, sme_id: smeId ?? null }),
    }).then(async (r) => {
      if (!r.ok) throw new Error(`${r.status}: ${await r.text().catch(() => r.statusText)}`);
      return r.json();
    }),

  session: (sessionId: string): Promise<ForgeSessionSummary> =>
    fetch(`${BASE}/forge/sessions/${encodeURIComponent(sessionId)}`, {
      headers: { ...authHeaders() },
    }).then(async (r) => {
      if (!r.ok) throw new Error(`${r.status}: ${await r.text().catch(() => r.statusText)}`);
      return r.json();
    }),

  evalItems: (opts: { playbookId?: string; sessionId?: string } = {}): Promise<ForgeEvalItem[]> => {
    const q = new URLSearchParams();
    if (opts.playbookId) q.set('playbook_id', opts.playbookId);
    if (opts.sessionId) q.set('session_id', opts.sessionId);
    const qs = q.toString();
    return fetch(`${BASE}/forge/eval-items${qs ? `?${qs}` : ''}`, {
      headers: { ...authHeaders() },
    }).then(async (r) => {
      if (!r.ok) throw new Error(`${r.status}: ${await r.text().catch(() => r.statusText)}`);
      return (await r.json()).eval_items ?? [];
    });
  },
};

// ── Playbook authoring (DI-5) ───────────────────────────────────────
// CRUD + versioning + rollback over runtime-editable Answer Playbooks. The
// live forge play loop grows these; this surface browses + audits them.

export interface PlaybookRoute { kind: string; value: string; }

export interface PlaybookDimension {
  key: string;
  label: string;
  sub_question: string;
  /** Routes serialise as "kind:value" strings, e.g. "predicate:adverse_event". */
  routes: string[];
  required: boolean;
  weight: number;
}

export interface PlaybookDoc {
  id: string;
  pack: string;
  trigger: Record<string, unknown>;
  dimensions: PlaybookDimension[];
  synthesis: Record<string, unknown>;
}

export interface PlaybookMeta {
  version: number | null;
  author: string | null;
  active: boolean;
  tenant_scope?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

/** A playbook list entry: the doc + meta + whether it is DB-backed or seed. */
export interface PlaybookListItem {
  playbook: PlaybookDoc;
  meta: PlaybookMeta;
  source: 'db' | 'seed';
}

export interface PlaybookDetail {
  playbook: PlaybookDoc;
  meta: PlaybookMeta;
}

export interface PlaybookVersion {
  version: number;
  action: 'create' | 'update' | 'rollback' | 'delete' | string;
  snapshot: PlaybookDoc;
  diff: Record<string, { from: unknown; to: unknown }>;
  author: string | null;
  note: string | null;
  rolled_back_from: number | null;
  created_at: string | null;
}

export const playbooksApi = {
  list: (): Promise<PlaybookListItem[]> =>
    fetch(`${BASE}/playbooks`, { headers: { ...authHeaders() } }).then(async (r) => {
      if (!r.ok) throw new Error(`${r.status}: ${await r.text().catch(() => r.statusText)}`);
      return (await r.json()).playbooks ?? [];
    }),

  get: (playbookId: string): Promise<PlaybookDetail> =>
    fetch(`${BASE}/playbooks/${encodeURIComponent(playbookId)}`, {
      headers: { ...authHeaders() },
    }).then(async (r) => {
      if (!r.ok) throw new Error(`${r.status}: ${await r.text().catch(() => r.statusText)}`);
      return r.json();
    }),

  versions: (playbookId: string): Promise<PlaybookVersion[]> =>
    fetch(`${BASE}/playbooks/${encodeURIComponent(playbookId)}/versions`, {
      headers: { ...authHeaders() },
    }).then(async (r) => {
      if (!r.ok) throw new Error(`${r.status}: ${await r.text().catch(() => r.statusText)}`);
      return (await r.json()).versions ?? [];
    }),

  rollback: (playbookId: string, targetVersion: number, note?: string): Promise<PlaybookDetail> =>
    fetch(`${BASE}/playbooks/${encodeURIComponent(playbookId)}/rollback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ target_version: targetVersion, note: note ?? null }),
    }).then(async (r) => {
      if (!r.ok) throw new Error(`${r.status}: ${await r.text().catch(() => r.statusText)}`);
      return r.json();
    }),
};
