# Data Agent Playbook — operating manual for the parallel data squad

*Author: Claude Code · 2026-06-05 · Pairs with `specs/SPEC_DATA_001_data_layer_remediation.md`
and `docs/data-sense-layer-status.html`.*

> **BIND FIRST: `.claude/rules/conservation-gates.md`** — the harness floor for every role.
> Your "verified against the real DB or it doesn't ship" rule below IS Principle 2 (conservation
> before correctness). The conservation invariants (freshness SLA, FK-orphan ceilings, evidence
> floor) are **yours to strengthen** via an owner-reviewed change — never loosen to pass. New
> connector ⇒ add a `FRESHNESS_SLA_DAYS` entry ⇒ Lane 2 (`operational-health.yml`) covers it.

> This is the **method**, not the work. It encodes how to investigate and fix the Market Zero
> data/sense layer so a separate agent (or engineer) can run a data workstream in parallel without
> stepping on the product/UX loops. Read it once, then run the loop. Internalize one rule above all:
> **claims are verified against the real DB or they don't ship.** This codebase has a documented
> history of a fabricated diagnosis draft — the gate below is the antidote.

---

## 1. Mission & boundary

**You own the substrate:** ingestion freshness, entity connection, schema richness, fact quality,
narrative grounding/provenance. **You do not own:** product surfaces, war-game/decision UX, auth,
multi-tenant. If a task needs a new UI tab, it's the wrong squad — hand it back.

Your north star: **fresh → connected → rich → citeable.** Raw rows are worthless until they resolve
to entities, link into the graph, become facts, and surface with a working source link.

---

## 2. The loop (run this for every workstream)

```
1. PROBE      measure the real DB first — never reason from the code alone
2. SPEC       write the problem + the realistic ceiling (sample before you promise a target)
3. DESIGN     reuse-first: grep anti-slop.md + the symbol; extend, don't duplicate
4. BUILD      TDD — test first, then the change
5. RED-TEAM   run against REAL Railway prod, additive + idempotent
6. PROVE      re-probe; paste before/after in the PR; numbers trace to queries or are omitted
7. LOG        one-line backlog + memory note; conventional-commit PR; next
```

Each step has teeth — sections 3–7 below.

---

## 3. PROBE — measure first

Before touching code, run the freshness/linkage probe. This is the single most important habit; it
catches "stale vs active," orphans, and dup bloat in one shot. Template (read-only, safe):

```python
# scripts/probe_substrate.py  — read-only; pass DB URL inline (NOT in .env)
import psycopg2
from datetime import datetime, timezone
DB = "<railway url inline>"          # .env has OPENAI_API_KEY, not DATABASE_URL
conn = psycopg2.connect(DB); cur = conn.cursor(); now = datetime.now(timezone.utc)

# freshness per source table: count + newest recency column + age
# linkage: count(*) FILTER (WHERE <fk> IS NULL) vs count(*)
# ledger: facts by predicate, by fact_class, source_doc_id NULL share
# backlog: hitl_review_queue, unresolved_entities, steward_actions
# dedup: GROUP BY (primary_entity_id, event_type, description) ORDER BY count DESC
```

(A working version was used to produce `data-sense-layer-status.html` — reuse/extend it; don't
rewrite from zero.)

**Probe rules**
- Pick the right recency column per table: `last_verified_at` → `retrieved_at` → `created_at` →
  `asserted_at` (facts) → `updated_at`. A table can *look* fresh on `created_at` but be stale on
  `retrieved_at` — prefer the ingestion-time column.
- A scheduled connector with **0 rows** or a **months-old newest row** is a silent failure — flag it.
- A high-volume table with a high **FK-NULL share** is orphaned data — volume ≠ value.
- Always sample before promising a target: "99.6% NULL" doesn't mean "fixable to 0%" — many news
  events are genuinely entity-less. Sample 50, find the *resolvable ceiling*, promise to that.

---

## 4. DESIGN — reuse-first (anti-slop)

This repo has 2,200+ exports and a real duplication problem. Before writing anything:
1. Read `.claude/rules/anti-slop.md` and `Grep` for the symbol.
2. Prefer extending these existing primitives:
   - **Facts:** `services/fact_emitters/` — `run_emitter(db, <Emitter>(), drug_id=…)`,
     `run_all_emitters`, `scripts/backfill_fact_emitters.py` (resumable cross-drug backfill).
     Emitters: `ClinicalTrialEmitter`, `AdverseEventEmitter`, `DrugLabelEmitter`,
     `MechanismEmitter`, `LiteratureEmitter`, `CompetitionEmitter`, document facts. Idempotency key =
     `object_value.source_row_id`.
   - **Ledger:** `services/facts_ledger.py` — `assert_fact`, `facts_as_of`, `_write_evidence`,
     `route_predicate_to_domain`.
   - **Resolution/linking:** `integration/entity_resolver.py` (6-strategy cascade),
     `integration/cross_linker.py`, `domain/pharma/pack.py` (declarative link rules),
     `domain/pharma/mention_normalizer.py`.
   - **Consolidation:** `integration/entity_consolidator.py` —
     `EntityConsolidator(db, rank_by_richness=True, drug_name_normalizer=combo_safe_normalize)`.
   - **Dossier/KBQ surface:** `services/dossier_kb.py` (`build_domains`, `_PREDICATE_DOMAIN`,
     `resolve_asset_to_subject` — richness-ranked), `services/kbq_views.py` (`_PREDICATE_KBQ`).
   - **Freshness:** `services/source_registry.py`, `scheduler/config.py` (CONNECTOR_SCHEDULES),
     `integration/pipeline_hooks.py` (staleness hook), `harness/measure.py`.
