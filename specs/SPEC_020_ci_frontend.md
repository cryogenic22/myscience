# SPEC-020: CI Frontend MVP

*Date: 2 May 2026*
*Status: in progress*

---

## Goal

Ship the analyst's day-one CI surface at `/ci` — a Daily Digest, Signal
Detail, Watchlist, and Reviewer queue — wired to the data we have today
(market_events via `/intelligence/feed`, the signals table, a new
watchlist table). Honest empty states where the SPEC-015 pipeline hasn't
landed yet, structured so the pipeline can populate the UI without rework.

This is **not** the full SPEC-015 vision (14–20 weeks of pipeline work).
It IS the workflow shell that turns "we have intelligence data" into
"an analyst can use it."

## Why this matters

- The CI workflow described in `specs/comp_intel_2.md` §3 (the morning
  analyst) has zero dedicated surface today — `IntelligenceFeed.tsx`
  exists but is a side-panel, not a page.
- A consulting demo of "look how the pipeline becomes the product" needs
  a screen that reads as "CI control center," not a feed widget.
- When SPEC-015 backend ships (clustering, KBQ engine, 8-K parser), we
  want the UI ready to consume it — same endpoints, same shapes.

## Scope

In:
- New `/ci` page route, sidebar + detail layout (matches Connectors pattern)
- 4 tabs: Digest / Signals / Watchlist / Reviewer
- `GET /signals?status=&impact=&kbq=&entity_type=&entity_id=&limit=` — list
- `GET /signals/{id}` — detail (resolved evidence document references)
- `POST /signals/{id}/review` (enterprise) — set status + reviewed_by/at
- `GET /watchlist`, `POST /watchlist`, `DELETE /watchlist/{id}` — user-scoped
- Migration 044: `watchlist_entries` table (user_id, entity_type, entity_id, label, created_at)
- Frontend: SignalCard, SignalDetail, EvidenceStack, KBQFilter, WatchlistManager
- Keyboard nav (j/k navigate, e escalate, x dismiss, return open)
- Role-aware: Reviewer tab enterprise-only; Watchlist requires viewer+

Out (deferred):
- Brief composer (SPEC-015 F4)
- Connector health dashboard (already SPEC-019)
- Trackers (SPEC-015 F9)
- Alert delivery (push/email) — UI surface only for now
- Pattern signals (KBQ 2 exec change clusters, KBQ 4 trial-aggregation)
- Clustering / KBQ engine — that's the SPEC-015 backend track
- 8-K parser — same

## Non-Goals

We are NOT writing to `signals` from the API. The clustering/scoring
service writes; the API only reads + reviews. This keeps the API thin
and avoids racing with the future write path.

## Architecture

### Storage

Migration `044_watchlist_entries.sql`:

```sql
CREATE TABLE watchlist_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    label TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, entity_type, entity_id)
);
CREATE INDEX idx_watchlist_user ON watchlist_entries (user_id);
```

Per-user, no team sharing in MVP (defer per `comp_intel_2.md` §3.2).

### Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/signals` | anon | List signals (status defaults to shipped+reviewed) |
| GET | `/signals/{id}` | anon | Single signal with evidence |
| POST | `/signals/{id}/review` | enterprise | Set status (reviewed/shipped/retracted) + actor |
| GET | `/watchlist` | viewer+ | Current user's watchlist entries |
| POST | `/watchlist` | viewer+ | Add an entry; idempotent on (user, type, id) |
| DELETE | `/watchlist/{id}` | viewer+ | Remove (404 if not owned by current user) |

`/signals` and `/signals/{id}` are anonymous on purpose — same reasoning
as `/connectors`. Read surface is a demo proof-point. Mutations gated.

### Frontend

```
frontend/src/
├── pages/
│   └── CIPage.tsx                  — header + tabs + body
├── components/ci/
│   ├── CILayout.tsx                — left rail + main pane shell
│   ├── DigestTab.tsx               — wraps /intelligence/feed in CI styling
│   ├── SignalsTab.tsx              — list from /signals + detail pane
│   ├── WatchlistTab.tsx            — CRUD + filter signals to watchlist
│   ├── ReviewerTab.tsx             — candidates queue, enterprise-only
│   ├── SignalCard.tsx              — one row in any list (with badges)
│   ├── SignalDetail.tsx            — right pane: headline + evidence stack
│   ├── EvidenceStack.tsx           — list of evidence documents
│   ├── KBQFilter.tsx               — chip group for kbq_tags
│   ├── ConfidenceBadge.tsx         — confirmed/reported/inferred/disputed
│   └── ImpactBadge.tsx             — high/medium/low
└── lib/
    └── (api wrappers in api.ts — signalsApi, watchlistApi)
```

