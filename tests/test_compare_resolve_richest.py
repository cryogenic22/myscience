"""Lane-1: the chat compare/general path must resolve a drug name to its richest
ACTIVE row — never an arbitrary soft-deleted duplicate.

Audit RC1 (same disease the dossier resolver already fixed): on prod
'semaglutide' has 17 drug rows and 'tirzepatide' has 2; the A6 consolidation
soft-deleted the dups (record_status='merged'/'superseded'). resolve_entity used
`WHERE LOWER(generic_name)=LOWER(%s) LIMIT 1` with no ORDER BY and no status
filter, so 'Compare semaglutide vs tirzepatide' landed on near-empty merged dups
(reported 2 trials vs 1 for drugs that own 184 and 114). Pin the ranking so it
can't be silently dropped.
"""

from services.chat_handlers.formatting import resolve_entity


class _CapturingDB:
    """Returns the rich active row only when the query both excludes soft-deleted
    rows and ranks by richness — i.e. the bug's fix. A naive LIMIT-1 query (the
    pre-fix behaviour) gets the near-empty merged duplicate, so the behaviour test
    fails without the fix (RED) and passes with it (GREEN)."""

    def __init__(self):
        self.sql = None

    def fetch_one(self, sql, params=None):
        s = (sql or "").lower()
        if "from drugs" not in s:
            return None
        self.sql = sql
        ranks_by_richness = "order by richness desc" in s
        skips_softdeleted = "record_status is distinct from 'merged'" in s
        if ranks_by_richness and skips_softdeleted:
            return {"entity_id": "rich-active", "gname": "tirzepatide", "richness": 550}
        # Pre-fix path: arbitrary duplicate (a 0-fact merged row).
        return {"entity_id": "merged-dup", "label": "Tirzepatide"}


def test_resolve_entity_drug_sql_ranks_by_richness_and_skips_softdeleted():
    db = _CapturingDB()
    resolve_entity("tirzepatide", "drug", db)
    s = db.sql.lower()
    assert "richness" in s
    assert "order by richness desc" in s
    assert "clinical_trials" in s and "facts" in s
    assert "record_status is distinct from 'merged'" in s
    assert "record_status is distinct from 'superseded'" in s


def test_resolve_entity_drug_picks_richest_active_row():
    db = _CapturingDB()
    r = resolve_entity("tirzepatide", "drug", db)
    assert r is not None
    assert r["entity_id"] == "rich-active"
    assert r["label"] == "tirzepatide"
    assert r["entity_type"] == "drug"
    assert r["match_score"] == 1.0


def test_resolve_entity_drug_brand_returns_generic_label():
    """A brand hit still returns the canonical generic_name as the label."""
    class _BrandDB:
        def fetch_one(self, sql, params=None):
            if "from drugs" in (sql or "").lower():
                return {"entity_id": "rich-active", "gname": "tirzepatide", "richness": 550}
            return None

    r = resolve_entity("Mounjaro", "drug", _BrandDB())
    assert r is not None and r["label"] == "tirzepatide"


def test_resolve_entity_drug_alias_beats_fuzzy_junk_row():
    """A curated brand alias (Wegovy→semaglutide) must win over a greedy fuzzy
    LIKE that would otherwise grab a junk look-alike row ('wegovy '). Alias sits
    between exact and fuzzy in the cascade."""
    class _AliasDB:
        def fetch_one(self, sql, params=None):
            s = (sql or "").lower()
            if "from entity_aliases" in s:
                return {"entity_id": "rich-active", "gname": "semaglutide"}
            if "like" in s:  # fuzzy would return the junk row — must not be reached
                return {"entity_id": "junk-wegovy", "gname": "wegovy"}
            return None  # exact miss

    r = resolve_entity("Wegovy", "drug", _AliasDB())
    assert r is not None
    assert r["entity_id"] == "rich-active"
    assert r["label"] == "semaglutide"
    assert r["match_score"] == 0.95


def test_resolve_entity_drug_sql_skips_excluded_rows():
    """Entity-extraction junk quarantined as record_status='excluded' (e.g.
    'semaglutide or tirzepatide') must be filtered too — else the fuzzy LIKE for
    'tirzepatide' resolves to that look-alike. Regression: the status filter
    originally excluded only 'merged'/'superseded'."""
    db = _CapturingDB()
    resolve_entity("tirzepatide", "drug", db)
    s = db.sql.lower()
    assert "record_status is distinct from 'excluded'" in s


def test_resolve_entity_drug_unknown_returns_none():
    class _EmptyDB:
        def fetch_one(self, sql, params=None):
            return None

    assert resolve_entity("totallyunknownmolecule", "drug", _EmptyDB()) is None
