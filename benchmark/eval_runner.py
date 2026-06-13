"""Evaluation benchmark runner — scores intelligence pipeline quality.

Two modes:
- Live: POST queries to running API, score responses
- Offline: Score pre-captured responses from JSON

Usage:
    python -m benchmark.eval_runner --live --url https://myscience-production.up.railway.app
    python -m benchmark.eval_runner --offline --responses benchmark/captured_responses.json
    python -m benchmark.eval_runner --golden benchmark/golden_queries.json --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from benchmark.scorers import (
    score_intent,
    score_entity_grounding,
    score_factual_accuracy,
    score_evidence_completeness,
    score_citation_validity,
    composite_score,
)

logger = logging.getLogger(__name__)

DEFAULT_GOLDEN = Path(__file__).parent / "golden_queries.json"
DEFAULT_REPORT_DIR = Path(__file__).parent / "reports"

# Eval tier (MZ-XR-20260613-005). This heuristic runner is SMOKE / REGRESSION
# coverage: `benchmark/scorers.py` scores route mechanics (intent match, grounding,
# numeric coincidence, evidence count, citation well-formedness) and CANNOT judge
# SME synthesis quality — provenance, closed-world honesty, count-fallacy, domain
# correctness. The SME CONTENT-QUALITY gate is `benchmark/pharma_eval.py`
# (EVAL_TIER="content_gate"). A green run here is NOT evidence of content quality.
EVAL_TIER = "smoke"


@dataclass
class EvalResult:
    query_id: str
    question: str
    intent_expected: str
    intent_actual: str | None
    scores: dict[str, float]
    overall: float
    latency_ms: float
    error: str | None = None


@dataclass
class EvalReport:
    run_id: str
    timestamp: str
    total_queries: int
    overall_score: float
    by_intent: dict[str, float]
    by_dimension: dict[str, float]
    results: list[EvalResult]
    failures: list[dict]
    latency_p50: float = 0.0
    latency_p95: float = 0.0


class EvalRunner:
    """Orchestrates evaluation: load queries → send/score → report."""

    def __init__(self, base_url: str = "", golden_path: str = ""):
        self.base_url = base_url.rstrip("/")
        self.golden_path = golden_path or str(DEFAULT_GOLDEN)
        self._queries = self._load_golden()

    def _load_golden(self) -> list[dict]:
        with open(self.golden_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def run_live(self, query_ids: list[str] | None = None) -> EvalReport:
        """Run queries against live API and score responses."""
        import requests

        queries = self._filter_queries(query_ids)
        results: list[EvalResult] = []

        for q in queries:
            question = q["question"]
            if not question:
                results.append(EvalResult(
                    query_id=q["id"], question=question,
                    intent_expected=q.get("intent", ""),
                    intent_actual=None, scores={}, overall=0.0,
                    latency_ms=0, error="empty question",
                ))
                continue

            t0 = time.monotonic()
            try:
                resp = requests.post(
                    f"{self.base_url}/chat",
                    json={"question": question, "session_id": f"eval-{q['id']}"},
                    timeout=60,
                )
                latency = (time.monotonic() - t0) * 1000
                if resp.status_code != 200:
                    results.append(EvalResult(
                        query_id=q["id"], question=question,
                        intent_expected=q.get("intent", ""),
                        intent_actual=None, scores={}, overall=0.0,
                        latency_ms=latency, error=f"HTTP {resp.status_code}",
                    ))
                    continue

                response = resp.json()
                result = self._score(q, response, latency)
                results.append(result)
                logger.info("[%s] %.2f — %s (%.0fms)", q["id"], result.overall, question[:50], latency)

            except Exception as e:
                latency = (time.monotonic() - t0) * 1000
                results.append(EvalResult(
                    query_id=q["id"], question=question,
                    intent_expected=q.get("intent", ""),
                    intent_actual=None, scores={}, overall=0.0,
                    latency_ms=latency, error=str(e),
                ))

        return self._build_report(results)

    def run_offline(self, responses: list[dict]) -> EvalReport:
        """Score pre-captured responses (no API call)."""
        resp_by_id = {r["query_id"]: r["response"] for r in responses}
        results: list[EvalResult] = []

        for q in self._queries:
            response = resp_by_id.get(q["id"])
            if not response:
                continue
            result = self._score(q, response, latency_ms=0)
            results.append(result)

        return self._build_report(results)

    def _filter_queries(self, query_ids: list[str] | None) -> list[dict]:
        if not query_ids:
            return self._queries
        id_set = set(query_ids)
        return [q for q in self._queries if q["id"] in id_set]

    def _score(self, query: dict, response: dict, latency_ms: float) -> EvalResult:
        expected = query.get("expected", {})
        scores = {
            "intent": score_intent(response, query),
            "grounding": score_entity_grounding(response, expected),
            "factual": score_factual_accuracy(response),
            "completeness": score_evidence_completeness(response, expected),
            "citation": score_citation_validity(response, expected),
        }
        overall = composite_score(scores)

        return EvalResult(
            query_id=query["id"],
            question=query["question"],
            intent_expected=query.get("intent", ""),
            intent_actual=response.get("intent"),
            scores=scores,
            overall=overall,
            latency_ms=latency_ms,
        )

    def _build_report(self, results: list[EvalResult]) -> EvalReport:
        if not results:
            return EvalReport(
                run_id=f"eval-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}",
                timestamp=datetime.now(timezone.utc).isoformat(),
                total_queries=0, overall_score=0.0,
                by_intent={}, by_dimension={}, results=[], failures=[],
            )

        # Overall
        overall = sum(r.overall for r in results) / len(results)

        # By intent
        intent_scores: dict[str, list[float]] = {}
        for r in results:
            intent_scores.setdefault(r.intent_expected, []).append(r.overall)
        by_intent = {k: round(sum(v) / len(v), 3) for k, v in intent_scores.items()}

        # By dimension
        dim_totals: dict[str, list[float]] = {}
        for r in results:
            for dim, val in r.scores.items():
                dim_totals.setdefault(dim, []).append(val)
        by_dimension = {k: round(sum(v) / len(v), 3) for k, v in dim_totals.items()}

        # Failures (score < 0.5)
        failures = [
            {"id": r.query_id, "question": r.question, "score": r.overall,
             "error": r.error, "scores": r.scores}
            for r in results if r.overall < 0.5 or r.error
        ]

        # Latency percentiles
        latencies = sorted(r.latency_ms for r in results if r.latency_ms > 0)
        p50 = latencies[len(latencies) // 2] if latencies else 0
        p95 = latencies[int(len(latencies) * 0.95)] if latencies else 0

        return EvalReport(
            run_id=f"eval-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}",
            timestamp=datetime.now(timezone.utc).isoformat(),
            total_queries=len(results),
            overall_score=round(overall, 3),
            by_intent=by_intent,
            by_dimension=by_dimension,
            results=results,
            failures=failures,
            latency_p50=round(p50, 1),
            latency_p95=round(p95, 1),
        )

    def save_report(self, report: EvalReport, output_dir: str = "") -> str:
        """Save report as JSON + markdown."""
        out_dir = Path(output_dir) if output_dir else DEFAULT_REPORT_DIR
        out_dir.mkdir(parents=True, exist_ok=True)

        # JSON
        json_path = out_dir / f"{report.run_id}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump({
                "run_id": report.run_id,
                "timestamp": report.timestamp,
                "total_queries": report.total_queries,
                "overall_score": report.overall_score,
                "by_intent": report.by_intent,
                "by_dimension": report.by_dimension,
                "failures": report.failures,
                "latency_p50": report.latency_p50,
                "latency_p95": report.latency_p95,
            }, f, indent=2)

        # Markdown
        md_path = out_dir / f"{report.run_id}.md"
        lines = [
            f"# Evaluation Report — {report.timestamp[:10]}",
            f"",
            f"**Overall: {report.overall_score*100:.1f}%** | Queries: {report.total_queries} | Failures: {len(report.failures)}",
            f"",
            f"## By Intent",
            f"| Intent | Score |",
            f"|--------|-------|",
        ]
        for intent, score in sorted(report.by_intent.items()):
            lines.append(f"| {intent} | {score*100:.1f}% |")
        lines += [
            f"",
            f"## By Dimension",
            f"| Dimension | Score |",
            f"|-----------|-------|",
        ]
        for dim, score in sorted(report.by_dimension.items()):
            lines.append(f"| {dim} | {score*100:.1f}% |")

        if report.failures:
            lines += [f"", f"## Failures ({len(report.failures)})"]
            for f_ in report.failures:
                lines.append(f"- **{f_['id']}**: {f_['question'][:60]} — score {f_['score']:.2f}")
                if f_.get("error"):
                    lines.append(f"  - Error: {f_['error']}")

        lines += [f"", f"## Latency", f"- p50: {report.latency_p50:.0f}ms | p95: {report.latency_p95:.0f}ms"]

        with open(md_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        return str(json_path)


def main():
    parser = argparse.ArgumentParser(description="Run intelligence evaluation benchmark")
    parser.add_argument("--live", action="store_true", help="Run against live API")
    parser.add_argument("--url", default="https://myscience-production.up.railway.app", help="API base URL")
    parser.add_argument("--offline", action="store_true", help="Score pre-captured responses")
    parser.add_argument("--responses", help="Path to captured responses JSON")
    parser.add_argument("--golden", default=str(DEFAULT_GOLDEN), help="Path to golden queries")
    parser.add_argument("--output", default=str(DEFAULT_REPORT_DIR), help="Report output directory")
    parser.add_argument("--ids", nargs="*", help="Run specific query IDs only")
    parser.add_argument("--dry-run", action="store_true", help="Load queries and validate without running")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    runner = EvalRunner(base_url=args.url, golden_path=args.golden)
    logger.info("Loaded %d golden queries from %s", len(runner._queries), args.golden)

    if args.dry_run:
        intents = {}
        for q in runner._queries:
            intents.setdefault(q.get("intent", "?"), []).append(q["id"])
        print(f"\nGolden dataset: {len(runner._queries)} queries")
        for intent, ids in sorted(intents.items()):
            print(f"  {intent}: {len(ids)} ({', '.join(ids[:3])}{'...' if len(ids) > 3 else ''})")
        return

    if args.live:
        report = runner.run_live(query_ids=args.ids)
    elif args.offline and args.responses:
        with open(args.responses, "r") as f:
            responses = json.load(f)
        report = runner.run_offline(responses)
    else:
        parser.error("Specify --live or --offline --responses <path>")
        return

    path = runner.save_report(report, args.output)
    print(f"\n=== Evaluation Report ===")
    print(f"Overall: {report.overall_score*100:.1f}%")
    print(f"Queries: {report.total_queries} | Failures: {len(report.failures)}")
    print(f"Latency: p50={report.latency_p50:.0f}ms p95={report.latency_p95:.0f}ms")
    print(f"\nBy Intent:")
    for intent, score in sorted(report.by_intent.items()):
        print(f"  {intent}: {score*100:.1f}%")
    print(f"\nSaved to: {path}")


if __name__ == "__main__":
    main()
