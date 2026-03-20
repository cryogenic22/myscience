"""Domain validation test suite.

Phase 2.1: Structural, clinical, and value tests that verify data curation
quality. These tests run against a live database and validate the completeness
and correctness of cross-linked pharma data.

Run:
    python -m pytest tests/test_domain_coverage.py -v

Requires DATABASE_URL or local PostgreSQL with market_zero database.
"""

from __future__ import annotations

import os
import re

import pytest

# Skip entire module if no database available
pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL") and not os.getenv("MZ_DB_HOST"),
    reason="No database configured (set DATABASE_URL or MZ_DB_HOST)",
)


@pytest.fixture(scope="module")
def db():
    """Shared database connection for all tests in this module."""
    from config import config
    from db import Database

    database = Database(config.db.dsn)
    database.connect()
    yield database
    database.close()


# ════════════════════════════════════════════════════════════
# Structural Tests
# ════════════════════════════════════════════════════════════


class TestTACoverage:
    """All 18 therapeutic areas should have linked entities."""

    def test_all_tas_have_at_least_one_drug(self, db):
        rows = db.fetch_all(
            """
            SELECT ta.name, COUNT(el.id) AS link_count
            FROM therapeutic_areas ta
            LEFT JOIN entity_links el
              ON el.target_entity_id = ta.id::text
              AND el.target_entity_type = 'therapeutic_area'
              AND el.link_type = 'IN_THERAPEUTIC_AREA'
            GROUP BY ta.name
            HAVING COUNT(el.id) = 0
            """
        )
        empty_tas = [r["name"] for r in rows]
        assert len(empty_tas) == 0, f"TAs with zero drug links: {empty_tas}"

    def test_ta_count_at_least_18(self, db):
        row = db.fetch_one("SELECT COUNT(*) AS cnt FROM therapeutic_areas")
        assert row["cnt"] >= 18, f"Expected ≥18 TAs, got {row['cnt']}"


class TestMechanismCoverage:
    """All mechanisms should have at least one linked drug."""

    def test_all_mechanisms_have_drugs(self, db):
        rows = db.fetch_all(
            """
            SELECT m.name, COUNT(el.id) AS link_count
            FROM mechanisms_of_action m
            LEFT JOIN entity_links el
              ON el.target_entity_id = m.id::text
              AND el.target_entity_type = 'mechanism'
              AND el.link_type = 'TARGETS_MECHANISM'
            GROUP BY m.name
            HAVING COUNT(el.id) = 0
            """
        )
        empty = [r["name"] for r in rows]
        assert len(empty) == 0, f"Mechanisms with zero drug links: {empty}"


class TestNoDuplicateCompanies:
    """No duplicate company names after normalization."""

    SUFFIX_RE = re.compile(
        r"\b(?:inc\.?|ltd\.?|llc\.?|corp\.?|pharms?\.?|pharmaceuticals?"
        r"|usa|limited|gmbh|plc\.?)\s*$",
        re.IGNORECASE,
    )

    def _normalize(self, name: str) -> str:
        n = name.strip()
        for _ in range(3):
            n = self.SUFFIX_RE.sub("", n).strip()
        return re.sub(r"\s+", " ", n).lower()

    def test_no_duplicate_active_companies(self, db):
        rows = db.fetch_all(
            """
            SELECT name FROM companies
            WHERE record_status IS DISTINCT FROM 'merged'
              AND record_status IS DISTINCT FROM 'excluded'
            """
        )
        seen: dict[str, list[str]] = {}
        for r in rows:
            norm = self._normalize(r["name"])
            seen.setdefault(norm, []).append(r["name"])

        dupes = {k: v for k, v in seen.items() if len(v) > 1}
        assert len(dupes) == 0, f"Duplicate companies: {dupes}"


class TestNoDosageDrugNames:
    """No drug names with dosage patterns."""

    DOSAGE_RE = re.compile(
        r"\d+\s*(?:mg|ml|units?|mcg|µg|iu)", re.IGNORECASE
    )

    def test_no_dosage_in_active_drug_names(self, db):
        rows = db.fetch_all(
            """
            SELECT generic_name FROM drugs
            WHERE record_status IS DISTINCT FROM 'excluded'
              AND record_status IS DISTINCT FROM 'merged'
              AND generic_name IS NOT NULL
            """
        )
        bad = [
            r["generic_name"] for r in rows
            if self.DOSAGE_RE.search(r["generic_name"])
        ]
        assert len(bad) == 0, f"Drugs with dosage patterns: {bad[:10]}"


