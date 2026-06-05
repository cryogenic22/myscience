# SPEC_DATA_001 — Data & Sense Layer Remediation

*Status: proposed · Author: Claude Code · Date: 2026-06-05*
*Companion analysis: `docs/data-sense-layer-status.html` · Operating method: `docs/data-agent-playbook.md`*

> This spec turns the live-verified diagnosis into an executable program for a **data + engineering
> squad** running in parallel to the product/UX loops. It is scoped to the **substrate** —
> ingestion freshness, entity connection, schema richness, fact quality, and narrative grounding —
> *not* to new product surfaces. Every workstream is independently shippable, gated on the **real
> Railway DB**, and ordered by leverage.

---

## 0. Context & ground truth (verified 2026-06-05)

The substrate is further along than the 01-Jun `intelligence-layer-*` docs assume: the facts
ledger is **alive (9,858 facts / 17 predicates / 4 classes)** — the A1 "ledger = 1 row" bug is
fixed. The remaining problems are **specific and surgical**, surfaced by one read-only prod probe
plus four code sweeps:

| Symptom | Evidence (live) | Root cause |
|---|---|---|
| 2 clinical sources 105 days stale | `drug_labels` last 19 Feb (185 rows); `adverse_events` last 19 Feb (2,075) | openFDA Labels/FAERS jobs died silently; `etl_runs` shows 0 FAILURE, 10 stuck RUNNING |
| PMC empty despite daily schedule | `pmc_articles` = 0 with 4,381 pubmed rows | PMC connector dependency/failure not surfaced |
| ChEMBL runs → orphan | `bioactivities` 628 (6d) **100% drug_id NULL**; `molecular_targets` = 0 | connector never links compounds to drugs; no link rule in pack |
| market_events barely grounded | **99.6% (37,186/37,325) `primary_entity_id` NULL**; top dup group **1,041 copies** | name resolution rarely fires on news/SEC text; ingest dedup didn't backfill |
| literature weakly linked | **66% (2,889/4,381) `drug_id` NULL** | `EVIDENCE_FOR` link only fires on a clean drug string |
| ledger partly low-trust | `market_event` = 3,301 facts (33%); **35% of facts `source_doc_id` NULL** | bulk noise from unlinked/duplicated events; pre-DR-5 facts unlinked |
| metrics/graph unciteable | materialized views + graph edges carry no source/as-of | provenance not stamped at aggregation/link time |
| resolution debt growing | `unresolved_entities` 46,579↑, `hitl_review_queue` 29,429↑, `steward_actions` 263 (flat) | no drain; staleness hook uses hardcoded table map |
| strategic tables empty | `patents` 0, `drug_pricing` 0 | connectors unwired / no source data (NADAC) |

**Non-goals:** new UI surfaces, war-game/decision features, multi-tenant isolation, auth — those
live in the product tracks (master-plan Tracks B/D/F/G). This spec stops at "the substrate is fresh,
connected, rich, and citeable."

---

## 1. Operating contract (every workstream)

```
SPEC → DESIGN (reuse-first; grep anti-slop.md) → BUILD (TDD) →
RED-TEAM vs REAL Railway DB (additive/idempotent) → FIX → LOG + PR (one logical change) → next
```

- **Reuse-first.** Before adding any function/connector/emitter, read `.claude/rules/anti-slop.md`
  and `Grep` for the symbol. Extend, don't duplicate. Especially: `run_emitter` / `run_all_emitters`
  (`services/fact_emitters/`), `EntityConsolidator`, `entity_resolver`, `source_registry`,
  `scripts/backfill_fact_emitters.py`.
- **Prod writes are additive & idempotent** by default. Destructive cleanups (dedup deletes,
  backfills that mutate keys) are **SUPERVISED** — propose, get human sign-off, soft-delete
  (`record_status='superseded'`) over hard-delete, verify zero orphans.
- **No fabricated figures.** Every number in a PR/report traces to a query or is omitted.
- **Gate on the real DB.** A workstream is not "done" until verified against Railway prod, not a
  mock. Pass the DB URL inline; `.env` has `OPENAI_API_KEY` (use `load_dotenv()`) but not
  `DATABASE_URL`.
- **Test discipline.** TDD; new code needs a test (`.claude/rules/test-requirements.md`).
  Backend: `python -m pytest`. Coverage ratchet: never decrease test count.

---

## 2. Workstreams

