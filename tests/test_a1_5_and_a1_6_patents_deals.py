"""A1.5 + A1.6 — patents and deals tables (skeletons).

Two new tables, similar shape:

  patents — populated by A5.1 USPTO PatentsView connector
  deals   — populated by A2.2 8-K Item 1.01 parser

Both are skeletons in this PR — schema only, no service code yet.
The connectors come in their respective swimlane PRs.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PATENTS_MIGRATION = REPO_ROOT / "schema" / "migrations" / "041_patents_table.sql"
DEALS_MIGRATION   = REPO_ROOT / "schema" / "migrations" / "042_deals_table.sql"


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
# A1.5 — patents
# ────────────────────────────────────────────────────────────────────

class TestPatentsMigration:

    def test_migration_041_file_exists(self):
        assert PATENTS_MIGRATION.exists()

    def test_migration_041_creates_patents_table(self):
        sql = PATENTS_MIGRATION.read_text(encoding="utf-8")
        assert re.search(
            r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+patents\b",
            sql, re.IGNORECASE,
        )

    def test_migration_041_adds_uspto_columns(self):
        """Migration 041 ADDs the USPTO PatentsView columns that 006 didn't have.
        Columns from 006 (source_api, source_url, retrieved_at, created_at) are
        already present on the existing table — 041 doesn't re-declare them."""
        sql = PATENTS_MIGRATION.read_text(encoding="utf-8").lower()
        for col in [
            "patent_office", "assignee_company_id", "assignee_name_raw",
            "filing_date", "grant_date", "expiration_date", "priority_date",
            "cpc_codes", "status", "title", "abstract", "updated_at",
        ]:
            assert re.search(rf"\b{col}\b", sql), f"missing column: {col}"

    def test_migration_041_uses_additive_alter(self):
        """041 must be a pure ADD COLUMN IF NOT EXISTS sequence — the patents
        table already exists from migration 006 with a different shape, so
        any new column has to be additive."""
        sql = PATENTS_MIGRATION.read_text(encoding="utf-8")
        # At least one ADD COLUMN IF NOT EXISTS for cpc_codes (the headline
        # USPTO field that triggered the original deploy bug)
        assert re.search(
            r"ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS\s+cpc_codes",
            sql, re.IGNORECASE,
        ), "041 must additively ADD cpc_codes"

    def test_migration_041_no_check_constraints_on_legacy_columns(self):
        """Original 041 had CHECK on patent_type/status with new vocabulary
        ('grant', 'granted', etc.) — but legacy data from 006 uses
        'Drug Substance', 'Method of Use'. CHECK constraints would fail.
        Migration 041 must NOT add them."""
        sql = PATENTS_MIGRATION.read_text(encoding="utf-8")
        assert "patents_patent_type_check" not in sql, (
            "CHECK on patent_type would violate legacy rows"
        )
        assert "patents_status_check" not in sql, (
            "CHECK on status would violate legacy rows"
        )

    def test_migration_041_assignee_fk(self):
        sql = PATENTS_MIGRATION.read_text(encoding="utf-8")
        assert re.search(
            r"assignee_company_id[\s\S]{0,200}REFERENCES\s+companies\s*\(\s*id",
            sql, re.IGNORECASE,
        )

    def test_migration_041_indexes(self):
        sql = PATENTS_MIGRATION.read_text(encoding="utf-8")
        for idx in ("idx_patents_assignee", "idx_patents_expiration",
                    "idx_patents_cpc", "idx_patents_status"):
            assert re.search(
                rf"CREATE\s+(?:UNIQUE\s+)?INDEX\s+IF\s+NOT\s+EXISTS\s+{idx}",
                sql, re.IGNORECASE,
            ), f"missing: {idx}"

    @db_required
    def test_patents_table_exists(self, db):
        rows = db.fetch_all(
            "SELECT 1 FROM information_schema.tables WHERE table_name='patents'"
        )
        assert len(rows) == 1


# ────────────────────────────────────────────────────────────────────
# A1.6 — deals
# ────────────────────────────────────────────────────────────────────