Add nav entry to `TopBar.tsx` between "Catalog" and "Connectors":
"CI" — visible to all, page itself shows role-appropriate tabs.

### Empty states

- Signals tab when `signals` table empty: card explaining the SPEC-015
  pipeline isn't active yet, with a link to the Connectors page so users
  can verify data is flowing.
- Reviewer tab empty: "No candidates awaiting review" — distinct from
  pipeline-not-active.
- Watchlist with no entries: "Add a company or drug to track its signals"
  with an inline add control.

## Tests First

### `tests/test_signals_api.py`
- `list_endpoint_returns_200_anonymous`
- `list_endpoint_response_shape` (items[].id, headline, kbq_tags, impact_tier, confidence_tier)
- `list_endpoint_filters_by_status`
- `list_endpoint_filters_by_impact`
- `list_endpoint_filters_by_kbq` (any-of matching on TEXT[])
- `list_endpoint_filters_by_entity` (entity_type + entity_id)
- `list_endpoint_default_excludes_candidate_and_superseded`
- `list_endpoint_orders_by_impact_then_recency`
- `detail_endpoint_returns_signal_with_evidence`
- `detail_endpoint_404_for_unknown_id`
- `review_endpoint_401_anonymous`
- `review_endpoint_403_viewer`
- `review_endpoint_403_uploader`
- `review_endpoint_200_enterprise_sets_status_and_actor`
- `review_endpoint_400_for_invalid_status`

### `tests/test_watchlist_api.py`
- `list_endpoint_401_anonymous`
- `list_endpoint_returns_200_for_viewer`
- `list_endpoint_returns_only_users_own_entries`
- `add_endpoint_201_creates_entry`
- `add_endpoint_idempotent_on_duplicate` (returns 200 with existing row)
- `add_endpoint_401_anonymous`
- `delete_endpoint_404_for_other_users_entry`
- `delete_endpoint_204_for_own_entry`

All tests must FAIL before impl.

## Implementation Plan

1. Spec ✅
2. Tests written, see them fail
3. Migration 044 + connector_registry-style read service
4. `services/signal_service.py` + `services/watchlist_service.py`
5. `api/routes/signals.py` + `api/routes/watchlist.py`
6. Register routers in `api/app.py`, add to SPA fallback list
7. Run pytest — all SPEC-020 tests green, zero regressions
8. Backend commit
9. Frontend: api.ts wrappers, then components, then page, then route
10. vite build clean
11. Frontend commit
12. Push, wait for deploy, run /debug/migrate, smoke-test endpoints

## Acceptance

- 23 new tests pass; baseline 1841 still passes
- `GET /signals` returns `{signals: [...], count, limit, offset}` even when empty
- `GET /watchlist` (viewer token) returns `{entries: []}` for fresh user
- `POST /watchlist` (viewer token) with body `{entity_type:"company", entity_id:"<uuid>", label:"Pfizer"}` 201s; second identical call 200s with same entry
- `POST /signals/{id}/review` 401 anon, 403 viewer/uploader, 200 enterprise
- `/ci` route renders sidebar with 4 tabs; Digest shows current intelligence feed; Signals shows pipeline-not-active card; Watchlist shows add control; Reviewer hidden for non-enterprise
- vite build clean

## Rollout

1. Local pytest passes
2. Push → Railway auto-deploys
3. Apply migration via `POST /debug/migrate`
4. Verify endpoints via curl
5. Browse `/ci` to confirm render
6. No env var changes

## Rollback

- Migration 044 additive — safe to leave applied
- Remove the two router includes in `api/app.py` to disable signals/watchlist API
- Remove `/ci` from `App.tsx` routes + `is_api` list to hide page

## Follow-ups (not this spec)

- Frontend login UI (separate spec) — without it, watchlist/review needs DevTools-injected token
- Pattern signals + alert delivery — needs SPEC-015 backend
- Brief composer — SPEC-015 F4
- Real signal pipeline — SPEC-015 B1–B5
