# WP-4 — Deterministic Identity Spine

**Status:** P0 design spec — DRAFT for owner approval (ADR-first). No implementation authorized until the owner selects the WP (SPEC_003 owner ruling 2026-08-07; SPEC_HANDOFF §H0.3.5). Sequenced behind the handoff floor (H0–H1).

## Summary

Market Zero has no authoritative-identifier path for molecules. `EXACT_LOOKUP_MAP` (`integration/entity_resolver.py:115-125`) carries only regulatory/bibliographic keys (`nct_id`, `pmid`, `nda_number`, `mesh_id`, `cik`, `ticker`, `orcid`, `patent_number`) — no `unii`, `rxcui`, `chembl_id`, `pubchem_cid`, `inchi_key`, `ndc`, or `drugbank_id`. Drug identity therefore collapses to name-based fuzzy matching plus a `LOWER(generic_name)` fallback in `_store_drug` (`integration/knowledge_store.py:285-293`), which silently conflates salts, formulations, combinations, brands, and substances. The governed `crosswalk_records` table (migration `091`) exists but is never queried by the resolver. This WP installs a grain-typed identity spine so exact identifiers resolve deterministically *before* any name matching runs. It is P0 because identity is the highest-leverage substrate defect: every downstream fact, edge, and synthesis inherits a wrong merge.

## Current state (verified)

- **No molecule IDs are exact-resolver keys.** `EXACT_LOOKUP_MAP` (`entity_resolver.py:115-125`) has 8 keys, none molecular. `_resolve_single` (`entity_resolver.py:260-312`) runs Strategy 1 (exact) only for keys in that map; for drugs the only registered exact key is `nda_number` (`domain/pharma/pack.py:47-49`).
- **Drug identity falls to name matching.** `FUZZY_MATCH_FIELDS` (`entity_resolver.py:128-135`) maps `generic_name`/`brand_name` → `drugs` by name; the cascade then runs alias → fuzzy trigram → embedding → LLM → combo-component → auto-create (`entity_resolver.py:271-311`).
- **Store-side collapse.** `_store_drug` does NDA-first, then `WHERE LOWER(generic_name)=LOWER(%s) ... ORDER BY quality_score DESC LIMIT 1` (`knowledge_store.py:285-293`) — one name can absorb distinct substances/formulations.
- **Crosswalk is orphaned from resolution.** `crosswalk_records` is governed (relation/scope/confidence, enrich-never-overwrite, `UNIQUE(internal_entity_id, external_system, external_id)` — `091_crosswalk_records.sql:14-40`) and loaded by `services/crosswalk_loader.py`, but `entity_resolver.py` contains zero references to `crosswalk` or `entity_identifiers` (grep: none).
- **Identifier ownership is split.** `chembl_id` is a drug column (`038_drugs_modality_external_ids.sql:87-91`) but its exact-lookup ownership sits on `molecular_target` (`pack.py:203-204`), not `drug`. Migration `035` added `canonical_molecule_id` as a self-link but its backfill is explicitly deferred (`035_canonical_molecule_id.sql:11`). Migration `038` already created `UNIQUE` partial indexes on `drugs(unii|chembl_id|drugbank_id) WHERE NOT NULL` (`038:114-124`) — DB-level uniqueness exists but is unused because fill is ~0.
- **Live fill (read-only prod probe 2026-08-05, re-verified 2026-08-07 unchanged; 2,102 drugs):** `chembl_id`/`unii`/`inchi_key`/`drugbank_id`/`ndc`/`canonical_molecule_id` = 0; `pubchem_cid` 27, `rxcui` 123, `atc` 104, `nda` 92. `crosswalk_records` = 217 rows (rxnorm 108 approved, atc 109 machine_only). Name resolution dominates because the authoritative columns are empty.

## Target behavior

