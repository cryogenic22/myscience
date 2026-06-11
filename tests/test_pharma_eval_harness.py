"""Lane-1: the pharma-eval SCORING logic is deterministic and fail-closed.

The judge itself is an LLM (Lane-2, non-deterministic), but the pass rule that
sits on top of its verdict must be testable without an LLM or a DB. These tests
pin the fail-closed contract so a future edit can't quietly make the gate
generous — a vacuous green at the eval layer is the same disease the eval exists
to catch.
"""

import pytest

from benchmark.pharma_eval import (
    GATE_IDS,
    GRADED_IDS,
    apply_fail_closed,
    score_item,
    aggregate,
    load_eval,
    compact_response,
)


def _verdict(*, gate_pass=True, g2_quote="cov limit", graded=3, traps=None):
    return {
        "gates": {
            g: {
                "pass": gate_pass,
                "evidence_quote": g2_quote if g == "G2_closed_world_honesty" else "src [1]",
                "reason": "",
            }
            for g in GATE_IDS
        },
        "graded": {q: {"score": graded} for q in GRADED_IDS},
        "traps_fired": traps or [],
        "summary": "x",
    }


def _item(mode="reachable_reasoning"):
    return {"id": "T1", "persona": "Clinical Development", "data_reality": {"mode": mode},
            "capability_tags": ["x"]}


def test_all_pass_with_full_marks_passes():
    s = apply_fail_closed(_item(), _verdict(gate_pass=True, graded=3))
    assert s["item_pass"] is True
    assert s["graded_sum"] == 12
    assert s["all_gates_pass"] is True


def test_graded_below_threshold_fails_even_with_all_gates():
    # 4 dims * 1 = 4 < 8
    s = apply_fail_closed(_item(), _verdict(gate_pass=True, graded=1))
    assert s["all_gates_pass"] is True
    assert s["graded_sum"] == 4
    assert s["item_pass"] is False


def test_any_gate_fail_fails_item_regardless_of_graded():
    v = _verdict(gate_pass=True, graded=3)
    v["gates"]["G4_domain_correctness"]["pass"] = False
    s = apply_fail_closed(_item(), v)
    assert s["item_pass"] is False
    assert s["all_gates_pass"] is False


def test_fired_trap_is_automatic_fail():
    s = apply_fail_closed(_item(), _verdict(gate_pass=True, graded=3, traps=["called both GLP-1"]))
    assert s["traps_fired"] == ["called both GLP-1"]
    assert s["item_pass"] is False


def test_g2_requires_quote_for_missing_data_mode():
    """The keystone: on a missing-data item, G2 'pass' with no coverage-limit
    quote is forced to FAIL (fail-closed). A confident answer that doesn't state
    the limit cannot pass."""
    v = _verdict(gate_pass=True, g2_quote="", graded=3)  # judge claims pass, no quote
    s = apply_fail_closed(_item(mode="missing_data"), v)
    assert s["gates"]["G2_closed_world_honesty"]["pass"] is False
    assert s["item_pass"] is False


def test_g2_quote_not_required_for_reachable_mode():
    """On a reachable item there may be no coverage limit to quote — G2 can pass
    without one (the requirement only bites where data is missing/unreachable)."""
    v = _verdict(gate_pass=True, g2_quote="", graded=3)
    s = apply_fail_closed(_item(mode="reachable_reasoning"), v)
    assert s["gates"]["G2_closed_world_honesty"]["pass"] is True
    assert s["item_pass"] is True


def test_g2_with_quote_passes_for_missing_data_mode():
    v = _verdict(gate_pass=True, g2_quote="NADAC connector holds 0 records", graded=3)
    s = apply_fail_closed(_item(mode="missing_data"), v)
    assert s["gates"]["G2_closed_world_honesty"]["pass"] is True
    assert s["item_pass"] is True


def test_graded_score_clamped_and_coerced():
    v = _verdict(graded=3)
    v["graded"]["Q1_join_completeness"]["score"] = 9     # out of range
    v["graded"]["Q2_synthesis"]["score"] = "bad"          # non-numeric -> 0
    v["graded"]["Q3_calibration"]["score"] = -2           # below 0
    s = apply_fail_closed(_item(), v)
    assert s["graded"]["Q1_join_completeness"] == 3
    assert s["graded"]["Q2_synthesis"] == 0
    assert s["graded"]["Q3_calibration"] == 0


def test_score_item_short_circuits_on_error_response_without_judge():
    """A transport error / empty narrative never reaches the judge and never passes."""
    calls = []

    def boom(item, response, cs):
        calls.append(item["id"])
        raise AssertionError("judge must not be called for an error response")

    s = score_item(_item(), {"error": "HTTP 500"}, {}, boom)
    assert s["item_pass"] is False
    assert s.get("no_response") is True
    assert calls == []


def test_score_item_calls_judge_for_real_response():
    captured = {}

    def stub(item, response, cs):
        captured["called"] = True
        return _verdict(gate_pass=True, graded=3)

    s = score_item(_item(), {"narrative": "a real answer"}, {}, stub)
    assert captured.get("called") is True
    assert s["item_pass"] is True


def test_aggregate_rates_and_breakdowns():
    scored = [
        apply_fail_closed(_item("reachable_reasoning"), _verdict(graded=3)),               # pass
        apply_fail_closed(_item("missing_data"), _verdict(g2_quote="", graded=3)),          # fail (G2)
    ]
    scored[0]["id"], scored[1]["id"] = "A", "B"
    agg = aggregate(scored)
    assert agg["total_items"] == 2
    assert agg["items_passed"] == 1
    assert agg["pass_rate"] == 0.5
    assert agg["pass_rate_by_mode"]["reachable_reasoning"] == 1.0
    assert agg["pass_rate_by_mode"]["missing_data"] == 0.0
    assert set(agg["gate_pass_rate"]) == set(GATE_IDS)


def test_compact_response_extracts_sources_and_narrative():
    resp = {
        "narrative": "Semaglutide [1] has 184 trials.",
        "intent": "compare",
        "data": {
            "evidence": [{"source": "clinicaltrials_gov"}, {"source": "openfda_faers"}, {"source": "clinicaltrials_gov"}],
            "metrics_context": {"pipeline_score": 341.0},
        },
    }
    c = compact_response(resp)
    assert c["narrative"].startswith("Semaglutide")
    assert c["evidence_count"] == 3
    assert c["evidence_sources"] == ["clinicaltrials_gov", "openfda_faers"]
    assert "pipeline_score" in c["metrics_present"]


def test_eval_yaml_loads_and_is_well_formed():
    """The committed eval file parses and every item carries the fields the judge
    and scorer require — a malformed eval is a vacuous run."""
    spec = load_eval()
    items = spec["items"]
    assert len(items) == 19
    assert set(spec["connector_state_actual"]) , "connector_state_actual present"
    for it in items:
        assert it.get("question"), f"{it['id']} has a question"
        assert it.get("gold_must_include"), f"{it['id']} has gold_must_include"
        assert it.get("pass_criteria"), f"{it['id']} has pass_criteria"
        assert it["data_reality"]["mode"] in {"reachable_reasoning", "missing_data", "ingested_unreachable"}


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
