# Anti-Slop Rules — DO NOT DUPLICATE Existing Utilities

*Auto-generated: 2026-03-22 12:45*
*Scanned: 710 exports across 23 directories*

**BEFORE creating any new function, class, or constant:**
1. Search this list for an existing implementation
2. If it exists, import it — do NOT create a new version
3. If you need a variant, extend the existing one

## Known Duplicates (40 — consolidate these)

- **`EvidenceItem`** — defined in: `frontend/src/api.ts`, `services/query_engine.py`
- **`GraphEdge`** — defined in: `frontend/src/api.ts`, `services/graph.py`
- **`GraphNode`** — defined in: `frontend/src/api.ts`, `services/graph.py`
- **`QualityResult`** — defined in: `frontend/src/api.ts`, `integration/data_quality.py`
- **`QueryResponse`** — defined in: `api/schemas.py`, `frontend/src/api.ts`
- **`SearchResult`** — defined in: `frontend/src/api.ts`, `services/search.py`
- **`SourceCoverageItem`** — defined in: `api/schemas.py`, `frontend/src/api.ts`
- **`__init__`** — defined in: `connectors/base.py`, `connectors/clinical_trials.py`, `connectors/enrichment_runner.py`, `connectors/fda_shortages.py`, `connectors/mesh.py`, `connectors/openfda_faers.py`, `connectors/openfda_labels.py`, `connectors/orange_book.py`, `connectors/pmc.py`, `connectors/pubmed.py`, `connectors/sec_edgar.py`, `db.py`, `integration/cross_linker.py`, `integration/data_quality.py`, `integration/dataset_catalog.py`, `integration/embedder.py`, `integration/entity_consolidator.py`, `integration/entity_resolver.py`, `integration/knowledge_store.py`, `integration/normalizer.py`, `integration/pipeline.py`, `integration/pipeline.py`, `integration/pipeline_hooks.py`, `integration/pipeline_hooks.py`, `integration/pipeline_hooks.py`, `integration/pipeline_hooks.py`, `integration/pipeline_hooks.py`, `integration/pipeline_hooks.py`, `integration/pipeline_hooks.py`, `integration/pipeline_hooks.py`, `integration/pipeline_hooks.py`, `integration/pipeline_hooks.py`, `scheduler/runner.py`, `services/agent/schema_introspector.py`, `services/agent/tools/graph_tool.py`, `services/agent/tools/metrics_tool.py`, `services/agent/tools/rag_tool.py`, `services/agent/tools/sql_tool.py`, `services/conversation_memory.py`, `services/ctx_context.py`, `services/ctx_corpus.py`, `services/ctx_pipeline.py`, `services/graph.py`, `services/llm.py`, `services/metrics.py`, `services/query_engine.py`, `services/research_agent.py`, `services/search.py`, `services/unified_handler.py`, `services/web_research.py`, `services/workspace.py`, `tests/conftest.py`, `tests/conftest.py`, `tests/conftest.py`
- **`__post_init__`** — defined in: `connectors/base.py`, `domain/ta_definitions/schema.py`
- **`call_count`** — defined in: `tests/conftest.py`, `tests/conftest.py`
- **`company_portfolio`** — defined in: `api/routes/metrics.py`, `services/metrics.py`
- **`competitive_landscape`** — defined in: `api/routes/metrics.py`, `services/metrics.py`
- **`create_research_job`** — defined in: `api/routes/chat.py`, `services/workspace.py`
- **`derive_competition`** — defined in: `api/routes/enrichment.py`, `scripts/derive_competition.py`
- **`enabled`** — defined in: `services/llm.py`, `services/web_research.py`
- **`entity_summary`** — defined in: `api/routes/graph.py`, `services/graph.py`
- **`evidence_density`** — defined in: `api/routes/metrics.py`, `services/metrics.py`
- **`execute`** — defined in: `db.py`, `integration/pipeline_hooks.py`, `integration/pipeline_hooks.py`, `integration/pipeline_hooks.py`, `integration/pipeline_hooks.py`, `integration/pipeline_hooks.py`, `integration/pipeline_hooks.py`, `integration/pipeline_hooks.py`, `integration/pipeline_hooks.py`, `integration/pipeline_hooks.py`, `services/agent/tools/base.py`, `services/agent/tools/graph_tool.py`, `services/agent/tools/metrics_tool.py`, `services/agent/tools/rag_tool.py`, `services/agent/tools/sql_tool.py`, `tests/conftest.py`, `tests/conftest.py`
- **`fetch`** — defined in: `connectors/base.py`, `connectors/clinical_trials.py`, `connectors/fda_shortages.py`, `connectors/mesh.py`, `connectors/openfda_faers.py`, `connectors/openfda_labels.py`, `connectors/orange_book.py`, `connectors/pmc.py`, `connectors/pubmed.py`, `connectors/sec_edgar.py`
- **`find_similar`** — defined in: `api/routes/search.py`, `services/search.py`
- **`get_entity`** — defined in: `api/mcp_server.py`, `api/routes/entities.py`
- **`get_metrics`** — defined in: `api/deps.py`, `api/mcp_server.py`
- **`get_research_job`** — defined in: `api/routes/chat.py`, `services/workspace.py`
- **`health_check`** — defined in: `connectors/base.py`, `connectors/clinical_trials.py`, `connectors/fda_shortages.py`, `connectors/mesh.py`, `connectors/openfda_faers.py`, `connectors/openfda_labels.py`, `connectors/orange_book.py`, `connectors/pmc.py`, `connectors/pubmed.py`, `connectors/sec_edgar.py`
- **`list_research_jobs`** — defined in: `api/routes/chat.py`, `services/workspace.py`
- **`main`** — defined in: `migrate.py`, `run_consolidation.py`, `scheduler/__main__.py`, `scripts/ai_enrich.py`, `scripts/auto_curate.py`, `scripts/backfill_mechanisms.py`, `scripts/backfill_ta_links.py`, `scripts/clean_drug_names.py`, `scripts/dedup_companies.py`, `scripts/derive_competition.py`, `scripts/enrich_companies.py`, `scripts/enrich_drugs.py`, `scripts/extract_biomarkers.py`, `scripts/onboard_ta.py`, `scripts/quality_scorecard.py`
- **`name`** — defined in: `services/agent/tools/base.py`, `services/agent/tools/graph_tool.py`, `services/agent/tools/metrics_tool.py`, `services/agent/tools/rag_tool.py`, `services/agent/tools/sql_tool.py`, `tests/conftest.py`, `tests/conftest.py`
- **`neighborhood`** — defined in: `api/routes/graph.py`, `services/graph.py`
- **`path_between`** — defined in: `api/routes/graph.py`, `services/graph.py`
- **`query`** — defined in: `api/routes/query.py`, `services/query_engine.py`
- **`refresh_materialized_views`** — defined in: `api/routes/catalog.py`, `fix_data_quality.py`
- **`register`** — defined in: `domain/registry.py`, `integration/pipeline_hooks.py`
- **`resolve`** — defined in: `integration/entity_resolver.py`, `integration/pipeline_hooks.py`
- **`run`** — defined in: `backfill_data_linkage.py`, `fix_data_quality.py`, `integration/entity_consolidator.py`, `integration/pipeline.py`, `scripts/ai_enrich.py`, `scripts/auto_curate.py`, `scripts/backfill_mechanisms.py`, `scripts/backfill_ta_links.py`, `scripts/clean_drug_names.py`, `scripts/dedup_companies.py`, `scripts/enrich_companies.py`, `scripts/enrich_drugs.py`, `scripts/extract_biomarkers.py`, `scripts/onboard_ta.py`, `scripts/quality_scorecard.py`
- **`run_enrichment`** — defined in: `api/routes/catalog.py`, `api/routes/enrichment.py`
- **`search`** — defined in: `api/routes/search.py`, `services/search.py`, `services/web_research.py`
- **`should_fire`** — defined in: `integration/pipeline_hooks.py`, `integration/pipeline_hooks.py`, `integration/pipeline_hooks.py`
- **`source_type`** — defined in: `connectors/base.py`, `connectors/clinical_trials.py`, `connectors/fda_shortages.py`, `connectors/mesh.py`, `connectors/openfda_faers.py`, `connectors/openfda_labels.py`, `connectors/orange_book.py`, `connectors/pmc.py`, `connectors/pubmed.py`, `connectors/sec_edgar.py`
- **`summary`** — defined in: `integration/pipeline.py`, `services/ctx_context.py`
- **`traverse`** — defined in: `api/routes/graph.py`, `services/graph.py`

