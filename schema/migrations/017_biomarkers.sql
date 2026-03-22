-- Migration 017: Biomarker entity type
-- Seed biomarkers for metabolic/CV/renal scope

CREATE TABLE IF NOT EXISTS biomarkers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    abbreviation TEXT,
    unit TEXT,
    normal_range TEXT,
    clinical_significance TEXT,
    category TEXT NOT NULL DEFAULT 'efficacy',  -- efficacy, safety, surrogate, composite
    therapeutic_areas TEXT[],                    -- which TAs this biomarker is relevant to
    source_api TEXT NOT NULL DEFAULT 'seed',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Seed the 12 metabolic/CV/renal biomarkers
INSERT INTO biomarkers (name, abbreviation, unit, normal_range, clinical_significance, category, therapeutic_areas) VALUES
('Glycated Hemoglobin', 'HbA1c', '%', '4.0-5.6%', 'Primary measure of glycemic control in diabetes. Target <7% for most adults.', 'efficacy', ARRAY['Diabetes Mellitus, Type 2', 'Diabetes Mellitus, Type 1']),
('Body Weight', NULL, 'kg', NULL, 'Primary endpoint for obesity trials. Clinically meaningful: >=5% reduction.', 'efficacy', ARRAY['Obesity', 'Diabetes Mellitus, Type 2']),
('Fasting Plasma Glucose', 'FPG', 'mg/dL', '70-100 mg/dL', 'Measures overnight fasting glucose. Diabetes: >=126 mg/dL.', 'efficacy', ARRAY['Diabetes Mellitus, Type 2', 'Diabetes Mellitus, Type 1']),
('Body Mass Index', 'BMI', 'kg/m2', '18.5-24.9', 'Weight-for-height index. Obesity: >=30. Often used as inclusion criterion.', 'surrogate', ARRAY['Obesity']),
('Estimated Glomerular Filtration Rate', 'eGFR', 'mL/min/1.73m2', '>90', 'Kidney function marker. CKD stages: <60 (Stage 3), <30 (Stage 4), <15 (Stage 5).', 'efficacy', ARRAY['Renal Insufficiency, Chronic', 'Diabetic Nephropathies']),
('Urine Albumin-to-Creatinine Ratio', 'UACR', 'mg/g', '<30', 'Early kidney damage marker. Microalbuminuria: 30-300. Macroalbuminuria: >300.', 'efficacy', ARRAY['Diabetic Nephropathies', 'Renal Insufficiency, Chronic']),
('Major Adverse Cardiovascular Events', 'MACE', NULL, NULL, 'Composite endpoint: CV death + MI + stroke. Gold standard for CV outcome trials.', 'composite', ARRAY['Cardiovascular Diseases', 'Heart Failure']),
('N-terminal pro-B-type Natriuretic Peptide', 'NT-proBNP', 'pg/mL', '<125', 'Heart failure severity marker. Elevated in decompensated HF. Used for diagnosis and monitoring.', 'surrogate', ARRAY['Heart Failure']),
('Blood Pressure', 'BP', 'mmHg', '<120/80', 'Systolic and diastolic pressure. Hypertension: >=130/80 (ACC/AHA).', 'efficacy', ARRAY['Hypertension', 'Cardiovascular Diseases']),
('Waist Circumference', NULL, 'cm', 'M:<102, F:<88', 'Central adiposity marker. Correlates with visceral fat and cardiometabolic risk.', 'surrogate', ARRAY['Obesity', 'Metabolic Syndrome']),
('Left Ventricular Ejection Fraction', 'LVEF', '%', '55-70%', 'Cardiac pump function. HFrEF: <40%. HFmrEF: 40-49%. HFpEF: >=50%.', 'efficacy', ARRAY['Heart Failure', 'Heart Failure, Systolic', 'Heart Failure, Diastolic']),
('Alanine Aminotransferase', 'ALT', 'U/L', 'M:7-56, F:7-45', 'Liver enzyme. Elevated in MASH/NASH. Used to monitor hepatotoxicity.', 'safety', ARRAY['Obesity'])
ON CONFLICT (name) DO NOTHING;

-- Index for therapeutic area queries
CREATE INDEX IF NOT EXISTS idx_biomarkers_ta ON biomarkers USING GIN (therapeutic_areas);
