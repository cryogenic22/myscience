# SPEC-017: Sibling Project Reuse Catalog

*Date: 19 April 2026*
*Source surveys: Explore-agent reports on agentfuel, Proto_Demo, ProtoCode, Content_medical_hub*
*Status: catalog (informs SPEC_010-016 implementation, doesn't replace them)*

---

## Purpose

Document concrete reusable assets from four sibling projects (`agentfuel`, `Proto_Demo`, `ProtoCode`, `Content_medical_hub`) that accelerate Market Zero's existing SPEC_010 — SPEC_016 work. Each entry includes:
- Source file path (sibling project)
- Target Market Zero location
- Decision: **import** (use directly), **port** (copy + adapt), or **inspire** (read for ideas, write fresh)
- Effort estimate
- Acceptance criteria when integrated

This spec is not an implementation plan — it is a reference index that the per-phase TDD specs (SPEC_010 through SPEC_016) consult when building.

---

## Tier 1 — Direct ports (immediate value, low effort)

### 1.1 Document text extractor

| Field | Value |
|-------|-------|
| **Source** | `Proto_Demo/src/formatter/extractor.py` (`FormattingExtractor` class) + `src/formatter/ingest/` adapters |
| **What it does** | PDF (PyMuPDF), DOCX (python-docx), HTML (stdlib) text extraction with position/font/formatting metadata |
| **Decision** | **Port** — drop the `FormattedDocument` IR (overkill for our NER use case), keep the per-page extraction |
| **Target** | `services/document_extractor.py` (per SPEC_014 §3 implementation step 2) |
| **Effort** | 1-2 days (1 day port + 1 day adapt tests + dependencies) |
| **Acceptance** | All tests in `tests/test_document_extractor.py` pass: PDF/DOCX/HTML/text supported, size limit enforced, unsupported format raises |
| **Sibling code patterns to keep** | `fitz.open(stream=pdf_bytes, filetype="pdf")` per-page extraction; encoding detection for HTML |
| **Things to drop** | `FormattedDocument` paragraph/line/span hierarchy; we just need `pages: list[str]` |

### 1.2 Multi-provider LLM client (Anthropic + OpenAI + Azure)

| Field | Value |
|-------|-------|
| **Source** | `Proto_Demo/src/llm/client.py` (`LLMClient` class with `json_query()`, `vision_json_query()`) |
| **What it does** | Async LLM client with provider abstraction, structured JSON extraction with retry + validation |
| **Decision** | **Inspire** — Market Zero already has `services/llm.py::LLMSynthesizer`. Don't replace; cherry-pick the JSON-extraction + retry pattern for SPEC_014 NER |
| **Target** | `services/document_ner.py::extract_entities()` uses `services/llm.py` patterns + Proto_Demo's JSON-validate-and-retry logic |
| **Effort** | 0.5 day (extract just the JSON-validation logic) |
| **Acceptance** | NER consumer can request structured JSON output and recover from malformed responses |
| **Things to drop** | The provider abstraction (we already have one in `services/llm.py`) |

### 1.3 Entity + ProvenanceInfo schemas

| Field | Value |
|-------|-------|
| **Source** | `Proto_Demo/src/smb/core/entity.py` (`Entity`, `ProvenanceInfo`, `ConfidenceLevel` dataclasses) |
| **What it does** | Generic entity schema with provenance tracking (source_type, page_number, raw_text, extraction_method, confidence) |
| **Decision** | **Port** — Market Zero's `RawRecord` is the closest analog but lacks per-mention provenance |
| **Target** | `services/document_ner.py::EntityMention` extends with `ProvenanceInfo` field |
| **Effort** | 0.5 day |
| **Acceptance** | Every `EntityMention` carries `(source_type, page_number, raw_text, confidence)` minimum |
| **Why important** | Lead's #6 critique was "no provenance whatsoever"; this is the schema-layer fix |

### 1.4 Agent Harness with EventStream

| Field | Value |
|-------|-------|
| **Source** | `agentfuel/packages/sdk_core/src/agentfuel_sdk_core/agents/harness.py` + `event_stream.py` |
| **What it does** | Event-driven step execution with typed `AgentEvent` stream (turn_start, tool_invoked, step_completed, verification_passed/failed); session checkpointing; configurable verification modes |
| **Decision** | **Port** — replaces our minimal `services/agent/harness.py`. Critical for SPEC_016 Track 1 Phase 1 (unified router needs production-grade orchestration) |
| **Target** | `services/agent/harness.py` (rewrite) + new `services/agent/event_stream.py` |
| **Effort** | 3-4 days (port + adapt + tests + integration with existing query_graph) |
| **Acceptance** | Existing `test_agent_harness.py` tests still pass + new tests for event stream + verification |
| **Anti-pattern (per AgentFuel team)** | Don't conflate "event" with "logging" — events are for orchestration, not debug |

### 1.5 Tool Registry with permission tiers + budget

| Field | Value |
|-------|-------|
| **Source** | `agentfuel/packages/sdk_core/.../agents/tool_registry.py` |
| **What it does** | Rich tool metadata (version, negative_guidance, input/output schemas, side_effects, trust_tier, priority); session-mode permissions (assisted/semi/supervised/autonomous); priority ranking + token budgeting |
| **Decision** | **Port** — upgrades our basic `services/agent/registry.py` |
| **Target** | `services/agent/registry.py` (rewrite) |
| **Effort** | 1-2 days |
| **Acceptance** | Existing query_graph builds without errors using new registry; tool dispatch unchanged for callers |
| **Anti-pattern** | Don't use priority for "randomization" — it's deterministic ranking for budget-constrained scenarios |

---

## Tier 2 — Architectural patterns (moderate effort, big quality gain)

### 2.1 Evidence chain (CellEvidence + VerificationStep)

| Field | Value |
|-------|-------|
| **Source** | `ProtoCode/apps/api/app/core/trust/models.py` (`CellEvidence`, `VerificationStep`) |
| **What it does** | 3-tier confidence scoring (cell → row → protocol). Every entity carries `verification_steps` ordered chain (pass1/pass2 agreement, OCR grounding, challenger validation, human override) |
| **Decision** | **Port** — Market Zero's `entity_links.confidence` is a single float; this gives us auditable provenance |
| **Target** | New migration: add `verification_steps JSONB` column to `entity_links`. New `services/verification.py` model classes. |
| **Effort** | 3-4 days (schema migration + model + retrofit existing resolution paths) |
| **Acceptance** | New entity_links carry `verification_steps`; UI can render the chain; existing data backward-compatible |
| **Why important** | Directly addresses lead's "confidence is always 1.0" critique; foundation for SPEC_015 WS-4 (provenance) |

### 2.2 Claim graph builder (narrative → DAG of claims)

| Field | Value |
|-------|-------|
| **Source** | `Content_medical_hub/medcontent-ai-platform/agents/src/narrative/claim_graph_builder.py` (1039 LOC) + `evidence_linker.py` (652 LOC) |
| **What it does** | Extracts claims from narratives, detects dependencies (prerequisites/implications), builds semantic claim trees with evidence citations. Categorizes claims (EFFICACY_PRIMARY, SAFETY_OVERALL, CONCLUSION). |
| **Decision** | **Inspire** — too domain-specific to port directly, but the *pattern* (narrative → claim DAG with evidence anchors) is exactly what we need for the consulting demo's "before/after upload" visual |
| **Target** | New `services/claim_graph.py` written from scratch using the pattern; visualization in `frontend/src/components/canvas/ClaimGraphPanel.tsx` |
| **Effort** | 1 week (build + frontend viz) — this is post-Tier-1 work |
| **Acceptance** | Upload a document → claims extracted → visualized as DAG nodes with edges showing dependencies; each claim shows its source PDF page |
| **Why important** | THE consulting demo wedge per lead's notes ("The visual aha moment is when new connections light up after upload") |

### 2.3 Multi-dimension evaluation harness

| Field | Value |
|-------|-------|
| **Source** | `agentfuel/.../evaluation/{benchmarker,confidence,hallucination,grounding,rag_metrics}.py` |
| **What it does** | `BenchSuite` + `BenchResult` for case management; multi-dim scorers (RAG retrieval precision, hallucination detection, confidence calibration, semantic grounding); `HistogramSnapshot` for telemetry |
| **Decision** | **Port** — Market Zero's `benchmark/scorers.py` is basic; this is the rigor lead's notes called for in SPEC_015 WS-7 |
| **Target** | `benchmark/scorers/` directory (multi-file split: `confidence.py`, `hallucination.py`, `grounding.py`, `rag_metrics.py`) |
| **Effort** | 3-4 days (port + adapt RAG metrics to pharma domain) |
| **Acceptance** | `benchmark/ci_eval.py` produces multi-dim scores; CI gate threshold can be set per dimension |
| **Anti-pattern** | Don't treat confidence as ground truth — confidence (model's self-assessment) ≠ grounding (claim-to-source validation) |

