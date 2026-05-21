# Codebase Map

*Auto-generated: 2026-05-21 23:46*

## Stats

- **Python**: 507 files
- **TSX/React**: 210 files
- **TypeScript**: 45 files
- **JavaScript**: 17 files
- **Total source files**: 779

## Directory Structure

### `__init__.py/` (1 files)

- `__init__.py/` — 1 files

### `api/` (51 files)

- `api/__init__.py/` — 1 files
- `api/app.py/` — 1 files
- `api/deps.py/` — 1 files
- `api/exception_handlers.py/` — 1 files
- `api/mcp_server.py/` — 1 files
- `api/middleware/__init__.py/` — 1 files
- `api/middleware/rate_limit.py/` — 1 files
- `api/pagination.py/` — 1 files
- `api/routes/__init__.py/` — 1 files
- `api/routes/agent.py/` — 1 files
- `api/routes/agents_activity.py/` — 1 files
- `api/routes/ask.py/` — 1 files
- `api/routes/auth.py/` — 1 files
- `api/routes/bridge.py/` — 1 files
- `api/routes/catalog.py/` — 1 files
- `api/routes/chat.py/` — 1 files
- `api/routes/connectors.py/` — 1 files
- `api/routes/decision_briefs.py/` — 1 files
- `api/routes/decision_signing.py/` — 1 files
- `api/routes/decisions.py/` — 1 files
- `api/routes/dossier.py/` — 1 files
- `api/routes/enrichment.py/` — 1 files
- `api/routes/entities.py/` — 1 files
- `api/routes/evidence_batch.py/` — 1 files
- `api/routes/evidence_ledger.py/` — 1 files
- `api/routes/feedback.py/` — 1 files
- `api/routes/framing_triggers.py/` — 1 files
- `api/routes/game_theory.py/` — 1 files
- `api/routes/graph.py/` — 1 files
- `api/routes/inbox.py/` — 1 files
- `api/routes/intelligence.py/` — 1 files
- `api/routes/learning.py/` — 1 files
- `api/routes/literature.py/` — 1 files
- `api/routes/llm_gateway.py/` — 1 files
- `api/routes/materiality.py/` — 1 files
- `api/routes/metrics.py/` — 1 files
- `api/routes/pricing.py/` — 1 files
- `api/routes/query.py/` — 1 files
- `api/routes/recommendations.py/` — 1 files
- `api/routes/scenarios.py/` — 1 files
- `api/routes/search.py/` — 1 files
- `api/routes/signals.py/` — 1 files
- `api/routes/sources.py/` — 1 files
- `api/routes/steward.py/` — 1 files
- `api/routes/therapeutic_areas.py/` — 1 files
- `api/routes/upload.py/` — 1 files
- `api/routes/war_games.py/` — 1 files
- `api/routes/war_room.py/` — 1 files
- `api/routes/watchlist.py/` — 1 files
- `api/schemas.py/` — 1 files
- `api/utils.py/` — 1 files

### `apps/` (13 files)

- `apps/ci/src/` — 5 files
- `apps/ci/vite.config.ts/` — 1 files
- `apps/landing/src/` — 6 files
- `apps/landing/vite.config.ts/` — 1 files

### `backfill_data_linkage.py/` (1 files)

- `backfill_data_linkage.py/` — 1 files

### `backfill_embeddings.py/` (1 files)

- `backfill_embeddings.py/` — 1 files

### `backfill_resolution.py/` (1 files)

- `backfill_resolution.py/` — 1 files

### `benchmark/` (5 files)

- `benchmark/__init__.py/` — 1 files
- `benchmark/capture_responses.py/` — 1 files
- `benchmark/ci_eval.py/` — 1 files
- `benchmark/eval_runner.py/` — 1 files
- `benchmark/scorers.py/` — 1 files

### `comp_intel.tsx/` (1 files)

- `comp_intel.tsx/` — 1 files

### `config.py/` (1 files)

- `config.py/` — 1 files

### `connectors/` (32 files)

