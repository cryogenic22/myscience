-- 094_scenario_prob_history_stance_counts.sql
--
-- Loop 1+2 follow-up (Helix output-quality / OQ3 + dossier readiness H-d) —
-- persist the STANCE MIX of each probability move.
--
-- calibrate_scenario_prob already computes how many signals CORROBORATED vs
-- CONTRADICTED a scenario when it moved (#227 added downward calibration; #231
-- added the scenario_probability_history audit ledger). But those counts were
-- discarded — recoverable only by regex-parsing the human note. So "was this
-- move driven by a contradiction?" (OQ3 "surface contradictions, don't average
-- them away"; the dossier `contradicted` readiness state, H-d) could not be
-- answered as structured data.
--
-- This makes the stance mix first-class on the existing ledger (NOT a second
-- table — the prob-history ledger is the single canonical record of a move).
-- Additive + non-null with a 0 default, so every existing row and writer that
-- does not set them is unaffected (they read as "no contradiction recorded").

ALTER TABLE scenario_probability_history
    ADD COLUMN IF NOT EXISTS n_supporting    INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS n_contradicting INTEGER NOT NULL DEFAULT 0;
