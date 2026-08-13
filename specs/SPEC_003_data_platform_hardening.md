# SPEC 003 — Data-Platform Hardening Program

**Status:** Draft for owner approval (P0 floor specced; program sequenced)
**Owner ruling (2026-08-07):** run this as one program end-to-end (lanes merged for this work); **P0 design specs first, no implementation until the owner picks what to build.**
**Supersedes/extends:** the diagnosis in `docs/data-pipeline-groundup-analysis-20260805.html` and the red-team review `design-review-output/data_pipeline_deep_design_review_2026_08_07.md`.

---

## 1. Why this program exists

Two independent analyses converged on the same conclusion: Market Zero has a **credible, well-tested pharmaceutical ingestion application** with strong seams (connector boundary, resolution audit, facts/evidence ledgers, DLQ, conservation culture) — but it is **not yet a lossless, replayable, source-configured, domain-pluggable transformation platform.** Calling it a "gold-standard" data platform today would be an over-claim.

The first report's one-line diagnosis (build a deterministic identity spine, not another connector) was directionally right but incomplete. The complete picture has **four prerequisites**, and identity is only one of them:

| Constraint | Class | The gap |
|---|---|---|
| **Deterministic identity** | data-quality | Authoritative molecule IDs exist as columns but are stranded from the resolver; cross-source joins ride on names. |
| **Immutable raw capture** | platform-integrity | We hash payloads but discard the source bytes — provenance is a *label*, not *replay*. |
| **Truthful run semantics** | platform-integrity | Fail-open hooks + ignored quality blocks let a partially-failed run finalize as SUCCESS — a vacuous green inside our own runtime. |
| **Versioned source-instance config** | platform-integrity | Generic REST/RSS/CSV adapters exist but are unwired; `SourceType` (a closed enum) is doubling as source-*instance* identity. |

**Honest grades (accepted from the review, and I withdraw my earlier "A-grade provenance substrate"):**
bounded-pharma ingestion **B/B+** · deterministic identity **C-** · provenance-as-label **B-** · reproducible-lineage/replay **D+/C-** · config-driven new source **C code / D operational** · unstructured transformation **early C-**.

## 2. What was verified before writing specs (DoD: no say-so)

I re-read current code and confirmed the load-bearing P0 findings myself — these are not taken on the review's citations:

