"""D2 — market_events dedup planning + execution (SPEC_DATA_001 §D2).

Pure-planning tests (no DB) cover survivor selection + collapse grouping. A
recording-fake-DB test covers the soft-delete + fact-repoint + hash-backfill
execution order (the destructive but reversible path), in the established mock
style (tests/test_entity_consolidator.py).
"""

from __future__ import annotations

from contextlib import contextmanager

from scripts.dedup_market_events import pick_survivor, plan_collapse, run


# ── pure planning ──────────────────────────────────────────────────────────

def test_pick_survivor_prefers_highest_trust():
    rows = [
        {"id": "a", "trust_score": 0.5, "retrieved_at": "2026-01-01"},
        {"id": "b", "trust_score": 0.9, "retrieved_at": "2025-01-01"},
    ]
    assert pick_survivor(rows)["id"] == "b"


def test_pick_survivor_breaks_ties_by_newest():
    rows = [
        {"id": "old", "trust_score": 0.5, "retrieved_at": "2025-01-01"},
        {"id": "new", "trust_score": 0.5, "retrieved_at": "2026-06-01"},
    ]
    assert pick_survivor(rows)["id"] == "new"


def test_plan_collapse_keeps_one_per_group():
    rows = [
        {"id": "1", "primary_entity_id": "d1", "event_type": "recall",
         "description": "x", "trust_score": 0.5, "retrieved_at": "2026-01-01"},
        {"id": "2", "primary_entity_id": "d1", "event_type": "recall",
         "description": "x", "trust_score": 0.5, "retrieved_at": "2026-02-01"},
        {"id": "3", "primary_entity_id": "d1", "event_type": "recall",
         "description": "x", "trust_score": 0.5, "retrieved_at": "2026-03-01"},
    ]
    superseded, dup_to_canon = plan_collapse(rows)
    assert len(superseded) == 2          # 3 copies → 2 dropped
    assert set(dup_to_canon.values()) == {"3"}  # newest survives
    assert dup_to_canon == {"1": "3", "2": "3"}


def test_plan_collapse_groups_null_primary_entity_separately():
    # NULL-primary rows still collapse among themselves by (type, description).
    rows = [
        {"id": "a", "primary_entity_id": None, "event_type": "macro",
         "description": "fed news", "trust_score": 0.5, "retrieved_at": "2026-01-01"},
        {"id": "b", "primary_entity_id": None, "event_type": "macro",
         "description": "fed news", "trust_score": 0.5, "retrieved_at": "2026-02-01"},
        {"id": "c", "primary_entity_id": None, "event_type": "macro",
         "description": "other", "trust_score": 0.5, "retrieved_at": "2026-01-01"},
    ]
    superseded, dup_to_canon = plan_collapse(rows)
    assert superseded == ["a"]           # only the duplicate "fed news" pair collapses
    assert dup_to_canon == {"a": "b"}


def test_plan_collapse_singletons_untouched():
    rows = [
        {"id": "1", "primary_entity_id": "d1", "event_type": "approval",
         "description": "y", "trust_score": 0.5, "retrieved_at": "2026-01-01"},
        {"id": "2", "primary_entity_id": "d2", "event_type": "approval",
         "description": "z", "trust_score": 0.5, "retrieved_at": "2026-01-01"},
    ]
    superseded, dup_to_canon = plan_collapse(rows)
    assert superseded == [] and dup_to_canon == {}


# ── execution (recording fake DB) ──────────────────────────────────────────

class _FakeDB:
    """Records execute() calls; routes fetch_* by SQL substring."""

    def __init__(self, active_rows, dup_facts=None):
        self.executed: list[tuple[str, list]] = []
        self._active = active_rows
        self._dup_facts = dup_facts or []

    @contextmanager
    def transaction(self):
        yield

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetch_all(self, sql, params=None):
        s = sql.lower()
        if "distinct object_value->>'event_id'" in s:
            # referenced fact event_ids: claim the dup "1" has a referencing fact
            return [{"eid": "1"}]
        if "distinct event_id as eid from signals" in s:
            return []  # no signals reference events in this fixture
        if "from market_events where" in s and "event_hash is null" in s:
            return []  # no survivors need a hash in this fixture
        if "from market_events where" in s:
            return self._active
        if "predicate = 'market_event'" in s and "order by asserted_at" in s:
            return self._dup_facts
        return []

    def fetch_one(self, sql, params=None):
        return {"c": 0}


def _norm(sql: str) -> str:
    """Collapse whitespace so multi-line SQL matches a flat substring check."""
    return " ".join(sql.lower().split())


def _sql(db) -> str:
    return "\n".join(s.lower() for s, _ in db.executed)


def test_run_is_map_driven_and_soft_deletes():
    """The rewritten run() drives every repoint + the soft-delete from ONE
    server-side dup→survivor map (me_map), so they can never disagree. It must:
    build the map, repoint facts/signals/links FROM it, soft-delete (not hard),
    and collapse duplicate facts."""
    rows = [
        {"id": "1", "primary_entity_id": "d1", "event_type": "recall",
         "description": "x", "trust_score": 0.5, "retrieved_at": "2026-01-01"},
        {"id": "2", "primary_entity_id": "d1", "event_type": "recall",
         "description": "x", "trust_score": 0.5, "retrieved_at": "2026-02-01"},
    ]
    db = _FakeDB(rows)
    stats = run(db, reemit=False)
    flat = _norm("\n".join(s for s, _ in db.executed))
    # one source of truth: the dup→survivor map
    assert "create temp table me_map" in flat
    # facts/signals/links all repoint FROM me_map (consistent survivor)
    assert "update facts f set object_value" in flat and "from me_map" in flat
    assert "update signals s set event_id" in flat
    assert "update entity_links el set source_entity_id = m.survivor" in flat
    assert "update entity_links el set target_entity_id = m.survivor" in flat
    # soft-delete the dups from the same map — reversible, never hard-delete
    assert "update market_events me set record_status = 'superseded'" in flat
    assert "delete from market_events" not in flat
    # collapse duplicate market_event facts (append-only supersede)
    assert "update facts f set superseded_by = r.keeper" in flat
    assert stats["to_supersede"] == 1
    assert stats["survivors"] == 1


def test_run_links_dedup_before_repoint():
    """entity_links repoint must DELETE colliding dup-source links before the
    bulk UPDATE (idx_links_unique), or the survivor would get a duplicate edge.
    Both source and target sides are handled."""
    rows = [
        {"id": "1", "primary_entity_id": "d1", "event_type": "recall",
         "description": "x", "trust_score": 0.5, "retrieved_at": "2026-01-01"},
        {"id": "2", "primary_entity_id": "d1", "event_type": "recall",
         "description": "x", "trust_score": 0.5, "retrieved_at": "2026-02-01"},
    ]
    db = _FakeDB(rows)
    run(db, reemit=False)
    flat = _norm("\n".join(s for s, _ in db.executed))
    assert "delete from entity_links el using to_del" in flat
    assert "row_number() over" in flat   # keep-one-per-(survivor,target,link_type)


def test_run_dry_run_writes_nothing():
    rows = [
        {"id": "1", "primary_entity_id": "d1", "event_type": "recall",
         "description": "x", "trust_score": 0.5, "retrieved_at": "2026-01-01"},
        {"id": "2", "primary_entity_id": "d1", "event_type": "recall",
         "description": "x", "trust_score": 0.5, "retrieved_at": "2026-02-01"},
    ]
    db = _FakeDB(rows)
    stats = run(db, dry_run=True)
    assert db.executed == []
    assert stats["to_supersede"] == 1