## Shared Utilities (check these FIRST)

### `frontend/src/components/ui/`
| Name | Type | File:Line |
|------|------|-----------|
| `Drawer` | function | `frontend/src/components/ui/Drawer.tsx:13` |
| `Pill` | function | `frontend/src/components/ui/Pill.tsx:13` |

### `frontend/src/hooks/`
| Name | Type | File:Line |
|------|------|-----------|
| `PlatformStats` | type | `frontend/src/hooks/useHealthStats.ts:6` |
| `useAnimatedNumber` | function | `frontend/src/hooks/useAnimatedNumber.ts:3` |
| `useHealthStats` | function | `frontend/src/hooks/useHealthStats.ts:30` |
| `useTheme` | function | `frontend/src/hooks/useTheme.ts:14` |

### `services/`
| Name | Type | File:Line |
|------|------|-----------|
| `ABResult` | class | `services/ctx_context.py:73` |
| `AutonomousResearchAgent` | class | `services/research_agent.py:121` |
| `CTXContextBuilder` | class | `services/ctx_context.py:371` |
| `CTXQueryPipeline` | class | `services/ctx_pipeline.py:119` |
| `ChatWorkspaceService` | class | `services/workspace.py:14` |
| `ContextResult` | class | `services/ctx_context.py:61` |
| `ConversationMemory` | class | `services/conversation_memory.py:66` |
| `EnrichmentPlan` | class | `services/research_agent.py:50` |
| `EvalResult` | class | `services/research_agent.py:59` |
| `EvidenceItem` | class | `services/query_engine.py:29` |
| `GraphEdge` | class | `services/graph.py:33` |
| `GraphNode` | class | `services/graph.py:23` |
| `GraphTraversal` | class | `services/graph.py:66` |
| `HybridSearch` | class | `services/search.py:139` |
| `LLMSynthesizer` | class | `services/llm.py:241` |
| `LoopSummary` | class | `services/research_agent.py:70` |
| `PharmaCorpusBuilder` | class | `services/ctx_corpus.py:101` |
| `PharmaMetrics` | class | `services/metrics.py:30` |
| `QueryEngine` | class | `services/query_engine.py:59` |
| `QueryPlan` | class | `services/ctx_pipeline.py:42` |
| `QueryResult` | class | `services/query_engine.py:41` |
| `ReasoningResult` | class | `services/ctx_pipeline.py:72` |
| `ResearchTarget` | class | `services/research_agent.py:38` |
| `RetrievalResult` | class | `services/ctx_pipeline.py:52` |
| `SearchResult` | class | `services/search.py:24` |
| `Subgraph` | class | `services/graph.py:45` |
| `UnifiedChatHandler` | class | `services/unified_handler.py:22` |
| `WebResearchItem` | class | `services/web_research.py:16` |
| `WebResearchService` | class | `services/web_research.py:23` |
| `__init__` | function | `services/conversation_memory.py:79` |
| `__init__` | function | `services/ctx_context.py:380` |
| `__init__` | function | `services/ctx_corpus.py:104` |
| `__init__` | function | `services/ctx_pipeline.py:129` |
| `__init__` | function | `services/graph.py:69` |
| `__init__` | function | `services/llm.py:244` |
| `__init__` | function | `services/metrics.py:33` |
| `__init__` | function | `services/query_engine.py:62` |
| `__init__` | function | `services/research_agent.py:130` |
| `__init__` | function | `services/search.py:142` |
| `__init__` | function | `services/unified_handler.py:32` |
| `__init__` | function | `services/web_research.py:26` |
| `__init__` | function | `services/workspace.py:17` |
| `add_exchange` | function | `services/conversation_memory.py:86` |
| `available_sections` | function | `services/ctx_pipeline.py:167` |
| `build` | function | `services/ctx_context.py:386` |
| `build_corpus_dir` | function | `services/ctx_corpus.py:176` |
| `build_system_prompt` | function | `services/ctx_pipeline.py:425` |
| `check_response` | function | `services/ctx_pipeline.py:421` |
| `commit_or_revert` | function | `services/research_agent.py:361` |
| `company_portfolio` | function | `services/metrics.py:242` |
| `compare_entities` | function | `services/query_engine.py:285` |
| `competitive_landscape` | function | `services/metrics.py:182` |
| `complete_research_job` | function | `services/workspace.py:224` |
| `create_research_job` | function | `services/workspace.py:144` |
| `delete_session` | function | `services/workspace.py:131` |
| `drug_pipeline_strength` | function | `services/metrics.py:37` |
| `drugs_by_mechanism_class` | function | `services/graph.py:299` |
| `enabled` | function | `services/llm.py:249` |
| `enabled` | function | `services/web_research.py:30` |
| `entity_dossier` | function | `services/query_engine.py:191` |
| `entity_summary` | function | `services/graph.py:239` |
| `evaluate` | function | `services/research_agent.py:311` |
| `evidence_density` | function | `services/metrics.py:149` |
| `execute_enrichment` | function | `services/research_agent.py:275` |
| `export_companies` | function | `services/ctx_corpus.py:127` |
| `export_drugs` | function | `services/ctx_corpus.py:107` |
| `export_mechanisms` | function | `services/ctx_corpus.py:161` |
| `export_trials` | function | `services/ctx_corpus.py:143` |
| `fail_research_job` | function | `services/workspace.py:239` |
| `find_similar` | function | `services/search.py:250` |
| `from_dict` | function | `services/conversation_memory.py:44` |
| `get_context` | function | `services/conversation_memory.py:127` |
| `get_cumulative_stats` | function | `services/research_agent.py:428` |
| `get_entities_discussed` | function | `services/conversation_memory.py:175` |
| `get_research_job` | function | `services/workspace.py:188` |
| `get_session` | function | `services/workspace.py:108` |
| `handle` | function | `services/unified_handler.py:48` |
| `identify_target` | function | `services/research_agent.py:164` |
| `list_research_jobs` | function | `services/workspace.py:165` |
| `list_sessions` | function | `services/workspace.py:84` |
| `log_ctx_event` | function | `services/telemetry.py:16` |
| `log_iteration` | function | `services/research_agent.py:382` |
| `mark_research_job_running` | function | `services/workspace.py:212` |
| `mechanism_hierarchy` | function | `services/graph.py:319` |
| `neighborhood` | function | `services/graph.py:73` |
| `pack` | function | `services/ctx_corpus.py:258` |
| `pack_evidence` | function | `services/ctx_evidence.py:86` |
| `path_between` | function | `services/graph.py:131` |
| `persist_log` | function | `services/research_agent.py:411` |
| `plan_enrichment` | function | `services/research_agent.py:229` |
| `query` | function | `services/query_engine.py:76` |
| `reason` | function | `services/ctx_pipeline.py:354` |
| `refresh` | function | `services/metrics.py:279` |
| `render_context` | function | `services/ctx_pipeline.py:60` |
| `resolve_reference` | function | `services/conversation_memory.py:191` |
| `restore` | function | `services/conversation_memory.py:276` |
| `retrieve` | function | `services/ctx_pipeline.py:295` |
| `run_loop` | function | `services/research_agent.py:440` |
| `save_session` | function | `services/workspace.py:20` |
| `search` | function | `services/search.py:187` |
| `search` | function | `services/web_research.py:34` |
| `search_entity_type` | function | `services/search.py:288` |
| `search_paginated` | function | `services/search.py:208` |
| `snapshot` | function | `services/conversation_memory.py:262` |
| `summary` | function | `services/ctx_context.py:79` |
| `synthesize` | function | `services/llm.py:261` |
| `synthesize_comparison` | function | `services/llm.py:413` |
| `synthesize_dossier` | function | `services/llm.py:384` |
| `synthesize_landscape` | function | `services/llm.py:442` |
| `synthesize_pipeline` | function | `services/llm.py:456` |
| `synthesize_research_report` | function | `services/llm.py:472` |
| `synthesize_stream` | function | `services/llm.py:336` |
| `to_dict` | function | `services/conversation_memory.py:34` |
| `traverse` | function | `services/graph.py:77` |
| `trial_success_rate` | function | `services/metrics.py:103` |
| `understand` | function | `services/ctx_pipeline.py:173` |

