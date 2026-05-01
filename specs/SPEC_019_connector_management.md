# SPEC-019: Connector Management UI

*Date: 1 May 2026*
*Status: in progress*

---

## Goal

Make Market Zero's data connectors a first-class managed surface — a Claude-style
"Connectors" view that lists every data source, shows its status / dossier /
permissions / health, and lets the right roles toggle, re-run, and configure
them.

The pipeline IS the product. Today it's invisible behind the catalog. After this
spec, every demo can open one screen and answer "what's connected, how fresh is
it, who controls it?" — the same question pattern that makes Claude's connector
view so legible.

## Why this matters

- **Consulting wedge**: shows a buyer that we manage real production sources
  with role-controlled permissions. "Look, FDA Orange Book, last sync 11h ago,
  auto-approval ON for uploader role, 4,127 records flowing into 2 entity
  tables." That story is currently buried in `/catalog/source-profile/...`.
- **Operational hygiene**: today there's no UI to disable a misbehaving
  connector or see whether the upstream API is reachable RIGHT NOW. We have
  `BaseConnector.health_check()` but no live endpoint that calls it.
- **Foundation for SPEC_012 (OpenAlex) and beyond**: when connectors land, they
  appear in the Connectors page automatically, with no per-source UI work.

## Scope

In scope:
- Sidebar listing of every registered connector (Connected / Available)
- Per-connector dossier (already 80% built — wraps `/catalog/source-profile`)
- Live health-check endpoint that actually pings the upstream API
- Per-connector config row (`enabled`, `auto_approve_runs`, `manual_only`, `notes`)
- Role-gated config edits (enterprise only) and run triggers (uploader+ when
  `auto_approve_runs` is true; enterprise+ otherwise)
- Frontend page at `/connectors`

