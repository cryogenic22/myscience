"""Data Steward API routes.

Trigger, monitor, and inspect the autonomous data curation loop.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Query

from api.deps import get_db
from db import Database

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/steward", tags=["steward"])


@router.post("/run")
def run_steward(
    body: dict,
    background_tasks: BackgroundTasks,
    db: Database = Depends(get_db),
):
    """Trigger a steward loop run as a background task."""
    dry_run = body.get("dry_run", False)
    max_iterations = body.get("max_iterations", 20)
    skip_ai = body.get("skip_ai", True)

    def _run():
        try:
            from services.steward_signals import StewardSignalCollector
            from services.data_steward import DataSteward, StewardConfig
            collector = StewardSignalCollector(db)
            config = StewardConfig(
                max_iterations=max_iterations,
                dry_run=dry_run,
                skip_ai=skip_ai,
            )
            steward = DataSteward(db, collector, config)
            summary = steward.run_loop()
            logger.info("Steward run complete: %s", summary)
        except Exception:
            logger.exception("Steward background run failed")

    background_tasks.add_task(_run)
    return {"status": "started", "dry_run": dry_run, "max_iterations": max_iterations}


@router.get("/status")
def steward_status(db: Database = Depends(get_db)):
    """Return latest steward activity stats."""
    try:
        recent = db.fetch_all(
            """
            SELECT status, COUNT(*) AS cnt
            FROM steward_actions
            WHERE created_at > NOW() - INTERVAL '7 days'
            GROUP BY status
            """
        )
        total = db.fetch_one(
            "SELECT COUNT(*) AS cnt FROM steward_actions"
        )
        latest = db.fetch_one(
            "SELECT MAX(completed_at) AS last_run FROM steward_actions WHERE status = 'completed'"
        )
        return {
            "total_actions": total["cnt"] if total else 0,
            "last_7_days": {r["status"]: r["cnt"] for r in recent},
            "last_completed_run": latest["last_run"] if latest else None,
        }
    except Exception:
        return {"total_actions": 0, "last_7_days": {}, "last_completed_run": None}


@router.get("/signals")
def list_signals(
    limit: int = Query(20, ge=1, le=100),
    since_days: int = Query(7, ge=1, le=90),
    db: Database = Depends(get_db),
):
    """Preview the current ranked signal queue."""
    try:
        from services.steward_signals import StewardSignalCollector
        collector = StewardSignalCollector(db)
        signals = collector.collect_signals(limit=limit, since_days=since_days)
        return {
            "signals": [
                {
                    "source": s.source,
                    "source_id": s.source_id,
                    "entity_name": s.entity_name,
                    "gap_type": s.gap_type,
                    "priority_score": round(s.priority_score, 3),
                    "details": s.details,
                }
                for s in signals
            ],
            "count": len(signals),
        }
    except Exception:
        return {"signals": [], "count": 0}


@router.get("/actions")
def list_actions(
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Database = Depends(get_db),
):
    """Return steward action history."""
    try:
        conditions = []
        params = []
        if status:
            conditions.append("status = %s")
            params.append(status)

        where = "WHERE " + " AND ".join(conditions) if conditions else ""

        rows = db.fetch_all(
            f"""
            SELECT id, signal_source, entity_type, entity_name,
                   action_type, status, fair_before, fair_after, fair_delta,
                   error_message, created_at, completed_at
            FROM steward_actions {where}
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
            """,
            params + [limit, offset],
        )
        total = db.fetch_one(
            f"SELECT COUNT(*) AS cnt FROM steward_actions {where}", params
        )
        return {
            "items": rows,
            "total": total["cnt"] if total else 0,
            "limit": limit,
            "offset": offset,
        }
    except Exception:
        return {"items": [], "total": 0, "limit": limit, "offset": offset}