### `services/agent/`
| Name | Type | File:Line |
|------|------|-----------|
| `JoinPath` | class | `services/agent/schema_introspector.py:19` |
| `SchemaIntrospector` | class | `services/agent/schema_introspector.py:26` |
| `__init__` | function | `services/agent/schema_introspector.py:29` |
| `get_agent_llm` | function | `services/agent/llm_provider.py:19` |
| `get_joinable_paths` | function | `services/agent/schema_introspector.py:119` |
| `get_schema_description` | function | `services/agent/schema_introspector.py:35` |
| `get_table_names` | function | `services/agent/schema_introspector.py:111` |
| `plan_presentation` | function | `services/agent/presenter.py:64` |
| `plan_team_eval_presentation` | function | `services/agent/presenter.py:253` |

### `services/agent/graphs/`
| Name | Type | File:Line |
|------|------|-----------|
| `PersonaInput` | class | `services/agent/graphs/team_eval_graph.py:43` |
| `QueryAgentState` | class | `services/agent/graphs/query_graph.py:39` |
| `TeamEvalState` | class | `services/agent/graphs/team_eval_graph.py:29` |
| `build_query_graph` | function | `services/agent/graphs/query_graph.py:536` |
| `build_team_eval_graph` | function | `services/agent/graphs/team_eval_graph.py:792` |
| `has_structured_signals` | function | `services/agent/graphs/query_graph.py:598` |

