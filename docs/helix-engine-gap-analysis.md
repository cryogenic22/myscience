# Helix Engine — Gap Analysis & Convergence Plan

*Analysis of the lead's two design docs vs. what we have built. 24 May 2026.*

**Source docs analysed**
- `MarketZero_Helix_Engine_Design.md` — the **engine**: 7 source classes, connector contract, Entity 360 data product, Context Layer API, 3-agent ownership map, quality/latency targets, 90-day plan.
- `MarketZero_Helix_v5_Three_Agents_One_Fabric.html` — the **product decomposition**: three agents (Data Automaton / Intelligence Agent / Helix), one fabric (registry + event bus + audit log + visual language), per-agent autonomy dials with audit-logged ceiling override, cross-agent fact-version propagation.

---

## 0. The one-sentence verdict

**We have the breadth (20+ connectors, war-game, KBQ, dossier, signals, and — as of this week — a temporal facts ledger) but not the spine the lead is describing: a single Context Layer over a unified fact store, three agents with clean event-driven boundaries, and a frontend organised as those three agents rather than as a "CI module."**

The good news: the lead's design is not a rewrite. It is a *re-spine*. Most of our code becomes the *implementation* of the three agents; what's missing is the connective tissue (Context Layer, one event bus, the Entity 360 as the API) and the discipline of clean boundaries. The facts ledger we just shipped (PB-1307) is, by luck and design, exactly the right foundation stone — it is just not yet load-bearing.

---

## 1. The target architecture, stated plainly

Two orthogonal pictures that must both be true:

### 1a. The engine (data → intelligence)
```
SOURCES → [7 connector classes] → FACTS (temporal, evidence-linked, append-only)
                                     │
                                     ▼
                            ENTITY 360  (composed view per entity, time-travel-able)
                                     │
                                     ▼
                          CONTEXT LAYER API  (5 ops, hides storage)
                  get_entity_360 · query_facts · traverse · semantic_search · emit_event
                                     │
                        ┌────────────┼────────────┐
                     Data Auto.  Intelligence    Helix
```

### 1b. The three agents (one fabric)
| Agent | Section (UI) | Loop | Owns | Safe ceiling |
|---|---|---|---|---|
| **Data Automaton** | Data | acquire→normalise→extract→reconcile→publish | ingestion + knowledge (connectors, entity resolution, fact ledger, reconciliation) | L4 ref/corp · L3 signal · L2 inferred |
| **Intelligence Agent** | Intelligence | scope→template→assemble→verify→compose→publish | reasoning (KBQ chains, dossier composition, verification) | L3 ref/corp · L2 signal/inferred |
| **Helix** | Engagement | sense→decide→act→learn | action (war room, decisions, watch) | L2 default, L1 inferred |

**The fabric** = (1) shared canonical entity registry — one ID space; (2) one event bus — `fact:published / fact:superseded / dossier:refreshed / move:committed / decision:recorded`; (3) one audit log — every agent action with user/level/fact-class/rationale; (4) one visual language. Agents **never call each other directly** — only via the event bus and the Context Layer.

**Our pragmatic constraint (already decided):** Postgres-only. The lead's doc names Neo4j/Qdrant/Redpanda; we implement the **logical** architecture (graph via recursive CTEs, vectors via pgvector, event bus as a table + dispatcher). We adopt the *contracts*, not the *infrastructure sprawl*.

---

## 2. Gap analysis — eight dimensions

Maturity scale: ⬤⬤⬤⬤ built-to-spec · ⬤⬤⬤◯ solid, needs hardening · ⬤⬤◯◯ partial/drifted · ⬤◯◯◯ stub · ◯◯◯◯ absent.

