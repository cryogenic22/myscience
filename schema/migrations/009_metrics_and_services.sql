-- 009_metrics_and_services.sql
-- Materialized views for pharma KPIs, graph traversal function, entity label view.
-- Supports the services layer: PharmaMetrics, HybridSearch, GraphTraversal, QueryEngine.

-- ============================================================
-- 1. ENTITY LABEL VIEW (used by graph, search, query engine)
-- ============================================================

CREATE OR REPLACE VIEW v_entity_labels AS
SELECT id::text AS entity_id, 'drug' AS entity_type,
       COALESCE(brand_name || ' (' || generic_name || ')', generic_name) AS label
FROM drugs
UNION ALL
SELECT id::text, 'company', name FROM companies
UNION ALL
SELECT id::text, 'trial', COALESCE(official_title, 'Trial ' || id) FROM clinical_trials
UNION ALL
SELECT id::text, 'literature', title FROM pubmed_articles
UNION ALL
SELECT id::text, 'event', LEFT(description, 120) FROM market_events
UNION ALL
SELECT id::text, 'therapeutic_area', name FROM therapeutic_areas
UNION ALL
SELECT id::text, 'mechanism', name FROM mechanisms_of_action;

-- ============================================================
-- 2. MATERIALIZED VIEWS: PHARMA METRICS
-- ============================================================

-- 2a. Drug Pipeline Strength
-- Phase weighting: P1=1, P1/P2=1.5, P2=2, P2/P3=3, P3=4, P4=1, Early=0.5, N/A=0.25
-- Only counts active trials (not COMPLETED, TERMINATED, WITHDRAWN, SUSPENDED)

CREATE MATERIALIZED VIEW mv_drug_pipeline_strength AS
SELECT
    d.id AS drug_id,
    d.generic_name AS drug_name,
    d.brand_name,
    ta.name AS therapeutic_area,
    moa.name AS mechanism,
    COUNT(*) FILTER (WHERE ct.phase IN ('Phase 1', 'EARLY_Phase 1')) AS p1_count,
    COUNT(*) FILTER (WHERE ct.phase IN ('Phase 2', 'Phase 1, Phase 2')) AS p2_count,
    COUNT(*) FILTER (WHERE ct.phase IN ('Phase 3', 'Phase 2, Phase 3')) AS p3_count,
    COUNT(*) FILTER (WHERE ct.phase = 'Phase 4') AS p4_count,
    COUNT(*) AS total_trials,
    COUNT(*) FILTER (WHERE ct.status IN ('RECRUITING', 'NOT_YET_RECRUITING',
                                          'ACTIVE_NOT_RECRUITING', 'ENROLLING_BY_INVITATION'))
        AS active_trials,
    ROUND(SUM(
        CASE
            WHEN ct.phase = 'Phase 1' THEN 1.0
            WHEN ct.phase = 'Phase 1, Phase 2' THEN 1.5
            WHEN ct.phase = 'Phase 2' THEN 2.0
            WHEN ct.phase = 'Phase 2, Phase 3' THEN 3.0
            WHEN ct.phase = 'Phase 3' THEN 4.0
            WHEN ct.phase = 'Phase 4' THEN 1.0
            WHEN ct.phase = 'EARLY_Phase 1' THEN 0.5
            ELSE 0.25
        END
    )::numeric, 1) AS pipeline_score,
    ROUND(SUM(
        CASE WHEN ct.status IN ('RECRUITING', 'NOT_YET_RECRUITING',
                                'ACTIVE_NOT_RECRUITING', 'ENROLLING_BY_INVITATION')
        THEN
            CASE
                WHEN ct.phase = 'Phase 1' THEN 1.0
                WHEN ct.phase = 'Phase 1, Phase 2' THEN 1.5
                WHEN ct.phase = 'Phase 2' THEN 2.0
                WHEN ct.phase = 'Phase 2, Phase 3' THEN 3.0
                WHEN ct.phase = 'Phase 3' THEN 4.0
                WHEN ct.phase = 'Phase 4' THEN 1.0
                WHEN ct.phase = 'EARLY_Phase 1' THEN 0.5
                ELSE 0.25
            END
        ELSE 0 END
    )::numeric, 1) AS active_pipeline_score,
    MAX(ct.start_date) AS last_trial_start
FROM drugs d
JOIN clinical_trials ct ON ct.drug_id = d.id
LEFT JOIN therapeutic_areas ta ON d.therapeutic_area_id = ta.id
LEFT JOIN mechanisms_of_action moa ON d.mechanism_id = moa.id
GROUP BY d.id, d.generic_name, d.brand_name, ta.name, moa.name;