class TestDealsMigration:

    def test_migration_042_file_exists(self):
        assert DEALS_MIGRATION.exists()

    def test_migration_042_creates_deals_table(self):
        sql = DEALS_MIGRATION.read_text(encoding="utf-8")
        assert re.search(
            r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+deals\b",
            sql, re.IGNORECASE,
        )

    def test_migration_042_required_columns(self):
        sql = DEALS_MIGRATION.read_text(encoding="utf-8").lower()
        for col in [
            "id", "deal_types", "acquirer_id", "target_id",
            "licensor_id", "licensee_id", "subject_drug_ids",
            "subject_indications", "geography",
            "upfront_value_usd", "milestones_total_usd",
            "royalty_terms", "total_potential_usd", "equity_component",
            "currency", "announced_date", "closing_date", "status",
            "source_document_id", "press_release_url", "filing_url",
            "created_at", "updated_at",
        ]:
            assert re.search(rf"\b{col}\b", sql), f"missing column: {col}"

    def test_migration_042_deal_types_array(self):
        """deal_types is text[] (composite — one deal can be multiple types)."""
        sql = DEALS_MIGRATION.read_text(encoding="utf-8")
        assert re.search(
            r"deal_types\s+TEXT\[\]\s+NOT\s+NULL",
            sql, re.IGNORECASE,
        ), "deal_types must be NOT NULL text[]"
        # All 9 deal-type values must be CHECK-validated somewhere
        for value in ("acquisition", "asset_purchase", "license_in",
                      "license_out", "collaboration", "option",
                      "co_promotion", "co_development", "royalty_monetisation"):
            assert f"'{value}'" in sql, f"deal_types check missing: {value}"

    def test_migration_042_status_check(self):
        sql = DEALS_MIGRATION.read_text(encoding="utf-8")
        for value in ("announced", "closed", "terminated"):
            assert f"'{value}'" in sql, f"status missing: {value}"

    def test_migration_042_party_fks(self):
        sql = DEALS_MIGRATION.read_text(encoding="utf-8")
        # All 4 party FKs must reference companies(id)
        assert sql.count("REFERENCES companies(id)") + sql.count("REFERENCES companies (id)") >= 4, (
            "deals must have 4 party FKs (acquirer, target, licensor, licensee) → companies(id)"
        )

    def test_migration_042_term_invariants(self):
        """Sanity check constraint: upfront + milestones <= total_potential
        when total_potential is disclosed. Per critique R6/A2.2."""
        sql = DEALS_MIGRATION.read_text(encoding="utf-8")
        # Look for a CHECK constraint that involves totals
        assert re.search(
            r"CHECK[\s\S]{0,200}(?:total_potential|upfront[\s\S]{0,80}milestones)",
            sql, re.IGNORECASE,
        ), "deals should have a sanity CHECK on terms (per critique R6)"

    def test_migration_042_indexes(self):
        sql = DEALS_MIGRATION.read_text(encoding="utf-8")
        for idx in ("idx_deals_acquirer", "idx_deals_target",
                    "idx_deals_announced", "idx_deals_status",
                    "idx_deals_deal_types"):
            assert re.search(
                rf"CREATE\s+(?:UNIQUE\s+)?INDEX\s+IF\s+NOT\s+EXISTS\s+{idx}",
                sql, re.IGNORECASE,
            ), f"missing: {idx}"

    def test_migration_042_idempotent(self):
        sql = DEALS_MIGRATION.read_text(encoding="utf-8")
        no_comments = re.sub(r"--[^\n]*", "", sql)
        assert "CREATE TABLE IF NOT EXISTS" in no_comments.upper()

    @db_required
    def test_deals_table_exists(self, db):
        rows = db.fetch_all(
            "SELECT 1 FROM information_schema.tables WHERE table_name='deals'"
        )
        assert len(rows) == 1

    @db_required
    def test_deals_status_default_is_announced(self, db):
        rows = db.fetch_all(
            "SELECT column_default FROM information_schema.columns "
            "WHERE table_name = 'deals' AND column_name = 'status'"
        )
        assert len(rows) == 1
        assert "announced" in (rows[0]["column_default"] or "").lower()
