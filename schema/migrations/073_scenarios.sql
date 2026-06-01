-- Migration 073: scenarios (the spine keystone — PB-H09 / Helix v8 parity)
--
-- The benchmark's whole "wargaming" identity rests on scenarios being
-- FIRST-CLASS, PROBABILISTIC objects grounded in the dossier — not the
-- deterministic what-if computations services/scenario_engine.py produces.
-- A scenario is a named, plausible future ("Lilly goes on offense") that:
--   * is DERIVED from a dossier snapshot (the state of knowledge), citing the
--     specific facts that justify it (from_fact_ids -> provenance),
--   * carries a PRIOR probability and, once the calibration loop (PB-H14) is
--     wired, a CURRENT probability re-weighted as signals arrive, with a note
--     explaining the shift,
--   * holds the per-team moves + decision options the war-game fills in.
--
-- This closes the missing vertebra in the provenance spine
-- (signal -> fact -> insight -> SCENARIO -> decision -> outcome).
--
-- Serialization note: the JSONB payloads (from_fact_ids, team_moves,
-- decision_options, blocked_by_gaps) are stored in the exact shape the
-- frontend ScenariosPage.tsx `Scenario` interface renders — assembly is
-- server-side, the UI is dumb. from_fact_ids is [{factId, predicate}] (NOT a
-- facts.id FK array): dossier facts include synthetic ids (metric-/entity-
-- graph-derived) that are not facts.id UUIDs, so a FK would reject them.

BEGIN;

CREATE TABLE IF NOT EXISTS scenarios (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    engagement_id       UUID NOT NULL REFERENCES engagements(id) ON DELETE CASCADE,
    -- The dossier snapshot this scenario was derived from (state-of-knowledge
    -- at derivation time). NULL-safe: a snapshot may later be pruned.
    dossier_snapshot_id UUID REFERENCES dossier_snapshots(id) ON DELETE SET NULL,

    name                TEXT NOT NULL,
    trigger_event       TEXT NOT NULL,                       -- what sets it off
    trigger_date        DATE,                                -- when (optional)

    -- Provenance: the dossier facts that justify this scenario.
    -- [{factId, predicate}] — mirrors the ScenarioEvidence interface.
    from_fact_ids       JSONB NOT NULL DEFAULT '[]'::jsonb,

    -- Bayesian calibration. prior = structural heuristic at derivation;
    -- current = re-weighted by the calibration loop (PB-H14) as signals land.
    prior_prob          REAL NOT NULL DEFAULT 0.3
                        CHECK (prior_prob >= 0 AND prior_prob <= 1),
    current_prob        REAL
                        CHECK (current_prob IS NULL
                               OR (current_prob >= 0 AND current_prob <= 1)),
    calibration_note    TEXT,                                -- why current moved

    -- War-game payloads (filled by later loops; the UI shape, server-assembled).
    team_moves          JSONB NOT NULL DEFAULT '[]'::jsonb,  -- [{team, move, rationale}]
    decision_options    JSONB NOT NULL DEFAULT '[]'::jsonb,  -- [{id,statement,rationale,npv5yDkkBn,recommended}]
    decision_output     TEXT,                                -- synthesis

    -- The dossier gaps that block confident execution of this scenario
    -- (reuses the D1 actionable-gaps surface). [string].
    blocked_by_gaps     JSONB NOT NULL DEFAULT '[]'::jsonb,

    created_by          TEXT NOT NULL DEFAULT 'system',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_archived         BOOLEAN NOT NULL DEFAULT FALSE
);

-- List scenarios for an engagement, newest first (the ScenariosPage feed).
CREATE INDEX IF NOT EXISTS idx_scenarios_engagement
    ON scenarios (engagement_id, created_at DESC)
    WHERE is_archived = FALSE;

COMMENT ON TABLE scenarios IS
    'First-class probabilistic scenarios (PB-H09). Derived from a dossier '
    'snapshot, citing the facts that justify them (from_fact_ids), carrying a '
    'prior + (later) calibrated current probability. The missing vertebra in '
    'the signal->fact->insight->SCENARIO->decision->outcome spine. JSONB '
    'payloads match the frontend Scenario interface.';

COMMIT;
