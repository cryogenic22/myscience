"""BE-14 — Scheduled-run executor for the PB-505 "run while I sleep" UX.

Idempotent picker: claim queued rows whose wake_at has elapsed,
mark RUNNING, execute, write result + bump status. The scheduler
loop (or a simple cron) calls ``execute_due(db)`` on a cadence.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# Registry: scenario_kind → callable(db, parameters) -> dict
# Caller registers handlers at startup. Registry lives at module
# scope so wiring stays explicit and testable.
_HANDLERS: dict[str, Callable[[Any, dict], dict]] = {}


def register_handler(scenario_kind: str, fn: Callable[[Any, dict], dict]) -> None:
    """Register an executor for a scenario_kind. Idempotent — last
    registration wins so tests can swap implementations."""
    _HANDLERS[str(scenario_kind)] = fn


def queue(
    db: Any,
    *,
    requested_by: str,
    scenario_kind: str,
    parameters: dict,
    wake_at: datetime,
    war_room_id: Optional[str] = None,
) -> dict:
    """Persist a queued run; returns the row dict."""
    row = db.fetch_one(
        """
        INSERT INTO delegated_runs
            (requested_by, war_room_id, scenario_kind,
             parameters, wake_at)
        VALUES (%s::uuid, %s, %s, %s::jsonb, %s)
        RETURNING run_id, requested_by, war_room_id, scenario_kind,
                  parameters, wake_at, status, created_at
        """,
        [requested_by, war_room_id, scenario_kind,
         json.dumps(parameters or {}), wake_at],
    )
    if not row:
        raise RuntimeError("queue: insert returned no row")
    return dict(row)


def _claim_one(db: Any) -> Optional[dict]:
    """Atomically claim ONE due row, marking it as running.

    Uses SKIP LOCKED so multiple workers can run the executor
    concurrently without stepping on each other.
    """
    row = db.fetch_one(
        """
        UPDATE delegated_runs
           SET status = 'running', started_at = NOW()
         WHERE run_id = (
            SELECT run_id FROM delegated_runs
             WHERE status = 'queued' AND wake_at <= NOW()
             ORDER BY wake_at ASC
             LIMIT 1
             FOR UPDATE SKIP LOCKED
         )
        RETURNING run_id, requested_by, war_room_id, scenario_kind,
                  parameters
        """
    )
    return dict(row) if row else None


def _complete(db: Any, run_id: str, *, status: str, result: Optional[dict] = None,
              error_message: Optional[str] = None) -> None:
    db.execute(
        """UPDATE delegated_runs
              SET status = %s,
                  result = %s::jsonb,
                  error_message = %s,
                  completed_at = NOW()
            WHERE run_id::text = %s""",
        [status, json.dumps(result or {}) if result is not None else None,
         (error_message or "")[:500] if error_message else None,
         str(run_id)],
    )


def execute_due(db: Any, *, max_runs: int = 5) -> dict:
    """Run up to ``max_runs`` due delegations. Returns a summary."""
    completed = 0
    failed = 0
    skipped = 0
    for _ in range(max(1, int(max_runs))):
        claimed = _claim_one(db)
        if claimed is None:
            break
        kind = claimed.get("scenario_kind")
        params = claimed.get("parameters") or {}
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except (TypeError, ValueError):
                params = {}
        handler = _HANDLERS.get(str(kind))
        if handler is None:
            skipped += 1
            _complete(
                db, claimed["run_id"],
                status="failed",
                error_message=f"no handler registered for scenario_kind={kind}",
            )
            continue
        try:
            result = handler(db, params) or {}
            _complete(db, claimed["run_id"], status="complete", result=result)
            completed += 1
        except Exception as exc:
            logger.exception("delegated run failed (run_id=%s)", claimed["run_id"])
            _complete(db, claimed["run_id"], status="failed",
                      error_message=str(exc))
            failed += 1
    return {"completed": completed, "failed": failed, "skipped": skipped}


def list_for_user(db: Any, *, user_id: str, limit: int = 50) -> list[dict]:
    rows = db.fetch_all(
        """SELECT run_id, war_room_id, scenario_kind,
                  status, wake_at, created_at, started_at, completed_at,
                  error_message
             FROM delegated_runs
            WHERE requested_by::text = %s
            ORDER BY created_at DESC
            LIMIT %s""",
        [str(user_id), max(1, min(int(limit), 500))],
    ) or []
    out = []
    for r in rows:
        d = dict(r)
        for k in ("wake_at", "created_at", "started_at", "completed_at"):
            v = d.get(k)
            if v and hasattr(v, "isoformat"):
                d[k] = v.isoformat()
        out.append(d)
    return out
