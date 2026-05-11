# Agent Backlog

Cross-domain bug & request board between Claude (backend) and Antigravity
(frontend). Either agent may file. Items are tagged by area and addressed by
the agent who owns that area.

> **Note**: For product/feature backlog, see `docs/backlog.md`. This file is
> only for agent-to-agent coordination.

Tags:
- `[BACKEND]` — request directed at Claude
- `[FRONTEND]` — request directed at Antigravity
- `[PROTOCOL]` — protocol violation or ambiguity; user mediates

Format:
```
## [TAG] Short title
- Filed: YYYY-MM-DD by <agent>
- Need / Repro: <what's needed or how to reproduce>
- Why: <motivation>
- Priority: low | medium | high | urgent
- Status: open | in-progress | done | wontfix
```

---

# Backend Backlog from SPEC-042 refresh (filed 2026-05-10)

> **Source:** `design-review-output/enhancement-backlog.md` 12-epic plan,
> mirrored into `docs/PRODUCT_BACKLOG.md` as PB-1XX..C03.
>
> **For backend Claude:** these are the concrete asks per epic. Each
> entry has the file/endpoint shape, acceptance criteria, and which
> frontend PB-NNN consumes it. Sequencing in §"Recommended ordering"
> below — the urgent items (BE-2, BE-37/38/39 multi-tenancy) ship
> first regardless of epic order.
>
> **Convention:** `BE-N` ids are referenced from PRODUCT_BACKLOG by
> `Source ref: AGENT_BACKLOG#BE-N`. Each BE entry is also reachable by
> Markdown anchor `#be-n-...`.

## Recommended ordering for backend Claude

1. **Urgent first** — BE-2 (production materiality 1% diagnostic), BE-37 → BE-38 → BE-39 (multi-tenancy enforcement).
2. **Unblocks E1 frontend** — BE-1 (evidence schema extension).
3. **Unblocks E2** — BE-3 (agent name field) → BE-4 (SSE stream) → BE-5 (nudge endpoint).
4. **Unblocks E3** — BE-6 (dossier composer).
5. **Unblocks E5** — BE-8/9/10 (payoff matrix + adversary twins) → BE-11 (cockpit SSE) → BE-12/13 (authority) → BE-14 (delegation executor).
6. **Unblocks E6 (highest-leverage)** — BE-15 (wire ConversationMemory) → BE-16/17 (citation tier + 4-dim confidence) → BE-18/19 (source-strip + why-this).
7. **Unblocks E7** — BE-20 (/ask subgraph context) + BE-21 (saved views).
8. **Unblocks E8** — BE-22..26 (catalog endpoints).
9. **E9 connectors** — BE-27..34 (8 free public sources, can be parallelised).
10. **E10/E12** — BE-35/36/40/41.

---

## E1 · Trust foundation backend asks

### [BACKEND] BE-1 · Extend evidence_records schema with tier, snippet, published_at
- Filed: 2026-05-10 by Frontend Claude (consumer of SPEC_024)
- For: PB-101 Evidence cards
- Need: Add columns to `evidence_records` (or join from `sources`):
  - `source_name TEXT` (display)
  - `source_tier TEXT CHECK (source_tier IN ('T1','T2','T3','T4'))`
  - `published_at TIMESTAMPTZ`
  - `snippet TEXT` (extracted 2-line preview)
- Endpoint changes: `GET /signals/{id}` and `GET /decision-briefs/{id}/evidence` return these fields nested under each evidence item. Update `EvidenceItemResponse` in `api/schemas.py`.
- Files: `schema/migrations/NNN_evidence_card_fields.sql`, `services/evidence_ledger.py`, `api/routes/evidence_ledger.py`, `api/schemas.py`.
- Acceptance: frontend can render EvidenceCard with source / favicon-deferred / tier badge / date / 2-line snippet without further backend calls.
- Priority: high
- Status: open

### [BACKEND] BE-2 · DIAGNOSTIC · production materiality scores all 1%
- Filed: 2026-05-10 by Frontend Claude
- For: PB-104b (blocks PB-103)
- Need: investigate why every materiality score on production renders 1%. Live walk on 2026-05-09 confirmed.
- Files to inspect: `services/materiality.py:score()`, the ingestion pipeline that triggers scoring, the `materiality_factors` JSONB on signals.
- Possible causes: (a) scorer not running on new ingestion, (b) factor weights misconfigured (all near zero?), (c) response shape changed and frontend reads the wrong path, (d) calibration data missing.
- Acceptance: written diagnostic with root cause + fix landed + spot-check 10 signals showing varied scores (>1% with sensible spread).
- Priority: **urgent** (blocks SPEC-031 deliverable from being visible)
- Status: open

### [BACKEND] BE-3 · Agent name field on /agent/events
- Filed: 2026-05-10 by Frontend Claude
- For: PB-201 Agent identity
- Need: every event emitted by `services/research_agent.py`, `services/conversation_memory.py`, `services/data_steward.py` carries `agent: "sentinel" | "strategist" | "curator"` (noun form per Phase 8 verification).
- Files: `api/routes/agent.py`, services above.
- Acceptance: GET `/agent/events?limit=20` returns events all of which have a non-null `agent` field with one of the three values.
- Priority: medium
- Status: open

---

## E2 · Live agent presence backend asks

### [BACKEND] BE-4 · GET /agents/stream (Server-Sent Events)
- Filed: 2026-05-10 by Frontend Claude
- For: PB-202 Agent activity feed
- Need: new SSE endpoint streaming agent events as they happen.
- Endpoint shape:
  ```
  GET /agents/stream?since=<iso>&agents=sentinel,strategist,curator
  Content-Type: text/event-stream
  data: {"agent":"sentinel","kind":"started","activity":"Scanning trial registry","ts":"...","entity_refs":["drug:tirzepatide"]}\n\n
  data: {...}\n\n
  ```
- Server-side: wraps existing `/agent/events` poll loop into a generator with heartbeat every 15s.
- Files: `api/routes/agent.py` (extend), reuse existing event publishers in `services/`.
- Acceptance: frontend `lib/sse.ts` + `AgentRail` consume the stream; reconnects with exponential backoff after server restart; falls back to polling if SSE unavailable.
- Priority: medium
- Status: open

### [BACKEND] BE-5 · POST /agents/{agent}/nudge with intent registry
- Filed: 2026-05-10 by Frontend Claude
- For: PB-203 Agent nudges
- Need: new endpoint to nudge a specific agent with a typed intent + payload.
- Endpoint shape:
  ```
  POST /agents/{agent}/nudge
  Body: { intent: string, payload: object }
  agent ∈ {sentinel, strategist, curator}
  ```
- Intent registry per agent:
  - Sentinel: `watch_entity`, `ignore_source`, `boost_source`
  - Strategist: `rerun_simulation`, `draft_counter_recommendation`
  - Curator: `explain_score`, `mark_outcome_verified`
- Files: new `services/agent/nudge_intents.py` (registry + dispatcher), `api/routes/agent.py` (endpoint), update `services/research_agent.py` etc. to handle nudges.
- Acceptance: each intent → one effect logged in `agent_events` with `nudge_intent` field; idempotent for repeated identical nudges within 5 min.
- Priority: medium
- Status: open

---

## E3 · Entity dossier backend asks

### [BACKEND] BE-6 · GET /dossier/{type}/{slug-or-id} composer endpoint
- Filed: 2026-05-10 by Frontend Claude
- For: PB-301 Dossier route + PB-303 timeline + PB-304 evidence pile
- Need: single composer endpoint that joins existing endpoints into one dossier payload.
- Endpoint shape:
  ```
  GET /dossier/{entity_type}/{slug-or-id}
  Response: {
    entity: { id, type, name, aliases[], identity_fields{} },
    synthesis: { text_with_citation_marks, last_synthesised_at, owner_user_id },
    recent_moves: [ { ts, kbq_tag, headline, signal_id?, transition? } ],   // 30-day window
    evidence_refs: [ EvidenceItemResponse ],     // up to 50, ordered by relevance
    watching: [ { user_id, name, avatar_url } ], // up to 10
    related_entities: [ { id, type, name, relation, edge_count } ]
  }
  ```
- entity_type ∈ {drug, company, mechanism, trial, therapeutic_area}.
- Files: new `api/routes/dossier.py`, new `services/dossier.py` (composer that calls existing `/catalog/entity-profile`, `/graph/neighborhood`, `/signals?entity_id=…` and assembles).
- Acceptance: single GET returns a structured payload that DossierPage renders without further calls; supports both `slug` and `entity_id` URL parameter.
- Priority: medium
- Status: open

