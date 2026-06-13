"""Pharma cross-source eval — LLM-judge harness (Lane 2, operational).

Runs the REAL /chat system against benchmark/eval_pharma_v1.yaml and scores each
answer with a strong LLM judge against the team's binary gates (G1-G4) and graded
marks (Q1-Q4). It is the quality bar the heuristic `benchmark/scorers.py` cannot
be — gates like "closed-world honesty" and "no count fallacy" are semantic, not
keyword-matchable.

Two halves, deliberately separated so the SCORING LOGIC is deterministically
testable without an LLM or a DB:
  * capture   — reuse benchmark.capture_responses (in-process or HTTP).
  * judge     — an injectable `judge_fn(item, response, connector_state) -> verdict`.
                The real one calls an LLM; tests pass a stub.
  * score     — `apply_fail_closed` / `score_item` are PURE: given a verdict they
                enforce the pass rule with no I/O. This is the Lane-1 unit-tested
                surface.

Fail-closed contract (conservation principle #3, no vacuous green — at the JUDGE
layer too):
  * A gate is PASS only if explicitly true in the verdict.
  * For items whose data is missing or ingested-but-unreachable, G2 (closed-world
    honesty) PASS additionally REQUIRES the judge to quote the coverage-limit
    sentence. A confident answer with no limitation quote fails G2 — exactly the
    "absent in my data reported as absent in reality" disease.
  * Any fired trap fails the item (the draft marks traps as automatic fails).
  * item_pass = all 4 gates pass AND no trap fired AND graded_sum >= 8/12.

This is operational: it needs a live system + an LLM judge (non-deterministic,
costs tokens). It runs on a schedule / on demand, NEVER as a PR-hard gate — a
flaky judge or a down model must not red a PR.

Usage:
    # baseline, in-process against the configured DB (needs DATABASE_URL + OPENAI_API_KEY)
    python -m benchmark.pharma_eval --in-process \
        --output benchmark/reports/pharma-eval-baseline.json

    # against a deployment
    python -m benchmark.pharma_eval --url https://<deployment>
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Callable, Optional

import yaml

logger = logging.getLogger(__name__)

# Prefer the normalized v2 pack (41 items + embedded specialist rubric — the
# single machine-readable pack the SME reviewer asked for in F6); fall back to
# v1 if v2 isn't present. Override explicitly with --eval / eval_path.
_V2 = Path(__file__).parent / "eval_pharma_v2.yaml"
DEFAULT_EVAL = _V2 if _V2.exists() else (Path(__file__).parent / "eval_pharma_v1.yaml")
DEFAULT_REPORT_DIR = Path(__file__).parent / "reports"

GATE_IDS = ["G1_provenance", "G2_closed_world_honesty", "G3_no_count_fallacy", "G4_domain_correctness"]
GRADED_IDS = ["Q1_join_completeness", "Q2_synthesis", "Q3_calibration", "Q4_contradiction_surfacing"]
GRADED_PASS_THRESHOLD = 8  # of 12
# Modes where an honest answer MUST state a coverage limit — G2 needs a quote.
_QUOTE_REQUIRED_MODES = {"missing_data", "ingested_unreachable"}

# A judge_fn takes (item, response, connector_state) and returns a raw verdict dict.
JudgeFn = Callable[[dict, dict, dict], dict]


# ── Eval loading ────────────────────────────────────────────────────

def load_eval(path: str = "") -> dict:
    p = path or str(DEFAULT_EVAL)
    with open(p, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ── Response compaction (what the judge sees) ───────────────────────

def compact_response(response: dict) -> dict:
    """Trim a /chat response to what the judge needs: the full narrative plus a
    provenance summary (so G1 can be judged) — never the raw evidence blobs."""
    data = response.get("data") or {}
    evidence = data.get("evidence") or []
    sources = sorted({
        (e.get("source") or e.get("source_name") or e.get("source_type") or "")
        for e in evidence if isinstance(e, dict)
    } - {""})
    provenance = data.get("provenance") or data.get("source_coverage") or {}
    return {
        "narrative": response.get("narrative", "") or "",
        "intent": response.get("intent"),
        "evidence_count": len(evidence),
        "evidence_sources": sources,
        "provenance": provenance,
        "metrics_present": sorted((data.get("metrics_context") or {}).keys())
        if isinstance(data.get("metrics_context"), dict) else [],
    }


# ── Scoring (PURE — the Lane-1 tested surface) ──────────────────────

def apply_fail_closed(item: dict, verdict: dict) -> dict:
    """Enforce the pass rule on a raw judge verdict. No I/O. Deterministic.

    Returns a scored dict: per-gate booleans (after fail-closed), graded sum,
    traps_fired, item_pass, and the reasons carried through for the scorecard.
    """
    mode = (item.get("data_reality") or {}).get("mode", "")
    raw_gates = verdict.get("gates") or {}
    raw_graded = verdict.get("graded") or {}

    gates: dict[str, dict] = {}
    for gid in GATE_IDS:
        g = raw_gates.get(gid) or {}
        passed = g.get("pass") is True
        quote = (g.get("evidence_quote") or "").strip()
        # Fail-closed: G2 on a missing/unreachable item must SHOW the limitation.
        if gid == "G2_closed_world_honesty" and mode in _QUOTE_REQUIRED_MODES and not quote:
            passed = False
        gates[gid] = {"pass": passed, "evidence_quote": quote, "reason": g.get("reason", "")}

    graded: dict[str, int] = {}
    for qid in GRADED_IDS:
        q = raw_graded.get(qid) or {}
        try:
            s = int(q.get("score"))
        except (TypeError, ValueError):
            s = 0
        graded[qid] = max(0, min(3, s))
    graded_sum = sum(graded.values())

    traps_fired = [t for t in (verdict.get("traps_fired") or []) if str(t).strip()]

    all_gates_pass = all(gates[g]["pass"] for g in GATE_IDS)
    item_pass = all_gates_pass and not traps_fired and graded_sum >= GRADED_PASS_THRESHOLD

    return {
        "id": item["id"],
        "persona": item.get("persona"),
        "mode": mode,
        "capability_tags": item.get("capability_tags", []),
        "gates": gates,
        "all_gates_pass": all_gates_pass,
        "graded": graded,
        "graded_sum": graded_sum,
        "traps_fired": traps_fired,
        "item_pass": item_pass,
        "judge_summary": verdict.get("summary", ""),
    }


def score_item(item: dict, response: dict, connector_state: dict, judge_fn: JudgeFn) -> dict:
    """Capture-agnostic: judge a single (item, response) and apply the pass rule."""
    # A transport error or empty narrative can never pass — don't waste a judge call.
    if not isinstance(response, dict) or response.get("error") or not (response.get("narrative") or "").strip():
        empty_verdict = {
            "gates": {g: {"pass": False, "reason": "no usable response"} for g in GATE_IDS},
            "graded": {q: {"score": 0} for q in GRADED_IDS},
            "traps_fired": [],
            "summary": f"no usable response: {response.get('error') if isinstance(response, dict) else 'non-dict'}",
        }
        scored = apply_fail_closed(item, empty_verdict)
        scored["no_response"] = True
        return scored
    verdict = judge_fn(item, response, connector_state)
    return apply_fail_closed(item, verdict)


# ── Aggregation ─────────────────────────────────────────────────────

def aggregate(scored: list[dict]) -> dict:
    n = len(scored)
    passed = sum(1 for s in scored if s["item_pass"])

    def _rate(pred) -> float:
        sub = [s for s in scored if pred(s)]
        return round(sum(1 for s in sub if s["item_pass"]) / len(sub), 3) if sub else 0.0

    by_gate = {
        g: round(sum(1 for s in scored if s["gates"][g]["pass"]) / n, 3) if n else 0.0
        for g in GATE_IDS
    }
    modes = sorted({s["mode"] for s in scored})
    personas = sorted({s["persona"] for s in scored if s["persona"]})
    return {
        "total_items": n,
        "items_passed": passed,
        "pass_rate": round(passed / n, 3) if n else 0.0,
        "graded_mean": round(sum(s["graded_sum"] for s in scored) / n, 2) if n else 0.0,
        "gate_pass_rate": by_gate,
        "pass_rate_by_mode": {m: _rate(lambda s, m=m: s["mode"] == m) for m in modes},
        "pass_rate_by_persona": {p: _rate(lambda s, p=p: s["persona"] == p) for p in personas},
        "items_with_trap_fired": sorted(s["id"] for s in scored if s["traps_fired"]),
    }


# ── The real LLM judge ──────────────────────────────────────────────

_JUDGE_SYSTEM = """You are a STRICT, adversarial evaluation judge for a pharma intelligence platform. \
You grade one answer against a fixed rubric. You are not helpful, not generous — you find the flaw. \
A pharma domain expert (Medical Affairs / Clinical Development / Regulatory) is reading over your shoulder.

