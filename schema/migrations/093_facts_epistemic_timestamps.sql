-- 093_facts_epistemic_timestamps.sql
--
-- Loop 2b (Helix temporal / decision-memory) — EPISTEMIC timestamps + contradiction links.
--
-- The facts ledger is operationally bitemporal (valid_from/valid_to = world
-- validity; asserted_at = when we wrote the row). But asserted_at conflates
-- three different "times" that fair hindsight needs kept apart:
--   * observed_at      — when the SOURCE observed/reported it in the world
--   * detected_at      — when OUR system ingested it
--   * known_to_team_at — when it became available to the decision-makers
-- Without the split, "what did we KNOW as of date D?" is unanswerable: facts_as_of
-- filters world-validity only, so a fact detected AFTER a decision still appears
-- "as of" the decision date — blaming the team for knowledge that did not exist
-- yet (the Helix Output-Quality Benchmark OQ6 / fair-hindsight gate).
--
-- contradicts_fact_ids makes refutation a first-class link (populated by
-- contradiction detection) instead of silently superseding.
--
-- All additive + nullable (contradicts defaults to empty), so every existing
-- caller is unaffected. detected_at is backfilled from asserted_at (the best
-- estimate of "when we learned it" for historical rows).

ALTER TABLE facts ADD COLUMN IF NOT EXISTS observed_at          TIMESTAMPTZ;
ALTER TABLE facts ADD COLUMN IF NOT EXISTS detected_at          TIMESTAMPTZ;
ALTER TABLE facts ADD COLUMN IF NOT EXISTS known_to_team_at     TIMESTAMPTZ;
ALTER TABLE facts ADD COLUMN IF NOT EXISTS contradicts_fact_ids UUID[] NOT NULL DEFAULT '{}';

-- Backfill: for historical rows, when-we-learned-it ≈ asserted_at.
UPDATE facts SET detected_at = asserted_at WHERE detected_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_facts_detected_at ON facts (detected_at);
