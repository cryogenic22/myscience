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


class TestCoAgonistMechanisms:
    """CLIN-02 regression: incretin co-agonists are NOT pure GLP-1 agonists."""

    def test_tirzepatide_is_dual_gip_glp1(self):
        from scripts.backfill_mechanisms import match_mechanism, MECH_GIP_GLP1
        assert match_mechanism("tirzepatide") == MECH_GIP_GLP1
        assert "GLP-1" != match_mechanism("tirzepatide")  # not the pure class

    def test_semaglutide_stays_pure_glp1(self):
        from scripts.backfill_mechanisms import match_mechanism, MECH_GLP1
        assert match_mechanism("semaglutide") == MECH_GLP1

    def test_co_agonist_family_corrected(self):
        from scripts.backfill_mechanisms import (
            match_mechanism, MECH_TRIPLE, MECH_GCG_GLP1, MECH_GLP1)
        assert match_mechanism("retatrutide") == MECH_TRIPLE
        for d in ("survodutide", "cotadutide", "mazdutide", "pemvidutide"):
            assert match_mechanism(d) == MECH_GCG_GLP1, d
        # none of them is the pure GLP-1 class
        assert MECH_GLP1 not in {match_mechanism(d) for d in
                                 ("tirzepatide", "retatrutide", "survodutide")}

    def test_corrections_subset_of_map(self):
        """The correction scope must agree with the backfill map (one truth)."""
        from scripts.backfill_mechanisms import (
            CO_AGONIST_CORRECTIONS, DRUG_MECHANISM_MAP)
        for g, mech in CO_AGONIST_CORRECTIONS.items():
            assert DRUG_MECHANISM_MAP[g] == mech, g

    def test_curated_specs_well_formed(self):
        from scripts.backfill_mechanisms import CURATED_CO_AGONIST_MECHANISMS
        names = {s["name"] for s in CURATED_CO_AGONIST_MECHANISMS}
        assert len(names) == len(CURATED_CO_AGONIST_MECHANISMS)  # no dup names
        for s in CURATED_CO_AGONIST_MECHANISMS:
            assert s["mechanism_class"] and len(s["scope_note"]) > 30


class TestCorrectDrugMechanisms:
    """find_mistagged repoints only mis-tagged co-agonists, idempotently."""

    def test_skips_already_correct_and_repoints_wrong(self):
        from scripts.correct_drug_mechanisms import find_mistagged
        from scripts.backfill_mechanisms import MECH_GIP_GLP1
        mech_ids = {MECH_GIP_GLP1: "dual-id"}
        db = MagicMock()

        def fetch_all(sql, params):
            generic = params[0]
            if generic == "tirzepatide":
                # one mis-tagged (on the GLP-1 row) + one already correct
                return [{"id": "d-wrong", "generic_name": "tirzepatide",
                         "mechanism_id": "glp1-id"},
                        {"id": "d-ok", "generic_name": "tirzepatide",
                         "mechanism_id": "dual-id"}]
            return []
        db.fetch_all.side_effect = fetch_all
        out = find_mistagged(db, mech_ids)
        ids = {t["drug_id"] for t in out}
        assert "d-wrong" in ids and "d-ok" not in ids
        assert all(t["to_mech"] == "dual-id" for t in out)


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