| # | Dimension | Maturity | What exists | The gap |
|---|---|---|---|---|
| 1 | **Connector model** | ⬤⬤⬤◯ | `BaseConnector` (`fetch/source_type/health_check`), 20+ connectors, full `Provenance` on every `RawRecord`, SHA-256 raw hash | Contract is `discover/fetch` only — **no `extract`/`publish`** stage; no **source classes** (each source is bespoke); doc extraction lives outside the connector path |
| 2 | **Facts / temporal model** | ⬤⬤⬤◯ | NEW `facts_ledger.py` + migration 065: point/interval/**anticipatory**, append-only (DB trigger), supersession, `facts_as_of()`, evidence link, tenant column | **Standalone.** Nothing asserts facts during ingest; war-game & dossier still read raw `signals`/`market_events`. Two truth-models run in parallel |
| 3 | **Entity 360** | ⬤⬤◯◯ | `dossier.compose_dossier()`, `query_engine.entity_dossier()`, `graph.traverse/neighborhood` | Three different entry points, none canonical; **defensive try/except silently empties sections** (masks staleness); not `as_of`-parameterised; synthesis is a separate call |
| 4 | **Context Layer API** | ⬤◯◯◯ | The pieces exist as scattered service methods | No typed, single API surface. Agents/routes call services & SQL directly → coupled to storage. No enforced provenance/freshness/tenant at one boundary |
| 5 | **Event bus** | ⬤⬤◯◯ | TWO buses: `agent/event_stream.py` (agent telemetry) + `event_collector→impact_router→intelligence_feed` (market events) | Not unified; not the v5 vocabulary; no cross-agent `fact:superseded → dossier:refresh → move:stale` chain as a real subscription. Today it's table polling + direct calls |
| 6 | **Three-agent boundaries** | ⬤⬤◯◯ | Maps loosely: Data Auto ≈ research_agent+entity_agents+data_steward; Intelligence ≈ dossier+kbq_views+query_engine; Helix ≈ war_game+decision_brief | Data Automaton is **3 uncoordinated services** with no shared state or contract; boundaries are fuzzy; agents call services directly, not the bus |
| 7 | **Unstructured extraction (PDF/PPT)** | ⬤⬤◯◯ | `document_extractor` (PDF/DOCX/HTML/TXT plain text), `document_ner`, `extraction/*` schemas, SEC 8-K item extractors | **Plain-text only** — no layout/section awareness, **no table structure, no PPT, no chart extraction**. A 10-K loses its structure; class 3/5 of the engine doc is unbuilt |
| 8 | **Autonomy levels (L1–L4)** | ⬤◯◯◯ | `agent/permissions.py` trust tiers (PUBLIC/STANDARD/ELEVATED/SYSTEM) + session modes; `budget.py` token caps | No L1–L4 ceiling model **per agent per fact-class**; no audit-logged override; war-game has no execution tier; the v5 three-dial topbar is unbuilt |

### Frontend (separate axis)
| Area | Maturity | Note |
|---|---|---|
| Helix design system (dark war-room, accent rails, fact glyphs, serif/mono) | ⬤⬤⬤◯ | `frontend/src/lib/helix.ts` + reskinned CI surfaces. Visual language largely lands the v5 look |
| Information architecture (3 agent sections: Engagement/Intelligence/Data) | ⬤◯◯◯ | We have a "CI module" with tabs, not the three work-named sections with per-agent level pills |
| Agent Activity view (3-column live agent state) | ⬤◯◯◯ | Loop-21 added an activity feed; not the 3-column parallel-loop centrepiece |
| Provenance w/ cross-agent chain | ⬤◯◯◯ | Evidence cards exist; the 3-row Data→Intel→Helix propagation chain is not wired to real events |
| Entity 360 / Dossier panel | ⬤⬤◯◯ | KbqDossier + dossier pages exist; not driven by a Context-Layer `get_entity_360` |

---

## 3. Where we've drifted (the honest part)

1. **Feature sprawl without a spine.** 70+ services, a 76-item backlog, many overlapping specs (SPEC_015 appears twice, two SPEC_003/004/029 etc.). We built war-game adversaries, game theory, decision signing, framing triggers, materiality, learning service — many of these are *Helix-layer* features sitting on a fact substrate that doesn't formally exist yet. They read raw tables. **This is the "build the pipeline and consumption in the same process" mistake Marcus Chen calls out in the v5 doc.**

2. **Two fact-models.** `market_events → signals → evidence_records/claims` (the existing pipeline) vs. the new `facts` ledger. Decisions are currently made on `signals`, which have no temporal `as_of` and no supersession lineage. The anticipatory-fact capability — the thing that makes war-game "what-if as of 2027" honest — is built but unused.

3. **Storage-coupled consumers.** Routes and agents reach into SQL/services directly. There is no boundary where provenance, freshness, tenant scope, and version selection are enforced once. Every consumer re-implements (or forgets) these.

4. **Frontend organised by feature, not by agent.** The v5 thesis is that naming the three agents changes what you build and sell. Our UI is a "CI" tab-set; it doesn't make the three loops legible, which is precisely the procurement-grade story.

### What's genuinely right (don't throw away)
- The connector `Provenance` discipline is excellent and already matches the engine doc's intent.
- The facts ledger is the correct foundation and well-tested.
- The Helix visual language is largely there.
- Recursive-CTE graph + pgvector is the right Postgres-only call — do not adopt Neo4j/Qdrant/Redpanda.
- War-game grounding (validate evidence against DB, downgrade confidence on stripped citations) is the right instinct — it just needs to read facts, not raw signals.

---

## 4. The core — what we are actually building

Cutting through everything, the product is **one sentence**:

> A system that turns sources into **temporal, evidence-linked facts**, composes them into **time-travel-able Entity 360s**, exposes them through **one Context Layer**, and runs **three agents** over that fabric — a factory (Data Automaton) that produces truth, an analyst (Intelligence Agent) that composes dossiers, and a theatre (Helix) where humans war-game decisions with full provenance and compounding memory.

Everything else is a feature of one of those three agents. If a piece of work doesn't make the **fact → 360 → Context Layer → agent** spine more real, it is premature.

---

## 5. Convergence plan — disciplined, phased

Principle: **build the spine, then re-seat existing features onto it.** Each phase has a hard acceptance test grounded in the real engagement data the lead cites (CagriSema, REDEFINE 4, Lilly Q1 2026 PR, the Zepbound stale-pricing chain). One Ralph loop per numbered step; tests first.

### Phase A — The Spine (highest leverage, ~2–3 loops)
**A1. Make the facts ledger load-bearing.** Write an assertion path from the existing pipeline: `market_events`/`signals` → `assert_fact()`. Backfill the demo entities. Add `query_facts(filter, as_of, tenant, min_confidence)` to the ledger.
**A2. Context Layer skeleton (`services/context_layer.py`).** Five typed ops: `get_entity_360`, `query_facts`, `traverse`, `semantic_search`, `emit_event`. Initially wraps existing services — but it is the *only* sanctioned entry point; it attaches provenance + freshness + tenant at the boundary; **no silent empty sections** (return explicit `unavailable` with reason).
**A3. Entity 360 as a pure function.** Refactor `dossier`/`query_engine` so `get_entity_360(id, projection, as_of, tenant)` is canonical and `as_of`-parameterised, reading facts from the ledger.

> **Acceptance:** `get_entity_360("prod:cagrisema", as_of="2026-01-15")` returns a coherent, provenance-rich view; passing a future `as_of` surfaces the anticipatory WAC fact. War-game and dossier panel both consume this single call.

### Phase B — One Event Bus + the cross-agent chain (~2 loops)
**B1. Unify on one event vocabulary** (`fact:published/superseded`, `dossier:refresh_proposed`, `move:evidence_stale`, `decision:committed`) as a Postgres `events` table + lightweight dispatcher/subscriptions. Fold the two existing buses behind it.
**B2. Wire the stale-evidence chain end-to-end:** Data Automaton supersedes a fact → emits `fact:superseded` → Intelligence subscribes, queues dossier refresh → Helix subscribes, flags the affected move. Surface the 3-row chain in Provenance.

> **Acceptance:** Ingesting the Lilly Q1 2026 PR supersedes the Zepbound pricing fact and the three-row Data→Intel→Helix chain renders in Provenance against real events, not mocks.

### Phase C — Three agents, made explicit (~2 loops)
**C1. Cohere the Data Automaton:** one orchestrator over connectors→extract→reconcile→`assert_fact`/`supersede_fact`→`emit_event`. research_agent/entity_agents/data_steward become stages, not islands.
**C2. Autonomy levels:** per-agent, per-fact-class L1–L4 ceiling model + audit-logged override (extend `permissions.py`). Persist overrides to the audit log.

> **Acceptance:** The three agents run as three loops emitting to one bus; raising Helix above its inferred-class ceiling writes an audit-log entry with user/level/rationale.

### Phase D — Frontend re-spine (~2 loops, can parallelise w/ C)
**D1. Reorganise the shell into three sections** (Engagement/Intelligence/Data) with per-agent level pills + the three-dial topbar.
**D2. Agent Activity view** (3-column parallel loops) + Provenance cross-agent chain driven by the Phase-B events.

> **Acceptance:** A user lands on Engagement, opens Agent Activity, sees three loops; clicking a stale-evidence banner opens the real cross-agent chain.

### Phase E — Unstructured depth + connector classes (later, larger)
**E1. Connector contract → `discover/fetch/extract/publish`; group into the 7 source classes.**
**E2. Layout-aware PDF (sections + tables), then PPT/slide + chart extraction (class 3 & 5).**
**E3. Class 7 internal docs + tenant scoping + RLS enforcement** (activates the `tenant_scope` column).

> **Acceptance:** A Lilly 10-K and the ECO 2026 deck yield section/slide-level facts with page/slide provenance; an uploaded tenant doc triangulates with public signals and never leaks across tenants.

---

## 6. What to stop / defer

- **Stop** adding net-new Helix-layer features (more adversary types, more scoring) until Phase A makes them read facts. They compound the two-model debt.
- **Defer** Neo4j/Qdrant/Redpanda indefinitely — implement the contracts on Postgres.
- **Defer** full multi-tenant RLS to Phase E; keep the nullable column as the seam (already done).
- **Consolidate** the duplicate/overlapping specs into the canonical `docs/PRODUCT_BACKLOG.md` and retire the rest, so the three-agent map is the single source of structure.

---

## 7. Recommended immediate next step

**Phase A1 + A2** — wire the facts ledger into ingestion and stand up the Context Layer skeleton. It is the smallest change with the largest architectural payoff: it converts the facts ledger from a clever standalone into the spine every other piece hangs from, and it gives us the single boundary the lead's whole design depends on. Everything in Phases B–E becomes straightforward once the Context Layer is the only door.

---

*Prepared as the requested analysis-first deliverable. No code changed. Awaiting direction on whether to proceed with Phase A.*
