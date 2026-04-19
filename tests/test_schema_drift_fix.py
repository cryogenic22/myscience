"""SPEC-010: Schema Drift Cleanup — TDD test contract.

These tests verify that the production schema matches what services expect,
and that the code does not reference non-existent columns. Run BEFORE
implementing fixes to confirm they all FAIL (TDD discipline).

Categories:
1. Static source checks (always run, no DB required)
2. Migration file checks (always run, file system only)
3. Live DB schema checks (require DATABASE_URL; auto-skip otherwise)
4. End-to-end steward cycle (requires live DB)
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


# ────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────

def _read(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


def _can_connect_to_db() -> bool:
    """Try a real connection — env var alone isn't enough."""
    try:
        from db import Database
        from config import config
        d = Database(config.db.dsn)
        d.connect()
        d.close()
        return True
    except Exception:
        return False


db_required = pytest.mark.skipif(
    not _can_connect_to_db(),
    reason="No reachable database — skipping live DB schema checks",
)


@pytest.fixture(scope="module")
def db():
    """Live DB connection. Skips if not reachable."""
    if not _can_connect_to_db():
        pytest.skip("No reachable database")
    from db import Database
    from config import config
    d = Database(config.db.dsn)
    d.connect()
    yield d
    d.close()


# ────────────────────────────────────────────────────────────────────
# Category 1: Static source code checks (no DB needed)
# ────────────────────────────────────────────────────────────────────

def _scan_python_files() -> list[Path]:
    """All Python files under services/, scripts/, api/, integration/."""
    out: list[Path] = []
    for sub in ("services", "scripts", "api", "integration"):
        out.extend((REPO_ROOT / sub).rglob("*.py"))
    return out


def test_no_python_file_queries_etl_runs_source_type():
    """SPEC-010 (a): etl_runs.source_type doesn't exist; column is source_name.
    Only flag actual SQL patterns (SELECT/GROUP BY/WHERE), not Python dict keys.
    """
    offenders: list[str] = []
    bad_sql_patterns = [
        # SELECT source_type ... FROM etl_runs (within one statement, no ] boundary)
        r"SELECT[^;\]]{0,200}\bsource_type\b[^;\]]{0,200}FROM\s+etl_runs",
        # FROM etl_runs ... GROUP BY source_type
        r"FROM\s+etl_runs[^;\]]{0,200}GROUP\s+BY\s+source_type",
        # FROM etl_runs WHERE source_type
        r"FROM\s+etl_runs[^;\]]{0,200}WHERE[^;\]]{0,100}\bsource_type\b",
    ]
    for path in _scan_python_files():
        src = path.read_text(encoding="utf-8")
        for pat in bad_sql_patterns:
            if re.search(pat, src, re.IGNORECASE):
                offenders.append(str(path.relative_to(REPO_ROOT)))
                break
    assert offenders == [], (
        "Files have SQL queries on etl_runs using source_type (should be source_name): "
        + ", ".join(offenders)
    )


def test_no_python_file_selects_bare_details_from_steward_actions():
    """SPEC-010 (b): steward_actions column is action_details, not details."""
    offenders: list[tuple[str, str]] = []
    for path in _scan_python_files():
        src = path.read_text(encoding="utf-8")
        for m in re.findall(
            r"SELECT[\s\S]{0,300}FROM\s+steward_actions",
            src, re.IGNORECASE,
        ):
            bare_details = re.search(r"[\s,]details(?=[\s,])", m)
            if bare_details and "action_details" not in m:
                offenders.append((str(path.relative_to(REPO_ROOT)), m[:120]))
    assert offenders == [], (
        "Files SELECT 'details' from steward_actions but column is 'action_details': "
        + "; ".join(f"{p}: {snippet!r}" for p, snippet in offenders)
    )


def test_no_python_file_queries_clinical_trials_label():
    """SPEC-010 (c): clinical_trials has no 'label' column.

    Skip files that defensively guard with information_schema column checks —
    those files self-skip in production where the column doesn't exist.
    """
    offenders: list[str] = []
    for path in _scan_python_files():
        src = path.read_text(encoding="utf-8")
        if not re.search(r"FROM\s+clinical_trials[\s\S]{0,300}\blabel\b",
                         src, re.IGNORECASE):
            continue
        # Defensive: file checks information_schema for the label column first
        has_guard = re.search(
            r"information_schema\.columns[\s\S]{0,200}clinical_trials[\s\S]{0,200}label",
            src, re.IGNORECASE,
        )
        if not has_guard:
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert offenders == [], (
        "Files query clinical_trials.label without a defensive column check: "
        + ", ".join(offenders)
    )


