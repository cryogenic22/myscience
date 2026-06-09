"""Tests for the governed RxNorm/ATC crosswalk engine (Loop L1a).

Includes a data-driven runner over the pack's eval golden set (SME docs/pharmcore_atc.md
§9) — every corrected crosswalk edge case becomes a permanent test.
"""

from __future__ import annotations

import pytest

from services.ontology_crosswalk import (
    CrosswalkCandidate,
    classify,
    load_crosswalk_pack,
)

_PACK = load_crosswalk_pack()


def _cand(d: dict) -> CrosswalkCandidate:
    """Build a candidate from an eval-case dict."""
    return CrosswalkCandidate(
        from_system=d["from_system"],
        to_target=d["to_target"],
        tty=d.get("tty"),
        level=d.get("level"),
        method=d.get("method"),
        external_id=d.get("atc_code"),
        many_to_many=bool(d.get("many_to_many", False)),
        combination=bool(d.get("combination", False)),
    )


# ============================================================
# Hard rules — the cardinal sins must be refused
# ============================================================

def test_rxnorm_scd_reverse_to_atc_exact_is_rejected():
    r = classify(_cand({"from_system": "rxnorm", "tty": "SCD", "to_target": "atc_exact_reverse"}), _PACK)
    assert r.relation == "rejected"
    assert "RXNORM_TOO_SPECIFIC_FOR_REVERSE_MATCH" in r.flags
    assert r.action == "rejected_or_quarantined"


def test_atc_level4_to_exact_product_is_rejected():
    r = classify(_cand({"from_system": "atc", "level": 4, "to_target": "exact_product"}), _PACK)
    assert r.relation == "rejected" and "ATC_TOO_BROAD_FOR_EXACT_MATCH" in r.flags


def test_atc_to_pricing_is_rejected():
    r = classify(_cand({"from_system": "atc", "level": 5, "to_target": "pricing_configuration"}), _PACK)
    assert r.relation == "rejected" and "PRICING_REQUIRES_CONFIGURATION_NOT_ATC" in r.flags


def test_atc_class_to_payer_product_is_rejected():
    r = classify(_cand({"from_system": "atc", "level": 4, "to_target": "payer_policy_product"}), _PACK)
    assert "PAYER_POLICY_CLASS_NOT_EQUAL_ATC_CLASS" in r.flags
    assert r.action == "rejected_or_quarantined"


def test_rxnorm_brand_to_market_authorisation_is_rejected():
    r = classify(_cand({"from_system": "rxnorm", "tty": "BN", "to_target": "market_authorisation"}), _PACK)
    assert r.relation == "rejected" and "BRAND_MARKET_AMBIGUITY" in r.flags


# ============================================================
# Legal mappings — relation/scope/action
# ============================================================

def test_rxnorm_ingredient_to_molecule_exact_auto():
    r = classify(CrosswalkCandidate(
        from_system="rxnorm", tty="IN", to_target="molecule", method="exact_identifier_loaded_from_source"), _PACK)
    assert r.relation == "exact" and r.scope == "substance_level"
    assert r.confidence >= 0.95 and r.action == "approved_auto"


def test_atc_level4_to_drug_class_exact():
    r = classify(_cand({"from_system": "atc", "level": 4, "to_target": "drug_class", "method": "atc_hierarchy"}), _PACK)
    assert r.relation == "exact" and r.scope == "drug_class_level"


def test_atc_level5_to_molecule_is_related_not_exact():
    """ATC L5 is a substance CLASSIFICATION, not identity -> related, never exact."""
    r = classify(_cand({"from_system": "atc", "level": 5, "to_target": "molecule"}), _PACK)
    assert r.relation == "related"


def test_many_to_many_is_flagged_and_never_auto():
    r = classify(CrosswalkCandidate(
        from_system="rxnorm", tty="IN", to_target="molecule",
        method="exact_identifier_loaded_from_source", many_to_many=True), _PACK)
    assert "RXNORM_ATC_MANY_TO_MANY" in r.flags
    assert r.relation == "related", "many-to-many must not assert exact identity"
    assert r.action == "review_required"


def test_combination_min_is_flagged():
    r = classify(_cand({"from_system": "rxnorm", "tty": "MIN", "to_target": "component_set"}), _PACK)
    assert "COMBINATION_COMPONENT_AMBIGUITY" in r.flags


def test_unknown_concept_rejected():
    r = classify(CrosswalkCandidate(from_system="rxnorm", tty="ZZZ", to_target="molecule"), _PACK)
    assert r.relation == "rejected" and "UNKNOWN_EXTERNAL_CONCEPT" in r.flags


def test_confidence_is_explainable_breakdown():
    r = classify(CrosswalkCandidate(
        from_system="rxnorm", tty="IN", to_target="molecule",
        method="exact_identifier_loaded_from_source"), _PACK)
    assert "base" in r.confidence_breakdown and "final" in r.confidence_breakdown


# ============================================================
# Data-driven eval golden set (SME §9, embedded in the pack)
# ============================================================

@pytest.mark.parametrize("case", _PACK["eval_cases"], ids=[c["id"] for c in _PACK["eval_cases"]])
def test_eval_case(case):
    r = classify(_cand(case["candidate"]), _PACK)
    if "expect_relation" in case:
        assert r.relation == case["expect_relation"], \
            f"{case['id']}: relation {r.relation} != {case['expect_relation']} ({case.get('gold_reason')})"
    if "expect_scope" in case:
        assert r.scope == case["expect_scope"]
    for flag in case.get("expect_flags", []):
        assert flag in r.flags, f"{case['id']}: expected flag {flag}, got {r.flags}"
    if "expect_action" in case:
        assert r.action == case["expect_action"], \
            f"{case['id']}: action {r.action} != {case['expect_action']}"
