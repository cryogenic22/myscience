# Anti-Slop Rules — DO NOT DUPLICATE Existing Utilities

*Auto-generated: 2026-03-24 17:15*
*Scanned: 884 exports across 24 directories*

**BEFORE creating any new function, class, or constant:**
1. Search this list for an existing implementation
2. If it exists, import it — do NOT create a new version
3. If you need a variant, extend the existing one

## Known Duplicates (50 — consolidate these)

- **`EvalResult`** — defined in: `benchmark/eval_runner.py`, `services/research_agent.py`
- **`EvidenceItem`** — defined in: `frontend/src/api.ts`, `services/query_engine.py`
- **`GraphEdge`** — defined in: `frontend/src/api.ts`, `services/graph.py`
- **`GraphNode`** — defined in: `frontend/src/api.ts`, `services/graph.py`
- **`QualityResult`** — defined in: `frontend/src/api.ts`, `integration/data_quality.py`
- **`QueryResponse`** — defined in: `api/schemas.py`, `frontend/src/api.ts`
- **`SearchResult`** — defined in: `frontend/src/api.ts`, `services/search.py`
- **`SourceCoverageItem`** — defined in: `api/schemas.py`, `frontend/src/api.ts`
- **`__init__`** — defined in: `benchmark/eval_runner.py`, `connectors/base.py`, `connectors/clinical_trials.py`, `connectors/enrichment_runner.py`, `connectors/fda_shortages.py`, `connectors/mesh.py`, `connectors/openfda_faers.py`, `connectors/openfda_labels.py`, `connectors/orange_book.py`, `connectors/pmc.py`, `connectors/pubmed.py`, `connectors/sec_edgar.py`, `db.py`, `integration/cross_linker.py`, `integration/data_quality.py`, `integration/dataset_catalog.py`, `integration/embedder.py`, `integration/entity_consolidator.py`, `integration/entity_resolver.py`, `integration/knowledge_store.py`, `integration/normalizer.py`, `integration/pipeline.py`, `integration/pipeline.py`, `integration/pipeline_hooks.py`, `integration/pipeline_hooks.py`, `integration/pipeline_hooks.py`, `integration/pipeline_hooks.py`, `integration/pipeline_hooks.py`, `integration/pipeline_hooks.py`, `integration/pipeline_hooks.py`, `integration/pipeline_hooks.py`, `integration/pipeline_hooks.py`, `integration/pipeline_hooks.py`, `scheduler/runner.py`, `services/agent/schema_introspector.py`, `services/agent/tools/graph_tool.py`, `services/agent/tools/metrics_tool.py`, `services/agent/tools/rag_tool.py`, `services/agent/tools/sql_tool.py`, `services/concept_registry.py`, `services/conversation_memory.py`, `services/ctx_context.py`, `services/ctx_corpus.py`, `services/ctx_pipeline.py`, `services/data_steward.py`, `services/entity_agents.py`, `services/entity_agents.py`, `services/fair_scorer.py`, `services/feedback_loops.py`, `services/feedback_loops.py`, `services/feedback_loops.py`, `services/feedback_loops.py`, `services/graph.py`, `services/graph_analytics.py`, `services/insight_engine.py`, `services/llm.py`, `services/metrics.py`, `services/query_engine.py`, `services/research_agent.py`, `services/scenario_engine.py`, `services/search.py`, `services/steward_signals.py`, `services/unified_handler.py`, `services/web_research.py`, `services/workspace.py`, `tests/conftest.py`, `tests/conftest.py`, `tests/conftest.py`
- **`__post_init__`** — defined in: `connectors/base.py`, `domain/ta_definitions/schema.py`
- **`analyze`** — defined in: `fair_analysis.py`, `services/feedback_loops.py`, `services/feedback_loops.py`, `services/feedback_loops.py`
- **`call_count`** — defined in: `tests/conftest.py`, `tests/conftest.py`
- **`company_portfolio`** — defined in: `api/routes/metrics.py`, `services/metrics.py`
- **`competitive_clusters`** — defined in: `api/routes/graph.py`, `services/graph_analytics.py`
- **`competitive_landscape`** — defined in: `api/routes/metrics.py`, `services/metrics.py`
- **`create_research_job`** — defined in: `api/routes/chat.py`, `services/workspace.py`
- **`derive_competition`** — defined in: `api/routes/enrichment.py`, `scripts/derive_competition.py`
- **`enabled`** — defined in: `services/llm.py`, `services/web_research.py`
- **`entity_influence`** — defined in: `api/routes/graph.py`, `services/graph_analytics.py`
- **`entity_summary`** — defined in: `api/routes/graph.py`, `services/graph.py`
- **`evidence_density`** — defined in: `api/routes/metrics.py`, `services/metrics.py`
- **`execute`** — defined in: `db.py`, `integration/pipeline_hooks.py`, `integration/pipeline_hooks.py`, `integration/pipeline_hooks.py`, `integration/pipeline_hooks.py`, `integration/pipeline_hooks.py`, `integration/pipeline_hooks.py`, `integration/pipeline_hooks.py`, `integration/pipeline_hooks.py`, `integration/pipeline_hooks.py`, `services/agent/tools/base.py`, `services/agent/tools/graph_tool.py`, `services/agent/tools/metrics_tool.py`, `services/agent/tools/rag_tool.py`, `services/agent/tools/sql_tool.py`, `tests/conftest.py`, `tests/conftest.py`
- **`fetch`** — defined in: `connectors/base.py`, `connectors/clinical_trials.py`, `connectors/fda_shortages.py`, `connectors/mesh.py`, `connectors/openfda_faers.py`, `connectors/openfda_labels.py`, `connectors/orange_book.py`, `connectors/pmc.py`, `connectors/pubmed.py`, `connectors/sec_edgar.py`
- **`find_similar`** — defined in: `api/routes/search.py`, `services/search.py`
- **`get`** — defined in: `domain/registry.py`, `services/concept_registry.py`
- **`get_entity`** — defined in: `api/mcp_server.py`, `api/routes/entities.py`
- **`get_metrics`** — defined in: `api/deps.py`, `api/mcp_server.py`
- **`get_research_job`** — defined in: `api/routes/chat.py`, `services/workspace.py`
- **`health_check`** — defined in: `connectors/base.py`, `connectors/clinical_trials.py`, `connectors/fda_shortages.py`, `connectors/mesh.py`, `connectors/openfda_faers.py`, `connectors/openfda_labels.py`, `connectors/orange_book.py`, `connectors/pmc.py`, `connectors/pubmed.py`, `connectors/sec_edgar.py`
- **`list_research_jobs`** — defined in: `api/routes/chat.py`, `services/workspace.py`
- **`main`** — defined in: `benchmark/capture_responses.py`, `benchmark/ci_eval.py`, `benchmark/eval_runner.py`, `migrate.py`, `run_consolidation.py`, `scheduler/__main__.py`, `scripts/ai_enrich.py`, `scripts/auto_curate.py`, `scripts/backfill_mechanisms.py`, `scripts/backfill_sponsor_links.py`, `scripts/backfill_ta_links.py`, `scripts/clean_drug_names.py`, `scripts/dedup_companies.py`, `scripts/derive_competition.py`, `scripts/enrich_companies.py`, `scripts/enrich_drugs.py`, `scripts/extract_biomarkers.py`, `scripts/fetch_nadac_pricing.py`, `scripts/fetch_who_gprm.py`, `scripts/onboard_ta.py`, `scripts/quality_scorecard.py`
- **`name`** — defined in: `services/agent/tools/base.py`, `services/agent/tools/graph_tool.py`, `services/agent/tools/metrics_tool.py`, `services/agent/tools/rag_tool.py`, `services/agent/tools/sql_tool.py`, `tests/conftest.py`, `tests/conftest.py`
- **`neighborhood`** — defined in: `api/routes/graph.py`, `services/graph.py`
- **`path_between`** — defined in: `api/routes/graph.py`, `services/graph.py`
- **`pipeline_excluding_inactive`** — defined in: `api/routes/scenarios.py`, `services/scenario_engine.py`
- **`query`** — defined in: `api/routes/query.py`, `services/query_engine.py`
- **`refresh_materialized_views`** — defined in: `api/routes/catalog.py`, `fix_data_quality.py`
- **`register`** — defined in: `domain/registry.py`, `integration/pipeline_hooks.py`, `services/concept_registry.py`
- **`resolve`** — defined in: `integration/entity_resolver.py`, `integration/pipeline_hooks.py`
- **`run`** — defined in: `backfill_data_linkage.py`, `fix_data_quality.py`, `integration/entity_consolidator.py`, `integration/pipeline.py`, `scripts/ai_enrich.py`, `scripts/auto_curate.py`, `scripts/backfill_mechanisms.py`, `scripts/backfill_sponsor_links.py`, `scripts/backfill_ta_links.py`, `scripts/clean_drug_names.py`, `scripts/dedup_companies.py`, `scripts/derive_competition.py`, `scripts/enrich_companies.py`, `scripts/enrich_drugs.py`, `scripts/extract_biomarkers.py`, `scripts/fetch_nadac_pricing.py`, `scripts/fetch_who_gprm.py`, `scripts/onboard_ta.py`, `scripts/quality_scorecard.py`, `services/entity_agents.py`, `services/feedback_loops.py`, `services/scenario_engine.py`
- **`run_all`** — defined in: `connectors/enrichment_runner.py`, `services/entity_agents.py`
- **`run_enrichment`** — defined in: `api/routes/catalog.py`, `api/routes/enrichment.py`
- **`run_loop`** — defined in: `services/data_steward.py`, `services/research_agent.py`
- **`run_one`** — defined in: `scheduler/runner.py`, `services/entity_agents.py`
- **`search`** — defined in: `api/routes/search.py`, `services/search.py`, `services/web_research.py`
- **`should_fire`** — defined in: `integration/pipeline_hooks.py`, `integration/pipeline_hooks.py`, `integration/pipeline_hooks.py`
- **`source_type`** — defined in: `connectors/base.py`, `connectors/clinical_trials.py`, `connectors/fda_shortages.py`, `connectors/mesh.py`, `connectors/openfda_faers.py`, `connectors/openfda_labels.py`, `connectors/orange_book.py`, `connectors/pmc.py`, `connectors/pubmed.py`, `connectors/sec_edgar.py`
- **`threshold_alert`** — defined in: `api/routes/scenarios.py`, `services/scenario_engine.py`
- **`traverse`** — defined in: `api/routes/graph.py`, `services/graph.py`
- **`weighted_path`** — defined in: `api/routes/graph.py`, `services/graph_analytics.py`

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
| `AutonomousResearchAgent` | class | `services/research_agent.py:121` |
| `CTXContextBuilder` | class | `services/ctx_context.py:344` |
| `CTXQueryPipeline` | class | `services/ctx_pipeline.py:119` |
| `ChatWorkspaceService` | class | `services/workspace.py:14` |
| `Concept` | class | `services/concept_registry.py:27` |
| `ConceptRegistry` | class | `services/concept_registry.py:58` |
| `ContextResult` | class | `services/ctx_context.py:61` |
| `ConversationMemory` | class | `services/conversation_memory.py:66` |
| `DataSteward` | class | `services/data_steward.py:92` |
| `EnrichmentPlan` | class | `services/research_agent.py:50` |
| `EntityAgent` | class | `services/entity_agents.py:44` |
| `EntityAgentConfig` | class | `services/entity_agents.py:29` |
| `EntityAgentOrchestrator` | class | `services/entity_agents.py:174` |
| `EvalResult` | class | `services/research_agent.py:59` |
| `EvidenceItem` | class | `services/query_engine.py:29` |
| `FAIRScorer` | class | `services/fair_scorer.py:62` |
| `FeedbackAction` | class | `services/feedback_loops.py:41` |
| `FeedbackLoopOrchestrator` | class | `services/feedback_loops.py:306` |
| `FewShotExemplar` | class | `services/few_shot_library.py:25` |
| `FewShotLibrary` | class | `services/few_shot_library.py:261` |
| `GraphAnalytics` | class | `services/graph_analytics.py:24` |
| `GraphEdge` | class | `services/graph.py:33` |
| `GraphNode` | class | `services/graph.py:23` |
| `GraphTraversal` | class | `services/graph.py:77` |
| `HybridSearch` | class | `services/search.py:191` |
| `Insight` | class | `services/insight_engine.py:28` |
| `InsightEngine` | class | `services/insight_engine.py:52` |
| `LLMSynthesizer` | class | `services/llm.py:372` |
| `LoopSummary` | class | `services/research_agent.py:70` |
| `PharmaCorpusBuilder` | class | `services/ctx_corpus.py:101` |
| `PharmaMetrics` | class | `services/metrics.py:30` |
| `QualityLoop` | class | `services/feedback_loops.py:230` |
| `QueryEngine` | class | `services/query_engine.py:59` |
| `QueryPatternLoop` | class | `services/feedback_loops.py:63` |
| `QueryPlan` | class | `services/ctx_pipeline.py:42` |
| `QueryResult` | class | `services/query_engine.py:41` |
| `ReasoningResult` | class | `services/ctx_pipeline.py:72` |
| `ResearchTarget` | class | `services/research_agent.py:38` |
| `ResolutionFailureLoop` | class | `services/feedback_loops.py:127` |
| `RetrievalResult` | class | `services/ctx_pipeline.py:52` |
| `ScenarioEngine` | class | `services/scenario_engine.py:36` |
| `ScenarioResult` | class | `services/scenario_engine.py:25` |
| `SearchResult` | class | `services/search.py:25` |
| `StewardConfig` | class | `services/data_steward.py:30` |
| `StewardLoopSummary` | class | `services/data_steward.py:55` |
| `StewardResult` | class | `services/data_steward.py:41` |
| `StewardSignal` | class | `services/steward_signals.py:50` |
| `StewardSignalCollector` | class | `services/steward_signals.py:65` |
| `Subgraph` | class | `services/graph.py:45` |
| `UnifiedChatHandler` | class | `services/unified_handler.py:22` |
| `WebResearchItem` | class | `services/web_research.py:16` |
| `WebResearchService` | class | `services/web_research.py:23` |
| `__init__` | function | `services/concept_registry.py:66` |
| `__init__` | function | `services/conversation_memory.py:79` |
| `__init__` | function | `services/ctx_context.py:352` |
| `__init__` | function | `services/ctx_corpus.py:104` |
| `__init__` | function | `services/ctx_pipeline.py:129` |
| `__init__` | function | `services/data_steward.py:95` |
| `__init__` | function | `services/entity_agents.py:47` |
| `__init__` | function | `services/entity_agents.py:222` |
| `__init__` | function | `services/fair_scorer.py:65` |
| `__init__` | function | `services/feedback_loops.py:71` |
| `__init__` | function | `services/feedback_loops.py:134` |
| `__init__` | function | `services/feedback_loops.py:237` |
| `__init__` | function | `services/feedback_loops.py:313` |
| `__init__` | function | `services/graph.py:80` |
| `__init__` | function | `services/graph_analytics.py:27` |
| `__init__` | function | `services/insight_engine.py:55` |
| `__init__` | function | `services/llm.py:375` |
| `__init__` | function | `services/metrics.py:33` |
| `__init__` | function | `services/query_engine.py:62` |
| `__init__` | function | `services/research_agent.py:130` |
| `__init__` | function | `services/scenario_engine.py:44` |
| `__init__` | function | `services/search.py:194` |
| `__init__` | function | `services/steward_signals.py:68` |
| `__init__` | function | `services/unified_handler.py:32` |
| `__init__` | function | `services/web_research.py:26` |
| `__init__` | function | `services/workspace.py:17` |
| `activate` | function | `services/concept_registry.py:95` |
| `add_exchange` | function | `services/conversation_memory.py:86` |
| `analyze` | function | `services/feedback_loops.py:74` |
| `analyze` | function | `services/feedback_loops.py:137` |
| `analyze` | function | `services/feedback_loops.py:240` |
| `available_sections` | function | `services/ctx_pipeline.py:167` |
| `build` | function | `services/ctx_context.py:358` |
| `build_corpus_dir` | function | `services/ctx_corpus.py:176` |
| `build_system_prompt` | function | `services/ctx_pipeline.py:425` |
| `check_response` | function | `services/ctx_pipeline.py:421` |
| `collect_signals` | function | `services/steward_signals.py:71` |
| `commit_or_revert` | function | `services/research_agent.py:361` |
| `company_portfolio` | function | `services/metrics.py:271` |
| `compare_entities` | function | `services/query_engine.py:285` |
| `competitive_clusters` | function | `services/graph_analytics.py:88` |
| `competitive_landscape` | function | `services/metrics.py:189` |
| `complete_research_job` | function | `services/workspace.py:224` |
| `compute` | function | `services/fair_scorer.py:70` |
| `compute_priority` | function | `services/steward_signals.py:259` |
| `create_research_job` | function | `services/workspace.py:144` |
| `delete_session` | function | `services/workspace.py:131` |
| `detect_query_gap` | function | `services/telemetry.py:60` |
| `detect_truncation` | function | `services/graph.py:66` |
| `drug_pipeline_strength` | function | `services/metrics.py:37` |
| `drugs_by_mechanism_class` | function | `services/graph.py:310` |
| `enabled` | function | `services/llm.py:380` |
| `enabled` | function | `services/web_research.py:30` |
| `entity_centrality_batch` | function | `services/graph_analytics.py:323` |
| `entity_dossier` | function | `services/query_engine.py:191` |
| `entity_influence` | function | `services/graph_analytics.py:32` |
| `entity_summary` | function | `services/graph.py:250` |
| `evaluate` | function | `services/research_agent.py:311` |
| `evidence_density` | function | `services/metrics.py:156` |
| `execute_enrichment` | function | `services/research_agent.py:275` |
| `export_companies` | function | `services/ctx_corpus.py:127` |
| `export_drugs` | function | `services/ctx_corpus.py:107` |
| `export_mechanisms` | function | `services/ctx_corpus.py:161` |
| `export_trials` | function | `services/ctx_corpus.py:143` |
| `fail_research_job` | function | `services/workspace.py:239` |
| `find_similar` | function | `services/search.py:302` |
| `format_concept_context` | function | `services/concept_registry.py:277` |
| `format_context` | function | `services/few_shot_library.py:292` |
| `from_dict` | function | `services/conversation_memory.py:44` |
| `get` | function | `services/concept_registry.py:75` |
| `get_context` | function | `services/conversation_memory.py:127` |
| `get_cumulative_stats` | function | `services/research_agent.py:428` |
| `get_entities_discussed` | function | `services/conversation_memory.py:175` |
| `get_exemplars` | function | `services/few_shot_library.py:264` |
| `get_research_job` | function | `services/workspace.py:188` |
| `get_session` | function | `services/workspace.py:108` |
| `get_signal_stats` | function | `services/steward_signals.py:234` |
| `handle` | function | `services/unified_handler.py:48` |
| `identify_target` | function | `services/research_agent.py:164` |
| `is_relevant_for_intent` | function | `services/concept_registry.py:48` |
| `is_stale` | function | `services/concept_registry.py:52` |
| `landscape_single_mechanism` | function | `services/scenario_engine.py:276` |
| `landscape_without_company` | function | `services/scenario_engine.py:217` |
| `landscape_without_entity` | function | `services/scenario_engine.py:82` |
| `latest` | function | `services/fair_scorer.py:125` |
| `list_agents` | function | `services/entity_agents.py:273` |
| `list_for_entity_type` | function | `services/concept_registry.py:87` |
| `list_for_intent` | function | `services/concept_registry.py:79` |
| `list_research_jobs` | function | `services/workspace.py:165` |
| `list_sessions` | function | `services/workspace.py:84` |
| `log_ctx_event` | function | `services/telemetry.py:20` |
| `log_iteration` | function | `services/research_agent.py:382` |
| `log_query_event` | function | `services/telemetry.py:96` |
| `mark_research_job_running` | function | `services/workspace.py:212` |
| `mechanism_hierarchy` | function | `services/graph.py:330` |
| `neighborhood` | function | `services/graph.py:84` |
| `pack` | function | `services/ctx_corpus.py:258` |
| `pack_evidence` | function | `services/ctx_evidence.py:86` |
| `parse_sections` | function | `services/literature.py:19` |
| `path_between` | function | `services/graph.py:142` |
| `persist` | function | `services/fair_scorer.py:103` |
| `persist_log` | function | `services/research_agent.py:411` |
| `pipeline_excluding_inactive` | function | `services/scenario_engine.py:161` |
| `pipeline_without_entity` | function | `services/scenario_engine.py:127` |
| `plan_enrichment` | function | `services/research_agent.py:229` |
| `query` | function | `services/query_engine.py:76` |
| `rank_by_recency` | function | `services/search.py:170` |
| `realtime_competitive_landscape` | function | `services/metrics.py:325` |
| `realtime_pipeline_strength` | function | `services/metrics.py:369` |
| `reason` | function | `services/ctx_pipeline.py:354` |
| `recency_score` | function | `services/search.py:140` |
| `refresh` | function | `services/metrics.py:308` |
| `register` | function | `services/concept_registry.py:71` |
| `render_context` | function | `services/ctx_pipeline.py:60` |
| `resolve_reference` | function | `services/conversation_memory.py:191` |
| `restore` | function | `services/conversation_memory.py:276` |
| `retrieve` | function | `services/ctx_pipeline.py:295` |
| `run` | function | `services/entity_agents.py:51` |
| `run` | function | `services/feedback_loops.py:321` |
| `run` | function | `services/scenario_engine.py:50` |
| `run_all` | function | `services/entity_agents.py:226` |
| `run_loop` | function | `services/data_steward.py:106` |
| `run_loop` | function | `services/research_agent.py:440` |
| `run_one` | function | `services/entity_agents.py:266` |
| `save_session` | function | `services/workspace.py:20` |
| `scan` | function | `services/insight_engine.py:58` |
| `search` | function | `services/search.py:239` |
| `search` | function | `services/web_research.py:34` |
| `search_entity_type` | function | `services/search.py:340` |
| `search_paginated` | function | `services/search.py:260` |
| `snapshot` | function | `services/conversation_memory.py:262` |
| `synthesize` | function | `services/llm.py:420` |
| `synthesize_comparison` | function | `services/llm.py:579` |
| `synthesize_dossier` | function | `services/llm.py:550` |
| `synthesize_landscape` | function | `services/llm.py:608` |
| `synthesize_pipeline` | function | `services/llm.py:622` |
| `synthesize_research_report` | function | `services/llm.py:638` |
| `synthesize_stream` | function | `services/llm.py:502` |
| `threshold_alert` | function | `services/scenario_engine.py:307` |
| `to_dict` | function | `services/conversation_memory.py:34` |
| `traverse` | function | `services/graph.py:88` |
| `trend` | function | `services/fair_scorer.py:134` |
| `trial_success_rate` | function | `services/metrics.py:110` |
| `understand` | function | `services/ctx_pipeline.py:173` |
| `validate_citations` | function | `services/llm.py:30` |
| `verify_narrative_numbers` | function | `services/llm.py:96` |
| `weighted_path` | function | `services/graph_analytics.py:174` |

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
| `build_query_graph` | function | `services/agent/graphs/query_graph.py:537` |
| `build_team_eval_graph` | function | `services/agent/graphs/team_eval_graph.py:792` |
| `has_structured_signals` | function | `services/agent/graphs/query_graph.py:599` |

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
| `build_compare_graph` | function | `services/chat_handlers/formatting.py:419` |
| `build_comparison_table` | function | `services/chat_handlers/formatting.py:270` |
| `build_conversation_context` | function | `services/chat_handlers/context.py:10` |
| `build_visualizations` | function | `services/chat_handlers/formatting.py:228` |
| `coerce_bool` | function | `services/chat_handlers/formatting.py:12` |
| `compute_comparison_insights` | function | `services/chat_handlers/formatting.py:184` |
| `compute_response_confidence` | function | `services/chat_handlers/formatting.py:371` |
| `detect_compound_intent` | function | `services/chat_handlers/intent.py:141` |
| `detect_format_hint` | function | `services/chat_handlers/intent.py:38` |
| `detect_intent` | function | `services/chat_handlers/intent.py:48` |
| `expand_topic_synonyms` | function | `services/chat_handlers/formatting.py:175` |
| `generate_followups` | function | `services/chat_handlers/formatting.py:127` |
| `handle_compare` | function | `services/chat_handlers/handlers.py:818` |
| `handle_compound` | function | `services/chat_handlers/handlers.py:1374` |
| `handle_deep_research` | function | `services/chat_handlers/handlers.py:1267` |
| `handle_dossier` | function | `services/chat_handlers/handlers.py:549` |
| `handle_general` | function | `services/chat_handlers/handlers.py:1250` |
| `handle_landscape` | function | `services/chat_handlers/handlers.py:950` |
| `handle_pipeline` | function | `services/chat_handlers/handlers.py:1150` |
| `handle_portfolio` | function | `services/chat_handlers/handlers.py:1082` |
| `handle_structured_query` | function | `services/chat_handlers/handlers.py:482` |
| `handle_team_eval` | function | `services/chat_handlers/handlers.py:517` |
| `normalize_scope` | function | `services/chat_handlers/formatting.py:324` |
| `resolve_entity` | function | `services/chat_handlers/formatting.py:69` |
| `resolve_followup_question` | function | `services/chat_handlers/context.py:52` |
| `safe_filename` | function | `services/chat_handlers/formatting.py:333` |
| `sanitize_transcript` | function | `services/chat_handlers/formatting.py:338` |
| `to_number` | function | `services/chat_handlers/formatting.py:359` |

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

