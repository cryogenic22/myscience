"""Tests for scripts/backfill_mechanisms.py — mechanism_id backfill.

TDD: Verify pure matching logic and DB integration with MagicMock.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock


# ── Pure function tests (no DB) ──


class TestMatchMechanism:
    """Verify the 4-level matching cascade in match_mechanism()."""

    def test_exact_map_semaglutide(self):
        from scripts.backfill_mechanisms import match_mechanism
        assert match_mechanism("semaglutide") == "Glucagon-Like Peptide-1 Receptor Agonists"

    def test_exact_map_empagliflozin(self):
        from scripts.backfill_mechanisms import match_mechanism
        assert match_mechanism("empagliflozin") == "Sodium-Glucose Transporter 2 Inhibitors"

    def test_exact_map_metformin(self):
        from scripts.backfill_mechanisms import match_mechanism
        assert match_mechanism("metformin") == "Metformin"

    def test_inn_suffix_gliflozin(self):
        from scripts.backfill_mechanisms import match_mechanism
        assert match_mechanism("bexagliflozin") == "Sodium-Glucose Transporter 2 Inhibitors"

    def test_inn_suffix_gliptin(self):
        from scripts.backfill_mechanisms import match_mechanism
        assert match_mechanism("teneligliptin") == "Dipeptidyl-Peptidase IV Inhibitors"

    def test_inn_suffix_sartan(self):
        from scripts.backfill_mechanisms import match_mechanism
        assert match_mechanism("azilsartan") == "Angiotensin II Type 1 Receptor Blockers"

    def test_insulin_prefix(self):
        from scripts.backfill_mechanisms import match_mechanism
        assert match_mechanism("insulin xyz") == "Insulin"

    def test_metformin_combo(self):
        from scripts.backfill_mechanisms import match_mechanism
        # "metformin/sitagliptin" matches -gliptin suffix before metformin check
        # Pure metformin combo without INN suffix hits the metformin fallback
        assert match_mechanism("metformin/empagliflozin") == "Sodium-Glucose Transporter 2 Inhibitors"
        assert match_mechanism("metformin extended release") == "Metformin"

    def test_unrecognized_returns_none(self):
        from scripts.backfill_mechanisms import match_mechanism
        assert match_mechanism("unknowndrug123") is None

    def test_case_insensitive(self):
        from scripts.backfill_mechanisms import match_mechanism
        assert match_mechanism("SEMAGLUTIDE") == "Glucagon-Like Peptide-1 Receptor Agonists"

    def test_whitespace_stripped(self):
        from scripts.backfill_mechanisms import match_mechanism
        assert match_mechanism("  semaglutide  ") == "Glucagon-Like Peptide-1 Receptor Agonists"

    def test_exact_map_takes_priority_over_suffix(self):
        """Exact map should match before INN suffix fallback."""
        from scripts.backfill_mechanisms import match_mechanism
        # sitagliptin is in the exact map AND matches -gliptin suffix
        result = match_mechanism("sitagliptin")
        assert result == "Dipeptidyl-Peptidase IV Inhibitors"


# ── DB integration tests (MagicMock) ──


@pytest.fixture
def mock_db():
    """MagicMock DB with mechanism + drug data pre-loaded."""
    db = MagicMock()
    return db


class TestBackfillMechanisms:
    """Verify DB interaction via backfill_mechanisms(db, dry_run)."""

    def test_dry_run_no_writes(self, mock_db):
        mock_db.fetch_all.side_effect = [
            # mechanisms
            [{"id": "m1", "name": "Glucagon-Like Peptide-1 Receptor Agonists"}],
            # drugs without mechanism
            [{"id": "d1", "generic_name": "semaglutide"}],
        ]
        mock_db.fetch_one.side_effect = [
            {"cnt": 1},  # final coverage count
            {"cnt": 1},  # total drugs count
        ]

        from scripts.backfill_mechanisms import backfill_mechanisms
        result = backfill_mechanisms(mock_db, dry_run=True)
        assert result["total_updated"] == 1
        mock_db.execute.assert_not_called()

    def test_updates_drug_with_mechanism(self, mock_db):
        mock_db.fetch_all.side_effect = [
            [{"id": "m1", "name": "Glucagon-Like Peptide-1 Receptor Agonists"}],
            [{"id": "d1", "generic_name": "semaglutide"}],
        ]
        mock_db.fetch_one.side_effect = [
            {"cnt": 1},
            {"cnt": 1},
        ]

        from scripts.backfill_mechanisms import backfill_mechanisms
        result = backfill_mechanisms(mock_db, dry_run=False)
        assert result["total_updated"] == 1
        assert mock_db.execute.call_count == 1
        call_args = mock_db.execute.call_args[0]
        assert "UPDATE drugs SET mechanism_id" in call_args[0]
        assert call_args[1] == ["m1", "d1"]

    def test_skips_unrecognized_drug(self, mock_db):
        mock_db.fetch_all.side_effect = [
            [{"id": "m1", "name": "Glucagon-Like Peptide-1 Receptor Agonists"}],
            [{"id": "d1", "generic_name": "unknowndrug123"}],
        ]
        mock_db.fetch_one.side_effect = [
            {"cnt": 0},
            {"cnt": 1},
        ]

        from scripts.backfill_mechanisms import backfill_mechanisms
        result = backfill_mechanisms(mock_db, dry_run=False)
        assert result["total_updated"] == 0
        mock_db.execute.assert_not_called()

    def test_counts_direct_vs_suffix(self, mock_db):
        mock_db.fetch_all.side_effect = [
            # mechanisms
            [
                {"id": "m1", "name": "Glucagon-Like Peptide-1 Receptor Agonists"},
                {"id": "m2", "name": "Sodium-Glucose Transporter 2 Inhibitors"},
            ],
            # drugs: one exact match, one suffix match
            [
                {"id": "d1", "generic_name": "semaglutide"},
                {"id": "d2", "generic_name": "bexagliflozin"},
            ],
        ]
        mock_db.fetch_one.side_effect = [
            {"cnt": 2},
            {"cnt": 2},
        ]

        from scripts.backfill_mechanisms import backfill_mechanisms
        result = backfill_mechanisms(mock_db, dry_run=False)
        assert result["direct_matches"] == 1
        assert result["suffix_matches"] == 1
        assert result["total_updated"] == 2

    def test_skips_mechanism_not_in_db(self, mock_db):
        """Drug matches a pattern but mechanism name isn't in the DB."""
        mock_db.fetch_all.side_effect = [
            [],  # no mechanisms in DB
            [{"id": "d1", "generic_name": "semaglutide"}],
        ]
        mock_db.fetch_one.side_effect = [
            {"cnt": 0},
            {"cnt": 1},
        ]

        from scripts.backfill_mechanisms import backfill_mechanisms
        result = backfill_mechanisms(mock_db, dry_run=False)
        assert result["total_updated"] == 0
