"""Red-team regression suite for the typed drug-mention parser.

Each test maps to a category in the semantic-matching red-team challenge. Every
corrected edge case should add a row here (the challenge's "produce regression
tests from every corrected edge case" requirement).

Run: pytest tests/test_drug_mention_parser.py -v
"""

from __future__ import annotations

import pytest

from domain.pharma.drug_mention_parser import (
    DrugLexicon,
    parse_drug_mention,
)


# ============================================================
# Semaglutide configuration ambiguity (the headline test)
# ============================================================

def test_semaglutide_bare_is_ingredient_only():
    m = parse_drug_mention("semaglutide")
    assert m.substance == "semaglutide"
    assert not m.is_combination
    assert m.strength is None and m.concentration is None and m.volume is None
    assert m.original_text == "semaglutide"


def test_semaglutide_2_5_mL_is_volume_not_strength():
    m = parse_drug_mention("semaglutide 2.5 mL")
    assert m.volume is not None and m.volume.kind == "volume"
    assert m.volume.value == 2.5 and m.volume.unit == "mL"
    assert m.strength is None, "mL must not be read as strength"


def test_semaglutide_2_5_mg_is_strength():
    m = parse_drug_mention("semaglutide 2.5 mg")
    assert m.strength is not None and m.strength.kind == "strength"
    assert m.strength.value == 2.5 and m.strength.unit == "mg"
    assert m.volume is None and m.concentration is None


def test_semaglutide_mg_per_mL_is_concentration():
    m = parse_drug_mention("semaglutide 5.0 mg/mL")
    assert m.concentration is not None and m.concentration.kind == "concentration"
    assert m.concentration.value == 5.0 and m.concentration.unit == "mg/mL"
    assert m.strength is None and m.volume is None, "mg/mL is concentration, not strength or volume"


def test_semaglutide_pen_infers_route_subcutaneous():
    m = parse_drug_mention("semaglutide pen")
    assert m.formulation == "pen"
    assert m.route == "subcutaneous"
    assert m.route_inferred is True, "route from formulation must be marked inferred, not confirmed"


def test_semaglutide_weekly_injection_separates_regimen():
    m = parse_drug_mention("semaglutide weekly injection")
    assert m.substance == "semaglutide"
    assert m.formulation == "injection"
    assert "once_weekly" in m.regimen_flags
    assert m.strength is None


def test_semaglutide_full_presentation():
    m = parse_drug_mention("semaglutide 2.5 mg/mL pen, once weekly")
    assert m.substance == "semaglutide"
    assert m.concentration.value == 2.5
    assert m.formulation == "pen"
    assert m.route == "subcutaneous" and m.route_inferred
    assert "once_weekly" in m.regimen_flags
    assert m.original_text == "semaglutide 2.5 mg/mL pen, once weekly"


# ============================================================
# Category 1 — mono vs combination
# ============================================================

@pytest.mark.parametrize("text,expect_combo,n", [
    ("metformin", False, 1),
    ("metformin + sitagliptin", True, 2),
    ("valsartan", False, 1),
    ("sacubitril / valsartan", True, 2),
    ("amlodipine + atorvastatin", True, 2),
    ("sacubitril and valsartan", True, 2),
])
def test_mono_vs_combination_component_count(text, expect_combo, n):
    m = parse_drug_mention(text)
    assert m.is_combination is expect_combo
    assert len(m.components) == n


def test_combo_slash_not_confused_with_concentration_slash():
    """'sacubitril/valsartan' splits as a combo; 'mg/mL' does not."""
    combo = parse_drug_mention("sacubitril/valsartan")
    assert combo.is_combination and set(combo.components) == {"sacubitril", "valsartan"}
    conc = parse_drug_mention("insulin 100 units/mL")
    assert not conc.is_combination


# ============================================================
# Category 2 — strength / concentration / volume separation
# ============================================================

def test_strength_concentration_volume_are_distinct_fields():
    assert parse_drug_mention("5 mg").strength.value == 5.0
    assert parse_drug_mention("5 mL").volume.value == 5.0
    assert parse_drug_mention("5 mg/mL").concentration.value == 5.0


def test_mg_per_half_mL_computes_concentration():
    m = parse_drug_mention("5 mg per 0.5 mL")
    assert m.concentration is not None
    assert m.concentration.value == 10.0, "5 mg / 0.5 mL = 10 mg/mL"


