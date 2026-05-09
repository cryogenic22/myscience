✓ Signed off by Claude
Pending sign-off by Antigravity (powers the frontend Evidence Affordance + Evidence Panel)

# SPEC_024: Evidence Ledger — content-addressed claim provenance

## Goal
Make every claim in Market Zero linkable to one or more append-only evidence
records with content-addressed source provenance. Implements the spec §8.2
"Evidence Ledger" + §11.1 hallucination control invariant ("every claim that
appears in any user-facing artifact must be linkable to one or more evidence
ledger records") + §11.2 reproducibility guarantee ("given a decision_id,
recreate the exact evidence available at decision time").

## Why now
Today, claim provenance is a single `provenance_source` text field stuffed on
each row — not reproducible (the source content can change), not content-
addressed (no integrity check), and not auditable (no record of who extracted
the claim, with which prompt version). For SPEC-026 (LLM Gateway) and the
decision-signing follow-up to mean anything, every claim must be traceable
to an immutable evidence record. SPEC-023 Decision Briefs reference evidence;
this spec defines what "evidence" actually is.

## Non-goals
- Replacing all existing `provenance_source` fields in one PR. The ledger
  starts as additive; existing fields stay until SPEC_028 Learning Service
  (which depends on the ledger) lands.
- Storing the actual source PDFs/HTML. We store a hash + an `archived_snapshot_ref`
  (S3 key or URL) — actual storage is handled by the Ingestion Service.
- Cryptographic signing of evidence records. That's deferred to the
  decision-signing follow-up; the ledger gives signing the immutable
  substrate it needs.

## Data contract

### Table: `claims`
A claim is a structured assertion about an entity. Identified by content
+ entity, deduplicated by `(claim_text_hash, entity_ref)`.

| Column | Type | Notes |
|---|---|---|
| `claim_id` | UUID PK | gen_random_uuid() |
| `claim_text` | TEXT NOT NULL | The assertion in plain language ("Tirzepatide approved for chronic weight management 2023-11-08") |
| `claim_text_hash` | BYTEA NOT NULL | SHA-256 of `claim_text` for fast dedup lookup |
| `claim_type` | TEXT NOT NULL | `regulatory` \| `clinical` \| `commercial` \| `pricing` \| `safety` \| `pipeline` \| `other` |
| `entity_type` | TEXT | `drug` \| `company` \| `trial` \| `indication` \| `mechanism` \| null for general |
| `entity_id` | UUID | FK-style reference (no DB-level FK — entity tables vary) |
| `confidence` | REAL CHECK (0 ≤ x ≤ 1) | Aggregate confidence across all backing evidence |
| `created_at` | TIMESTAMPTZ NOT NULL | DEFAULT NOW() |
| `updated_at` | TIMESTAMPTZ NOT NULL | DEFAULT NOW(); bumped on confidence recalc |

UNIQUE constraint on `(claim_text_hash, entity_type, entity_id)` (with NULLs
treated as equal via partial unique index).

### Table: `evidence_records`
The append-only ledger. Each record backs one or more claims (via
`claim_evidence_links`).

| Column | Type | Notes |
|---|---|---|
| `evidence_id` | UUID PK | gen_random_uuid() |
| `source_id` | TEXT NOT NULL | Source identifier (canonical name, e.g. `clinical_trials_gov`, `fda_orange_book`) |
| `source_url` | TEXT | Original URL (may break over time — that's why we hash) |
| `source_content_hash` | BYTEA NOT NULL | SHA-256 of `extracted_text`; primary integrity check |
| `archived_snapshot_ref` | TEXT | Pointer to immutable archive (S3 key, IPFS CID, etc.). Null until archive job runs. |
| `retrieved_at` | TIMESTAMPTZ NOT NULL | When the source was fetched |
| `extraction_method` | JSONB NOT NULL | `{agent, model_version, prompt_version, prompt_id, retrieval_strategy}` |
| `extracted_text` | TEXT NOT NULL | Exact passage backing the claim (subject to size cap — see red-team) |
| `confidence` | REAL CHECK (0 ≤ x ≤ 1) | Per-evidence confidence (calibrated 0-1) |
| `retrieved_by_user_id` | UUID | Who/what triggered the fetch (may be system user for autonomous agents) |
| `created_at` | TIMESTAMPTZ NOT NULL | DEFAULT NOW(); evidence is immutable post-create |

Append-only enforcement: a TRIGGER rejects UPDATE/DELETE on `evidence_records`
except for `archived_snapshot_ref` (which can be filled in once after
archival).

### Table: `claim_evidence_links`
Many-to-many between claims and evidence. A single evidence record can
back multiple claims; a single claim can be backed by multiple evidences.

| Column | Type | Notes |
|---|---|---|
| `link_id` | UUID PK | gen_random_uuid() |
| `claim_id` | UUID NOT NULL | FK claims ON DELETE CASCADE |
| `evidence_id` | UUID NOT NULL | FK evidence_records ON DELETE RESTRICT (immutable history) |
| `relation` | TEXT NOT NULL | `supports` \| `contradicts` \| `qualifies` |
| `created_at` | TIMESTAMPTZ NOT NULL | DEFAULT NOW() |

UNIQUE on `(claim_id, evidence_id, relation)`.

### Table: `evidence_snapshots`
A frozen list of `(claim_id, evidence_id)` pairs at a point in time, used
to make decisions reproducible. The `snapshot_hash` is content-addressed:
SHA-256 of the canonical-JSON serialization of the snapshot body.

| Column | Type | Notes |
|---|---|---|
| `snapshot_hash` | BYTEA PK | SHA-256 of canonical JSON body |
| `body` | JSONB NOT NULL | `{snapshot_at, brief_id?, decision_id?, claims: [{claim_id, evidence_ids: [...]}]}` |
| `brief_id` | UUID | Optional FK decision_briefs (set when frozen for a brief) |
| `decision_id` | UUID | Optional FK decisions (set when frozen for a decision commit) |
| `created_at` | TIMESTAMPTZ NOT NULL | DEFAULT NOW() |

Snapshots are themselves immutable. Re-snapshotting the same set of
(claim, evidence) pairs returns the same hash (idempotent).

## API surface

| Method | Path | Purpose |
|---|---|---|
| POST | `/claims` | Create or upsert a claim (uploader+) |
| GET | `/claims/{claim_id}` | Get claim with all backing evidence (viewer+) |
| GET | `/claims` | Search claims by entity_type/entity_id, claim_type, text-search (viewer+) |
| POST | `/claims/{claim_id}/evidence` | Append evidence to a claim (uploader+) |
| GET | `/evidence/{evidence_id}` | Get one evidence record (viewer+) |
| POST | `/briefs/{brief_id}/evidence-snapshot` | Freeze the brief's evidence into a snapshot (uploader+, idempotent) |
| GET | `/evidence-snapshots/{snapshot_hash}` | Reconstruct a snapshot (viewer+) |

Standard error envelope. Auth via JWT.

## Hash specification (deterministic)

**Claim text hash**: `sha256(claim_text.strip().encode("utf-8"))`. Whitespace
matters but leading/trailing trim is applied to handle copy-paste noise.

**Evidence content hash**: `sha256(extracted_text.encode("utf-8"))`. NO
trim — the exact bytes the extractor saw is what we attest to.

**Snapshot hash**: `sha256(canonical_json(body).encode("utf-8"))` where
`canonical_json` is JSON with `sort_keys=True, separators=(",", ":"),
ensure_ascii=False`. The `body` includes `claims` sorted by `claim_id` and
`evidence_ids` sorted lexically within each claim, plus optional
`brief_id` / `decision_id` context. **`snapshot_at` is intentionally
NOT part of the hashed body** — two snapshots of identical claim/evidence
content taken at different times produce the same hash, which is the
intended idempotency behavior. The actual snapshot time lives on
`evidence_snapshots.created_at` as DB metadata, not part of identity.

## Integration with existing systems

**Decision Briefs (SPEC-023)**: `decision_briefs.evidence_refs[]` already
accepts `{type: 'signal'|'kbq_view'|...}`. Add a new `type: 'claim'` so
briefs can reference structured claims. Backwards-compatible.

**Decision signing (follow-up)**: When a Decision is committed, snapshot
all `claim_id`s referenced by the brief's `evidence_refs`, store the
snapshot_hash on the decision, return 200 with `{decision_id, snapshot_hash}`.

**LLM Gateway (SPEC-026)**: Every LLM call's response that asserts a fact
will create-or-link a `claim` + `evidence_record` automatically. The
`extraction_method.prompt_id` lets Learning Service (SPEC-028) attribute
prediction accuracy to specific prompt versions.

**Frontend Evidence Affordance**: `<EvidenceAffordance claimId={...} />`
calls `GET /claims/{claim_id}`, which returns the claim plus all backing
evidence ordered by confidence DESC.

## Red-team — attack vectors and mitigations

| # | Vector | Mitigation |
|---|---|---|
| R1 | SQL injection via claim_text | Parameterized everywhere; bytea hash params use psycopg2.Binary |
| R2 | DoS via massive `extracted_text` | Cap at 64 KB at API layer (rejected with 400); bytea hash never exceeds 32 bytes |
| R3 | Hash collision (theoretical) | SHA-256; collision-resistant for our use case |
| R4 | Append-only bypass via UPDATE | DB trigger rejects UPDATE on all columns except `archived_snapshot_ref` |
| R5 | Snapshot tampering | snapshot_hash IS the primary key; modifying `body` after insert means a different hash, breaking the existing reference |
| R6 | Evidence injection (false provenance) | `retrieved_by_user_id` is set from auth context, not request body |
| R7 | Cross-tenant claim leak | viewer-level access for now; SPEC-030 multi-tenant work tightens |
| R8 | Race on dedup (two concurrent identical claim creates) | UNIQUE constraint on `(claim_text_hash, entity_type, entity_id)` + ON CONFLICT DO NOTHING in INSERT |
| R9 | Replay (re-POSTing identical evidence) | Dedup on `(source_content_hash, source_id, retrieved_at::date)` — same content from same source on same day = same evidence |
| R10 | Snapshot enumeration (privacy) | snapshot_hash is 32 bytes random-looking; no enumeration risk if we don't list them |

## Success criteria
- [ ] Migration 053 applies clean
- [ ] Append-only trigger rejects forbidden UPDATEs
- [ ] Snapshot hash is deterministic across two independent runs
- [ ] Re-snapshotting the same claim+evidence set returns the same hash
- [ ] Modifying a claim's confidence after snapshot does NOT change the
      snapshot's hash (snapshot stores frozen evidence_ids, not confidence)
- [ ] Dedup on identical claims (text + entity) returns the existing claim_id
- [ ] Full test suite green; no regressions
- [ ] OpenAPI snapshot regenerated; API_CHANGELOG appended

## Out of scope (deferred)
- Cryptographic signing of evidence records (decision-signing follow-up)
- Backfilling existing entities' provenance_source into the ledger
  (separate batch job)
- Source quality scoring on evidence (rolled into SPEC-027)
- Multi-tenant compartmentalization of claims (SPEC-030)
