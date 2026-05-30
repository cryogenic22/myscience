-- Migration 067: fact_class column on the facts ledger (Z1)
--
-- The v7 design canon defines four fact classes with differential
-- agentic-autonomy ceilings:
--   reference  — peer-reviewed scientific truth (L4-safe)
--   corporate  — filed company facts (L3-safe)
--   signal     — observed market behaviour, triangulation required (L2)
--   inferred   — analyst conclusion (L1/L2 only, never autonomous)
--
-- Today the ledger has no fact_class column, so ceilings can only be
-- enforced by convention. This migration adds the column with a CHECK
-- constraint over the four valid values. Defaults to 'corporate' for the
-- in-place backfill (the safest mid-ceiling class); the backfill script
-- (scripts/backfill_fact_class.py) will refine by predicate.

BEGIN;

ALTER TABLE facts
    ADD COLUMN IF NOT EXISTS fact_class TEXT NOT NULL DEFAULT 'corporate'
        CHECK (fact_class IN ('reference','corporate','signal','inferred'));

CREATE INDEX IF NOT EXISTS idx_facts_class
    ON facts (fact_class, valid_from DESC);

COMMENT ON COLUMN facts.fact_class IS
    'One of {reference,corporate,signal,inferred}. Carries the agentic '
    'ceiling: reference→L4, corporate→L3, signal→L2, inferred→L1/L2 only. '
    'Z1.';

COMMIT;
