-- 078_signal_facts.sql
--
-- Unify the two sensing stores (E20 / PB-SL05 + PB-SL07).
--
-- Until now `signals` (037) derived only from market_events and never
-- referenced the `facts` ledger (065). This migration makes the signal a
-- *lens over facts*:
--   1. signal_facts — the Helix v8 `feeds_fact_ids` edge: which facts a signal
--      produces / corroborates / relates to. Enables bidirectional provenance.
--   2. signals.event_id becomes NULLABLE so a signal can be minted from a fact
--      (a deck readout, a boxed warning) that has no market_event. The
--      UNIQUE(event_id) from 077 still holds for event-derived signals (NULLs
--      are allowed in a unique index).
-- Additive + reversible.

ALTER TABLE signals ALTER COLUMN event_id DROP NOT NULL;

CREATE TABLE IF NOT EXISTS signal_facts (
    signal_id   UUID NOT NULL REFERENCES signals(id) ON DELETE CASCADE,
    fact_id     UUID NOT NULL REFERENCES facts(id) ON DELETE CASCADE,
    role        TEXT NOT NULL DEFAULT 'produces'
                  CHECK (role IN ('produces', 'corroborates', 'contradicts', 'relates')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (signal_id, fact_id)
);

CREATE INDEX IF NOT EXISTS idx_signal_facts_fact ON signal_facts(fact_id);
