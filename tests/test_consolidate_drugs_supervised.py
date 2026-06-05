"""D2 (drug-side) — supervised drug consolidation runner.

Tests the orphan-check coverage (every spine table) and the additive reground
SQL, in the recording-fake-DB style.
"""

from __future__ import annotations

from scripts.consolidate_drugs_supervised import (
    drug_orphans,
    reground_null_primary_events,
)


class _FakeDB:
    def __init__(self):
        self.executed: list[tuple[str, list]] = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetch_one(self, sql, params=None):
        return {"c": 0}


def test_drug_orphans_covers_every_spine_table():
    out = drug_orphans(_FakeDB())
    # text-keyed spine refs the generic FK loop misses
    assert "facts.subject_entity_id" in out
    assert "signals.primary_entity_id" in out
    assert "entity_links.drug" in out
    # FK tables incl. the newly-added bioactivities
    assert "bioactivities.drug_id" in out
    assert "clinical_trials.drug_id" in out
    # all zero in the fake (no superseded rows)
    assert all(v == 0 for v in out.values())


def test_reground_sets_primary_entity_id_from_drug_id_additively():
    db = _FakeDB()
    reground_null_primary_events(db)
    sql = "\n".join(s.lower() for s, _ in db.executed)
    assert "set primary_entity_id = me.drug_id::text" in sql
    # additive: only fills NULLs, never overwrites an existing primary_entity_id
    assert "where me.primary_entity_id is null" in sql
    # never touches superseded rows
    assert "record_status is distinct from 'superseded'" in sql