### 2.4 Knowledge Base Manager (versioning + workspace isolation)

| Field | Value |
|-------|-------|
| **Source** | `Content_medical_hub/.../knowledge_base/kb_manager.py` + `project_kb.py` |
| **What it does** | Manages document versioning, workspace isolation, incremental ingestion. Tracks "which doc was processed when by which pipeline version". Supports multi-project KBs. |
| **Decision** | **Inspire** — adopt the versioning pattern as a small migration; no need to port the full multi-project module yet |
| **Target** | New columns on `source_records`: `pipeline_version`, `processed_at`, `superseded_by_id` |
| **Effort** | 1-2 days |
| **Acceptance** | Re-uploading same document creates a new version row; queries default to latest unsuperseded |
| **Why important** | Enterprise-trust feature for consulting (audit trail per upload) |

### 2.5 Production error handling + fallback chains

| Field | Value |
|-------|-------|
| **Source** | `agentfuel/.../gateway/fallback.py` + `contracts/errors.py` |
| **What it does** | `FallbackChainExecutor` with circuit breaker + health checker; categorized error mapping (validation/auth/authz/rate_limited/upstream/internal); `AgentFuelError` factory for context-aware error responses (execution_id, trace_id, retry_after) |
| **Decision** | **Port** — integrates well with our existing `UnifiedChatHandler` fallback pattern (SPEC_011) |
| **Target** | `services/llm.py` (LLM fallback) + `api/routes/chat.py` (handler fallback) |
| **Effort** | 1-2 days |
| **Acceptance** | Distinct retry policies per error category; circuit breaker prevents thundering herd on upstream failure |
| **Anti-pattern** | Don't treat all 5xx as retriable — `ModelAuthenticationError` should fail fast, `ModelGatewayError` retries |

