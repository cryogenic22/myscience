"""A1 — tests for fact assertion on ingest (spine convergence Phase A).

Pure mapping (event_to_fact) needs no DB. Idempotency + backfill use a
MagicMock DB in the established style: _fact_exists uses db.fetch_all,
facts_ledger.assert_fact uses db.fetch_one — distinct methods so the two
calls don't collide in mocks. See specs/SPEC_A1_fact_assertion_on_ingest.md.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

import services.fact_ingest as fi
from services.fact_ingest import (
    event_to_fact,
    assert_event_fact,
    backfill_facts_from_events,
)

NOW = datetime.now(timezone.utc)
FUTURE = NOW + timedelta(days=400)


def _event(**over):
    base = {
        "id": "evt-1",
        "event_type": "approval",
        "description": "FDA approves drug X for obesity",
        "source_url": "https://fda.gov/x",
        "source_feed": "fda_press",
        "event_date": datetime(2026, 3, 1, tzinfo=timezone.utc),
        "created_at": datetime(2026, 3, 2, tzinfo=timezone.utc),
        "entity_type": "drug",
        "entity_id": "wegovy-demo",
        "trust_score": 0.9,
    }
    base.update(over)
    return base


# ── event_to_fact (pure) ───────────────────────────────────────────

class TestEventToFact:
    def test_approval_maps_to_regulatory_approval_point_fact(self):
        d = event_to_fact(_event())
        assert d is not None
        assert d.predicate == "regulatory_approval"
        assert d.kind == "point"
        assert d.subject_entity_type == "drug"
        assert d.subject_entity_id == "wegovy-demo"
        assert d.confidence == 0.9
        assert d.object_value["event_id"] == "evt-1"
        assert d.object_value["source_url"] == "https://fda.gov/x"

    def test_future_dated_event_is_anticipatory_with_future_valid_from(self):
        d = event_to_fact(_event(event_type="pricing", event_date=FUTURE))
        assert d is not None
        assert d.predicate == "pricing_intent"
        assert d.kind == "anticipatory"
        assert d.valid_from == FUTURE

    def test_missing_subject_returns_none(self):
        assert event_to_fact(_event(entity_id=None)) is None
        assert event_to_fact(_event(entity_type=None)) is None

    def test_unknown_event_type_falls_back_to_market_event(self):
        d = event_to_fact(_event(event_type="something_new"))
        assert d.predicate == "market_event"
        assert d.kind == "point"

    def test_bad_trust_score_defaults_to_half(self):
        d = event_to_fact(_event(trust_score=None))
        assert d.confidence == 0.5
        d2 = event_to_fact(_event(trust_score=5.0))  # out of range → clamped
        assert d2.confidence == 1.0


# ── assert_event_fact (idempotent) ─────────────────────────────────

class TestAssertEventFact:
    def test_asserts_when_not_existing(self):
        db = MagicMock()
        db.fetch_all.return_value = []              # _fact_exists → no
        db.fetch_one.return_value = {"id": "new-fact"}  # assert_fact insert
        fid = assert_event_fact(db, _event())
        assert fid == "new-fact"

    def test_skips_when_already_existing(self):
        db = MagicMock()
        db.fetch_all.return_value = [{"id": "existing"}]  # _fact_exists → yes
        db.fetch_one.return_value = {"id": "should-not-be-used"}
        fid = assert_event_fact(db, _event())
        assert fid is None  # skipped — idempotent

    def test_no_subject_returns_none_without_db_write(self):
        db = MagicMock()
        fid = assert_event_fact(db, _event(entity_id=None))
        assert fid is None
        db.fetch_one.assert_not_called()


# ── backfill_facts_from_events ─────────────────────────────────────

class TestBackfill:
    def test_counts_asserted_and_skipped(self, monkeypatch):
        events = [_event(id="1"), _event(id="2", entity_id=None), _event(id="3")]
        monkeypatch.setattr(fi, "_fetch_events", lambda *a, **k: events)
        db = MagicMock()
        db.fetch_all.return_value = []              # nothing exists yet
        db.fetch_one.return_value = {"id": "x"}
        stats = backfill_facts_from_events(db)
        assert stats.scanned == 3
        assert stats.asserted == 2
        assert stats.skipped_no_subject == 1
        assert stats.skipped_existing == 0

    def test_counts_skipped_existing(self, monkeypatch):
        events = [_event(id="1"), _event(id="2")]
        monkeypatch.setattr(fi, "_fetch_events", lambda *a, **k: events)
        db = MagicMock()
        db.fetch_all.return_value = [{"id": "existing"}]  # all already present
        stats = backfill_facts_from_events(db)
        assert stats.scanned == 2
        assert stats.asserted == 0
        assert stats.skipped_existing == 2
