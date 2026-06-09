"""Data-driven red-team eval — runs every golden case in
domain/pharma/packs/eval_semantic_resolution.yaml through the pack-driven engine.

This is the executable form of the challenge's "produce regression tests from
every corrected edge case" + the expert's eval_pack. Domain Forge appends cases
to the YAML; this test runs them all. Proves the engine is pack-configurable.

Run: pytest tests/test_semantic_resolution_eval.py -v
"""

from __future__ import annotations

import pathlib

import pytest
import yaml

from domain.pharma.drug_mention_parser import Quantity, parse_drug_mention
from domain.pharma.packs.loader import PACK_DIR, load_pack
from services.semantic_resolution import CandidateEntity, resolve_mention

_EVAL = yaml.safe_load((PACK_DIR / "eval_semantic_resolution.yaml").read_text(encoding="utf-8"))
_CASES = _EVAL["cases"]
_BUNDLE = load_pack()


def _candidate(spec: dict) -> CandidateEntity:
    spec = dict(spec)
    for qty_field in ("strength", "concentration", "volume"):
        if isinstance(spec.get(qty_field), dict):
            q = spec[qty_field]
            spec[qty_field] = Quantity(raw=q.get("raw", ""), kind=qty_field,
                                       value=q.get("value"), unit=q.get("unit", ""))
    return CandidateEntity(**spec)


def _ingredient_set(mention):
    return {c.lower() for c in mention.components}


def _config_signature(mention):
    def sig(q):
        return (q.kind, q.unit, q.value) if q else None
    return (mention.formulation, mention.route, sig(mention.strength),
            sig(mention.concentration), sig(mention.volume))


@pytest.mark.parametrize("case", _CASES, ids=[c["eval_id"] for c in _CASES])
def test_eval_case(case):
    kind = case.get("kind", "resolve")

    if kind == "pair":
        ms = [parse_drug_mention(t, _BUNDLE.lexicon) for t in case["raw_mentions"]]
        if case.get("expect_same_ingredient"):
            assert _ingredient_set(ms[0]) == _ingredient_set(ms[1]), \
                f"{case['eval_id']}: ingredients should match"
        if case.get("expect_same_configuration") is False:
            assert _config_signature(ms[0]) != _config_signature(ms[1]), \
                f"{case['eval_id']}: configurations must differ ({case.get('gold_reason')})"
        return

    # kind == resolve
    m = parse_drug_mention(case["raw_input"], _BUNDLE.lexicon)
    candidates = [_candidate(c) for c in case.get("candidates", [])]
    d = resolve_mention(m, candidates, _BUNDLE.policy)

    for flag in case.get("expected_flags", []):
        assert flag in d.ambiguity_flags, \
            f"{case['eval_id']}: expected flag {flag}; got {d.ambiguity_flags}"
    for flag in case.get("forbidden_flags", []):
        assert flag not in d.ambiguity_flags, \
            f"{case['eval_id']}: flag {flag} must NOT fire ({case.get('gold_reason')})"
    if "expected_entity_id" in case:
        assert d.selected_entity_id == case["expected_entity_id"]
    if "expected_level" in case:
        assert d.match_level.value == case["expected_level"], \
            f"{case['eval_id']}: level {d.match_level.value} != {case['expected_level']}"
    if "should_auto_resolve" in case:
        assert d.auto_resolved is case["should_auto_resolve"], \
            f"{case['eval_id']}: auto_resolved={d.auto_resolved}, expected {case['should_auto_resolve']}"
    if "expected_action" in case:
        assert d.routing == case["expected_action"], \
            f"{case['eval_id']}: routing={d.routing}, expected {case['expected_action']}"
