-- Migration 038: drugs modality + ATC/NDC/UNII/ChEMBL/DrugBank
--
-- SPEC-016 §7 swimlane A1, task A1.2.
--
-- Adds modality classification + canonical drug identifiers:
--   - modality TEXT (CHECK enum)         drug-class taxonomy for routing
--   - atc_codes TEXT[]                   WHO ATC therapeutic codes
--   - ndc_codes TEXT[]                   FDA NDC product codes
--   - unii TEXT                          FDA Unique Ingredient Identifier
--   - chembl_id TEXT                     ChEMBL compound id
--   - drugbank_id TEXT                   DrugBank id
--
-- Companions to the molecular fields already added in migration 028
-- (pubchem_cid, canonical_smiles, inchi, molecular_weight, …).
-- All additions are idempotent.

BEGIN;

-- ============================================================
-- Modality (drug-class taxonomy)
-- ============================================================

ALTER TABLE drugs
    ADD COLUMN IF NOT EXISTS modality TEXT;

-- CHECK constraint added separately (idempotent via DO block) so re-running
-- doesn't error on duplicate constraint name.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'drugs_modality_check'
    ) THEN
        ALTER TABLE drugs
            ADD CONSTRAINT drugs_modality_check
            CHECK (modality IS NULL OR modality IN (
                'small_molecule',  -- conventional small-molecule chemistry
                'mab',             -- monoclonal antibody
                'adc',             -- antibody-drug conjugate
                'bispecific',      -- bispecific antibody (BiTE etc.)
                'gene_therapy',    -- viral-vector gene therapies (AAV, lentiviral)
                'cell_therapy',    -- CAR-T, NK-cell, etc.
                'rna',             -- siRNA, ASO, mRNA therapeutics (non-vaccine)
                'vaccine',         -- mRNA + traditional vaccines
                'device',          -- combination products with device dominance
                'other'            -- explicit fallback so writes never null-out
            ));
    END IF;
END $$;

COMMENT ON COLUMN drugs.modality IS
    'Drug-class taxonomy. Populated by domain.pharma.modality.classify_modality() '
    'from generic name + mechanism, with manual override possible. NULL means '
    'unclassified; ''other'' means classified-but-unrecognised-bucket.';

-- ============================================================
-- Identifier arrays
-- ============================================================

ALTER TABLE drugs
    ADD COLUMN IF NOT EXISTS atc_codes TEXT[] NOT NULL DEFAULT '{}';

COMMENT ON COLUMN drugs.atc_codes IS
    'WHO ATC therapeutic-classification codes. Multiple per drug is normal '
    '(e.g. metformin: A10BA02 + A10BD05 + A10BD08 + …). Sourced from WHO ATC '
    'index lookups by INN.';

ALTER TABLE drugs
    ADD COLUMN IF NOT EXISTS ndc_codes TEXT[] NOT NULL DEFAULT '{}';

COMMENT ON COLUMN drugs.ndc_codes IS
    'FDA NDC product codes (10- or 11-digit, formatted with hyphens). '
    'Multiple per drug — one per package size / form. Sourced from openFDA '
    'NDC directory connector.';

-- ============================================================
-- Identifier scalars
-- ============================================================

ALTER TABLE drugs
    ADD COLUMN IF NOT EXISTS unii TEXT;

COMMENT ON COLUMN drugs.unii IS
    'FDA Unique Ingredient Identifier (10-char alphanumeric). Resolves to '
    'the same substance across NDA/BLA/ANDA/sNDA filings. Sourced from openFDA.';

ALTER TABLE drugs
    ADD COLUMN IF NOT EXISTS chembl_id TEXT;

COMMENT ON COLUMN drugs.chembl_id IS
    'ChEMBL compound id (e.g. CHEMBL1201580). Already used by molecular_targets '
    'table; mirrored on drugs for direct lookup.';

ALTER TABLE drugs
    ADD COLUMN IF NOT EXISTS drugbank_id TEXT;

COMMENT ON COLUMN drugs.drugbank_id IS
    'DrugBank id (e.g. DB00945). Cross-reference to DrugBank therapeutic / '
    'pharmacological data.';

-- ============================================================
-- Indexes
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_drugs_modality
    ON drugs (modality)
    WHERE modality IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_drugs_atc
    ON drugs USING GIN (atc_codes);

CREATE INDEX IF NOT EXISTS idx_drugs_ndc
    ON drugs USING GIN (ndc_codes);

CREATE UNIQUE INDEX IF NOT EXISTS idx_drugs_unii
    ON drugs (unii)
    WHERE unii IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_drugs_chembl
    ON drugs (chembl_id)
    WHERE chembl_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_drugs_drugbank
    ON drugs (drugbank_id)
    WHERE drugbank_id IS NOT NULL;

COMMIT;