Each workstream lists: **Problem → Investigate → Build → Acceptance gate → Files**. Effort: S <1d,
M 1–3d, L 3–7d.

### D1 — Connector freshness + failure alerting `[M]` ★ critical path

**Problem.** Two clinical sources (labels, FAERS) have been dead since 19 Feb and nothing noticed;
PMC writes 0; `etl_runs` records 0 FAILURE while 10 jobs hang in RUNNING. Staleness is invisible.

**Investigate.**
1. Why did openFDA Labels (Tue) and FAERS (Thu) stop on 19 Feb? Run each connector by hand against
   prod, capture the traceback. Suspects: openFDA API contract change, rate-limit/ban, chunk-index
   pointer stuck, exception swallowed in `_run_connector`.
2. Why is `pmc_articles` empty with 4,381 pubmed rows? Trace the PubMed→PMC dependency
   (`connectors/pmc.py`); confirm whether it runs and finds 0, or errors.
3. Audit `etl_runs` lifecycle: when/why is a run left in RUNNING; is FAILURE ever written?

**Build.**
- Record terminal states: a crashed/timed-out run must write `status='FAILURE'` with the error.
- Per-source freshness SLA (config, not one global `freshness_max_days`): e.g. CT.gov 2d, PubMed 2d,
  FAERS 14d, Labels 14d, ChEMBL 14d.
- Rewrite the staleness hook (`integration/pipeline_hooks.py:376-382`) to read `source_registry`
  instead of the hardcoded table map, so new sources are covered automatically.
- A `scripts/connector_health.py` (or extend `harness/measure.py`) that prints per-source: last
  success, rows, age vs SLA, last error — the one command the team runs each morning.

**Acceptance gate (real DB).** Labels + FAERS resume writing (newest row < SLA); PMC either
populates or its failure is recorded as FAILURE with a cause; `connector_health` flags any source
over SLA; a deliberately-broken connector run produces a FAILURE row + appears in the report.

**Files.** `scheduler/runner.py`, `scheduler/config.py`, `integration/pipeline_hooks.py`,
`services/source_registry.py`, `connectors/openfda_*`, `connectors/pmc.py`, `harness/measure.py`.

---

### D2 — market_events grounding + dedup `[L]` ★ critical path

**Problem.** 99.6% of events don't resolve to an entity, and one event exists in up to 1,041
copies. This is the biggest connection gap and it pollutes 33% of the fact ledger.

**Investigate.**
1. Sample 50 NULL-`primary_entity_id` events: how many *could* resolve (contain a known
   drug/company) vs are genuinely entity-less (macro news)? This sets the realistic ceiling.
2. Quantify duplication: `event_hash` coverage (migration added it but old rows are NULL); how many
   distinct events vs rows in a 5-yr window (prior probe: ~24× inflation).
3. Confirm the live ingest dedup (`_store_event` ON CONFLICT (event_hash)) actually fires on new
   rows (it only works once `event_hash` is set).

**Build.**
- Strengthen event→entity resolution: run resolved drug/company mentions through the existing
  6-strategy resolver at ingest; for back-data, a `scripts/reground_market_events.py` (additive:
  set `primary_entity_id` where confidently resolvable, log the rest).
- **Backfill `event_hash`** for legacy rows (read-time dedup already exists; this enables real
  collapse). Then a **SUPERVISED** dedup that soft-deletes dup copies keeping highest-trust/newest.
- Re-emit `market_event` facts only from grounded, deduped events (idempotent; old facts are
  append-only — document the cutover).

**Acceptance gate.** NULL `primary_entity_id` share drops materially on the resolvable subset
(report before/after with the realistic ceiling from the sample); dup groups collapse (1,041 → 1);
`market_event` facts no longer dominated by duplicates; zero orphaned links after dedup.

**Files.** `services/event_collector.py`, `integration/knowledge_store.py` (`_store_event`),
`integration/entity_resolver.py`, `scripts/` (reground + dedup), `services/fact_emitters/`.

---

### D3 — ChEMBL linkage (un-orphan bioactivities + targets) `[M]`

**Problem.** ChEMBL runs but `bioactivities.drug_id` is 100% NULL and `molecular_targets` = 0, so
the `BioactivityEmitter` emits nothing and there's no drug→target→activity path.

**Investigate.**
1. Does the ChEMBL connector ever populate `molecular_targets`? Why 0 rows despite a weekly run.
2. Why is `bioactivities.drug_id` never set — is the compound→drug resolution missing, or is the
   write path skipping it? (ChEMBL MCP `compound_search`/`get_mechanism` can confirm linkage keys.)