---

## E4 · Brief composer backend asks

### [BACKEND] BE-7 · services/brief_suggestions.py + POST /decision-briefs/{id}/suggest
- Filed: 2026-05-10 by Frontend Claude
- For: PB-402 Inline AI suggestions
- Need: endpoint that, given a brief draft, returns Strategist + Curator inline suggestions.
- Endpoint shape:
  ```
  POST /decision-briefs/{brief_id}/suggest
  Body: { current_text, current_options[], cursor_position? }
  Response: {
    suggestions: [
      {
        agent: "strategist" | "curator",
        kind: "add_counter" | "name_stakeholder" | "surface_contradiction" | "evidence_score" | "insert_evidence",
        anchor: { paragraph_index, char_offset },
        proposed_text: "...",
        rationale: "...",
        confidence: 0.0-1.0,
        evidence_refs: []
      }
    ]
  }
  ```
- Files: new `services/brief_suggestions.py`, extend `services/llm.py` with `suggest_brief_edit()` if `synthesize_research_report()` is too coarse, `api/routes/decision_briefs.py` (new endpoint).
- Acceptance: 6-second polling produces suggestions that anchor correctly; stale suggestions invalidated when underlying paragraphs change.
- Priority: low (only after E1-E3 ship)
- Status: open

---

## E5 · War-game cockpit backend asks

### [BACKEND] BE-8 · POST /war-rooms/{id}/payoff-matrix composer
- Filed: 2026-05-10 by Frontend Claude
- For: PB-501 Payoff matrix view
- Need: composer endpoint that returns a 2×2 payoff matrix using `services/game_theory.py::run_bayesian()` (1,200 Monte Carlo samples already implemented).
- Endpoint shape:
  ```
  POST /war-rooms/{id}/payoff-matrix
  Body: { our_moves: [m1, m2], adversary_states: [s1, s2] }
  Response: {
    cells: [[ { delta_pct, confidence, recommended }, { delta_pct, confidence, recommended } ],
             [ { delta_pct, confidence, recommended }, { delta_pct, confidence, recommended } ]],
    recommended_cell: [row, col]
  }
  ```
- Files: new `services/simulation/payoff.py`, `api/routes/war_room.py` (extend).
- Priority: medium
- Status: open

### [BACKEND] BE-9 · services/adversary_twin.py — adversary digital twin model
- Filed: 2026-05-10 by Frontend Claude
- For: PB-502 Adversary twins
- Need: per-competitor twin model storing behavioural posterior + history.
- Schema: new table `adversary_twins (twin_id, name, kind, posterior JSONB, last_updated_at, evidence_log[])`.
- Initial seed: 6 twins for diabetes/obesity TA — Pfizer, Lilly, AZN, FDA, Payer, KOL — with their archetypes (aggressive/defensive/cash-constrained mixture).
- Files: new `services/adversary_twin.py`, new `schema/migrations/NNN_adversary_twins.sql`, `domain/pharma/pack.py` (register twin entity type if needed).
- Priority: medium
- Status: open

### [BACKEND] BE-10 · GET /adversaries/{id}/posterior
- Filed: 2026-05-10 by Frontend Claude
- For: PB-502 Adversary twins (consumes BE-9)
- Need:
  ```
  GET /adversaries/{twin_id}/posterior
  Response: {
    posterior: { aggressive: 0.61, defensive: 0.24, cash_constrained: 0.15 },
    last_updated_at: "...",
    last_5_evidence_updates: [ { ts, evidence_id, what_shifted, magnitude } ]
  }
  ```
- Files: new `api/routes/adversary.py`.
- Priority: medium
- Status: open

### [BACKEND] BE-11 · GET /war-rooms/{id}/cockpit-stream (SSE)
- Filed: 2026-05-10 by Frontend Claude
- For: PB-503 Live cockpit
- Need: SSE stream of Strategist's reasoning steps + Sentinel/Curator activity during a simulation.
- `services/game_theory.py::run_bayesian()` already produces sample-by-sample; surface as event stream.
- Endpoint shape: SSE yielding `{ kind: "step" | "sample" | "complete", agent, payload }` events.
- Acceptance: frontend cockpit renders thinking-stream live; supports stress-test variants by running multiple sims tagged with `variant_id`.
- Priority: medium (after BE-8/9/10)
- Status: open

### [BACKEND] BE-12 · services/agent/authority.py — calibration windowing + promotion
- Filed: 2026-05-10 by Frontend Claude
- For: PB-504 Authority spectrum
- Need: model that tracks each agent's calibration per scenario type + auto-promotes when calibration > 0.70 over 14 scenarios.
- Schema: `agent_authority (agent, scenario_type, current_level, calibration_score, scenario_count, last_promoted_at)`.
- Files: new `services/agent/authority.py`, new `schema/migrations/NNN_agent_authority.sql`.
- Priority: medium
- Status: open

### [BACKEND] BE-13 · POST /agent-authority + settings endpoints
- Filed: 2026-05-10 by Frontend Claude
- For: PB-504 Authority spectrum (consumes BE-12)
- Need: settings endpoints to read/write authority levels per agent per scenario type, plus promotion notifications.
- Endpoints: `GET /agent-authority`, `PATCH /agent-authority/{agent}/{scenario_type}`, `GET /agent-authority/promotions`.
- Files: new `api/routes/agent_authority.py`.
- Priority: medium
- Status: open

### [BACKEND] BE-14 · Scheduled run executor for delegation
- Filed: 2026-05-10 by Frontend Claude
- For: PB-505 Delegation
- Need: queue scenario with parameters + wake-me-up condition; agents run overnight; log to `game_theory_runs`.
- Existing scheduler: `scheduler/runner.py` — extend for one-shot delegated runs.
- Acceptance: morning Pulse shows verdict + diff vs baseline; replayable end-to-end.
- Priority: low
- Status: open

---

## E6 · Chat surface upgrade backend asks

### [BACKEND] BE-15 · Wire ConversationMemory into /chat (the audit's #1 transformative move)
- Filed: 2026-05-10 by Frontend Claude
- For: PB-601 Wire ConversationMemory
- Need: `services/conversation_memory.ConversationMemory` is fully built but not used. Wire it into `services/chat_handlers/context.py::build_conversation_context()`, then into `services/unified_handler.UnifiedChatHandler.handle()`.
- Frontend will pass `session_id` to `/chat`; backend loads memory by session_id; calls `memory.get_context()`; feeds entity context into prompt assembly; resolves coreferences ("this drug" → tirzepatide from turn 1).
- Files: `api/routes/chat.py`, `services/chat_handlers/context.py`, `services/unified_handler.py`, `api/deps.py::get_conversation_memory()` (already exists).
- Acceptance: turn 2 user message "what's its safety profile?" resolves to the entity discussed in turn 1; backend response includes `coreference_resolution: { "this drug": "tirzepatide", from_turn: 1 }` so frontend can render branch indicator.
- Priority: **high** (highest leverage chat fix per audit)
- Status: open

### [BACKEND] BE-16 · Citation payload carries source tier
- Filed: 2026-05-10 by Frontend Claude
- For: PB-603 Citation chips
- Need: every citation in synthesis output carries `tier ∈ {T1, T2, T3, T4}` matching the source's registry tier.
- Files: `services/llm.py::validate_citations()` — ensure tier propagated; `services/ctx_evidence.py` — tier in evidence pack.
- Acceptance: `POST /chat` response has `citations: [{ id, source_name, tier, published_at, snippet }, ...]`.
- Priority: medium
- Status: open

### [BACKEND] BE-17 · Synthesize returns 4-dimension confidence breakdown
- Filed: 2026-05-10 by Frontend Claude
- For: PB-604 Confidence pill (replaces 3 inconsistent components)
- Need: `services/llm.py::synthesize()` returns
  ```
  confidence_assessment: {
    composite: 0.74,
    by_dimension: {
      evidence_quality: 0.82,
      source_diversity: 0.71,
      recency: 0.65,
      calibration: 0.78
    }
  }
  ```
- Acceptance: frontend ConfidencePill renders the 4 bars + composite without further calls.
- Priority: medium
- Status: open

