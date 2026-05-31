# SPEC A — Engagements CRUD API

*Loop A. Backend HTTP layer over the already-shipped Z3/Z4/Z5 service
modules. Unblocks the v7 IA frontend (Loop B) which needs endpoints to
fetch engagement, brief, and priority-matrix data from.*

## Problem

Z3 (`services/engagement.py`), Z4 (`services/business_context_brief.py`),
and Z5 (`services/priority_matrix.py`) shipped to main as service-layer
modules with full CRUD + FSM logic. There is **no HTTP layer over them**
— the React pages F2/F3/F4/F5 etc. that we shipped have no endpoints
to call. The data model is invisible from outside.

## Decision

One router (`api/routes/engagements.py`) exposing the minimum surface
the frontend needs:

| Method | Path | Auth | Returns |
|---|---|---|---|
| `POST` | `/engagements` | uploader+ | new Engagement |
| `GET` | `/engagements` | viewer+ | list (filter: status, situation) |
| `GET` | `/engagements/{eid}` | viewer+ | Engagement + optional nested brief |
| `POST` | `/engagements/{eid}/advance` | uploader+ | Engagement (post-advance) |
| `PATCH` | `/engagements/{eid}/status` | uploader+ | Engagement (post-status-change) |
| `POST` | `/engagements/{eid}/brief` | uploader+ | new BCB |
| `GET` | `/engagements/{eid}/brief` | viewer+ | BCB (or null) |
| `POST` | `/briefs/{bcb_id}/sign-off` | uploader+ | BCB (signed) |
| `PUT` | `/briefs/{bcb_id}/priority-matrix` | uploader+ | PriorityMatrix |
| `GET` | `/briefs/{bcb_id}/priority-matrix` | viewer+ | PriorityMatrix |

Errors map cleanly:
- `404` — engagement or brief not found
- `400` — invalid situation, empty name, malformed body
- `409` — FSM violation (`InvalidStageTransition`, `InvalidStatusTransition`)
- `401/403` — auth as in existing routes

## Acceptance test

A single integration test in `tests/test_engagements_api.py` reproduces
a full lifecycle:

```python
def test_acceptance_engagement_lifecycle(client_with_db):
    client, _ = client_with_db
    tok = _login(client, "uploader@demo.market-zero.io")

    # 1. POST creates an engagement in draft/brief.
    r = client.post("/engagements", headers=_hdr(tok), json={
        "name": "Wegovy MASH defense", "asset": "drug:wegovy",
        "situation": "defense",
    })
    assert r.status_code == 201
    eid = r.json()["id"]
    assert r.json()["stage"] == "brief"
    assert r.json()["status"] == "draft"

    # 2. PATCH status moves to active.
    r = client.patch(f"/engagements/{eid}/status", headers=_hdr(tok),
                     json={"status": "active"})
    assert r.status_code == 200

    # 3. POST /advance to sources works.
    r = client.post(f"/engagements/{eid}/advance", headers=_hdr(tok),
                    json={"to_stage": "sources", "rationale": "have sources"})
    assert r.status_code == 200
    assert r.json()["stage"] == "sources"

    # 4. Skip-ahead rejected with 409.
    r = client.post(f"/engagements/{eid}/advance", headers=_hdr(tok),
                    json={"to_stage": "workshop", "rationale": "skip"})
    assert r.status_code == 409

    # 5. GET list includes the engagement.
    r = client.get("/engagements", headers=_hdr(tok))
    assert r.status_code == 200
    assert any(e["id"] == eid for e in r.json()["engagements"])

    # 6. POST /brief creates a BCB.
    r = client.post(f"/engagements/{eid}/brief", headers=_hdr(tok), json={
        "purpose": "Defend market share post-MASH approval",
        "scope_in": ["mash"], "scope_out": [],
        "strategic_decisions": [], "success_metrics": ["share retention"],
        "deliverables": ["dossier"], "horizon_quarters": 4,
        "decision_owner": "Maria", "preparer": "Ravi",
    })
    assert r.status_code == 201
    bcb_id = r.json()["id"]

    # 7. GET /brief reads it back.
    r = client.get(f"/engagements/{eid}/brief", headers=_hdr(tok))
    assert r.status_code == 200
    assert r.json()["id"] == bcb_id
```

## Out of scope

- Dossier / Synthesis / Gaps / Scenarios / War-room data fetching (those
  pages will use existing endpoints or get their own routes in later loops)
- Multi-tenancy enforcement (the engagement table has `tenant_scope` but
  authority checks not yet wired)
- Pagination on list (limit=50 default; not paginated yet)

## Red-team checklist

1. **Auth tiers** — POSTs require uploader, GETs require viewer; mirrors
   `war_room.py` convention.
2. **FSM errors map to 409**, not 400 — distinguishes "your input is bad"
   from "your input is fine but the resource state precludes it."
3. **Validation at the door** — empty name, invalid situation, missing
   required BCB fields → 400 before any DB call.
4. **No silent-empty** — a missing engagement is 404, not an empty Engagement.
5. **No service-layer leak** — exceptions like `InvalidStageTransition`
   never escape the route; they're caught and mapped to HTTP codes.
6. **Anti-slop** — module imports only from `services.engagement`,
   `services.business_context_brief`, `services.priority_matrix`,
   plus the standard `api.deps`. No inline DB queries.

## File plan

| File | Why |
|---|---|
| `specs/SPEC_A_engagements_api.md` | This SPEC |
| `api/routes/engagements.py` | New router (HTTP wrapper over services) |
| `api/app.py` | Register the router |
| `tests/test_engagements_api.py` | Integration tests + acceptance |
