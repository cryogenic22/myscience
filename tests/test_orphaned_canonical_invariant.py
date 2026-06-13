"""Conservation invariant — no orphaned drug canonical (fail-loud detector).

Lane-1: the pure `find_orphaned` logic (a name with evidence but no active row is
orphaned). Lane-2 (behind DATABASE_URL): the live prod invariant — there must be
zero orphaned canonicals; a recurrence (a scheduled consolidation re-demoting a
canonical with no active survivor) fails this LOUDLY instead of rotting silently.
"""
import os

import pytest

from scripts.check_orphaned_canonicals import find_orphaned, scan


# ── Lane-1: pure logic ──────────────────────────────────────────────────────

def test_active_row_with_evidence_is_not_orphaned():
    rows = [{"name": "valsartan", "status": "active", "richness": 80}]
    assert find_orphaned(rows) == []


def test_evidence_but_no_active_row_is_orphaned():
    rows = [
        {"name": "valsartan", "status": "merged", "richness": 60},
        {"name": "valsartan", "status": "superseded", "richness": 20},
    ]
    out = find_orphaned(rows)
    assert len(out) == 1 and out[0]["name"] == "valsartan"
    assert out[0]["evidence"] == 80


def test_an_active_sibling_clears_the_orphan():
    rows = [
        {"name": "valsartan", "status": "merged", "richness": 60},
        {"name": "valsartan", "status": "active", "richness": 5},
    ]
    assert find_orphaned(rows) == []  # an active row holds some evidence → not orphaned


def test_below_floor_is_not_flagged():
    rows = [{"name": "obscure", "status": "merged", "richness": 3}]
    assert find_orphaned(rows) == []


def test_zero_evidence_excluded_row_is_not_flagged():
    rows = [{"name": "junk", "status": "excluded", "richness": 0}]
    assert find_orphaned(rows) == []


# ── Lane-2: live prod invariant (skipped without a DB) ──────────────────────

@pytest.mark.skipif(not os.environ.get("DATABASE_URL"),
                    reason="Lane-2: requires DATABASE_URL (prod invariant)")
def test_no_orphaned_canonicals_on_prod():
    from db import Database
    db = Database(os.environ["DATABASE_URL"])
    db.connect()
    orphaned = scan(db)
    assert not orphaned, (
        f"{len(orphaned)} orphaned canonical(s) — a drug with evidence but no "
        f"active row (silent degradation recurrence): "
        f"{[o['name'] for o in orphaned[:10]]}")
