"""L1/L2 — wire ontology_support in semantic_resolution._score to real crosswalk
evidence (was a hardcoded 0.6 placeholder).

Pure tests on the grader + the DB→dict loader shape. The SME rule (docs/pharmcore_atc.md)
is load-bearing here: ATC is class-reasoning ONLY and must never grade exact
product identity, so an ATC mapping gives only a modest bump above neutral, while
an RxNorm identity (exact/narrower) mapping grades full identity support.
"""
from __future__ import annotations

from services.ontology_crosswalk import fetch_ontology_codes
from services.semantic_resolution import (
    CandidateEntity,
    DrugMention,
    ontology_support_score,
)

NEUTRAL = 0.6


def _cand(ontology_codes=None):
    return CandidateEntity(entity_id="d1", name="semaglutide",
                           components=["semaglutide"],
                           ontology_codes=ontology_codes or [])


# ── grader ────────────────────────────────────────────────────────────────────

def test_no_evidence_is_neutral_placeholder_value():
    # preserves prior behaviour for the ~1210 drugs with no crosswalk record
    assert ontology_support_score(_cand([])) == NEUTRAL


def test_atc_mapping_is_class_level_modest_not_identity():
    score = ontology_support_score(_cand([
        {"system": "atc", "code": "A10BJ06", "relation": "related",
         "scope": "substance_level", "confidence": 0.9},
    ]))
    assert NEUTRAL < score < 1.0          # a bump, but NOT identity-grade
    assert score == 0.7


def test_rxnorm_exact_is_identity_grade():
    score = ontology_support_score(_cand([
        {"system": "rxnorm", "code": "1991302", "relation": "exact",
         "scope": "clinical_drug", "confidence": 0.95},
    ]))
    assert score == 1.0


def test_rxnorm_nonexact_below_identity_grade():
    score = ontology_support_score(_cand([
        {"system": "rxnorm", "code": "1551291", "relation": "related",
         "confidence": 0.8},
    ]))
    assert score == 0.75


def test_best_evidence_wins_across_multiple_records():
    score = ontology_support_score(_cand([
        {"system": "atc", "code": "A10BJ06", "relation": "related", "confidence": 0.9},
        {"system": "rxnorm", "code": "1991302", "relation": "exact", "confidence": 0.95},
    ]))
    assert score == 1.0                    # RxNorm-exact dominates the ATC bump


def test_rejected_and_low_confidence_records_are_ignored():
    assert ontology_support_score(_cand([
        {"system": "rxnorm", "code": "x", "relation": "rejected", "confidence": 0.95},
    ])) == NEUTRAL                          # rejected → no support, no penalty
    assert ontology_support_score(_cand([
        {"system": "atc", "code": "A10BJ06", "relation": "related", "confidence": 0.2},
    ])) == NEUTRAL                          # below the 0.5 confidence floor


# ── wired into _score ──────────────────────────────────────────────────────────

def test_score_uses_real_ontology_support_not_placeholder():
    from services.semantic_resolution import _score, DEFAULT_POLICY, compare_attributes
    m = DrugMention(original_text="semaglutide", normalized_text="semaglutide",
                    substance="semaglutide", components=["semaglutide"],
                    is_combination=False)
    c = _cand([{"system": "atc", "code": "A10BJ06", "relation": "related",
                "confidence": 0.9}])
    comparison = compare_attributes(m, c)
    bd = _score(m, c, comparison, [], DEFAULT_POLICY)
    assert bd.ontology_support == 0.7      # not the old hardcoded 0.6


# ── DB→dict loader shape (MockDB, no live connection) ───────────────────────────

class _MockDB:
    def __init__(self, rows):
        self._rows = rows

    def fetch_all(self, sql, params=None):
        return self._rows


def test_fetch_ontology_codes_maps_columns_and_skips_rejected():
    db = _MockDB([
        {"external_system": "atc", "external_id": "A10BJ06",
         "external_label": "A10BJ06 (GLP-1 analogues)", "mapping_relation": "related",
         "mapping_scope": "substance_level", "mapping_confidence": 0.9},
    ])
    codes = fetch_ontology_codes(db, "15b2232d")
    assert codes == [{
        "system": "atc", "code": "A10BJ06", "label": "A10BJ06 (GLP-1 analogues)",
        "relation": "related", "scope": "substance_level", "confidence": 0.9,
    }]


def test_fetch_ontology_codes_returns_empty_on_db_error():
    class _BoomDB:
        def fetch_all(self, sql, params=None):
            raise RuntimeError("connection lost")
    assert fetch_ontology_codes(_BoomDB(), "d1") == []
