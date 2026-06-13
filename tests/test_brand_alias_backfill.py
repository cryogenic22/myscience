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


class TestReverseRoundTrip:
    """The de-smear is reversible: --reverse must restore every cleared brand_name
    from the manifest and remove the inserted aliases. Untested reversibility is a
    silent-loss risk, so this exercises the actual _reverse path."""

    def _manifest(self, tmp_path, entries):
        import json
        p = tmp_path / "brand_desmear_manifest.json"
        p.write_text(json.dumps(entries), encoding="utf-8")
        return str(p)

    def test_reverse_restores_each_row_and_deletes_aliases(self, tmp_path, monkeypatch):
        import scripts.backfill_brand_aliases as m
        monkeypatch.setattr(m, "_MANIFEST", self._manifest(
            tmp_path, [{"id": "frag1", "brand_name": "Ozempic"},
                       {"id": "frag2", "brand_name": "Januvia"}]))
        db = MagicMock(); db.execute = MagicMock()
        stats = m._reverse(db, apply=True)
        assert stats["restored"] == 2
        calls = [(c.args[0], c.args[1]) for c in db.execute.call_args_list]
        restores = [p for sql, p in calls if "update drugs set brand_name = %s" in sql.lower()]
        assert ["Ozempic", "frag1"] in restores and ["Januvia", "frag2"] in restores
        deletes = [(sql, p) for sql, p in calls if "delete from entity_aliases" in sql.lower()]
        assert deletes and deletes[0][1] == [m.ALIAS_SOURCE]   # only our backfilled aliases

    def test_reverse_dry_run_writes_nothing(self, tmp_path, monkeypatch):
        import scripts.backfill_brand_aliases as m
        monkeypatch.setattr(m, "_MANIFEST", self._manifest(
            tmp_path, [{"id": "frag1", "brand_name": "Ozempic"}]))
        db = MagicMock(); db.execute = MagicMock()
        stats = m._reverse(db, apply=False)
        assert stats["restored"] == 1          # counts what WOULD restore
        db.execute.assert_not_called()         # but writes nothing

    def test_reverse_missing_manifest_is_safe(self, tmp_path, monkeypatch):
        import scripts.backfill_brand_aliases as m
        monkeypatch.setattr(m, "_MANIFEST", str(tmp_path / "does_not_exist.json"))
        db = MagicMock(); db.execute = MagicMock()
        assert m._reverse(db, apply=True) == {"restored": 0}   # no raise, no writes
        db.execute.assert_not_called()