CREATE UNIQUE INDEX idx_mv_pipeline_drug ON mv_drug_pipeline_strength(drug_id);
CREATE INDEX idx_mv_pipeline_ta ON mv_drug_pipeline_strength(therapeutic_area);
CREATE INDEX idx_mv_pipeline_score ON mv_drug_pipeline_strength(pipeline_score DESC);


-- 2b. Trial Success Rate
-- Per drug: completed, terminated, withdrawn, suspended counts + success rate

CREATE MATERIALIZED VIEW mv_trial_success_rate AS
WITH drug_stats AS (
    SELECT
        ct.drug_id,
        COUNT(*) AS total,
        COUNT(*) FILTER (WHERE ct.status = 'COMPLETED') AS completed,
        COUNT(*) FILTER (WHERE ct.status = 'TERMINATED') AS terminated,
        COUNT(*) FILTER (WHERE ct.status = 'WITHDRAWN') AS withdrawn,
        COUNT(*) FILTER (WHERE ct.status = 'SUSPENDED') AS suspended,
        COUNT(*) FILTER (WHERE ct.status IN ('RECRUITING', 'NOT_YET_RECRUITING',
                                             'ACTIVE_NOT_RECRUITING', 'ENROLLING_BY_INVITATION'))
            AS active
    FROM clinical_trials ct
    WHERE ct.drug_id IS NOT NULL
    GROUP BY ct.drug_id
),
ta_avg AS (
    SELECT
        d.therapeutic_area_id,
        ROUND(AVG(
            CASE WHEN ds.completed + ds.terminated + ds.withdrawn > 0
                 THEN ds.completed::float / (ds.completed + ds.terminated + ds.withdrawn)
                 ELSE NULL END
        )::numeric, 3) AS ta_avg_success_rate
    FROM drug_stats ds
    JOIN drugs d ON d.id = ds.drug_id
    WHERE d.therapeutic_area_id IS NOT NULL
    GROUP BY d.therapeutic_area_id
)
SELECT
    d.id AS drug_id,
    d.generic_name AS drug_name,
    ta.name AS therapeutic_area,
    ds.total,
    ds.completed,
    ds.terminated,
    ds.withdrawn,
    ds.suspended,
    ds.active,
    CASE WHEN ds.completed + ds.terminated + ds.withdrawn > 0
         THEN ROUND(ds.completed::numeric / (ds.completed + ds.terminated + ds.withdrawn), 3)
         ELSE NULL
    END AS success_rate,
    taa.ta_avg_success_rate
FROM drug_stats ds
JOIN drugs d ON d.id = ds.drug_id
LEFT JOIN therapeutic_areas ta ON d.therapeutic_area_id = ta.id
LEFT JOIN ta_avg taa ON taa.therapeutic_area_id = d.therapeutic_area_id;

CREATE UNIQUE INDEX idx_mv_success_drug ON mv_trial_success_rate(drug_id);
CREATE INDEX idx_mv_success_ta ON mv_trial_success_rate(therapeutic_area);
CREATE INDEX idx_mv_success_rate ON mv_trial_success_rate(success_rate DESC NULLS LAST);


-- 2c. Evidence Density
-- PubMed articles per drug, recency-weighted (last 2yr=1.0, 2-5yr=0.5, 5+yr=0.25)

CREATE MATERIALIZED VIEW mv_evidence_density AS
SELECT
    d.id AS drug_id,
    d.generic_name AS drug_name,
    COUNT(pa.id) AS total_articles,
    COUNT(pa.id) FILTER (WHERE pa.publication_date >= CURRENT_DATE - INTERVAL '2 years') AS recent_count,
    ROUND(
        SUM(
            CASE
                WHEN pa.publication_date >= CURRENT_DATE - INTERVAL '2 years' THEN 1.0
                WHEN pa.publication_date >= CURRENT_DATE - INTERVAL '5 years' THEN 0.5
                ELSE 0.25
            END
        )::numeric, 1
    ) AS weighted_score,
    MIN(pa.publication_date) AS oldest_date,
    MAX(pa.publication_date) AS newest_date
FROM drugs d
JOIN pubmed_articles pa ON pa.drug_id = d.id
GROUP BY d.id, d.generic_name
HAVING COUNT(pa.id) >= 1;

CREATE UNIQUE INDEX idx_mv_evidence_drug ON mv_evidence_density(drug_id);
CREATE INDEX idx_mv_evidence_score ON mv_evidence_density(weighted_score DESC);


