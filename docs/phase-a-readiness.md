# Phase A Readiness Pack — Spine Convergence

*The gate before any Phase A code. Answers the lead's open questions from the codebase, locks the Context Layer contract, revises the loop budget honestly, and enumerates the migration surface. 24 May 2026.*

Companion to `docs/helix-engine-gap-analysis.md`. This doc supersedes that doc's §5 loop estimates and §6 enforcement note.

---

## 0. The operating contract — how each loop runs

Every numbered step below is one **Ralph loop**, run with this fixed cadence. No step skips a stage.

| Stage | What it produces | Gate to advance |
|---|---|---|
| **SPEC** | A short `SPEC_*.md` (problem, contract, acceptance test, out-of-scope) | Acceptance test is runnable, not aspirational |
| **DESIGN** | Types + signatures + data flow, reviewed against anti-slop index | No duplicate of an existing utility; boundaries named |
| **BUILD** | Implementation, tests-first (TDD) | New tests written *before* impl |
| **RED-TEAM** | Adversarial pass: what does this hide, lie about, or silently swallow? | A written list of found gaps |
| **TEST + FIX** | Green suite (`pytest`, `vitest`), gaps from red-team closed | 0 unit failures; coverage ratchet not decreased |
| **RIGOR / DRIFT** | Check vs SPEC acceptance + check for scope drift and convention drift | Acceptance test passes; no undeclared scope added |
| **PUSH** | Conventional commit, branch, PR, Railway deploy verified live | Health check green; acceptance reproduced in prod |

This is the discipline the convergence requires. I will not mark a step "done" without the acceptance test reproduced against the deployed system.

---

## 1. The lead's open questions — answered from the code

### Q2 — What does `permissions.py` actually do? (checked `services/agent/permissions.py`)
**Finding:** It is **tool-level RBAC**, not an autonomy model. Four `TrustTier`s (PUBLIC/STANDARD/ELEVATED/SYSTEM) × three `SessionMode`s, deciding whether a *tool call* is allowed. The decision log is **`self._decisions: list` — in-memory, ephemeral, not persisted, not append-only, not exportable** (`permissions.py:64`).

**Implication (lead was right):** C2 is **not** "extend `permissions.py`." The L1–L4 ceiling is a **new orthogonal axis** — autonomy level *per agent per fact-class*, distinct from per-tool trust tier. The two coexist (RBAC stays at the tool boundary; the ceiling governs agent autonomy). And the **audit log must be a real persisted, append-only, exportable table** — the in-memory list is procurement-unfit. **→ Phase C is 3 loops (ceiling model · audit-log table · override flow), confirmed.**

### Doc-extractor — can it produce a paragraph-level `source_locator` for the Lilly Q1 PR? (checked `services/document_extractor.py`)
**Finding:** **No.** `ExtractedDocument` is `pages: list[str]` plus `full_text` and coarse `metadata` (`document_extractor.py:39-52`). pdfplumber gives **page text only** — no paragraph structure, no section headings, no tables, no `source_locator`.

**Implication (lead was right):** The Phase B acceptance test cannot resolve to "page 3, paragraph 2, Pricing-strategy section" today. **Resolution adopted:**
- Phase B uses a **page-level** `source_locator` (`{doc_id, page}`) — achievable now.
- The cross-agent chain demo asserts the Zepbound anticipatory pricing fact via a **seeded `assert_fact()`** (page-level provenance), so the *event chain* is real even though the extraction is coarse.
- **Paragraph/section/table-level extraction becomes a hard E2 dependency**, explicitly blocking the v5 paragraph-locator demo until then. Phase E2 is pulled to the front of Phase E for this reason.

### Bus enumeration & migration surface
Answered in §4 below (full producer/consumer lists + shim checklist).

---

## 2. Revised loop budget (honest)

Adopting the lead's calibration. A "loop" = one full SPEC→PUSH cadence (§0), not a calendar week.

| Phase | Steps | Loops | Was |
|---|---|---|---|
| **A — Spine** | A1 assert facts on ingest + backfill · A2 Context Layer skeleton + migrate entity-view consumers · A3 Entity 360 as pure `as_of` function | **4** | 2–3 |
| **B — One bus** | B0 enumerate+shim (done here) · B1 unify behind one events table · B2 cross-agent stale chain (page-level locator) | **2** | 2 |
| **C — Three agents** | C1 cohere Data Automaton · C2 L1–L4 ceiling model · C3 persisted append-only audit log + override flow | **3** | 2 |
| **D — Frontend re-spine** | D1 three sections + per-agent dials · D2 Agent Activity wired to **real** Phase-B events | **2** | 2 |
| **E — Unstructured depth** | E2 layout/section/table PDF (pulled forward) · PPT/slide · chart · class-7 + tenant RLS | **6–8** | "later" |
| | **Spine total (A–C)** | **9** | |

