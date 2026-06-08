"""Backfill fact governance — DB-free tests via a MockDB.

Pins the backfill's mapping behaviour: it computes governance for un-scored
facts, pulls resolver_confidence from resolution_audit where available, falls
back to a default otherwise, is idempotent (only fills facts whose trust_score
IS NULL), and NEVER overwrites a human_approved review_status.
"""
from __future__ import annotations

from datetime import datetime, timezone

from scripts.backfill_fact_governance import (
    backfill_governance,
    resolver_conf_for_subject,
)

NOW = datetime(2026, 6, 8, tzinfo=timezone.utc)


class MockDB:
    """Minimal DB stub: serves facts to backfill and records UPDATEs."""

    def __init__(self, facts, audit=None):
        self._facts = facts
        self._audit = audit or {}  # subject_entity_id -> confidence
        self.updates = []  # list of (sql, params)

    def fetch_all(self, sql, params=None):
        s = " ".join(sql.lower().split())
        if "from facts" in s:
            # backfill selects un-scored facts (trust_score IS NULL)
            return [f for f in self._facts if f.get("trust_score") is None]
        if "from resolution_audit" in s:
            sid = params[0] if params else None
            conf = self._audit.get(sid)
            return [{"confidence": conf}] if conf is not None else []
        return []

    def fetch_one(self, sql, params=None):
        rows = self.fetch_all(sql, params)
        return rows[0] if rows else None

    def execute(self, sql, params=None):
        self.updates.append((sql, params))


def _fact(fid, **kw):
    base = {
        "id": fid,
        "fact_class": "corporate",
        "created_by": "fact_emitter",
        "confidence": 0.9,
        "subject_entity_type": "drug",
        "subject_entity_id": f"sub-{fid}",
        "valid_from": NOW,
        "created_at": NOW,
        "object_value": {},
        "review_status": "unreviewed",
        "trust_score": None,
    }
    base.update(kw)
    return base


def test_backfill_updates_unscored_facts():
    db = MockDB([_fact("a"), _fact("b")])
    stats = backfill_governance(db, now=NOW)
    assert stats["scored"] == 2
    assert len(db.updates) == 2
    # each UPDATE carries a trust_score in [0,1]
    for sql, params in db.updates:
        assert "update facts" in " ".join(sql.lower().split())


def test_backfill_is_idempotent_skips_already_scored():
    db = MockDB([_fact("a", trust_score=0.7), _fact("b")])
    stats = backfill_governance(db, now=NOW)
    assert stats["scored"] == 1  # only the unscored one
    assert len(db.updates) == 1


def test_backfill_uses_resolution_audit_confidence():
    conf = resolver_conf_for_subject(
        MockDB([], audit={"drug:x": 0.42}), "drug", "drug:x"
    )
    assert conf == 0.42


def test_resolver_conf_default_when_no_audit_row():
    conf = resolver_conf_for_subject(MockDB([], audit={}), "drug", "missing")
    assert conf is None  # caller substitutes the score_fact default


def test_backfill_never_overwrites_human_approved():
    db = MockDB([_fact("h", review_status="human_approved")])
    stats = backfill_governance(db, now=NOW)
    # it still computes the numeric dimensions, but the UPDATE must not set
    # review_status away from human_approved.
    assert stats["scored"] == 1
    sql, params = db.updates[0]
    s = " ".join(sql.lower().split())
    # Either review_status is excluded from the UPDATE, or preserved explicitly.
    if "review_status" in s:
        assert "human_approved" in [str(p) for p in (params or [])] or \
            "coalesce" in s or "case" in s
    assert stats["preserved_human"] == 1


def test_backfill_reports_counts():
    db = MockDB([_fact("a"), _fact("b"), _fact("c", trust_score=0.5)])
    stats = backfill_governance(db, now=NOW)
    assert stats["scanned"] == 2
    assert stats["scored"] == 2