3. If you genuinely need a new emitter/connector, model it on the nearest sibling (read 2–3 first).

---

## 5. RED-TEAM — write to prod safely

Prod is the gate, but prod is also live. Rules, in order of importance:

1. **Additive + idempotent by default.** New facts/links/aliases only. Re-running must skip, not
   duplicate (assert the idempotency-skip in your gate).
2. **Destructive = SUPERVISED.** Any delete/merge/key-mutation (dedup, consolidation, hash backfill)
   needs explicit human sign-off in the turn. Then:
   - **Soft-delete** (`record_status='superseded'`) over hard-delete — reversible.
   - Canonical = **highest-richness** row (matches the resolver's ranking, so they agree).
   - **Repoint the text-keyed spine refs** the generic FK loop misses:
     `facts.subject_entity_id`, `signals.primary_entity_id`, plus `entity_links` (set-based, not
     per-link — per-link loops are pathological on high-degree nodes like "placebo").
   - Conflict-safe via SQL savepoints; verify **zero orphans** after.
3. **Connection hygiene.** Reconnect per long-running drug/loop (Railway drops idle connections); the
   backfill scripts already do this — follow the pattern.
4. **Cutovers, not silent rewrites.** The ledger is append-only. If you re-emit grounded facts (e.g.
   after D2 dedup), document the cutover; don't expect old facts to change.
5. **Rate limits.** openFDA/ChEMBL/PubMed throttle. Respect the chunked-batch design; stagger.

---

## 6. PROVE — the before/after discipline

- Run the **same query shape** before and after; paste both in the PR. Targets are claims —
  back them with the re-probe.
- No number ships unverified. If you can't query it, omit it or label it an estimate.
- If a workstream bounds coverage (top-N, sampling, "resolvable only"), **say so** — silent
  truncation reads as "covered everything" when it didn't.
- Re-read your own claims against the proof before committing (the explicit anti-fabrication step).

---

## 7. GATES (commands)

- **Backend:** `python -m pytest tests/ -v` (run touched suites first; full suite can hang on a slow
  live-DB test — a targeted-broad run is the reliable signal). Use `python`, not `python3`.
- **New code needs a test** (`.claude/rules/test-requirements.md`); never decrease test count.
- **Real-DB gate:** the workstream-specific acceptance gate in SPEC_DATA_001 §2, run on prod.
- **Frontend** (only if you touch it): from `frontend/` — `vitest <touched> --no-file-parallelism`,
  `tsc -p tsconfig.app.json --noEmit` (root tsconfig checks nothing), then `vite build` (deploy gate;
  tolerates pre-existing type errors).

---

## 8. Gotchas (learned the hard way)

- **Route shadowing.** `api/routes/entities.py` has greedy `GET /entities/{entity_type}[/{id}]` —
  any new 1- or 2-segment `/entities/X[/Y]` route is shadowed. Mount new endpoints on their own
  prefix; test through `create_app()` via TestClient, not just the service fn.
- **`fact_class` was once dropped in `facts_as_of`** — all facts rendered as `signal`. If you touch
  the ledger SELECT, keep `fact_class`.
- **Predicate must be mapped twice** to surface: `_PREDICATE_DOMAIN` (dossier) *and* `_PREDICATE_KBQ`
  (KBQ). A fact can exist and still be invisible (e.g. `target_activity`). Check both.
- **Duplicate drug rows** break resolution by table order — the resolver now richness-ranks; keep it.
- **`etl_runs` doesn't record FAILURE today** — a "successful-looking" scheduler can be silently
  dead. Don't trust SUCCESS counts; trust newest-row age.
- **market_events read-time dedup** hides table bloat in the UI — the ledger still ingests the
  duplicates. Fix at ingest (`event_hash`) + supervised collapse, not just at read.

---

## 9. Parallelism — staying out of the product squad's way

- **Branch per workstream:** `claude/data-<Dn>-<slug>`. One logical change per PR.
- **Touch the substrate, not surfaces.** If a fix changes what the dossier/chat renders (D2 re-emit,
  D5 backfill), flag it so the product squad expects the shift.
- **Coordinate cutovers.** Schedule re-emissions/backfills when they won't make a live demo flicker.
- **Leave a trail.** Each loop: one-line backlog status + a memory note (`MEMORY.md` pointer +
  topic file) so the next session resumes without re-discovery.

---

## 10. First-day checklist

1. Read `data-sense-layer-status.html` (what's broken) + `SPEC_DATA_001` (what to build).
2. Run the substrate probe yourself — confirm the numbers still hold (they drift daily).
3. Pick the critical path: **D1 → D2 → D5**. Start with D1 (freshness/alerting) — it's how you'll
   verify every later workstream.
4. For D1: reproduce the labels/FAERS 19-Feb death by running those connectors by hand against prod;
   capture the traceback before changing anything.
5. Ship D1 behind the loop above. Re-probe. Prove. Then D2.
