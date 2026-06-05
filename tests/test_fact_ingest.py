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
        # No entity_id AND no drug_id → genuinely no subject.
        assert event_to_fact(_event(entity_id=None, drug_id=None)) is None
        assert event_to_fact(_event(entity_type=None, entity_id=None, drug_id=None)) is None

    def test_falls_back_to_drug_id_when_primary_entity_absent(self):
        # Real prod shape (1 Jun 2026): primary_entity_id NULL, drug_id set for
        # 96% of events. Must produce a drug-subject fact, not skip.
        d = event_to_fact(_event(entity_id=None, entity_type=None, drug_id="drug-123"))
        assert d is not None
        assert d.subject_entity_type == "drug"
        assert d.subject_entity_id == "drug-123"

    def test_explicit_entity_id_wins_over_drug_id(self):
        d = event_to_fact(_event(entity_id="ent-9", entity_type="company", drug_id="drug-123"))
        assert d.subject_entity_id == "ent-9"
        assert d.subject_entity_type == "company"

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

class TestFetchSqlColumns:
    """Regression for the A1 bug: the backfill read market_events directly via
    _FETCH_SQL and selected columns that do not exist on the table
    (source_feed/entity_id/entity_type), throwing UndefinedColumn so zero facts
    were ever asserted. The existing backfill tests monkeypatched _fetch_events,
    so they never exercised the SQL — fake-DB blindness. These tests pin the SQL
    against the REAL market_events schema (verified on Railway 1 Jun 2026)."""

    REAL_COLUMNS = {
        "id", "drug_id", "event_type", "event_date", "description",
        "impact_score", "source_api", "source_url", "etl_run_id",
        "retrieved_at", "created_at", "content_hash", "last_verified_at",
        "record_status", "quality_score", "source_tier", "trust_score",
        "primary_entity_type", "primary_entity_name", "status", "event_hash",
        "corroborating_sources", "verified_at", "primary_entity_id",
    }
    # Columns event_to_fact() reads off each row dict (the alias targets).
    EXPECTED_ALIASES = {"entity_id", "entity_type", "source_feed"}

    def test_fetch_sql_does_not_select_nonexistent_columns(self):
        import re
        sql = fi._FETCH_SQL.lower()
        # The phantom names may only appear as alias TARGETS (AS x), never as
        # bare selected columns. Word-boundary match so primary_entity_id does
        # not falsely flag the 'entity_id' substring.
        for phantom in ("source_feed", "entity_id", "entity_type"):
            for m in re.finditer(r"(?<![a-z_])" + phantom + r"(?![a-z_])", sql):
                preceding = sql[max(0, m.start() - 4):m.start()]
                assert "as " in preceding, (
                    f"_FETCH_SQL selects phantom column '{phantom}' as a raw "
                    f"market_events column (not an alias) — it does not exist"
                )

    def test_fetch_sql_uses_real_subject_columns(self):
        sql = fi._FETCH_SQL.lower()
        assert "primary_entity_id" in sql, "must read the real subject id column"
        assert "primary_entity_type" in sql, "must read the real subject type column"
        assert "source_api" in sql, "must read the real feed column"

    def test_fetch_sql_aliases_to_event_to_fact_keys(self):
        """event_to_fact reads entity_id/entity_type/source_feed off the row;
        the SQL must alias the real columns to those names."""
        sql = fi._FETCH_SQL.lower()
        assert "as entity_id" in sql
        assert "as entity_type" in sql
        assert "as source_feed" in sql

    def test_active_only_filters_superseded_events(self):
        """D2: active_only=True must exclude soft-deleted (superseded) events so
        a post-dedup re-emit never re-grounds a dropped duplicate."""
        captured = {}

        class _DB:
            def fetch_all(self, sql, params=None):
                captured["sql"] = sql.lower()
                return []

        fi._fetch_events(_DB(), None, None, None, active_only=True)
        assert "record_status is distinct from 'superseded'" in captured["sql"]
        # default (active_only=False) must NOT add the filter
        fi._fetch_events(_DB(), None, None, None)
        assert "record_status" not in captured["sql"]


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
