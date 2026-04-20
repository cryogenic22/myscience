-- Migration 035: drugs.canonical_molecule_id (WS-1B)
--
-- Lead transcript review (lead_notes_4_dev.md, 19 Apr 2026) flagged that
-- "Show pipeline for Ozempic" resolved to "Semaglutide Auto-Injector"
-- (a formulation row) rather than to the canonical "Semaglutide" molecule.
--
-- This migration adds a self-link: formulation rows point to their canonical
-- molecule row via canonical_molecule_id. Canonical molecule rows have
-- canonical_molecule_id IS NULL.
--
-- Backfill of existing duplicate drug rows is a SEPARATE data task (TBD).
-- This migration only adds the column + index so:
--   1. The canonicalizer can ORDER BY canonical_molecule_id NULLS FIRST
--      to prefer molecule rows when multiple drugs match a query
--   2. Future ingestion can populate the field
--   3. A follow-up backfill script can identify clusters of similar drug
--      names (e.g. "Semaglutide", "Semaglutide Injection", "Semaglutide
--      Auto-Injector") and assign canonical_molecule_id

ALTER TABLE drugs
    ADD COLUMN IF NOT EXISTS canonical_molecule_id UUID REFERENCES drugs(id);

-- Index supports both lookups:
--   (a) "find all formulations of molecule X" — WHERE canonical_molecule_id = X
--   (b) "is this row a canonical molecule?" — WHERE canonical_molecule_id IS NULL
CREATE INDEX IF NOT EXISTS idx_drugs_canonical_molecule
    ON drugs (canonical_molecule_id)
    WHERE canonical_molecule_id IS NOT NULL;