### `api/` (44 exports)
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
- *...and 34 more — search with Grep*

### `api/routes/` (99 exports)
- `BulkResolveRequest` (class) — `api/routes/catalog.py:805`
- `BulkUpdateRequest` (class) — `api/routes/catalog.py:761`
- `CompanyRemovalRequest` (class) — `api/routes/scenarios.py:52`
- `EnrichmentRequest` (class) — `api/routes/catalog.py:131`
- `EntityTagRequest` (class) — `api/routes/catalog.py:137`
- `EntityUpdateRequest` (class) — `api/routes/catalog.py:121`
- `FeedbackCreateRequest` (class) — `api/routes/feedback.py:28`
- `FeedbackUpdateRequest` (class) — `api/routes/feedback.py:40`
- `HITLResolveRequest` (class) — `api/routes/catalog.py:126`
- `LandscapeWithoutRequest` (class) — `api/routes/scenarios.py:30`
- *...and 89 more — search with Grep*

### `benchmark/` (18 exports)
- `EvalReport` (class) — `benchmark/eval_runner.py:52`
- `EvalResult` (class) — `benchmark/eval_runner.py:40`
- `EvalRunner` (class) — `benchmark/eval_runner.py:65`
- `__init__` (function) — `benchmark/eval_runner.py:68`
- `capture_responses` (function) — `benchmark/capture_responses.py:24`
- `composite_score` (function) — `benchmark/scorers.py:191`
- `main` (function) — `benchmark/capture_responses.py:95`
- `main` (function) — `benchmark/ci_eval.py:105`
- `main` (function) — `benchmark/eval_runner.py:276`
- `run_ci_eval` (function) — `benchmark/ci_eval.py:26`
- *...and 8 more — search with Grep*

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

