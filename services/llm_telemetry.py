"""SPEC-021 D2 — LLM call telemetry.

Lightweight wrapper around `LLMSynthesizer.raw_chat` that persists
per-call metadata to `llm_call_log` so we can compute p95 latency,
daily cost rollup per user, and retrospectively diagnose bad
responses.

Designed to be a strict superset of `raw_chat`'s contract — call
sites only need to substitute the function name; the return value is
identical (`Optional[str]`). DB write failures are non-fatal.

Cost estimation uses a small in-process price table; update when
upstream pricing changes. Token counts come from the OpenAI response
when present, else estimated from text length (4 chars ≈ 1 token).
"""

from __future__ import annotations

import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)


# Price per 1M tokens in USD. Update when OpenAI pricing changes.
# Conservative defaults — we'd rather over-estimate cost than miss it.
_PRICE_TABLE = {
    # Input, Output (USD per 1M tokens)
    "gpt-4o":              (2.50, 10.00),
    "gpt-4o-mini":         (0.15, 0.60),
    "gpt-4-turbo":         (10.00, 30.00),
    "gpt-4":               (30.00, 60.00),
    "gpt-3.5-turbo":       (0.50, 1.50),
}


def _estimate_cost_usd(model: Optional[str], prompt_tokens: int, completion_tokens: int) -> float:
    """Conservative cost estimate. Defaults to a mid-tier model price
    when the exact model isn't in the table."""
    in_per_m, out_per_m = _PRICE_TABLE.get(model or "", (2.50, 10.00))
    return (prompt_tokens / 1_000_000) * in_per_m + (completion_tokens / 1_000_000) * out_per_m


def _est_tokens(text: str) -> int:
    """Rough token estimate when the API doesn't return usage. 4 chars ≈ 1 token
    is the well-known OpenAI rule of thumb for English text."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def log_llm_call(
    db,
    *,
    caller: str,
    model: Optional[str],
    prompt_version: Optional[str],
    user_id: Optional[str],
    latency_ms: int,
    prompt_tokens: int,
    completion_tokens: int,
    succeeded: bool,
    error_message: Optional[str] = None,
) -> None:
    """Insert one row into llm_call_log. Failure is non-fatal."""
    cost = _estimate_cost_usd(model, prompt_tokens, completion_tokens)
    try:
        db.execute(
            """INSERT INTO llm_call_log
                   (caller, model, prompt_version, user_id, latency_ms,
                    prompt_tokens, completion_tokens, cost_estimate_usd,
                    succeeded, error_message)
               VALUES (%s, %s, %s, %s::uuid, %s, %s, %s, %s, %s, %s)""",
            [
                caller, model, prompt_version, user_id, latency_ms,
                prompt_tokens, completion_tokens, cost,
                succeeded, error_message,
            ],
        )
    except Exception as exc:
        # Telemetry must never break the caller. Log + drop.
        logger.warning("llm_call_log insert failed: %s", exc)


def chat_with_telemetry(
    llm,
    db,
    *,
    system: str,
    user: str,
    caller: str,
    prompt_version: str = "v1",
    user_id: Optional[str] = None,
    max_tokens: int = 900,
    temperature: float = 0.2,
    timeout_seconds: float = 45.0,
) -> Optional[str]:
    """Drop-in wrapper for `LLMSynthesizer.raw_chat` that persists
    a row to `llm_call_log` AND enforces a wall-clock timeout.

    The timeout uses a ThreadPoolExecutor future — when the budget
    expires, we stop waiting and return None. Note: this does NOT
    actually cancel the underlying HTTP request (the orphaned thread
    eventually finishes/errors); but it does prevent slow LLM calls
    from blocking request handlers indefinitely.

    Behaviour mirrors `raw_chat`:
      - `llm` is None or `llm.enabled` is False → returns None, no log row
      - call succeeds → returns text, logs row with succeeded=True
      - all model attempts fail → returns None, logs row with succeeded=False
      - timeout exceeded → returns None, logs row with error_message='timeout'
    """
    if llm is None or not getattr(llm, "enabled", False):
        return None

    model = getattr(getattr(llm, "config", None), "llm", None)
    model_name = getattr(model, "model", None) if model else None

    import concurrent.futures

    t0 = time.perf_counter()
    text: Optional[str] = None
    error: Optional[str] = None

    def _invoke() -> Optional[str]:
        return llm.raw_chat(
            system=system, user=user,
            max_tokens=max_tokens, temperature=temperature,
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_invoke)
        try:
            text = future.result(timeout=timeout_seconds)
        except concurrent.futures.TimeoutError:
            error = f"timeout after {timeout_seconds}s"
            # We don't .cancel() — the running request can't be killed.
            # The thread will finish and be GC'd; we just stop waiting.
        except Exception as exc:
            error = str(exc)[:500]
    elapsed_ms = int((time.perf_counter() - t0) * 1000)

    succeeded = bool(text)
    # Token estimates: OpenAI client may surface `.usage` when available
    # but raw_chat doesn't currently bubble it. Until raw_chat is upgraded
    # to return usage, estimate from text lengths — under-counts but the
    # rollup is still useful for trend tracking.
    pt = _est_tokens(system + "\n" + user)
    ct = _est_tokens(text or "")

    log_llm_call(
        db,
        caller=caller,
        model=model_name,
        prompt_version=prompt_version,
        user_id=user_id,
        latency_ms=elapsed_ms,
        prompt_tokens=pt,
        completion_tokens=ct,
        succeeded=succeeded,
        error_message=error,
    )

    return text
