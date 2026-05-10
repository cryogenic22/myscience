# BE-39 — Per-tenant audit trail + CI cross-tenant isolation tests

> Filed in `docs/AGENT_BACKLOG.md#be-39`. Loop opened 2026-05-10.
> Stacks on `claude/be-038-tenant-isolation-middleware`.
> Branch: `claude/be-039-tenant-audit-tests`.

## 1 · Problem

BE-38 wires the WHERE filter; BE-39 proves it works in CI and gives
stewards an audit surface so they can verify per-customer isolation
after the fact.

Two deliverables:

1. **Per-tenant query audit log** — every read against a
   tenant-scoped table is logged with `(tenant_id, query_kind,
   table_name, row_count, created_at)`. Append-only. 90-day TTL via
   a cleanup helper a steward / cron can invoke.
2. **CI isolation tests** — fixture-based tests that construct two
   tenants with overlapping entity ids and assert HybridSearch +
   GraphTraversal return zero rows from the other tenant.

## 2 · Design

### Audit log

`schema/migrations/067_tenant_query_audit.sql`:

```sql
CREATE TABLE tenant_query_audit_log (
    id          BIGSERIAL PRIMARY KEY,
    tenant_id   TEXT NOT NULL,
    query_kind  TEXT NOT NULL,    -- 'search' | 'graph' | 'dossier' | …
    table_name  TEXT NOT NULL,
    row_count   INTEGER NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX … ON (tenant_id, created_at DESC);
```

`services/tenant_audit.py`:

- `record_query(db, *, query_kind, table_name, row_count)` — fire-
  and-forget INSERT. Reads the active tenant from the BE-38
  contextvar.
- `cleanup_older_than(db, days=90)` — DELETE WHERE created_at <
  NOW() - INTERVAL ':days days'. Logs the deleted count.
- `read_audit(db, *, tenant_id, since=None, limit=200)` — recent
  audit events for a tenant.

### CI isolation tests

`tests/test_tenant_isolation.py`:

- Fixture: a fake DB serving rows for two tenants ("pfizer" and
  "roche") plus a "public" baseline. Same-shaped data so the only
  difference is the tenant tag.
- For each entity type with a tenant column (drug / company /
  trial), assert: searching while in tenant A returns A + public
  rows but **never** B's rows.
- For graph: same with `_resolve_labels`.
- Negative test: a coding-bug regression — if someone mistakenly
  removes the tenant filter, the test must fail loudly.

## 3 · Acceptance

- [x] migration 067 + tenant_query_audit_log table
- [x] services/tenant_audit.py with record_query / cleanup / read
- [x] tests proving record_query writes one row per call
- [x] tests proving cleanup_older_than removes only stale rows
- [x] cross-tenant CI tests pass — zero rows from the other tenant
  in search and graph
- [x] regression-canary test: stub a "broken" search that omits the
  filter; confirm the canary test FAILS, proving the assertion
  shape is sensitive

The audit endpoint is left for a follow-up PR (steward / admin UI
work, lives with BE-A03 in PRODUCT_BACKLOG).
