"""Regression tests for the Novavax/Garvan wrong-company attribution repair.

Root cause: stale ``drugs.company_id`` attributed Novo Nordisk's diabetes pipeline
to NOVAVAX, INC. and investigator-trial drugs to the (excluded) Garvan Institute.
The authoritative truth is the trial ``sponsor_name``; we re-derive the company
from the dominant sponsor via a SAFE normalized-exact match (never fuzzy).

Pure tests on the decision helpers + the normalized key (which is what makes
'Novo Nordisk A/S' and 'NOVO NORDISK INC' agree while 'Novavax' stays distinct).
"""
from __future__ import annotations

from scripts.fix_company_misattribution import (
    dominant_sponsor,
    normalized_company_key,
    should_reattribute,
)


# ── normalized key: the safety property of the whole repair ─────────────────────

def test_novo_nordisk_variants_share_a_key_but_novavax_does_not():
    novo_as = normalized_company_key("Novo Nordisk A/S")
    novo_inc = normalized_company_key("NOVO NORDISK INC")
    novavax = normalized_company_key("NOVAVAX, INC.")
    assert novo_as == novo_inc          # sponsor string resolves to the company row
    assert novavax != novo_as           # and never collapses onto Novavax


def test_normalized_key_is_empty_for_blank():
    assert normalized_company_key("") == ""
    assert normalized_company_key(None) == ""


# ── dominant sponsor (mode with a plurality floor) ──────────────────────────────

def test_dominant_sponsor_returns_clear_majority():
    counts = {"Novo Nordisk A/S": 216, "RenJi Hospital": 2, "Eli Lilly and Company": 1}
    assert dominant_sponsor(counts) == "Novo Nordisk A/S"


def test_dominant_sponsor_none_when_no_plurality():
    # no sponsor clears the 50% share floor → don't guess, leave for review
    counts = {"Sponsor A": 5, "Sponsor B": 4, "Sponsor C": 3}
    assert dominant_sponsor(counts, min_share=0.5) is None


def test_dominant_sponsor_none_on_empty():
    assert dominant_sponsor({}) is None


def test_dominant_sponsor_ignores_blank_sponsors():
    counts = {"": 100, "Novo Nordisk A/S": 10}
    assert dominant_sponsor(counts) == "Novo Nordisk A/S"


# ── reattribution decision ──────────────────────────────────────────────────────

def test_reattribute_only_when_resolved_differs_from_current():
    assert should_reattribute(resolved_company_id="novo-id",
                              current_company_id="novavax-id") is True
    # already correct → no-op (idempotent)
    assert should_reattribute(resolved_company_id="novo-id",
                              current_company_id="novo-id") is False
    # sponsor didn't resolve to any company → never null out an existing link
    assert should_reattribute(resolved_company_id=None,
                              current_company_id="novavax-id") is False
