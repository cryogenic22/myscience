-- Migration 050: signal_score_adjustments (SPEC-021 Phase D MVP)
--
-- Every captured outcome appends a row here. The numbers feed Phase D's
-- recalibration job (Phase 2) which aggregates per (rule_version_id,
-- kbq_tag) and adjusts the weights in intelligence_rules.yaml.
--
-- Migration is additive + idempotent.

CREATE TABLE IF NOT EXISTS signal_score_adjustments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- What rule version was active when the matched signal fired?
    rule_version_id TEXT NOT NULL,
    kbq_tag         TEXT NOT NULL,

    -- Provenance
    decision_id        UUID REFERENCES decisions(id) ON DELETE SET NULL,
    matched_signal_id  UUID REFERENCES signals(id)   ON DELETE SET NULL,

    -- The numbers
    calibration_score      REAL NOT NULL
        CHECK (calibration_score BETWEEN 0.0 AND 1.0),
    weight_delta_suggested REAL,  -- e.g. -0.05 if missed, +0.05 if verified

    notes      TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_signal_adj_rule_kbq
    ON signal_score_adjustments (rule_version_id, kbq_tag);

CREATE INDEX IF NOT EXISTS idx_signal_adj_decision
    ON signal_score_adjustments (decision_id) WHERE decision_id IS NOT NULL;

COMMENT ON TABLE signal_score_adjustments IS
    'SPEC-021 Phase D learning ledger. Every captured decision outcome '
    'appends a row keyed to the rule_version_id + kbq_tag of the '
    'matched signal. Phase 2 recalibration job aggregates these to '
    'tune intelligence_rules.yaml weights.';

COMMENT ON COLUMN signal_score_adjustments.weight_delta_suggested IS
    'Suggested adjustment for the rule weight. Sign indicates direction: '
    'positive when the signal correctly predicted the outcome, negative '
    'when it misled. Magnitude proportional to (calibration_score - 0.5).';
