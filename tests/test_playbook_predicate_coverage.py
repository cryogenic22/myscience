"""DB-free tests for the playbook predicate-coverage analyzer (data-lane)."""

from __future__ import annotations

import pathlib

import yaml

from scripts.playbook_predicate_coverage import (
    classify_coverage,
    dimension_predicates,
)

_PB = pathlib.Path(__file__).parent.parent / "domain" / "pharma" / "packs" / "pharma_question_playbooks.yaml"


def test_covered_when_rows_high_and_some_present():
    v, total, missing = classify_coverage(
        ["efficacy_endpoint", "trial_result"], {"efficacy_endpoint": 4062, "trial_result": 44})
    assert v == "covered"
    assert total == 4106 and missing == []


def test_gap_when_all_predicates_absent():
    v, total, missing = classify_coverage(
        ["formulary_status", "prior_authorisation", "step_edit"], {"pricing_intent": 4})
    assert v == "gap"
    assert total == 0
    assert set(missing) == {"formulary_status", "prior_authorisation", "step_edit"}


def test_partial_band():
    v, total, missing = classify_coverage(
        ["regulatory_approval", "label_indication"], {"regulatory_approval": 67, "label_indication": 0})
    assert v == "partial"
    assert "label_indication" in missing


def test_generic_fallback_does_not_inflate_to_covered():
    """development lens trap: high rows from a generic predicate (clinical_trial)
    must NOT read as covered when the lens-specific predicates are all missing."""
    v, total, missing = classify_coverage(
        ["phase_transition", "discontinuation", "approval_event", "clinical_trial"],
        {"clinical_trial": 4201})  # only the generic catch-all has rows
    assert v == "partial", "majority of predicates missing -> not covered"
    assert set(missing) == {"phase_transition", "discontinuation", "approval_event"}


def test_gap_when_near_empty_commercial():
    # commercial lens on prod: product_sales=3, supply_disruption=1 -> gap
    v, total, missing = classify_coverage(
        ["product_sales", "launch_event", "uptake_signal"], {"product_sales": 3})
    assert v == "gap"
    assert "launch_event" in missing and "uptake_signal" in missing


def test_dimension_predicates_parses_route_strings():
    pb = yaml.safe_load(_PB.read_text(encoding="utf-8"))
    dims = dimension_predicates(pb)
    assert "trial_endpoint_success" in dims
    assert "efficacy_endpoint" in dims["trial_endpoint_success"]
    # market access lens routes to predicates that are the known prod gaps
    assert "formulary_status" in dims["market_access_success"]


def test_every_dimension_has_predicates():
    pb = yaml.safe_load(_PB.read_text(encoding="utf-8"))
    dims = dimension_predicates(pb)
    assert len(dims) == 5
    for key, preds in dims.items():
        assert preds, f"{key} has no predicate routes"