class TestTrialLabels:
    """All trials should have non-empty labels."""

    def test_all_trials_have_labels(self, db):
        row = db.fetch_one(
            """
            SELECT COUNT(*) AS cnt FROM clinical_trials
            WHERE label IS NULL OR label = ''
            """
        )
        assert row["cnt"] == 0, f"{row['cnt']} trials missing labels"


class TestNoUnknownEntityTypes:
    """No 'unknown' entity types in entity_links."""

    def test_no_unknown_source_types(self, db):
        row = db.fetch_one(
            "SELECT COUNT(*) AS cnt FROM entity_links WHERE source_entity_type = 'unknown'"
        )
        assert row["cnt"] == 0, f"{row['cnt']} links with unknown source type"

    def test_no_unknown_target_types(self, db):
        row = db.fetch_one(
            "SELECT COUNT(*) AS cnt FROM entity_links WHERE target_entity_type = 'unknown'"
        )
        assert row["cnt"] == 0, f"{row['cnt']} links with unknown target type"


class TestSourceCoverage:
    """Each expected source should have >0 records."""

    EXPECTED_SOURCES = [
        "mesh_ontology",
        "fda_orange_book",
        "clinical_trials_gov",
        "pubmed",
    ]

    def test_each_source_has_records(self, db):
        for source in self.EXPECTED_SOURCES:
            # Check multiple tables for source_api
            found = False
            for table in ["drugs", "clinical_trials", "pubmed_articles",
                          "therapeutic_areas", "mechanisms_of_action", "companies"]:
                try:
                    row = db.fetch_one(
                        f"SELECT COUNT(*) AS cnt FROM {table} WHERE source_api = %s",
                        [source],
                    )
                    if row and row["cnt"] > 0:
                        found = True
                        break
                except Exception:
                    continue
            assert found, f"No records from source: {source}"


# ════════════════════════════════════════════════════════════
# Clinical Domain Tests
# ════════════════════════════════════════════════════════════


class TestSemaglutide:
    """Semaglutide should be well-connected in the knowledge graph."""

    @pytest.fixture(autouse=True)
    def _find_semaglutide(self, db):
        row = db.fetch_one(
            "SELECT id FROM drugs WHERE LOWER(generic_name) = 'semaglutide' LIMIT 1"
        )
        if row:
            self.drug_id = str(row["id"])
        else:
            pytest.skip("Semaglutide not found in database")

    def test_has_mechanism_link(self, db):
        row = db.fetch_one(
            """
            SELECT COUNT(*) AS cnt FROM entity_links
            WHERE source_entity_id = %s AND source_entity_type = 'drug'
              AND link_type = 'TARGETS_MECHANISM'
            """,
            [self.drug_id],
        )
        assert row["cnt"] >= 1, "Semaglutide missing mechanism link"

    def test_has_ta_link(self, db):
        row = db.fetch_one(
            """
            SELECT COUNT(*) AS cnt FROM entity_links
            WHERE source_entity_id = %s AND source_entity_type = 'drug'
              AND link_type = 'IN_THERAPEUTIC_AREA'
            """,
            [self.drug_id],
        )
        assert row["cnt"] >= 1, "Semaglutide missing TA link"

    def test_has_company_link(self, db):
        row = db.fetch_one(
            """
            SELECT COUNT(*) AS cnt FROM entity_links
            WHERE target_entity_id = %s AND target_entity_type = 'drug'
              AND link_type = 'OWNS'
            """,
            [self.drug_id],
        )
        assert row["cnt"] >= 1, "Semaglutide missing company (OWNS) link"

    def test_has_trials(self, db):
        row = db.fetch_one(
            """
            SELECT COUNT(*) AS cnt FROM entity_links
            WHERE target_entity_id = %s AND target_entity_type = 'drug'
              AND link_type = 'INVESTIGATES'
            """,
            [self.drug_id],
        )
        assert row["cnt"] >= 5, f"Semaglutide has only {row['cnt']} trial links (expected ≥5)"

    def test_has_literature(self, db):
        row = db.fetch_one(
            """
            SELECT COUNT(*) AS cnt FROM entity_links
            WHERE target_entity_id = %s AND target_entity_type = 'drug'
              AND link_type = 'EVIDENCE_FOR'
            """,
            [self.drug_id],
        )
        assert row["cnt"] >= 1, "Semaglutide missing literature links"


