"""SPEC-021 PD strengthenings — war_game_engine unit tests.

Covers the three reviewer asks:
  1. numeric confidence_score (0..1) with categorical derivation
  2. post-LLM evidence validation against the live DB
  3. dossier coverage statement
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from services import war_game_engine as eng


# ────────────────────────────────────────────────────────────────────
# Confidence helpers
# ────────────────────────────────────────────────────────────────────

class TestConfidenceCalibration:

    def test_categorize_high(self):
        assert eng.categorize_confidence(0.9) == "high"
        assert eng.categorize_confidence(0.66) == "high"

    def test_categorize_medium(self):
        assert eng.categorize_confidence(0.5) == "medium"
        assert eng.categorize_confidence(0.33) == "medium"

    def test_categorize_low(self):
        assert eng.categorize_confidence(0.1) == "low"
        assert eng.categorize_confidence(0.0) == "low"

    def test_coerce_from_numeric_field(self):
        assert eng._coerce_confidence_score({"confidence_score": 0.72}) == 0.72

    def test_coerce_clamps_out_of_range(self):
        assert eng._coerce_confidence_score({"confidence_score": 1.5}) == 1.0
        assert eng._coerce_confidence_score({"confidence_score": -0.2}) == 0.0

    def test_coerce_from_categorical_high(self):
        assert eng._coerce_confidence_score({"confidence": "high"}) == 0.8

    def test_coerce_from_categorical_low(self):
        assert eng._coerce_confidence_score({"confidence": "low"}) == 0.2

    def test_coerce_default_when_missing(self):
        assert eng._coerce_confidence_score({}) == 0.5


# ────────────────────────────────────────────────────────────────────
# Evidence validation
# ────────────────────────────────────────────────────────────────────

class TestEvidenceValidation:

    def _db(self, *, nct_present=False, pmid_present=False, drug_present=False):
        db = MagicMock()
        def fake_fetch_one(sql, params=None):
            s = (sql or "").lower()
            if "from clinical_trials" in s and nct_present:
                return {"?column?": 1}
            if "from pubmed_articles" in s and pmid_present:
                return {"?column?": 1}
            if "from drugs" in s and drug_present:
                return {"?column?": 1}
            return None
        db.fetch_one.side_effect = fake_fetch_one
        return db

    def test_strips_unknown_nct(self):
        db = self._db(nct_present=False)
        validated, stripped = eng.validate_evidence_basis(db, ["NCT99999999"])
        assert validated == []
        assert stripped == ["NCT99999999"]

    def test_keeps_real_nct(self):
        db = self._db(nct_present=True)
        validated, stripped = eng.validate_evidence_basis(db, ["NCT04822181"])
        assert validated == ["NCT04822181"]
        assert stripped == []

    def test_strips_unknown_drug_name(self):
        db = self._db(drug_present=False)
        validated, stripped = eng.validate_evidence_basis(db, ["fakedrugxyz"])
        assert stripped == ["fakedrugxyz"]

    def test_keeps_known_drug_name(self):
        db = self._db(drug_present=True)
        validated, _ = eng.validate_evidence_basis(db, ["semaglutide"])
        assert validated == ["semaglutide"]

    def test_chembl_format_passthrough(self):
        # We can't currently validate ChEMBL — accept the format
        db = self._db()
        validated, stripped = eng.validate_evidence_basis(db, ["CHEMBL1201823"])
        assert validated == ["CHEMBL1201823"]

    def test_empty_list_returns_empty(self):
        db = self._db()
        assert eng.validate_evidence_basis(db, []) == ([], [])


# ────────────────────────────────────────────────────────────────────
# Dossier coverage statement
# ────────────────────────────────────────────────────────────────────

class TestDossierCoverage:

    def test_dossier_includes_coverage_statement(self):
        db = MagicMock()
        # Minimal DB: empty fetch_all everywhere, count returns
        def fake_fetch_all(sql, params=None):
            return []
        def fake_fetch_one(sql, params=None):
            s = (sql or "").lower()
            if "count(*)" in s and "from drugs" in s:
                return {"c": 12}
            if "count(*)" in s and "from clinical_trials" in s:
                return {"c": 25}
            return None
        db.fetch_all.side_effect = fake_fetch_all
        db.fetch_one.side_effect = fake_fetch_one

        dossier = eng.build_competitor_dossier(db, "uuid-pfizer")
        assert "coverage_statement" in dossier
        assert "12" in dossier["coverage_statement"]
        assert "25" in dossier["coverage_statement"]

    def test_dossier_no_company_id_returns_default_coverage(self):
        db = MagicMock()
        dossier = eng.build_competitor_dossier(db, None)
        assert "coverage_statement" in dossier
        assert dossier["drugs"] == []


# ────────────────────────────────────────────────────────────────────
# Reaction normalization with strengthenings
# ────────────────────────────────────────────────────────────────────

class TestReactionNormalization:

    def _db_validates_all(self):
        db = MagicMock()
        def _present(sql, params=None):
            return {"?column?": 1}
        db.fetch_one.side_effect = _present
        return db

    def _db_validates_none(self):
        db = MagicMock()
        db.fetch_one.return_value = None
        return db

    def test_normalize_carries_numeric_score(self):
        db = self._db_validates_all()
        out = eng._normalize_reaction(
            {
                "reaction_type": "counter_launch",
                "headline": "x", "rationale": "y",
                "evidence_basis": ["NCT12345678"],
                "confidence_score": 0.85,
                "scores": {"market_share_delta": 3, "time_to_execute_months": 12,
                           "capex_required_musd": 200, "regulatory_risk": 4,
                           "payer_acceptance": 7},
            },
            {"id": "ent-x", "name": "X"},
            db=db,
        )
        assert out["confidence_score"] == 0.85
        assert out["confidence"] == "high"
        assert out["evidence_validated"] is True
        assert out["stripped_citations"] == []

    def test_normalize_strips_hallucinated_evidence_and_downgrades(self):
        db = self._db_validates_none()
        out = eng._normalize_reaction(
            {
                "reaction_type": "counter_launch",
                "headline": "x", "rationale": "y",
                "evidence_basis": ["NCT99999999", "fakedrug"],
                "confidence_score": 0.7,
                "scores": {},
            },
            {"id": "ent-x", "name": "X"},
            db=db,
        )
        # 0.7 - 2*0.2 = 0.3
        assert out["confidence_score"] == pytest.approx(0.3, abs=0.001)
        assert out["confidence"] == "low"
        assert out["evidence_validated"] is False
        assert set(out["stripped_citations"]) == {"NCT99999999", "fakedrug"}
        assert out["evidence_basis"] == []

    def test_normalize_downgrade_floors_at_zero(self):
        db = self._db_validates_none()
        out = eng._normalize_reaction(
            {
                "reaction_type": "counter_launch",
                "headline": "x", "rationale": "y",
                "evidence_basis": ["x", "y", "z", "a", "b"],
                "confidence_score": 0.2,
                "scores": {},
            },
            {"id": "ent-x", "name": "X"},
            db=db,
        )
        assert out["confidence_score"] == 0.0
        assert out["confidence"] == "low"
