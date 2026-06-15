# Market Zero — Data & Intelligence Layer Strategy Audit

*Produced 2026-06-14 by a 20-agent audit workflow (10 subsystem maps + 4 live end-to-end
prod probes + 1 independent connector review → 3-lens strategy panel → synthesis →
adversarial critique). All prod numbers below were probed READ-ONLY against the Railway
prod Postgres this session unless tagged `[prior-session]`. The critique pass corrected
the synthesis where it drifted from probed ground truth; those corrections are folded in.*

---

## 1. Headline

**The sensing loop is INGEST-RICH and REASON-LIVE but CONVERSION-DEAD at two joints.**

The substrate is genuinely healthy and synthesis is live in prod — the platform can
*answer*. It cannot yet *sense* (detect & rank signals) or *scale* (onboard sources without
engineering), because two fully-built capabilities are not wired into the running system:

- **J1 — DETECTION is dead code.** `ImpactRouter.route_event` has **zero** production
  callers; `impact_assessments` is **empty (0 rows)**; so `derive_severity` can never
  return critical/high and **every** surfaced event is pinned `medium`. Signal promotion
  has been **stalled 11 days** (newest signal `2026-06-03`) — the promoter is fed
  unfiltered, so 95% of what it scans is `RECALL_CLASS_I` recall-noise and real events
  starve. `trust_score`/`source_tier` are uniform COALESCE defaults (`0.5`/`tier_3`).
- **J2 — ONBOARDING is unreachable.** The three generic connectors (CSV/REST/RSS) are
  production-grade code but absent from `CONNECTOR_REGISTRY`, with no config-persistence
  schema, no `load_connector_from_source_id` factory, and no scheduler dispatch. "Onboard
  any source as config" is true in code but cannot be reached from the product.

**Strategic consequence:** building *more connectors* (more coverage) before fixing
detection scales **blindness** — more sources feeding a read-only log that doesn't detect.
The right order is **WIRE BEFORE BUILD**, with a parallel **TRUST** track to clear the two
conservation gates that are RED on prod *right now*. This **supersedes** the prior
"finish all the L4 connectors next" plan.

---

## 2. Maturity scorecard (probed, honest grades)

