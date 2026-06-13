"""Loop 2b (Helix temporal) — epistemic timestamps + fair-hindsight as-of (OQ6).

facts_as_of filters WORLD validity (valid_from/valid_to) only, so a fact the
system learned AFTER a date still appears "as of" that date — blaming the team
for knowledge that did not exist yet. facts_known_as_of adds the epistemic filter
(detected_at <= as_of). This pins the OQ6 gate: as-of reconstruction must not
leak later-learned knowledge into the past.
"""

from __future__ import annotations

from datetime import datetime, timezone

from services.facts_ledger import _known_at, facts_known_as_of, facts_as_of


def _dt(s):
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def _fact(valid_from, detected_at, asserted_at=None, fid="f1"):
    return {
        "id": fid, "kind": "point", "predicate": "regulatory_approval",
        "subject_entity_type": "drug", "subject_entity_id": "d1",
        "object_value": {}, "valid_from": _dt(valid_from), "valid_to": None,
        "asserted_at": _dt(asserted_at) if asserted_at else None,
        "detected_at": _dt(detected_at) if detected_at else None,
        "superseded_by": None,
    }


class TestKnownAtPredicate:
    def test_detected_before_as_of_is_known(self):
        f = _fact("2026-01-01", detected_at="2026-02-01")
        assert _known_at(f, _dt("2026-03-01")) is True

    def test_detected_after_as_of_is_not_known(self):
        # the world-fact was true since Jan, but we only learned it in March
        f = _fact("2026-01-01", detected_at="2026-03-15")
        assert _known_at(f, _dt("2026-03-01")) is False

    def test_falls_back_to_asserted_at_when_detected_null(self):
        f = _fact("2026-01-01", detected_at=None, asserted_at="2026-03-15")
        assert _known_at(f, _dt("2026-03-01")) is False

    def test_null_both_treated_as_always_known(self):
        f = _fact("2026-01-01", detected_at=None, asserted_at=None)
        assert _known_at(f, _dt("2026-03-01")) is True


class _DB:
    def __init__(self, rows):
        self._rows = rows

    def fetch_all(self, sql, params=None):
        return list(self._rows)


def test_facts_known_as_of_excludes_later_learned_fact():
    # A fact valid since Jan but detected mid-March.
    rows = [_fact("2026-01-01", detected_at="2026-03-15", fid="late")]
    db = _DB(rows)
    as_of = _dt("2026-03-01")
    # facts_as_of (world-validity only) WOULD include it — the bug.
    assert any(r["id"] == "late" for r in facts_as_of(db, "drug", "d1", as_of))
    # facts_known_as_of excludes it — fair hindsight (OQ6).
    assert not any(r["id"] == "late" for r in facts_known_as_of(db, "drug", "d1", as_of))


def test_facts_known_as_of_includes_timely_fact():
    rows = [_fact("2026-01-01", detected_at="2026-02-01", fid="timely")]
    db = _DB(rows)
    out = facts_known_as_of(db, "drug", "d1", _dt("2026-03-01"))
    assert [r["id"] for r in out] == ["timely"]
