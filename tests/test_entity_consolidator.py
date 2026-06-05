"""Tests for EntityConsolidator drug-merge enhancements (A6).

Covers the changes that make consolidation SAFE + complete: text-keyed spine
repointing (facts / signals), richness-based canonical selection, combo-safe
normalizer grouping, and FK-table existence filtering. Uses a recording fake DB
(records every execute) in the established mock style.
"""

from __future__ import annotations

from contextlib import contextmanager

from integration.entity_consolidator import EntityConsolidator


class _FakeDB:
    """Records execute() calls; routes fetch_* by SQL substring."""

    def __init__(self, *, fk_tables=None, richness=None, group_rows=None,
                 drug_records=None):
        self.executed: list[tuple[str, list]] = []
        self._fk_tables = fk_tables if fk_tables is not None else []
        self._richness = richness or {}
        self._group_rows = group_rows or []
        self._drug_records = drug_records or []

    @contextmanager
    def transaction(self):
        yield

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetch_all(self, sql, params=None):
        s = sql.lower()
        if "information_schema.columns" in s:
            return [{"table_name": t} for t in self._fk_tables]
        if "array_agg(id)" in s:  # exact-name grouping
            return self._group_rows
        if "select id, generic_name from drugs" in s:  # normalizer grouping
            return self._group_rows
        if "select * from drugs where id" in s:
            return self._drug_records
        if "from entity_links" in s:
            return []
        return []

    def fetch_one(self, sql, params=None):
        s = sql.lower()
        if "richness" in s:
            return {"richness": self._richness.get(str(params[0]), 0)}
        return None


def _executed_sql(db) -> str:
    return "\n".join(sql.lower() for sql, _ in db.executed)


# ── text-keyed spine repointing (the safety fix) ───────────────────

class TestMergeRepointsSpine:
    def test_merge_repoints_facts_and_signals(self):
        db = _FakeDB(fk_tables=["clinical_trials", "market_events"])
        c = EntityConsolidator(db)
        c._drug_fk_tables = ["clinical_trials", "market_events"]
        c._merge_drug({"id": "CANON"}, {"id": "DUP", "generic_name": "x"})

        # facts.subject_entity_id repointed DUP -> CANON
        facts_calls = [(s, p) for s, p in db.executed
                       if "update facts set subject_entity_id" in s.lower()]
        assert facts_calls, "facts.subject_entity_id must be repointed"
        assert facts_calls[0][1] == ["CANON", "DUP"]

        # signals.primary_entity_id repointed
        sig_calls = [(s, p) for s, p in db.executed
                     if "update signals set primary_entity_id" in s.lower()]
        assert sig_calls and sig_calls[0][1] == ["CANON", "DUP"]

    def test_merge_repoints_only_existing_fk_tables(self):
        db = _FakeDB()
        c = EntityConsolidator(db)
        c._drug_fk_tables = ["clinical_trials"]  # patents excluded
        c._merge_drug({"id": "CANON"}, {"id": "DUP", "generic_name": "x"})
        sql = _executed_sql(db)
        assert "update clinical_trials set drug_id" in sql
        assert "update patents set drug_id" not in sql

    def test_merge_marks_duplicate_superseded(self):
        db = _FakeDB()
        c = EntityConsolidator(db)
        c._drug_fk_tables = []
        c._merge_drug({"id": "CANON"}, {"id": "DUP", "generic_name": "x"})
        assert "update drugs set record_status = 'superseded'" in _executed_sql(db)

    def test_bioactivities_is_a_repointable_fk_table(self):
        """D2: a merged drug's ChEMBL bioactivities must repoint to the
        canonical, not orphan on the superseded row."""
        from integration.entity_consolidator import DRUG_FK_TABLES
        assert "bioactivities" in DRUG_FK_TABLES
        db = _FakeDB(fk_tables=["bioactivities"])
        c = EntityConsolidator(db)
        c._drug_fk_tables = ["bioactivities"]
        c._merge_drug({"id": "CANON"}, {"id": "DUP", "generic_name": "x"})
        assert "update bioactivities set drug_id" in _executed_sql(db)


# ── richness-based canonical selection ─────────────────────────────

class TestRichnessCanonical:
    def test_richest_row_becomes_canonical(self):
        # DUP-RICH has 200 richness, DUP-POOR has 1 → rich wins, dry-run plan.
        group_rows = [{"norm_name": "semaglutide", "ids": ["poor", "rich"]}]
        drug_records = [
            {"id": "poor", "generic_name": "semaglutide", "created_at": "2020"},
            {"id": "rich", "generic_name": "semaglutide", "created_at": "2021"},
        ]
        db = _FakeDB(group_rows=group_rows, drug_records=drug_records,
                     richness={"poor": 1, "rich": 200})
        c = EntityConsolidator(db, rank_by_richness=True, dry_run=True)
        stats = c.consolidate_drugs()
        assert stats["groups_found"] == 1
        plan = stats["plan"][0]
        assert plan["canonical"] == "rich"
        assert plan["merge"][0]["id"] == "poor"


# ── combo-safe normalizer grouping ─────────────────────────────────

class TestNormalizerGrouping:
    def test_normalizer_groups_variants_but_not_combos(self):
        from scripts.consolidate_drugs import _normalize_drug_name

        group_rows = [
            {"id": "a", "generic_name": "Sitagliptin"},
            {"id": "b", "generic_name": "sitagliptin phosphate"},
            {"id": "c", "generic_name": "sitagliptin and metformin"},  # combo
        ]
        db = _FakeDB(group_rows=group_rows)
        c = EntityConsolidator(db, drug_name_normalizer=_normalize_drug_name)
        groups = c._drug_duplicate_groups()
        as_dict = {n: set(ids) for n, ids in groups}
        # a + b collapse to 'sitagliptin'; the combo is NOT pulled in
        assert any(ids == {"a", "b"} for ids in as_dict.values())
        assert all("c" not in ids for ids in as_dict.values())
