"""Live-eval capture + score — the TRUE system-quality bar.

The PR `benchmark` gate only smoke-tests the *scorer* (synthetic known-good
responses). This runs the REAL system against the golden queries, scores the
real answers, and checks them against a committed baseline. It is operational
(Lane 2): it needs a live system, so it runs on a schedule, never on a PR.

Two capture modes:
  --url <deployment>   capture over HTTP (the scheduled job vs prod)
  --in-process         boot create_app() + TestClient against the configured DB
                       (used to produce an honest baseline from an owned DB)

Fail-loud contract (principle #3, no vacuous green): if too few queries produce
a real 200 response, the run FAILS rather than scoring a near-empty capture as
"healthy". A dead deployment must red the scheduled run, not pass it.

Usage:
    # scheduled job, vs prod
    python -m benchmark.live_eval --url https://<deployment> \
        --baseline benchmark/reports/live-eval-baseline.json \
        --threshold 50 --regression-limit 10

    # produce a baseline from prod DB in-process
    DATABASE_URL=... python -m benchmark.live_eval --in-process \
        --output benchmark/reports/live-eval-baseline.json --write-baseline
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from benchmark.capture_responses import http_poster, in_process_poster, run_capture
from benchmark.ci_eval import run_ci_eval
from benchmark.eval_runner import DEFAULT_GOLDEN, DEFAULT_REPORT_DIR

logger = logging.getLogger(__name__)

# If fewer than this share of queries return a real (non-error) response, the
# capture is considered broken — a dead/unreachable system must fail loud.
MIN_HEALTHY_SHARE = 0.5


def _healthy_count(captured: list[dict]) -> int:
    """Count captured items that carry a real response (no transport error)."""
    n = 0
    for item in captured:
        resp = item.get("response") or {}
        if isinstance(resp, dict) and "error" not in resp and resp.get("narrative") is not None:
            n += 1
    return n


def run_live_eval(
    *,
    url: str = "",
    in_process: bool = False,
    golden_path: str = "",
    baseline_path: str = "",
    threshold: float = 0.0,
    regression_limit: float = 10.0,
    captured_output: str = "",
) -> dict:
    """Capture real responses then score them. Returns the ci_eval result dict
    augmented with capture health. Raises RuntimeError if the capture is unhealthy."""
    if not (url or in_process):
        raise ValueError("provide --url <deployment> or --in-process")

    gp = golden_path or str(DEFAULT_GOLDEN)
    with open(gp, "r", encoding="utf-8") as f:
        queries = json.load(f)

    poster = in_process_poster() if in_process else http_poster(url)
    cap_out = captured_output or str(DEFAULT_REPORT_DIR / "live-captured.json")
    _, captured = run_capture(queries, poster, cap_out)

    # Health is measured over ATTEMPTABLE queries (a golden item with an empty
    # question is never posted, so it must not count against the system).
    attemptable = sum(1 for q in queries if q.get("question"))
    healthy = _healthy_count(captured)
    share = healthy / attemptable if attemptable else 0.0
    logger.info("capture health: %d/%d (%.0f%%) returned a real response", healthy, attemptable, share * 100)
    if share < MIN_HEALTHY_SHARE:
        raise RuntimeError(
            f"capture unhealthy: only {healthy}/{len(queries)} ({share:.0%}) queries returned a "
            f"real response (floor {MIN_HEALTHY_SHARE:.0%}) — refusing to score a broken capture"
        )

    result = run_ci_eval(
        baseline_path=baseline_path,
        responses_path=cap_out,
        golden_path=gp,
        threshold=threshold,
        regression_limit=regression_limit,
    )
    result["capture_healthy"] = healthy
    result["capture_total"] = attemptable
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture + score the real system (live eval)")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--url", default="", help="Deployment base URL (HTTP capture)")
    src.add_argument("--in-process", action="store_true", help="Capture in-process via TestClient")
    parser.add_argument("--golden", default="", help="Path to golden queries JSON")
    parser.add_argument("--baseline", default="", help="Path to baseline report JSON")
    parser.add_argument("--threshold", type=float, default=0.0, help="Min composite score %% (fail if below)")
    parser.add_argument("--regression-limit", type=float, default=10.0, help="Max per-dimension drop (pp)")
    parser.add_argument("--output", default="", help="Where to write the captured responses")
    parser.add_argument(
        "--write-baseline", action="store_true",
        help="Also copy the scored report to --output as the new baseline",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    try:
        result = run_live_eval(
            url=args.url,
            in_process=args.in_process,
            golden_path=args.golden,
            baseline_path=args.baseline,
            threshold=args.threshold,
            regression_limit=args.regression_limit,
            captured_output=args.output if not args.write_baseline else "",
        )
    except Exception as e:  # noqa: BLE001
        print(f"\nLIVE-EVAL ERROR: {e}", file=sys.stderr)
        return 1

    if args.write_baseline and args.output:
        # Persist a baseline in the shape run_ci_eval's baseline loader reads
        # (overall_score + by_dimension). Writing the ci-summary here instead
        # would key it as "overall" and the loader would silently read 0.0 — a
        # vacuous regression check. So emit the loader-compatible keys explicitly.
        baseline_doc = {
            "overall_score": result["overall"],
            "by_dimension": result["by_dimension"],
            "by_intent": result["by_intent"],
            "total_queries": result["total_queries"],
            "timestamp": result["timestamp"],
        }
        Path(args.output).write_text(json.dumps(baseline_doc, indent=2), encoding="utf-8")
        print(f"  Wrote baseline -> {args.output}")

    overall = result["overall"] * 100
    print(f"\n  LIVE-EVAL: overall {overall:.1f}% on real responses "
          f"({result['capture_healthy']}/{result['capture_total']} healthy)")
    if result["passed"]:
        print("  RESULT: PASSED")
        return 0
    print("  RESULT: FAILED")
    for reason in result.get("fail_reasons", []):
        print(f"    - {reason}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
