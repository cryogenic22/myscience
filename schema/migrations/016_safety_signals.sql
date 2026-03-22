-- Migration 016: Safety signal scoring (disproportionality analysis)
-- Computes PRR and ROR from FAERS adverse_events data

-- Materialized view: safety_signals per drug × reaction
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_safety_signals AS
WITH
-- Count reports per drug × reaction
drug_reaction AS (
    SELECT
        drug_name,
        drug_id,
        reaction_meddra_pt AS reaction,
        COUNT(*) AS a  -- cases with drug AND reaction
    FROM adverse_events
    WHERE reaction_meddra_pt IS NOT NULL
      AND drug_name IS NOT NULL
      AND (record_status IS NULL OR record_status = 'active')
    GROUP BY drug_name, drug_id, reaction_meddra_pt
),
-- Total reports per drug
drug_totals AS (
    SELECT drug_name, COUNT(*) AS drug_total
    FROM adverse_events
    WHERE reaction_meddra_pt IS NOT NULL
      AND (record_status IS NULL OR record_status = 'active')
    GROUP BY drug_name
),
-- Total reports per reaction (across all drugs)
reaction_totals AS (
    SELECT reaction_meddra_pt AS reaction, COUNT(*) AS reaction_total
    FROM adverse_events
    WHERE reaction_meddra_pt IS NOT NULL
      AND (record_status IS NULL OR record_status = 'active')
    GROUP BY reaction_meddra_pt
),
-- Grand total
grand_total AS (
    SELECT COUNT(*) AS n
    FROM adverse_events
    WHERE reaction_meddra_pt IS NOT NULL
      AND (record_status IS NULL OR record_status = 'active')
)
SELECT
    dr.drug_name,
    dr.drug_id,
    dr.reaction,
    dr.a,                                          -- cases: drug + reaction
    (dt.drug_total - dr.a) AS b,                   -- drug without reaction
    (rt.reaction_total - dr.a) AS c,               -- reaction without drug
    (gt.n - dt.drug_total - rt.reaction_total + dr.a) AS d,  -- neither

    -- PRR = (a / (a+b)) / (c / (c+d))
    CASE
        WHEN (dr.a + (dt.drug_total - dr.a)) > 0
         AND (rt.reaction_total - dr.a + gt.n - dt.drug_total - rt.reaction_total + dr.a) > 0
         AND (rt.reaction_total - dr.a) > 0
        THEN (dr.a::float / NULLIF(dt.drug_total, 0)) /
             NULLIF((rt.reaction_total - dr.a)::float /
                    NULLIF(gt.n - dt.drug_total, 0), 0)
        ELSE NULL
    END AS prr,

    -- ROR = (a * d) / (b * c)
    CASE
        WHEN (dt.drug_total - dr.a) > 0
         AND (rt.reaction_total - dr.a) > 0
        THEN (dr.a::float * (gt.n - dt.drug_total - rt.reaction_total + dr.a)::float) /
             NULLIF((dt.drug_total - dr.a)::float * (rt.reaction_total - dr.a)::float, 0)
        ELSE NULL
    END AS ror,

    -- Lower bound 95% CI for ROR (Gart method: exp(ln(ROR) - 1.96 * SE))
    -- SE = sqrt(1/a + 1/b + 1/c + 1/d)
    CASE
        WHEN dr.a > 0 AND (dt.drug_total - dr.a) > 0
         AND (rt.reaction_total - dr.a) > 0
         AND (gt.n - dt.drug_total - rt.reaction_total + dr.a) > 0
        THEN EXP(
            LN(
                (dr.a::float * (gt.n - dt.drug_total - rt.reaction_total + dr.a)::float) /
                ((dt.drug_total - dr.a)::float * (rt.reaction_total - dr.a)::float)
            ) - 1.96 * SQRT(
                1.0 / dr.a + 1.0 / (dt.drug_total - dr.a) +
                1.0 / (rt.reaction_total - dr.a) +
                1.0 / (gt.n - dt.drug_total - rt.reaction_total + dr.a)
            )
        )
        ELSE NULL
    END AS ror_lower_ci,

    dt.drug_total,
    rt.reaction_total,
    gt.n AS total_reports

FROM drug_reaction dr
JOIN drug_totals dt ON dt.drug_name = dr.drug_name
JOIN reaction_totals rt ON rt.reaction = dr.reaction
CROSS JOIN grand_total gt
WHERE dr.a >= 2  -- Minimum 2 cases for signal detection
ORDER BY ror DESC NULLS LAST;

-- Index for fast drug-specific queries
CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_safety_drug_reaction
ON mv_safety_signals (drug_name, reaction);

CREATE INDEX IF NOT EXISTS idx_mv_safety_signals_significant
ON mv_safety_signals (drug_name)
WHERE ror_lower_ci > 1;
