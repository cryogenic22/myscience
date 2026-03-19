-- 005_moa_scope_embedding.sql
-- Add scope_note_embedding vector column to mechanisms_of_action.
-- The store code treats both ontology tables identically, so they need
-- matching columns.

ALTER TABLE mechanisms_of_action
    ADD COLUMN IF NOT EXISTS scope_note_embedding VECTOR(1536);