You return ONLY a JSON object, no prose. Schema:
{
  "gates": {
    "G1_provenance":            {"pass": bool, "evidence_quote": "<exact sentence from the answer that attributes a claim to a named source, or empty>", "reason": "<=200 chars"},
    "G2_closed_world_honesty":  {"pass": bool, "evidence_quote": "<exact sentence stating a coverage/ingest limit, or empty>", "reason": "..."},
    "G3_no_count_fallacy":      {"pass": bool, "evidence_quote": "<violating sentence if it fails, else empty>", "reason": "..."},
    "G4_domain_correctness":    {"pass": bool, "evidence_quote": "<false statement if it fails, else empty>", "reason": "..."}
  },
  "graded": {
    "Q1_join_completeness":     {"score": 0-3, "reason": "..."},
    "Q2_synthesis":             {"score": 0-3, "reason": "..."},
    "Q3_calibration":           {"score": 0-3, "reason": "..."},
    "Q4_contradiction_surfacing":{"score": 0-3, "reason": "..."}
  },
  "traps_fired": ["<verbatim trap text for each trap the answer falls into>"],
  "summary": "<=300 chars: the single most important judgement"
}

Hard rules:
- Judge ONLY against the provided ingest state. The answer is correct to say data is missing when the connector_state shows it empty or unreachable; it is WRONG to report missing-in-our-data as absent-in-reality.
- G2 is the keystone. If the question needs a source that is empty (0 rows) or ingested-but-unreachable, the answer MUST explicitly state that limit. If it instead gives a confident figure or a verdict, G2 FAILS and the matching trap fires.
- G3: any ranking/verdict/strength claim justified by record counts, trial counts or pipeline scores alone FAILS G3.
- G4: any clinically/regulatorily false statement (wrong mechanism, wrong approval status, misread statistics) FAILS G4.
- Quote EXACTLY from the answer. If you cannot find a sentence to quote for a positive gate (G1, or G2 when a limit is required), that gate cannot pass.
- Be conservative: when uncertain, fail the gate."""


def _build_judge_user(item: dict, compacted: dict, connector_state: dict) -> str:
    dr = item.get("data_reality") or {}
    # Only the connectors this item needs, with their real state — keeps the judge focused.
    needed = {
        s: connector_state.get(s, {"note": "not in connector_state"})
        for s in item.get("sources_required", [])
    }
    payload = {
        "question": item.get("question"),
        "persona": item.get("persona"),
        "sources_required": item.get("sources_required", []),
        "connector_state_for_required_sources": needed,
        "data_reality": dr,
        "gold_must_include": item.get("gold_must_include", []),
        "traps": item.get("traps", []),
        "pass_criteria": item.get("pass_criteria", ""),
        "answer_under_test": compacted,
    }
    return (
        "Grade this answer. Use the connector_state as ground truth for what the "
        "platform can and cannot know.\n\n"
        + json.dumps(payload, indent=2, default=str)
    )


def parse_verdict(raw_text: str) -> dict:
    """Best-effort JSON extraction from a model reply."""
    raw_text = (raw_text or "").strip()
    if raw_text.startswith("```"):
        raw_text = raw_text.split("```", 2)[1]
        if raw_text.startswith("json"):
            raw_text = raw_text[4:]
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        start, end = raw_text.find("{"), raw_text.rfind("}")
        if 0 <= start < end:
            return json.loads(raw_text[start:end + 1])
        raise


def _judge_error_verdict(e) -> dict:
    """Fail-closed verdict for a judge call that couldn't run."""
    return {
        "gates": {g: {"pass": False, "reason": f"judge error: {e}"} for g in GATE_IDS},
        "graded": {q: {"score": 0} for q in GRADED_IDS},
        "traps_fired": [],
        "summary": f"judge error: {e}",
    }


