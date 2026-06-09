"""L1b-ii — bulk RxNorm/ATC crosswalk loader (RxNav REST → governed records).

Pure tests on the response parsers + governed candidate builders. No HTTP, no DB.
The governed engine (services.ontology_crosswalk.classify) decides relation/scope;
these tests pin the SME invariants through the RxNav path:
  * an RxNorm ingredient (IN) is identity-grade (exact, substance_level);
  * an ATC class is class-level ONLY (never molecule identity) — and is loaded
    UNCURATED (source_curated=False), unlike the SME seed.
"""
from __future__ import annotations

from services.ontology_crosswalk import classify, load_crosswalk_pack
from services.rxnav_crosswalk import (
    atc_level,
    build_rxnav_atc_candidate,
    build_rxnorm_ingredient_candidate,
    parse_deepest_atc,
    parse_rxcui,
)

_PACK = load_crosswalk_pack()


# ── response parsers ────────────────────────────────────────────────────────────

def test_parse_rxcui_picks_first_id():
    assert parse_rxcui({"idGroup": {"rxnormId": ["1991302", "999"]}}) == "1991302"
    assert parse_rxcui({"idGroup": {}}) is None
    assert parse_rxcui({}) is None


def test_atc_level_by_code_length():
    assert atc_level("A") == 1            # anatomical main group
    assert atc_level("A10") == 2          # therapeutic subgroup
    assert atc_level("A10B") == 3         # pharmacological subgroup
    assert atc_level("A10BJ") == 4        # chemical subgroup
    assert atc_level("A10BJ06") == 5      # chemical substance
    assert atc_level("") is None


def _rxclass_payload(classes):
    return {"rxclassDrugInfoList": {"rxclassDrugInfo": [
        {"rxclassMinConceptItem": {"classId": c, "className": n, "classType": "ATC1-4"}}
        for c, n in classes
    ]}}


def test_parse_deepest_atc_returns_most_specific_class():
    payload = _rxclass_payload([
        ("A", "ALIMENTARY TRACT AND METABOLISM"),
        ("A10", "DRUGS USED IN DIABETES"),
        ("A10B", "BLOOD GLUCOSE LOWERING DRUGS, EXCL. INSULINS"),
        ("A10BJ", "Glucagon-like peptide-1 (GLP-1) analogues"),
    ])
    deepest = parse_deepest_atc(payload)
    assert deepest["code"] == "A10BJ"        # the L4, not the L1
    assert deepest["level"] == 4
    assert "GLP-1" in deepest["label"]


def test_parse_deepest_atc_none_when_empty():
    assert parse_deepest_atc(_rxclass_payload([])) is None
    assert parse_deepest_atc({}) is None


# ── governed candidate builders (SME invariants through the RxNav path) ─────────

def test_rxnorm_ingredient_is_identity_grade():
    rec = classify(build_rxnorm_ingredient_candidate("1991302"), _PACK)
    assert rec.relation == "exact"
    assert rec.scope == "substance_level"
    assert rec.action in {"approved_auto", "approved_with_audit"}


def test_atc_class_is_never_molecule_identity():
    # an L4 ATC class maps to a drug_class — asserting molecule identity is forbidden
    rec = classify(build_rxnav_atc_candidate("A10BJ", 4, _PACK), _PACK)
    assert rec.relation != "exact" or rec.scope != "substance_level"
    assert rec.relation != "rejected"        # drug_class target is allowed
    # and it must NOT be loaded as a curated mapping (raw release, not SME-reviewed)
    cand = build_rxnav_atc_candidate("A10BJ", 4, _PACK)
    assert cand.source_curated is False


def test_atc_l1_is_broad_therapeutic_area():
    rec = classify(build_rxnav_atc_candidate("A", 1, _PACK), _PACK)
    assert rec.relation != "rejected"
    assert rec.scope == "therapeutic_area_level"
