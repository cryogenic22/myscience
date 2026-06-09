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
# Allowlist gate — unenumerated illegal intents must ALSO be refused
# (these were the holes an independent review found; RED before the allowlist).
# ============================================================

@pytest.mark.parametrize("from_system,tty,level,to_target,flag", [
    ("atc", None, 4, "brand", "PRODUCT_CONFIGURATION_REQUIRED_BUT_ONLY_ATC_AVAILABLE"),
    ("atc", None, 4, "market_authorisation", "PRODUCT_CONFIGURATION_REQUIRED_BUT_ONLY_ATC_AVAILABLE"),
    ("atc", None, 4, "product_configuration", "PRODUCT_CONFIGURATION_REQUIRED_BUT_ONLY_ATC_AVAILABLE"),
    ("atc", None, 3, "molecule", "ATC_TOO_BROAD_FOR_EXACT_MATCH"),
    ("rxnorm", "IN", None, "pricing_configuration", "PRICING_REQUIRES_CONFIGURATION_NOT_ATC"),
    ("rxnorm", "IN", None, "payer_policy_product", "PAYER_POLICY_CLASS_NOT_EQUAL_ATC_CLASS"),
    ("rxnorm", "IN", None, "market_authorisation", "TARGET_EXCEEDS_SOURCE_IDENTITY_GRADE"),
    ("rxnorm", "BN", None, "product_configuration", "TARGET_EXCEEDS_SOURCE_IDENTITY_GRADE"),
])
def test_allowlist_refuses_illegal_intent(from_system, tty, level, to_target, flag):
    r = classify(CrosswalkCandidate(
        from_system=from_system, tty=tty, level=level, to_target=to_target,
        method="exact_identifier"), _PACK)
    assert r.relation == "rejected", f"{from_system}/{tty or level}->{to_target} must refuse"
    assert flag in r.flags
    assert r.action == "rejected_or_quarantined"


def test_atc_can_never_create_exact_product_identity():
    """The cardinal sin: no ATC level may yield a non-rejected identity-grade match."""
    for level in (1, 2, 3, 4, 5):
        for target in ("exact_product", "brand", "product_configuration", "market_authorisation", "pricing_configuration"):
            r = classify(CrosswalkCandidate(from_system="atc", level=level, to_target=target), _PACK)
            assert r.relation == "rejected", f"ATC L{level}->{target} leaked as {r.relation}"


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


def test_stale_source_cannot_auto_approve():
    """Pack band requires a current source for approved_auto."""
    r = classify(CrosswalkCandidate(
        from_system="rxnorm", tty="IN", to_target="molecule",
        method="exact_identifier", stale_source=True), _PACK)
    assert r.action == "approved_with_audit", "stale source must not auto-approve"


def test_unknown_method_is_flagged_not_silent():
    r = classify(CrosswalkCandidate(
        from_system="rxnorm", tty="IN", to_target="molecule", method="totally_made_up"), _PACK)
    assert "UNKNOWN_MAPPING_METHOD" in r.flags


def test_combination_without_m2m_is_not_exact():
    r = classify(CrosswalkCandidate(
        from_system="rxnorm", tty="MIN", to_target="component_set"), _PACK)
    assert r.relation != "exact", "ambiguous combination must not assert exact identity"
    assert "COMBINATION_COMPONENT_AMBIGUITY" in r.flags


def test_precise_ingredient_conflict_raises_flag():
    r = classify(CrosswalkCandidate(
        from_system="rxnorm", tty="PIN", to_target="molecule_variant",
        method="exact_identifier", precise_ingredient_conflict=True), _PACK)
    assert "PRECISE_INGREDIENT_CONFLICT" in r.flags


def test_pharma_core_pack_parses_and_has_levels():
    import yaml, pathlib
    p = pathlib.Path(__file__).parent.parent / "domain" / "pharma" / "packs" / "pharma_core.yaml"
    core = yaml.safe_load(p.read_text(encoding="utf-8"))
    assert "configuration_level" in core["identity_levels"]
    # molecule prioritises rxnorm ingredient + ATC L5 for identity/class
    prio = core["entity_types"]["molecule"]["external_identifier_priority"]
    assert prio[0] == "rxnorm_ingredient_rxcui" and "atc_level_5_code" in prio


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
