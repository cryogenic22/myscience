"""SPEC-021 D2 — daily LLM call quota per authenticated user.

Persisted in `llm_quota_usage(user_id, day, call_count)`. Cap defaults
to 200/user/day, configurable via `MZ_LLM_DAILY_CAP`. Resets at
midnight UTC. Failed calls also count (a failed call still costs).

Flow:
  - Endpoint-level: caller checks `quota_check(db, user_id)` before
    invoking the LLM. Returns (allowed, used, cap, reset_in_seconds).
  - On allowed: caller invokes LLM, then `quota_increment(db, user_id)`.
  - On denied: caller returns 429 with structured envelope.

Race: between check and increment, two concurrent requests could both
pass the check and exceed the cap by 1. Acceptable for a soft cap.
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime, time as dtime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


def _cap() -> int:
    raw = os.environ.get("MZ_LLM_DAILY_CAP", "200")
    try:
        return max(1, int(raw))
    except ValueError:
        return 200


def _seconds_until_utc_midnight() -> int:
    now = datetime.now(timezone.utc)
    midnight = datetime.combine(now.date(), dtime.max, tzinfo=timezone.utc)
    return max(60, int((midnight - now).total_seconds()))


def quota_check(db, user_id: str) -> tuple[bool, int, int, int]:
    """Returns (allowed, used_today, cap, reset_in_seconds).

    `allowed` is True when used < cap. Always returns a usable tuple
    even if the DB lookup fails (defaults to allowed=True so we
    fail-open on infra errors rather than blocking valid traffic).
    """
    cap = _cap()
    today = date.today()
    used = 0
    try:
        row = db.fetch_one(
            "SELECT call_count FROM llm_quota_usage WHERE user_id = %s::uuid AND day = %s",
            [user_id, today],
        )
        used = int(row["call_count"]) if row and row.get("call_count") is not None else 0
    except Exception:
        logger.warning("quota_check: DB read failed for user=%s; failing open", user_id)
        return True, 0, cap, _seconds_until_utc_midnight()

    return used < cap, used, cap, _seconds_until_utc_midnight()


def quota_increment(db, user_id: str) -> None:
    """Increment today's count for a user. Uses INSERT ... ON CONFLICT
    so the row is created on first call of the day."""
    today = date.today()
    try:
        db.execute(
            """INSERT INTO llm_quota_usage (user_id, day, call_count)
               VALUES (%s::uuid, %s, 1)
               ON CONFLICT (user_id, day)
               DO UPDATE SET call_count = llm_quota_usage.call_count + 1""",
            [user_id, today],
        )
    except Exception:
        logger.warning("quota_increment: DB write failed for user=%s", user_id)


def quota_envelope(used: int, cap: int, reset_in_seconds: int) -> dict:
    """Build the structured 429 response body for cap exceeded."""
    return {
        "error": {
            "code": 429,
            "type": "llm_quota_exceeded",
            "message": (
                f"Daily LLM call quota reached ({used}/{cap}). "
                f"Resets in {reset_in_seconds // 60} minutes (midnight UTC)."
            ),
            "details": {
                "used": used,
                "cap": cap,
                "reset_in_seconds": reset_in_seconds,
            },
        },
        "detail": f"Daily LLM cap reached ({used}/{cap}). Resets at midnight UTC.",
    }
