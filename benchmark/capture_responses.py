"""Capture live API responses for offline CI evaluation.

Sends each golden query to the system, captures the response, and saves the
paired (query_id, response) list as JSON. Two capture modes share one loop:

  * HTTP   — POST /chat against a running deployment (the scheduled live-eval
             job uses this against prod).
  * in-process — boot create_app() + TestClient and call /chat directly. Used to
             produce an honest baseline from an owned DB without depending on a
             reachable public URL.

Usage:
    python -m benchmark.capture_responses --url https://<deployment> \
                                          --output benchmark/captured_responses.json
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Callable, Tuple

from benchmark.eval_runner import DEFAULT_GOLDEN

logger = logging.getLogger(__name__)

# A poster takes (question, session_id) and returns (status_code, body, latency_ms).
Poster = Callable[[str, str], Tuple[int, dict, float]]


def http_poster(base_url: str, timeout: float = 90.0) -> Poster:
    """A poster that POSTs /chat to a running deployment."""
    import requests

    url = base_url.rstrip("/")

    def post(question: str, session_id: str) -> Tuple[int, dict, float]:
        t0 = time.monotonic()
        resp = requests.post(
            f"{url}/chat",
            json={"question": question, "session_id": session_id},
            timeout=timeout,
        )
        latency = (time.monotonic() - t0) * 1000
        if resp.status_code == 200:
            return resp.status_code, resp.json(), latency
        return resp.status_code, {"error": f"HTTP {resp.status_code}"}, latency

    return post


def in_process_poster() -> Poster:
    """A poster that calls /chat in-process via TestClient (no network/uvicorn).

    Requires DATABASE_URL + OPENAI_API_KEY in the environment — it runs the real
    chat handler against whatever DB is configured.
    """
    from fastapi.testclient import TestClient

    from api.app import create_app

    client = TestClient(create_app())

    def post(question: str, session_id: str) -> Tuple[int, dict, float]:
        t0 = time.monotonic()
        resp = client.post("/chat", json={"question": question, "session_id": session_id})
        latency = (time.monotonic() - t0) * 1000
        if resp.status_code == 200:
            return resp.status_code, resp.json(), latency
        return resp.status_code, {"error": f"HTTP {resp.status_code}"}, latency

    return post


def run_capture(
    queries: list[dict],
    poster: Poster,
    output_path: str = "",
) -> Tuple[str, list[dict]]:
    """Run *poster* over *queries* and persist the captured responses.

    Returns (output_path, captured). Per-query errors are captured (not raised)
    so one failure doesn't abort the run — the caller decides whether the overall
    capture is healthy (see live_eval, which fails loud on too many errors).
    """
    captured: list[dict] = []
    for q in queries:
        qid = q["id"]
        question = q.get("question", "")
        if not question:
            logger.warning("Skipping empty question: %s", qid)
            continue
        try:
            status, body, latency = poster(question, f"capture-{qid}")
            captured.append({"query_id": qid, "response": body, "latency_ms": round(latency, 1)})
            if status == 200:
                logger.info("[%s] captured (%.0fms): %s", qid, latency, question[:50])
            else:
                logger.warning("[%s] HTTP %d: %s", qid, status, question[:50])
        except Exception as e:  # noqa: BLE001 — record, don't abort the batch
            logger.error("[%s] error: %s", qid, e)
            captured.append({"query_id": qid, "response": {"error": str(e)}, "latency_ms": 0})

    out = output_path or str(Path(DEFAULT_GOLDEN).parent / "captured_responses.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(captured, f, indent=2)
    logger.info("Captured %d/%d responses -> %s", len(captured), len(queries), out)
    return out, captured


def capture_responses(
    base_url: str,
    golden_path: str = "",
    output_path: str = "",
) -> str:
    """Capture live API responses over HTTP (back-compat entry point)."""
    gp = golden_path or str(DEFAULT_GOLDEN)
    with open(gp, "r", encoding="utf-8") as f:
        queries = json.load(f)
    out, _ = run_capture(queries, http_poster(base_url), output_path)
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