-- 2d. Competitive Landscape
-- Drugs per mechanism per TA with trial pipeline depth

CREATE MATERIALIZED VIEW mv_competitive_landscape AS
SELECT
    moa.id AS mechanism_id,
    moa.name AS mechanism_name,
    ta.id AS therapeutic_area_id,
    ta.name AS therapeutic_area,
    COUNT(DISTINCT d.id) AS drug_count,
    COUNT(DISTINCT ct.id) AS trial_count,
    COUNT(DISTINCT ct.id) FILTER (WHERE ct.status IN ('RECRUITING', 'NOT_YET_RECRUITING',
                                                       'ACTIVE_NOT_RECRUITING')) AS active_trial_count,
    (SELECT d2.generic_name
     FROM drugs d2
     JOIN clinical_trials ct2 ON ct2.drug_id = d2.id
     WHERE d2.mechanism_id = moa.id
       AND (d2.therapeutic_area_id = ta.id OR ta.id IS NULL)
     GROUP BY d2.generic_name
     ORDER BY COUNT(ct2.id) DESC LIMIT 1) AS top_drug,
    ROUND(SUM(
        CASE
            WHEN ct.phase = 'Phase 3' THEN 4.0
            WHEN ct.phase = 'Phase 2' THEN 2.0
            WHEN ct.phase = 'Phase 1' THEN 1.0
            WHEN ct.phase = 'Phase 4' THEN 1.0
            ELSE 0.25
        END
    )::numeric, 1) AS total_pipeline_score
FROM drugs d
JOIN mechanisms_of_action moa ON d.mechanism_id = moa.id
LEFT JOIN therapeutic_areas ta ON d.therapeutic_area_id = ta.id
LEFT JOIN clinical_trials ct ON ct.drug_id = d.id
GROUP BY moa.id, moa.name, ta.id, ta.name;

CREATE UNIQUE INDEX idx_mv_competitive_pk ON mv_competitive_landscape(mechanism_id, therapeutic_area_id);
CREATE INDEX idx_mv_competitive_mech ON mv_competitive_landscape(mechanism_id);
CREATE INDEX idx_mv_competitive_ta ON mv_competitive_landscape(therapeutic_area_id);


-- 2e. Company Portfolio
-- Uses entity_links (SPONSORS) since drugs.company_id is sparsely populated

CREATE MATERIALIZED VIEW mv_company_portfolio AS
WITH company_drugs AS (
    -- drugs via OWNS link or drugs.company_id FK
    SELECT c.id AS company_id, d.id AS drug_id
    FROM companies c
    JOIN entity_links el ON el.source_entity_id = c.id::text
        AND el.link_type = 'OWNS'
    JOIN drugs d ON d.id::text = el.target_entity_id
    UNION
    SELECT d.company_id, d.id FROM drugs d WHERE d.company_id IS NOT NULL
),
company_trials AS (
    -- trials via SPONSORS link
    SELECT el.source_entity_id::uuid AS company_id, el.target_entity_id AS trial_id
    FROM entity_links el
    WHERE el.link_type = 'SPONSORS'
),
company_articles AS (
    -- articles for company's drugs
    SELECT cd.company_id, pa.id AS article_id
    FROM company_drugs cd
    JOIN pubmed_articles pa ON pa.drug_id = cd.drug_id
)
SELECT
    c.id AS company_id,
    c.name AS company_name,
    c.ticker,
    c.country,
    COALESCE(cd_count.drug_count, 0) AS drug_count,
    COALESCE(ct_count.trial_count, 0) AS trial_count,
    COALESCE(ct_count.active_trial_count, 0) AS active_trial_count,
    COALESCE(ca_count.article_count, 0) AS article_count,
    COALESCE(ta_count.ta_count, 0) AS ta_count,
    COALESCE(ps.pipeline_score_total, 0) AS pipeline_score_total
