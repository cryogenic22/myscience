# Anti-Slop Rules — DO NOT DUPLICATE Existing Utilities

*Auto-generated: 2026-05-21 23:46*
*Scanned: 2216 exports across 60 directories*

**BEFORE creating any new function, class, or constant:**
1. Search this list for an existing implementation
2. If it exists, import it — do NOT create a new version
3. If you need a variant, extend the existing one

> Read on demand. This is an index — `Grep` for any specific symbol.

## Known Duplicates (125 — consolidate these)

- **`AgentSession`** — `ctxpack/agent/session.py`, `services/agent/session_store.py`
- **`BriefState`** — `frontend/src/api.ts`, `services/decision_brief.py`
- **`ConfidenceTier`** — `frontend/src/api.ts`, `packages/design-tokens/src/index.ts`
- **`DecisionBrief`** — `frontend/src/api.ts`, `services/decision_brief.py`
- **`DecisionBriefOption`** — `frontend/src/api.ts`, `services/decision_brief.py`
- **`DiffResult`** — `ctxpack/core/diff.py`, `services/ctgov_diff_service.py`, `services/spl_diff_service.py`
- **`EntityMentionData`** — `frontend/src/components/v2/RichNarrative.tsx`, `frontend/src/types/newui.ts`
- **`EntitySchema`** — `ctxpack/core/packer/templates.py`, `domain/schema.py`
- **`EvalResult`** — `benchmark/eval_runner.py`, `services/research_agent.py`
- **`EvidenceItem`** — `frontend/src/api.ts`, `services/query_engine.py`
- **`EvidenceTier`** — `frontend/src/types/dossier.ts`, `frontend/src/types/evidence.ts`
- **`FeedSummary`** — `frontend/src/api.ts`, `frontend/src/components/ci/SensingFeed.tsx`, `services/intelligence_feed.py`
- **`GraphEdge`** — `frontend/src/api.ts`, `services/ask_engine.py`, `services/graph.py`
- **`GraphNode`** — `frontend/src/api.ts`, `services/ask_engine.py`, `services/graph.py`
- **`Header`** — `apps/landing/src/components/Header.tsx`, `ctxpack/core/model.py`
- **`ImpactTier`** — `frontend/src/api.ts`, `packages/design-tokens/src/index.ts`
- **`IntelligenceFeedItem`** — `frontend/src/api.ts`, `frontend/src/components/ci/SensingFeed.tsx`
- **`MaterialityFactor`** — `frontend/src/types/materiality.ts`, `services/materiality.py`
- **`Pill`** — `frontend/src/components/ui/Pill.tsx`, `packages/ui/src/components/Pill.tsx`
- **`Provenance`** — `connectors/base.py`, `ctxpack/core/model.py`
- **`QualityResult`** — `frontend/src/api.ts`, `integration/data_quality.py`
- **`QueryResponse`** — `api/schemas.py`, `frontend/src/api.ts`
- **`SearchResult`** — `frontend/src/api.ts`, `services/search.py`
- **`SourceCoverageItem`** — `api/schemas.py`, `frontend/src/api.ts`
- **`V2Message`** — `frontend/src/components/v2/DialoguePanel.tsx`, `frontend/src/pages/NewWorkspace.tsx`, `frontend/src/types/newui.ts`
- **`__str__`** — `ctxpack/core/errors.py`, `ctxpack/core/packer/ir.py`
- **`add_option`** — `api/routes/decision_briefs.py`, `services/decision_brief.py`
- **`analyze`** — `fair_analysis.py`, `services/feedback_loops.py`, `services/feedback_loops.py`, `services/feedback_loops.py`
- **`append_evidence`** — `api/routes/evidence_ledger.py`, `services/evidence_ledger.py`
- **`append_roles_history`** — `services/db_adapter_8k.py`, `services/sec_8k_pipeline.py`
- **`ask`** — `api/routes/ask.py`, `services/ask_engine.py`
- **`build_event_row`** — `services/event_emitters/biosimilar_approval.py`, `services/event_emitters/deal_announced.py`, `services/event_emitters/drug_discontinuation.py`, `services/event_emitters/ema_chmp_opinion.py`, `services/event_emitters/exec_change.py` *(+6 more)*
- **`build_hydration_tool_schema`** — `ctxpack/core/hydration_protocol.py`, `ctxpack/core/hydration_protocol.py`
- **`build_system_prompt`** — `ctxpack/core/hydration_protocol.py`, `services/ctx_pipeline.py`
- **`call`** — `services/extraction_llm.py`, `services/extraction_llm.py`
- **`call_count`** — `tests/conftest.py`, `tests/conftest.py`
- **`canonical_json`** — `services/decision_signing.py`, `services/evidence_ledger.py`
- **`check`** — `ctxpack/modules/guard.py`, `services/agent/permissions.py`
- **`company_portfolio`** — `api/routes/metrics.py`, `services/metrics.py`
- **`competitive_clusters`** — `api/routes/graph.py`, `services/graph_analytics.py`
- **`competitive_landscape`** — `api/routes/metrics.py`, `services/metrics.py`
- **`consolidate_drugs`** — `integration/entity_consolidator.py`, `scripts/consolidate_drugs.py`
- **`count_tokens`** — `ctxpack/benchmarks/metrics/compression.py`, `ctxpack/core/packer/compressor.py`
- **`create_ctxpack_config`** — `ctxpack/benchmarks/realworld/fda_corpus.py`, `ctxpack/benchmarks/realworld/twilio_corpus.py`
- **`create_research_job`** — `api/routes/chat.py`, `services/workspace.py`
- **`create_supplementary_docs`** — `ctxpack/benchmarks/realworld/fda_corpus.py`, `ctxpack/benchmarks/realworld/twilio_corpus.py`
- **`derive_competition`** — `api/routes/enrichment.py`, `scripts/derive_competition.py`
- **`dismiss_event`** — `api/routes/intelligence.py`, `services/intelligence_feed.py`
- **`enabled`** — `services/llm.py`, `services/web_research.py`
- **`enrich_from_reference`** — `scripts/enrich_companies.py`, `scripts/enrich_drugs.py`
- **`entity_influence`** — `api/routes/graph.py`, `services/graph_analytics.py`
- **`entity_summary`** — `api/routes/graph.py`, `services/graph.py`
- **`evaluate_one`** — `api/routes/framing_triggers.py`, `services/framing_triggers.py`
- **`evidence_density`** — `api/routes/metrics.py`, `services/metrics.py`
- **`executor`** — `api/deps.py`, `api/deps.py`, `api/deps.py`, `api/deps.py`, `api/deps.py` *(+1 more)*
- **`extract`** — `connectors/sec_8k/item_1_01.py`, `connectors/sec_8k/item_2_02.py`, `connectors/sec_8k/item_5_02.py`, `connectors/sec_8k/item_8_01.py`, `services/extraction_llm.py` *(+4 more)*
- **`fetch_all`** — `connectors/fda_purple_book.py`, `db.py`, `db.py`
- **`fetch_for_drug_name`** — `connectors/fda_designations.py`, `connectors/fda_discontinuations.py`
- **`fetch_one`** — `db.py`, `db.py`
- **`find_similar`** — `api/routes/search.py`, `services/search.py`
- **`from_document`** — `ctxpack/core/entity_graph.py`, `ctxpack/modules/keywords.py`
- **`get`** — `ctxpack/core/model.py`, `domain/registry.py`, `services/agent/registry.py`, `services/agent/session_store.py`, `services/concept_registry.py` *(+5 more)*
- **`get_claim`** — `api/routes/evidence_ledger.py`, `services/evidence_ledger.py`
- **`get_entity`** — `api/mcp_server.py`, `api/routes/entities.py`
- **`get_evidence`** — `api/routes/evidence_ledger.py`, `services/evidence_ledger.py`
- **`get_feed`** — `api/routes/intelligence.py`, `services/intelligence_feed.py`
- **`get_insights`** — `api/routes/inbox.py`, `api/routes/steward.py`
- **`get_metrics`** — `api/deps.py`, `api/mcp_server.py`
- **`get_recent`** — `services/agent/event_stream.py`, `services/agent/session_store.py`
- **`get_research_job`** — `api/routes/chat.py`, `services/workspace.py`
- **`get_run`** — `api/routes/game_theory.py`, `api/routes/learning.py`, `api/routes/war_games.py`, `services/game_theory.py`, `services/learning_service.py`
- **`get_snapshot`** — `api/routes/evidence_ledger.py`, `services/evidence_ledger.py`
- **`get_stats`** — `integration/pipeline_hooks.py`, `services/agent/budget.py`
- **`health_summary`** — `api/routes/sources.py`, `services/source_registry.py`
- **`insert_deal`** — `services/db_adapter_8k.py`, `services/sec_8k_pipeline.py`
- **`insert_event`** — `services/db_adapter_8k.py`, `services/sec_8k_pipeline.py`, `services/spl_diff_service.py`
- **`invoke`** — `api/routes/llm_gateway.py`, `services/llm_gateway.py`, `tests/conftest.py`
- **`list`** — `services/decision_brief.py`, `services/framing_triggers.py`, `services/llm_gateway.py`, `services/source_registry.py`, `services/war_game_adversary.py`
- **`list_claims`** — `api/routes/evidence_ledger.py`, `services/evidence_ledger.py`
- **`list_fires`** — `api/routes/framing_triggers.py`, `services/framing_triggers.py`
- **`list_prompt_flags`** — `api/routes/learning.py`, `services/learning_service.py`
- **`list_research_jobs`** — `api/routes/chat.py`, `services/workspace.py`
- **`list_runs`** — `api/routes/game_theory.py`, `api/routes/learning.py`, `api/routes/war_games.py`, `services/game_theory.py`, `services/learning_service.py`
- **`list_signals`** — `api/routes/signals.py`, `api/routes/steward.py`
- **`migrate_file`** — `scripts/migrate_slate_classes.py`, `scripts/migrate_text_sizes.py`
- **`neighborhood`** — `api/routes/graph.py`, `services/graph.py`
- **`pack`** — `ctxpack/core/packer/__init__.py`, `services/ctx_corpus.py`
- **`parse`** — `ctxpack/core/packer/yaml_parser.py`, `ctxpack/core/parser.py`, `ctxpack/core/parser.py`
- **`parse_openfda_results`** — `connectors/fda_designations.py`, `connectors/fda_discontinuations.py`
- **`parse_sections`** — `services/literature.py`, `services/spl_section_parser.py`
- **`path`** — `ctxpack/core/entity_graph.py`, `ctxpack/core/telemetry.py`
- **`path_between`** — `api/routes/graph.py`, `services/graph.py`
- **`pipeline_excluding_inactive`** — `api/routes/scenarios.py`, `services/scenario_engine.py`
- **`query`** — `api/routes/query.py`, `services/query_engine.py`
- **`react`** — `services/war_game_adversary.py`, `services/war_game_adversary.py`
- **`recompute_quality`** — `api/routes/sources.py`, `services/source_registry.py`
- **`refresh_materialized_views`** — `api/routes/catalog.py`, `fix_data_quality.py`
- **`register`** — `domain/registry.py`, `integration/pipeline_hooks.py`, `services/agent/registry.py`, `services/concept_registry.py`, `services/llm_gateway.py` *(+1 more)*
- **`remove_option`** — `api/routes/decision_briefs.py`, `services/decision_brief.py`
- **`replay`** — `api/routes/decision_signing.py`, `services/decision_signing.py`
- **`reset`** — `api/middleware/rate_limit.py`, `tests/conftest.py`
- **`resolve`** — `integration/entity_resolver.py`, `integration/pipeline_hooks.py`
- **`resolve_drug_id`** — `services/db_adapter_8k.py`, `services/sec_8k_pipeline.py`
- **`run_all`** — `connectors/enrichment_runner.py`, `services/entity_agents.py`
- **`run_enrichment`** — `api/routes/catalog.py`, `api/routes/enrichment.py`
- **`run_loop`** — `services/data_steward.py`, `services/research_agent.py`
- **`run_one`** — `scheduler/runner.py`, `services/entity_agents.py`
- **`run_scaling_eval`** — `ctxpack/benchmarks/scaling/scaling_runner.py`, `ctxpack/benchmarks/scaling_eval.py`
- **`search`** — `api/routes/search.py`, `services/search.py`, `services/web_research.py`
- **`should_fire`** — `integration/pipeline_hooks.py`, `integration/pipeline_hooks.py`, `integration/pipeline_hooks.py`
- **`should_skip`** — `scripts/migrate_slate_classes.py`, `scripts/migrate_text_sizes.py`
- **`sign`** — `api/routes/decision_signing.py`, `services/decision_signing.py`
- **`snapshot`** — `ctxpack/agent/session.py`, `services/conversation_memory.py`
- **`start`** — `scheduler/runner.py`, `services/agent/session_store.py`
- **`summary`** — `ctxpack/core/telemetry.py`, `integration/pipeline.py`
- **`synthesize`** — `api/routes/bridge.py`, `api/routes/recommendations.py`, `services/counter_recommendation.py`, `services/llm.py`
- **`threshold_alert`** — `api/routes/scenarios.py`, `services/scenario_engine.py`
- **`tick`** — `services/framing_triggers.py`, `services/outcome_scheduler.py`
- **`to_json`** — `ctxpack/benchmarks/bench.py`, `ctxpack/core/json_export.py`
- **`toml_parse`** — `ctxpack/core/packer/toml_parser.py`, `ctxpack/core/packer/toml_parser.py`
- **`traverse`** — `api/routes/graph.py`, `ctxpack/core/entity_graph.py`, `services/graph.py`
- **`update`** — `ctxpack/agent/session.py`, `services/decision_brief.py`, `services/framing_triggers.py`, `services/source_registry.py`
- **`verify`** — `api/routes/decision_signing.py`, `services/decision_signing.py`
- **`walk`** — `scripts/migrate_slate_classes.py`, `scripts/migrate_text_sizes.py`, `services/spl_section_parser.py`
- **`weighted_path`** — `api/routes/graph.py`, `services/graph_analytics.py`

