"""Capture live API responses for offline CI evaluation.

Sends each golden query to the running API, captures the response,
and saves the paired (query_id, response) list as JSON.

Usage:
    python -m benchmark.capture_responses --url https://myscience-production.up.railway.app \
                                          --golden benchmark/golden_queries.json \
                                          --output benchmark/captured_responses.json
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from benchmark.eval_runner import DEFAULT_GOLDEN

logger = logging.getLogger(__name__)


def capture_responses(
    base_url: str,
    golden_path: str = "",
    output_path: str = "",
) -> str:
    """Capture live API responses for offline evaluation.

    Args:
        base_url: Running API base URL (e.g. http://localhost:8020).
        golden_path: Path to golden queries JSON.
        output_path: Where to write the captured responses.

    Returns:
        Path to the saved captured responses file.
    """
    import requests

    gp = golden_path or str(DEFAULT_GOLDEN)
    with open(gp, "r", encoding="utf-8") as f:
        queries = json.load(f)

    out = output_path or str(Path(gp).parent / "captured_responses.json")
    captured: list[dict] = []
    url = base_url.rstrip("/")

    for q in queries:
        qid = q["id"]
        question = q.get("question", "")
        if not question:
            logger.warning("Skipping empty question: %s", qid)
            continue

        try:
            t0 = time.monotonic()
            resp = requests.post(
                f"{url}/chat",
                json={"question": question, "session_id": f"capture-{qid}"},
                timeout=60,
            )
            latency = (time.monotonic() - t0) * 1000

            if resp.status_code == 200:
                captured.append({
                    "query_id": qid,
                    "response": resp.json(),
                    "latency_ms": round(latency, 1),
                })
                logger.info("[%s] captured (%.0fms): %s", qid, latency, question[:50])
            else:
                logger.warning("[%s] HTTP %d: %s", qid, resp.status_code, question[:50])
                captured.append({
                    "query_id": qid,
                    "response": {"error": f"HTTP {resp.status_code}"},
                    "latency_ms": round(latency, 1),
                })

        except Exception as e:
            logger.error("[%s] error: %s", qid, e)
            captured.append({
                "query_id": qid,
                "response": {"error": str(e)},
                "latency_ms": 0,
            })

    with open(out, "w", encoding="utf-8") as f:
        json.dump(captured, f, indent=2)

    logger.info("Captured %d/%d responses -> %s", len(captured), len(queries), out)
    return out


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Capture live API responses for CI eval")
    parser.add_argument("--url", required=True, help="API base URL")
    parser.add_argument("--golden", default="", help="Path to golden queries JSON")
    parser.add_argument("--output", default="", help="Output path for captured responses")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    path = capture_responses(args.url, args.golden, args.output)
    print(f"Saved captured responses to: {path}")


if __name__ == "__main__":
    main()
