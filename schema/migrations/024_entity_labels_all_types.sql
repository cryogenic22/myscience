-- Migration 024: Expand v_entity_labels to cover ALL entity types
-- Previously only covered drugs, companies, trials, literature, events, TAs, mechanisms.
-- Now adds: trial_location, investigator, trial_outcome, adverse_event, patent.

CREATE OR REPLACE VIEW v_entity_labels AS
SELECT id::text AS entity_id, 'drug' AS entity_type,
       COALESCE(brand_name || ' (' || generic_name || ')', generic_name) AS label
FROM drugs
UNION ALL
SELECT id::text, 'company', name FROM companies
UNION ALL
SELECT id::text, 'trial',
       COALESCE(official_title, 'Trial ' || id) FROM clinical_trials
UNION ALL
SELECT id::text, 'literature', title FROM pubmed_articles
UNION ALL
SELECT id::text, 'event', LEFT(description, 120) FROM market_events
UNION ALL
SELECT id::text, 'therapeutic_area', name FROM therapeutic_areas
UNION ALL
SELECT id::text, 'mechanism', name FROM mechanisms_of_action
UNION ALL
SELECT id::text, 'trial_location',
       COALESCE(facility_name, '') || CASE WHEN city IS NOT NULL THEN ', ' || city ELSE '' END
       || CASE WHEN country IS NOT NULL THEN ', ' || country ELSE '' END
FROM trial_locations
UNION ALL
SELECT id::text, 'investigator',
       COALESCE(name, '') || CASE WHEN affiliation IS NOT NULL THEN ' (' || LEFT(affiliation, 50) || ')' ELSE '' END
FROM investigators
UNION ALL
SELECT id::text, 'trial_outcome',
       COALESCE(outcome_type || ': ', '') || COALESCE(measure, '')
       || CASE WHEN time_frame IS NOT NULL THEN ' [' || LEFT(time_frame, 40) || ']' ELSE '' END
FROM trial_outcomes
UNION ALL
SELECT id::text, 'adverse_event',
       COALESCE(drug_name, '') || ' - ' || COALESCE(reaction, '') || ' (' || COALESCE(outcome, '') || ')'
FROM adverse_events
UNION ALL
SELECT id::text, 'patent',
       COALESCE(patent_number, '') || CASE WHEN patent_expiry_date IS NOT NULL THEN ' (exp ' || patent_expiry_date::text || ')' ELSE '' END
FROM patents;