## Shared Utilities (check these FIRST — `Grep` for functions)

### `ctxpack/core/` (65 exports, 23 classes/types)
- `CTXDocument` (class) — `ctxpack/core/model.py:151`
- `CrossRef` (class) — `ctxpack/core/model.py:93`
- `Diagnostic` (class) — `ctxpack/core/errors.py:35`
- `DiagnosticLevel` (class) — `ctxpack/core/errors.py:28`
- `DiffEntry` (class) — `ctxpack/core/diff.py:23`
- `DiffResult` (class) — `ctxpack/core/diff.py:32`
- `EntityGraph` (class) — `ctxpack/core/entity_graph.py:37`
- `Header` (class) — `ctxpack/core/model.py:123`
- `HydrationEvent` (class) — `ctxpack/core/telemetry.py:20`
- `HydrationResult` (class) — `ctxpack/core/hydrator.py:29`
- `InlineList` (class) — `ctxpack/core/model.py:65`
- `KeyValue` (class) — `ctxpack/core/model.py:51`
- *...and 11 more classes — `Grep` to find*

### `ctxpack/core/packer/` (47 exports, 18 classes/types)
- `CSVData` (class) — `ctxpack/core/packer/csv_parser.py:29`
- `Certainty` (class) — `ctxpack/core/packer/ir.py:29`
- `CompressionPreset` (class) — `ctxpack/core/packer/budget.py:22`
- `DiscoveryResult` (class) — `ctxpack/core/packer/discovery.py:28`
- `DomainTemplate` (class) — `ctxpack/core/packer/templates.py:28`
- `EntityBudget` (class) — `ctxpack/core/packer/budget.py:42`
- `EntitySchema` (class) — `ctxpack/core/packer/templates.py:19`
- `FieldBudget` (class) — `ctxpack/core/packer/budget.py:33`
- `IRCorpus` (class) — `ctxpack/core/packer/ir.py:108`
- `IREntity` (class) — `ctxpack/core/packer/ir.py:85`
- `IRField` (class) — `ctxpack/core/packer/ir.py:68`
- `IRRelationship` (class) — `ctxpack/core/packer/ir.py:53`
- *...and 6 more classes — `Grep` to find*

