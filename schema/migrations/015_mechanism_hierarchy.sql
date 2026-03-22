-- Migration 015: Mechanism-of-action hierarchy
-- Adds parent_mechanism_id for tree queries and mechanism_class for grouping

-- Add parent mechanism FK (self-referencing)
ALTER TABLE mechanisms_of_action
ADD COLUMN IF NOT EXISTS parent_mechanism_id UUID REFERENCES mechanisms_of_action(id);

-- Add mechanism class for pharma-relevant grouping
ALTER TABLE mechanisms_of_action
ADD COLUMN IF NOT EXISTS mechanism_class TEXT;

-- Create index for hierarchy traversal
CREATE INDEX IF NOT EXISTS idx_moa_parent ON mechanisms_of_action(parent_mechanism_id)
WHERE parent_mechanism_id IS NOT NULL;

-- Create index for class grouping
CREATE INDEX IF NOT EXISTS idx_moa_class ON mechanisms_of_action(mechanism_class)
WHERE mechanism_class IS NOT NULL;

-- Populate mechanism_class based on pharma-relevant groupings
UPDATE mechanisms_of_action SET mechanism_class = CASE
    WHEN name IN ('Glucagon-Like Peptide-1 Receptor Agonists', 'Incretins',
                  'Glucagon-Like Peptide-1 Receptor', 'Glucagon-Like Peptide 1',
                  'Gastric Inhibitory Polypeptide')
        THEN 'incretin_based'
    WHEN name = 'Dipeptidyl-Peptidase IV Inhibitors'
        THEN 'dpp4_inhibitor'
    WHEN name = 'Sodium-Glucose Transporter 2 Inhibitors'
        THEN 'sglt2_inhibitor'
    WHEN name IN ('Insulin', 'Hypoglycemic Agents')
        THEN 'insulin_glucose'
    WHEN name IN ('Metformin', 'Thiazolidinediones')
        THEN 'insulin_sensitizer'
    WHEN name = 'Appetite Depressants'
        THEN 'appetite_suppressant'
    WHEN name IN ('Angiotensin-Converting Enzyme Inhibitors',
                  'Angiotensin II Type 1 Receptor Blockers')
        THEN 'raas_inhibitor'
    WHEN name IN ('Adrenergic beta-Antagonists', 'Calcium Channel Blockers',
                  'Vasodilator Agents')
        THEN 'cardiovascular_other'
    WHEN name IN ('Mineralocorticoid Receptor Antagonists', 'Diuretics')
        THEN 'mra_diuretic'
    WHEN name = 'Phosphodiesterase Inhibitors'
        THEN 'pde_inhibitor'
    ELSE 'other'
END;

-- Set parent_mechanism_id for incretin subtypes → GLP-1 RA parent
UPDATE mechanisms_of_action child
SET parent_mechanism_id = parent.id
FROM mechanisms_of_action parent
WHERE parent.name = 'Glucagon-Like Peptide-1 Receptor Agonists'
  AND child.name IN ('Glucagon-Like Peptide-1 Receptor', 'Glucagon-Like Peptide 1',
                     'Gastric Inhibitory Polypeptide', 'Incretins');

-- Set GLP-1 RA parent → Hypoglycemic Agents
UPDATE mechanisms_of_action child
SET parent_mechanism_id = parent.id
FROM mechanisms_of_action parent
WHERE parent.name = 'Hypoglycemic Agents'
  AND child.name = 'Glucagon-Like Peptide-1 Receptor Agonists';

-- Set DPP-4i, SGLT2i parent → Hypoglycemic Agents
UPDATE mechanisms_of_action child
SET parent_mechanism_id = parent.id
FROM mechanisms_of_action parent
WHERE parent.name = 'Hypoglycemic Agents'
  AND child.name IN ('Dipeptidyl-Peptidase IV Inhibitors',
                     'Sodium-Glucose Transporter 2 Inhibitors');

-- Set ACEi, ARB parent (RAAS grouping) — no explicit parent in our table,
-- so we leave them as top-level with mechanism_class = 'raas_inhibitor'
