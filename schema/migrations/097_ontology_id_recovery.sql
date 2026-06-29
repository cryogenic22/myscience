-- 097_ontology_id_recovery.sql
--
-- Recover the #1 *active* dead-letter-queue bleed: open_targets target-disease
-- associations (3,121 'pending' failed_records, growing daily until PR #300).
--
-- The open_targets connector emits diseases identified by an EFO/MONDO ontology
-- id (e.g. 'EFO_0001073', 'MONDO_0005148'), NOT a MeSH id. `therapeutic_areas`
-- (and its sibling `mechanisms_of_action`) only had `mesh_id` as a stable
-- ontology key, so those rows could not be deduped on their real identifier:
-- a re-run would re-INSERT the same disease by name and crash the UNIQUE name
-- constraint → back into the DLQ.
--
-- This adds a generic `ontology_id TEXT` (the namespaced source ontology id) to
-- both ontology tables, with a PARTIAL-UNIQUE index so the column is the stable
-- dedup key while every existing (NULL) row stays valid. Additive + nullable +
-- idempotent — no existing row or column is altered destructively. `mesh_id`
-- stays reserved for MeSH so its namespace is not muddied with EFO/MONDO ids.

ALTER TABLE therapeutic_areas
    ADD COLUMN IF NOT EXISTS ontology_id TEXT;

ALTER TABLE mechanisms_of_action
    ADD COLUMN IF NOT EXISTS ontology_id TEXT;

-- Partial-unique: NULLs are unconstrained (existing rows untouched), but any
-- non-NULL ontology_id is unique → robust idempotent upsert keyed on it.
CREATE UNIQUE INDEX IF NOT EXISTS uix_therapeutic_areas_ontology_id
    ON therapeutic_areas(ontology_id)
    WHERE ontology_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uix_mechanisms_of_action_ontology_id
    ON mechanisms_of_action(ontology_id)
    WHERE ontology_id IS NOT NULL;
