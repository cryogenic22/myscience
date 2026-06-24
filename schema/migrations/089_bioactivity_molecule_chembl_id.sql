-- 089_bioactivity_molecule_chembl_id.sql
--
-- RESTORED FILE. This migration is recorded as APPLIED in prod's
-- schema_migrations, but its file had gone missing from disk — so a fresh
-- `python migrate.py` would NOT create bioactivities.molecule_chembl_id, and the
-- store INSERT/UPDATE that reference it would crash on a fresh database (schema
-- drift between prod and disk). Restored here, idempotent (IF NOT EXISTS), to
-- exactly match the live prod shape: a nullable TEXT column + a partial index.
--
-- molecule_chembl_id = the MOLECULE's ChEMBL id (e.g. CHEMBL1487), distinct from
-- chembl_activity_id (the assay record) and target_chembl_id (the protein). It
-- is the molecule link for bioactivity rows whose drug_id never resolved.

ALTER TABLE bioactivities
    ADD COLUMN IF NOT EXISTS molecule_chembl_id TEXT;

CREATE INDEX IF NOT EXISTS ix_bioactivity_molecule_chembl
    ON bioactivities (molecule_chembl_id)
    WHERE molecule_chembl_id IS NOT NULL;