- `connectors/__init__.py/` — 1 files
- `connectors/base.py/` — 1 files
- `connectors/chembl.py/` — 1 files
- `connectors/clinical_trials.py/` — 1 files
- `connectors/cms_asp.py/` — 1 files
- `connectors/dailymed_spl.py/` — 1 files
- `connectors/ema.py/` — 1 files
- `connectors/ema_chmp.py/` — 1 files
- `connectors/enrichment_runner.py/` — 1 files
- `connectors/fda_designations.py/` — 1 files
- `connectors/fda_discontinuations.py/` — 1 files
- `connectors/fda_purple_book.py/` — 1 files
- `connectors/fda_shortages.py/` — 1 files
- `connectors/mesh.py/` — 1 files
- `connectors/nadac.py/` — 1 files
- `connectors/news.py/` — 1 files
- `connectors/open_targets.py/` — 1 files
- `connectors/openfda_faers.py/` — 1 files
- `connectors/openfda_labels.py/` — 1 files
- `connectors/orange_book.py/` — 1 files
- `connectors/pmc.py/` — 1 files
- `connectors/pubchem.py/` — 1 files
- `connectors/pubmed.py/` — 1 files
- `connectors/sec_8k/__init__.py/` — 1 files
- `connectors/sec_8k/item_1_01.py/` — 1 files
- `connectors/sec_8k/item_2_02.py/` — 1 files
- `connectors/sec_8k/item_5_02.py/` — 1 files
- `connectors/sec_8k/item_8_01.py/` — 1 files
- `connectors/sec_edgar.py/` — 1 files
- `connectors/sec_edgar_8k_runner.py/` — 1 files
- `connectors/user_document.py/` — 1 files
- `connectors/uspto_patentsview.py/` — 1 files

### `ctxpack/` (83 files)

- `ctxpack/__init__.py/` — 1 files
- `ctxpack/agent/__init__.py/` — 1 files
- `ctxpack/agent/session.py/` — 1 files
- `ctxpack/agent/state_parser.py/` — 1 files
- `ctxpack/benchmarks/__init__.py/` — 1 files
- `ctxpack/benchmarks/ablation_runner.py/` — 1 files
- `ctxpack/benchmarks/baselines/` — 8 files
- `ctxpack/benchmarks/bench.py/` — 1 files
- `ctxpack/benchmarks/definitive_eval.py/` — 1 files
- `ctxpack/benchmarks/dotenv.py/` — 1 files
- `ctxpack/benchmarks/eval_config.py/` — 1 files
- `ctxpack/benchmarks/gemini_eval.py/` — 1 files
- `ctxpack/benchmarks/hydration_eval.py/` — 1 files
- `ctxpack/benchmarks/metrics/` — 5 files
- `ctxpack/benchmarks/model_affinity_eval.py/` — 1 files
- `ctxpack/benchmarks/rate_distortion.py/` — 1 files
- `ctxpack/benchmarks/realworld/` — 4 files
- `ctxpack/benchmarks/reasoning_model_eval.py/` — 1 files
- `ctxpack/benchmarks/runner.py/` — 1 files
- `ctxpack/benchmarks/save_extension_results.py/` — 1 files
- `ctxpack/benchmarks/scaling/` — 5 files
- `ctxpack/benchmarks/scaling_eval.py/` — 1 files
- `ctxpack/benchmarks/tokenizer_mapping.py/` — 1 files
- `ctxpack/cli/__init__.py/` — 1 files
- `ctxpack/cli/main.py/` — 1 files
- `ctxpack/core/__init__.py/` — 1 files
- `ctxpack/core/diff.py/` — 1 files
- `ctxpack/core/entity_graph.py/` — 1 files
- `ctxpack/core/errors.py/` — 1 files
- `ctxpack/core/hydration_protocol.py/` — 1 files
- `ctxpack/core/hydrator.py/` — 1 files
- `ctxpack/core/json_export.py/` — 1 files
- `ctxpack/core/model.py/` — 1 files
- `ctxpack/core/operators.py/` — 1 files
- `ctxpack/core/packer/` — 17 files
- `ctxpack/core/parser.py/` — 1 files
- `ctxpack/core/serializer.py/` — 1 files
- `ctxpack/core/telemetry.py/` — 1 files
- `ctxpack/core/validator.py/` — 1 files
- `ctxpack/integrations/__init__.py/` — 1 files
- `ctxpack/integrations/__main__.py/` — 1 files
- `ctxpack/integrations/mcp_server.py/` — 1 files
- `ctxpack/modules/__init__.py/` — 1 files
- `ctxpack/modules/analytics.py/` — 1 files
- `ctxpack/modules/catalog_queries.py/` — 1 files
- `ctxpack/modules/codebase.py/` — 1 files
- `ctxpack/modules/grounding.py/` — 1 files
- `ctxpack/modules/guard.py/` — 1 files
- `ctxpack/modules/keywords.py/` — 1 files