**Build.**
- Resolve ChEMBL compounds → `drugs` at ingest (reuse `entity_resolver`); set `bioactivities.drug_id`
  and write `molecular_targets`.
- Add the missing `bioactivities` link rule to `domain/pharma/pack.py` (drug → bioactivity →
  target) so it joins the entity graph.
- Map `target_activity` into `_PREDICATE_KBQ` (`services/kbq_views.py`) so the facts surface.
- Backfill via `scripts/backfill_fact_emitters.py` once linked.

**Acceptance gate.** `bioactivities.drug_id` non-NULL for resolvable compounds; `molecular_targets`
> 0; `BioactivityEmitter` asserts `target_activity` facts; they appear in the dossier/KBQ for a
known drug (e.g. a kinase inhibitor).

**Files.** `connectors/chembl*.py`, `integration/knowledge_store.py` (`_store_bioactivity`,
`_store_molecular_target`), `domain/pharma/pack.py`, `services/fact_emitters/mechanisms.py`,
`services/kbq_views.py`, `services/dossier_kb.py` (`_PREDICATE_DOMAIN` already has `target_activity`).

---

### D4 — Literature linkage (the 66% MeSH-only tail) `[M]`

**Problem.** Two-thirds of pubmed articles have no `drug_id`, so they never surface for a drug.

**Investigate.** Of the 2,889 NULL articles, how many carry MeSH descriptors that map (via
TA/mechanism) to a drug, vs are genuinely off-topic? Sets the bridgeable share.

**Build.** Extend the literature linkage to bridge via MeSH → therapeutic_area/mechanism →
drug (the `EVIDENCE_FOR` ontology path partially exists in `cross_linker`); a back-data
`scripts/relink_literature.py`. Then re-run `LiteratureEmitter`.

**Acceptance gate.** `pubmed_articles.drug_id` NULL share drops on the bridgeable subset; a drug
with known literature shows more `key_publication`/`disease_evidence` facts; before/after report.

**Files.** `integration/cross_linker.py`, `domain/pharma/pack.py`, `scripts/relink_literature.py`,
`services/fact_emitters/literature.py`.

---

### D5 — Evidence completeness (close the citation leak) `[M]`

**Problem.** 35% of facts have `source_doc_id` NULL → no drill-through; evidence compression drops
per-item source URLs before the LLM sees them.

**Investigate.** Which predicates account for the NULL `source_doc_id` facts (likely pre-DR-5
`market_event`/early backfill)? Which are backfillable from the source row vs genuinely sourceless?

**Build.**
- Backfill `evidence_records` + `facts.source_doc_id` for backfillable facts (reuse
  `facts_ledger._write_evidence`; idempotent on content-hash).
- Preserve provenance through `pack_evidence` (`services/ctx_evidence.py`) so compressed L2 still
  carries a citeable source id per merged snippet.

**Acceptance gate.** `source_doc_id` NULL share drops materially; a previously-uncited fact now
drills through to a source; a compressed-evidence chat answer still renders working citations.

**Files.** `services/facts_ledger.py`, `services/ctx_evidence.py`, `scripts/backfill_evidence.py`.

---

### D6 — Metric & graph provenance `[L]`

**Problem.** Materialized-view metrics and graph edges carry no source/as-of, so metric/graph
narratives ("23 drugs in P2-3", "X used alongside Y") are real but unciteable — the largest
ungrounded-prose risk.

**Investigate.** Inventory the materialized views (`services/metrics.py`) and graph edge builders
(`services/graph.py`, `cross_linker`): which can attach a source set + computed-at timestamp without
a schema rewrite.

**Build.** Stamp `computed_at` + a source/derivation reference on metric rows and graph edges;
thread it into `EvidenceItem`/`DossierFact` so the synthesis path can cite it. Make the fallback
narrative path emit at least a "derived from N records, as of <date>" provenance line.

**Acceptance gate.** A metrics-driven chat answer cites a derivation + as-of date; a graph-edge
claim drills to its supporting source(s); the fallback path no longer emits bare uncited prose.

**Files.** `services/metrics.py`, `services/graph.py`, `services/query_engine.py`,
`services/unified_handler.py`, `services/llm.py`.

---

### D7 — Resolution backlog drain `[M]`

**Problem.** `unresolved_entities` (46,579) and `hitl_review_queue` (29,429) are growing; steward
flat at 263.