### `frontend/src/` (49 exports)
- `CatalogBrowseResponse` (type) — `frontend/src/api.ts:306`
- `CatalogDataset` (type) — `frontend/src/api.ts:286`
- `CatalogEntity` (type) — `frontend/src/api.ts:301`
- `CatalogEntityDetail` (type) — `frontend/src/api.ts:361`
- `CatalogStats` (type) — `frontend/src/api.ts:385`
- `ChangeLogEntry` (type) — `frontend/src/api.ts:325`
- `ChatModeFlags` (type) — `frontend/src/api.ts:252`
- `ChatResponse` (type) — `frontend/src/api.ts:229`
- `ChatSessionDetail` (type) — `frontend/src/api.ts:270`
- `ChatSessionSummary` (type) — `frontend/src/api.ts:261`
- *...and 39 more — search with Grep*

### `frontend/src/components/` (2 exports)
- `LiteratureExplorer` (function) — `frontend/src/components/LiteratureExplorer.tsx:17`
- `Message` (type) — `frontend/src/components/ChatMessage.tsx:24`

### `frontend/src/components/layout/` (1 exports)
- `TopBarTab` (type) — `frontend/src/components/layout/TopBar.tsx:5`

### `frontend/src/components/search/` (20 exports)
- `ENTITY_TYPES` (constant) — `frontend/src/components/search/search-utils.ts:7`
- `GraphFocus` (type) — `frontend/src/components/search/search-utils.ts:5`
- `InsightTile` (function) — `frontend/src/components/search/SearchResults.tsx:454`
- `PAGE_SIZE` (constant) — `frontend/src/components/search/search-utils.ts:36`
- `ResultsToolbar` (function) — `frontend/src/components/search/SearchFilters.tsx:169`
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
- `run_one` (function) — `scheduler/runner.py:177`
- `start` (function) — `scheduler/runner.py:41`
- `status` (function) — `scheduler/runner.py:189`
- `stop` (function) — `scheduler/runner.py:55`

### `scripts/` (73 exports)
- `backfill_mechanisms` (function) — `scripts/backfill_mechanisms.py:144`
- `backfill_sponsor_links` (function) — `scripts/backfill_sponsor_links.py:67`
- `backfill_ta_links_from_mechanism` (function) — `scripts/backfill_ta_links.py:279`
- `backfill_ta_links_from_trials` (function) — `scripts/backfill_ta_links.py:206`
- `backfill_trial_ta_links` (function) — `scripts/backfill_ta_links.py:328`
- `clean_drug_names` (function) — `scripts/clean_drug_names.py:93`
- `compute_completeness` (function) — `scripts/quality_scorecard.py:52`
- `compute_freshness` (function) — `scripts/quality_scorecard.py:169`
- `compute_link_density` (function) — `scripts/quality_scorecard.py:94`
- `compute_overall_score` (function) — `scripts/quality_scorecard.py:240`
- *...and 63 more — search with Grep*
