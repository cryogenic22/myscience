"""Tests for the live-eval orchestrator (benchmark/live_eval.py).

These exercise the capture-health + scoring wiring with a FAKE poster, so they
need no network and no DB — the real system is mocked. The point under test is
the fail-loud contract (a broken capture must NOT score as healthy) and that a
healthy capture flows into the scorer + regression check.
"""
from __future__ import annotations

import json

import pytest

from benchmark import live_eval
from benchmark.eval_runner import DEFAULT_GOLDEN


def _golden():
    with open(DEFAULT_GOLDEN, "r", encoding="utf-8") as f:
        return json.load(f)


def _good_response(q: dict) -> dict:
    """A well-formed response that will score reasonably for query *q*."""
    expected = q.get("expected", {})
    must = expected.get("must_mention", [])
    entities = expected.get("entities", [])
    n_ev = max(expected.get("min_evidence", 0) or 0, expected.get("min_citations", 0) or 0, 1)
    ev_content = " ".join(must) if must else "supporting evidence"
    cites = " ".join(f"[{i+1}]" for i in range(min(expected.get("min_citations", 0) or 0, n_ev)))
    narrative = " ".join([f"**{e}**" for e in entities] + list(must) + [cites]) or "answer"
    return {
        "intent": q.get("intent", "general"),
        "narrative": narrative,
        "data": {
            "evidence": [
                {"id": f"e{i}", "title": f"src {i}", "content": ev_content, "source_type": "x"}
                for i in range(n_ev)
            ],
            "entity_focus": [{"label": e, "entity_type": "entity", "id": e} for e in entities],
            "graph_context": {"nodes": [], "edges": [], "node_count": 0, "edge_count": 0},
            "metrics_context": {},
            "provenance_summary": {},
        },
    }


def _fake_poster(behaviour):
    """behaviour: callable(q) -> (status, body). Robust to skipped queries — the
    query is resolved from the qid embedded in session_id (capture-{qid})."""
    by_id = {q["id"]: q for q in _golden()}

    def post(question, session_id):
        qid = session_id.replace("capture-", "", 1)
        q = by_id[qid]
        status, body = behaviour(q)
        return status, body, 12.3

    return post


def test_healthy_capture_scores_and_reports(monkeypatch, tmp_path):
    """A fully-healthy capture flows into the scorer and returns a real overall."""
    monkeypatch.setattr(live_eval, "in_process_poster", lambda: _fake_poster(lambda q: (200, _good_response(q))))
    result = live_eval.run_live_eval(
        in_process=True,
        threshold=0.0,
        captured_output=str(tmp_path / "cap.json"),
    )
    assert result["capture_healthy"] == result["capture_total"]
    assert 0.0 <= result["overall"] <= 1.0
    assert result["passed"] is True


def test_dead_deployment_fails_loud(monkeypatch, tmp_path):
    """Every query erroring (dead system) must RAISE, not score as healthy."""
    monkeypatch.setattr(
        live_eval, "in_process_poster",
        lambda: _fake_poster(lambda q: (502, {"error": "HTTP 502"})),
    )
    with pytest.raises(RuntimeError, match="capture unhealthy"):
        live_eval.run_live_eval(in_process=True, captured_output=str(tmp_path / "cap.json"))


def test_mostly_dead_capture_fails_loud(monkeypatch, tmp_path):
    """Below the healthy-share floor still fails loud (no near-empty green)."""
    ids = [q["id"] for q in _golden()]
    n = len(ids)
    # Make only the first ~20% (by gold order) return real responses.
    def behaviour(q):
        if ids.index(q["id"]) < n * 0.2:
            return 200, _good_response(q)
        return 200, {"error": "boom"}
    monkeypatch.setattr(live_eval, "in_process_poster", lambda: _fake_poster(behaviour))
    with pytest.raises(RuntimeError, match="capture unhealthy"):
        live_eval.run_live_eval(in_process=True, captured_output=str(tmp_path / "cap.json"))


def test_threshold_failure_is_reported(monkeypatch, tmp_path):
    """Healthy capture but low quality -> passed False with a threshold reason."""
    # Empty narratives score low but still count as 'real' (narrative present).
    monkeypatch.setattr(
        live_eval, "in_process_poster",
        lambda: _fake_poster(lambda q: (200, {"intent": "wrong", "narrative": "", "data": {}})),
    )
    result = live_eval.run_live_eval(
        in_process=True,
        threshold=99.0,  # impossibly high -> must fail threshold
        captured_output=str(tmp_path / "cap.json"),
    )
    assert result["passed"] is False
    assert any("below threshold" in r for r in result["fail_reasons"])


def test_requires_a_source():
    with pytest.raises(ValueError, match="--url|--in-process"):
        live_eval.run_live_eval(threshold=0.0)


def test_committed_baseline_is_loader_compatible():
    """The committed baseline MUST carry the keys run_ci_eval's baseline loader
    reads (overall_score + by_dimension). A baseline keyed 'overall' instead would
    make the loader silently read 0.0 — a vacuous regression check that can never
    fire. This guards against that regression (it is how the first baseline broke)."""
    from pathlib import Path

    baseline = Path(__file__).resolve().parents[1] / "benchmark" / "reports" / "live-eval-baseline.json"
    if not baseline.is_file():
        pytest.skip("no committed baseline yet")
    doc = json.loads(baseline.read_text(encoding="utf-8"))
    assert "overall_score" in doc, "baseline missing 'overall_score' — loader would read 0.0 (vacuous)"
    assert isinstance(doc["overall_score"], (int, float)) and doc["overall_score"] > 0
    assert doc.get("by_dimension"), "baseline missing by_dimension"
