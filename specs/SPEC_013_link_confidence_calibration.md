# SPEC-013: Link Confidence Calibration

*Date: 19 April 2026*
*Priority: P2 (ship before SPEC_012 backfill so new links inherit calibrated confidence)*
*Effort: 2–3 days*

---

## Goal

Differentiate `entity_links.confidence` by how the link was discovered, and expose confidence as a first-class filter in graph traversal and evidence retrieval. Today most links land at 1.0 regardless of provenance, which prevents downstream reasoning from distinguishing reliable facts from tentative ones.

## Why This Matters

From the lead's review (Section 7.2):

> Most links are created with 1.0 confidence regardless of how they were discovered. This should be calibrated so that an llm_extracted link carries lower confidence than an exact_id link.

And Section 5.2:

> Link confidence is underused — an agent cannot easily distinguish between a high-confidence exact_id link and a low-confidence llm_extracted link when navigating. Exposing link_via and confidence as first-class filters in the traversal API would help.

Net effect: every link looks equally trustworthy to the query engine, so the LLM context contains both exact-ID-matched facts and noisy LLM-extracted associations with no way to weight them.

## Calibration Targets

Confidence by `link_via` value (canonical):

| `link_via` | Confidence | Justification |
|------------|-----------|---------------|
| `exact_id` | 1.00 | NCT, PMID, NDA, MeSH, CIK match — lossless |
| `user_tagged` | 0.95 | Human review explicitly affirmed |
| `entity_resolution` | use the resolver's score | Already computed in `resolution_audit.confidence` |
| `mesh_term` | 0.90 | Authoritative ontology mapping |
| `ror_match` | 0.90 | New: ROR-identified institution match (SPEC_012) |
| `cross_link_rule` | 0.85 | Domain pack rule, deterministic but pattern-based |
| `auto_create_trusted_source` | 0.80 | Auto-created from FDA/CT.gov etc. (was uniform 0.5 — too pessimistic) |
| `embedding_similarity` | 0.70 | Vector cosine match — semantic but not exact |
| `llm_extracted` | 0.65 | LLM-identified mention, no structured ID |
| `auto_create_news` | 0.55 | Auto-created from news article — weakest signal |

## Tests First

Create `tests/test_link_confidence_calibration.py`:

```python
"""TDD for link confidence calibration. All tests must FAIL before implementation."""
import pytest
from db import Database
from config import config

from integration.cross_linker import CrossLinker, calibrated_confidence
from integration.entity_resolver import EntityResolver


# ── Calibration table tests ──────────────────────────────────────

@pytest.mark.parametrize("link_via,expected", [
    ("exact_id", 1.00),
    ("user_tagged", 0.95),
    ("mesh_term", 0.90),
    ("ror_match", 0.90),
    ("cross_link_rule", 0.85),
    ("auto_create_trusted_source", 0.80),
    ("embedding_similarity", 0.70),
    ("llm_extracted", 0.65),
    ("auto_create_news", 0.55),
])
def test_calibrated_confidence_table(link_via, expected):
    """SPEC_013: helper must return canonical confidence by link_via."""
    assert calibrated_confidence(link_via) == expected


def test_calibrated_confidence_unknown_link_via_defaults_to_lowest():
    """Unknown link_via must not silently get 1.0 — return floor."""
    assert calibrated_confidence("mystery_method") <= 0.6


def test_entity_resolution_confidence_passes_through():
    """For link_via=entity_resolution, the resolver's score is preserved."""
    assert calibrated_confidence("entity_resolution", resolver_score=0.83) == 0.83


def test_entity_resolution_without_score_defaults_to_floor():
    assert calibrated_confidence("entity_resolution") <= 0.6


# ── CrossLinker integration ──────────────────────────────────────

def test_cross_linker_emits_calibrated_confidence(monkeypatch):
    """When CrossLinker creates links, confidence must reflect the link_via."""
    inserted = []
    class FakeDB:
        def execute(self, sql, params=None): inserted.append((sql, params))
        def fetch_all(self, sql, params=None): return []
    linker = CrossLinker(FakeDB())
    linker.create_link(
        source_id="d1", source_type="drug",
        target_id="m1", target_type="mechanism",
        link_type="TARGETS_MECHANISM",
        link_via="cross_link_rule",
        provenance_source="domain_pack",
    )
    assert any("0.85" in str(p) for _, p in inserted) or \
           any(0.85 in (p or {}).values() for _, p in inserted if isinstance(p, dict))


# ── Migration: traverse_graph must accept min_confidence ─────────

def test_traverse_graph_accepts_min_confidence_param(db):
    """SPEC_013 migration must add min_confidence param to traverse_graph()."""
    rows = db.fetch_all(
        "SELECT proargnames FROM pg_proc WHERE proname = 'traverse_graph'"
    )
    assert rows
    args = rows[0]["proargnames"]
    assert "p_min_confidence" in args


def test_traverse_graph_filters_by_min_confidence(db):
    """When min_confidence=0.8, low-confidence links should be excluded."""
    # Seed test data with two links: one at 0.9, one at 0.5
    db.execute("""
        INSERT INTO entity_links
            (source_entity_id, source_entity_type, target_entity_id, target_entity_type,
             link_type, confidence, link_via, provenance_source)
        VALUES
            ('test_d1', 'drug', 'test_m1', 'mechanism', 'TARGETS_MECHANISM', 0.9, 'exact_id', 'test'),
            ('test_d1', 'drug', 'test_m2', 'mechanism', 'TARGETS_MECHANISM', 0.5, 'llm_extracted', 'test')
    """)
    try:
        results = db.fetch_all(
            "SELECT * FROM traverse_graph('test_d1', 1, NULL, 50, 0.8)"
        )
        target_ids = {r["tgt_id"] for r in results}
        assert "test_m1" in target_ids
        assert "test_m2" not in target_ids
    finally:
        db.execute("DELETE FROM entity_links WHERE provenance_source = 'test'")


# ── Evidence retrieval honours confidence floor ───────────────────

def test_evidence_retrieval_applies_confidence_floor(monkeypatch):
    """services/search.py or query_engine.py must filter evidence by MZ_LINK_CONFIDENCE_FLOOR."""
    monkeypatch.setenv("MZ_LINK_CONFIDENCE_FLOOR", "0.7")
    from services.query_engine import QueryEngine
    engine = QueryEngine.__new__(QueryEngine)  # bypass __init__ for unit test
    # The engine's internal confidence floor must reflect env
    assert engine._confidence_floor() == 0.7


# ── Backfill correctness ─────────────────────────────────────────

def test_backfill_recalibrates_existing_links(db):
    """Migration 017 backfill should set all existing links to calibrated values."""
    # Pick a sample of links, verify they are NOT all 1.0 anymore
    samples = db.fetch_all("""
        SELECT confidence, link_via, COUNT(*) AS n
        FROM entity_links
        GROUP BY confidence, link_via
        ORDER BY n DESC
        LIMIT 20
    """)
    # After backfill, we should see multiple confidence values (not just 1.0)
    distinct_confidences = {row["confidence"] for row in samples}
    assert len(distinct_confidences) > 1, (
        "after backfill, entity_links must have varied confidence — "
        "currently all uniformly 1.0"
    )
```

