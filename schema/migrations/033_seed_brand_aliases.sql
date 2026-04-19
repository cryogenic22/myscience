-- Migration 033: Seed entity_aliases from drugs.brand_name
--
-- WS-1 of SPEC_015 (intelligence remediation). Production transcript showed
-- that "Show pipeline for Ozempic" returns no data, even though Ozempic IS
-- semaglutide. The entity_resolver had no path from brand to generic.
--
-- This migration backfills entity_aliases with one row per drug that has a
-- brand_name distinct from its generic_name. After this runs, the resolver's
-- alias_lookup strategy (which already exists) will find drugs by brand name.
--
-- Idempotent — uses ON CONFLICT against the unique index on
-- (entity_type, alias_text, source_type) defined in migration 003.

INSERT INTO entity_aliases (entity_type, entity_id, alias_text, source_type, confidence, verified)
SELECT
    'drug'                       AS entity_type,
    d.id                         AS entity_id,
    LOWER(TRIM(d.brand_name))    AS alias_text,
    'fda_orange_book'            AS source_type,
    1.0                          AS confidence,
    TRUE                         AS verified
FROM drugs d
WHERE d.brand_name IS NOT NULL
  AND TRIM(d.brand_name) <> ''
  AND LOWER(TRIM(d.brand_name)) <> LOWER(TRIM(d.generic_name))
ON CONFLICT (entity_type, alias_text, source_type) DO NOTHING;