### `db.py/` (1 files)

- `db.py/` — 1 files

### `design-review-output/` (16 files)

- `design-review-output/_build/_lib.js/` — 1 files
- `design-review-output/_build/api-mapping.js/` — 1 files
- `design-review-output/_build/data-layer-audit.js/` — 1 files
- `design-review-output/_build/executive-summary.js/` — 1 files
- `design-review-output/_build/phase1-recon.js/` — 1 files
- `design-review-output/_build/phase2-persona.js/` — 1 files
- `design-review-output/_build/phase3-heuristics.js/` — 1 files
- `design-review-output/_build/phase4-aesthetic.js/` — 1 files
- `design-review-output/_build/phase5-gaps.js/` — 1 files
- `design-review-output/_build/phase6-demo.js/` — 1 files
- `design-review-output/_build/phase7-response.js/` — 1 files
- `design-review-output/_build/phase8-verification.js/` — 1 files
- `design-review-output/_build/phase9-backlog.js/` — 1 files
- `design-review-output/_build/phase9-instruction-set.js/` — 1 files
- `design-review-output/_build/phase9-tech-specs.js/` — 1 files
- `design-review-output/_build/v3-positioning.js/` — 1 files

### `domain/` (9 files)

- `domain/__init__.py/` — 1 files
- `domain/pharma/__init__.py/` — 1 files
- `domain/pharma/mention_normalizer.py/` — 1 files
- `domain/pharma/modality.py/` — 1 files
- `domain/pharma/pack.py/` — 1 files
- `domain/registry.py/` — 1 files
- `domain/schema.py/` — 1 files
- `domain/ta_definitions/__init__.py/` — 1 files
- `domain/ta_definitions/schema.py/` — 1 files

### `fair_analysis.py/` (1 files)

- `fair_analysis.py/` — 1 files

### `fix_data_quality.py/` (1 files)

- `fix_data_quality.py/` — 1 files

### `frontend/` (224 files)

- `frontend/__tests__/ci/` — 19 files
- `frontend/__tests__/design-system/` — 4 files
- `frontend/__tests__/feedback/` — 4 files
- `frontend/__tests__/helix/` — 2 files
- `frontend/__tests__/hooks/` — 3 files
- `frontend/__tests__/loop10/` — 1 files
- `frontend/__tests__/pages/` — 2 files
- `frontend/__tests__/primitives/` — 11 files
- `frontend/demo.tsx/` — 1 files
- `frontend/eslint.config.js/` — 1 files
- `frontend/src/App.tsx/` — 1 files
- `frontend/src/api.ts/` — 1 files
- `frontend/src/brand.ts/` — 1 files
- `frontend/src/components/` — 139 files
- `frontend/src/hooks/` — 11 files
- `frontend/src/lib/` — 1 files
- `frontend/src/main.tsx/` — 1 files
- `frontend/src/pages/` — 9 files
- `frontend/src/test/` — 1 files
- `frontend/src/types/` — 7 files
- `frontend/src/utils/` — 2 files
- `frontend/vite.config.ts/` — 1 files
- `frontend/vitest.config.ts/` — 1 files

### `integration/` (12 files)

- `integration/__init__.py/` — 1 files
- `integration/company_identity.py/` — 1 files
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

### `packages/` (16 files)

- `packages/design-tokens/src/` — 1 files
- `packages/ui/.storybook/` — 2 files
- `packages/ui/src/` — 12 files
- `packages/ui/vitest.config.ts/` — 1 files

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

### `scripts/` (24 files)

