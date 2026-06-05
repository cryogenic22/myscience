"""PB-H19 — event→entity resolution tests (pure + fake-DB)."""
from __future__ import annotations

from services.event_entity_resolver import (
    VocabEntry,
    backfill_orphaned_events,
    derive_primary_from_drug_id,
    load_vocabulary,
    resolve_from_text,
)

VOCAB = [
    VocabEntry("Foundayo", "foundayo", "drug", "d-found"),
    VocabEntry("orforglipron", "orforglipron", "drug", "d-orfor"),
    VocabEntry("Eli Lilly", "eli lilly", "company", "c-lilly"),
    VocabEntry("Lilly", "lilly", "company", "c-lilly"),
    VocabEntry("Novo", "novo", "company", "c-novo"),
]
# Match function expects longest-first ordering (load_vocabulary guarantees it).
VOCAB.sort(key=lambda v: len(v.name_lower), reverse=True)


class TestResolveFromText:
    def test_matches_a_known_drug(self):
        hit = resolve_from_text("FDA approves Lilly's Foundayo for obesity", VOCAB)
        assert hit == ("drug", "d-found", "Foundayo")

    def test_longest_match_wins(self):
        # "Eli Lilly" (9) should beat "Lilly" (5) when both appear.
        hit = resolve_from_text("Eli Lilly reported Q2 results", VOCAB)
        assert hit == ("company", "c-lilly", "Eli Lilly")

    def test_word_boundary_no_substring_match(self):
        # 'novo' must not match inside 'innovonova'.
        assert resolve_from_text("the innovonova platform", VOCAB) is None

    def test_case_insensitive(self):
        hit = resolve_from_text("ORFORGLIPRON hit its endpoint", VOCAB)
        assert hit == ("drug", "d-orfor", "orforglipron")

    def test_no_match_returns_none(self):
        assert resolve_from_text("Pfizer announces a buyback", VOCAB) is None

    def test_empty_text(self):
        assert resolve_from_text("", VOCAB) is None


class _FakeDB:
    def __init__(self, rows):
        self.rows = rows
        self.updates = []

    def fetch_all(self, sql, params=None):
        return self.rows

    def execute(self, sql, params=None):
        self.updates.append(params)


class _VocabDB:
    """Fake DB whose fetch_all dispatches by the table named in the SQL."""
    def __init__(self, drugs, companies, aliases):
        self.drugs, self.companies, self.aliases = drugs, companies, aliases

    def fetch_all(self, sql, params=None):
        s = sql.lower()
        if "from drugs" in s:
            return self.drugs
        if "from companies" in s:
            return self.companies
        if "entity_aliases" in s:
            return self.aliases
        return []


class TestLoadVocabulary:
    def test_pulls_brand_and_generic_drug_names(self):
        """Pins the column contract: drugs has brand_name + generic_name,
        NOT a single 'name' column (regression guard for the H19 build)."""
        db = _VocabDB(
            drugs=[{"id": "d1", "brand_name": "Wegovy", "generic_name": "semaglutide"}],
            companies=[{"id": "c1", "name": "Novo Nordisk"}],
            aliases=[{"entity_type": "drug", "entity_id": "d1", "alias_text": "Ozempic"}],
        )
        vocab = load_vocabulary(db)
        names = {(v.name_lower, v.entity_type, v.entity_id) for v in vocab}
        assert ("wegovy", "drug", "d1") in names
        assert ("semaglutide", "drug", "d1") in names
        assert ("ozempic", "drug", "d1") in names        # verified/high-conf alias
        assert ("novo nordisk", "company", "c1") in names
        # longest-first ordering preserved
        assert [len(v.name_lower) for v in vocab] == sorted(
            [len(v.name_lower) for v in vocab], reverse=True
        )

    def test_drops_short_and_numeric_names(self):
        db = _VocabDB(
            drugs=[{"id": "d1", "brand_name": "ABC", "generic_name": "123456"}],
            companies=[], aliases=[],
        )
        vocab = load_vocabulary(db)
        # "ABC" < MIN_NAME_LEN dropped; "123456" is numeric → dropped.
        assert vocab == []


class TestBackfill:
    def test_resolves_and_updates_orphaned_events(self):
        rows = [
            {"id": "e1", "event_type": "approval",
             "description": "FDA approves Foundayo", "title": None},
            {"id": "e2", "event_type": "ma_deal",
             "description": "Eli Lilly acquires a biotech", "title": None},
            {"id": "e3", "event_type": "trial_readout",
             "description": "Unknown molecule misses endpoint", "title": None},
        ]
        db = _FakeDB(rows)
        stats = backfill_orphaned_events(db, vocab=VOCAB, limit=10)
        assert stats["scanned"] == 3
        assert stats["resolved"] == 2          # e3 has no known entity
        assert stats["by_type"] == {"approval": 1, "ma_deal": 1}
        assert len(db.updates) == 2

    def test_drug_match_sets_drug_id(self):
        rows = [{"id": "e1", "event_type": "approval",
                 "description": "Foundayo approved", "title": None}]
        db = _FakeDB(rows)
        backfill_orphaned_events(db, vocab=VOCAB, limit=10)
        # UPDATE params: [eid, etype, name, drug_id, id]
        params = db.updates[0]
        assert params[1] == "drug"
        assert params[3] == "d-found"          # drug_id set for drug matches

    def test_company_match_leaves_drug_id_none(self):
        rows = [{"id": "e2", "event_type": "ma_deal",
                 "description": "Eli Lilly acquires a biotech", "title": None}]
        db = _FakeDB(rows)
        backfill_orphaned_events(db, vocab=VOCAB, limit=10)
        params = db.updates[0]
        assert params[1] == "company"
        assert params[3] is None               # no drug_id for company matches


class _UpdateReturningDB:
    """Fake DB for the set-based UPDATE…RETURNING path; returns N rows and
    captures the SQL so we can assert the canonical-only guard."""
    def __init__(self, returned_rows):
        self._rows = returned_rows
        self.sql_seen: list[str] = []

    def fetch_all(self, sql, params=None):
        self.sql_seen.append(sql)
        return self._rows


class TestDerivePrimaryFromDrugId:
    """D2-additive: ground events that already carry a canonical drug_id."""

    def test_derives_primary_entity_from_drug_id(self):
        db = _UpdateReturningDB([{"?column?": 1}, {"?column?": 1}])
        stats = derive_primary_from_drug_id(db, limit=10)
        assert stats == {"scanned": 2, "grounded": 2}
        # one set-based statement, guarding against merged drug rows
        sql = db.sql_seen[0].lower()
        assert "update market_events" in sql
        assert "record_status" in sql and "merged" in sql
        assert "primary_entity_id is null" in sql  # additive/idempotent

    def test_empty_when_nothing_to_ground(self):
        db = _UpdateReturningDB([])
        stats = derive_primary_from_drug_id(db)
        assert stats == {"scanned": 0, "grounded": 0}
