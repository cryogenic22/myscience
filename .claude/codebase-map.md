# Codebase Map

*Auto-generated: 2026-03-20 23:14*

## Stats

- **Python**: 116 files
- **TSX/React**: 27 files
- **TypeScript**: 6 files
- **JavaScript**: 1 files
- **Total source files**: 150

## Directory Structure

### `__init__.py/` (1 files)

- `__init__.py/` — 1 files

### `api/` (15 files)

- `api/__init__.py/` — 1 files
- `api/app.py/` — 1 files
- `api/deps.py/` — 1 files
- `api/mcp_server.py/` — 1 files
- `api/routes/__init__.py/` — 1 files
- `api/routes/catalog.py/` — 1 files
- `api/routes/chat.py/` — 1 files
- `api/routes/entities.py/` — 1 files
- `api/routes/graph.py/` — 1 files
- `api/routes/metrics.py/` — 1 files
- `api/routes/query.py/` — 1 files
- `api/routes/search.py/` — 1 files
- `api/routes/therapeutic_areas.py/` — 1 files
- `api/schemas.py/` — 1 files
- `api/utils.py/` — 1 files

### `backfill_data_linkage.py/` (1 files)

- `backfill_data_linkage.py/` — 1 files

### `backfill_embeddings.py/` (1 files)

- `backfill_embeddings.py/` — 1 files

### `backfill_resolution.py/` (1 files)

- `backfill_resolution.py/` — 1 files

### `config.py/` (1 files)

- `config.py/` — 1 files

### `connectors/` (11 files)

- `connectors/__init__.py/` — 1 files
- `connectors/base.py/` — 1 files
- `connectors/clinical_trials.py/` — 1 files
- `connectors/fda_shortages.py/` — 1 files
- `connectors/mesh.py/` — 1 files
- `connectors/openfda_faers.py/` — 1 files
- `connectors/openfda_labels.py/` — 1 files
- `connectors/orange_book.py/` — 1 files
- `connectors/pmc.py/` — 1 files
- `connectors/pubmed.py/` — 1 files
- `connectors/sec_edgar.py/` — 1 files

### `db.py/` (1 files)

- `db.py/` — 1 files

### `domain/` (8 files)

- `domain/__init__.py/` — 1 files
- `domain/pharma/__init__.py/` — 1 files
- `domain/pharma/mention_normalizer.py/` — 1 files
- `domain/pharma/pack.py/` — 1 files
- `domain/registry.py/` — 1 files
- `domain/schema.py/` — 1 files
- `domain/ta_definitions/__init__.py/` — 1 files
- `domain/ta_definitions/schema.py/` — 1 files

### `fair_analysis.py/` (1 files)

- `fair_analysis.py/` — 1 files

### `fix_data_quality.py/` (1 files)

- `fix_data_quality.py/` — 1 files

### `frontend/` (34 files)

- `frontend/eslint.config.js/` — 1 files
- `frontend/src/App.tsx/` — 1 files
- `frontend/src/api.ts/` — 1 files
- `frontend/src/brand.ts/` — 1 files
- `frontend/src/components/` — 21 files
- `frontend/src/hooks/` — 3 files
- `frontend/src/main.tsx/` — 1 files
- `frontend/src/pages/` — 4 files
- `frontend/vite.config.ts/` — 1 files

### `integration/` (11 files)

- `integration/__init__.py/` — 1 files
- `integration/cross_linker.py/` — 1 files
- `integration/data_quality.py/` — 1 files
- `integration/dataset_catalog.py/` — 1 files
- `integration/embedder.py/` — 1 files
- `integration/entity_consolidator.py/` — 1 files
- `integration/entity_resolver.py/` — 1 files
- `integration/knowledge_store.py/` — 1 files
- `integration/normalizer.py/` — 1 files
- `integration/pipeline.py/` — 1 files
- `integration/pipeline_hooks.py/` — 1 files

