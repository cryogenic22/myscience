"""D4: literature relink matching tests (pure, no DB)."""

from __future__ import annotations

from scripts.relink_literature import (
    DrugName,
    build_name_index,
    match_drug_in_text,
)


def _rows():
    return [
        {"drug_id": "d-sema", "name": "semaglutide", "richness": 800},
        {"drug_id": "d-tirz", "name": "tirzepatide", "richness": 260},
        {"drug_id": "d-tirz", "name": "Mounjaro", "richness": 260},  # brand
        {"drug_id": "d-noise", "name": "beta blockers", "richness": 5},  # stop
        {"drug_id": "d-short", "name": "abc", "richness": 1},  # too short
    ]


def test_index_drops_short_and_stop_names():
    idx = build_name_index(_rows())
    assert "semaglutide" in idx
    assert "mounjaro" in idx
    assert "beta blockers" not in idx
    assert "abc" not in idx


def test_index_keeps_richer_on_collision():
    rows = [
        {"drug_id": "d-poor", "name": "semaglutide", "richness": 3},
        {"drug_id": "d-rich", "name": "semaglutide", "richness": 800},
    ]
    idx = build_name_index(rows)
    assert idx["semaglutide"].drug_id == "d-rich"


def test_match_word_boundary_hit():
    idx = build_name_index(_rows())
    dn = match_drug_in_text("A trial of semaglutide in obesity.", idx)
    assert dn is not None and dn.drug_id == "d-sema"


def test_match_brand_name():
    idx = build_name_index(_rows())
    dn = match_drug_in_text("Mounjaro reduced HbA1c.", idx)
    assert dn is not None and dn.drug_id == "d-tirz"


def test_no_substring_false_positive():
    """'semaglutides' (no word boundary at end of 'semaglutide') still matches
    via \\b? No — \\bsemaglutide\\b requires a boundary; 'presemaglutidex' must
    not match."""
    idx = build_name_index(_rows())
    assert match_drug_in_text("presemaglutidex compound", idx) is None


def test_prefers_longer_more_specific_name():
    rows = [
        {"drug_id": "d-a", "name": "glutide", "richness": 999},
        {"drug_id": "d-sema", "name": "semaglutide", "richness": 10},
    ]
    idx = build_name_index(rows)
    dn = match_drug_in_text("semaglutide and glutide study", idx)
    # longer name wins despite lower richness
    assert dn.drug_id == "d-sema"


def test_no_match_returns_none():
    idx = build_name_index(_rows())
    assert match_drug_in_text("A study with no known drug.", idx) is None
    assert match_drug_in_text("", idx) is None