- `scripts/__init__.py/` — 1 files
- `scripts/ai_enrich.py/` — 1 files
- `scripts/auto_curate.py/` — 1 files
- `scripts/auto_curate_v2.py/` — 1 files
- `scripts/backfill_mechanisms.py/` — 1 files
- `scripts/backfill_sponsor_links.py/` — 1 files
- `scripts/backfill_ta_links.py/` — 1 files
- `scripts/clean_drug_names.py/` — 1 files
- `scripts/consolidate_drugs.py/` — 1 files
- `scripts/dedup_companies.py/` — 1 files
- `scripts/derive_competition.py/` — 1 files
- `scripts/enrich_companies.py/` — 1 files
- `scripts/enrich_drugs.py/` — 1 files
- `scripts/extract_biomarkers.py/` — 1 files
- `scripts/fetch_nadac_pricing.py/` — 1 files
- `scripts/fetch_who_gprm.py/` — 1 files
- `scripts/migrate_legacy_backlogs.py/` — 1 files
- `scripts/migrate_slate_classes.py/` — 1 files
- `scripts/migrate_text_sizes.py/` — 1 files
- `scripts/onboard_ta.py/` — 1 files
- `scripts/quality_scorecard.py/` — 1 files
- `scripts/seed_demo_users.py/` — 1 files
- `scripts/snapshot_openapi.py/` — 1 files
- `scripts/validate_product_backlog.py/` — 1 files

### `seed_quality_and_catalog.py/` (1 files)

- `seed_quality_and_catalog.py/` — 1 files

### `semantic/` (1 files)

- `semantic/__init__.py/` — 1 files

### `services/` (118 files)

- `services/__init__.py/` — 1 files
- `services/agent/__init__.py/` — 1 files
- `services/agent/budget.py/` — 1 files
- `services/agent/event_stream.py/` — 1 files
- `services/agent/graphs/` — 3 files
- `services/agent/harness.py/` — 1 files
- `services/agent/llm_provider.py/` — 1 files
- `services/agent/permissions.py/` — 1 files
- `services/agent/presenter.py/` — 1 files
- `services/agent/registry.py/` — 1 files
- `services/agent/schema_introspector.py/` — 1 files
- `services/agent/session_store.py/` — 1 files
- `services/agent/tools/` — 6 files
- `services/ask_engine.py/` — 1 files
- `services/auth.py/` — 1 files
- `services/calibration_math.py/` — 1 files
- `services/chat_handlers/__init__.py/` — 1 files
- `services/chat_handlers/context.py/` — 1 files
- `services/chat_handlers/formatting.py/` — 1 files
- `services/chat_handlers/handlers.py/` — 1 files
- `services/chat_handlers/intent.py/` — 1 files
- `services/concept_registry.py/` — 1 files
- `services/concept_weight_adjuster.py/` — 1 files
- `services/connector_registry.py/` — 1 files
- `services/conversation_memory.py/` — 1 files
- `services/counter_recommendation.py/` — 1 files
- `services/ctgov_diff_service.py/` — 1 files
- `services/ctx_context.py/` — 1 files
- `services/ctx_corpus.py/` — 1 files
- `services/ctx_evidence.py/` — 1 files
- `services/ctx_pipeline.py/` — 1 files
- `services/data_steward.py/` — 1 files
- `services/db_adapter_8k.py/` — 1 files
- `services/decision_brief.py/` — 1 files
- `services/decision_signing.py/` — 1 files
- `services/document_extractor.py/` — 1 files
- `services/document_ner.py/` — 1 files
- `services/dossier.py/` — 1 files
- `services/ema_chmp_parser.py/` — 1 files
- `services/entity_agents.py/` — 1 files
- `services/entity_canonicalizer.py/` — 1 files
- `services/event_collector.py/` — 1 files
- `services/event_emitters/__init__.py/` — 1 files
- `services/event_emitters/biosimilar_approval.py/` — 1 files
- `services/event_emitters/deal_announced.py/` — 1 files
- `services/event_emitters/drug_discontinuation.py/` — 1 files
- `services/event_emitters/ema_chmp_opinion.py/` — 1 files
- `services/event_emitters/exec_change.py/` — 1 files
- `services/event_emitters/fda_designation.py/` — 1 files
- `services/event_emitters/financial_disclosure.py/` — 1 files
- `services/event_emitters/label_change.py/` — 1 files
- `services/event_emitters/patent_grant.py/` — 1 files
- `services/event_emitters/pricing_observation.py/` — 1 files
- `services/event_emitters/regulatory_crl.py/` — 1 files
- `services/event_emitters/trial_readout.py/` — 1 files
- `services/evidence_ledger.py/` — 1 files
- `services/extraction/__init__.py/` — 1 files
- `services/extraction/biologic_product.py/` — 1 files
- `services/extraction/deal_announced.py/` — 1 files
- `services/extraction/drug_discontinuation.py/` — 1 files
- `services/extraction/ema_chmp_opinion.py/` — 1 files
- `services/extraction/exec_change.py/` — 1 files
- `services/extraction/fda_designation.py/` — 1 files
- `services/extraction/financial_disclosure.py/` — 1 files
- `services/extraction/patent.py/` — 1 files
- `services/extraction/pricing_observation.py/` — 1 files
- `services/extraction/regulatory_crl.py/` — 1 files
- `services/extraction/trial_readout.py/` — 1 files
- `services/extraction_llm.py/` — 1 files
- `services/fair_scorer.py/` — 1 files
- `services/feedback_loops.py/` — 1 files
- `services/few_shot_library.py/` — 1 files
- `services/framing_triggers.py/` — 1 files
- `services/game_theory.py/` — 1 files
- `services/graph.py/` — 1 files
- `services/graph_analytics.py/` — 1 files
- `services/impact_router.py/` — 1 files
- `services/insight_engine.py/` — 1 files
- `services/intelligence_feed.py/` — 1 files
- `services/learning_service.py/` — 1 files
- `services/literature.py/` — 1 files
- `services/llm.py/` — 1 files
- `services/llm_gateway.py/` — 1 files
- `services/llm_quota.py/` — 1 files
- `services/llm_telemetry.py/` — 1 files
- `services/materiality.py/` — 1 files
- `services/metrics.py/` — 1 files
- `services/move_suggester.py/` — 1 files
- `services/outcome_detector.py/` — 1 files
- `services/outcome_scheduler.py/` — 1 files
- `services/person_roles.py/` — 1 files
- `services/query_engine.py/` — 1 files
- `services/query_telemetry.py/` — 1 files
- `services/research_agent.py/` — 1 files
- `services/scenario_engine.py/` — 1 files
- `services/search.py/` — 1 files
- `services/sec_8k_pipeline.py/` — 1 files
- `services/simulation/__init__.py/` — 1 files
- `services/simulation/payoff.py/` — 1 files
- `services/source_registry.py/` — 1 files
- `services/spl_diff_service.py/` — 1 files
- `services/spl_section_parser.py/` — 1 files
- `services/steward_signals.py/` — 1 files
- `services/telemetry.py/` — 1 files
- `services/trial_alias_seeder.py/` — 1 files
- `services/trial_status_history.py/` — 1 files
- `services/unified_handler.py/` — 1 files
- `services/war_game_adversary.py/` — 1 files
- `services/war_game_engine.py/` — 1 files
- `services/web_research.py/` — 1 files
- `services/workspace.py/` — 1 files

