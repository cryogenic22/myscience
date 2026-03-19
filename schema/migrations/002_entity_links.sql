-- 002_entity_links.sql
-- Cross-source relationship graph stored as a flat table.
-- Replaces Neo4j for MVP. Traversal via SQL joins.

CREATE TABLE entity_links (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_entity_id UUID NOT NULL,
    source_entity_type TEXT NOT NULL,
    target_entity_id UUID NOT NULL,
    target_entity_type TEXT NOT NULL,
    link_type TEXT NOT NULL,
    -- How this link was discovered:
    -- "exact_id" (NDA, NCT, PMID match), "entity_resolution" (fuzzy name match),
    -- "mesh_term" (ontology-mediated), "llm_extracted", "user_tagged"
    link_via TEXT NOT NULL,
    confidence FLOAT DEFAULT 1.0,
    metadata JSONB,
    provenance_source TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Prevent duplicate links
CREATE UNIQUE INDEX idx_links_unique ON entity_links(
    source_entity_id, target_entity_id, link_type
);

CREATE INDEX idx_links_source ON entity_links(source_entity_id, source_entity_type);
CREATE INDEX idx_links_target ON entity_links(target_entity_id, target_entity_type);
CREATE INDEX idx_links_type ON entity_links(link_type);
CREATE INDEX idx_links_via ON entity_links(link_via);

-- Common link_type values:
-- OWNS               (company → drug)
-- SPONSORS            (company → trial)
-- INVESTIGATES        (trial → drug)
-- TARGETS_MECHANISM   (drug → mechanism)
-- IN_THERAPEUTIC_AREA (drug → therapeutic_area)
-- EVIDENCE_FOR        (pubmed_article → drug)
-- MENTIONED_IN        (knowledge_chunk → company or drug)
-- COMPETES_WITH       (drug → drug, same mechanism/area)
-- PATENT_BLOCKS       (drug → drug, via patent overlap)
-- SHORTAGE_AFFECTS    (market_event → drug)
-- USER_LINKED         (user_source → any entity)
