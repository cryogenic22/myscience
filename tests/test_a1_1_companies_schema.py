"""A1.1 — companies schema extension (TDD).

SPEC-016 §7 swimlane A1: extend `companies` with the CI-relevant fields
that catalog/intel both depend on. Three additions:

  - aliases jsonb (array of normalised name forms)
  - external_ids jsonb (bag: cik, lei, duns, openfda_labeler_codes,
    cortellis_id, pitchbook_id, isin, …)
  - parent_company_id uuid (self-FK, nullable; for subs / acquired entities)

Plus an LEI column (top-level for join-friendliness; mirrored in external_ids).

Tests are split into:
  Category 1 — migration file existence and shape (always run)
  Category 2 — live DB schema checks (skip if no DATABASE_URL)
  Category 3 — domain pack updates (always run)
  Category 4 — backfill helper invariants (always run, uses fixtures)

Run with `python -m pytest tests/test_a1_1_companies_schema.py -v`. All
must FAIL before implementation; all must PASS after.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATION = REPO_ROOT / "schema" / "migrations" / "036_companies_aliases_external_ids.sql"


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
    not _can_connect_to_db(),
    reason="No reachable database — skipping live schema checks",
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
# Category 1 — migration file shape
# ────────────────────────────────────────────────────────────────────

def test_migration_036_file_exists():
    assert MIGRATION.exists(), (
        f"Migration {MIGRATION.name} must exist. SPEC-016 A1.1 — companies schema extension."
    )


def test_migration_036_adds_aliases_column():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert re.search(
        r"ALTER\s+TABLE\s+companies\s+ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS\s+aliases\s+JSONB",
        sql, re.IGNORECASE,
    ), "Migration must add aliases jsonb idempotently"
    assert re.search(r"DEFAULT\s+'\[\]'", sql, re.IGNORECASE), (
        "aliases must default to empty array"
    )


def test_migration_036_adds_external_ids_column():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert re.search(
        r"ALTER\s+TABLE\s+companies\s+ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS\s+external_ids\s+JSONB",
        sql, re.IGNORECASE,
    ), "Migration must add external_ids jsonb idempotently"
    assert re.search(r"DEFAULT\s+'\{\}'", sql, re.IGNORECASE), (
        "external_ids must default to empty object"
    )


def test_migration_036_adds_lei_column():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert re.search(
        r"ALTER\s+TABLE\s+companies\s+ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS\s+lei\s+TEXT",
        sql, re.IGNORECASE,
    )


def test_migration_036_adds_parent_company_id_column():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert re.search(
        r"ALTER\s+TABLE\s+companies\s+ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS\s+parent_company_id\s+UUID",
        sql, re.IGNORECASE,
    ), "parent_company_id must be uuid (self-FK to companies.id)"
    # Self-FK constraint is added separately to be idempotent
    assert "REFERENCES companies(id)" in sql or "REFERENCES companies (id)" in sql, (
        "parent_company_id must reference companies(id)"
    )


def test_migration_036_creates_indexes():
    sql = MIGRATION.read_text(encoding="utf-8")
    # GIN index on aliases for jsonb containment queries
    assert re.search(
        r"CREATE\s+INDEX\s+IF\s+NOT\s+EXISTS\s+idx_companies_aliases\s+ON\s+companies",
        sql, re.IGNORECASE,
    )
    # GIN on external_ids for fast lookup-by-vendor-id
    assert re.search(
        r"CREATE\s+INDEX\s+IF\s+NOT\s+EXISTS\s+idx_companies_external_ids\s+ON\s+companies",
        sql, re.IGNORECASE,
    )
    # btree on lei
    assert re.search(
        r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+IF\s+NOT\s+EXISTS\s+idx_companies_lei",
        sql, re.IGNORECASE,
    )
    # btree on parent_company_id
    assert re.search(
        r"CREATE\s+INDEX\s+IF\s+NOT\s+EXISTS\s+idx_companies_parent",
        sql, re.IGNORECASE,
    )


def test_migration_036_is_idempotent():
    """Running the migration twice must not error.

    Verified by static check: every CREATE / ADD COLUMN must use IF NOT EXISTS.
    """
    sql = MIGRATION.read_text(encoding="utf-8")
    # Strip strings/comments so we don't false-positive on examples in comments
    sql_no_comments = re.sub(r"--[^\n]*", "", sql)

    add_columns = re.findall(r"ADD\s+COLUMN\s+(\S+)", sql_no_comments, re.IGNORECASE)
    create_indexes = re.findall(r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+(\S+)",
                                sql_no_comments, re.IGNORECASE)

    for stmt_kind in ("ADD COLUMN", "CREATE INDEX"):
        # Check each statement of the given kind has IF NOT EXISTS within ~30 chars before its name
        if stmt_kind == "ADD COLUMN":
            pattern = r"ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS"
            count_total = len(add_columns)
        else:
            pattern = r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+IF\s+NOT\s+EXISTS"
            count_total = len(create_indexes)
        count_idempotent = len(re.findall(pattern, sql_no_comments, re.IGNORECASE))
        assert count_idempotent == count_total, (
            f"{stmt_kind}: {count_idempotent}/{count_total} statements use "
            f"IF NOT EXISTS. All must."
        )


# ────────────────────────────────────────────────────────────────────
# Category 2 — live DB schema checks (skip if no DB)
# ────────────────────────────────────────────────────────────────────

@db_required
def test_companies_has_aliases_column(db):
    rows = db.fetch_all(
        "SELECT data_type FROM information_schema.columns "
        "WHERE table_name = 'companies' AND column_name = 'aliases'"
    )
    assert len(rows) == 1
    assert rows[0]["data_type"] == "jsonb"


@db_required
def test_companies_has_external_ids_column(db):
    rows = db.fetch_all(
        "SELECT data_type FROM information_schema.columns "
        "WHERE table_name = 'companies' AND column_name = 'external_ids'"
    )
    assert len(rows) == 1
    assert rows[0]["data_type"] == "jsonb"


@db_required
def test_companies_has_lei_column(db):
    rows = db.fetch_all(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = 'companies' AND column_name = 'lei'"
    )
    assert len(rows) == 1


@db_required
def test_companies_has_parent_company_id_column(db):
    rows = db.fetch_all(
        "SELECT data_type FROM information_schema.columns "
        "WHERE table_name = 'companies' AND column_name = 'parent_company_id'"
    )
    assert len(rows) == 1
    assert rows[0]["data_type"] == "uuid"


@db_required
def test_companies_aliases_default_is_empty_array(db):
    """Insert a minimal row without setting aliases — should default to []."""
    db.execute(
        "INSERT INTO companies (name, source_api, source_url, retrieved_at) "
        "VALUES ('TestCo Schema A1.1', 'test', 'http://t', NOW())"
    )
    row = db.fetch_one(
        "SELECT aliases, external_ids FROM companies WHERE name = 'TestCo Schema A1.1'"
    )
    try:
        assert row["aliases"] == [], f"aliases default should be [], got {row['aliases']!r}"
        assert row["external_ids"] == {}, f"external_ids default should be {{}}, got {row['external_ids']!r}"
    finally:
        db.execute("DELETE FROM companies WHERE name = 'TestCo Schema A1.1'")


@db_required
def test_companies_indexes_created(db):
    rows = db.fetch_all(
        "SELECT indexname FROM pg_indexes "
        "WHERE tablename = 'companies' "
        "AND indexname IN ('idx_companies_aliases', 'idx_companies_external_ids', "
        "                  'idx_companies_lei', 'idx_companies_parent')"
    )
    found = {r["indexname"] for r in rows}
    expected = {
        "idx_companies_aliases", "idx_companies_external_ids",
        "idx_companies_lei", "idx_companies_parent",
    }
    assert expected <= found, f"missing indexes: {expected - found}"


# ────────────────────────────────────────────────────────────────────
# Category 3 — domain pack reflects the new fields
# ────────────────────────────────────────────────────────────────────

def test_domain_pack_company_recommends_aliases_and_external_ids():
    """domain/pharma/pack.py company schema should mention these as recommended fields.

    Soft check — the domain pack is descriptive, not enforced. But if it
    doesn't list them, the entity resolver won't use them.
    """
    pack_src = (REPO_ROOT / "domain" / "pharma" / "pack.py").read_text(encoding="utf-8")
    # Look for the company EntitySchema declaration
    company_block = re.search(
        r"company\s*=\s*EntitySchema\(([\s\S]*?)\)\s*\n",
        pack_src,
    )
    assert company_block is not None, "Could not find company EntitySchema in pack.py"
    block = company_block.group(1)
    # Either present in recommended_fields or referenced in a comment
    has_aliases = '"aliases"' in block or "'aliases'" in block or "# aliases" in block
    has_external_ids = (
        '"external_ids"' in block
        or "'external_ids'" in block
        or "# external_ids" in block
    )
    assert has_aliases, "domain pack company schema should mention aliases"
    assert has_external_ids, "domain pack company schema should mention external_ids"


# ────────────────────────────────────────────────────────────────────
# Category 4 — backfill helper invariants
# ────────────────────────────────────────────────────────────────────

def test_backfill_helper_module_exists():
    """A1.1 ships a small helper for accumulating aliases + external_ids."""
    helper = REPO_ROOT / "integration" / "company_identity.py"
    assert helper.exists(), (
        "integration/company_identity.py must exist with merge_aliases / "
        "merge_external_ids helpers"
    )


def test_merge_aliases_dedupes_case_insensitive():
    """Two equivalent forms of the same name should merge to one."""
    from integration.company_identity import merge_aliases
    out = merge_aliases(
        existing=["Pfizer Inc.", "Pfizer"],
        new=["pfizer inc.", "PFIZER", "Pfizer Inc"],
    )
    # Normalised forms collapsed; canonical capitalisation preserved
    lowered = [a.lower().strip().rstrip(".") for a in out]
    assert len(set(lowered)) == len(lowered), (
        f"merge_aliases must dedupe case-insensitively, got {out!r}"
    )
    # Should keep at least one form per unique alias
    assert any("pfizer inc" in a.lower() for a in out)


def test_merge_aliases_strips_legal_suffixes_for_dedup_only():
    """'Pfizer' and 'Pfizer Inc.' are the same alias for dedup purposes,
    but we keep BOTH forms in the output (so resolver can match either)."""
    from integration.company_identity import merge_aliases
    out = merge_aliases(existing=["Pfizer Inc."], new=["Pfizer"])
    # Both kept (different surface forms)
    assert any(a == "Pfizer Inc." for a in out)
    assert any(a == "Pfizer" for a in out)


def test_merge_external_ids_takes_higher_authority_value_on_conflict():
    """If existing has cik='0000078003' and new has cik='0000078004' from a
    less authoritative source, existing wins. Source ranking:
    sec_edgar > openfda > cortellis > pitchbook > other.
    """
    from integration.company_identity import merge_external_ids
    out = merge_external_ids(
        existing={"cik": "0000078003", "_source_cik": "sec_edgar"},
        new={"cik": "0000078004", "_source_cik": "pitchbook"},
    )
    assert out["cik"] == "0000078003", f"expected sec_edgar to win, got {out!r}"


def test_merge_external_ids_adds_new_keys():
    """New keys not in existing get added regardless of source."""
    from integration.company_identity import merge_external_ids
    out = merge_external_ids(
        existing={"cik": "0000078003", "_source_cik": "sec_edgar"},
        new={"openfda_labeler": "0069", "_source_openfda_labeler": "openfda"},
    )
    assert out["cik"] == "0000078003"
    assert out["openfda_labeler"] == "0069"


def test_merge_external_ids_handles_list_valued_fields():
    """openfda_labeler_codes is a list — union, not overwrite."""
    from integration.company_identity import merge_external_ids
    out = merge_external_ids(
        existing={"openfda_labeler_codes": ["0069", "0007"]},
        new={"openfda_labeler_codes": ["0007", "0093"]},
    )
    assert sorted(out["openfda_labeler_codes"]) == ["0007", "0069", "0093"]