def aggregate_verdicts(verdicts: list[dict]) -> dict:
    """Majority-vote a set of judge samples into one stable verdict. PURE.

    A single LLM judge call is itself a vacuous-green risk (conservation #3): the
    same provenance legend was seen to pass G1 on one item and fail on another.
    Voting over N samples denoises that. Rules:
      * gate passes iff a STRICT majority of samples pass it (ties → fail-closed);
        evidence_quote taken from the first passing sample.
      * graded score = rounded mean across samples.
      * a trap fires iff a strict majority of samples fire it (denoises false fires).
    """
    n = len(verdicts)
    if n == 0:
        return _judge_error_verdict("no samples")
    if n == 1:
        return verdicts[0]
    need = n // 2 + 1  # strict majority

    gates: dict[str, dict] = {}
    for gid in GATE_IDS:
        samples = [(v.get("gates") or {}).get(gid) or {} for v in verdicts]
        passes = [s for s in samples if s.get("pass") is True]
        passed = len(passes) >= need
        quote = next((s.get("evidence_quote") for s in passes if (s.get("evidence_quote") or "").strip()), "")
        gates[gid] = {
            "pass": passed,
            "evidence_quote": quote or "",
            "reason": f"{len(passes)}/{n} judges passed",
        }

    graded: dict[str, dict] = {}
    for qid in GRADED_IDS:
        scores = []
        for v in verdicts:
            q = (v.get("graded") or {}).get(qid) or {}
            try:
                scores.append(int(q.get("score")))
            except (TypeError, ValueError):
                scores.append(0)
        graded[qid] = {"score": round(sum(scores) / n) if scores else 0}

    # Count each trap by exact text; fires only on strict majority.
    trap_counts: dict[str, int] = {}
    for v in verdicts:
        for t in (v.get("traps_fired") or []):
            t = str(t).strip()
            if t:
                trap_counts[t] = trap_counts.get(t, 0) + 1
    traps_fired = [t for t, c in trap_counts.items() if c >= need]

    return {
        "gates": gates,
        "graded": graded,
        "traps_fired": traps_fired,
        "summary": f"majority of {n} judges; "
                   + "; ".join(f"{g.split('_')[0]} {gates[g]['reason']}" for g in GATE_IDS),
    }