1. **A grain-typed identity ADR** defines identity grains: *substance/ingredient*, *salt/precise-ingredient*, *clinical/branded product+strength+form*, *regulatory application*, *package*, *trial-intervention/arm*. Every identifier is TYPED by `(grain, vocabulary, scope)`: UNII / RxNorm-IN = substance; RxNorm SCD/SBD = product; NDA/BLA = application-relation; NDC = package; **ATC = classification, NEVER identity**; InChIKey carries a full-vs-connectivity-only (`first-block`) caveat flag.
2. **A resolver exact-ID stage runs first.** Before alias/fuzzy/embedding/LLM, the resolver queries approved exact identifiers + governed crosswalk. A name only generates candidates *after* exact fails. Fuzzy/LLM may never override an exact result.
3. **Relation-aware uniqueness.** An active exact-identity identifier cannot map to two canonical entities; class/related identifiers may be many-to-many. A conflicting exact identifier is **quarantined to a review queue** (terminal-to-automatic), never silently reassigned.
4. **Connectors emit typed identifiers**, promoting `inchi_key`/`chembl_id`/`rxcui`/`pubchem_cid` out of `data{}` into typed identifier records with grain+scope.

## Design & approach

- **Normalized `entity_identifiers` table** as the single identity store; `crosswalk_records` is retained and exposed to the resolver behind a read-only compatibility view that maps its `(internal_entity_id, external_system, external_id, mapping_relation, mapping_scope, review_status)` into identifier rows. No data is copied out of `crosswalk_records` during migration — it is *read through*.
- **`IdentityResolver.resolve_by_identifier(grain, vocab, value)`** — new Strategy 0 invoked from `_resolve_single` before `_exact_lookup`. It selects only `status='approved'` exact-identity rows; on exactly one match → deterministic link (`matched_via="exact_identity"`); on zero → return None (fall through to names); on >1 canonical target → emit a quarantine row via the existing `_log_unresolved` seam (`entity_resolver.py:1110`) tagged `reason="exact_identity_collision"` and return None (no auto-merge).
- **Grain/vocab registry** in the domain pack: extend `EntitySchema` with `identity_keys: dict[str, IdentifierSpec]` where `IdentifierSpec = (grain, vocabulary, scope, is_identity: bool)`. ATC entries carry `is_identity=False` and are rejected from the exact stage by construction.
- **Store-side guard.** `_store_drug` gains an identity-key lookup ahead of the `LOWER(generic_name)` fallback; the name fallback is retained but only fires when no identity key is present, preserving the current auto-created-from-CT.gov path.

## Schema / migrations

**Migration NNN (reserve number at impl time)** — additive + reversible (`DROP TABLE` / `DROP VIEW`):

```
CREATE TABLE IF NOT EXISTS entity_identifiers (
  identifier_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  canonical_entity_id   TEXT NOT NULL,
  entity_type     TEXT NOT NULL,
  grain           TEXT NOT NULL,      -- substance|salt|product|application|package|intervention
  vocabulary      TEXT NOT NULL,      -- unii|rxnorm_in|rxnorm_scd|nda|bla|ndc|chembl|pubchem_cid|inchikey|drugbank
  identifier_value TEXT NOT NULL,
  scope           TEXT NOT NULL,      -- exact_identity|classification|related
  is_identity     BOOLEAN NOT NULL DEFAULT TRUE,
  connectivity_only BOOLEAN DEFAULT FALSE,  -- InChIKey first-block caveat
  status          TEXT NOT NULL DEFAULT 'candidate', -- candidate|approved|quarantined|superseded
  provenance      JSONB, source_version TEXT,
  valid_from TIMESTAMPTZ DEFAULT NOW(), valid_to TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW()
);
-- one canonical target per active exact identifier (relation-aware uniqueness):
CREATE UNIQUE INDEX IF NOT EXISTS uq_entity_identifiers_exact
  ON entity_identifiers (vocabulary, identifier_value)
  WHERE is_identity AND status='approved';
CREATE INDEX IF NOT EXISTS idx_entity_identifiers_canon
  ON entity_identifiers (canonical_entity_id);
-- read-through compat: crosswalk_records surfaced as identifier rows
CREATE OR REPLACE VIEW v_identity_all AS
  SELECT ... FROM entity_identifiers
  UNION ALL SELECT ... FROM crosswalk_records WHERE record_status='active';
```

The partial unique index is the structural collision floor — an INSERT that violates it forces the quarantine path instead of a silent overwrite. No legacy columns (`drugs.unii`, `.chembl_id`, migration `038`) are dropped; they are the shadow-backfill source.

## Tests (RED→GREEN)