### [BACKEND] BE-18 · Aggregate-by-source endpoint for source strip
- Filed: 2026-05-10 by Frontend Claude
- For: PB-605 Source strip
- Need: per-message aggregation of citations grouped by source.
- Endpoint shape: response of `/chat` includes `source_aggregation: [ { source_id, source_name, tier, cite_count } ]`.
- Files: `services/llm.py` post-process step.
- Priority: low
- Status: open

### [BACKEND] BE-19 · Why-this explanation generator
- Filed: 2026-05-10 by Frontend Claude
- For: PB-606 Why-this pattern
- Need: endpoint that, given any proactive surface item (Pulse card, brief proposal, agent suggestion, war-game rec, framing trigger fire), returns a one-paragraph plain-language explanation + deep-link refs.
- Endpoint shape:
  ```
  POST /why-this
  Body: { surface: "pulse" | "brief_proposal" | "agent_suggestion" | "wargame_rec" | "trigger_fire",
          item_id, ... }
  Response: { explanation_paragraph, deep_links: { factor_breakdown_url?, source_registry_url?, trigger_config_url? } }
  ```
- Files: new `services/explainer.py`, `api/routes/explainer.py`.
- Priority: low
- Status: open

---

## E7 · Graph as interlocutor backend asks

### [BACKEND] BE-20 · /ask accepts subgraph context
- Filed: 2026-05-10 by Frontend Claude
- For: PB-701 Ask-this-subgraph
- Need: extend `POST /ask` body with optional `context.subgraph: { node_ids: [], edge_types: [] }`. When provided, `services/llm.py` constructs prompt with subgraph as the focal context.
- Files: `api/routes/ask.py`, `services/ask_engine.py` (already shipped per SPEC-035).
- Acceptance: subgraph-bounded answer; suggestion generator returns selection-specific suggestions.
- Priority: medium
- Status: open

### [BACKEND] BE-21 · saved_views table + CRUD endpoints
- Filed: 2026-05-10 by Frontend Claude
- For: PB-703 Saved subgraphs
- Need: new persistence + endpoints.
- Schema: `saved_views (view_id UUID, owner_user_id, name, version, state JSONB, shareable_slug, created_at, updated_at)`.
- Endpoints: `GET /saved-views`, `POST /saved-views`, `GET /saved-views/{id}`, `PATCH /saved-views/{id}`, `DELETE /saved-views/{id}`, `GET /shared/views/{slug}`.
- Files: new `api/routes/saved_views.py`, new `services/saved_views.py`, new migration.
- Priority: low
- Status: open

---

## E8 · Data catalog backend asks

### [BACKEND] BE-22 · /catalog/stats tier-rollup data
- Filed: 2026-05-10 by Frontend Claude
- For: PB-801 Catalog overview
- Need: extend `GET /catalog/stats` response with per-tier rollup:
  ```
  by_tier: {
    T1: { sources, records, avg_freshness_hours, avg_fair_score },
    T2: {...}, T3: {...}, T4: {...}
  }
  ```
- Priority: medium
- Status: open

### [BACKEND] BE-23 · /catalog/24h-stats aggregate endpoint
- Filed: 2026-05-10 by Frontend Claude
- For: PB-803 Ingestion activity
- Need: new endpoint with 24h breadcrumbs (cycles run, records ingested, drift events, cost).
- Priority: low
- Status: open

### [BACKEND] BE-24 · Source detail FAIR breakdown + schema preview
- Filed: 2026-05-10 by Frontend Claude
- For: PB-804 Source detail dive
- Need: extend `api/routes/sources.py` with:
  - `GET /sources/{id}/fair` — 5-dimension breakdown per spec §8.3 (coverage, latency, predictive_accuracy, stability, license_health).
  - `GET /sources/{id}/schema` — schema preview with column types + 5 sample rows.
- Priority: medium
- Status: open

### [BACKEND] BE-25 · Licence model in source registry
- Filed: 2026-05-10 by Frontend Claude
- For: PB-807 Licence health panel
- Need: extend `sources` table or new `source_licences` table with `annual_cost_usd`, `renewal_at`, `licence_type`, `health` fields.
- Endpoint: `GET /sources/licences` returns per-source row + total today + projected total after Phase 2.
- Priority: low
- Status: open

### [BACKEND] BE-26 · /connectors → 301 redirect to /catalog
- Filed: 2026-05-10 by Frontend Claude
- For: PB-809 Decommission /connectors raw JSON
- Need: move JSON response to `/api/connectors`; `/connectors` HTTP route returns 301 to `/catalog`.
- Files: `api/routes/connectors.py` (or wherever `/connectors` lives).
- Priority: low (after PB-801 catalog ships)
- Status: open

---

## E9 · Phase 1 connectors backend asks (8 free public sources)

> All 8 connectors follow the same pattern as existing `connectors/clinical_trials.py` etc.: inherit `BaseConnector`, register in `integration/pipeline_hooks.py`, add tests under `tests/test_*.py`.

### [BACKEND] BE-27 · USPTO PatentsView API connector
- Filed: 2026-05-10 by Frontend Claude
- For: PB-901 — closes KBQ-10 Patent
- Files: new `connectors/uspto.py`, register in `integration/pipeline_hooks.py`, add patent entity type to `domain/pharma/pack.py` if not present.
- Schedule: weekly cron.
- Priority: medium
- Status: open

### [BACKEND] BE-28 · EPO Patents (OPS API) connector
- Filed: 2026-05-10 by Frontend Claude
- For: PB-902 — closes KBQ-10 international
- Files: new `connectors/epo.py`. Depends on BE-27 (patent entity type).
- Priority: low
- Status: open

### [BACKEND] BE-29 · bioRxiv + medRxiv preprints connector
- Filed: 2026-05-10 by Frontend Claude
- For: PB-903 — closes scientific KBQ-4 priority
- Files: new `connectors/biorxiv.py` (RSS + API), entity type already exists (literature).
- Priority: medium
- Status: open

### [BACKEND] BE-30 · FDA OPDP warning letters connector
- Filed: 2026-05-10 by Frontend Claude
- For: PB-904 — closes KBQ-3 Regulatory + KBQ-9 Reputational
- Files: new `connectors/fda_opdp.py` (scraper + parser).
- Priority: medium
- Status: open

### [BACKEND] BE-31 · CMS Medicare Part D formulary (50 plan files) connector
- Filed: 2026-05-10 by Frontend Claude
- For: PB-905 — closes KBQ-8 Access (formularies, PA, step therapy)
- Files: new `connectors/cms_partd.py`. Batch download + parse 50 plan files.
- Priority: medium
- Status: open

### [BACKEND] BE-32 · CMS Medicare B + D pricing connector
- Filed: 2026-05-10 by Frontend Claude
- For: PB-906 — closes KBQ-7 Pricing (free public alternative to RedBook/FDB until executive cost-benefit on those)
- Files: new `connectors/cms_pricing.py`.
- Priority: medium
- Status: open

### [BACKEND] BE-33 · WHO ICTRP global trial registry connector
- Filed: 2026-05-10 by Frontend Claude
- For: PB-907 — closes international trial gap
- Files: new `connectors/who_ictrp.py` + cross-walk to canonical Trial entity.
- Priority: low
- Status: open

### [BACKEND] BE-34 · VA / DoD national formulary connector
- Filed: 2026-05-10 by Frontend Claude
- For: PB-908 — public-payer access gap
- Files: new `connectors/va_dod.py`.
- Priority: low
- Status: open

---

## E10 · Source registry + FAIR backend asks

### [BACKEND] BE-35 · Curator-driven weight learning service
- Filed: 2026-05-10 by Frontend Claude
- For: PB-A02
- Need: new `services/curator/weight_learning.py` — outcome-to-weight feedback loop, weekly recalibration job, weight-change audit log.
- Priority: low
- Status: open

### [BACKEND] BE-36 · Source health monitoring + graceful degradation
- Filed: 2026-05-10 by Frontend Claude
- For: PB-A03
- Need: per-source SLA monitoring + "Missing because" inline message in user-facing answers (when a degraded source would have been used).
- Priority: low
- Status: open

---

## E11 · Multi-tenancy enforcement backend asks (CRITICAL · SaaS-blocker)