**Investigate.** Composition of the backlog: how much resolves automatically *after* D2/D4 land
(better links + cleaner names) vs needs human triage.

**Build.** A re-resolution sweep (reuse `enrichment_runner` / `entity_resolver`) run after D2/D4;
report drop. (The SME triage *UI* is master-plan Track D — out of scope here; this workstream is the
automated drain only.)

**Acceptance gate.** `unresolved_entities` drops materially; new confident matches create aliases
that improve subsequent resolution; before/after report.

**Files.** `connectors/enrichment_runner.py`, `integration/entity_resolver.py`, `scripts/`.

---

### D8 — Empty strategic tables (patents + pricing) `[M]`

**Problem.** `patents` and `drug_pricing` are empty → no FTO/patent-cliff or WAC intelligence
(blocks DR-2 pricing facts).

**Investigate.** Confirm the source path: Orange Book patent fields / USPTO PatentsView for patents;
NADAC/CMS for pricing (note: prior finding — `nadac_prices` table absent, may need ingest first).

**Build.** Wire the patent connector (Orange Book patent block or USPTO) → `patents`; wire a pricing
ingest → `drug_pricing`; then the existing pricing/patent fact emitters can run.

**Acceptance gate.** `patents` + `drug_pricing` have rows; a known drug shows a patent expiry and a
WAC; DR-2 pricing facts emit.

**Files.** `connectors/fda_purple_book.py` / `connectors/uspto_patentsview.py`, `connectors/nadac*`,
`scheduler/config.py`, `services/fact_emitters/`.

---

## 3. Sequencing & dependencies

```
D1 (freshness/alerting)  ── unblocks trust; run first, it's how you'll verify everything else
        │
        ├── D2 (market_events grounding+dedup) ──┐
        ├── D3 (ChEMBL linkage)                   ├── D7 (resolution drain, after D2/D4)
        ├── D4 (literature linkage) ──────────────┘
        │
        ├── D5 (evidence completeness)  ── depends on D2 (re-emit grounded facts first)
        ├── D6 (metric/graph provenance) ── parallel, independent
        └── D8 (patents/pricing) ── parallel, independent
```

**Critical path:** D1 → D2 → D5 (grounded ledger → citeable). D3/D4/D6/D8 parallelise. D7 after
D2/D4. Two engineers: one takes D1→D2→D5, the other D3→D4→D6, D7/D8 shared.

---

## 4. Success metrics (re-probe at the end of each workstream)

| Metric | Today (05 Jun) | Target |
|---|---|---|
| Sources within SLA | ~5/11 | 9/11 (PMC/patents/pricing may stay out with documented reason) |
| ETL runs with terminal status | RUNNING leaks | 100% reach SUCCESS or FAILURE |
| market_events `primary_entity_id` NULL | 99.6% | < ceiling from sample (report the ceiling) |
| market_events max dup group | 1,041 | 1 |
| pubmed `drug_id` NULL | 66% | < bridgeable ceiling |
| bioactivities `drug_id` NULL | 100% | < 20% (resolvable) |
| facts `source_doc_id` NULL | 35% | < 10% |
| `market_event` share of ledger | 33% | falls as noise is removed |
| `unresolved_entities` | 46,579 | materially down, trend reversed |

---

## 5. Risks & guardrails

- **Destructive dedup (D2) is the riskiest step.** Soft-delete only; keep canonical = highest-trust;
  verify zero orphans across `facts.subject_entity_id`, `signals.primary_entity_id`, `entity_links`
  (the text-keyed spine refs the generic FK loop misses — see `EntityConsolidator` precedent).
- **Append-only ledger.** Old facts are not rewritten; cutovers must be documented, not silently
  mutated.
- **openFDA/ChEMBL rate limits.** Stagger; respect existing chunked-batch design.
- **Re-emission idempotency.** All emitters key on `object_value.source_row_id`; re-runs must skip,
  not duplicate — assert this in the gate.
- **Don't regress the product tracks.** This squad touches the substrate; coordinate cutovers
  (D2 re-emit, D5 backfill) so dossier/chat surfaces don't flicker.

---

## 6. Deliverables per workstream

1. Code + tests (TDD, real-DB gate green).
2. A **before/after probe** (the same query shape, run pre and post) pasted in the PR.
3. One-line backlog status update + memory note for the next session.
4. Conventional-commit PR, one logical change.