def test_pen_with_fill_volume_keeps_both():
    m = parse_drug_mention("2.5 mL pen")
    assert m.volume.value == 2.5
    assert m.formulation == "pen"


# ============================================================
# Category 5 — unit & formatting variability (raw text preserved)
# ============================================================

@pytest.mark.parametrize("text,expected_mg", [
    ("5mg", 5.0),
    ("5 mg", 5.0),
    ("5.0 MG", 5.0),
    ("five milligrams", 5.0),
    ("100mcg", 0.1),     # 100 mcg = 0.1 mg
    ("1 g", 1000.0),
])
def test_strength_unit_variability_normalises_to_mg(text, expected_mg):
    m = parse_drug_mention(text)
    assert m.strength is not None
    assert m.strength.value == pytest.approx(expected_mg)
    assert m.strength.raw  # original token preserved


@pytest.mark.parametrize("text,expected_ml", [
    ("0.5ml", 0.5),
    ("0,5 mL", 0.5),   # comma decimal
    ("5 mL", 5.0),
])
def test_volume_unit_variability(text, expected_ml):
    m = parse_drug_mention(text)
    assert m.volume is not None and m.volume.value == pytest.approx(expected_ml)


def test_iu_is_activity_not_strength():
    m = parse_drug_mention("insulin glargine 100 IU")
    assert m.strength is None
    assert any(q.kind == "activity" and q.unit == "IU" for q in m.other_quantities)


def test_original_text_always_preserved():
    raw = "SEMAGLUTIDE 0,5 MG/ML Pen"
    assert parse_drug_mention(raw).original_text == raw


# ============================================================
# Category 4 — formulation & route
# ============================================================

def test_formulation_and_route_typed_separately():
    m = parse_drug_mention("metformin oral tablet")
    assert m.formulation == "tablet"
    assert m.route == "oral" and not m.route_inferred


# ============================================================
# Category 6 — salt / ester / release variants
# ============================================================

def test_salt_token_flagged_not_dropped_silently():
    m = parse_drug_mention("metformin hydrochloride")
    assert "hydrochloride" in m.salt_tokens
    assert m.substance == "metformin"


def test_release_qualifier_preserved():
    m = parse_drug_mention("metformin extended-release 500 mg")
    assert m.release == "extended-release"
    assert m.strength.value == 500.0
    assert m.substance == "metformin"


# ============================================================
# Category 7 — context-dependent mentions (identity vs event)
# ============================================================

def test_negation_flagged():
    m = parse_drug_mention("not currently taking metformin")
    assert "negation" in m.context_flags
    assert m.substance == "metformin"


def test_switch_flagged():
    m = parse_drug_mention("switched from semaglutide to tirzepatide")
    assert "switch" in m.context_flags


def test_dose_change_is_not_product_identity():
    m = parse_drug_mention("increased to 5 mg")
    assert "dose_change" in m.context_flags
    assert m.strength.value == 5.0
    assert m.substance == "", "a bare dose change carries no product identity"


def test_starter_pack_is_regimen_not_identity():
    m = parse_drug_mention("semaglutide starter pack")
    assert "starter_pack" in m.regimen_flags
    assert m.substance == "semaglutide"


# ============================================================
# Brand mapping (Category 3) — lexicon-driven, configurable
# ============================================================

def test_brand_maps_to_generic_when_lexicon_supplies_it():
    lex = DrugLexicon(brands={"ozempic": "semaglutide", "entresto": "sacubitril/valsartan"})
    m = parse_drug_mention("Ozempic 0.5 mg", lexicon=lex)
    assert m.brand == "ozempic"
    assert m.brand_maps_to == "semaglutide"
    assert m.strength.value == 0.5


def test_unknown_brand_not_guessed():
    m = parse_drug_mention("Wegovy", lexicon=DrugLexicon())  # empty brand map
    assert m.brand is None, "no brand lexicon entry -> do not guess"


def test_configurable_lexicon_can_extend_formulations():
    lex = DrugLexicon(formulations=frozenset({"nanoparticle"}))
    m = parse_drug_mention("paclitaxel nanoparticle", lexicon=lex)
    assert m.formulation == "nanoparticle"