### [BACKEND] BE-37 · tenant_id on core entity tables
- Filed: 2026-05-10 by Frontend Claude
- For: PB-B01
- Need: add `tenant_id` column to `drugs`, `companies`, `trials`, `mechanisms`. Backfill from `chat_sessions.scope_key` provenance where possible; default to `"public"` for entities ingested before tenancy.
- Sequencing: NULL allowed during backfill; NOT NULL added after backfill verifies 100%.
- Files: new `schema/migrations/NNN_tenant_id_core_entities.sql`, backfill script `scripts/backfill_tenant_id.py`.
- Acceptance: every row in core tables has tenant_id set; query `SELECT COUNT(*) FROM drugs WHERE tenant_id IS NULL` returns 0.
- Priority: **urgent**
- Status: open

### [BACKEND] BE-38 · Tenant isolation middleware
- Filed: 2026-05-10 by Frontend Claude
- For: PB-B02
- Need: DB middleware that injects `tenant_id = :current_tenant` into all WHERE clauses. Update `services/search.py` + `services/graph.py` to filter by tenant.
- Files: `db.py` (middleware), `services/search.py`, `services/graph.py`, plus any service that currently does raw SQL across core tables.
- Acceptance: cross-tenant test (Pfizer session queries Roche-tenant entity) returns 0 rows; existing single-tenant tests still pass.
- Priority: **urgent**
- Status: open

### [BACKEND] BE-39 · Tenant audit + CI isolation tests
- Filed: 2026-05-10 by Frontend Claude
- For: PB-B03
- Need: per-tenant audit trail (90d retention) + CI tests that assert cross-tenant queries return zero rows.
- Files: new `tests/test_tenant_isolation.py`, audit log table.
- Priority: high
- Status: open

---

## E12 · Prompt registry + active feedback backend asks

