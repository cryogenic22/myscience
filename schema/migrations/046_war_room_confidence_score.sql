-- Migration 046: numeric confidence score on war room reactions (SPEC-021 PD review)
--
-- The PD review asked for numeric confidence (0.0-1.0) rather than just
-- categorical (high/medium/low). The categorical label is now derived from
-- the score at API serialization (>=0.66 = high, >=0.33 = medium, else low).
--
-- This makes Phase D's prediction-error computation mathematical rather
-- than categorical — essential for meaningful weight adjustment.
--
-- Also adds evidence_validated boolean: true if all cited evidence IDs
-- resolved against the live DB; false if any were stripped as hallucinated.
--
-- Migration is additive (ADD COLUMN IF NOT EXISTS). Idempotent.

ALTER TABLE war_room_reactions
    ADD COLUMN IF NOT EXISTS confidence_score REAL
        CHECK (confidence_score IS NULL
               OR confidence_score BETWEEN 0.0 AND 1.0);

ALTER TABLE war_room_reactions
    ADD COLUMN IF NOT EXISTS evidence_validated BOOLEAN
        NOT NULL DEFAULT TRUE;

ALTER TABLE war_room_reactions
    ADD COLUMN IF NOT EXISTS stripped_citations TEXT[]
        NOT NULL DEFAULT '{}';

COMMENT ON COLUMN war_room_reactions.confidence_score IS
    'PD review strengthening: numeric confidence (0.0-1.0). Categorical '
    '`confidence` column is derived at serialization time. Used by Phase D '
    'prediction-error math for signal weight recalibration.';

COMMENT ON COLUMN war_room_reactions.evidence_validated IS
    'True if every cited evidence ID resolved against the live DB at '
    'persistence time. False if at least one citation was stripped as '
    'hallucinated.';

COMMENT ON COLUMN war_room_reactions.stripped_citations IS
    'Citations the LLM produced that did not resolve in the DB. Stored '
    'so the UI can show them as "1 citation removed (drug_id-not-found)" '
    'and so post-mortems can audit hallucination rate over time.';
