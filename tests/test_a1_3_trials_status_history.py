"""A1.3 — clinical_trials.status_history (TDD).

Adds a JSONB array column that captures every observed (status, phase,
primary_completion_date) snapshot for a trial, plus a helper service
that the A3.1 diff connector will call.

Each entry shape:
  {
    "status": str,                           # not_yet_recruiting | …
    "phase": str | null,
    "primary_completion_date": ISO date | null,
    "observed_at": ISO datetime,
    "source_document_id": uuid | null
  }

Append semantics:
  - Append-only — never rewrite history.
  - Idempotent on the (status, phase, primary_completion_date) tuple at
    the same observed-at second — re-running the diff doesn't duplicate.
  - Strictly ordered by observed_at.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATION = REPO_ROOT / "schema" / "migrations" / "039_trials_status_history.sql"


def _can_connect_to_db() -> bool:
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
    not _can_connect_to_db(), reason="No reachable database",
)


@pytest.fixture(scope="module")
def db():
    if not _can_connect_to_db():
        pytest.skip("No reachable database")
    from db import Database
    from config import config
    d = Database(config.db.dsn)
    d.connect()
    yield d
    d.close()


# ────────────────────────────────────────────────────────────────────
# Cat 1 — migration file
# ────────────────────────────────────────────────────────────────────

def test_migration_039_file_exists():
    assert MIGRATION.exists()


def test_migration_039_adds_status_history_jsonb():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert re.search(
        r"ALTER\s+TABLE\s+clinical_trials\s+ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS\s+status_history\s+JSONB",
        sql, re.IGNORECASE,
    )
    assert re.search(r"DEFAULT\s+'\[\]'", sql, re.IGNORECASE)


def test_migration_039_creates_gin_index():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert re.search(
        r"CREATE\s+INDEX\s+IF\s+NOT\s+EXISTS\s+idx_trials_status_history\s+ON\s+clinical_trials\s+USING\s+GIN",
        sql, re.IGNORECASE,
    ), "GIN index on status_history needed for jsonb containment queries"


def test_migration_039_seeds_existing_trials_with_one_entry():
    """The migration backfills each existing trial with a single
    status_history entry capturing its current state, so the diff
    service has a baseline to compare against on first run."""
    sql = MIGRATION.read_text(encoding="utf-8")
    # Look for a backfill statement that reads current status/phase and writes
    # a one-element jsonb array
    assert re.search(
        r"UPDATE\s+clinical_trials[\s\S]{0,200}status_history\s*=",
        sql, re.IGNORECASE,
    ), "Migration should backfill existing trials with their current state"


def test_migration_039_idempotent():
    sql = MIGRATION.read_text(encoding="utf-8")
    no_comments = re.sub(r"--[^\n]*", "", sql)
    assert "ADD COLUMN IF NOT EXISTS" in no_comments.upper()
    assert "CREATE INDEX IF NOT EXISTS" in no_comments.upper()


# ────────────────────────────────────────────────────────────────────
# Cat 2 — live DB
# ────────────────────────────────────────────────────────────────────

@db_required
def test_clinical_trials_has_status_history_column(db):
    rows = db.fetch_all(
        "SELECT data_type FROM information_schema.columns "
        "WHERE table_name='clinical_trials' AND column_name='status_history'"
    )
    assert len(rows) == 1
    assert rows[0]["data_type"] == "jsonb"


@db_required
def test_clinical_trials_status_history_default_empty(db):
    """For a freshly-inserted trial (post-migration), default is []."""
    db.execute(
        "INSERT INTO clinical_trials (id, nct_id, title, status, source_api, "
        "source_url, retrieved_at) "
        "VALUES (gen_random_uuid(), 'NCT99999990', 't', 'Completed', "
        "'test', 'http://t', NOW())"
    )
    try:
        row = db.fetch_one(
            "SELECT status_history FROM clinical_trials WHERE nct_id = 'NCT99999990'"
        )
        assert row["status_history"] == []
    finally:
        db.execute("DELETE FROM clinical_trials WHERE nct_id = 'NCT99999990'")


# ────────────────────────────────────────────────────────────────────
# Cat 3 — append helper service
# ────────────────────────────────────────────────────────────────────

def test_helper_module_exists():
    assert (REPO_ROOT / "services" / "trial_status_history.py").exists()


def test_build_history_entry_shape():
    """The entry the helper produces must match the documented shape."""
    from services.trial_status_history import build_history_entry

    entry = build_history_entry(
        status="Recruiting",
        phase="PHASE2",
        primary_completion_date="2026-12-31",
        source_document_id="123e4567-e89b-12d3-a456-426614174000",
    )
    assert entry["status"] == "Recruiting"
    assert entry["phase"] == "PHASE2"
    assert entry["primary_completion_date"] == "2026-12-31"
    assert entry["source_document_id"] == "123e4567-e89b-12d3-a456-426614174000"
    # observed_at must be ISO 8601 with timezone (we always store UTC)
    assert "observed_at" in entry
    parsed = datetime.fromisoformat(entry["observed_at"].replace("Z", "+00:00"))
    assert parsed.tzinfo is not None


def test_build_history_entry_handles_nulls():
    from services.trial_status_history import build_history_entry
    entry = build_history_entry(
        status="Withdrawn",
        phase=None,
        primary_completion_date=None,
        source_document_id=None,
    )
    assert entry["status"] == "Withdrawn"
    assert entry["phase"] is None
    assert entry["primary_completion_date"] is None
    assert entry["source_document_id"] is None


def test_should_append_skips_no_change():
    """If the new (status, phase, pcd) tuple matches the last history entry,
    no append — keeps the array clean."""
    from services.trial_status_history import should_append

    history = [
        {"status": "Recruiting", "phase": "PHASE2",
         "primary_completion_date": "2026-12-31",
         "observed_at": "2026-04-25T10:00:00+00:00",
         "source_document_id": None},
    ]
    new = {
        "status": "Recruiting",
        "phase": "PHASE2",
        "primary_completion_date": "2026-12-31",
        "observed_at": "2026-04-28T10:00:00+00:00",
        "source_document_id": None,
    }
    assert should_append(history, new) is False


def test_should_append_returns_true_on_status_change():
    from services.trial_status_history import should_append
    history = [
        {"status": "Recruiting", "phase": "PHASE2",
         "primary_completion_date": "2026-12-31",
         "observed_at": "2026-04-25T10:00:00+00:00",
         "source_document_id": None},
    ]
    new = {
        "status": "Active, not recruiting",
        "phase": "PHASE2",
        "primary_completion_date": "2026-12-31",
        "observed_at": "2026-04-28T10:00:00+00:00",
        "source_document_id": None,
    }
    assert should_append(history, new) is True


def test_should_append_returns_true_on_pcd_slip():
    from services.trial_status_history import should_append
    history = [
        {"status": "Active, not recruiting", "phase": "PHASE3",
         "primary_completion_date": "2026-09-30",
         "observed_at": "2026-01-15T10:00:00+00:00",
         "source_document_id": None},
    ]
    new = {
        "status": "Active, not recruiting", "phase": "PHASE3",
        "primary_completion_date": "2027-03-31",  # slipped by 6 months
        "observed_at": "2026-04-28T10:00:00+00:00",
        "source_document_id": None,
    }
    assert should_append(history, new) is True


def test_should_append_handles_empty_history():
    """First-time observation — always append."""
    from services.trial_status_history import should_append
    new = {
        "status": "Recruiting", "phase": "PHASE2",
        "primary_completion_date": "2026-12-31",
        "observed_at": "2026-04-28T10:00:00+00:00",
        "source_document_id": None,
    }
    assert should_append([], new) is True


def test_diff_summary_describes_change():
    """diff_summary returns a structured dict describing what changed —
    used to populate the trial_status_change event payload in A3.1."""
    from services.trial_status_history import diff_summary

    prior = {"status": "Recruiting", "phase": "PHASE2",
             "primary_completion_date": "2026-12-31"}
    new = {"status": "Active, not recruiting", "phase": "PHASE3",
           "primary_completion_date": "2027-03-31"}
    out = diff_summary(prior, new)

    assert out["status_changed"] is True
    assert out["prev_status"] == "Recruiting"
    assert out["new_status"] == "Active, not recruiting"
    assert out["phase_changed"] is True
    assert out["prev_phase"] == "PHASE2"
    assert out["new_phase"] == "PHASE3"
    assert out["pcd_changed"] is True
    assert out["pcd_slip_days"] == 90  # 2026-12-31 → 2027-03-31


def test_diff_summary_handles_first_observation():
    """No prior — diff_summary returns initial=True with all fields populated."""
    from services.trial_status_history import diff_summary

    out = diff_summary(None, {
        "status": "Recruiting", "phase": "PHASE1",
        "primary_completion_date": "2027-06-30",
    })
    assert out["initial"] is True
    assert out["new_status"] == "Recruiting"