### [BACKEND] BE-40 · Promote SYSTEM_PROMPTS dict to prompt_registry
- Filed: 2026-05-10 by Frontend Claude
- For: PB-C01
- Need: migrate hardcoded `SYSTEM_PROMPTS` dict at `services/llm.py:179-250` to the existing `prompt_registry` table (table already exists, columns already populated for ad-hoc prompts; system prompts haven't been migrated). Update `services/llm.py` to load prompts from registry. Add versioning + A/B test harness.
- Files: `services/llm.py`, new migration to seed registry from current dict, `scripts/migrate_system_prompts.py`.
- Acceptance: prompts loaded from DB at startup; flagged-prompt rollback works; A/B harness can run two prompt versions side-by-side.
- Priority: medium
- Status: open

### [BACKEND] BE-41 · Outcome-to-prompt-weight backpropagation
- Filed: 2026-05-10 by Frontend Claude
- For: PB-C02
- Need: per spec §6.5.2 — when an outcome is detected, attribute accuracy to the prompt versions that produced the recommendation; update prompt weights via Curator.
- Files: extend `services/outcome_detector.py`, new `services/curator/prompt_calibration.py`, weekly job.
- Priority: low
- Status: open

---

## [FRONTEND] InboxTab login wall blocks the default landing
- Filed: 2026-05-09 by Claude
- Repro: Open `/ci` (the CI page) without an `mz_auth_token` in localStorage.
  The default tab is now `inbox` (since Phase E), which renders only the message
  "Log in (viewer or above) to see your decision inbox." with no login CTA.
- Why: Hostile first impression — unauthenticated users hit a dead end on the
  primary surface. The user reported this directly.
- Suggested fix: Either (a) detect auth state in `frontend/src/pages/CIPage.tsx`
  and default unauth users to `digest` (which works without auth), OR (b)
  replace the message in `frontend/src/components/ci/InboxTab.tsx` with a real
  login CTA + button that routes to `/login`, OR (c) both.
- Reference: `frontend/src/pages/CIPage.tsx:39` (default tab) and
  `frontend/src/components/ci/InboxTab.tsx` (unauth branch).
- Priority: urgent
- Status: **done** (2026-05-09 — see `docs/UI_CHANGELOG.md`. CIPage defaults
  unauthed users to `digest`; InboxTab unauth branch now renders a real login CTA.)

## [FRONTEND] UI is "demo-grade" — needs Phase F Cockpit redesign
- Filed: 2026-05-09 by Claude
- Need: Comprehensive UX/UI redesign matching the sophistication of Oura Ring,
  Apple Health, Apple.com, Spotify. User has explicitly asked for this.
- Reference prototype: `specs/test.tsx` — the "north star" — sophisticated dark
  theme, SVG flow diagrams, Syne+DM Mono typography, color-coded scoring matrices.
- Suggested approach: Write `specs/SPEC_022_cockpit_design_system.md` first
  with: design tokens (light + dark), motion principles, typography hierarchy,
  component primitives (MetricRing, Sparkline, RadarChart, FlowDiagram,
  Timeline, AgentStatusBar, HeroCard), phased implementation plan.
- Implement progressively per surface, behind feature flag
  `localStorage.mz_ui_v2 === 'true'` until ready to flip.
- Priority: high
- Status: open

---

# CI Decision Flywheel v2 — items from `specs/CI_Agent_Reimagined_Spec.md`

The CI Agent Reimagined Spec (filed 2026-05-09) describes a next-generation
Decision Flywheel platform. Much of it is **already partially built** in
SPEC-021. The items below are the gaps between current state and the spec's
target state. Each is tagged for ownership.

> **Coordination rule** (per `AGENTS.md` §5): items marked `[CROSS-CUTTING]`
> require a written `specs/SPEC_NNN_*.md` with sign-off from BOTH agents
> before implementation begins. The spec defines the data contract; backend
> ships first, frontend consumes.

---

## Backend backlog (Claude)

### [BACKEND] Decision Brief object (first-class, with options + stakeholders)
- Filed: 2026-05-09 by Claude (from spec §6.2.2)
- Need: Promote war_rooms / decisions into a proper `decision_briefs` table
  with: `brief_id`, `question`, `trigger_signal_ids[]`, `stakeholders[]`,
  `time_horizon`, `options[]` (min 2, target 3-5), `evidence_refs[]`,
  `constraints[]`, `success_criteria`, `confidence_to_proceed`, plus a state
  machine (`draft → human_review → simulation_pending → simulation_complete →
  decision_pending → committed → in_review → closed`).
- Why: Current `war_rooms` are option-discovery surfaces and current `decisions`
  capture commitment, but neither is a structured Brief that frames the
  question + stakeholders + success criteria up-front. Spec treats this as
  the canonical handoff from sensing → simulation.
- Cross-cutting: write `specs/SPEC_023_decision_briefs.md` first (data contract
  blocks frontend Decision Workspace work).
- Priority: high
- Status: **done** (2026-05-09 — `specs/SPEC_023_decision_briefs.md`,
  migration 052, `services/decision_brief.py`, `api/routes/decision_briefs.py`,
  31 tests green. Commits 1dace1c + b0e52b5.)

### [BACKEND] Triggers — threshold / cluster / calendar
- Filed: 2026-05-09 by Claude (from spec §6.2.1)
- Need: A `framing_triggers` evaluator (cron-style, runs every 5 min) that
  detects: (a) any signal with materiality_score ≥ 80, (b) ≥3 related signals
  within a rolling window, (c) calendar-scheduled review points. On trigger,
  auto-creates a draft DecisionBrief and routes to the assigned strategist.
- Why: Today decisions only get created when a human opens a war room.
  Auto-framing closes the signal-to-decision latency gap (spec target: <24h).
- Depends on: Decision Brief object above.
- Priority: medium
- Status: **done** (2026-05-09 — specs/SPEC_029_framing_triggers.md, migration 059, services/framing_triggers.py, api/routes/framing_triggers.py, 34 tests green. Threshold + cluster + calendar evaluators with dedup rules and isolated failures.)

### [BACKEND] Materiality scoring — learned model with calibration
- Filed: 2026-05-09 by Claude (from spec §6.1.2)
- Need: Replace the current heuristic scorer with a trained model whose
  inputs include source tier, entity criticality, claim type, recency.
  Calibration reviewed quarterly. Outputs go on every signal as
  `materiality_score` (0-100) plus a JSON `materiality_factors` explaining
  the score (so the frontend signal card can show "why this is material").
- Why: Spec metric "materiality precision >70%". Today's scoring is a single
  weight, not factor-attributed. Antigravity's signal cards need the factor
  breakdown.
- Priority: high
- Status: **done** (2026-05-09 — specs/SPEC_031_materiality_scoring.md, migration 058, services/materiality.py, api/routes/materiality.py, 29 tests green. Factor-attributed v1; learned weight tuning deferred to SPEC-028 Learning Service.)

### [BACKEND] Source registry with quality scoring (5 dimensions)
- Filed: 2026-05-09 by Claude (from spec §8.3)
- Need: A `sources` table with per-source quality across 5 dimensions:
  coverage, latency, predictive_accuracy, stability, license_health. Computed
  nightly. Surfaced via `GET /sources/health` for the Source Health admin UI.
- Why: Today connectors are hard-coded; no learned weighting. Spec target:
  source weights influence materiality scoring + evidence ranking.
- Priority: medium
- Status: **done** (2026-05-09 — `specs/SPEC_027_source_registry.md`,
  migration 055, `services/source_registry.py`, `api/routes/sources.py`,
  36 tests green. 5-dim scoring with documented weights + license-health
  linear degradation. `predictive_accuracy` placeholder until SPEC-028.)

### [BACKEND] Evidence ledger — content-addressed claim provenance
- Filed: 2026-05-09 by Claude (from spec §8.2)
- Need: Append-only `evidence_ledger` table: `source_id`, `source_url`,
  `archived_snapshot_ref` (S3 key for snapshot), `retrieved_at`,
  `extraction_method` (agent + model + prompt versions), `extracted_text`
  (exact passage), `confidence` (calibrated 0-1), `contradicting_evidence_ids[]`.
  Every Claim node in the graph references one or more ledger records.
- Why: Spec hallucination-control invariant: "every claim must be linkable to
  one or more evidence ledger records." Today provenance is `provenance_source`
  string — not reproducible, not content-addressed.
- Cross-cutting: spec §11.2 reproducibility ("given a decision_id, recreate
  exact evidence available at decision time"). Frontend Evidence Panel +
  evidence-affordance click-throughs depend on this.
- Priority: high
- Status: **done** (2026-05-09 — `specs/SPEC_024_evidence_ledger.md`,
  migration 053, `services/evidence_ledger.py`, `api/routes/evidence_ledger.py`,
  35 tests green. Append-only DB triggers + content-addressed snapshots.)

### [BACKEND] War-game adversaries — multi-agent role-play
- Filed: 2026-05-09 by Claude (from spec §6.3.2)
- Need: Replace current single move-suggester with adversary panel:
  - `CompetitorAgent` (one per top-3 competitor, prompted with that
    competitor's known strategy + recent moves + financial position from KG)
  - `PayerAgent` (formulary economics, IRA pressure, recent decisions)
  - `RegulatorAgent` (FDA/EMA posture, advisory committee patterns)
  - `KOLAgent` (clinical opinion-leader + patient advocacy reactions)
  Each reacts per option per round (default 3 rounds). Discipline rule:
  every adversary action MUST be tagged with a historical precedent or
  stated strategy from the KG. Outputs: war-game transcript per option.
- Why: Spec calls this "the most distinctive capability." Current war room
  scoring matrix is static; adversary role-play is the simulation upgrade.
- Cross-cutting: write `specs/SPEC_024_adversary_war_game.md`. Frontend
  War-Room mode (real-time multi-user with adversary transcripts) depends.
- Priority: medium
- Status: **done** (2026-05-09 — `specs/SPEC_028_war_game_adversaries.md`,
  migration 056, `services/war_game_adversary.py`,
  `api/routes/war_games.py`, 22 tests green. Grounding rule enforced at
  DB level via NOT NULL FK on grounding_evidence_id. StubReactor produces
  deterministic grounded actions; LLMGatewayReactor is a ~50-line swap.)

### [BACKEND] Monte Carlo simulation service
- Filed: 2026-05-09 by Claude (from spec §6.3.1)
- Need: Probabilistic outcome distributions — for each Brief option, run N
  trials with parameter uncertainty, return distribution + sensitivity ranking
  + assumptions log + reproducibility seed.
- Why: Spec mode for pricing decisions, launch-timing, R&D portfolio prio.
- Priority: medium (deferred until Decision Brief object lands)
- Status: open

### [BACKEND] LLM Gateway — centralized provider + prompt registry
- Filed: 2026-05-09 by Claude (from spec §10.3)
- Need: Promote `llm_telemetry.chat_with_telemetry` into a proper Gateway
  service: prompt registry (versioned, addressable by prompt_id), provider
  abstraction (route per-task), centralized cost guardrails, PII filter on
  the way out, content-policy filter on the way in. Every prompt used in
  prod is registered + tied to outcomes (so Learning Service can attribute
  prediction accuracy to specific prompt versions).
- Why: Today prompts are scattered across services. Spec calls this
  "non-negotiable" for cost visibility, prompt versioning, provider
  portability, and PII safety.
- Priority: medium
- Status: **done** (2026-05-09 — `specs/SPEC_026_llm_gateway.md`,
  migration 054, `services/llm_gateway.py`, `api/routes/llm_gateway.py`,
  46 tests green. Prompt registry + PII filter (email/SSN/phone/Luhn-CC) +
  cost summary endpoint. Provider abstraction deferred to follow-up.)

### [BACKEND] Learning Service — source-weight + agent-strategy updates
- Filed: 2026-05-09 by Claude (from spec §6.5.2)
- Need: Nightly job + on-review-trigger that:
  1. Compares predicted vs actual outcome on every Decision past `review_at`
  2. Attributes accuracy to source(s) that contributed evidence
  3. Updates `sources.predictive_accuracy` (raises good sources, demotes bad)
  4. Flags prompt versions with poor accuracy for review
  5. Retrains recommendation calibration model when N new outcomes accumulated
- Why: This is the "flywheel rotating" — today we capture outcomes but don't
  feed them back into source weights or prompt selection.
- Depends on: Source registry (above) + LLM Gateway (above).
- Priority: medium
- Status: **done** (2026-05-09 — specs/SPEC_032_learning_service.md, migration 060, services/learning_service.py, api/routes/learning.py, 24 tests green. EWMA source.predictive_accuracy update + prompt flagging. Sync run; APScheduler wiring deferred.)

### [BACKEND] Counter-recommendation enforcement
- Filed: 2026-05-09 by Claude (from spec §6.4.1)
- Need: Recommendation Agent must always return at least one well-argued
  counter-recommendation alongside its top pick. Rejected if it doesn't.
  Spec: "A unanimous AI is a suspicious AI."
- Why: Cheap, high-trust win. Antigravity needs the dissent payload to render
  a "Dissent view" panel in the Decision Workspace.
- Priority: low (cheap to add when Decision Workspace is being built)
- Status: **done** (2026-05-09 — specs/SPEC_033_counter_recommendation.md, migration 061, services/counter_recommendation.py, api/routes/recommendations.py, 31 tests green. score_based + dimension_split methods; <2 options returns 422 instead of faking dissent.)

### [BACKEND] Decision signing + immutable evidence_snapshot
- Filed: 2026-05-09 by Claude (from spec §6.4.2 + §11.2)
- Need: On decision commit, freeze `evidence_snapshot` (a content hash of all
  ledger records referenced by the brief at commit time) and cryptographically
  sign the immutable fields with the decision-maker's session token. Replay
  endpoint: `GET /decisions/{id}/replay` reconstructs exact agent calls,
  prompts, and outputs from snapshot + LLM call log.
- Why: Spec "every decision is reproducible." Required for audit/compliance.
- Depends on: Evidence ledger (above) + LLM Gateway (above).
- Priority: medium
- Status: **done** (2026-05-09 — specs/SPEC_034_decision_signing.md, migration 062, services/decision_signing.py, api/routes/decision_signing.py, 33 tests green. HMAC-SHA256 + immutable evidence_snapshot + replay endpoint. Asymmetric PKI deferred.)

### [BACKEND] /ask graph-traversal natural-language endpoint
- Filed: 2026-05-09 by Claude (from spec §9.2.4 "Ask-Anything")
- Need: NL → Cypher (or SQL recursive CTE) → graph traversal. Returns
  graph-shaped result (nodes + edges, deep-linkable to entity pages), not a
  flat search result list.
- Why: Spec persistent overlay; every page can ask "show me every product in
  my TA whose payer access has degraded in the last 90 days."
- Priority: medium
- Status: **done** (2026-05-09 — specs/SPEC_035_ask_graph.md, migration 063, services/ask_engine.py, api/routes/ask.py, 32 tests green. 6 NL patterns; LLM-fallback parsing deferred to follow-up.)

---

## Game-theoretic simulation backlog (Claude)

> Adds formal game-theoretic structure to the war-game layer. All three items
> roll up under `specs/SPEC_025_game_theoretic_simulation.md`. Depends on
> SPEC_028 War-Game Adversaries landing first.

### [BACKEND] Bayesian war-game upgrade — incomplete-information adversaries
- Filed: 2026-05-09 by Claude (from game-theory recommendation)
- Need: Each adversary agent carries a "type distribution" over private states
  (e.g., CompetitorAgent type ∈ {aggressive, defensive, cash-constrained} with
  prior probabilities sourced from KG signals). Each round samples a type per
  adversary; reactions are belief-distributions, not point reactions. Output:
  posterior over outcomes per option after N rounds.
- Why: Pharma adversaries have private info (pipeline state, internal Phase 2
  reads, cost structure). Treating them as fully observable misses the central
  uncertainty in CI strategy.
- Depends on: SPEC_028 war-game adversaries.
- Priority: medium
- Status: **done** (2026-05-09 — see specs/SPEC_025_game_theoretic_simulation.md, migration 057, services/game_theory.py, api/routes/game_theory.py, 25 tests green)

### [BACKEND] Stackelberg sequencing module — leader-follower analysis
- Filed: 2026-05-09 by Claude (from game-theory recommendation)
- Need: For any Decision Brief option that is timing-sensitive (launch date,
  readout date, regulatory submission date), compute the Stackelberg-optimal
  competitor counter-move. Algorithm: enumerate competitor's response set,
  apply their estimated payoff function (sourced from KG + recent moves),
  return arg-max counter. Surface as a "Stackelberg outlook" panel in the
  simulation output: "If you accelerate Phase 3 readout 4 months, the
  Stackelberg-optimal Pfizer response is to fast-follow with PRGN-2009 +
  defensive pricing in 2L."
- Why: Pharma launches are inherently sequential — first-mover sets context,
  follower optimizes against it. Current simultaneous-move war-game misses
  this structure.
- Depends on: SPEC_028 war-game adversaries.
- Priority: medium
- Status: **done** (2026-05-09 — see specs/SPEC_025_game_theoretic_simulation.md, migration 057, services/game_theory.py, api/routes/game_theory.py, 25 tests green)

### [BACKEND] POMDP value-of-information service
- Filed: 2026-05-09 by Claude (from game-theory recommendation)
- Need: For any pending Decision Brief, compute expected information value
  of waiting for upcoming signals (earnings calendar, FDA action calendar,
  conference dates from KG). Frame the brief as a POMDP: signals → posterior
  belief update → optimal action under updated belief. Compare expected utility
  of "decide now with current belief" vs "wait W weeks, decide with updated
  belief minus W·discount_rate." Surface as a "Wait vs Decide" panel.
- Why: Strategists routinely face the question "is it worth waiting for the
  next earnings call?" Today this is intuition; the POMDP gives a principled
  answer with explicit assumptions.
- Priority: medium
- Status: **done** (2026-05-09 — see specs/SPEC_025_game_theoretic_simulation.md, migration 057, services/game_theory.py, api/routes/game_theory.py, 25 tests green)

---

## Frontend backlog (Antigravity)

> All items below trace to spec §9 (Frontend Design Specification). Items
> marked **[needs backend]** are blocked on a corresponding [BACKEND] item
> above; items marked **[buildable now]** can ship against today's API.

### [FRONTEND] Sensing Feed as default Inbox surface — [buildable now]
- Filed: 2026-05-09 by Claude (from spec §9.1.1)
- Need: Replace current InboxTab with a Sensing Feed: per-user materiality-
  ranked signal stream, organized by entity (focal product, top competitors,
  key indications). Each signal card shows: source, timestamp, materiality
  score WITH the factors driving it (waiting on backend factor breakdown but
  ship without first), KBQ view(s) it changed, one-click "frame as decision."
- Spec ref: §9.1.1 Always-On Sensing Mode
- Reads: `GET /signals` (cursor-paginated), `GET /inbox`
- Priority: high
- Status: open

### [FRONTEND] Confidence as a first-class visual — [buildable now]
- Filed: 2026-05-09 by Claude (from spec §9.2.1)
- Need: Every claim, recommendation, forecast across the app renders with a
  visible confidence indicator. Never show a number without uncertainty;
  never collapse a range into a point estimate without explicit user click.
  Build a `<Confidence value={0.74} />` primitive with tier coloring + tooltip.
- Spec ref: §9.2.1
- Priority: high
- Status: open

### [FRONTEND] Evidence panel — one-click from any claim — [buildable now]
- Filed: 2026-05-09 by Claude (from spec §9.2.2)
- Need: Every claim across the UI has an "evidence" affordance (small icon
  next to the claim) that opens a side panel showing: source, retrieved_at,
  exact passage, contradicting evidence (if any), agent reasoning that
  produced the claim. Build a `<EvidenceAffordance claimId={...} />` primitive.
- Spec ref: §9.2.2
- Reads: `GET /evidence/{claim_id}` (lightweight; backs onto current
  provenance fields until evidence ledger ships, then upgrades).
- Priority: high
- Status: open

### [FRONTEND] Disagreement-surface design — [buildable now]
- Filed: 2026-05-09 by Claude (from spec §9.2.3)
- Need: When two sources disagree on a claim (e.g., formulary tier 2 vs tier 3),
  the UI surfaces both side-by-side, ranks by source quality, lets the user
  designate which to accept or escalate.
- Spec ref: §9.2.3
- Priority: medium
- Status: open

### [FRONTEND] Decision Workspace — multi-panel single-page surface — [needs backend]
- Filed: 2026-05-09 by Claude (from spec §9.1.2)
- Need: 5-panel layout per spec:
  - Brief panel (top): question, options, time horizon, stakeholders (editable
    until simulation runs)
  - Evidence panel (left): KBQ views, deep-linkable to source records
  - Simulation panel (center): scenario / Monte Carlo / war-game outputs with
    interactive sensitivity controls
  - Recommendation panel (right): ranked options, Dissent view, commit action
  - Reasoning trace (collapsible drawer): full chain of agent calls + prompts
    + intermediate outputs
- Spec ref: §9.1.2
- Blocked on: Decision Brief object backend [BACKEND above]
- Priority: high
- Status: open

### [FRONTEND] War-Room Mode — real-time multi-user — [needs backend]
- Filed: 2026-05-09 by Claude (from spec §9.1.3)
- Need: Multiple users join the same Decision Brief, see live-updating
  evidence + simulations, run new war-game rounds with custom adversary
  prompts, chat alongside the workspace. Session persisted as Decision Brief
  artifact when room closes.
- Spec ref: §9.1.3
- Blocked on: war-game adversary backend + WebSocket/SSE channel
- Priority: medium
- Status: open

### [FRONTEND] Outcome Dashboard — predictions vs outcomes — [partial-now / full-needs-backend]
- Filed: 2026-05-09 by Claude (from spec §9.3 + §13.1)
- Need: Surface that shows: prediction accuracy over time (current
  InsightsTab is the seed), source-quality trends, agent-strategy performance.
- Spec ref: §9.3, §13
- Buildable now from `GET /insights`; full version blocked on Source registry
  + Learning Service.
- Priority: medium
- Status: open

### [FRONTEND] Source Health admin surface — [needs backend]
- Filed: 2026-05-09 by Claude (from spec §9.3)
- Need: Per-source freshness, error rates, license status, quality scores
  (5 dimensions). Power-user / admin surface.
- Spec ref: §9.3
- Blocked on: Source registry [BACKEND above]
- Priority: low
- Status: open

### [FRONTEND] Ask-Anything persistent overlay — [needs backend]
- Filed: 2026-05-09 by Claude (from spec §9.2.4)
- Need: Persistent NL input (⌘K palette feel) that runs graph traversals.
  Results render as graph-shaped result (nodes + edges, deep-linkable to
  entity views), not flat search list.
- Spec ref: §9.2.4
- Blocked on: `/ask` endpoint [BACKEND above]
- Priority: medium
- Status: open

### [FRONTEND] Reasoning trace UI — [partial-now]
- Filed: 2026-05-09 by Claude (from spec §10.4 observability)
- Need: Collapsible drawer in Decision Workspace showing full chain of agent
  calls, prompts, intermediate outputs. Backend already has `llm_call_log`;
  needs surface to render trace given a brief_id or decision_id.
- Spec ref: §10.4 ("trace ID surfaced in the Reasoning Trace UI panel")
- Priority: medium
- Status: open

---

### [FRONTEND] SPEC-030 deferred items — minor a11y/UX backlog
- Filed: 2026-05-09 by Frontend Claude (from SPEC-030 §14 red-team)
- Items deferred from Stage 6 FIX-ALL to a future loop:
  - **#12 Reuse `<Drawer>` primitive in `ReasoningTraceDrawer`** —
    `frontend/src/components/ui/Drawer.tsx` has a fixed
    title/subtitle/children API that doesn't fit a timeline; refactor
    Drawer to expose a slot-style API first, then port. Anti-slop
    issue, not a UX bug.
  - **#15 `getRole()` × 4 across codebase** — extract to
    `frontend/src/hooks/useRole.ts`; touches CIPage, BriefPanel,
    SignalDetail, ConnectorPermissionsTab. Low risk; out of scope
    for SPEC-030 (changes pre-existing files outside the spec).
  - **#16 Three modal patterns rolled separately** — build a shared
    `<Modal>` primitive in `components/ui/`, port NewBriefDialog,
    KeyboardHintDialog, OptionEditor.
  - **#17 "Options (N / 5)" hardcoded max** — pull cap from a single
    constant; align UI with backend invariant.
  - **#18 Edit-option flow not wired** — OptionEditor supports
    `mode="edit"`+`onRemove`; BriefPanel only invokes create.
  - **#19 No add-evidence affordance for editable states** — spec
    §8.3 calls for it; ships with SPEC-032 (war-game evidence flow).
  - **#20 Destructive remove-option without confirm** — small
    UX-only backlog item.
  - **#21 Mouse hover sets selected index** — list keyboard/mouse
    interaction polish; Linear has the same UX, deemed acceptable.
  - **#22 Pagination silently truncates at 50** — `it.todo` exists.
    Build cursor scroll + state filter chip group together.
  - **#23 Filter chip group not implemented** — pairs with #22.
  - **#24 Commit decision button has no on-button help** — minor.
  - **#25 War-game `title` attribute is poor a11y** — minor; the
    sibling `aria-describedby` span already covers screen readers.
  - **Nits #27/#28** — redundant `role="textbox"`,
    `STATE_META` re-export — cosmetic.
- Priority: medium (cosmetic + small UX); none block Stage 7.
- Status: open

### [FRONTEND] SPEC-030 deploy gate — Lighthouse a11y on changed surfaces
- Filed: 2026-05-09 by Frontend Claude
- Need: run `npx lighthouse <route> --only-categories=accessibility`
  on `/ci?tab=decisions` and `/ci/decisions/:id`, light + dark.
  Target ≥95. RALPH_LOOP §5 mandates this; Stage 5 environment had no
  headless Chromium so the score is unverified.
- Status: open (must clear before Stage 7 closes)

### [FRONTEND] 401 redirect destination needs a real /login surface
- Filed: 2026-05-09 by Frontend Claude (from SPEC-030 fix #11)
- Stage 6 wired `expectJson` to dispatch `mz:auth-expired` and
  `App.tsx` redirects to `/?session=expired`. Landing page does not
  yet read `?session=expired` and show a banner; this is the missing
  follow-up.
- Status: open

### [FRONTEND] SPEC-041 deferred items — minor a11y / ops polish
- Filed: 2026-05-09 by Frontend Claude (from SPEC-041 §13a red-team)
- Deferred from Stage 6 FIX-ALL to a future loop:
  - **#5** Console.error wrap captures dev-mode noise — needs an
    allow-list of own-source frames, deny-list of React internals.
  - **#6** Hover state mutates DOM imperatively in `FeedbackButton`
    — replace with `:hover` CSS rule.
  - **#7** Pill missing focus-ring polish — match SPEC_022 token
    `box-shadow: 0 0 0 3px rgba(28,110,247,0.15)`.
  - **#8** No idempotency key on submit — double-click can land
    twice. Add a client-side UUID + retry semantics.
  - **#9** No drag-drop attachment path (paste only). Scriptiva
    reference has it; small win.
  - **#10** No size cap on description / payload — cap at 10 KB
    text and 5 MB total payload client-side.
  - **#12** Category + priority pickers mouse-only — `1`-`6` for
    category, `←/→` for priority.
  - **#13** Q4 pill placement on `/workspace` needs visual
    verification — Stage 7 attached screenshot is the gate.
  - **#14** No client-side payload size cap.
  - **#15** `sync.sh` portability (bash + python). Document or
    rewrite in pwsh-portable form.
  - **#16** `python` vs `python3` portability in `sync.sh`.
  - **#17** `/triage-feedback` `git log -30` — bump to `--all
    --since=6mo`.
  - **#18** Human-mode `/process-feedback` lacks rate cap.
  - **#19** Modal pattern rolled separately for the 4th time —
    finally extract `<Modal>` primitive (joins SPEC-030 backlog #16).
  - Nits 20-24 from §13a.
- Priority: medium (none block usability; PII filter from M1
  already covers the actual privacy risk).
- Status: open

### [FRONTEND] SPEC-041 admin retraction UI for `DELETE /feedback/{id}`
- Filed: 2026-05-09 by Frontend Claude (from SPEC-041 fix M4)
- Stage 6 added `DELETE /feedback/{id}` on the backend +
  `feedbackApi.remove()` on the frontend. There is no per-user
  retraction UI yet — the slash commands use it to purge resolved
  duplicates during triage. Build: a `/admin/feedback` admin view
  that lists submissions and exposes a "delete" action behind
  `mz_auth_role === 'enterprise'`.
- Priority: medium (privacy mitigation already in via PII filter)
- Status: open

### [FRONTEND] vitest parallel-mode flakes — 3 pre-existing tests
- Filed: 2026-05-09 by Frontend Claude
- Symptom: `__tests__/primitives/{DisagreementPanel,EvidenceAffordance}`
  + `src/components/__tests__/GraphContextMenu` flake under default
  `npx vitest run` parallel mode (different test fails each run,
  always near 5s timeouts). All pass under
  `npx vitest run --no-file-parallelism`. Pre-existing; not
  introduced by SPEC-030 or SPEC-041.
- Suggested fix: bump `waitFor`/`findBy*` timeouts on the affected
  tests, or limit `vitest.config.ts` `pool.threads.maxThreads` to 4.
- Priority: low (workaround documented; doesn't block CI per-file)
- Status: open

# 2026-05-09 — Frontend takeover (Frontend Claude in Antigravity's seat)

The previous frontend agent (Antigravity) was unable to continue. A second
Claude instance has assumed the Frontend Lead role per `AGENTS.md §11`.
Frontend branches from this date forward use the prefix `claude-fe/*` to
disambiguate from backend Claude's `claude/*` branches.

Master frontend spec: `specs/SPEC_029_app_aesthetics_upgrade.md` (Draft;
pending user sign-off). Ralph-style 7-stage loop process documented in
`docs/process/RALPH_LOOP.md`.

Mini-specs queued under SPEC_029 §9 (skipping 031 which is backend's
Materiality Scoring): SPEC_030, 032, 033, 034, 035, 036, 037, 038, 039, 040.

## [BACKEND] (Frontend-filed) Confirm `materiality_factors` JSONB shape on `/signals` items
- Filed: 2026-05-09 by Frontend Claude (consumer of SPEC_031)
- Need: When backend SPEC_031 lands, ensure `GET /signals` and
  `GET /signals/{id}` include `materiality_factors` in the response payload
  alongside `materiality_score`. Shape used by FactorBar primitive:
  `{ source_tier: number, entity_criticality: number, claim_type: number,
  recency: number }` — each 0-1, weighted contribution to the 0-100 score.
- Why: SPEC_035 Sensing Feed v2 renders factor bars on every signal card.
  Currently signals expose `materiality_score` but not the breakdown.
- Priority: medium (blocks SPEC_035 only; SPECs 030/032/033/034 can ship first)
- Status: open

## [BACKEND] (Frontend-filed) Optional: war-game adversary preview helper
- Filed: 2026-05-09 by Frontend Claude (consumer of SPEC_028)
- Need: A helper endpoint or precomputed seed to suggest groundable
  `evidence_ids` per adversary kind (competitor / payer / regulator / KOL)
  for a given brief, so the Decision Workspace "Start war-game" dialog can
  preview "what evidence is available to ground each adversary?" without
  forcing the user to know UUIDs. Could be:
  - `GET /war-games/preview-adversaries?brief_id={id}` →
    `{ competitor: { suggested_evidence_ids: [...] }, payer: {...}, ... }`
- Why: SPEC_032 War-Game UI starts a run; without preview the user has to
  paste evidence_ids by hand. Not a blocker — UI can ship with a "paste
  evidence_ids" textarea fallback in v1.
- Priority: low (UX nicety; ship SPEC_032 v1 without it)
- Status: open

## [BACKEND] (Frontend-filed) `POST /decisions/from-brief` — mint decision_id from a committed brief
- Filed: 2026-05-09 by Frontend Claude (consumer of SPEC_023 + SPEC_021)
- Need: When a SPEC_023 Decision Brief transitions to `committed`, it
  requires `decision_id` to be set on the brief. Today there's no clean
  bridge between a brief and a SPEC_021 `decisions` row.
- Proposed shape:
  ```
  POST /decisions/from-brief
  Body: { brief_id: UUID, rationale?: string, predicted_outcome?: string }
  Response 201: { decision_id: UUID, brief_id: UUID, committed_at: ISO8601 }
  ```
  Side effects: creates `decisions` row, sets `decision_briefs.decision_id`,
  appends a `state_log` entry transitioning the brief to `committed`.
  Ideally atomic (single transaction).
- Why: SPEC_030 Decision Workspace v2 ships a "Commit decision" button.
  Without this endpoint the button is disabled-with-tooltip; once it lands
  the button enables in `decision_pending` state and the workspace becomes
  end-to-end usable.
- Priority: medium (SPEC_030 ships v1 with the button disabled; once
  endpoint lands frontend wires it via tooltip-flip)
- Status: open

## [BACKEND] (Frontend-filed) Decision calibration time-series endpoint
- Filed: 2026-05-09 by Frontend Claude
- Need: `GET /decisions/calibration?since=YYYY-MM-DD&until=YYYY-MM-DD` →
  `{ buckets: [{ stated_confidence: 0.7, actual_correct_rate: 0.62, n: 18 }, ...] }`
  for the Decisions list "calibration sparkline" header.
- Why: SPEC_030 Decision Workspace v2 wants a small calibration trend chart
  (Outcome Dashboard partial). Existing `/insights` endpoint returns latest
  calibration but not the time-series.
- Priority: medium (ship SPEC_030 v1 without it; chart added in v2 once
  endpoint lands)
- Status: open

## [PROTOCOL] Spec number reservation convention
- Filed: 2026-05-09 by Frontend Claude
- Issue: Both Claude teams independently planned to use SPEC_031 (backend
  for Materiality Scoring, frontend for War-Game UI). Caught before either
  shipped, but the protocol should prevent this in future.
- Proposal: Add a "Spec numbers in flight" section to top of
  `docs/AGENT_BACKLOG.md`. Each agent claims a number by appending a line
  there before authoring the spec. First-to-write wins; the other rebases.
- Frontend has reclaimed: SPEC_029, 030, 032, 033, 034, 035, 036, 037, 038, 039, 040.
- Backend currently holds: SPEC_031.
- Priority: low (one-time clarification, not recurring blocker)
- Status: open

## [PROTOCOL] SPEC-029 number collision — frontend committed first; backend has a `claude/spec-029-framing-triggers` branch
- Filed: 2026-05-09 by Frontend Claude
- Issue: Frontend Claude committed `specs/SPEC_029_app_aesthetics_upgrade.md`
  on branch `claude-fe/spec-029-aesthetics` (commit 053dce1) at ~2026-05-09.
  Subsequently noticed backend Claude has a local branch
  `claude/spec-029-framing-triggers` (no commits yet beyond main's tip
  0bea866). Both teams appear to have planned SPEC-029 independently.
- Resolution per AGENTS.md §6: "whoever opens a PR first wins. Other rebases."
  Frontend has committed; backend's branch is empty. Frontend keeps SPEC_029.
- Action requested from backend Claude: rename branch to e.g.
  `claude/spec-041-framing-triggers` (next free number) and use SPEC_041 for
  the framing-triggers spec content. Frontend's mini-spec block (§9 of
  SPEC_029) currently runs 030–040; if backend prefers a number outside
  that block, please use SPEC_041 or higher.
- Priority: urgent (resolve before either team's PR lands)
- Status: open

---

# Spec numbers in flight (claim-by-write convention — start of day)

Each agent claims a spec number by appending a line below BEFORE authoring
the spec content. First entry wins; the other rebases. This list is
append-only; resolved entries stay for audit.

| # | Title | Owner | Branch | Status |
|---|---|---|---|---|
| 029 | App-wide Aesthetics Upgrade | Frontend Claude | `claude-fe/spec-029-aesthetics` | committed (053dce1) |
| 030 | Decision Workspace v2 | Frontend Claude | `claude-fe/spec-029-aesthetics` | Stage 1 sign-off complete |
| 031 | Materiality Scoring (factor-attributed) | Backend Claude | `claude/spec-031-materiality` | committed (c12b905) |
| 032 | War-Game Multi-Adversary UI | Frontend Claude | (planned) | reserved |
| 033 | Source Health admin + Cost Telemetry | Frontend Claude | (planned) | reserved |
| 034 | Connectors page reskin | Frontend Claude | (planned) | reserved |
| 035 | Sensing Feed v2 + Signals + Watchlist | Frontend Claude | (planned) | reserved |
| 036 | Cockpit-grade Landing | Frontend Claude | (planned) | reserved |
| 037 | Workspace (chat + canvas) reskin | Frontend Claude | (planned) | reserved |
| 038 | Search reskin | Frontend Claude | (planned) | reserved |
| 039 | Catalog reskin | Frontend Claude | (planned) | reserved |
| 040 | Auth surfaces | Frontend Claude | (planned) | reserved |
| 041 | User Feedback Loop (in-app widget + autonomous triage) | Frontend Claude (cross-cutting) | `claude-fe/spec-041-feedback-loop` | merged 2026-05-11 (PR #35) |
| 042 | Centralized Product Backlog (consolidate four legacy backlogs) | Frontend Claude (docs) | `claude-fe/spec-042-product-backlog` | merged 2026-05-11 (PR #36) |
| PB-104 | Multi-select KBQ chips · 2-hour bug fix (E1.S1.4) | Frontend Claude | `claude-fe/loop-5-pb-104-kbq-chips` | merged 2026-05-11 (PR #71) |
| PB-301 | Entity dossier scaffold (frontend half of E3.S3.1) | Frontend Claude | `claude-fe/loop-6-pb-301-dossier-scaffold` | merged 2026-05-11 (PR #72); BE-6 (PR #57) unmerged |
| PB-501 | Payoff matrix scaffold (frontend half of E5.S5.1) | Frontend Claude | `claude-fe/loop-7-pb-501-payoff-matrix` | merged 2026-05-11 (PR #73); BE-8 (PR #59) unmerged |
| PB-201 | Agent identity strip (frontend half of E2.S2.1) | Frontend Claude | `claude-fe/loop-8-pb-201-agent-identity` | merged 2026-05-11 (PR #74); BE-3 (PR #50) merged 2026-05-11 — unblocks PB-202 next |
| Loop #9 | Swap mocks→real for PB-301 + PB-501 after BE trio merge | Frontend Claude | `claude-fe/loop-9-swap-mocks-to-real` | merged 2026-05-11 (PR #75) |
| Loop #10 | UI integration pass (sidebar / dossier chrome / strategy group / agent tint) | Frontend Claude | `claude-fe/loop-10-ui-integration` | merged 2026-05-11 (PR #76) |
| Loop #11 | Design system fixup (Fraunces canonical / borderless / type scale / spacing) | Frontend Claude | `claude-fe/loop-11-design-system-fixup` | merged 2026-05-11 (PR #77) |
| Loop #12 | Type-scale migration (pages + visible primitives) + codemod | Frontend Claude | `claude-fe/loop-12-type-scale-migration` | merged 2026-05-11 (PR #78) |
| Loop #13 | Delete `!important` legacy slate block + slate-class codemod | Frontend Claude | `claude-fe/loop-13-delete-legacy-slate` | merged 2026-05-11 (PR #79) |
| Loop #14 | `.mz-elevated` hover-bloom primitive + 4 card surfaces | Frontend Claude | `claude-fe/loop-14-elevation-primitive` | Stage 7 deploy in progress |
| 043+ | (free — either side may claim) | — | — | available |