Lane-1 (deterministic, DB-free / seeded), all fail today:

- `test_exact_identifier_stage_runs_before_fuzzy` — a UNII match wins over a colliding `generic_name` fuzzy candidate.
- `test_atc_code_never_used_as_identity` — an ATC value passed as an identifier is rejected from the exact stage (`is_identity=False`), routes to classification only.
- `test_exact_identity_collision_quarantines` — one identifier value pointing at two canonical entities produces a quarantine row and returns None; no merge.
- `test_fuzzy_cannot_override_exact` — LLM/fuzzy candidate is discarded when an exact identity link already resolved.
- `test_crosswalk_records_visible_to_resolver` — an `approved` rxnorm crosswalk row resolves via the compat view (regression: today the resolver never reads it).
- `test_store_drug_prefers_identity_over_name` — `_store_drug` with a UNII does not collapse into a different `LOWER(generic_name)` row.
- `test_inchikey_connectivity_only_flag` — a first-block-only InChIKey is stored with `connectivity_only=True` and excluded from exact identity uniqueness.
- `test_identifier_grain_typed_in_pack` — every `identity_key` in the pharma pack carries a valid `(grain, vocabulary, scope)`.

## Exit gate / conservation equation

- **Gold set:** 100% of a reviewed top-500-asset gold set (`tests/fixtures/identity_gold.yaml`) resolves via the exact/crosswalk path, not by name. `python -m pytest tests/test_identity_spine.py -q` pasted green.
- **Zero collisions:** `SELECT vocabulary, identifier_value, count(DISTINCT canonical_entity_id) FROM entity_identifiers WHERE is_identity AND status='approved' GROUP BY 1,2 HAVING count(DISTINCT canonical_entity_id) > 1` returns **0 rows** (pasted prod probe).
- **Precision floor:** ≥99.5% precision on auto-approved identity links (prefer unresolved to false merge), measured against the gold set.
- **Coverage:** every top-500 asset has a reviewed identity `status` (approved/quarantined), pasted count.
- **Conservation equation:** `identifiers_in = identifiers_approved + identifiers_quarantined + identifiers_superseded` — no identifier is dropped; collisions are recorded, never silently reassigned. No protected-surface file edited to pass. Lane-2 adds a scheduled collision-count + orphan-identifier probe to `operational-health.yml`.

## Rollout

1. **Shadow:** land migration NNN + `IdentityResolver`; backfill `entity_identifiers` from existing `drugs.unii/chembl_id/rxcui/pubchem_cid/inchi_key/nda_number` columns and `crosswalk_records` as `status='candidate'`. Resolver still returns the legacy link; the exact stage runs in shadow and logs a match/mismatch delta.
2. **Dual-read:** compare exact-stage result vs legacy name result for every drug resolution; emit a collision/divergence report. Promote clean, single-target substance-grain candidates to `approved`.
3. **Flag:** gate the exact stage behind `MZ_IDENTITY_SPINE=false` (reversible); flip to `true` only after the shadow delta shows zero regressions on the gold set.
4. **Cutover:** exact stage authoritative for top-500 assets + substance grain first (right-sized); `_store_drug` identity guard active.
5. **Cleanup:** once fill and precision floors hold across two Lane-2 cycles, tighten the `drugs.unii/chembl_id` legacy columns to read-through-only (kept, not dropped — supersede + reconcile). Expand grains beyond substance/product in a follow-up WP.

## Risks & out-of-scope

- **Risk: sparse fill (0 UNII/ChEMBL live).** The spine is inert until connectors emit typed IDs; backfill precedes cutover, and the flag prevents an empty spine from breaking name resolution.
- **Risk: crosswalk double-source.** Read-through view avoids copying; a later WP may consolidate `crosswalk_records` fully into `entity_identifiers`.
- **Risk: InChIKey false merges** from connectivity-only keys — mitigated by `connectivity_only` exclusion from exact uniqueness.
- **Out of scope:** bulk WHO ATC / RxNorm release load (Loop L1b-ii); `canonical_molecule_id` formulation-cluster backfill (migration `035` follow-up); company/investigator identity (this WP is molecule-grain); LLM-based identifier extraction. ATC classification enrichment stays on the existing `crosswalk_loader` path.
