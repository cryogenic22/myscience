-- 080_playbooks.sql
--
-- DI-1 — DB-backed, SME-editable Answer Playbooks (Domain Intelligence module).
--
-- A playbook is encoded domain expertise for a CLASS of question: a trigger
-- (intent × entity-type signature) + a list of routed dimensions + a synthesis
-- shape. The bundled YAML seeds (services/domain_intelligence/playbooks/*.yaml)
-- are the defaults; a row here OVERRIDES the seed for the same id. This is the
-- SME-editable path (DI-5): CRUD + validation + versioning land on this table.
--
-- The planner (services/domain_intelligence/planner.py) reads playbooks via
-- PlaybookRegistry(db=...), which loads the seed then layers DB rows on top.
-- Additive + idempotent + reversible (drop table to revert to seed-only).

CREATE TABLE IF NOT EXISTS playbooks (
    id          TEXT PRIMARY KEY,           -- e.g. 'compare.drug_x_drug'
    pack        TEXT NOT NULL DEFAULT 'pharma',
    trigger     JSONB NOT NULL DEFAULT '{}'::jsonb,   -- {intent, entities}
    dimensions  JSONB NOT NULL DEFAULT '[]'::jsonb,   -- [{key,label,sub_question,routes,required,weight}]
    synthesis   JSONB NOT NULL DEFAULT '{}'::jsonb,   -- {shape, lead_with}
    active      BOOLEAN NOT NULL DEFAULT true,
    version     INTEGER NOT NULL DEFAULT 1,           -- DI-5 versioning
    author      TEXT,                                 -- DI-5 audit
    tenant_scope TEXT,                                -- E11 multi-tenancy forward-compat
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_playbooks_active ON playbooks(active);
CREATE INDEX IF NOT EXISTS idx_playbooks_pack ON playbooks(pack);
