✓ Signed off by Claude
Pending sign-off by Frontend Claude (Decision Workspace + Insights surfaces consume signed bundles)

# SPEC_034: Decision Signing — immutable evidence_snapshot + replay

## Goal
Implement spec §6.4.2 + §11.2: every Decision is reproducible. On commit,
freeze the evidence the decision was based on into an immutable snapshot,
HMAC-sign the canonical decision fields plus the snapshot hash, and
expose a replay endpoint that reconstructs the exact view a decision
was made on.

## Why now
SPEC-024 Evidence Ledger gave us content-addressed claim provenance.
SPEC-026 LLM Gateway gave us prompt versioning. Today, decisions can be
captured but the audit chain isn't sealed: nothing prevents post-commit
mutation of supporting evidence. Decision signing closes the audit
invariant.

## Non-goals (deferred)
- **Asymmetric (RSA/Ed25519) signing**. HMAC-SHA256 with server secret
  is sufficient for "the server attests to this state." Full PKI signing
  (per-user keypair) is a follow-up if/when external auditors require it.
- **Multi-party signing** (decision committee, M-of-N approvals).
- **Hardware key storage / KMS integration**. Server secret lives in
  env var for now.
- **Signing of in-progress war-game runs**. Only Decisions sign.

## Data contract

### Augmentation to existing `decisions` table (additive, back-compat)
Adds nullable columns:

| Column | Type | Notes |
|---|---|---|
| `evidence_snapshot_hash` | BYTEA | SHA-256 of the canonical snapshot body (32 bytes) |
| `signature` | BYTEA | HMAC-SHA256 of canonical(decision_immutable_fields + snapshot_hash) using server secret (32 bytes) |
| `signing_algo` | TEXT | `hmac-sha256-v1` for now; future-proofed for upgrade |
| `signed_at` | TIMESTAMPTZ | When signed |
| `signing_user_id` | UUID | Who signed |
| `signing_metadata_jsonb` | JSONB | `{claim_ids[], brief_id?, server_id, secret_version}` |

NULL means "unsigned" — back-compat with all existing decision rows.

### No new table
Single-signature-per-decision is sufficient; an audit table can be added
later if multi-sig becomes a requirement.

## Signing math (deterministic, exposed as service helpers)

### snapshot_hash
```python
sha256(canonical_json({
    "decision_id": "uuid",
    "claim_ids": ["sorted", "lexically", ...],
    "brief_id": "uuid|null",
}).encode("utf-8"))
```

`canonical_json` = `json.dumps(obj, sort_keys=True, separators=(",", ":"),
ensure_ascii=False)`. Idempotent — same claim set → same hash.

### signature
```python
canonical_fields = canonical_json({
    "decision_id": "uuid",
    "title": "...",
    "rationale": "...",
    "owner_user_id": "uuid",
    "target_metric": "...",
    "target_value": "...",
    "deadline": "ISO date|null",
    "confidence_at_commit": 0.74,
    "evidence_snapshot_hash": "<hex>",
    "signing_algo": "hmac-sha256-v1",
    "signed_at": "ISO datetime",
    "signing_user_id": "uuid",
})
signature = hmac.new(server_secret, canonical_fields.encode("utf-8"), sha256).digest()
```

Stored as raw 32-byte BYTEA. Verification re-computes from stored fields
and compares with `hmac.compare_digest`.

### Server secret
- Env var `MZ_DECISION_SIGNING_SECRET` (UTF-8 string, ≥32 bytes recommended)
- Dev/test fallback: a fixed `"dev-only-change-me"` string with WARN log
- Future: secret rotation via `signing_metadata.secret_version`

## API surface

| Method | Path | Purpose |
|---|---|---|
| POST | `/decisions/{decision_id}/sign` | Sign the decision (decision owner only); body `{ claim_ids[], brief_id? }` |
| GET | `/decisions/{decision_id}/replay` | Reconstruct the immutable bundle (viewer+) |
| GET | `/decisions/{decision_id}/verify` | Re-compute + compare signature (viewer+); returns `{valid: bool, ...}` |

### Replay bundle shape
```json
{
  "decision": { ...decision fields... },
  "evidence_snapshot": {
    "hash": "<hex>",
    "claim_ids": ["..."],
    "brief_id": "uuid|null"
  },
  "signature": {
    "value_hex": "<hex>",
    "algo": "hmac-sha256-v1",
    "signed_at": "...",
    "signing_user_id": "uuid"
  },
  "claims": [...],          // hydrated when SPEC-024 ledger present
  "evidence_records": [...], // hydrated when SPEC-024 ledger present
  "llm_calls": [...]        // hydrated from llm_call_log within brief lifecycle
}
```

When SPEC-024 ledger is not deployed, `claims` and `evidence_records`
arrays are empty; the bundle still proves the SET of claim_ids that
were referenced at signing time.

## Red-team

| # | Vector | Mitigation |
|---|---|---|
| R1 | Tampering with stored decision fields post-sign | Verify endpoint re-computes signature; mismatch → `valid: false` |
| R2 | Signing as another user | Signing requires `request.user.id == decision.owner_user_id` (403 otherwise) |
| R3 | Re-sign attempts (mutate signed decision) | Service rejects re-sign by default; `force=true` flag for admin override (logged) |
| R4 | Empty claim_ids → meaningless snapshot | Validate `len(claim_ids) >= 1`; routes return 400 |
| R5 | claim_ids with non-UUID strings | Service str()-coerces; canonical_json normalizes; no SQL injection (parameterized) |
| R6 | Signature replay across decisions (copy sig to different decision) | Signature is over `decision_id` field — bound to specific decision |
| R7 | HMAC secret leakage | Stored only in env; never returned in API responses; rotation via secret_version field |
| R8 | Integer overflow / NaN in numeric fields | Numbers serialized as JSON; canonical_json doesn't tolerate NaN |
| R9 | Deserialization attack via signing_metadata_jsonb | JSONB read; never eval'd |
| R10 | Replay leaks PII to lower-role users | Replay is viewer+; consider future role-gating per decision compartment |

## Success criteria
- [ ] Migration 062 applies clean
- [ ] snapshot_hash is deterministic across ordering
- [ ] signature differs when ANY immutable field changes
- [ ] verify returns true for unmodified decision
- [ ] verify returns false after a single field is mutated
- [ ] Re-sign rejected without `force=true`
- [ ] Sign rejected for non-owner (403)
- [ ] Replay returns the full bundle with snapshot + signature
- [ ] Tests cover the math + endpoint + red-team

## Out of scope
- Asymmetric/PKI signing
- Multi-party signing
- KMS / hardware secret storage
- Auto-snapshot at commit (decision owner explicitly POSTs to /sign)