### `frontend/src/components/ui/` (10 exports, 5 classes/types)
- `DataTableColumn` (type) — `frontend/src/components/ui/DataTable.tsx:3`
- `DataTableProps` (type) — `frontend/src/components/ui/DataTable.tsx:11`
- `ErrorBoundary` (class) — `frontend/src/components/ui/ErrorBoundary.tsx:16`
- `ToastItem` (type) — `frontend/src/components/ui/Toast.tsx:111`
- `ToastProps` (type) — `frontend/src/components/ui/Toast.tsx:4`

### `frontend/src/hooks/` (21 exports, 7 classes/types)
- `AutosaveStatus` (type) — `frontend/src/hooks/useBriefAutosave.ts:14`
- `PlatformStats` (type) — `frontend/src/hooks/useHealthStats.ts:6`
- `UseAgentActivityResult` (type) — `frontend/src/hooks/useAgentActivity.ts:12`
- `UseBriefAutosaveResult` (type) — `frontend/src/hooks/useBriefAutosave.ts:16`
- `UseDossierResult` (type) — `frontend/src/hooks/useDossier.ts:15`
- `UseEvidenceDocumentsResult` (type) — `frontend/src/hooks/useEvidenceDocuments.ts:17`
- `UsePayoffMatrixResult` (type) — `frontend/src/hooks/usePayoffMatrix.ts:18`

