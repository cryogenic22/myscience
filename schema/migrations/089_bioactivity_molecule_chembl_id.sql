-- Migration 089: persist the molecule ChEMBL id on bioactivity rows.
--
-- Why: bioactivities only ever stored ``chembl_activity_id`` (the assay-row id),
-- never the *molecule* identifier. The D3 ingest fix links drug_id at store time
-- via the resolver, but rows ingested before that fix (and any re-ingest gap)
-- could ONLY be relinked by re-hitting the ChEMBL API — there was no pure-DB key
-- to map a compound back to the drug spine. Persisting molecule_chembl_id makes
-- the linkage re-runnable offline:
--     bioactivities.molecule_chembl_id  ->  drugs.chembl_id  ->  drug_id
-- (drugs.chembl_id exists + is uniquely indexed, migration 038.)
--
-- Additive + reversible: a nullable column, no data loss. scripts/relink_bioactivities.py
-- consumes it to fill NULL drug_id additively (counting, never dropping, the
-- off-spine residue).

ALTER TABLE bioactivities ADD COLUMN IF NOT EXISTS molecule_chembl_id TEXT;

COMMENT ON COLUMN bioactivities.molecule_chembl_id IS
    'ChEMBL molecule id of the assayed compound (e.g. CHEMBL1201247). Pure-DB '
    'join key to drugs.chembl_id for offline drug_id relink. Populated by the '
    'ChEMBL connector store path; backfilled by scripts/relink_bioactivities.py.';

CREATE INDEX IF NOT EXISTS ix_bioactivity_molecule_chembl
    ON bioactivities(molecule_chembl_id)
    WHERE molecule_chembl_id IS NOT NULL;