### `migrate.py/` (1 files)

- `migrate.py/` — 1 files

### `process_unresolved.py/` (1 files)

- `process_unresolved.py/` — 1 files

### `run_consolidation.py/` (1 files)

- `run_consolidation.py/` — 1 files

### `run_scenario_tests.py/` (1 files)

- `run_scenario_tests.py/` — 1 files

### `scheduler/` (4 files)

- `scheduler/__init__.py/` — 1 files
- `scheduler/__main__.py/` — 1 files
- `scheduler/config.py/` — 1 files
- `scheduler/runner.py/` — 1 files

### `scripts/` (10 files)

- `scripts/__init__.py/` — 1 files
- `scripts/ai_enrich.py/` — 1 files
- `scripts/auto_curate.py/` — 1 files
- `scripts/backfill_ta_links.py/` — 1 files
- `scripts/clean_drug_names.py/` — 1 files
- `scripts/dedup_companies.py/` — 1 files
- `scripts/enrich_companies.py/` — 1 files
- `scripts/enrich_drugs.py/` — 1 files
- `scripts/onboard_ta.py/` — 1 files
- `scripts/quality_scorecard.py/` — 1 files

### `seed_quality_and_catalog.py/` (1 files)

- `seed_quality_and_catalog.py/` — 1 files

### `semantic/` (1 files)

- `semantic/__init__.py/` — 1 files

### `services/` (29 files)

- `services/__init__.py/` — 1 files
- `services/agent/__init__.py/` — 1 files
- `services/agent/graphs/` — 3 files
- `services/agent/llm_provider.py/` — 1 files
- `services/agent/presenter.py/` — 1 files
- `services/agent/schema_introspector.py/` — 1 files
- `services/agent/tools/` — 6 files
- `services/conversation_memory.py/` — 1 files
- `services/ctx_context.py/` — 1 files
- `services/ctx_corpus.py/` — 1 files
- `services/ctx_evidence.py/` — 1 files
- `services/ctx_pipeline.py/` — 1 files
- `services/graph.py/` — 1 files
- `services/llm.py/` — 1 files
- `services/metrics.py/` — 1 files
- `services/query_engine.py/` — 1 files
- `services/research_agent.py/` — 1 files
- `services/search.py/` — 1 files
- `services/telemetry.py/` — 1 files
- `services/unified_handler.py/` — 1 files
- `services/web_research.py/` — 1 files
- `services/workspace.py/` — 1 files

### `tests/` (14 files)

- `tests/__init__.py/` — 1 files
- `tests/agent/__init__.py/` — 1 files
- `tests/agent/conftest.py/` — 1 files
- `tests/agent/test_query_graph_contracts.py/` — 1 files
- `tests/agent/test_team_eval_contracts.py/` — 1 files
- `tests/agent/test_team_eval_integration.py/` — 1 files
- `tests/conftest.py/` — 1 files
- `tests/test_conversation_memory.py/` — 1 files
- `tests/test_ctx_corpus.py/` — 1 files
- `tests/test_ctx_evidence.py/` — 1 files
- `tests/test_ctx_pipeline.py/` — 1 files
- `tests/test_domain_coverage.py/` — 1 files
- `tests/test_research_agent.py/` — 1 files
- `tests/test_unified_handler.py/` — 1 files

## Key Entry Points

- `apps/api/app/main.py` — Backend app factory [MISSING]
- `apps/api/app/api/v1/router.py` — API route registration [MISSING]
- `apps/api/app/db.py` — Database engine and session [MISSING]
- `apps/api/app/config.py` — Backend settings [MISSING]
- `apps/web/app/layout.tsx` — Frontend root layout [MISSING]
- `apps/web/lib/api.ts` — Frontend API client (fetchJson) [MISSING]
- `apps/web/lib/api-platform.ts` — Platform API functions [MISSING]
- `apps/web/lib/api-domains.ts` — Domain API functions [MISSING]
