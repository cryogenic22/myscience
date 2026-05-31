# SPEC A1 — Fact assertion on ingest

*Phase A, loop 1 of the spine convergence (`docs/phase-a-readiness.md`). 24 May 2026.*

## Problem
The facts ledger (PB-1307, migration 065) is standalone: nothing asserts facts during ingest, so `facts` is empty in prod while ~569 `market_events` sit in the existing pipeline. The ledger cannot be the spine until ingest writes to it. A1 makes the ledger **load-bearing** by mapping `market_events → facts`, both as a one-time backfill and going forward.

## Contract
New module `services/fact_ingest.py`:

```
event_to_fact(event: dict) -> FactDraft | None
    Pure mapping (no DB). market_event row → a FactDraft, or None if the event
    has no resolvable subject entity (entity_id/entity_type both required).
    - predicate: from event_type via _EVENT_PREDICATE map (regulatory_approval,
      trial_result, pricing_intent, ma_deal, safety_signal, ...); fallback 'market_event'.
    - kind: 'anticipatory' if event is forward-looking (pricing_intent, or event_date
      in the future); else 'point'.
    - subject_entity_type/id: event.entity_type / event.entity_id.
    - object_value: {event_type, description, source_url, source_feed, event_id}.
    - valid_from: event_date (fallback created_at).
    - confidence: event.trust_score (clamped [0,1], default 0.5).

assert_event_fact(db, event: dict) -> str | None
    Idempotent. Skips if a non-superseded fact already exists for
    (subject, predicate, object_value->>'event_id'). Else calls
    facts_ledger.assert_fact and returns the new fact id.

backfill_facts_from_events(db, *, limit=None, since_days=None,
                           event_types=None) -> BackfillStats
    Iterate market_events (optionally filtered), assert_event_fact each.
    Returns {scanned, asserted, skipped_existing, skipped_no_subject}.
```

Wire-in: `EventCollector._persist_event` calls `assert_event_fact` after a new event is persisted (best-effort, logged on failure — ingest must not break if the ledger write fails).

## Acceptance test (runnable)
1. `event_to_fact` maps an `approval` event for `(drug, wegovy-demo)` → `predicate='regulatory_approval'`, `kind='point'`, subject correct, confidence from trust_score. *(pure, no DB)*
2. A `pricing` event with a **future** `event_date` → `kind='anticipatory'`, `valid_from` in the future.
3. `assert_event_fact` is **idempotent**: asserting the same event twice asserts once (second is `skipped_existing`).
4. An event missing `entity_id` → `event_to_fact` returns `None`; `backfill` counts it `skipped_no_subject`.
5. **Prod reproduction (the spine proof):** run backfill over real `market_events`; then `query_facts`/`facts_as_of` for a backfilled subject returns the asserted fact; a seeded future-dated WAC fact for `(drug, wegovy-demo)` is **invisible now**, **visible `as_of=2027`**. (The A2/A3 `get_entity_360` read lands next loop; A1 proves the assertion + temporal read via `facts_as_of`.)

## Out of scope (drift guard)
- No Context Layer (A2). No `get_entity_360` (A3). No bus changes (B).
- No paragraph/section extraction (E2). `source_doc_id` stays null for now (events have URLs, not evidence UUIDs); provenance lives in `object_value.source_url`.
- No supersession logic on backfill (corrections come later); backfill only asserts.
- Signals/`signal_promoter` unchanged — they keep reading `market_events`. A1 adds facts alongside, it does not migrate signals.

## Tests
`tests/test_fact_ingest.py` — pure mapping cases (1,2,4) with no DB; idempotency (3) with MagicMock DB in the established style. Coverage ratchet: net-new tests, 0 regressions.