### `services/agent/tools/`
| Name | Type | File:Line |
|------|------|-----------|
| `BaseTool` | class | `services/agent/tools/base.py:58` |
| `GraphSearchTool` | class | `services/agent/tools/graph_tool.py:13` |
| `MetricsQueryTool` | class | `services/agent/tools/metrics_tool.py:13` |
| `RAGSearchTool` | class | `services/agent/tools/rag_tool.py:13` |
| `SQLQueryTool` | class | `services/agent/tools/sql_tool.py:30` |
| `ToolResult` | class | `services/agent/tools/base.py:11` |
| `__init__` | function | `services/agent/tools/graph_tool.py:16` |
| `__init__` | function | `services/agent/tools/metrics_tool.py:16` |
| `__init__` | function | `services/agent/tools/rag_tool.py:16` |
| `__init__` | function | `services/agent/tools/sql_tool.py:40` |
| `clamp_limit` | function | `services/agent/tools/sql_tool.py:170` |
| `execute` | function | `services/agent/tools/base.py:67` |
| `execute` | function | `services/agent/tools/graph_tool.py:23` |
| `execute` | function | `services/agent/tools/metrics_tool.py:23` |
| `execute` | function | `services/agent/tools/rag_tool.py:23` |
| `execute` | function | `services/agent/tools/sql_tool.py:49` |
| `has_date_column` | function | `services/agent/tools/base.py:49` |
| `has_numeric_column` | function | `services/agent/tools/base.py:37` |
| `is_scalar` | function | `services/agent/tools/base.py:23` |
| `name` | function | `services/agent/tools/base.py:63` |
| `name` | function | `services/agent/tools/graph_tool.py:20` |
| `name` | function | `services/agent/tools/metrics_tool.py:20` |
| `name` | function | `services/agent/tools/rag_tool.py:20` |
| `name` | function | `services/agent/tools/sql_tool.py:46` |
| `scalar_value` | function | `services/agent/tools/base.py:28` |

