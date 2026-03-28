-- Migration 027: company_financials table
-- Stores structured XBRL financial data from SEC EDGAR (revenue, R&D, profit, etc.)

CREATE TABLE IF NOT EXISTS company_financials (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID REFERENCES companies(id),
    cik TEXT NOT NULL,
    fiscal_year INT NOT NULL,
    fiscal_period TEXT NOT NULL DEFAULT 'FY',  -- FY, Q1, Q2, Q3, Q4
    metric_name TEXT NOT NULL,  -- 'revenue', 'rd_expense', 'profit', 'cost_of_sales', 'total_assets', 'cash', 'employees'
    metric_value FLOAT,
    currency TEXT DEFAULT 'USD',
    filed_date DATE,
    source_api TEXT DEFAULT 'sec_edgar',
    retrieved_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(cik, fiscal_year, fiscal_period, metric_name)
);

CREATE INDEX IF NOT EXISTS idx_financials_company ON company_financials(company_id);
CREATE INDEX IF NOT EXISTS idx_financials_cik ON company_financials(cik);
CREATE INDEX IF NOT EXISTS idx_financials_metric ON company_financials(metric_name, fiscal_year DESC);
