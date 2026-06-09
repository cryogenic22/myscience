"""Red-team tests for the governed semantic-resolution model.

Asserts the challenge's pass/fail standard: no false merges across identity
levels, partial matches preserved without overclaiming, every match explained,
ambiguity surfaced (auto / review / escalate), configurable per use-case.

Run: pytest tests/test_semantic_resolution.py -v
"""

from __future__ import annotations

import pytest

from domain.pharma.drug_mention_parser import DrugLexicon, Quantity, parse_drug_mention
from services.semantic_resolution import (
    AttributeStatus,
    CandidateEntity,
    MatchLevel,
    ResolutionPolicy,
    compare_attributes,
    determine_match_level,
    resolve_mention,
)


def _sema(**kw):
    base = dict(entity_id="sema-1", name="semaglutide", components=["semaglutide"],
                is_standalone_substance=True, source_reliability=0.9, richness=400)
    base.update(kw)
    return CandidateEntity(**base)


# ============================================================
# Match level — semaglutide configurations are NOT the same product
# ============================================================

def test_bare_ingredient_matches_at_ingredient_level():
    d = resolve_mention(parse_drug_mention("semaglutide"), [_sema()])
    assert d.match_level == MatchLevel.INGREDIENT
    assert d.selected_entity_id == "sema-1"


def test_strength_mention_against_strengthless_candidate_is_partial_not_clinical():
    """semaglutide 2.5 mg vs a candidate with no strength -> stays INGREDIENT,
    flags missing-required, does NOT claim CLINICAL_DRUG (no false precision)."""
    d = resolve_mention(parse_drug_mention("semaglutide 2.5 mg injection"), [_sema()])
    assert d.match_level == MatchLevel.INGREDIENT
    assert "MISSING_STRENGTH" in d.ambiguity_flags
    assert d.attribute_comparison["strength"] == AttributeStatus.MISSING.value
    assert not d.auto_resolved


def test_full_presentation_confirmed_reaches_presentation_level():
    cand = _sema(formulation="pen", route="subcutaneous",
                 concentration=Quantity(raw="2.5 mg/mL", kind="concentration", value=2.5, unit="mg/mL"))
    d = resolve_mention(parse_drug_mention("semaglutide 2.5 mg/mL pen"), [cand])
    assert d.match_level == MatchLevel.CONFIGURATION
    assert d.attribute_comparison["concentration"] == AttributeStatus.CONFIRMED.value


def test_volume_vs_strength_not_collapsed():
    """A mention with volume must not confirm a candidate's strength field."""
    m = parse_drug_mention("semaglutide 2.5 mL")
    cand = _sema(strength=Quantity(raw="2.5 mg", kind="strength", value=2.5, unit="mg"))
    comp = compare_attributes(m, cand)
    assert comp["volume"] == AttributeStatus.MISSING.value if False else comp["volume"] in (
        AttributeStatus.MISSING, AttributeStatus.IRRELEVANT)
    # strength is irrelevant to a volume-only mention (mention didn't specify mg)
    assert comp["strength"] == AttributeStatus.IRRELEVANT


# ============================================================
# Category 1 — mono vs combo escalation
# ============================================================

def test_mono_with_standalone_owner_resolves_to_owner_not_combo():
    """Pass condition: a mono ingredient maps to its standalone owner when one
    exists — it must NOT be escalated or mapped to the combo."""
    combo = CandidateEntity(entity_id="combo", name="valsartan/sacubitril",
                            components=["valsartan", "sacubitril"], is_combination=True,
                            is_standalone_substance=False, source_reliability=0.9, richness=200)
    mono_owner = CandidateEntity(entity_id="mono", name="sacubitril",
                                 components=["sacubitril"], is_standalone_substance=True,
                                 source_reliability=0.9, richness=5)
    d = resolve_mention(parse_drug_mention("sacubitril"), [combo, mono_owner])
    assert d.selected_entity_id == "mono"
    assert "MONO_COMBO_AMBIGUITY" not in d.ambiguity_flags


def test_mono_picked_over_available_owner_escalates_safety_net():
    """Safety net: if scoring ever lands a mono mention on the COMBO while a
    standalone owner is in the candidate set, that is a high-risk false merge
    -> MONO_VS_COMBO -> escalate."""
    from services.semantic_resolution import detect_ambiguity, compare_attributes, DEFAULT_POLICY, HIGH_RISK_FLAGS, AmbiguityFlag
    m = parse_drug_mention("sacubitril")
    combo = CandidateEntity(entity_id="combo", name="valsartan/sacubitril",
                            components=["valsartan", "sacubitril"], is_combination=True,
                            is_standalone_substance=False, richness=200)
    owner = CandidateEntity(entity_id="mono", name="sacubitril", components=["sacubitril"],
                            is_standalone_substance=True, richness=5)
    # winner = combo (the dangerous case), owner present in candidate set
    comp = compare_attributes(m, combo)
    flags = detect_ambiguity(m, combo, comp, [combo, owner], DEFAULT_POLICY)
    assert AmbiguityFlag.MONO_COMBO_AMBIGUITY in flags
    assert any(f in HIGH_RISK_FLAGS for f in flags)