### `frontend/src/lib/` (4 exports, 0 classes/types)

### `frontend/src/utils/` (10 exports, 3 classes/types)
- `DisplayProperty` (type) — `frontend/src/utils/inspector-helpers.ts:104`
- `LinkGroup` (type) — `frontend/src/utils/inspector-helpers.ts:124`
- `QueryType` (type) — `frontend/src/utils/query-patterns.ts:1`

### `services/` (559 exports, 162 classes/types)
- `AdjustmentReport` (class) — `services/concept_weight_adjuster.py:44`
- `AdversaryReactor` (class) — `services/war_game_adversary.py:188`
- `AdversarySpec` (class) — `services/war_game_adversary.py:48`
- `AppendOnlyViolation` (class) — `services/evidence_ledger.py:205`
- `AskEngine` (class) — `services/ask_engine.py:226`
- `AskResult` (class) — `services/ask_engine.py:163`
- `AuthError` (class) — `services/auth.py:52`
- `AutonomousResearchAgent` (class) — `services/research_agent.py:121`
- `BayesianAdversaryConfig` (class) — `services/game_theory.py:61`
- `BayesianRunConfig` (class) — `services/game_theory.py:69`
- `BriefImmutable` (class) — `services/decision_brief.py:174`
- `BriefNotEligible` (class) — `services/war_game_adversary.py:167`
- *...and 150 more classes — `Grep` to find*

