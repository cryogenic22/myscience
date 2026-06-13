"""MZ-XR-20260613-005 — the two eval runners declare distinct, explicit tiers.

The heuristic `benchmark/eval_runner.py` is smoke/regression coverage (route
mechanics); the LLM-judge `benchmark/pharma_eval.py` is the SME content-quality
gate (provenance / closed-world honesty / count-fallacy / domain correctness). A
system can pass the smoke runner while still producing thin, overconfident, or
commercially misleading answers — so the distinction must be machine-checkable,
not just prose, to stop the two being conflated in coordination/release criteria.
"""
from __future__ import annotations

VALID_TIERS = {"smoke", "content_gate"}


def test_eval_runner_is_smoke_tier():
    from benchmark.eval_runner import EVAL_TIER
    assert EVAL_TIER == "smoke"


def test_pharma_eval_is_content_gate_tier():
    from benchmark.pharma_eval import EVAL_TIER
    assert EVAL_TIER == "content_gate"


def test_the_two_runners_declare_distinct_tiers():
    from benchmark.eval_runner import EVAL_TIER as smoke
    from benchmark.pharma_eval import EVAL_TIER as gate
    assert smoke in VALID_TIERS and gate in VALID_TIERS
    assert smoke != gate, "the smoke runner and the content gate must be distinct"
