-- Migration 070: priority_matrix column on business_context_briefs (Z5)
--
-- ZS framework Section 1.1: the priority matrix codifies which dossier
-- domains are Critical / High / Medium for this engagement. Lives inline
-- on the BCB since matrices don't outlive their BCB.

BEGIN;

ALTER TABLE business_context_briefs
    ADD COLUMN IF NOT EXISTS priority_matrix JSONB;

-- When present, the matrix must cover all 8 ZS dossier domains. Enforced
-- in Python (services/priority_matrix.py:PriorityMatrix.__post_init__) and
-- mirrored here for defence-in-depth.
ALTER TABLE business_context_briefs
    ADD CONSTRAINT bcb_priority_matrix_complete CHECK (
        priority_matrix IS NULL OR (
            priority_matrix ? 'disease_and_patient'    AND
            priority_matrix ? 'clinical_profile'       AND
            priority_matrix ? 'competitive'            AND
            priority_matrix ? 'pricing_and_access'     AND
            priority_matrix ? 'commercial_operational' AND
            priority_matrix ? 'hcp_and_patient'        AND
            priority_matrix ? 'pipeline_and_macro'     AND
            priority_matrix ? 'wargame_specific'
        )
    );

COMMENT ON COLUMN business_context_briefs.priority_matrix IS
    'ZS Section 1.1 priority matrix. 8 dossier domains -> {critical|high|medium}. '
    'NULL until set; when set must cover all 8 domains. Z5.';

COMMIT;
