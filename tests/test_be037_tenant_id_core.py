"""BE-37 — tenant_id on core entity tables.

Migration shape + backfill-script behaviour. The runtime WHERE-filter
middleware lives on BE-38; isolation tests on BE-39.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest


_TARGET_TABLES = ("drugs", "companies", "clinical_trials", "mechanisms_of_action")


# ════════════════════════════════════════════════════════════════════
# Migration 066 shape
# ════════════════════════════════════════════════════════════════════

class TestMigration066:
    def _migration_sql(self) -> str:
        path = (
            Path(__file__).parent.parent
            / "schema" / "migrations" / "066_tenant_id_core_entities.sql"
        )
        assert path.exists(), f"missing {path.name}"
        return path.read_text(encoding="utf-8").lower()

    def test_migration_exists(self):
        self._migration_sql()

    @pytest.mark.parametrize("table", _TARGET_TABLES)
    def test_adds_tenant_id_to_table(self, table):
        sql = self._migration_sql()
        # alter table <table> add column tenant_id
        assert table in sql, f"migration must mention {table}"
        # ALTER TABLE <table> ... ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'public'
        snippet = sql.split(f"alter table {table}", 1)[-1]
        assert "tenant_id" in snippet[:400], f"{table}: tenant_id not in ALTER snippet"
        assert "text" in snippet[:400], f"{table}: tenant_id must be TEXT"
        assert "not null" in snippet[:400], f"{table}: tenant_id must be NOT NULL"
        assert "'public'" in snippet[:400], f"{table}: default must be 'public'"

    @pytest.mark.parametrize("table", _TARGET_TABLES)
    def test_adds_index_per_table(self, table):
        sql = self._migration_sql()
        idx_name = f"idx_{table}_tenant_id"
        assert idx_name in sql, f"missing {idx_name}"

    def test_idempotent(self):
        """The migration must be safe to run twice (IF NOT EXISTS guards)."""
        sql = self._migration_sql()
        assert "if not exists" in sql, (
            "migration must use IF NOT EXISTS so re-running is safe"
        )


# ════════════════════════════════════════════════════════════════════
# Backfill script
# ════════════════════════════════════════════════════════════════════

class TestBackfillScript:
    def test_module_importable(self):
        import scripts.backfill_tenant_id as mod
        assert hasattr(mod, "run"), "run(...) must exist"

    def test_refuses_unknown_table(self):
        from scripts.backfill_tenant_id import run

        db = MagicMock()
        with pytest.raises(ValueError, match="unknown table"):
            run(db, table="users", tenant="pfizer", where_source_api="x")

    def test_refuses_empty_filter(self):
        """Safety — won't tag the whole table accidentally."""
        from scripts.backfill_tenant_id import run

        db = MagicMock()
        with pytest.raises(ValueError, match="refusing"):
            run(db, table="drugs", tenant="pfizer")

    def test_refuses_empty_tenant(self):
        from scripts.backfill_tenant_id import run

        db = MagicMock()
        with pytest.raises(ValueError, match="tenant"):
            run(db, table="drugs", tenant="", where_source_api="x")

    def test_dry_run_does_not_update(self):
        from scripts.backfill_tenant_id import run

        db = MagicMock()
        db.fetch_all.return_value = [
            {"id": "00000000-0000-0000-0000-000000000001"},
            {"id": "00000000-0000-0000-0000-000000000002"},
        ]

        summary = run(
            db,
            table="drugs",
            tenant="pfizer",
            where_source_api="sec_pfizer_private",
            dry_run=True,
        )

        assert summary["matched"] == 2
        assert summary["updated"] == 0
        assert summary["dry_run"] is True
        # No UPDATE drugs SET ... should fire in dry-run.
        update_calls = [
            c for c in db.execute.call_args_list
            if c.args and "update drugs" in str(c.args[0]).lower()
        ]
        assert update_calls == [], "dry-run must not UPDATE"

    def test_apply_updates_and_writes_audit(self):
        from scripts.backfill_tenant_id import run

        db = MagicMock()
        db.fetch_all.return_value = [
            {"id": "id-A"}, {"id": "id-B"}, {"id": "id-C"},
        ]
        db.execute.return_value = None

        summary = run(
            db,
            table="drugs",
            tenant="pfizer",
            where_source_api="sec_pfizer_private",
            dry_run=False,
        )

        assert summary["matched"] == 3
        assert summary["updated"] == 3

        sqls = [str(c.args[0]).lower() for c in db.execute.call_args_list if c.args]
        update_sqls = [s for s in sqls if "update drugs" in s and "tenant_id" in s]
        assert len(update_sqls) == 1, "exactly one UPDATE per run() call"
        audit_sqls = [s for s in sqls if "tenant_id_audit_log" in s]
        assert len(audit_sqls) == 1, "audit log must be appended on apply"

    def test_audit_log_failure_is_non_fatal(self):
        """If the audit table doesn't yet exist, the UPDATE still wins."""
        from scripts.backfill_tenant_id import run

        db = MagicMock()
        db.fetch_all.return_value = [{"id": "id-A"}]

        # First call (UPDATE) succeeds; second call (INSERT into audit
        # table) fails — represents a deploy that hasn't created the
        # audit table yet.
        call_seq = [None, RuntimeError("audit table missing")]
        def _exec(sql, params=None):
            outcome = call_seq.pop(0)
            if isinstance(outcome, BaseException):
                raise outcome
            return outcome
        db.execute.side_effect = _exec

        summary = run(
            db,
            table="drugs",
            tenant="pfizer",
            where_source_api="x",
            dry_run=False,
        )
        assert summary["updated"] == 1

    def test_id_filter_alone_is_sufficient(self):
        from scripts.backfill_tenant_id import run

        db = MagicMock()
        db.fetch_all.return_value = [{"id": "abc-123"}]

        summary = run(
            db,
            table="companies",
            tenant="roche",
            where_id_in=["abc-123"],
            dry_run=True,
        )
        assert summary["matched"] == 1
