"""PB-1307 — tests for the temporal facts ledger.

Pure temporal logic (_valid_at) needs no DB; assert/supersede/facts_as_of use
a MagicMock DB in the established style. The headline behaviour is the
ANTICIPATORY fact: a future-dated fact is invisible today but visible when
queried as-of its effective date — what powers war-game "what if as-of X".
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

import pytest

from services.facts_ledger import (
    _valid_at,
    assert_fact,
    supersede_fact,
    facts_as_of,
    InvalidFact,
)

NOW = datetime(2026, 5, 22, tzinfo=timezone.utc)
JAN_2027 = datetime(2027, 1, 1, tzinfo=timezone.utc)


def _fact(**over):
    base = {
        "id": "f1", "kind": "point", "predicate": "fda_approval_date",
        "subject_entity_type": "drug", "subject_entity_id": "d1",
        "object_value": {"date": "2026-05-01"},
        "valid_from": datetime(2026, 5, 1, tzinfo=timezone.utc),
        "valid_to": None, "superseded_by": None,
    }
    base.update(over)
    return base


# ── _valid_at (pure temporal predicate) ───────────────────────────

class TestValidAt:
    def test_point_fact_valid_after_valid_from(self):
        f = _fact(valid_from=datetime(2026, 5, 1, tzinfo=timezone.utc))
        assert _valid_at(f, NOW) is True

    def test_point_fact_not_valid_before_valid_from(self):
        f = _fact(valid_from=datetime(2026, 6, 1, tzinfo=timezone.utc))
        assert _valid_at(f, NOW) is False

    def test_interval_fact_within_window(self):
        f = _fact(kind="interval",
                  valid_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
                  valid_to=datetime(2026, 12, 31, tzinfo=timezone.utc))
        assert _valid_at(f, NOW) is True

    def test_interval_fact_after_window(self):
        f = _fact(kind="interval",
                  valid_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
                  valid_to=datetime(2025, 12, 31, tzinfo=timezone.utc))
        assert _valid_at(f, NOW) is False

    def test_anticipatory_fact_invisible_today_visible_as_of_future(self):
        # "Novo WAC = $675 effective 2027-01-01"
        f = _fact(kind="anticipatory", predicate="wac_usd",
                  valid_from=JAN_2027, object_value={"wac": 675})
        assert _valid_at(f, NOW) is False          # not yet
        assert _valid_at(f, JAN_2027) is True       # as-of effective date
        assert _valid_at(f, JAN_2027 + timedelta(days=90)) is True

    def test_superseded_fact_never_valid(self):
        f = _fact(superseded_by="f2")
        assert _valid_at(f, NOW) is False

    def test_null_valid_from_is_always_valid_until_valid_to(self):
        f = _fact(valid_from=None, valid_to=None)
        assert _valid_at(f, NOW) is True


# ── assert_fact ───────────────────────────────────────────────────

def _db():
    db = MagicMock()
    db.execute = MagicMock()
    db.fetch_all = MagicMock(return_value=[])
    db.fetch_one = MagicMock(return_value=None)
    return db


class TestAssertFact:
    def test_inserts_and_returns_id(self):
        db = _db()
        fid = assert_fact(
            db, kind="point", predicate="fda_approval_date",
            subject_entity_type="drug", subject_entity_id="d1",
            object_value={"date": "2026-05-01"},
            valid_from=datetime(2026, 5, 1, tzinfo=timezone.utc),
        )
        assert fid
        assert db.execute.called

    def test_rejects_bad_kind(self):
        with pytest.raises(InvalidFact):
            assert_fact(_db(), kind="guess", predicate="x",
                        subject_entity_type="drug", subject_entity_id="d1",
                        object_value={})

    def test_rejects_out_of_range_confidence(self):
        with pytest.raises(InvalidFact):
            assert_fact(_db(), kind="point", predicate="x",
                        subject_entity_type="drug", subject_entity_id="d1",
                        object_value={}, confidence=1.5)

    def test_interval_requires_valid_to(self):
        with pytest.raises(InvalidFact):
            assert_fact(_db(), kind="interval", predicate="x",
                        subject_entity_type="drug", subject_entity_id="d1",
                        object_value={}, valid_from=NOW)  # no valid_to

    def test_anticipatory_requires_valid_from(self):
        with pytest.raises(InvalidFact):
            assert_fact(_db(), kind="anticipatory", predicate="x",
                        subject_entity_type="drug", subject_entity_id="d1",
                        object_value={})  # no valid_from


# ── supersede_fact ────────────────────────────────────────────────

class TestSupersede:
    def test_inserts_new_and_marks_old(self):
        db = _db()
        new_id = supersede_fact(
            db, "old-id", kind="point", predicate="wac_usd",
            subject_entity_type="drug", subject_entity_id="d1",
            object_value={"wac": 700},
            valid_from=datetime(2026, 6, 1, tzinfo=timezone.utc),
        )
        assert new_id
        # two execute calls: insert new + update old.superseded_by
        joined = " ".join(str(c.args[0]).lower() for c in db.execute.call_args_list)
        assert "insert into facts" in joined
        assert "superseded_by" in joined and "update facts" in joined


# ── facts_as_of (temporal query) ──────────────────────────────────

class TestFactsAsOf:
    def _db_with(self, rows):
        db = MagicMock()
        db.fetch_all = MagicMock(return_value=rows)
        return db

    def test_excludes_future_anticipatory_when_as_of_now(self):
        rows = [
            _fact(id="a", kind="point", valid_from=datetime(2026, 1, 1, tzinfo=timezone.utc)),
            _fact(id="b", kind="anticipatory", valid_from=JAN_2027, object_value={"wac": 675}),
        ]
        out = facts_as_of(self._db_with(rows), "drug", "d1", as_of=NOW)
        ids = {f["id"] for f in out}
        assert "a" in ids and "b" not in ids

    def test_includes_anticipatory_when_as_of_future(self):
        rows = [
            _fact(id="b", kind="anticipatory", valid_from=JAN_2027, object_value={"wac": 675}),
        ]
        out = facts_as_of(self._db_with(rows), "drug", "d1", as_of=JAN_2027)
        assert {f["id"] for f in out} == {"b"}

    def test_excludes_superseded(self):
        rows = [_fact(id="a", superseded_by="z")]
        out = facts_as_of(self._db_with(rows), "drug", "d1", as_of=NOW)
        assert out == []