---

## Tier 3 — Frontend + observability (consulting-demo critical)

### 3.1 Clinical visualization components (Kaplan-Meier, risk tables)

| Source | `Content_medical_hub/frontend/src/components/visualizations/` |
| **Decision** | **Port** — used selectively for trial-outcome visualizations |
| **Target** | `frontend/src/components/canvas/visualizations/` |
| **Effort** | 2-3 days per component (KM curve, risk table, etc.) |

### 3.2 TraceRecorder + EvidenceTracker (regulated mode)

| Source | `agentfuel/.../observability/{trace_recorder,evidence_tracker,metrics}.py` |
| **Decision** | **Port** — pharma compliance story for consulting clients |
| **Target** | `services/observability/` (new module) |
| **Effort** | 2-3 days |
| **Anti-pattern** | Don't log raw PHI — AgentFuel's redaction layer is pharma-safe; preserve it |

---

## Anti-Patterns We Are Adopting From Sibling Mistakes

| From | Lesson | Implication for Market Zero |
|------|--------|----------------------------|
| ProtoCode | Moved AWAY from LangChain; deliberate "Anthropic SDK only" decision | Don't add LangChain abstraction. Keep direct Anthropic SDK in `services/llm.py`. (We already do this.) |
| ProtoCode | Dual-pass extraction (pass1 + pass2 for agreement) doesn't scale at thousands of docs — doubles API cost/latency | Use dual-pass only for low-confidence fallback in entity resolution, never as default |
| Proto_Demo | VLM cell extraction without grid anchoring hallucinates structure | If we ever do table extraction, use grid-anchored prompts (deterministic row/col indices) |
| AgentFuel | Confidence ≠ grounding — they're different signals | Our scorers must measure both separately; don't compute one and pretend it's the other |

---

## Integration Sequencing (referenced from EXECUTION_PLAN_2026-04.md)

The catalog above informs phase sequencing. Updated order with sibling-code acceleration:

| Phase | Work | Sibling assets used | Original effort | Accelerated effort |
|-------|------|---------------------|----------------|-------------------|
| 4a | IE-pattern grounding | (none — fresh build) | 2-3d | 2-3d |
| 4b | WS-1B molecule canonicalization | (extends WS-1) | 1-2d | 1-2d |
| **4c** | **SPEC_014 MVP doc upload + NER** | **Proto_Demo extractor + LLMClient + Entity** | **1 week** | **3-4 days** |
| 5 | Track 1 Phase 1 unify router | AgentFuel Harness + ToolRegistry | 1-2 weeks | 1 week |
| 6 | IE Priority 2 (retry, catalog-wide, title-ID) | (logic-heavy, no shortcut) | 3d | 3d |
| 7 | Track 1 Phase 2 sufficiency loop | AgentFuel evaluation patterns | 1-2 weeks | 1 week |
| 8 | Numeric guardrails (WS-5) | ProtoCode evidence chain | 3-4d | 2-3d |
| **NEW 9** | **Frontend "before/after" graph viz** | **Content_medical_hub claim graph + viz components** | **(not in plan)** | **1 week** |
| 10 | Eval harness overhaul (WS-7) | AgentFuel evaluation/ module | 4-5d | 3-4d |

**Net savings: ~10-12 days** across the sprint, with HIGHER quality foundations.

---

## License / Ownership Notes

All four sibling projects appear to be owned by the same team. Verify before each port:
- Are there third-party licenses in the source files we want to port? (Proto_Demo PyMuPDF dependency is AGPL — already a constraint in their build, not a new one for us)
- Are there any client-confidential snippets embedded? (Especially in `Content_medical_hub` which deals with regulatory content)

Each port commit should include a short attribution comment in the file header noting the source.

---

## Maintenance

This catalog should be updated whenever:
- A new sibling project becomes available
- A port lands in Market Zero (move row to "ported" status)
- An anti-pattern is verified or refuted by our own experience

Owner: implementation lead. Cadence: review at end of each phase.