### `services/chat_handlers/`
| Name | Type | File:Line |
|------|------|-----------|
| `Intent` | class | `services/chat_handlers/intent.py:11` |
| `apply_chat_modes` | function | `services/chat_handlers/formatting.py:26` |
| `build_comparison_table` | function | `services/chat_handlers/formatting.py:262` |
| `build_conversation_context` | function | `services/chat_handlers/context.py:10` |
| `build_visualizations` | function | `services/chat_handlers/formatting.py:220` |
| `coerce_bool` | function | `services/chat_handlers/formatting.py:12` |
| `compute_comparison_insights` | function | `services/chat_handlers/formatting.py:176` |
| `detect_format_hint` | function | `services/chat_handlers/intent.py:38` |
| `detect_intent` | function | `services/chat_handlers/intent.py:48` |
| `expand_topic_synonyms` | function | `services/chat_handlers/formatting.py:167` |
| `generate_followups` | function | `services/chat_handlers/formatting.py:119` |
| `handle_compare` | function | `services/chat_handlers/handlers.py:708` |
| `handle_deep_research` | function | `services/chat_handlers/handlers.py:1105` |
| `handle_dossier` | function | `services/chat_handlers/handlers.py:473` |
| `handle_general` | function | `services/chat_handlers/handlers.py:1088` |
| `handle_landscape` | function | `services/chat_handlers/handlers.py:818` |
| `handle_pipeline` | function | `services/chat_handlers/handlers.py:1001` |
| `handle_portfolio` | function | `services/chat_handlers/handlers.py:933` |
| `handle_structured_query` | function | `services/chat_handlers/handlers.py:406` |
| `handle_team_eval` | function | `services/chat_handlers/handlers.py:441` |
| `normalize_scope` | function | `services/chat_handlers/formatting.py:316` |
| `resolve_entity` | function | `services/chat_handlers/formatting.py:69` |
| `resolve_followup_question` | function | `services/chat_handlers/context.py:52` |
| `safe_filename` | function | `services/chat_handlers/formatting.py:325` |
| `sanitize_transcript` | function | `services/chat_handlers/formatting.py:330` |
| `to_number` | function | `services/chat_handlers/formatting.py:351` |