### `services/agent/` (74 exports, 21 classes/types)
- `AgentEvent` (class) — `services/agent/event_stream.py:37`
- `AgentEventType` (class) — `services/agent/event_stream.py:22`
- `AgentSession` (class) — `services/agent/session_store.py:24`
- `BudgetStatus` (class) — `services/agent/budget.py:26`
- `EventStream` (class) — `services/agent/event_stream.py:54`
- `HarnessConfig` (class) — `services/agent/harness.py:35`
- `HarnessResult` (class) — `services/agent/harness.py:55`
- `JoinPath` (class) — `services/agent/schema_introspector.py:19`
- `MarketZeroHarness` (class) — `services/agent/harness.py:68`
- `PermissionDecision` (class) — `services/agent/permissions.py:46`
- `PermissionDenied` (class) — `services/agent/permissions.py:32`
- `PermissionEngine` (class) — `services/agent/permissions.py:59`
- *...and 9 more classes — `Grep` to find*

### `services/agent/graphs/` (6 exports, 3 classes/types)
- `PersonaInput` (class) — `services/agent/graphs/team_eval_graph.py:43`
- `QueryAgentState` (class) — `services/agent/graphs/query_graph.py:128`
- `TeamEvalState` (class) — `services/agent/graphs/team_eval_graph.py:29`

