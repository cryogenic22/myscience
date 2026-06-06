-- 083_domain_forge.sql
--
-- DF-1 / DF-2 — Domain Forge: a playable SME knowledge-elicitation round.
--
-- One SME interaction = a playbook edit + a gold eval label + a validation
-- signal. This migration stores the three persisted artefacts of that loop:
--
--   forge_rounds      one generated prompt FROM real DB entities (the "play").
--                     Round type ① "What matters?": given a real compare
--                     question, the SME picks/ranks the dimensions that matter.
--   forge_eval_items  the GOLD eval label minted from a played round (prompt →
--                     SME answer) — consumed by the eval harness.
--   forge_scores      a per-answer score row, gated on validation / consensus
--                     (reward correctness, not volume). DF-2.
--
-- The elicited dimension itself is persisted into a PLAYBOOK VERSION via the
-- existing PlaybookAuthoringService (migrations 080/082) — NOT duplicated here.
-- These tables are the round/eval/score substrate around that authoring write.
--
-- Additive + idempotent (CREATE ... IF NOT EXISTS) + reversible (drop to revert).

-- ── rounds ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS forge_rounds (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id    TEXT NOT NULL,                       -- groups one SME's plays
    round_type    TEXT NOT NULL DEFAULT 'what_matters',-- ① what_matters (more types: DF-5)
    playbook_id   TEXT NOT NULL,                       -- the playbook this round elicits into
    intent        TEXT NOT NULL,                       -- e.g. 'compare'
    prompt        TEXT NOT NULL,                       -- the question shown to the SME
    -- the constrained choice set the SME picks/ranks from, grounded in real
    -- entities: {entities:[{entity_id,label,entity_type}], options:[{key,label,...}]}
    payload       JSONB NOT NULL DEFAULT '{}'::jsonb,
    status        TEXT NOT NULL DEFAULT 'open',         -- open | answered
    created_by    TEXT,                                 -- audit: who generated it
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    answered_at   TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_forge_rounds_session ON forge_rounds(session_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_forge_rounds_playbook ON forge_rounds(playbook_id);

-- ── answers → gold eval items ─────────────────────────────────────────────
-- Each played round mints a gold eval item: the prompt + the SME's constrained
-- answer, the canonical label the eval harness scores future model output against.
CREATE TABLE IF NOT EXISTS forge_eval_items (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    round_id        UUID NOT NULL REFERENCES forge_rounds(id) ON DELETE CASCADE,
    session_id      TEXT NOT NULL,
    playbook_id     TEXT NOT NULL,
    intent          TEXT NOT NULL,
    prompt          TEXT NOT NULL,
    -- the SME's constrained answer: {selected:[keys], ranking:[keys], dimension:{...}}
    answer          JSONB NOT NULL DEFAULT '{}'::jsonb,
    sme_id          TEXT,                               -- who answered (consensus key)
    -- validation outcome at submit time (DF-2): {valid:bool, errors:[...]}
    validation      JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- did this answer get applied to a playbook version, or flagged for review?
    consensus_state TEXT NOT NULL DEFAULT 'pending',    -- pending | promoted | flagged
    promoted_version INTEGER,                            -- playbook_versions.version if promoted
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_forge_eval_round ON forge_eval_items(round_id);
CREATE INDEX IF NOT EXISTS idx_forge_eval_session ON forge_eval_items(session_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_forge_eval_playbook ON forge_eval_items(playbook_id);

-- ── scores ────────────────────────────────────────────────────────────────
-- A score is awarded per answer, GATED on validation + consensus: a correct,
-- corroborated answer scores; a flagged/dissenting one does not (reward
-- correctness, not volume). One row per eval item.
CREATE TABLE IF NOT EXISTS forge_scores (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    eval_item_id  UUID NOT NULL REFERENCES forge_eval_items(id) ON DELETE CASCADE,
    session_id    TEXT NOT NULL,
    sme_id        TEXT,
    points        INTEGER NOT NULL DEFAULT 0,
    reason        TEXT,                                 -- why this score (audit)
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_forge_scores_eval ON forge_scores(eval_item_id);
CREATE INDEX IF NOT EXISTS idx_forge_scores_session ON forge_scores(session_id);