- **Fail-open control → false green (G-02) — CONFIRMED.** `pipeline_hooks.py:116-118` swallows any hook exception into `action="continue"`; `pipeline.py:422-429` never checks `has_block()` on the POST_STORE quality gate (and it runs after the write); `pipeline.py:345-361` discards the `ON_NEW_ENTITY` result *and* its `link_info.method=='auto_create'` guard is dead (`ResolvedLink` has no `.method` — it's `matched_via`), so it never fires; `pipeline.py:454-455` is a literal `except Exception: pass`.
- **Non-atomic record (G-04) — CONFIRMED.** `db.py` connections default `autocommit=True`; a `transaction()` primitive exists (`db.py:159-207`) but `_process_record` never uses it — store/link/quality/HITL are separate commits.
- **Identity spine stranded (G-05) — CONFIRMED.** `entity_resolver.py:115-125` `EXACT_LOOKUP_MAP` = `{nct_id, pmid, nda_number, mesh_id, cik, ticker, orcid, patent_number}` only; drug identity falls to name-based `FUZZY_MATCH_FIELDS`; `_store_drug` (`knowledge_store.py:285-293`) falls back to `LOWER(generic_name)`. Live prod fill (2026-08-05, 2,102 drugs): `chembl_id/unii/inchi_key/drugbank_id/ndc/canonical_molecule_id = 0`; `pubchem_cid 27, rxcui 123, atc 104, nda 92`. `crosswalk_records` (217 rows) is loaded offline and never queried by the resolver.
- **Nuance the review undersells:** `classify_run_outcome` (`pipeline.py:125-168`) is already a *good* pure Lane-1 outcome gate (LANDED / NO_CHANGE / ZERO_ROWS / PARTIAL). WP-0 should **extend** it (feed it skipped/quarantined/failed, enforce a conservation equation), not replace it.

## 3. Strategic decisions (ratified for this program)

- **Decision: Evolve, do not rewrite.** The connector boundary, resolution audit, facts/evidence ledgers, DLQ, and conservation gates are the right foundations. Every WP lands **additively** with shadow reads and compatibility adapters.
- **Decision: No Kafka / Spark / lakehouse.** A bounded iterator, a durable source cursor, object storage for raw bytes, Postgres for metadata, and distributed leases are sufficient for the next stage. Introduce heavy infra only when measured volume/latency/recovery demands it.
- **Decision: Pause net-new connector breadth** except connectors that directly improve raw capture or deterministic identifiers, until the P0 floor lands. More sources into a name-resolved graph add ambiguity faster than value.
- **Decision: Fold into the canonical board.** This SPEC + per-WP design specs under `specs/data_platform/`, backlog entries in `PRODUCT_BACKLOG.md`, cross-refs in `COORDINATION.md`. No third backlog (anti-sprawl).
- **Decision: Verify each finding against current code before speccing it** (done for the P0 floor above; repeat for P1 WPs when they're picked up).

## 4. The honest modularity boundary

Split today's over-broad `DomainPack` idea into two responsibilities:

- **`SourceContract`** — declarative, versioned, validated, deployable config for a *source instance*: transport, mapping, schema, quality rules, SLA, license, ownership, secret *references*. A new REST feed into an existing record kind (`drug_label`, `event`) is **config-only** once WP-2 lands.
- **`DomainPlugin`** — reviewed *code* that owns record/entity schemas, typed identifier namespaces, projection/store strategy, link rules, and migrations. A genuinely new concept (payer formulary, genomic sample, package-level product) requires a plugin + migration.

Extensibility contract we will actually honor: **new source instance = config; new protocol = one reviewed adapter; new entity type/domain = plugin + migration.** We will not pretend arbitrary relational semantics are config-only.

## 5. Identity model (WP-4 ADR, summarized)

Do not treat every drug-like row as one grain. Typed grains + typed identifiers:

- substance/ingredient → **UNII**, correctly-scoped **RxNorm IN/PIN**
- clinical/branded product + strength/form → **RxNorm SCD/SBD** (never molecule identity)
- regulatory application → **NDA/BLA/ANDA** as *relations*, not universal identity
- package/presentation → **NDC**
- external molecular records → **ChEMBL id / PubChem CID** (governed by relation/scope)
- **InChIKey**: full match = same compound; connectivity-only (first block) = explicit caveat
- **ATC** = classification, **never** exact identity
- trial intervention/arm = its own grain (see WP-11)

Rule: **prefer unresolved/quarantined to a false merge.** Name/fuzzy/embedding/LLM are candidate generation and fallback linkage — never identity proof.

## 6. The work-package program

All WPs run under one team for this program. Priority and sequence below; findings map to the review's register (G-01…G-16). **WP-12 (assurance harness + safe rollout) applies throughout.**

| # | Work package | Priority | Covers | Verified | Seq |
|---|---|---|---|---|---|
| **WP-0** | Truthful run outcomes & controls | **P0** | G-02, G-04(part), G-16 | ✅ confirmed | 1 |
| **WP-1** | Immutable raw artifacts + replay + per-record atomicity | **P0** | G-03, G-04, G-12(part) | ✅ confirmed | 2 |
| **WP-2** | Versioned source-contract control plane (+ source_id, SSRF/secret boundary) | P0/P1 | G-01, G-07, G-10, G-12, G-14 | pending re-verify | 3 |
| **WP-4** | Deterministic identity spine | **P0/P1** (highest semantic leverage) | G-05, G-09, G-13, G-15(part) | ✅ confirmed | 4 |
| **WP-3** | Explicit, testable domain plugin (activate `DomainPack`, handler registry) | P1 | G-07, G-12 | pending | 5 |
| **WP-5** | Versioned Document IR (spans/locators/OCR, NER-offset fix, untrusted-content) | P0/P1 (unstructured goal) | G-06, G-14, G-15, G-16 | pending | 6 |
| **WP-6** | Derived graph/fact transforms as first-class jobs | P1 | G-08, G-12, G-15 | pending | 7 |
| **WP-7** | Source-observation layer + field-level survivorship | P1 | G-09, G-11, G-12 | pending | 8 |
| **WP-8** | Quality as contract + promotion gate (kill vacuous-pass rules) | P1 | G-02, G-11, G-16 | pending | 9 |
| **WP-9** | Durable cursors, streaming batches, leases, cost controls | P1 | G-01, G-10, G-04(part) | pending | 10 |
| **WP-10** | End-to-end lineage (OpenLineage/PROV) + validated catalog (Croissant 1.1) | P1/P2 | G-03, G-12, G-16 | pending | 11 |
| **WP-11** | Normalize multi-valued relationships (trial interventions/arms) | P1 | G-05, G-13 | pending | 12 |
| **WP-12** | Assurance harness + safe rollout protocol | continuous | all, esp. G-16 | — | ∞ |

**P0 floor (this SPEC's detailed deliverables):** `specs/data_platform/WP-0_truthful_run_outcomes.md`, `WP-1_raw_capture_and_replay.md`, `WP-4_deterministic_identity_spine.md`.

## 7. Definition of "gold standard" (the finish line)

Claimable only when demonstrable, not merely documented: (1) every prod source runs from a versioned approved contract with an independent `source_id`; (2) exact input bytes + sanitized metadata retained per policy; (3) artifact + pinned versions deterministically replay to identical outputs; (4) every stage has reconciling counters + explicit terminal reasons; (5) required controls fail **closed**; (6) deterministic IDs + governed crosswalks precede names/embeddings/LLMs; (7) exact-identity conflicts **quarantine, not merge**; (8) unstructured outputs keep exact artifact/page/block/span locators + parser/model versions; (9) canonical fields preserve source observations + survivorship rationale; (10) derived edges/facts are versioned jobs with manifests + supersession; (11) source/event/valid/asserted times distinct where semantics require; (12) quality is versioned, non-vacuous, historical, promotion-blocking; (13) any fact/edge/field traces to artifact + contract + run + code/config version; (14) catalog validates against Croissant 1.1 and reflects deployed reality; (15) kill/restart, truncation, late-arrival, multi-instance tests prove no loss/dup; (16) security/license/retention/PII/untrusted-content policies enforced in the runtime path.

## 8. What NOT to do (guardrails)

- Do not register the generic connectors under one shared enum and call onboarding done.
- Do not populate `canonical_molecule_id` by fuzzy name alone. Do not equate ATC membership with molecule identity. Do not make LLM confidence an identity proof.
- Do not treat a payload hash as replayable provenance once the bytes are gone.
- Do not add another best-effort post-task without a run record, dependency, lease, and output manifest.
- Do not put arbitrary SQL/Python callables into user-editable runtime contracts.
- Do not delete legacy data or derivations during migration — supersede and reconcile.

## 9. Governance

Every WP: RED→GREEN with pasted output; additive + reversible migration (reserve the number at implementation time); shadow → dual-read → reversible flag → cutover → separate cleanup PR; an independent reviewer pass; no protected-surface edit-to-pass; a real read-only prod probe where a data claim is made. New hard gates couple protection with hardening in the same change (`protected-surface.txt` + regen CODEOWNERS).
