"""A1.4 — investigators.roles_history (TDD).

investigators is the existing 'persons' table (rename to persons in
Phase 2). Adds an append-only role history so A2.1's 8-K Item 5.02
parser can record exec transitions, and the pattern detector (B5) can
spot "3 leadership departures in 90d" patterns.

Each entry shape:
  {
    "company_id": uuid | null,
    "company_name": str | null,
    "title": str,
    "functional_area": "CEO"|"CFO"|"CSO"|"CMO"|"CCO"|"head_of_RD"|"board"|"other",
    "seniority_tier": "C-suite"|"EVP/SVP"|"VP"|"Director"|"Other",
    "start_date": ISO date | null,
    "end_date": ISO date | null,
    "transition_id": uuid | null,
    "source_document_id": uuid | null,
    "confirmed": bool
  }
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATION = REPO_ROOT / "schema" / "migrations" / "040_investigators_roles_history.sql"


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
# Cat 1 — migration shape
# ────────────────────────────────────────────────────────────────────

def test_migration_040_file_exists():
    assert MIGRATION.exists()


def test_migration_040_adds_roles_history():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert re.search(
        r"ALTER\s+TABLE\s+investigators\s+ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS\s+roles_history\s+JSONB",
        sql, re.IGNORECASE,
    )
    assert re.search(r"DEFAULT\s+'\[\]'", sql, re.IGNORECASE)


def test_migration_040_adds_canonical_name_column():
    """canonical_name is the lowercased+normalised form for resolver fuzzy match."""
    sql = MIGRATION.read_text(encoding="utf-8")
    assert re.search(
        r"ALTER\s+TABLE\s+investigators\s+ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS\s+canonical_name\s+TEXT",
        sql, re.IGNORECASE,
    )


def test_migration_040_adds_linkedin_url_column():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert re.search(
        r"ALTER\s+TABLE\s+investigators\s+ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS\s+linkedin_url\s+TEXT",
        sql, re.IGNORECASE,
    )


def test_migration_040_creates_indexes():
    sql = MIGRATION.read_text(encoding="utf-8")
    for idx in ("idx_investigators_roles_history",
                "idx_investigators_canonical_name"):
        assert re.search(
            rf"CREATE\s+INDEX\s+IF\s+NOT\s+EXISTS\s+{idx}",
            sql, re.IGNORECASE,
        ), f"missing: {idx}"


def test_migration_040_idempotent():
    sql = MIGRATION.read_text(encoding="utf-8")
    no_comments = re.sub(r"--[^\n]*", "", sql)
    add_columns = re.findall(r"ADD\s+COLUMN\s+(\S+)", no_comments, re.IGNORECASE)
    if_not_exists = re.findall(r"ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS", no_comments, re.IGNORECASE)
    assert len(add_columns) == len(if_not_exists)


# ────────────────────────────────────────────────────────────────────
# Cat 2 — live DB
# ────────────────────────────────────────────────────────────────────

@db_required
def test_investigators_has_roles_history(db):
    rows = db.fetch_all(
        "SELECT data_type FROM information_schema.columns "
        "WHERE table_name='investigators' AND column_name='roles_history'"
    )
    assert len(rows) == 1
    assert rows[0]["data_type"] == "jsonb"


# ────────────────────────────────────────────────────────────────────
# Cat 3 — helper service
# ────────────────────────────────────────────────────────────────────

def test_helper_module_exists():
    assert (REPO_ROOT / "services" / "person_roles.py").exists()


def test_classify_seniority_known_titles():
    from services.person_roles import classify_seniority

    # C-suite
    assert classify_seniority("Chief Executive Officer") == "C-suite"
    assert classify_seniority("CEO") == "C-suite"
    assert classify_seniority("Chief Financial Officer") == "C-suite"
    assert classify_seniority("Chief Medical Officer") == "C-suite"
    assert classify_seniority("Chief Scientific Officer and EVP, R&D") == "C-suite"

    # EVP / SVP
    assert classify_seniority("Executive Vice President, Specialty Care") == "EVP/SVP"
    assert classify_seniority("Senior Vice President, Oncology Commercial") == "EVP/SVP"
    assert classify_seniority("EVP, R&D") == "EVP/SVP"
    assert classify_seniority("SVP and General Counsel") == "EVP/SVP"

    # VP
    assert classify_seniority("Vice President, Investor Relations") == "VP"
    assert classify_seniority("VP of Marketing") == "VP"

    # Director
    assert classify_seniority("Senior Director, Clinical Operations") == "Director"
    assert classify_seniority("Director, Regulatory Affairs") == "Director"

    # Board
    assert classify_seniority("Director (Board)") == "C-suite"  # board director treated as C-suite
    assert classify_seniority("Independent Director") == "C-suite"
    assert classify_seniority("Chair of the Board") == "C-suite"


def test_classify_seniority_falls_back_to_other():
    from services.person_roles import classify_seniority
    assert classify_seniority("Chief Memes Officer") == "C-suite"  # any "Chief X Officer" caught
    assert classify_seniority("Senior Scientist II") == "Other"
    assert classify_seniority("") == "Other"
    assert classify_seniority(None) == "Other"


def test_classify_functional_area_known():
    from services.person_roles import classify_functional_area

    assert classify_functional_area("Chief Executive Officer") == "CEO"
    assert classify_functional_area("Chief Financial Officer") == "CFO"
    assert classify_functional_area("Chief Medical Officer") == "CMO"
    assert classify_functional_area("Chief Scientific Officer") == "CSO"
    assert classify_functional_area("Chief Commercial Officer") == "CCO"
    assert classify_functional_area("EVP, Research and Development") == "head_of_RD"
    assert classify_functional_area("Head of R&D") == "head_of_RD"
    assert classify_functional_area("Director (Board)") == "board"
    assert classify_functional_area("Lead Independent Director") == "board"
    assert classify_functional_area("VP, Marketing") == "other"
    assert classify_functional_area(None) == "other"


def test_normalise_name_strips_punctuation_and_lowercases():
    from services.person_roles import normalise_name
    assert normalise_name("Albert Bourla, Ph.D.") == "albert bourla"
    assert normalise_name("Dr. Mikael Dolsten") == "mikael dolsten"
    assert normalise_name("  John  Smith  III  ") == "john smith iii"
    assert normalise_name("") == ""
    assert normalise_name(None) == ""


def test_build_role_entry_shape():
    from services.person_roles import build_role_entry

    entry = build_role_entry(
        company_id="00000000-0000-0000-0000-000000000001",
        company_name="Pfizer Inc.",
        title="Chief Medical Officer",
        start_date="2026-01-15",
        end_date=None,
        transition_id="00000000-0000-0000-0000-000000000002",
        source_document_id="00000000-0000-0000-0000-000000000003",
        confirmed=True,
    )
    assert entry["company_id"] == "00000000-0000-0000-0000-000000000001"
    assert entry["company_name"] == "Pfizer Inc."
    assert entry["title"] == "Chief Medical Officer"
    assert entry["functional_area"] == "CMO"
    assert entry["seniority_tier"] == "C-suite"
    assert entry["start_date"] == "2026-01-15"
    assert entry["end_date"] is None
    assert entry["transition_id"] == "00000000-0000-0000-0000-000000000002"
    assert entry["confirmed"] is True


def test_build_role_entry_handles_minimal_input():
    from services.person_roles import build_role_entry
    entry = build_role_entry(
        company_id=None,
        company_name="Some Co",
        title="VP, Investor Relations",
        start_date=None,
        end_date=None,
        transition_id=None,
        source_document_id=None,
        confirmed=False,
    )
    assert entry["functional_area"] == "other"
    assert entry["seniority_tier"] == "VP"
    assert entry["confirmed"] is False