### `specs/` (2 files)

- `specs/helix_proto.tsx/` — 1 files
- `specs/test.tsx/` — 1 files

### `start.py/` (1 files)

- `start.py/` — 1 files

### `tests/` (154 files)

- `tests/__init__.py/` — 1 files
- `tests/agent/__init__.py/` — 1 files
- `tests/agent/conftest.py/` — 1 files
- `tests/agent/test_query_graph_contracts.py/` — 1 files
- `tests/agent/test_team_eval_contracts.py/` — 1 files
- `tests/agent/test_team_eval_integration.py/` — 1 files
- `tests/conftest.py/` — 1 files
- `tests/test_a1_1_companies_schema.py/` — 1 files
- `tests/test_a1_2_drugs_schema.py/` — 1 files
- `tests/test_a1_3_trials_status_history.py/` — 1 files
- `tests/test_a1_4_persons_roles_history.py/` — 1 files
- `tests/test_a1_5_and_a1_6_patents_deals.py/` — 1 files
- `tests/test_a1_7_signals_table.py/` — 1 files
- `tests/test_a2_1_item_5_02_parser.py/` — 1 files
- `tests/test_a2_2_item_1_01_parser.py/` — 1 files
- `tests/test_a2_3_item_2_02_parser.py/` — 1 files
- `tests/test_a2_4_item_8_01_crl.py/` — 1 files
- `tests/test_agent_api.py/` — 1 files
- `tests/test_agent_router_rollout.py/` — 1 files
- `tests/test_agents_activity.py/` — 1 files
- `tests/test_alpha1_extraction_llm.py/` — 1 files
- `tests/test_alpha2_sec_orchestration.py/` — 1 files
- `tests/test_alpha3_db_adapter.py/` — 1 files
- `tests/test_ask_api.py/` — 1 files
- `tests/test_auth.py/` — 1 files
- `tests/test_auto_curate_v2.py/` — 1 files
- `tests/test_backfill_mechanisms.py/` — 1 files
- `tests/test_backfill_ta_links.py/` — 1 files
- `tests/test_be003_agent_name.py/` — 1 files
- `tests/test_be006_dossier_composer.py/` — 1 files
- `tests/test_be008_payoff_matrix.py/` — 1 files
- `tests/test_bridge_moments.py/` — 1 files
- `tests/test_catalog_api.py/` — 1 files
- `tests/test_ci_benchmark.py/` — 1 files
- `tests/test_citation_validation.py/` — 1 files
- `tests/test_clean_drug_names.py/` — 1 files
- `tests/test_compare_graph.py/` — 1 files
- `tests/test_competition.py/` — 1 files
- `tests/test_compound_intent.py/` — 1 files
- `tests/test_concept_activation.py/` — 1 files
- `tests/test_concept_registry.py/` — 1 files
- `tests/test_concept_weight_adjuster.py/` — 1 files
- `tests/test_confidence_scoring.py/` — 1 files
- `tests/test_connector_overrides.py/` — 1 files
- `tests/test_connector_registry.py/` — 1 files
- `tests/test_connectors_api.py/` — 1 files
- `tests/test_consolidate_drugs.py/` — 1 files
- `tests/test_conversation_memory.py/` — 1 files
- `tests/test_counter_recommendation_api.py/` — 1 files
- `tests/test_cross_linker.py/` — 1 files
- `tests/test_ctx_corpus.py/` — 1 files
- `tests/test_ctx_evidence.py/` — 1 files
- `tests/test_ctx_guard_default.py/` — 1 files
- `tests/test_ctx_pipeline.py/` — 1 files
- `tests/test_cycle10_uspto_patentsview.py/` — 1 files
- `tests/test_cycle11_fda_purple_book.py/` — 1 files
- `tests/test_cycle12_cms_asp_pricing.py/` — 1 files
- `tests/test_cycle1_sec_edgar_runner.py/` — 1 files
- `tests/test_cycle2_ctgov_diff_service.py/` — 1 files
- `tests/test_cycle3_trial_alias_seeder.py/` — 1 files
- `tests/test_cycle4_trial_readout.py/` — 1 files
- `tests/test_cycle5_dailymed_spl.py/` — 1 files
- `tests/test_cycle6_spl_diff_service.py/` — 1 files
- `tests/test_cycle7_ema_chmp.py/` — 1 files
- `tests/test_cycle8_fda_designations.py/` — 1 files
- `tests/test_cycle9_fda_discontinuations.py/` — 1 files
- `tests/test_d2_calibration_math.py/` — 1 files
- `tests/test_d2_llm_quota.py/` — 1 files
- `tests/test_d2_outcome_scheduler.py/` — 1 files
- `tests/test_d2_pagination.py/` — 1 files
- `tests/test_d2_rate_limit.py/` — 1 files
- `tests/test_d2_telemetry_and_envelope.py/` — 1 files
- `tests/test_data_steward.py/` — 1 files
- `tests/test_decision_briefs_api.py/` — 1 files
- `tests/test_decision_signing_api.py/` — 1 files
- `tests/test_decisions_api.py/` — 1 files
- `tests/test_dedup_companies.py/` — 1 files
- `tests/test_dlq.py/` — 1 files
- `tests/test_document_extractor.py/` — 1 files
- `tests/test_document_ner.py/` — 1 files
- `tests/test_domain_coverage.py/` — 1 files
- `tests/test_drug_pricing.py/` — 1 files
- `tests/test_ema_connector.py/` — 1 files
- `tests/test_enrichment.py/` — 1 files
- `tests/test_entity_agents.py/` — 1 files
- `tests/test_entity_canonicalizer.py/` — 1 files
- `tests/test_entity_dossier.py/` — 1 files
- `tests/test_entity_profile.py/` — 1 files
- `tests/test_entity_resolution.py/` — 1 files
- `tests/test_entity_resolver_cascade.py/` — 1 files
- `tests/test_eval_benchmark.py/` — 1 files
- `tests/test_event_collector.py/` — 1 files
- `tests/test_event_stream.py/` — 1 files
- `tests/test_evidence_batch.py/` — 1 files
- `tests/test_evidence_ledger_api.py/` — 1 files
- `tests/test_fair_scorer.py/` — 1 files
- `tests/test_feedback_api.py/` — 1 files
- `tests/test_feedback_loops.py/` — 1 files
- `tests/test_few_shot_library.py/` — 1 files
- `tests/test_framing_triggers_api.py/` — 1 files
- `tests/test_game_theory_api.py/` — 1 files
- `tests/test_graph_analytics.py/` — 1 files
- `tests/test_graph_entity_map.py/` — 1 files
- `tests/test_graph_truncation.py/` — 1 files
- `tests/test_harness.py/` — 1 files
- `tests/test_harness_integration.py/` — 1 files
- `tests/test_ie_pattern_grounding.py/` — 1 files
- `tests/test_impact_router.py/` — 1 files
- `tests/test_inbox_api.py/` — 1 files
- `tests/test_insight_engine.py/` — 1 files
- `tests/test_intelligence_feed.py/` — 1 files
- `tests/test_intent_planning_hints.py/` — 1 files
- `tests/test_learning_service_api.py/` — 1 files
- `tests/test_literature.py/` — 1 files
- `tests/test_llm_gateway_api.py/` — 1 files
- `tests/test_materiality_api.py/` — 1 files
- `tests/test_memory_persistence.py/` — 1 files
- `tests/test_mention_normalizer.py/` — 1 files
- `tests/test_molecule_canonicalization.py/` — 1 files
- `tests/test_move_suggester.py/` — 1 files
- `tests/test_mv_fallback.py/` — 1 files
- `tests/test_narrative_verification.py/` — 1 files
- `tests/test_outcome_detector.py/` — 1 files
- `tests/test_permissions.py/` — 1 files
- `tests/test_pipeline_intent_drug.py/` — 1 files
- `tests/test_product_backlog.py/` — 1 files
- `tests/test_quality_monitor.py/` — 1 files
- `tests/test_query_graph_intent_hint.py/` — 1 files
- `tests/test_query_graph_smoke.py/` — 1 files
- `tests/test_query_telemetry.py/` — 1 files
- `tests/test_research_agent.py/` — 1 files
- `tests/test_resolution_monitoring.py/` — 1 files
- `tests/test_role_gates.py/` — 1 files
- `tests/test_scenario_primitives.py/` — 1 files
- `tests/test_schema_drift_fix.py/` — 1 files
- `tests/test_search_enriched.py/` — 1 files
- `tests/test_sec_xbrl.py/` — 1 files
- `tests/test_session_store.py/` — 1 files
- `tests/test_signals_api.py/` — 1 files
- `tests/test_source_profile.py/` — 1 files
- `tests/test_source_registry_api.py/` — 1 files
- `tests/test_steward_signals.py/` — 1 files
- `tests/test_ta_definitions.py/` — 1 files
- `tests/test_temporal_scoring.py/` — 1 files
- `tests/test_token_budget.py/` — 1 files
- `tests/test_tool_registry.py/` — 1 files
- `tests/test_unified_handler.py/` — 1 files
- `tests/test_upload_persistence.py/` — 1 files
- `tests/test_user_document_connector.py/` — 1 files
- `tests/test_war_game_adversaries_api.py/` — 1 files
- `tests/test_war_game_engine.py/` — 1 files
- `tests/test_war_room_api.py/` — 1 files
- `tests/test_watchlist_api.py/` — 1 files
- `tests/test_who_gprm.py/` — 1 files

## Key Entry Points

- `apps/api/app/main.py` — Backend app factory [MISSING]
- `apps/api/app/api/v1/router.py` — API route registration [MISSING]
- `apps/api/app/db.py` — Database engine and session [MISSING]
- `apps/api/app/config.py` — Backend settings [MISSING]
- `apps/web/app/layout.tsx` — Frontend root layout [MISSING]
- `apps/web/lib/api.ts` — Frontend API client (fetchJson) [MISSING]
- `apps/web/lib/api-platform.ts` — Platform API functions [MISSING]
- `apps/web/lib/api-domains.ts` — Domain API functions [MISSING]
