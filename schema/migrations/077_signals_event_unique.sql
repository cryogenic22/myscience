-- 077_signals_event_unique.sql
--
-- Dedup hardening for the sensing stream.
--
-- signal_promoter inserts with `ON CONFLICT (event_id) DO NOTHING`, but
-- migration 037 never added a UNIQUE constraint on signals.event_id — so the
-- ON CONFLICT was a silent no-op and dedup relied on a per-call Python set
-- (lost across crashes / concurrent runs). The table is clean today (verified:
-- 625 rows, 625 distinct event_ids), so we can add the constraint safely now
-- and make the promoter's idempotency real and durable. Additive.

ALTER TABLE signals
    ADD CONSTRAINT signals_event_id_unique UNIQUE (event_id);
