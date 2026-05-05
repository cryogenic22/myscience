"""SPEC-021 D2 — per-user rate limiting for LLM-heavy endpoints.

Sliding-window in-memory counter. Sufficient for single-instance prod;
for multi-instance deployments, swap the in-memory dict for Redis.

Limits are soft — when MZ_RATE_LIMIT_DISABLED=true the middleware is a
no-op (escape hatch for incident response). Limits per endpoint
defined in `_LIMITS`; tune via env var pattern `MZ_RATE_LIMIT_<ENDPOINT>=<n>`.

Returns 429 with `Retry-After: <seconds>` header when limit exceeded.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import deque
from typing import Optional

from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


# Default limits: (calls_per_window, window_seconds)
# Tune via MZ_RATE_LIMIT_<UPPER>=<n> env vars.
_DEFAULT_LIMITS: dict[str, tuple[int, int]] = {
    # path_pattern → (max_calls, window_seconds)
    "POST:/war-rooms/{room_id}/rounds":         (12, 3600),
    "POST:/war-rooms/{room_id}/suggest-moves":  (20, 3600),
    "POST:/decisions/{id}/suggest-outcome":     (30, 3600),
    "POST:/decisions/{id}/capture-outcome":     (30, 3600),
}


def _is_disabled() -> bool:
    return os.environ.get("MZ_RATE_LIMIT_DISABLED", "").lower() in ("1", "true", "yes")


def _env_limit(endpoint_key: str, default: tuple[int, int]) -> tuple[int, int]:
    """Allow per-endpoint override via env var."""
    safe = endpoint_key.replace("/", "_").replace("{", "").replace("}", "").replace(":", "_").upper()
    raw = os.environ.get(f"MZ_RATE_LIMIT_{safe}")
    if not raw:
        return default
    try:
        return (int(raw), default[1])
    except ValueError:
        return default


class _SlidingCounter:
    """Per-(user, endpoint) sliding window."""

    def __init__(self):
        self._buckets: dict[tuple[str, str], deque] = {}
        self._lock = threading.Lock()

    def hit(self, user_id: str, endpoint: str, max_calls: int, window_s: int) -> tuple[bool, int]:
        """Returns (allowed, retry_after_seconds).

        retry_after is 0 when allowed, else seconds until the oldest hit
        in the window expires (caller can wait this long and retry).
        """
        now = time.time()
        cutoff = now - window_s
        key = (user_id, endpoint)
        with self._lock:
            dq = self._buckets.setdefault(key, deque())
            # Drop expired
            while dq and dq[0] < cutoff:
                dq.popleft()
            if len(dq) >= max_calls:
                retry_after = max(1, int(dq[0] + window_s - now))
                return False, retry_after
            dq.append(now)
            return True, 0

    def reset(self) -> None:
        """For tests."""
        with self._lock:
            self._buckets.clear()


# Module-level singleton (per-process, fine for single-instance Railway)
_counter = _SlidingCounter()


def reset_rate_limit_state() -> None:
    """Clear all counters. Call from test setup/teardown."""
    _counter.reset()


def _match_endpoint(method: str, path: str) -> Optional[str]:
    """Match a concrete request path to one of the rate-limited
    parametric routes. Returns the canonical key or None.

    Path matching is intentionally loose: we substitute the {param}
    segments by checking segment counts + literal prefix/suffix.
    Cheaper than importing FastAPI's path matcher.
    """
    for key in _DEFAULT_LIMITS:
        m, pattern = key.split(":", 1)
        if m != method:
            continue
        # Replace {param} segments with wildcards in a positional check
        pattern_segs = pattern.strip("/").split("/")
        path_segs = path.strip("/").split("/")
        if len(pattern_segs) != len(path_segs):
            continue
        ok = True
        for ps, xs in zip(pattern_segs, path_segs):
            if ps.startswith("{") and ps.endswith("}"):
                continue  # wildcard
            if ps != xs:
                ok = False
                break
        if ok:
            return key
    return None


def _decode_user_id(request: Request) -> Optional[str]:
    """Pull `sub` out of the JWT without verifying — UI hint only.
    Rate limiting unauthenticated traffic by IP is a separate concern
    (the routes themselves require auth so this only catches authed
    misuse anyway)."""
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        return None
    tok = auth.split(None, 1)[1].strip()
    parts = tok.split(".")
    if len(parts) != 3:
        return None
    import base64
    import json as _json
    payload = parts[1]
    pad = "=" * ((4 - len(payload) % 4) % 4)
    try:
        decoded = base64.urlsafe_b64decode(payload + pad).decode("utf-8")
        data = _json.loads(decoded)
        return data.get("sub")
    except Exception:
        return None


async def rate_limit_middleware(request: Request, call_next):
    """ASGI middleware for per-user rate limiting on configured endpoints.

    Skips:
      - any request when MZ_RATE_LIMIT_DISABLED is set
      - paths that don't match a configured limit
      - requests without a parseable user JWT (route auth handles those)
    """
    if _is_disabled():
        return await call_next(request)

    endpoint = _match_endpoint(request.method, request.url.path)
    if endpoint is None:
        return await call_next(request)

    user_id = _decode_user_id(request)
    if user_id is None:
        # Let the route's auth dependency reject — no point counting.
        return await call_next(request)

    max_calls, window_s = _env_limit(endpoint, _DEFAULT_LIMITS[endpoint])
    allowed, retry_after = _counter.hit(user_id, endpoint, max_calls, window_s)

    if not allowed:
        logger.info(
            "rate_limit: user=%s endpoint=%s blocked, retry_after=%ds",
            user_id, endpoint, retry_after,
        )
        return JSONResponse(
            status_code=429,
            headers={"Retry-After": str(retry_after)},
            content={
                "error": {
                    "code": 429,
                    "type": "rate_limited",
                    "message": (
                        f"Rate limit exceeded for {endpoint}: "
                        f"{max_calls} requests per {window_s}s. "
                        f"Retry in {retry_after}s."
                    ),
                    "details": {
                        "endpoint": endpoint,
                        "max_calls": max_calls,
                        "window_seconds": window_s,
                        "retry_after_seconds": retry_after,
                    },
                },
                # Back-compat: keep `detail` for clients that read it
                "detail": f"Rate limit exceeded; retry in {retry_after}s.",
            },
        )

    return await call_next(request)