**Run them**: `python -m pytest tests/test_link_confidence_calibration.py -v`. All must FAIL.

## Implementation Plan

### Step 1 — Create `integration/confidence.py` with the canonical table

```python
"""Single source of truth for link confidence calibration.

See SPEC-013 for justifications. Update this table — do not hardcode
confidence values elsewhere in the pipeline."""

from typing import Optional

CALIBRATION_TABLE: dict[str, float] = {
    "exact_id": 1.00,
    "user_tagged": 0.95,
    "mesh_term": 0.90,
    "ror_match": 0.90,
    "cross_link_rule": 0.85,
    "auto_create_trusted_source": 0.80,
    "embedding_similarity": 0.70,
    "llm_extracted": 0.65,
    "auto_create_news": 0.55,
}

FLOOR = 0.50


def calibrated_confidence(link_via: str, resolver_score: Optional[float] = None) -> float:
    """Return confidence for a link given how it was discovered.

    For link_via="entity_resolution", pass the resolver's own score via
    resolver_score. For all other methods the table above is authoritative.
    """
    if link_via == "entity_resolution":
        return float(resolver_score) if resolver_score is not None else FLOOR
    return CALIBRATION_TABLE.get(link_via, FLOOR)
```

### Step 2 — Update `integration/cross_linker.py`

Replace any hardcoded `confidence = 1.0` (or similar) with `confidence = calibrated_confidence(link_via, resolver_score=...)`.

### Step 3 — Update `integration/entity_resolver.py`

For the auto-create paths, set `link_via` correctly:
- Auto-create from FDA/CT.gov/PMID etc. → `auto_create_trusted_source`
- Auto-create from news/press release → `auto_create_news`

Remove the uniform 0.5 confidence assignment.

### Step 4 — Migration `schema/migrations/017_link_confidence.sql`