FROM companies c
LEFT JOIN (
    SELECT company_id, COUNT(DISTINCT drug_id) AS drug_count
    FROM company_drugs GROUP BY company_id
) cd_count ON cd_count.company_id = c.id
LEFT JOIN (
    SELECT company_id,
           COUNT(DISTINCT trial_id) AS trial_count,
           COUNT(DISTINCT trial_id) FILTER (
               WHERE trial_id IN (
                   SELECT id FROM clinical_trials
                   WHERE status IN ('RECRUITING','NOT_YET_RECRUITING','ACTIVE_NOT_RECRUITING')
               )
           ) AS active_trial_count
    FROM company_trials GROUP BY company_id
) ct_count ON ct_count.company_id = c.id
LEFT JOIN (
    SELECT company_id, COUNT(DISTINCT article_id) AS article_count
    FROM company_articles GROUP BY company_id
) ca_count ON ca_count.company_id = c.id
LEFT JOIN (
    SELECT cd.company_id, COUNT(DISTINCT d.therapeutic_area_id) AS ta_count
    FROM company_drugs cd
    JOIN drugs d ON d.id = cd.drug_id
    WHERE d.therapeutic_area_id IS NOT NULL
    GROUP BY cd.company_id
) ta_count ON ta_count.company_id = c.id
LEFT JOIN (
    SELECT cd.company_id,
           ROUND(SUM(ps.pipeline_score)::numeric, 1) AS pipeline_score_total
    FROM company_drugs cd
    JOIN mv_drug_pipeline_strength ps ON ps.drug_id = cd.drug_id
    GROUP BY cd.company_id
) ps ON ps.company_id = c.id;

CREATE UNIQUE INDEX idx_mv_portfolio_company ON mv_company_portfolio(company_id);
CREATE INDEX idx_mv_portfolio_score ON mv_company_portfolio(pipeline_score_total DESC);


-- ============================================================
-- 3. GRAPH TRAVERSAL FUNCTION
-- ============================================================

CREATE OR REPLACE FUNCTION traverse_graph(
    p_start_id TEXT,
    p_max_hops INT DEFAULT 2,
    p_link_types TEXT[] DEFAULT NULL,
    p_max_nodes INT DEFAULT 100
)
RETURNS TABLE(
    source_id TEXT,
    source_type TEXT,
    target_id TEXT,
    target_type TEXT,
    link_type TEXT,
    confidence FLOAT,
    link_via TEXT,
    depth INT
) AS $$
BEGIN
    RETURN QUERY
    WITH RECURSIVE graph_bfs AS (
        -- Seed: edges touching start node (both directions)
        SELECT
            el.source_entity_id AS src_id,
            el.source_entity_type AS src_type,
            el.target_entity_id AS tgt_id,
            el.target_entity_type AS tgt_type,
            el.link_type AS ltype,
            el.confidence AS conf,
            el.link_via AS via,
            1 AS d,
            ARRAY[p_start_id, CASE
                WHEN el.source_entity_id = p_start_id THEN el.target_entity_id
                ELSE el.source_entity_id
            END] AS visited
        FROM entity_links el
        WHERE (el.source_entity_id = p_start_id OR el.target_entity_id = p_start_id)
          AND (p_link_types IS NULL OR el.link_type = ANY(p_link_types))

        UNION ALL

        -- Recursive: expand frontier
        SELECT
            el.source_entity_id,
            el.source_entity_type,
            el.target_entity_id,
            el.target_entity_type,
            el.link_type,
            el.confidence,
            el.link_via,
            g.d + 1,
            g.visited || CASE
                WHEN el.source_entity_id = ANY(g.visited) THEN el.target_entity_id
                ELSE el.source_entity_id
            END
        FROM entity_links el
        JOIN graph_bfs g ON (
            (el.source_entity_id = g.tgt_id AND NOT el.target_entity_id = ANY(g.visited))
            OR
            (el.target_entity_id = g.tgt_id AND NOT el.source_entity_id = ANY(g.visited))
            OR
            (el.source_entity_id = g.src_id AND g.d = 1 AND NOT el.target_entity_id = ANY(g.visited))
        )
        WHERE g.d < p_max_hops
          AND (p_link_types IS NULL OR el.link_type = ANY(p_link_types))
    )
    SELECT DISTINCT ON (g2.src_id, g2.tgt_id, g2.ltype)
        g2.src_id, g2.src_type, g2.tgt_id, g2.tgt_type,
        g2.ltype, g2.conf, g2.via, g2.d
    FROM graph_bfs g2
    ORDER BY g2.src_id, g2.tgt_id, g2.ltype, g2.d
    LIMIT p_max_nodes;
END;
$$ LANGUAGE plpgsql STABLE;


-- ============================================================
-- 4. RECORD MIGRATION
-- ============================================================

INSERT INTO etl_runs (id, source_name, api_endpoint, query_params, status, records_processed, started_at, completed_at)
VALUES (gen_random_uuid(), 'migration_009', 'schema/migrations/009_metrics_and_services.sql',
        '{"description": "Materialized views, graph function, entity labels"}'::jsonb,
        'SUCCESS', 0, NOW(), NOW());
