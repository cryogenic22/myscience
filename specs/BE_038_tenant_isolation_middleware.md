# BE-38 — Tenant isolation middleware

> Filed in `docs/AGENT_BACKLOG.md#be-38`. Loop opened 2026-05-10.
> Stacks on `claude/be-037-tenant-id-core`. Branch:
> `claude/be-038-tenant-isolation-middleware`.

## 1 · Problem

BE-37 added `tenant_id` to `drugs / companies / clinical_trials /
mechanisms_of_action` but the application code does not yet
**filter** by it. Until search and graph reads include
`WHERE tenant_id = :current` clauses, the SaaS-blocker is still
open: a misconfigured query in `services.search.HybridSearch` could
return another tenant's drug rows.

## 2 · Design

### Tenant context

`services/tenant_context.py` — a single contextvar carrying the
current tenant_id, with helpers:

```python
from services.tenant_context import (
    get_current_tenant,   # returns the active tenant slug
    set_current_tenant,   # raw setter (returns Token for reset)
    with_tenant,          # ctx-manager: with with_tenant("pfizer"): ...
    DEFAULT_TENANT,       # 'public'
    TABLES_WITH_TENANT,   # frozenset of tables BE-37 added the column to
)
```

Reads default to `'public'` when nothing is set so any code path
that runs outside a request (background workers, cron, scripts)
sees only the shared tenant — the safest default, **never** a
specific customer's data.

### Search filter

`HybridSearch._build_where_clause` now appends
`AND tenant_id IN ('public', :current)` for entity types whose
tables have the column (drug, company, trial). Public-tenant rows
remain visible from any session — that's the cross-tenant fixture
data (FDA-approved drugs, public trials, etc.) so customers don't
suddenly see an empty knowledge base. Customer-private uploads
(`tenant_id = 'pfizer'`) are visible only inside that tenant.

### Graph traversal filter

`GraphTraversal._resolve_labels` now joins through the entity
tables to the tenant column, dropping nodes whose tenant doesn't
match `('public', :current)`. The traversal SQL function still
walks `entity_links` across tenants (it has no tenant column) but
nodes that resolve to disallowed tenants don't surface in the
returned `Subgraph`. Defense-in-depth — primary isolation is at
the table level; the graph layer prunes any leakage.

### Connector / writer side (deferred)

Inserting tenant_id at write time is BE-2 and BE-37 follow-ups
(production signal-creation path is not in this tree). The
default column DEFAULT 'public' covers writers that don't supply
the column.

## 3 · Wiring at the edge

`api/deps.py::get_current_tenant_dep`:

1. If `session_id` is present and `chat_sessions.scope_key` resolves
   to a non-empty slug → use it.
2. Else `'public'`.

The dep installs the tenant on the contextvar for the duration of
the request. Endpoints that bypass the dep (CLI scripts, cron) get
`'public'` automatically.

## 4 · Acceptance

- [x] `services/tenant_context.py` with contextvar + ctx-manager
  + DEFAULT_TENANT + TABLES_WITH_TENANT
- [x] HybridSearch filters drug / company / trial reads by tenant
- [x] GraphTraversal `_resolve_labels` filters by tenant
- [x] api/deps `get_current_tenant_dep` reads `chat_sessions.scope_key`
- [x] Tests prove: search results exclude other-tenant rows; graph
  resolves cross-tenant entity ids to "unknown" nodes; nothing
  changes for public-tenant queries
- BE-39 (separate branch) adds the per-tenant audit trail and CI
  cross-tenant zero-leak tests using these primitives.