### `services/agent/tools/` (25 exports, 6 classes/types)
- `BaseTool` (class) — `services/agent/tools/base.py:58`
- `GraphSearchTool` (class) — `services/agent/tools/graph_tool.py:13`
- `MetricsQueryTool` (class) — `services/agent/tools/metrics_tool.py:13`
- `RAGSearchTool` (class) — `services/agent/tools/rag_tool.py:13`
- `SQLQueryTool` (class) — `services/agent/tools/sql_tool.py:30`
- `ToolResult` (class) — `services/agent/tools/base.py:11`

### `services/chat_handlers/` (30 exports, 1 classes/types)
- `Intent` (class) — `services/chat_handlers/intent.py:11`

### `services/event_emitters/` (15 exports, 0 classes/types)

### `services/extraction/` (15 exports, 15 classes/types)
- `BiologicProduct` (class) — `services/extraction/biologic_product.py:23`
- `CRLExtraction` (class) — `services/extraction/regulatory_crl.py:43`
- `ChmpOpinion` (class) — `services/extraction/ema_chmp_opinion.py:27`
- `DealExtraction` (class) — `services/extraction/deal_announced.py:39`
- `DrugDiscontinuation` (class) — `services/extraction/drug_discontinuation.py:26`
- `EfficacyOutcome` (class) — `services/extraction/trial_readout.py:52`
- `ExecChangeExtraction` (class) — `services/extraction/exec_change.py:40`
- `FdaDesignation` (class) — `services/extraction/fda_designation.py:33`
- `FinancialDisclosureExtraction` (class) — `services/extraction/financial_disclosure.py:66`
- `FinancialMetric` (class) — `services/extraction/financial_disclosure.py:32`
- `GuidanceIssuance` (class) — `services/extraction/financial_disclosure.py:117`
- `GuidanceMetric` (class) — `services/extraction/financial_disclosure.py:94`
- *...and 3 more classes — `Grep` to find*

### `services/simulation/` (1 exports, 0 classes/types)

## Other Directories

*`Grep` for specific symbols — counts only.*

- `./` — 70 exports
- `api/` — 72 exports
- `api/middleware/` — 5 exports
- `api/routes/` — 285 exports
- `apps/ci/src/` — 1 exports
- `apps/ci/src/components/` — 3 exports
- `apps/ci/src/surfaces/` — 1 exports
- `apps/landing/src/` — 1 exports
- `apps/landing/src/components/` — 7 exports
- `benchmark/` — 18 exports
- `connectors/` — 138 exports
- `connectors/sec_8k/` — 19 exports
- `ctxpack/agent/` — 10 exports
- `ctxpack/benchmarks/` — 51 exports
- `ctxpack/benchmarks/baselines/` — 10 exports
- `ctxpack/benchmarks/metrics/` — 19 exports
- `ctxpack/benchmarks/realworld/` — 18 exports
- `ctxpack/benchmarks/scaling/` — 11 exports
- `ctxpack/cli/` — 1 exports
- `ctxpack/integrations/` — 10 exports
