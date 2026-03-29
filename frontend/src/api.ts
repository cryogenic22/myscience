// In dev mode (vite dev server), proxy rewrites /api -> /
// In production (served from FastAPI), call routes directly
const BASE = import.meta.env.DEV ? '/api' : '';

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
  traverse: (entityType: string, entityId: string, hops?: number) =>
    get<{ nodes: GraphNode[]; edges: GraphEdge[] }>(
      `/graph/traverse/${entityType}/${encodeURIComponent(entityId)}?hops=${hops ?? 2}&max_nodes=50`
    ),
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