## Other Exports (top directories only)

*Use `Grep` to search for specific functions — this list shows key directories only.*

### `./` (66 exports)
- `AgentConfig` (class) — `config.py:158`
- `AppConfig` (class) — `config.py:172`
- `ConnectorConfig` (class) — `config.py:52`
- `Database` (class) — `db.py:24`
- `DatabaseConfig` (class) — `config.py:19`
- `EmbeddingConfig` (class) — `config.py:43`
- `FAIRMetrics` (class) — `fair_analysis.py:31`
- `LLMConfig` (class) — `config.py:135`
- `PipelineConfig` (class) — `config.py:70`
- `ResearchConfig` (class) — `config.py:149`
- *...and 56 more — search with Grep*

### `api/` (39 exports)
- `CompareRequest` (class) — `api/schemas.py:32`
- `DossierRequest` (class) — `api/schemas.py:27`
- `EntityResponse` (class) — `api/schemas.py:75`
- `EntitySummaryResponse` (class) — `api/schemas.py:105`
- `EvidenceItemResponse` (class) — `api/schemas.py:57`
- `GraphEdgeResponse` (class) — `api/schemas.py:88`
- `GraphNodeResponse` (class) — `api/schemas.py:82`
- `HealthResponse` (class) — `api/schemas.py:120`
- `QueryRequest` (class) — `api/schemas.py:20`
- `QueryResponse` (class) — `api/schemas.py:66`
- *...and 29 more — search with Grep*

