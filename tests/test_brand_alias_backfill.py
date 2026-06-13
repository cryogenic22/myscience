"""A1 (eval handoff Part A1) — brand→generic alias backfill + brand_name de-smear.

`brand_name` is over-applied: e.g. "Ozempic" sits on ~30 semaglutide fragment rows,
not just the rich canonical. So (a) the resolver can't pick a single brand→generic
target, and (b) the unique index on entity_aliases(entity_type, alias_text,
source_type) makes a per-row self-alias impossible. The fix keeps brand_name on the
ONE richest active canonical, clears it from the rest (reversibly), and aliases the
brand to that canonical. Lane-1, DB-free.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from scripts.backfill_brand_aliases import choose_canonical, ALIAS_SOURCE


def _row(id, status, richness):
    return {"id": id, "record_status": status, "richness": richness}


class TestChooseCanonical:
    def test_picks_richest_active_row(self):
        rows = [
            _row("frag1", "active", 35),
            _row("canon", "active", 1049),
            _row("ex", "excluded", 8),
        ]
        assert choose_canonical(rows) == "canon"

    def test_prefers_active_over_richer_inactive(self):
        # an excluded row may be "richer" but must never be the canonical if an
        # active row exists (resolution must land on an active row)
        rows = [
            _row("ex", "excluded", 500),
            _row("active", "active", 50),
        ]
        assert choose_canonical(rows) == "active"

    def test_falls_back_to_richest_when_none_active(self):
        # nothing active: keep the brand on the richest row rather than lose it
        rows = [
            _row("sup", "superseded", 0),
            _row("ex", "excluded", 12),
        ]
        assert choose_canonical(rows) == "ex"

    def test_none_when_empty(self):
        assert choose_canonical([]) is None


class TestAliasInsertIsIdempotent:
    def test_insert_uses_on_conflict(self):
        from scripts.backfill_brand_aliases import _insert_alias
        db = MagicMock()
        db.execute = MagicMock()
        _insert_alias(db, "Ozempic", "canon-id")
        sql, params = db.execute.call_args[0]
        assert "insert into entity_aliases" in sql.lower()
        assert "on conflict" in sql.lower() and "do nothing" in sql.lower()
        assert ALIAS_SOURCE in params and "Ozempic" in params and "canon-id" in params


class TestDesmearReversible:
    def test_clear_records_old_value_for_reversal(self):
        from scripts.backfill_brand_aliases import _clear_brand
        db = MagicMock(); db.execute = MagicMock()
        manifest = []
        _clear_brand(db, "frag1", "Ozempic", manifest)
        # manifest captures (id, old_brand) so --reverse can restore it
        assert {"id": "frag1", "brand_name": "Ozempic"} in manifest
        sql, params = db.execute.call_args[0]
        assert "update drugs set brand_name = null" in sql.lower()
        assert "frag1" in params
