-- 099_source_onboarding_contract.sql
--
-- Connector Press Phase 1 — persist the onboarding *contract* so a registered
-- source is RUNNABLE + governed, not just lifecycle metadata. Today
-- source_onboarding (096) stores only owner/contact/status; the Connect wizard's
-- connector config + field mappings + trust tier + must-capture + license + the
-- target record_type + cadence have nowhere to go, so "Register source" is a
-- preview-only stub (datahubOnboarding.ts) and the generic Rest/Csv/Rss
-- connectors are never instantiated from stored config. (See COORDINATION ASK A1.)
--
-- These columns are the DB projection of a connectors/specs/<id>.yaml spec: the
-- scheduler rebuilds a ConnectorSpec from (sources.display_name, sources.connector_type,
-- record_type, config) and runs it through the universal IntegrationPipeline.
--
-- Additive only — every column is nullable or defaulted, so existing
-- source_onboarding rows stay valid and no read path changes.

ALTER TABLE source_onboarding
    -- the connector config block (RestConfig/CsvConfig/RssConfig-shaped: url,
    -- external_id_field, records_path, field_map, identifiers_map, auth, …).
    -- Secrets are NOT stored here (supplied out-of-band) — see SCHEMA.md.
    ADD COLUMN IF NOT EXISTS config         JSONB  NOT NULL DEFAULT '{}'::jsonb,
    -- the wizard's contract field mappings [{source_field, target_field}, …]
    ADD COLUMN IF NOT EXISTS field_mappings JSONB  NOT NULL DEFAULT '[]'::jsonb,
    -- which existing core entity the rows map to (a RecordType: drug/company/…)
    ADD COLUMN IF NOT EXISTS record_type    TEXT,
    -- data-contract trust tier 1|2|3 (distinct from sources.tier registry tier)
    ADD COLUMN IF NOT EXISTS trust_tier     INTEGER
                            CHECK (trust_tier IS NULL OR trust_tier BETWEEN 1 AND 3),
    -- fields that must be present or the row is rejected (the contract)
    ADD COLUMN IF NOT EXISTS must_capture   TEXT[] NOT NULL DEFAULT '{}',
    -- data licence string
    ADD COLUMN IF NOT EXISTS license        TEXT,
    -- APScheduler CronTrigger kwargs, e.g. {"hour": "*/12"}; NULL ⇒ a default
    ADD COLUMN IF NOT EXISTS cadence        JSONB;