**Calendar, stated under both assumptions** (the lead's point — "two loops" is not a budget without loop length):
- If a loop ≈ 1 working session and A–C run single-threaded: spine in ~9 sessions. D can run in parallel with C (different surface, frontend) → shaves ~2.
- E is a quarter on its own and should not be promised against A–C.

**Drift guardrail:** if any Phase-A step exceeds its loop budget, I flag it at the *start* of the overflow, not at the end — with the specific scope that grew.

---

## 3. Context Layer interface specification (design locked before build)

`services/context_layer.py` — the **only** sanctioned door for reading composed entity state. Five typed ops. The fill-state model makes "no silent empty section" **structurally impossible** — it is a type invariant, not a convention.

### 3.1 The fill-state type (the keystone)
```python
class FillState(str, Enum):
    POPULATED            = "populated"
    UNAVAILABLE_NO_DATA  = "unavailable_no_data"   # queried, nothing matched
    UNAVAILABLE_STALE    = "unavailable_stale"     # data exists but past freshness SLA
    UNAVAILABLE_BLOCKED  = "unavailable_blocked"   # tenant scope / permission
    UNAVAILABLE_ERROR    = "unavailable_error"     # upstream failed — SURFACED, not swallowed

@dataclass
class Section:
    key: str
    fill: FillState
    as_of: datetime
    data: Any | None = None
    reason: str | None = None          # REQUIRED whenever fill != POPULATED
    provenance: list[FactRef] = field(default_factory=list)
    freshness: Freshness | None = None # newest/oldest contributing fact timestamps

    def __post_init__(self):
        if self.fill is FillState.POPULATED and self.data is None:
            raise ContextContractError(f"{self.key}: POPULATED section has no data")
        if self.fill is not FillState.POPULATED and not self.reason:
            raise ContextContractError(f"{self.key}: {self.fill} requires a reason")
```
A section can never be silently empty: either `POPULATED` with `data`, or an explicit unavailable state **with a reason**. The dataclass refuses to construct otherwise.

### 3.2 The five operations
```python
def get_entity_360(entity_ref: str, *, projection: list[str] | None = None,
                   as_of: datetime | None = None, tenant: str | None = None) -> Entity360: ...
    # Entity360 = { identity, sections: dict[str, Section], as_of, tenant }
    # as_of=None → now. Future as_of surfaces anticipatory facts.

def query_facts(filter: FactFilter, *, as_of: datetime | None = None,
                tenant: str | None = None, min_confidence: float = 0.0) -> list[Fact]: ...
    # Reads facts_ledger.facts_as_of under the hood; attaches provenance + freshness.

def traverse(start: str, edge_types: list[str], *, depth: int = 1,
             filter: dict | None = None, tenant: str | None = None) -> SubGraph: ...
    # Wraps graph.traverse (recursive CTE). Postgres-only — no external graph DB.

def semantic_search(query_text: str, *, scope: dict | None = None,
                    k: int = 20, tenant: str | None = None) -> list[Ref]: ...
    # pgvector. Candidates only — never ground truth alone.

def emit_event(event_type: str, payload: dict) -> EventId: ...
    # The one bus (Phase B). Vocabulary: fact:published|superseded,
    # dossier:refresh_proposed, move:evidence_stale, decision:committed.
```

### 3.3 Error semantics (explicit, not defensive)
- **Entity not found** → raise `EntityNotFound` (the *entity* is the request; absence is an error).
- **A section's sub-query fails** → caught **only** at the section boundary, returned as `Section(fill=UNAVAILABLE_ERROR, reason=str(exc))`, logged at ERROR. Never swallowed, never returns `[]`. The 360 as a whole still returns.
- **Tenant-scoped data the caller can't see** → `UNAVAILABLE_BLOCKED` for a *requested* section; silently filtered for a bulk `query_facts` list (RLS semantics).
- **Write ops absent by design:** no `insert_fact`/`update_fact`/`delete_fact`. Facts enter via the Knowledge plane; derived assertions use a separate gated path (engine doc §5.3).

### 3.4 The "no silent empty" enforcement (test, not guideline)
1. **Structural:** `Section.__post_init__` (above) — the type can't represent a silent empty.
2. **Lint test** `tests/test_context_layer_contract.py`: greps `services/context_layer.py` + `services/dossier.py` composition functions and **fails** on any `except …: (pass | return [] | return None | continue)` inside a section builder. The defensive try/except called out in the gap analysis (`dossier.py:118,150,188`) gets refactored to the fill-state model in A2/A3, and this lint keeps it from returning.

---

## 4. Migration audit — the surface behind "Context Layer is the only door"

### 4.1 Entity-view consumers → **migrate in A2** (reads that belong behind `get_entity_360`)
| Consumer | Calls | Action |
|---|---|---|
| `api/routes/dossier.py:32` | `compose_dossier` | A2 — route reads via `get_entity_360` |
| `api/routes/query.py:41,53` | `.query()`, `.entity_dossier()` | A2 |
| `api/routes/graph.py:42,59,85` | `neighborhood/traverse/entity_summary` | A2 (graph stays a CL op, route stops calling service directly) |
| `api/routes/entities.py:68` | `entity_summary` | A2 |
| `api/routes/search.py:254` | `entity_summary` | A2 (search ranking stays; entity hydration via CL) |
| `api/routes/kbq.py` | `build_entity_kbqs` | A2 |

### 4.2 Raw-SQL-on-core-tables consumers → **migrate later** (not all in A2)
~18 route files run raw SQL on `drugs/companies/trials/signals/market_events/evidence_records`. **Not** all are entity-view reads. Classification:
- **A2 now (entity hydration):** `catalog.py`, `search.py` (the entity-read portions).
- **Phase B (event/feed reads):** `signals.py`, `intelligence.py`, `agents_activity.py`, `materiality.py` — these are bus consumers, migrate with the bus.
- **Later / leave (writes, admin, telemetry, curation):** `steward.py`, `metrics.py`, `inbox.py`, `decisions.py`, `enrichment.py`, `evidence_batch.py`, `catalog.py` (write/curation paths).

**Compatibility story:** the Context Layer **wraps** existing services in A2 — consumers switch their *read* calls to `get_entity_360`/`query_facts`, but the underlying services keep working. No big-bang rewrite. Writes and admin paths are explicitly **out of A2 scope**.

### 4.3 The two buses — shim checklist for Phase B (so no subscription breaks silently)
**Bus 1 — agent telemetry** (`agent/event_stream.py`, `agent_events` table)
- Producer: `agent/harness.py` (TURN_START / TOOL_* / SESSION_*).
- Consumer/route: `GET /agent/events` (`api/routes/agent.py:93`).

**Bus 2 — market events** (`event_collector → impact_router → intelligence_feed`)
- Producers: `event_collector.py:_persist_event`; 12 `event_emitters/*`; callers `ctgov_diff_service`, `sec_8k_pipeline`, `spl_diff_service`; `impact_router.py:299,381` (→ `impact_assessments`).
- Consumers/routes: `intelligence_feed.get_feed`; `GET /intelligence/feed[/summary|/{id}]` (`api/routes/intelligence.py`).

**Shim plan (B1):** introduce one `events` table with a `bus` discriminator + nullable bus-specific columns; route old producers/consumers through it behind their existing function signatures; keep `agent_events`/`market_events` as **views** over the unified table during a deprecation window so no consumer breaks on day one. Verify each route (`/agent/events`, `/intelligence/feed`) returns identical payloads pre/post cutover (golden test).

---

## 5. Feature-freeze ownership (the one decision that's not mine)

The gap analysis §6 says "stop net-new Helix-layer features" during the spine work. That is a **roadmap decision, not an engineering one** — it needs an owner. You (as product owner) are that owner. The recommendation: a **soft freeze on net-new Helix-layer features for the duration of Phase A–C** (the ~9 spine loops), with bug-fixes and the in-flight PB-1303 war-game allowed to finish or pause. Without this, spine loops compete with feature loops and the budget in §2 slips on politics, not code.

---

## 6. What I need from you to start

Two gates, then I begin **A1** under the §0 cadence:
1. **Approve the revised 9-loop spine budget** (A–C) and the decision to pull **E2 forward** (paragraph/table extraction is a real dependency of the v5 demo).
2. **Confirm the soft feature-freeze** scope for Phase A–C (or tell me the carve-outs).

On approval, A1 starts with `SPEC_A1_fact_assertion_on_ingest.md` and a runnable acceptance test: *ingesting a market_event asserts a corresponding fact; `get_entity_360` (A2) then reads it; a seeded future-dated WAC fact is invisible now and visible `as_of=2027`.*