### `api/routes/` (60 exports)
- `BulkResolveRequest` (class) — `api/routes/catalog.py:805`
- `BulkUpdateRequest` (class) — `api/routes/catalog.py:761`
- `EnrichmentRequest` (class) — `api/routes/catalog.py:131`
- `EntityTagRequest` (class) — `api/routes/catalog.py:137`
- `EntityUpdateRequest` (class) — `api/routes/catalog.py:121`
- `HITLResolveRequest` (class) — `api/routes/catalog.py:126`
- `RunEnrichmentRequest` (class) — `api/routes/catalog.py:877`
- `add_entity_tag` (function) — `api/routes/catalog.py:398`
- `browse_entities` (function) — `api/routes/catalog.py:170`
- `bulk_resolve_hitl` (function) — `api/routes/catalog.py:812`
- *...and 50 more — search with Grep*

### `connectors/` (66 exports)
- `BaseConnector` (class) — `connectors/base.py:172`
- `ClinicalTrialsConnector` (class) — `connectors/clinical_trials.py:88`
- `ConnectorError` (class) — `connectors/base.py:278`
- `EnrichmentResult` (class) — `connectors/enrichment_runner.py:21`
- `EnrichmentRunner` (class) — `connectors/enrichment_runner.py:29`
- `FDAShortagesConnector` (class) — `connectors/fda_shortages.py:74`
- `HealthCheckResult` (class) — `connectors/base.py:268`
- `LinkType` (class) — `connectors/base.py:66`
- `MeSHConnector` (class) — `connectors/mesh.py:42`
- `OpenFDAFAERSConnector` (class) — `connectors/openfda_faers.py:55`
- *...and 56 more — search with Grep*

### `domain/` (26 exports)
- `AgentPersona` (class) — `domain/schema.py:186`
- `DomainPack` (class) — `domain/schema.py:201`
- `DomainRegistry` (class) — `domain/registry.py:27`
- `EntitySchema` (class) — `domain/schema.py:25`
- `FieldMapping` (class) — `domain/schema.py:120`
- `LinkRule` (class) — `domain/schema.py:89`
- `MentionNormalizer` (class) — `domain/schema.py:173`
- `OntologyConfig` (class) — `domain/schema.py:141`
- `SourceConfig` (class) — `domain/schema.py:132`
- `active` (function) — `domain/registry.py:53`
- *...and 16 more — search with Grep*

### `domain/pharma/` (3 exports)
- `get_pharma_pack` (function) — `domain/pharma/pack.py:33`
- `normalize_company_mention` (function) — `domain/pharma/mention_normalizer.py:121`
- `normalize_drug_mention` (function) — `domain/pharma/mention_normalizer.py:67`

### `domain/ta_definitions/` (6 exports)
- `CompanyTarget` (class) — `domain/ta_definitions/schema.py:24`
- `TADefinition` (class) — `domain/ta_definitions/schema.py:33`
- `__post_init__` (function) — `domain/ta_definitions/schema.py:65`
- `load_ta_definition` (function) — `domain/ta_definitions/schema.py:108`
- `target_ciks` (function) — `domain/ta_definitions/schema.py:72`
- `to_connector_overrides` (function) — `domain/ta_definitions/schema.py:76`

### `frontend/src/` (46 exports)
- `CatalogBrowseResponse` (type) — `frontend/src/api.ts:272`
- `CatalogDataset` (type) — `frontend/src/api.ts:252`
- `CatalogEntity` (type) — `frontend/src/api.ts:267`
- `CatalogEntityDetail` (type) — `frontend/src/api.ts:327`
- `CatalogStats` (type) — `frontend/src/api.ts:351`
- `ChangeLogEntry` (type) — `frontend/src/api.ts:291`
- `ChatModeFlags` (type) — `frontend/src/api.ts:218`
- `ChatResponse` (type) — `frontend/src/api.ts:195`
- `ChatSessionDetail` (type) — `frontend/src/api.ts:236`
- `ChatSessionSummary` (type) — `frontend/src/api.ts:227`
- *...and 36 more — search with Grep*

### `frontend/src/components/` (1 exports)
- `Message` (type) — `frontend/src/components/ChatMessage.tsx:24`

### `frontend/src/components/layout/` (1 exports)
- `TopBarTab` (type) — `frontend/src/components/layout/TopBar.tsx:5`