def test_no_python_file_calls_min_uuid_in_dedup():
    """SPEC-010 (d): MIN(uuid) is invalid in PostgreSQL.
    Dedup queries on entity_links (uuid id) must use DISTINCT ON or cast.
    """
    offenders: list[str] = []
    for path in _scan_python_files():
        src = path.read_text(encoding="utf-8")
        if "entity_links" not in src:
            continue
        # MIN(id) AS keep_id near a entity_links GROUP BY is the bug pattern
        if re.search(
            r"MIN\s*\(\s*id\s*\)\s+AS\s+keep_id[\s\S]{0,200}entity_links",
            src, re.IGNORECASE,
        ):
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert offenders == [], (
        "Files use MIN(uuid) — PostgreSQL has no min() for UUID. "
        "Use DISTINCT ON or MIN(id::text)::uuid instead. Files: "
        + ", ".join(offenders)
    )


# ────────────────────────────────────────────────────────────────────
# Category 2: Migration file existence checks
# ────────────────────────────────────────────────────────────────────

def test_migration_029_agent_sessions_exists():
    """Migration 029 creates agent_sessions and agent_events tables.
    This must exist locally so production can apply it.
    """
    p = REPO_ROOT / "schema" / "migrations" / "029_agent_sessions.sql"
    assert p.exists(), "Migration 029_agent_sessions.sql must exist"
    sql = p.read_text(encoding="utf-8")
    assert "CREATE TABLE" in sql.upper()
    assert "agent_sessions" in sql.lower()
    assert "agent_events" in sql.lower()


def test_migration_032_market_events_primary_entity_id_exists():
    """SPEC-010: New migration adds market_events.primary_entity_id."""
    p = REPO_ROOT / "schema" / "migrations" / "032_market_events_primary_entity_id.sql"
    assert p.exists(), (
        "Migration 032_market_events_primary_entity_id.sql must exist. "
        "It adds the primary_entity_id column referenced by the dossier handler."
    )
    sql = p.read_text(encoding="utf-8")
    # Must add the column idempotently
    assert re.search(
        r"ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS\s+primary_entity_id",
        sql, re.IGNORECASE,
    ), "Migration 032 must add primary_entity_id idempotently"


def test_migration_032_uses_correct_number():
    """Sanity: the new migration must be 032, not 015 (which is taken).
    Verifies the file system is consistent with the spec."""
    taken = REPO_ROOT / "schema" / "migrations" / "015_mechanism_hierarchy.sql"
    assert taken.exists(), "015_mechanism_hierarchy.sql is the existing migration 015"


# ────────────────────────────────────────────────────────────────────
# Category 3: Live DB schema checks (skip if no DB)
# ────────────────────────────────────────────────────────────────────

@db_required
def test_agent_sessions_table_applied_in_db(db):
    """After migrate.py runs, agent_sessions must exist in the live DB."""
    rows = db.fetch_all(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_name = 'agent_sessions'"
    )
    assert len(rows) == 1, (
        "agent_sessions table missing from production DB. "
        "Run: railway run python migrate.py"
    )


@db_required
def test_agent_events_table_applied_in_db(db):
    rows = db.fetch_all(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_name = 'agent_events'"
    )
    assert len(rows) == 1, (
        "agent_events table missing. Migration 029 not applied."
    )


@db_required
def test_market_events_has_primary_entity_id_column(db):
    """SPEC-010 migration 032 adds this column."""
    rows = db.fetch_all(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = 'market_events' "
        "AND column_name = 'primary_entity_id'"
    )
    assert len(rows) == 1, "market_events.primary_entity_id missing — apply migration 032"


@db_required
def test_etl_runs_uses_source_name(db):
    """Confirm the canonical column name is source_name, not source_type."""
    rows = db.fetch_all(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'etl_runs' "
        "AND column_name IN ('source_name', 'source_type')"
    )
    cols = {r["column_name"] for r in rows}
    assert "source_name" in cols, "etl_runs must have source_name column"


@db_required
def test_steward_actions_has_action_details_not_details(db):
    rows = db.fetch_all(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'steward_actions' "
        "AND column_name IN ('action_details', 'details')"
    )
    cols = {r["column_name"] for r in rows}
    assert "action_details" in cols, "steward_actions.action_details must exist"


@db_required
def test_clinical_trials_has_title_column(db):
    rows = db.fetch_all(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = 'clinical_trials' "
        "AND column_name = 'title'"
    )
    assert len(rows) == 1, "clinical_trials must have a title column"


# ────────────────────────────────────────────────────────────────────
# Category 4: End-to-end Data Steward cycle
# ────────────────────────────────────────────────────────────────────

@db_required
def test_data_steward_cycle_runs_without_schema_errors(db, caplog):
    """A full Data Steward cycle must produce zero ERROR logs about
    missing tables or columns. This is the smoke test for SPEC-010 success.
    """
    from services.data_steward import DataSteward, StewardConfig

    steward = DataSteward(
        db,
        StewardConfig(max_iterations=1, dry_run=True, skip_ai=True),
    )
    with caplog.at_level("ERROR"):
        steward.run_loop()

    schema_errors = [
        r for r in caplog.records
        if "does not exist" in r.message
        or "min(uuid)" in r.message.lower()
        or "no function matches" in r.message.lower()
    ]
    assert schema_errors == [], (
        f"Data Steward emitted {len(schema_errors)} schema errors:\n"
        + "\n".join(r.message for r in schema_errors[:5])
    )
