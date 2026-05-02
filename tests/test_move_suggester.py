"""SPEC-021 Phase A.5 — Move Suggester unit tests.

Covers:
  - build_player_dossier shape + coverage statement
  - suggest_moves end-to-end with mocked LLM
  - move_type validation (drops invalid moves)
  - confidence + impact score ranges
  - evidence validation + downgrade
  - LLM-disabled returns []
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from services import move_suggester as ms


# ────────────────────────────────────────────────────────────────────
# Fake LLM
# ────────────────────────────────────────────────────────────────────

class _StubLLM:
    """Mimics the subset of LLMSynthesizer the suggester uses."""

    def __init__(self, *, enabled=True, reply: str = ""):
        self.enabled = enabled
        self._reply = reply
        self.calls = []

    def raw_chat(self, *, system, user, max_tokens=900):
        self.calls.append({"system": system, "user": user, "max_tokens": max_tokens})
        return self._reply


def _stub_db_for_dossier(*, drug_count=4, trial_count=3):
    """A DB whose count queries return what we say. Validates by default."""
    db = MagicMock()

    def fake_fetch_one(sql, params=None):
        s = (sql or "").lower()
        if "count(*)" in s and "from drugs" in s:
            return {"c": drug_count}
        if "count(*)" in s and "from clinical_trials" in s:
            return {"c": trial_count}
        # Validation lookups — pretend everything resolves.
        # Patterns ignore whitespace so multi-line SELECT ... FROM drugs
        # WHERE ... still matches.
        if "select 1 from drugs" in s or "select 1 from clinical_trials" in s:
            return {"?column?": 1}
        if "select 1 from pubmed_articles" in s or "select 1 from companies" in s:
            return {"?column?": 1}
        # Drug name fallback (multi-line)
        if "from drugs" in s and "lower(generic_name)" in s:
            return {"?column?": 1}
        return None

    def fake_fetch_all(sql, params=None):
        return []

    db.fetch_one.side_effect = fake_fetch_one
    db.fetch_all.side_effect = fake_fetch_all
    return db


# ────────────────────────────────────────────────────────────────────
# build_player_dossier
# ────────────────────────────────────────────────────────────────────

class TestPlayerDossier:

    def test_no_entity_id_returns_default_coverage(self):
        db = _stub_db_for_dossier()
        d = ms.build_player_dossier(db, "company", None)
        assert "coverage_statement" in d
        assert d["drugs"] == []
        assert d["trials"] == []

    def test_non_company_entity_returns_skipped(self):
        db = _stub_db_for_dossier()
        d = ms.build_player_dossier(db, "drug", "drug-123")
        # We only build for company entities in MVP
        assert d["drugs"] == []
        assert d["coverage_statement"]

    def test_company_entity_includes_coverage_counts(self):
        db = _stub_db_for_dossier(drug_count=12, trial_count=25)
        d = ms.build_player_dossier(db, "company", "ent-novo")
        assert "12" in d["coverage_statement"]
        assert "25" in d["coverage_statement"]


# ────────────────────────────────────────────────────────────────────
# suggest_moves end-to-end
# ────────────────────────────────────────────────────────────────────

class TestSuggestMoves:

    def _good_reply(self, suggestions: list) -> str:
        return json.dumps({"suggestions": suggestions})

    def test_llm_disabled_returns_empty(self):
        db = _stub_db_for_dossier()
        llm = _StubLLM(enabled=False)
        out = ms.suggest_moves(
            db, llm,
            player_entity_type="company", player_entity_id="ent-x",
            player_name="X", n=3,
        )
        assert out == []

    def test_returns_normalized_suggestions(self):
        db = _stub_db_for_dossier()
        reply = self._good_reply([
            {
                "move_type": "trial_readout",
                "move_payload": {"target_drug": "semaglutide"},
                "rationale": "Player has Phase 3 trial reading out Q3.",
                "evidence_basis": ["semaglutide", "NCT04822181"],
                "expected_impact_score": 0.8,
                "confidence_score": 0.7,
            },
            {
                "move_type": "label_expansion",
                "move_payload": {"target_drug": "semaglutide", "expansion": "MASH"},
                "rationale": "Existing label allows expansion to MASH.",
                "evidence_basis": ["semaglutide"],
                "expected_impact_score": 0.6,
                "confidence_score": 0.55,
            },
        ])
        llm = _StubLLM(enabled=True, reply=reply)
        out = ms.suggest_moves(
            db, llm,
            player_entity_type="company", player_entity_id="ent-novo",
            player_name="Novo Nordisk", n=3,
        )
        assert len(out) == 2
        assert out[0]["move_type"] == "trial_readout"
        assert out[0]["expected_impact_score"] == 0.8
        assert out[0]["confidence_score"] == 0.7
        assert out[0]["confidence"] == "high"
        assert out[0]["evidence_validated"] is True

    def test_drops_invalid_move_type(self):
        db = _stub_db_for_dossier()
        reply = self._good_reply([
            {
                "move_type": "invent_a_drug",  # not in MOVE_TYPES
                "move_payload": {},
                "rationale": "...",
                "evidence_basis": [],
                "expected_impact_score": 0.9,
                "confidence_score": 0.9,
            },
            {
                "move_type": "price_cut",
                "move_payload": {"target_drug": "x"},
                "rationale": "...",
                "evidence_basis": [],
                "expected_impact_score": 0.4,
                "confidence_score": 0.5,
            },
        ])
        llm = _StubLLM(enabled=True, reply=reply)
        out = ms.suggest_moves(
            db, llm,
            player_entity_type="company", player_entity_id="ent-x",
            player_name="X", n=3,
        )
        # Invalid move dropped, only price_cut remains
        assert len(out) == 1
        assert out[0]["move_type"] == "price_cut"

    def test_sorts_by_expected_impact_descending(self):
        db = _stub_db_for_dossier()
        reply = self._good_reply([
            {"move_type": "price_cut", "move_payload": {}, "rationale": "",
             "evidence_basis": [], "expected_impact_score": 0.3,
             "confidence_score": 0.5},
            {"move_type": "trial_readout", "move_payload": {}, "rationale": "",
             "evidence_basis": [], "expected_impact_score": 0.9,
             "confidence_score": 0.5},
            {"move_type": "label_expansion", "move_payload": {}, "rationale": "",
             "evidence_basis": [], "expected_impact_score": 0.6,
             "confidence_score": 0.5},
        ])
        llm = _StubLLM(enabled=True, reply=reply)
        out = ms.suggest_moves(
            db, llm,
            player_entity_type="company", player_entity_id="ent-x",
            player_name="X", n=3,
        )
        assert [s["move_type"] for s in out] == [
            "trial_readout", "label_expansion", "price_cut",
        ]

    def test_evidence_validation_strips_hallucinated(self):
        # DB that fails ALL validation lookups (everything is hallucinated)
        db = MagicMock()
        def fake_fetch_one(sql, params=None):
            s = (sql or "").lower()
            if "count(*)" in s:
                return {"c": 5}
            return None  # nothing validates
        def fake_fetch_all(sql, params=None):
            return []
        db.fetch_one.side_effect = fake_fetch_one
        db.fetch_all.side_effect = fake_fetch_all

        reply = self._good_reply([{
            "move_type": "trial_readout",
            "move_payload": {},
            "rationale": "x",
            "evidence_basis": ["NCT99999999", "fakedrug"],
            "expected_impact_score": 0.7,
            "confidence_score": 0.7,
        }])
        llm = _StubLLM(enabled=True, reply=reply)
        out = ms.suggest_moves(
            db, llm,
            player_entity_type="company", player_entity_id="ent-x",
            player_name="X", n=3,
        )
        assert len(out) == 1
        assert out[0]["evidence_validated"] is False
        # 0.7 - 2*0.2 = 0.3
        assert out[0]["confidence_score"] == pytest.approx(0.3, abs=0.001)
        assert set(out[0]["stripped_citations"]) == {"NCT99999999", "fakedrug"}
        assert out[0]["evidence_basis"] == []

    def test_clamps_impact_score(self):
        db = _stub_db_for_dossier()
        reply = self._good_reply([{
            "move_type": "price_cut", "move_payload": {}, "rationale": "",
            "evidence_basis": [], "expected_impact_score": 1.7,  # out of range
            "confidence_score": 0.5,
        }])
        llm = _StubLLM(enabled=True, reply=reply)
        out = ms.suggest_moves(
            db, llm,
            player_entity_type="company", player_entity_id="ent-x",
            player_name="X", n=3,
        )
        assert out[0]["expected_impact_score"] == 1.0

    def test_returns_empty_when_llm_returns_garbage(self):
        db = _stub_db_for_dossier()
        llm = _StubLLM(enabled=True, reply="not json at all")
        out = ms.suggest_moves(
            db, llm,
            player_entity_type="company", player_entity_id="ent-x",
            player_name="X", n=3,
        )
        assert out == []

    def test_signal_context_included_in_prompt(self):
        db = _stub_db_for_dossier()
        llm = _StubLLM(enabled=True, reply=self._good_reply([]))
        ms.suggest_moves(
            db, llm,
            player_entity_type="company", player_entity_id="ent-x",
            player_name="X",
            signal_context={"kbq_tags": ["clinical"], "headline": "Trial readout pending"},
            n=3,
        )
        assert len(llm.calls) == 1
        assert "TRIGGERING SIGNAL CONTEXT" in llm.calls[0]["user"]
        assert "clinical" in llm.calls[0]["user"]