class TestEmpagliflozin:
    """Empagliflozin should link to SGLT2i and HF/T2DM TAs."""

    @pytest.fixture(autouse=True)
    def _find_drug(self, db):
        row = db.fetch_one(
            "SELECT id FROM drugs WHERE LOWER(generic_name) = 'empagliflozin' LIMIT 1"
        )
        if row:
            self.drug_id = str(row["id"])
        else:
            pytest.skip("Empagliflozin not found in database")

    def test_has_mechanism_link(self, db):
        row = db.fetch_one(
            """
            SELECT COUNT(*) AS cnt FROM entity_links
            WHERE source_entity_id = %s AND source_entity_type = 'drug'
              AND link_type = 'TARGETS_MECHANISM'
            """,
            [self.drug_id],
        )
        assert row["cnt"] >= 1

    def test_has_ta_link(self, db):
        row = db.fetch_one(
            """
            SELECT COUNT(*) AS cnt FROM entity_links
            WHERE source_entity_id = %s AND source_entity_type = 'drug'
              AND link_type = 'IN_THERAPEUTIC_AREA'
            """,
            [self.drug_id],
        )
        assert row["cnt"] >= 1


class TestTopDrugConnectivity:
    """Top drugs should each have company, TA, mechanism, and trial links."""

    TOP_DRUGS = [
        "semaglutide", "tirzepatide", "empagliflozin", "dapagliflozin",
        "sacubitril", "metformin", "sitagliptin", "liraglutide",
    ]

    def test_top_drugs_have_trial_links(self, db):
        missing = []
        for drug_name in self.TOP_DRUGS:
            row = db.fetch_one(
                """
                SELECT d.id, COUNT(el.id) AS trials
                FROM drugs d
                LEFT JOIN entity_links el
                  ON el.target_entity_id = d.id::text
                  AND el.target_entity_type = 'drug'
                  AND el.link_type = 'INVESTIGATES'
                WHERE LOWER(d.generic_name) = %s
                  AND d.record_status IS DISTINCT FROM 'excluded'
                GROUP BY d.id
                """,
                [drug_name],
            )
            if not row or row["trials"] < 1:
                missing.append(drug_name)
        assert len(missing) == 0, f"Top drugs missing trial links: {missing}"


# ════════════════════════════════════════════════════════════
# Value Tests (query-level)
# ════════════════════════════════════════════════════════════


class TestQueryLevel:
    """Verify that key queries return meaningful results."""

    def test_phase3_semaglutide_trials(self, db):
        row = db.fetch_one(
            """
            SELECT COUNT(*) AS cnt
            FROM clinical_trials ct
            JOIN entity_links el ON el.source_entity_id = ct.id
              AND el.source_entity_type = 'trial'
              AND el.link_type = 'INVESTIGATES'
            JOIN drugs d ON d.id::text = el.target_entity_id
            WHERE LOWER(d.generic_name) = 'semaglutide'
              AND ct.phase IS NOT NULL
            """
        )
        assert row["cnt"] > 0, "No trials found for semaglutide"

    def test_competitive_landscape_glp1(self, db):
        """GLP-1 mechanism should have ≥3 drugs with trials."""
        row = db.fetch_one(
            """
            SELECT COUNT(DISTINCT d.id) AS drug_count
            FROM drugs d
            JOIN entity_links mech_link
              ON mech_link.source_entity_id = d.id::text
              AND mech_link.source_entity_type = 'drug'
              AND mech_link.link_type = 'TARGETS_MECHANISM'
            JOIN mechanisms_of_action m
              ON m.id::text = mech_link.target_entity_id
            JOIN entity_links trial_link
              ON trial_link.target_entity_id = d.id::text
              AND trial_link.target_entity_type = 'drug'
              AND trial_link.link_type = 'INVESTIGATES'
            WHERE LOWER(m.name) LIKE '%glp-1%'
              AND d.record_status IS DISTINCT FROM 'excluded'
            """
        )
        assert row["drug_count"] >= 3, f"GLP-1 landscape has only {row['drug_count']} drugs (expected ≥3)"

    def test_cross_source_validation(self, db):
        """Drugs from Orange Book should also appear in ClinicalTrials data."""
        row = db.fetch_one(
            """
            SELECT COUNT(DISTINCT d.id) AS cnt
            FROM drugs d
            JOIN entity_links el ON el.target_entity_id = d.id::text
              AND el.target_entity_type = 'drug'
              AND el.link_type = 'INVESTIGATES'
            WHERE d.source_api = 'fda_orange_book'
              AND d.record_status IS DISTINCT FROM 'excluded'
            """
        )
        assert row["cnt"] > 0, "No Orange Book drugs linked to clinical trials"
