-- 095_drug_pricing_idempotent_history.sql
--
-- D2 (NADAC pricing revival) — make drug_pricing an idempotent price-HISTORY.
--
-- drug_pricing (022) had no uniqueness, so re-pulling a weekly NADAC snapshot
-- (the same ~28k NDCs, mostly unchanged) would DUPLICATE every row each week
-- instead of accumulating a clean time-series. NADAC publishes a weekly snapshot
-- where each row's Effective Date = when that NDC's price last changed; so the
-- natural history key is (ndc_code, price_type, effective_date, source_api):
--   * an unchanged NDC re-appears with the SAME effective_date -> ON CONFLICT skip
--   * a changed NDC appears with a NEW effective_date -> a new history row lands
-- giving a real per-NDC price-change history with no dupes, fully re-runnable.
--
-- NULLs (missing ndc/effective_date) are treated as distinct by Postgres, so the
-- rare unparseable row is simply never de-duplicated (not silently dropped).
-- drug_pricing is empty on prod today, so the unique index builds cleanly.

CREATE UNIQUE INDEX IF NOT EXISTS uq_drug_pricing_ndc_type_date_src
    ON drug_pricing (ndc_code, price_type, effective_date, source_api);