| Layer | Grade | E2E status | One-line |
|---|---|---|---|
| Ingestion / bespoke connectors | **4/5** | wired & live | 14 sources within SLA, provenance 99.99%, outcome-vocab discriminates silent-zero. 105-day-stale failure mode is **absent**. |
| Reasoning (CTX pipeline / synthesis) | **3/5** | wired & live (DEFAULT, not opt-in) | CTX rollout 1.0; 1230 `ctx` vs 18 `legacy` telemetry rows/14d; LLM firing live. Guard is post-synthesis; provenance generically bucketed. |
| ETL pipeline | **3/5** | wired & live | Load-bearing; had a latent `NameError` on the auto-create path (**fixed this session**). DLQ failures log at DEBUG; PRE_STORE validates but doesn't block. |
| Entity resolution & consolidation | **3/5** | partial | Resolver + soft-delete conservation healthy (1 active dup drug). Two FK-orphan ceilings **RED on prod**; brand_name smear live. Consolidation **is** scheduled but only on full cycles. |
| Cross-linking, domain pack & graph | **3/5** | wired & live | 11.98M typed edges, **0 dangling/NULL endpoints**. A SUPPORT layer, not yet a SIGNAL layer (no competitor inference, no temporal clusters, no inverse edges). |
| Schema / migrations / conservation gates | **3/5** | partial | Two-lane structure sound & PR-hard. Two ceilings RED; migrations **089–090 absent from the worktree** (088→091, confirmed this session); deferred sources SKIP their SLA (vacuous-green). |
| **Sensing: feed / emitters / framing / scenarios** | **2/5** | partial (**the broken joint**) | Events land + dedup, feed read-path works — but impact dead, promotion stalled, framing manual-only, trust uniform. **Biggest lift, all wiring of written code.** |
| **Generic onboarding (DataHub L2–L4)** | **2/5** | opt-in-only | 3 connectors are 4-grade code; the 2 is the missing WIRING (persistence + factory + dispatch + pre-prod gate). |
| Autonomy (research agent / memory / steward) | **2/5** | partial | Components built; research agent dormant (`entity_data=None`); DataSteward marks `completed` with no FAIR-delta proof. Open loop. |
| Eval harness | **2/5** | partial | Tiers + fail-closed gates well-designed, but smoke gate scores SYNTHETIC responses (can't catch real regression) and the content gate runs post-deploy only. |

---

## 3. End-to-end verification (live prod probes)

| Chain | Verdict | Key probed evidence |
|---|---|---|
| Ingestion → DB | **WORKS** | `connector_health.py`: 14 sources, 7 GREEN / 6 AMBER / 1 RED, all within freshness SLA. `nadac` silent-zero correctly tagged `FAILURE_ZERO_ROWS`. Facts 15047/15048 carry `source_doc_id` (99.99%). The 1 RED (`mesh_ontology`) is the stuck-RUNNING-orphan gate firing as designed, not a data break. |
| DB → resolution → graph | **PARTIAL** | 11.98M `entity_links`, 0 NULL endpoints, 1 active dup drug (soft-delete healthy). **RED:** `clinical_trials.drug_id` orphan **11.24% > 10%** (658 trials), `pubmed_articles.drug_id` **20.07% > 20%** (932 articles) — Lane-2 pytest FAILED live. Brand smear live: 291 active drugs share a brand across distinct generics (ozempic→22); 72% of branded actives lack a resolving alias. |
| DB → sensing → signals | **PARTIAL** | `market_events` 39,984 fresh (today); `/intelligence/feed` serves 455 deduped rows. **But** `impact_assessments`=0; `ImpactRouter` zero callers; signals stalled at `2026-06-03`; 13,234/13,242 entity-linked 30d events unpromoted; `trust_score`=0.5/`tier_3` uniform across 13,726 rows. RECALL flood: 38,497 raw → 431 distinct. |
| Query → CTX → synthesis | **WORKS** | `MZ_UNIFIED_HANDLER` default-on (rollout 1.0). `ctx_telemetry` 1230 `ctx` / 18 `legacy` (14d); `llm_call_log` fired today (gpt-4o-mini 1155 + gpt-4o 78 / 30d). Grounding substrate rich. Weak spot: `landscape`-intent queries log 0 evidence; routing-attribution telemetry silently dropped (kwarg-signature TypeError swallowed). |

---

## 4. The target sensing approach

A **closed, conservation-gated, autonomous** loop where every vertebra is scheduled, fails
loud, and carries provenance:

```
SENSE → NORMALISE/RESOLVE → DETECT → ASSESS → SYNTHESISE → SURFACE → LEARN → SCALE
```

- **SENSE** — connectors land provenanced rows (healthy); scaled by config-driven onboarding
  (declare a CSV/REST/RSS source → persist → instantiate via factory → scheduler dispatches,
  no engineering handoff).
- **RESOLVE/LINK** — FK-orphan ceilings GREEN and monotonically ratcheted; brand_name scoped
  to its true owner with alias coverage; consolidation runs on the partial cadence too.
- **DETECT** — every meaningful event (filtered *away* from recall-noise) promotes to a
  signal within one scheduler cycle; `ImpactRouter` runs on promoted signals so severity
  spans real critical/high; trust/tier actually differentiated.
- **SYNTHESISE** — strong CTX path made DEFENSIVE (pre-emptive low-confidence hedge) and
  HONEST (per-claim NAMED source-class attribution from `source_doc_id`→connector).
- **SURFACE** — a ranked, severity-differentiated feed + autonomously-framed briefs
  (FramingOrchestrator on a cron).
- **LEARN** — research agent fed real `entity_data` + a quality scorer + live-usage gap
  signal; DataSteward gated on a *proven* non-negative FAIR delta.
- **SCALE** — AI-assisted propose-review-promote onboarding, built on the persistence+factory
  foundation, never an auto-trust layer.

Each new vertebra adds its **own** Lane-2 conservation gate (promotion-lag SLA, impact-coverage
floor, feed-freshness) so a future stall reds the operational lane loudly.

---

## 5. Roadmap (leverage-sequenced, lane-annotated)

Lanes: **[D]** = Data (mine), **[P]** = Platform, **[F]** = Frontend. Shared-file loops must
claim the seam in `COORDINATION.md §6` before building (scheduler/runner.py and api/ are shared).

| # | Loop | Lane | What | Value | Depends on |
|---|---|---|---|---|---|
| 0 | pipeline NameError | **[D]** | Fix `pipeline.py:351` auto-create `NameError` | Removes a run-killing landmine gating auto-create | — **✅ DONE this session** |
| 0b | routing telemetry | **[P]** | Fix `chat.py` `log_ctx_event` kwarg-mismatch (handler A/B attribution silently dropped) | Stops vacuous-green observability | — |
| S1a | promote filter | **[P/D]** | Pass `event_types=[approval, trial_readout, ma_deal, safety_signal, …]` to `promote_events` at `runner.py:264` | De-noises the RECALL flood | — |
| S1b | promote cadence | **[P/D]** | Ensure promotion fires on the 6-hourly **partial** cycle, not only full `run_now()` | Signal freshness < 1 cycle (the *real* root cause) | S1a |
| S5 | trust/tier | **[D]** | Populate real `trust_score`/`source_tier` from source-class reliability | Prereq for severity range | — |
| C1 | orphan floor | **[D]** | Root-cause + fix `clinical_trials`/`pubmed` → drug resolution under the 10%/20% ceilings; re-prove Lane-2 GREEN | 1,590 records become sensable; clears a RED conservation gate | — |
| S2 | impact wiring | **[P/D]** | Wire `ImpactRouter` into scheduler post-tasks (bounded by `since_days`/`limit`) → populate `impact_assessments` | Un-pins severity; feed becomes a ranked detector | S1, S5 |
| C2 | durable de-smear | **[D]** | Root-cause the ETL **re-smear**, idempotent POST_RUN de-smear + alias backfill + Lane-2 re-smear invariant; re-prove GREEN after a full ETL cycle | Brand-keyed queries resolve | C1 |
| S3 | autonomous framing | **[P]** | Schedule `FramingOrchestrator.tick()` on cron + skip-all circuit-breaker | Closes SENSE→SYNTHESISE autonomously | S1, S2 |
| S4 | sensing gates | **[D/P]** | Lane-2: promotion-lag SLA + impact-coverage floor + feed-freshness; add to `protected-surface.txt` + regen CODEOWNERS same change | A future stall fails LOUD | S1–S3 |
| CSE | connector-status-emission | **[D]** | Emit `SUCCESS_LANDED`/`FAILURE_ZERO_ROWS`/`FAILURE_STALE` at the connector (not post-hoc) + per-fetch counters | Unblocks S4/S5 + generic-connector silent-zero | — |
| DLQ | DLQ/zombie remediation | **[D]** | Raise DLQ-insert failures above DEBUG; mark/rollback rows that fail POST_STORE quality | Closes two silent-loss holes | — |
| G1g | eval teeth | **[P]** | Deterministic provenance-correctness proxy as a **Lane-1 PR-hard** gate (no paid LLM); score smoke gate on REAL captures | Commit-time teeth so synthesis can't regress | — |
| R1 | per-claim attribution | **[P]** | Named source-class attribution in PROSE from `source_doc_id`→connector | Moves G1 `[prior-session: judge 2%, SME 2/10]` | C1, C2, G1g |
| R2 | defensive guard | **[P]** | Move guard PRE-synthesis; hedge/fallback on low confidence | Stops over-confident answers (G2 honesty) | R1, G1g |
| D1 | onboarding wiring (J2) | **[D/P]** | Config-persistence schema (secret-ref indirection) + `load_connector_from_source_id` factory + scheduler dispatch + **pre-prod reachability/contract gate** | Turns the 3 dead generic connectors into a real product | S1–S4, S5 |
| C3 | resolution durability | **[D]** | Decouple consolidation + promotion from full-cycle gating (run on partial cadence); drain `unresolved_entities`; add **git-history monotonicity** assertion on the orphan ratchet | Stops dup accumulation; closes ratchet gap | C1 |
| D2 | graph as signal | **[D]** | Company-company COMPETES_WITH inference + temporal cluster snapshots + inverse-edge inference + link-coverage gate | Share-shift/concentration signals become detectable | C1, C3 |
| A2/A3 | WebScrape / Warehouse | **[D]** | The remaining generic connectors | More coverage — **only after the detection spine + D1** | D1 |
| AUT | autonomy LEARN | **[D/P]** | FAIR-delta gate on DataSteward + wake research agent with real `entity_data` + live-usage gap signal | Closes the LEARN loop | R1, R2, C1–C3 |
| D3 | AI onboarding (moonshot) | **[D/P]** | Propose-review-promote: sample→LLM draft config→reviewable proposal, auto-approve only low-blast+high-conf | Paste-a-URL onboarding | D1, G1g |

---

## 6. Risks (the ones that bite)

1. **Sequencing trap** — shipping the visible "onboard any source" feature (D1/D3) or more
   connectors (A2/A3) before the detection spine scales blindness. Coverage comes AFTER detection.
2. **Conservation hard-stop** — two FK-orphan ceilings are RED on prod now. **Never loosen the
   ceiling to pass** (protected-surface; route through owner ONLY after a real linkage fix).
   A regression-share tripwire already exists (`REGRESSION_SHARES`); the gap is strict git-history
   monotonicity, not "no protection".
3. **#242 durability trap** — the held de-smear is a one-shot field-clear the ETL re-smears
   `[prior-session: 277 missing / 275 re-smeared after a cycle]`. C2 is DONE only when a Lane-2
   re-smear invariant proves no re-smear AFTER a full ETL cycle, pasted.
4. **Attribution measures the wrong number** — R1 can move *mechanical* citation while SME-judged
   G1 barely moves. Measure on the SME v2 pack, not the mechanical scorer.
5. **Detection wiring side-effects** — turning `ImpactRouter` on against ~40k events with no cap
   could fire a large batch of traversals + LLM calls. Bound it + prod-probe cost before enabling.
6. **Secret leak on onboarding persistence** — D1 will serialize auth tokens; plaintext in
   `usage_profile` JSON is a real leak. Secret-ref indirection + redaction guard mandatory.
7. **Autonomy amplifies degradation** — close the LEARN loop LAST; gate on a proven FAIR delta.
8. **Doc/migration drift as standing audit items** — `CLAUDE.md` still calls CTX "OPT-IN" when
   it is default-on at rollout 1.0; migrations 089–090 are absent from the worktree (probe prod
   migration-version before any fact-governance work).

---

## 7. Shipped this session

- **A1 — generic `RestConnector`** (L4b): auth (none/bearer/basic/api-key), pagination
  (page/offset/cursor + max_pages cap + stuck-cursor guard), dotted `records_path`/field
  extraction, incremental `since`. 29 DB-free tests; prod-probed live (openFDA + ClinicalTrials.gov
  v2 cursor pagination). Independent review **APPROVE-WITH-NITS** → nits applied. Conservation: all
  degradation paths fail loud. Reuses `_fetch_with_retry` (no anti-slop dup).
- **Loop 0 — `pipeline.py:351` NameError fix** on the auto-create path. RED→GREEN regression.