def llm_judge(model: str = "", api_key: str = "", samples: int = 0) -> JudgeFn:
    """Return a judge_fn backed by an OpenAI chat model, majority-voted over
    `samples` calls (default $MZ_EVAL_JUDGE_SAMPLES or 3) to denoise a single
    LLM verdict. Default model is stronger than the synthesis model — a weak or
    single-shot judge is a vacuous gate."""
    from openai import OpenAI

    chosen = model or os.getenv("MZ_EVAL_JUDGE_MODEL", "gpt-4o")
    n = samples or int(os.getenv("MZ_EVAL_JUDGE_SAMPLES", "3"))
    key = api_key or os.getenv("OPENAI_API_KEY", "")
    client = OpenAI(api_key=key)
    # A touch of temperature so the N samples actually vary (majority vote over
    # identical temp-0 replies would be pointless); 0 when single-shot.
    temperature = 0.0 if n <= 1 else 0.4

    def _judge_once(user: str) -> dict:
        resp = client.chat.completions.create(
            model=chosen,
            messages=[
                {"role": "system", "content": _JUDGE_SYSTEM},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
            response_format={"type": "json_object"},
        )
        return parse_verdict(resp.choices[0].message.content)

    def judge(item: dict, response: dict, connector_state: dict) -> dict:
        compacted = compact_response(response)
        user = _build_judge_user(item, compacted, connector_state)
        verdicts: list[dict] = []
        for _ in range(max(1, n)):
            try:
                verdicts.append(_judge_once(user))
            except Exception as e:  # noqa: BLE001
                logger.exception("judge call failed for %s", item.get("id"))
                verdicts.append(_judge_error_verdict(e))
        return aggregate_verdicts(verdicts)

    return judge


# ── Orchestration ───────────────────────────────────────────────────

def run_pharma_eval(
    *,
    eval_path: str = "",
    poster=None,
    judge_fn: Optional[JudgeFn] = None,
    output: str = "",
) -> dict:
    """Capture real answers for every item, judge each, aggregate. Returns the
    full report dict (also written to `output` if given)."""
    from benchmark.capture_responses import run_capture

    spec = load_eval(eval_path)
    items = spec["items"]
    connector_state = spec.get("connector_state_actual", {})

    if poster is None:
        raise ValueError("poster is required (use in_process_poster() or http_poster(url))")
    if judge_fn is None:
        judge_fn = llm_judge()

    # Reuse the capture loop (it keys on id/question and records transport errors).
    queries = [{"id": it["id"], "question": it["question"]} for it in items]
    _, captured = run_capture(queries, poster, output_path=str(DEFAULT_REPORT_DIR / "pharma-captured.json"))
    by_id = {c["query_id"]: c.get("response") or {} for c in captured}

    scored: list[dict] = []
    for it in items:
        resp = by_id.get(it["id"], {"error": "not captured"})
        s = score_item(it, resp, connector_state, judge_fn)
        scored.append(s)
        logger.info("[%s] %s pass=%s gates=%d/4 graded=%d/12",
                    it["id"], it.get("persona"), s["item_pass"],
                    sum(1 for g in GATE_IDS if s["gates"][g]["pass"]), s["graded_sum"])

    report = {
        "eval_version": spec.get("meta", {}).get("version"),
        "summary": aggregate(scored),
        "items": scored,
    }
    if output:
        Path(output).write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        logger.info("wrote report -> %s", output)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Pharma cross-source eval (LLM judge)")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--url", default="", help="Deployment base URL (HTTP capture)")
    src.add_argument("--in-process", action="store_true", help="Capture in-process via TestClient")
    parser.add_argument("--eval", default="", help="Path to eval YAML")
    parser.add_argument("--judge-model", default="", help="Override judge model (default gpt-4o / $MZ_EVAL_JUDGE_MODEL)")
    parser.add_argument("--output", default="", help="Where to write the scored report")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    from benchmark.capture_responses import http_poster, in_process_poster
    poster = in_process_poster() if args.in_process else http_poster(args.url)

    try:
        report = run_pharma_eval(
            eval_path=args.eval,
            poster=poster,
            judge_fn=llm_judge(model=args.judge_model),
            output=args.output,
        )
    except Exception as e:  # noqa: BLE001
        print(f"\nPHARMA-EVAL ERROR: {e}", file=sys.stderr)
        return 1

    s = report["summary"]
    print(f"\n  PHARMA-EVAL: {s['items_passed']}/{s['total_items']} items pass "
          f"({s['pass_rate']:.0%}), graded mean {s['graded_mean']}/12")
    print(f"  gate pass-rates: " + ", ".join(f"{g.split('_')[0]} {r:.0%}" for g, r in s["gate_pass_rate"].items()))
    print(f"  by data-reality: " + ", ".join(f"{m} {r:.0%}" for m, r in s["pass_rate_by_mode"].items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