```sql
-- 017_link_confidence.sql
-- Recalibrates traverse_graph() to support min_confidence and backfills existing links.

-- Drop and recreate traverse_graph with new param
DROP FUNCTION IF EXISTS traverse_graph(text, integer, text[], integer);

CREATE OR REPLACE FUNCTION traverse_graph(
    p_start_id text,
    p_max_hops integer DEFAULT 2,
    p_link_types text[] DEFAULT NULL,
    p_max_nodes integer DEFAULT 50,
    p_min_confidence numeric DEFAULT 0.0
)
RETURNS TABLE (
    src_id text, src_type text, tgt_id text, tgt_type text,
    ltype text, conf numeric, via text, d integer
) AS $$
    WITH RECURSIVE graph_bfs AS (
        SELECT
            el.source_entity_id AS src_id,
            el.source_entity_type AS src_type,
            el.target_entity_id AS tgt_id,
            el.target_entity_type AS tgt_type,
            el.link_type AS ltype,
            el.confidence AS conf,
            el.link_via AS via,
            1 AS d,
            ARRAY[el.source_entity_id, el.target_entity_id] AS visited
        FROM entity_links el
        WHERE el.source_entity_id = p_start_id
          AND el.confidence >= p_min_confidence
          AND (p_link_types IS NULL OR el.link_type = ANY(p_link_types))

        UNION ALL

        SELECT
            el.source_entity_id, el.source_entity_type,
            el.target_entity_id, el.target_entity_type,
            el.link_type, el.confidence, el.link_via,
            g.d + 1,
            g.visited || el.target_entity_id
        FROM entity_links el
        JOIN graph_bfs g ON el.source_entity_id = g.tgt_id
        WHERE g.d < p_max_hops
          AND el.confidence >= p_min_confidence
          AND NOT el.target_entity_id = ANY(g.visited)
          AND (p_link_types IS NULL OR el.link_type = ANY(p_link_types))
    )
    SELECT DISTINCT ON (g2.src_id, g2.tgt_id, g2.ltype)
        g2.src_id, g2.src_type, g2.tgt_id, g2.tgt_type,
        g2.ltype, g2.conf, g2.via, g2.d
    FROM graph_bfs g2
    ORDER BY g2.src_id, g2.tgt_id, g2.ltype, g2.d
    LIMIT p_max_nodes
$$ LANGUAGE SQL STABLE;

-- Backfill existing links to use calibrated confidence
UPDATE entity_links SET confidence = 1.00 WHERE link_via = 'exact_id';
UPDATE entity_links SET confidence = 0.95 WHERE link_via = 'user_tagged';
UPDATE entity_links SET confidence = 0.90 WHERE link_via IN ('mesh_term', 'ror_match');
UPDATE entity_links SET confidence = 0.85 WHERE link_via = 'cross_link_rule';
UPDATE entity_links SET confidence = 0.80 WHERE link_via = 'auto_create_trusted_source';
UPDATE entity_links SET confidence = 0.70 WHERE link_via = 'embedding_similarity';
UPDATE entity_links SET confidence = 0.65 WHERE link_via = 'llm_extracted';
UPDATE entity_links SET confidence = 0.55 WHERE link_via = 'auto_create_news';
-- Leave entity_resolution links alone (they have specific scores)

-- Index to help confidence filters
CREATE INDEX IF NOT EXISTS idx_entity_links_confidence
    ON entity_links (confidence DESC);
```

### Step 5 — Wire confidence floor into `services/query_engine.py`

```python
def _confidence_floor(self) -> float:
    return float(os.getenv("MZ_LINK_CONFIDENCE_FLOOR", "0.5"))
```

Pass this floor to `traverse_graph()` calls and to evidence retrieval queries (`WHERE el.confidence >= floor`).

### Step 6 — Update Python callers of `traverse_graph`

Find all `SELECT * FROM traverse_graph(...)` callsites in `services/graph.py`. Add a fifth parameter, default 0.0 to preserve backward compatibility, override with floor where evidence quality matters.

## Acceptance Criteria

- [ ] All tests in `tests/test_link_confidence_calibration.py` pass
- [ ] Existing test suite has zero regressions
- [ ] Migration 017 applied successfully
- [ ] Distribution check: `SELECT confidence, COUNT(*) FROM entity_links GROUP BY confidence` shows ≥4 distinct values (was uniformly 1.0)
- [ ] `traverse_graph(...)` accepts and respects `p_min_confidence`
- [ ] Sample query with `MZ_LINK_CONFIDENCE_FLOOR=0.7` excludes `llm_extracted` and `auto_create_news` links from evidence

## Rollout / Rollback

**Rollout:**
1. Local tests pass.
2. Apply migration locally, verify backfill on a sample dataset.
3. Deploy to Railway.
4. Apply migration: `railway run python migrate.py` (backfill is in the migration; runs once).
5. Monitor query latency for 24h — confidence index should keep traverse fast.

**Rollback:**
- Set `MZ_LINK_CONFIDENCE_FLOOR=0.0` to disable filtering immediately.
- Revert function: a follow-up migration restoring 4-arg signature is straightforward (the SQL is in version control).
- Backfill is one-way; reverse would require re-running ETL — but the calibration is the desired state, so rollback is unlikely.

## Out of Scope

- Per-link-type confidence floors (e.g., evidence path 0.7, dossier path 0.5) — single global floor is enough for v1
- Confidence-weighted ranking in vector search — the floor is a hard cut, not a weight
- UI confidence indicators (separate frontend task)
