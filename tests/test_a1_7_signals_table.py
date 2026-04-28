"""A1.7 — signals table (the unit-of-output).

SPEC-016 §2.4 names this as the single biggest platform gap. The signals
table holds dedup'd, KBQ-tagged, dual-tier-scored Signals — what modules
actually consume.

This PR creates the SCHEMA only. Population (clustering, scoring,
synthesis) is sprint B1+. We need the table in place so that the
intel layer has somewhere to write.

Tests split:
  Cat 1 — migration file shape (always run)
  Cat 2 — live DB schema checks (skip if no DATABASE_URL)
  Cat 3 — DDL invariants (parse SQL with sqlparse-style checks)
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATION = REPO_ROOT / "schema" / "migrations" / "037_signals_table.sql"


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
# Cat 1 — migration file shape
# ────────────────────────────────────────────────────────────────────

def test_migration_037_file_exists():
    assert MIGRATION.exists(), (
        f"{MIGRATION.name} must exist — A1.7 ships the signals table."
    )


def test_migration_037_creates_signals_table():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert re.search(
        r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+signals\b",
        sql, re.IGNORECASE,
    ), "Migration must create signals table idempotently"


def test_migration_037_required_columns_present():
    """Every column from the OpenAPI Signal schema must be in the DDL."""
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    required = [
        "id",
        "event_id",
        "kbq_tags",
        "headline",
        "summary",
        "direction",
        "confidence_tier",
        "trust_score",
        "impact_tier",
        "impact_score",
        "rule_version_id",
        "primary_entity_type",
        "primary_entity_id",
        "primary_entity_name",
        "related_entity_ids",
        "evidence_document_ids",
        "superseded_by",
        "supersedence_reason",
        "status",
        "created_at",
        "reviewed_by",
        "reviewed_at",
        "shipped_at",
    ]
    missing = [c for c in required if not re.search(rf"\b{c}\b", sql)]
    assert missing == [], f"Migration is missing columns: {missing}"


def test_migration_037_confidence_tier_check_constraint():
    """confidence_tier must be enum-constrained per ADR-002."""
    sql = MIGRATION.read_text(encoding="utf-8")
    # CHECK constraint on confidence_tier listing all 4 values
    pattern = r"confidence_tier[\s\S]{0,200}CHECK[\s\S]{0,200}'confirmed'[\s\S]{0,200}'reported'[\s\S]{0,200}'inferred'[\s\S]{0,200}'disputed'"
    assert re.search(pattern, sql, re.IGNORECASE), (
        "confidence_tier must have CHECK constraint with all 4 enum values"
    )


def test_migration_037_impact_tier_check_constraint():
    sql = MIGRATION.read_text(encoding="utf-8")
    pattern = r"impact_tier[\s\S]{0,200}CHECK[\s\S]{0,200}'high'[\s\S]{0,200}'medium'[\s\S]{0,200}'low'"
    assert re.search(pattern, sql, re.IGNORECASE), (
        "impact_tier must have CHECK constraint with high/medium/low"
    )


def test_migration_037_status_check_constraint():
    sql = MIGRATION.read_text(encoding="utf-8")
    pattern = r"status[\s\S]{0,200}CHECK[\s\S]{0,500}'candidate'[\s\S]{0,500}'reviewed'[\s\S]{0,500}'shipped'[\s\S]{0,500}'superseded'[\s\S]{0,500}'retracted'"
    assert re.search(pattern, sql, re.IGNORECASE), (
        "status must have CHECK constraint with all 5 state-machine values"
    )


def test_migration_037_supersedence_reason_check_constraint():
    sql = MIGRATION.read_text(encoding="utf-8")
    pattern = r"supersedence_reason[\s\S]{0,300}CHECK[\s\S]{0,500}'corrected'[\s\S]{0,500}'progressed'[\s\S]{0,500}'downgraded'[\s\S]{0,500}'retracted'[\s\S]{0,500}'merged'"
    assert re.search(pattern, sql, re.IGNORECASE), (
        "supersedence_reason must have CHECK constraint with all 5 reasons "
        "per SPEC-017 D8"
    )


def test_migration_037_evidence_min_length_invariant():
    """The no-fabrication invariant: every signal cites ≥1 document."""
    sql = MIGRATION.read_text(encoding="utf-8")
    # Need a CHECK that cardinality(evidence_document_ids) >= 1, OR a NOT NULL
    # combined with a default that has elements (which we don't want — should be enforced).
    pattern = r"evidence_document_ids[\s\S]{0,300}CHECK[\s\S]{0,200}cardinality\s*\(\s*evidence_document_ids\s*\)\s*>=\s*1"
    assert re.search(pattern, sql, re.IGNORECASE), (
        "evidence_document_ids must have CHECK cardinality(...) >= 1 — "
        "the no-fabrication invariant"
    )


def test_migration_037_score_range_constraints():
    """trust_score and impact_score must be in [0, 1]."""
    sql = MIGRATION.read_text(encoding="utf-8")
    assert re.search(
        r"trust_score[\s\S]{0,200}CHECK[\s\S]{0,200}BETWEEN\s+0\s+AND\s+1",
        sql, re.IGNORECASE,
    ), "trust_score must have BETWEEN 0 AND 1 check"
    assert re.search(
        r"impact_score[\s\S]{0,200}CHECK[\s\S]{0,200}BETWEEN\s+0\s+AND\s+1",
        sql, re.IGNORECASE,
    ), "impact_score must have BETWEEN 0 AND 1 check"


def test_migration_037_headline_length_constraint():
    """headline ≤ 120 chars per OpenAPI contract."""
    sql = MIGRATION.read_text(encoding="utf-8")
    # Either VARCHAR(120) or a CHECK constraint
    has_varchar = re.search(r"headline\s+VARCHAR\s*\(\s*120\s*\)", sql, re.IGNORECASE)
    has_check = re.search(
        r"headline[\s\S]{0,200}CHECK[\s\S]{0,200}length\s*\(\s*headline\s*\)\s*<=\s*120",
        sql, re.IGNORECASE,
    )
    assert has_varchar or has_check, (
        "headline must enforce ≤ 120 chars (VARCHAR(120) or CHECK)"
    )


def test_migration_037_summary_length_constraint():
    """summary ≤ 500 chars per OpenAPI contract."""
    sql = MIGRATION.read_text(encoding="utf-8")
    has_varchar = re.search(r"summary\s+VARCHAR\s*\(\s*500\s*\)", sql, re.IGNORECASE)
    has_check = re.search(
        r"summary[\s\S]{0,200}CHECK[\s\S]{0,200}length\s*\(\s*summary\s*\)\s*<=\s*500",
        sql, re.IGNORECASE,
    )
    assert has_varchar or has_check


def test_migration_037_event_id_fk_to_market_events():
    sql = MIGRATION.read_text(encoding="utf-8")
    pattern = r"event_id[\s\S]{0,200}REFERENCES\s+market_events\s*\(\s*id\s*\)"
    assert re.search(pattern, sql, re.IGNORECASE), (
        "event_id must FK to market_events(id)"
    )


def test_migration_037_superseded_by_self_fk():
    sql = MIGRATION.read_text(encoding="utf-8")
    pattern = r"superseded_by[\s\S]{0,200}REFERENCES\s+signals\s*\(\s*id\s*\)"
    assert re.search(pattern, sql, re.IGNORECASE), (
        "superseded_by must FK to signals(id) (self-reference)"
    )


def test_migration_037_creates_required_indexes():
    """Per SPEC-016 §1.2 + OpenAPI intel.yaml access patterns."""
    sql = MIGRATION.read_text(encoding="utf-8")
    required_indexes = [
        ("idx_signals_event",
         r"CREATE\s+INDEX\s+IF\s+NOT\s+EXISTS\s+idx_signals_event\s+ON\s+signals\s*\(\s*event_id"),
        ("idx_signals_status_impact",
         r"CREATE\s+INDEX\s+IF\s+NOT\s+EXISTS\s+idx_signals_status_impact\s+ON\s+signals\s*\([\s\S]{0,150}status[\s\S]{0,150}impact_tier[\s\S]{0,150}created_at"),
        ("idx_signals_primary_entity",
         r"CREATE\s+INDEX\s+IF\s+NOT\s+EXISTS\s+idx_signals_primary_entity\s+ON\s+signals\s*\([\s\S]{0,150}primary_entity_type[\s\S]{0,150}primary_entity_id"),
        ("idx_signals_kbq",
         r"CREATE\s+INDEX\s+IF\s+NOT\s+EXISTS\s+idx_signals_kbq\s+ON\s+signals\s+USING\s+GIN\s*\(\s*kbq_tags"),
        ("idx_signals_supersedence",
         r"CREATE\s+INDEX\s+IF\s+NOT\s+EXISTS\s+idx_signals_supersedence\s+ON\s+signals\s*\(\s*superseded_by"),
    ]
    for name, pattern in required_indexes:
        assert re.search(pattern, sql, re.IGNORECASE), f"Missing/wrong index: {name}"


def test_migration_037_idempotent():
    sql = MIGRATION.read_text(encoding="utf-8")
    sql_no_comments = re.sub(r"--[^\n]*", "", sql)
    assert "CREATE TABLE IF NOT EXISTS" in sql_no_comments.upper()
    # Indexes must all be IF NOT EXISTS
    indexes = re.findall(r"CREATE\s+INDEX\s+(\S+)", sql_no_comments, re.IGNORECASE)
    if_not_exists = re.findall(
        r"CREATE\s+INDEX\s+IF\s+NOT\s+EXISTS", sql_no_comments, re.IGNORECASE
    )
    assert len(indexes) == len(if_not_exists), (
        "All CREATE INDEX must use IF NOT EXISTS"
    )


# ────────────────────────────────────────────────────────────────────
# Cat 2 — live DB schema checks (skip if no DB)
# ────────────────────────────────────────────────────────────────────

@db_required
def test_signals_table_exists(db):
    rows = db.fetch_all(
        "SELECT 1 FROM information_schema.tables WHERE table_name = 'signals'"
    )
    assert len(rows) == 1


@db_required
def test_signals_columns_present(db):
    rows = db.fetch_all(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'signals'"
    )
    cols = {r["column_name"] for r in rows}
    required = {
        "id", "event_id", "kbq_tags", "headline", "summary", "direction",
        "confidence_tier", "trust_score", "impact_tier", "impact_score",
        "rule_version_id", "primary_entity_type", "primary_entity_id",
        "primary_entity_name", "related_entity_ids", "evidence_document_ids",
        "superseded_by", "supersedence_reason", "status", "created_at",
        "reviewed_by", "reviewed_at", "shipped_at",
    }
    missing = required - cols
    assert missing == set(), f"missing columns: {missing}"


@db_required
def test_signals_check_constraints_enforced(db):
    """Try inserting bad values; expect constraint violations."""
    # Confidence tier outside enum
    with pytest.raises(Exception):
        db.execute(
            "INSERT INTO signals (event_id, headline, confidence_tier, trust_score, "
            "impact_tier, impact_score, rule_version_id, primary_entity_type, "
            "primary_entity_id, evidence_document_ids) "
            "VALUES (gen_random_uuid(), 'h', 'invalid_tier', 0.5, 'high', 0.5, "
            "'v0', 'drug', 'some-id', ARRAY[gen_random_uuid()])"
        )
    # trust_score out of range
    with pytest.raises(Exception):
        db.execute(
            "INSERT INTO signals (event_id, headline, confidence_tier, trust_score, "
            "impact_tier, impact_score, rule_version_id, primary_entity_type, "
            "primary_entity_id, evidence_document_ids) "
            "VALUES (gen_random_uuid(), 'h', 'confirmed', 1.5, 'high', 0.5, "
            "'v0', 'drug', 'some-id', ARRAY[gen_random_uuid()])"
        )


@db_required
def test_signals_evidence_must_be_non_empty(db):
    """The no-fabrication invariant: empty evidence array must fail."""
    with pytest.raises(Exception):
        db.execute(
            "INSERT INTO signals (event_id, headline, confidence_tier, trust_score, "
            "impact_tier, impact_score, rule_version_id, primary_entity_type, "
            "primary_entity_id, evidence_document_ids) "
            "VALUES (gen_random_uuid(), 'h', 'confirmed', 0.9, 'high', 0.9, "
            "'v0', 'drug', 'some-id', ARRAY[]::uuid[])"
        )


@db_required
def test_signals_indexes_created(db):
    rows = db.fetch_all(
        "SELECT indexname FROM pg_indexes WHERE tablename = 'signals'"
    )
    found = {r["indexname"] for r in rows}
    expected = {
        "idx_signals_event",
        "idx_signals_status_impact",
        "idx_signals_primary_entity",
        "idx_signals_kbq",
        "idx_signals_supersedence",
    }
    missing = expected - found
    assert missing == set(), f"missing indexes: {missing}"


@db_required
def test_signals_status_default_is_candidate(db):
    """Default status must be 'candidate' so reviewer queue gets new signals."""
    rows = db.fetch_all(
        "SELECT column_default FROM information_schema.columns "
        "WHERE table_name = 'signals' AND column_name = 'status'"
    )
    assert len(rows) == 1
    default = (rows[0]["column_default"] or "").lower()
    assert "candidate" in default, f"status default should be 'candidate', got {default!r}"