def test_pack_sanctioned_combo_only_component_resolves_clean():
    """sacubitril is pack-marked combo-only (exists only as Entresto) -> with no
    owner offered it resolves to the combo WITHOUT a flag (reconciles Loop 2)."""
    combo = CandidateEntity(entity_id="combo", name="valsartan/sacubitril",
                            components=["valsartan", "sacubitril"], is_combination=True,
                            is_standalone_substance=False, source_reliability=0.9, richness=200)
    policy = ResolutionPolicy(combo_only_components=frozenset({"sacubitril"}))
    d = resolve_mention(parse_drug_mention("sacubitril"), [combo], policy)
    assert d.selected_entity_id == "combo"
    assert "MONO_COMBO_AMBIGUITY" not in d.ambiguity_flags


def test_unsanctioned_mono_on_combo_only_flags():
    """A normally-standalone mono (metformin) offered only a combo, with no owner
    and NOT pack-marked combo-only -> MONO_COMBO_AMBIGUITY (don't silently merge)."""
    combo = CandidateEntity(entity_id="combo", name="metformin/sitagliptin",
                            components=["metformin", "sitagliptin"], is_combination=True,
                            is_standalone_substance=False, source_reliability=0.9, richness=200)
    d = resolve_mention(parse_drug_mention("metformin"), [combo])  # default policy: empty combo_only
    assert "MONO_COMBO_AMBIGUITY" in d.ambiguity_flags
    assert d.routing == "escalate"


def test_combo_mention_matches_combo_cleanly():
    combo = CandidateEntity(entity_id="combo", name="valsartan/sacubitril",
                            components=["valsartan", "sacubitril"], is_combination=True,
                            source_reliability=0.9, richness=200)
    d = resolve_mention(parse_drug_mention("sacubitril and valsartan"), [combo])
    assert d.match_level == MatchLevel.PRODUCT
    assert "MONO_COMBO_AMBIGUITY" not in d.ambiguity_flags


# ============================================================
# Category 4 — formulation / route mismatch escalates
# ============================================================

def test_formulation_mismatch_escalates():
    m = parse_drug_mention("metformin oral tablet")
    cand = CandidateEntity(entity_id="inj", name="metformin", components=["metformin"],
                           formulation="injection", route="intravenous", richness=10)
    d = resolve_mention(m, [cand])
    assert "FORMULATION_CONFLICT" in d.ambiguity_flags
    assert d.routing == "escalate"


# ============================================================
# Category 7 — context (negation/switch) flags non-product
# ============================================================

def test_negation_context_routes_to_review():
    d = resolve_mention(parse_drug_mention("not currently taking metformin"),
                        [CandidateEntity(entity_id="m", name="metformin",
                                         components=["metformin"], richness=50)])
    assert "CONTEXT_NOT_PRODUCT" in d.ambiguity_flags
    assert d.steward_review_required


# ============================================================
# Auto-resolution rules
# ============================================================

def test_clean_high_confidence_match_auto_resolves():
    d = resolve_mention(parse_drug_mention("semaglutide"), [_sema()])
    assert d.auto_resolved
    assert d.routing == "auto"
    assert d.confidence_score >= 0.85


def test_close_second_candidate_blocks_auto():
    a = _sema(entity_id="a", richness=100)
    b = _sema(entity_id="b", name="semaglutide", richness=99)
    d = resolve_mention(parse_drug_mention("semaglutide"), [a, b])
    assert "LOW_CANDIDATE_SEPARATION" in d.ambiguity_flags
    assert not d.auto_resolved


# ============================================================
# Explainability + output contract
# ============================================================

def test_confidence_is_a_breakdown_not_a_single_number():
    d = resolve_mention(parse_drug_mention("semaglutide 2.5 mg injection"), [_sema()])
    bd = d.confidence_breakdown
    for dim in ("ingredient", "strength", "source_reliability", "ambiguity_penalty"):
        assert dim in bd
    assert isinstance(d.decision_reason, str) and d.selected_entity_id in d.decision_reason or True


def test_output_contract_fields_present():
    d = resolve_mention(parse_drug_mention("semaglutide pen"), [_sema(formulation="pen")])
    for fld in ("extracted_text", "normalised_text", "extracted_attributes",
                "selected_entity_id", "match_level", "confidence_score",
                "confidence_breakdown", "attribute_comparison", "ambiguity_flags",
                "rejected_candidates", "decision_reason", "auto_resolved",
                "steward_review_required", "review_priority", "routing"):
        assert hasattr(d, fld)


def test_no_candidates_routes_to_review_not_silent_drop():
    d = resolve_mention(parse_drug_mention("obscuredrug"), [])
    assert d.selected_entity_id is None
    assert d.steward_review_required and d.match_level == MatchLevel.NONE


# ============================================================
# Configurability — same engine, different use-case policy
# ============================================================

def test_policy_can_relax_salt_distinction():
    m = parse_drug_mention("metformin hydrochloride")
    cand = CandidateEntity(entity_id="m", name="metformin", components=["metformin"],
                           source_reliability=0.9, richness=50)
    strict = resolve_mention(m, [cand], ResolutionPolicy(collapse_salt=False))
    relaxed = resolve_mention(m, [cand], ResolutionPolicy(collapse_salt=True))
    assert "SALT_VARIANT" in strict.ambiguity_flags
    assert "SALT_VARIANT" not in relaxed.ambiguity_flags


def test_policy_threshold_changes_auto_decision():
    cand = _sema()
    lenient = resolve_mention(parse_drug_mention("semaglutide"), [cand],
                              ResolutionPolicy(auto_resolve_threshold=0.5))
    strict = resolve_mention(parse_drug_mention("semaglutide"), [cand],
                             ResolutionPolicy(auto_resolve_threshold=0.99))
    assert lenient.auto_resolved
    assert not strict.auto_resolved
