"""Regression: auto-migrate-on-startup must be safe to run every boot.

The bug this guards against: migrations 068-071 shipped in a deploy but the
tables never existed in prod (Railway) until someone manually POSTed
/debug/migrate — surfacing as `relation "engagement_audit_log" does not
exist` 500s on engagement creation.

The fix wires run_migrations() into the app's startup callbacks. That is
only safe if running it repeatedly is a no-op. These tests pin two
properties:

  1. run_migrations() applies every pending .sql file and records it.
  2. A second run applies nothing (idempotent) — so re-running on every
     container boot can't error or double-apply.
"""
from __future__ import annotations

import migrate


class _FakeMigrateDB:
    """In-memory stand-in for db.Database, modelling schema_migrations."""

    def __init__(self):
        self.applied: set[str] = set()
        self.scripts_run: list[str] = []

    def execute(self, sql, params=None):
        s = (sql or "").lower()
        if "insert into schema_migrations" in s:
            # params is [filename]
            self.applied.add(params[0])
        # CREATE TABLE schema_migrations and any other execute() are no-ops.

    def execute_script(self, sql):
        # Applying a migration's DDL — we don't have a real DB, just record it.
        self.scripts_run.append(sql)

    def fetch_all(self, sql, params=None):
        s = (sql or "").lower()
        if "from schema_migrations" in s:
            return [{"filename": f} for f in sorted(self.applied)]
        return []


def test_run_migrations_applies_all_then_is_idempotent():
    db = _FakeMigrateDB()
    total = len(migrate.get_migration_files())
    assert total > 0, "expected migration files on disk"

    first = migrate.run_migrations(db)
    assert first == total, "first run should apply every pending migration"
    assert len(db.applied) == total

    second = migrate.run_migrations(db)
    assert second == 0, "second run must be a no-op (safe to re-run on boot)"
    assert len(db.applied) == total


def test_engagement_migrations_are_in_the_set():
    """The migrations behind the 500 (engagements + audit log) must exist."""
    names = {f for f, _ in migrate.get_migration_files()}
    assert "068_engagements.sql" in names
    assert "069_business_context_brief.sql" in names
    assert "070_priority_matrix.sql" in names
    assert "071_scenario_mode.sql" in names