Out of scope (deferred):
- Adding new connectors via the UI (today only via code + registry)
- Per-tool/operation permissions inside a connector (every connector exposes
  one operation: `fetch`. We don't need MCP-style per-tool gating yet.)
- Audit log of who changed what (basic `updated_by` only; richer audit later)
- Connector marketplace / install flow
- Mobile-responsive layout (desktop demo target)

## Non-Goals (explicit)

We are NOT replacing the existing `/catalog/source-profile/{key}` endpoint —
ConnectorsPage is a new view that consumes a richer connector-centric API.
The catalog still owns dataset/entity browsing.

## Architecture

### Storage

Migration `043_connector_config.sql`:

```sql
CREATE TABLE connector_config (
    source_key TEXT PRIMARY KEY,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    auto_approve_runs BOOLEAN NOT NULL DEFAULT FALSE,
    manual_only BOOLEAN NOT NULL DEFAULT FALSE,
    notes TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by UUID REFERENCES users(id) ON DELETE SET NULL
);
```

- `enabled = false` → connector is hidden from scheduler runs and manual
  triggers return 409.
- `auto_approve_runs = true` → uploader role can `POST /connectors/{key}/run`;
  otherwise enterprise required.
- `manual_only = true` → scheduler skips this connector even when `enabled`.
- A connector with no row uses defaults: enabled=true, auto_approve=false,
  manual_only=false. (We do NOT pre-seed rows — absence = defaults.)

### Service: `services/connector_registry.py`

```python
def list_connectors(db: Database) -> list[ConnectorSummary]:
    """One row per registered connector. Joins:
       - CONNECTOR_REGISTRY (which classes exist)
       - CONNECTOR_SCHEDULES (label + cron)
       - DATASET_DEFINITIONS (description, license)
       - connector_config (enabled, auto_approve_runs, manual_only, notes)
       - etl_runs (last_run_at, last_status)
       - record counts (cached from /pipeline-status logic, no per-call DB scan)
    """

def get_connector_detail(db: Database, source_key: str) -> ConnectorDetail:
    """Single-connector dossier. Reuses /catalog/source-profile + adds
    config row + recent etl_runs (last 10) + classification (Connected vs
    Available)."""
```

A connector is **Connected** if it has any successful `etl_runs` row OR
`config.enabled = true`. Otherwise **Available**.

### Endpoints (`api/routes/connectors.py`)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET    | `/connectors` | anonymous | Sidebar list |
| GET    | `/connectors/{key}` | anonymous | Dossier view |
| POST   | `/connectors/{key}/health-check` | uploader | Calls `connector.health_check()` live |
| PUT    | `/connectors/{key}/config` | enterprise | Update enabled/auto_approve/manual_only/notes |
| POST   | `/connectors/{key}/run` | uploader if `auto_approve_runs`, else enterprise | Manual fetch trigger |

Why anonymous on GETs: same reasoning as `/catalog/*` — read-only public
surface. Anonymous can SEE the connector list as a demo proof-point. Mutations
are gated.

### Frontend

```
frontend/src/
├── pages/
│   └── ConnectorsPage.tsx        — sidebar + detail layout
├── components/connectors/
│   ├── ConnectorList.tsx         — left rail (Connected/Available split)
│   ├── ConnectorListItem.tsx     — one row: dot + label + freshness chip
│   ├── ConnectorDetail.tsx       — right pane with 4 tabs
│   ├── ConnectorOverviewTab.tsx  — schedule, last run, total records, license
│   ├── ConnectorPermissionsTab.tsx — enabled/auto_approve toggles (enterprise)
│   ├── ConnectorDataTab.tsx      — entity_breakdown + field_completeness reuse
│   └── ConnectorHealthTab.tsx    — live health-check button + recent etl_runs
└── lib/
    └── api-connectors.ts         — typed fetch wrappers
```

Add a nav entry to `TopBar.tsx`: "Connectors" between "Catalog" and "Workspace".
Role-aware rendering: if `user.role !== 'enterprise'`, the Permissions tab
shows the current values read-only (no toggles, with a "log in as enterprise"
hint).

## Tests First

### `tests/test_connector_registry.py`
- `list_connectors_returns_all_registered` — every key in `CONNECTOR_REGISTRY` appears
- `list_connectors_uses_defaults_when_no_config_row` — enabled=true, auto_approve=false
- `list_connectors_marks_connected_when_etl_run_exists`
- `list_connectors_marks_available_when_no_runs_and_default_enabled` — borderline case
- `get_connector_detail_returns_404_for_unknown_key`
- `get_connector_detail_includes_recent_etl_runs`
- `get_connector_detail_includes_config_row_or_defaults`

### `tests/test_connectors_api.py`
- `list_endpoint_returns_200_anonymous` — read access works without auth
- `list_endpoint_response_shape` — `{connectors: [{source_key, label, status, enabled, last_run, records, schedule}, ...]}`
- `dossier_endpoint_returns_200_anonymous`
- `dossier_endpoint_404_for_unknown_key`
- `health_check_endpoint_401_anonymous`
- `health_check_endpoint_403_viewer`
- `health_check_endpoint_200_uploader_calls_connector_health_check` — mock the connector class
- `config_put_401_anonymous`
- `config_put_403_uploader` — uploader cannot edit config
- `config_put_200_enterprise_writes_row` — first PUT inserts, second updates
- `config_put_400_for_unknown_key`
- `run_endpoint_401_anonymous`
- `run_endpoint_403_viewer`
- `run_endpoint_403_uploader_when_auto_approve_false`
- `run_endpoint_200_uploader_when_auto_approve_true`
- `run_endpoint_200_enterprise_regardless_of_auto_approve`
- `run_endpoint_409_when_disabled` — `enabled = false` blocks even enterprise

All tests must FAIL before implementation. Use `app.dependency_overrides[get_current_user]`
+ `_can_connect_to_db()` skip helper + the `fake_db` fixture pattern from
`test_role_gates.py`.

## Implementation Plan

1. **Spec** ✅ (this file)
2. **Tests** — write both test files, see them fail
3. **Migration 043** — `connector_config` table + index on `source_key` (PK already covers it)
4. **Service** — `services/connector_registry.py` with `list_connectors()` + `get_connector_detail()`
5. **Routes** — `api/routes/connectors.py`; register in `api/app.py`
6. **Verify backend** — run pytest, confirm all SPEC_019 tests pass + zero regressions
7. **Commit backend** — `feat: SPEC_019 backend — connector management API`
8. **Frontend** — ConnectorsPage + components + nav entry
9. **Verify frontend** — manual smoke test, vite build clean
10. **Commit frontend** — `feat: SPEC_019 frontend — ConnectorsPage`

## Acceptance

Backend:
- Both test files pass; zero regressions in 1319-baseline suite
- After `migrate.py`:
  - `GET /connectors` returns one row per registered connector (15 today)
  - `GET /connectors/{key}` returns dossier with last 10 etl_runs
  - `POST /connectors/fda_orange_book/health-check` (uploader token) returns
    `{healthy: bool, response_time_ms, message}`
  - `PUT /connectors/fda_orange_book/config` (enterprise token) with
    `{auto_approve_runs: true}` writes the row; subsequent GET shows the change
  - Anonymous calls to GETs work; mutations 401/403 as specified

Frontend:
- `/connectors` route renders sidebar with Connected/Available split
- Clicking a row loads the dossier in the right pane
- Health-check button works (or shows 401/403 explainer when unauthorized)
- Permissions tab shows toggles to enterprise users, read-only labels otherwise
- vite build is clean; no console errors on the page

## Rollout

1. Local pytest passes
2. Push → Railway auto-deploy
3. Apply migration: `railway run python migrate.py` (043 only)
4. Verify endpoints with curl using a seeded enterprise token
5. Frontend ships in same release; nav entry visible to all roles
6. No env var changes required

## Rollback

- Migration 043 is additive; safe to leave applied
- If `/connectors` endpoints misbehave: remove the router include from
  `api/app.py` and redeploy. The page will 404 but nothing else breaks.
- Frontend: hide nav entry in `TopBar.tsx`; the page route stays but is
  unreachable

## Follow-ups (not this spec)

- Per-operation permissions (when a connector grows multiple operations beyond
  `fetch` — none today)
- Audit log of config changes (write to existing `steward_actions` table?)
- Cron editor in Permissions tab — today schedules live in
  `scheduler/config.py` source code; making them DB-driven is a separate spec
- Health-check polling / dashboard widget on landing page
- "Add connector" wizard — would need a connector plugin loader