### `frontend/src/components/search/` (20 exports)
- `ENTITY_TYPES` (constant) — `frontend/src/components/search/search-utils.ts:7`
- `GraphFocus` (type) — `frontend/src/components/search/search-utils.ts:5`
- `InsightTile` (function) — `frontend/src/components/search/SearchResults.tsx:441`
- `PAGE_SIZE` (constant) — `frontend/src/components/search/search-utils.ts:36`
- `ResultsToolbar` (function) — `frontend/src/components/search/SearchFilters.tsx:176`
- `SearchViewMode` (type) — `frontend/src/components/search/search-utils.ts:3`
- `SortMode` (type) — `frontend/src/components/search/search-utils.ts:4`
- `extractPreviewContent` (function) — `frontend/src/components/search/search-utils.ts:158`
- `extractTherapeuticAreasFromResult` (function) — `frontend/src/components/search/search-utils.ts:57`
- `formatDate` (function) — `frontend/src/components/search/search-utils.ts:47`
- *...and 10 more — search with Grep*

### `integration/` (94 exports)
- `ChangeDetectionHook` (class) — `integration/pipeline_hooks.py:129`
- `CrossLinker` (class) — `integration/cross_linker.py:27`
- `DataQualityEngine` (class) — `integration/data_quality.py:72`
- `DatasetCatalog` (class) — `integration/dataset_catalog.py:213`
- `EmbeddedRecord` (class) — `integration/embedder.py:38`
- `Embedder` (class) — `integration/embedder.py:45`
- `EntityConsolidator` (class) — `integration/entity_consolidator.py:71`
- `EntityResolver` (class) — `integration/entity_resolver.py:128`
- `HITLEscalationHook` (class) — `integration/pipeline_hooks.py:533`
- `HITLReviewManager` (class) — `integration/pipeline_hooks.py:651`
- *...and 84 more — search with Grep*

### `scheduler/` (8 exports)
- `DataPipelineScheduler` (class) — `scheduler/runner.py:32`
- `__init__` (function) — `scheduler/runner.py:35`
- `main` (function) — `scheduler/__main__.py:29`
- `run_now` (function) — `scheduler/runner.py:59`
- `run_one` (function) — `scheduler/runner.py:139`
- `start` (function) — `scheduler/runner.py:41`
- `status` (function) — `scheduler/runner.py:151`
- `stop` (function) — `scheduler/runner.py:55`

### `scripts/` (52 exports)
- `backfill_ta_links_from_mechanism` (function) — `scripts/backfill_ta_links.py:279`
- `backfill_ta_links_from_trials` (function) — `scripts/backfill_ta_links.py:206`
- `backfill_trial_ta_links` (function) — `scripts/backfill_ta_links.py:328`
- `clean_drug_names` (function) — `scripts/clean_drug_names.py:93`
- `compute_completeness` (function) — `scripts/quality_scorecard.py:52`
- `compute_freshness` (function) — `scripts/quality_scorecard.py:169`
- `compute_link_density` (function) — `scripts/quality_scorecard.py:94`
- `compute_overall_score` (function) — `scripts/quality_scorecard.py:240`
- `compute_quality_scores` (function) — `scripts/quality_scorecard.py:213`
- `compute_source_diversity` (function) — `scripts/quality_scorecard.py:147`
- *...and 42 more — search with Grep*

### `tests/` (25 exports)
- `MockLLM` (class) — `tests/conftest.py:125`
- `StubTool` (class) — `tests/conftest.py:55`
- `ToolCallRecorder` (class) — `tests/conftest.py:16`
- `__init__` (function) — `tests/conftest.py:27`
- `__init__` (function) — `tests/conftest.py:58`
- `__init__` (function) — `tests/conftest.py:132`
- `call_count` (function) — `tests/conftest.py:40`
- `call_count` (function) — `tests/conftest.py:148`
- `execute` (function) — `tests/conftest.py:31`
- `execute` (function) — `tests/conftest.py:67`
- *...and 15 more — search with Grep*
