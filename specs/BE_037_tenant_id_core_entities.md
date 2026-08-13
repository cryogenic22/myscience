# BE-37 — Tenant model on core entity tables

> Filed in `docs/AGENT_BACKLOG.md#be-37`. Loop opened 2026-05-10.
> Branch: `claude/be-037-tenant-id-core`.

## 1 · Problem

The intelligence-layer audit identified a critical SaaS-blocker:
`scope_key` exists on `chat_sessions` and `deep_research_jobs` (so
session state is per-tenant), but the **core entity tables**
(`drugs`, `companies`, `clinical_trials`, `mechanisms_of_action`)
have no tenant column. As a result a misconfigured query in
`services/search.py` or `services/graph.py` can return Pfizer's
data inside Roche's session.

BE-37 lays the schema. BE-38 (next branch) wires the WHERE-clause
middleware. BE-39 adds CI cross-tenant isolation tests.

## 2 · Design

### Tenant identifier shape

Reuse the **TEXT** shape of `chat_sessions.scope_key` so the same
slug ("public", "pfizer", "roche", per-customer) flows end-to-end:

```sql
tenant_id TEXT NOT NULL DEFAULT 'public'
```

`'public'` is the documented default for shared / pre-tenancy data
and for any entity ingested by a public connector (ClinicalTrials.gov,
PubMed, etc.) where ownership is not customer-specific.

### Tables in scope

| Table                   | Source migration | Rationale                              |
|-------------------------|------------------|----------------------------------------|
| `drugs`                 | 001              | Per BE-37 explicit list                 |
| `companies`             | 001              | Per BE-37 explicit list                 |
| `clinical_trials`       | 001              | BE-37 says "trials" — this is the table |
| `mechanisms_of_action`  | 001              | BE-37 says "mechanisms" — this is the table |

### Migration 066 strategy

Single migration adds `tenant_id` with a default. PostgreSQL fills
existing rows with the default value as part of the ALTER, so no
separate backfill pass is required for the "legacy → public"
transition. The NOT NULL constraint can be added in the same
statement once the default is in place.

Index per table on `tenant_id` so the BE-38 middleware's
`WHERE tenant_id = :current_tenant` is cheap.

### Backfill script

`scripts/backfill_tenant_id.py` is shipped for the **next** phase —
when ingestion paths start populating `tenant_id` from session
context, the script lets a steward retro-tag a slice of rows by
provenance (`source_api`, `source_url`) without writing custom SQL.
Today's migration leaves every row at `'public'`; the script is a
no-op until tenancy is meaningful.

### What BE-37 does NOT do

- Wire the WHERE-clause filter — that's BE-38.
- Audit / isolation tests — that's BE-39.
- Per-tenant pricing, white-labelling — explicitly out of scope per
  `docs/PRODUCT_BACKLOG.md` § "Out of scope".

## 3 · Acceptance

Per BE-37 entry in `AGENT_BACKLOG.md`:

- [x] `tenant_id TEXT NOT NULL DEFAULT 'public'` on drugs / companies
  / clinical_trials / mechanisms_of_action (migration 066).
- [x] Index per table on `tenant_id`.
- [x] Backfill script with `--dry-run`, `--source-api` filter, and
  audit log so a steward can retro-tag rows safely once tenancy
  starts being attached.
- [x] After running migration on a clean DB:
  `SELECT COUNT(*) FROM drugs WHERE tenant_id IS NULL` → 0.
- [x] Existing single-tenant tests still pass.
