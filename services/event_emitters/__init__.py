"""Event-row builders.

One module per event_type. Each module exports a `build_event_row(...)`
function that takes typed inputs and returns a dict ready for INSERT
INTO market_events. They do NOT touch the DB — that's the caller's
job. Keeps unit tests pure (no DB required).

Idempotency: every builder computes a deterministic event_hash so
re-running the connector doesn't produce duplicate rows. The DB has
a UNIQUE INDEX on event_hash (migration 026).
"""
