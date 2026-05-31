# SPEC Z3 — Engagement entity + 7-stage lifecycle FSM

*Bucket 2 (Data model) loop 3. 30 May 2026.*

## Problem
The v7 design canon's single most important structural commitment is **engagement-as-spine**: every meaningful unit of work is an `Engagement` with a fixed lifecycle. Today there's no `Engagement` entity in the codebase — no table, no service, no FSM. Bucket 3 (Frontend IA) hangs entirely off this; F2/F3/F4 cannot start until the entity exists. Z4 (BCB) and Z5 (priority matrix) attach to it.

## Contract

### Lifecycle (7 stages, matching `docs/helix-v7-gap-analysis.html` §1.2)
```
brief → sources → dossier → synthesis → gaps → scenarios → workshop
```
`workshop` is the terminal stage (war + decisions). Stages map 1:1 onto the gap-analysis lifecycle diagram.

### Status (orthogonal to stage)
```
draft → active → completed → archived
```

### FSM rules
- **Forward progression** between adjacent stages: always allowed when `status='active'`.
- **Back-track** to an earlier stage: allowed (with audit log entry — "revisited synthesis because new fact arrived").
- **Skip-ahead** (e.g. brief → scenarios): rejected with `InvalidStageTransition`. Must walk the lifecycle.
- **Stage changes** only allowed when `status='active'`. Draft engagements have no stage progression.
- **Status changes**: `draft → active` allowed; `active → completed` only from `workshop` stage; `* → archived` always allowed.

### Service `services/engagement.py`
```python
class LifecycleStage(str, Enum):
    BRIEF, SOURCES, DOSSIER, SYNTHESIS, GAPS, SCENARIOS, WORKSHOP = ...

class EngagementStatus(str, Enum):
    DRAFT, ACTIVE, COMPLETED, ARCHIVED = ...

class InvalidStageTransition(ValueError): ...
class InvalidStatusTransition(ValueError): ...

@dataclass
class Engagement:
    id: str
    name: str             # "CagriSema Pre-Launch Wargame, May 2026"
    asset: str            # "drug:cagrisema" or similar
    sponsor: str | None   # "novo_nordisk"
    situation: str        # "launch" | "defense" | "lcm"
    workshop_date: datetime | None
    stage: LifecycleStage
    status: EngagementStatus
    scope: dict           # extensible JSON: tags, decisions to inform, etc.
    created_by: str
    created_at: datetime
    updated_at: datetime
    tenant_scope: str | None

def create_engagement(db, *, name, asset, situation, sponsor=None,
                      workshop_date=None, scope=None, created_by) -> str
def get_engagement(db, eid) -> Engagement | None
def list_engagements(db, *, status=None, situation=None, limit=50) -> list[Engagement]
def advance_stage(db, eid, *, to_stage, rationale, actor) -> Engagement
def set_status(db, eid, *, to_status, actor) -> Engagement
```

Every stage/status mutation writes an `engagement_audit_log` row.

## Database

Migration `068_engagements.sql`:
- `engagements` table with the fields above, CHECK constraints over stage + status, FOREIGN KEY hints commented (FKs to drugs/indications etc. deferred to E phase since asset is polymorphic).
- `engagement_audit_log` table: id, engagement_id, actor, event_type ('stage_change' | 'status_change' | 'created'), from_value, to_value, rationale, created_at.

## Acceptance tests
1. **Forward stage progression works** — `brief → sources → dossier → … → workshop`.
2. **Skip-ahead is rejected** — `brief → scenarios` raises `InvalidStageTransition`.
3. **Back-track allowed but logged** — `dossier → sources` succeeds and writes an audit entry.
4. **Stage change blocked when status is draft** — raises `InvalidStageTransition`.
5. **Status `draft → active` works**; **`draft → completed` rejected**; **`workshop+active → completed` works**.
6. **Invalid situation value rejected** at create-time.
7. **`get_engagement(unknown_id)` returns None**, doesn't raise.
8. **`list_engagements(status='active')` filters correctly**.

## Out of scope (drift guard)
- No UI surface (F4 EngagementPage builds the stepper).
- No tenant RLS enforcement (E phase).
- No coupling to BCB (Z4) — Engagement stands alone; BCB attaches in Z4.

## Files
- NEW `schema/migrations/068_engagements.sql`
- NEW `services/engagement.py`
- NEW `tests/test_engagement.py`
