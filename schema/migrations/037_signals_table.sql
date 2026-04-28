-- Migration 037: signals table — the unit-of-output
--
-- SPEC-016 §2.4 names this as the single biggest platform gap. The
-- signals table holds dedup'd, KBQ-tagged, dual-tier-scored Signals.
-- Modules consume from here; the intelligence layer writes to here.
--
-- This migration creates the SCHEMA only. Population (clustering,
-- scoring, synthesis) is sprint B1+. We need the table in place so
-- the intel layer has somewhere to write.
--
-- Aligns with packages/api-contracts/src/intel.yaml Signal schema.
-- ADR-002 governs the dual confidence_tier / trust_score columns.

BEGIN;

-- ============================================================
-- signals table
-- ============================================================

CREATE TABLE IF NOT EXISTS signals (
    -- Identity
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id                UUID NOT NULL
                            REFERENCES market_events(id),

    -- Classification
    kbq_tags                TEXT[] NOT NULL DEFAULT '{}',
    headline                VARCHAR(120) NOT NULL,
    summary                 VARCHAR(500),
    direction               TEXT
                            CHECK (direction IS NULL
                                   OR direction IN ('positive', 'negative',
                                                    'neutral', 'mixed')),

    -- Tiers (ADR-002): confidence_tier authoritative; trust_score companion
    confidence_tier         TEXT NOT NULL
                            CHECK (confidence_tier IN ('confirmed', 'reported',
                                                       'inferred', 'disputed')),
    trust_score             REAL NOT NULL
                            CHECK (trust_score BETWEEN 0 AND 1),
    impact_tier             TEXT NOT NULL
                            CHECK (impact_tier IN ('high', 'medium', 'low')),
    impact_score            REAL NOT NULL
                            CHECK (impact_score BETWEEN 0 AND 1),

    -- Scoring rule version (B3 sprint — YAML rule registry)
    rule_version_id         TEXT NOT NULL,

    -- Subject entity
    primary_entity_type     TEXT NOT NULL,
    primary_entity_id       TEXT NOT NULL,
    primary_entity_name     TEXT,
    related_entity_ids      TEXT[] NOT NULL DEFAULT '{}',

    -- Evidence — the no-fabrication invariant
    evidence_document_ids   UUID[] NOT NULL
                            CHECK (cardinality(evidence_document_ids) >= 1),

    -- Lifecycle
    status                  TEXT NOT NULL DEFAULT 'candidate'
                            CHECK (status IN ('candidate', 'reviewed',
                                              'shipped', 'superseded',
                                              'retracted')),
    superseded_by           UUID REFERENCES signals(id),
    supersedence_reason     TEXT
                            CHECK (supersedence_reason IS NULL
                                   OR supersedence_reason IN ('corrected',
                                                              'progressed',
                                                              'downgraded',
                                                              'retracted',
                                                              'merged')),

    -- Audit
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reviewed_by             UUID,
    reviewed_at             TIMESTAMPTZ,
    shipped_at              TIMESTAMPTZ,

    -- Pairing invariants
    CONSTRAINT signals_supersedence_paired
        CHECK (
            (superseded_by IS NULL AND supersedence_reason IS NULL)
            OR (superseded_by IS NOT NULL AND supersedence_reason IS NOT NULL)
        ),
    CONSTRAINT signals_review_state_paired
        CHECK (
            (status NOT IN ('reviewed', 'shipped'))
            OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL)
        ),
    CONSTRAINT signals_shipped_state_paired
        CHECK (
            status != 'shipped' OR shipped_at IS NOT NULL
        )
);

COMMENT ON TABLE signals IS
    'The unit-of-output: dedup''d, KBQ-tagged, dual-tier-scored intelligence '
    'units consumed by module surfaces (CI digest/detail/brief/alert). '
    'Written by the clustering + scoring service (B1+B2 sprints). Read-only '
    'from module code. SPEC-016 §2.4.';

COMMENT ON COLUMN signals.kbq_tags IS
    'Subset of {financial, governance, strategic, clinical, product, '
    'ai_digital, conferences, pricing_access, regulatory, m_and_a, esg_supply}';

COMMENT ON COLUMN signals.confidence_tier IS
    'Authoritative tier (ADR-002). Drives synthesis hedging language and '
    'reviewer routing. Derived, never assigned.';

COMMENT ON COLUMN signals.trust_score IS
    'Companion to confidence_tier — same data, continuous form. Used for '
    'impact composite and the legacy intelligence_feed surface.';

COMMENT ON COLUMN signals.evidence_document_ids IS
    'No-fabrication invariant: every signal cites ≥1 source_records row. '
    'Empty array is forbidden by CHECK constraint.';

COMMENT ON COLUMN signals.supersedence_reason IS
    '5-value enum per SPEC-017 D8: corrected (factual error fixed), '
    'progressed (world moved forward — both shown in history), downgraded '
    '(confidence dropped after time-decay), retracted (source retracted), '
    'merged (two clusters determined to be the same event).';

-- ============================================================
-- Indexes — one per primary access pattern
-- ============================================================

-- Event reverse-lookup (every event has 0..N signals)
CREATE INDEX IF NOT EXISTS idx_signals_event
    ON signals (event_id);

-- Daily Digest read pattern: status + impact_tier + recency
CREATE INDEX IF NOT EXISTS idx_signals_status_impact
    ON signals (status, impact_tier, created_at DESC);

-- Watchlist filter: by entity
CREATE INDEX IF NOT EXISTS idx_signals_primary_entity
    ON signals (primary_entity_type, primary_entity_id);

-- KBQ filter on digest
CREATE INDEX IF NOT EXISTS idx_signals_kbq
    ON signals USING GIN (kbq_tags);

-- Supersedence chain walks (provenance audit + UI history)
CREATE INDEX IF NOT EXISTS idx_signals_supersedence
    ON signals (superseded_by)
    WHERE superseded_by IS NOT NULL;

COMMIT;
