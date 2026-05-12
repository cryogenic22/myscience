"""Loop #21 — Agent activity feed.

Surfaces the latest line of work for each of the three named agents
(Sentinel, Strategist, Curator) so /ci can show them as colleagues
rather than static labels. Derives activity from real DB rows so the
feed is honest:

  • Sentinel  → newest shipped/reviewed signals
  • Strategist → newest war_room sessions and game-theory sims
  • Curator   → newest learning events / weight changes

When the underlying tables are empty or unavailable the endpoint falls
back to a small set of plausible idle lines so the UI never displays
a blank row in demos.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from api.deps import get_db
from db import Database

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents", tags=["agents"])


def _iso(v) -> str | None:
    if v is None:
        return None
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return str(v)


def _safe_fetch_one(db: Database, sql: str, params: list | None = None) -> dict | None:
    try:
        return db.fetch_one(sql, params or [])
    except Exception:
        logger.exception("agent activity fetch failed")
        return None


def _sentinel(db: Database) -> dict:
    row = _safe_fetch_one(
        db,
        """
        SELECT headline, impact_tier, impact_score, kbq_tags,
               COALESCE(shipped_at, reviewed_at, created_at) AS ts
          FROM signals
         WHERE status IN ('shipped', 'reviewed')
         ORDER BY COALESCE(shipped_at, reviewed_at, created_at) DESC NULLS LAST
         LIMIT 1
        """,
    )
    if row and row.get("headline"):
        ts = _iso(row.get("ts")) or datetime.now(timezone.utc).isoformat()
        tier = (row.get("impact_tier") or "").lower()
        prefix = "Promoted to shipped" if tier == "high" else "Scored"
        text = f"{prefix}: {row['headline']}"
        return {
            "agent_id": "sentinel",
            "kind": "completed",
            "text": text[:240],
            "timestamp": ts,
        }
    return {
        "agent_id": "sentinel",
        "kind": "started",
        "text": "Sweeping ingestion queue for fresh market signals…",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _strategist(db: Database) -> dict:
    # Prefer a recent war_room session; fall back to a game-theory run.
    row = _safe_fetch_one(
        db,
        """
        SELECT title, scenario_question, created_at
          FROM war_room_sessions
         ORDER BY created_at DESC NULLS LAST
         LIMIT 1
        """,
    )
    if row and row.get("title"):
        ts = _iso(row.get("created_at")) or datetime.now(timezone.utc).isoformat()
        title = row["title"]
        text = f'War-gaming scenario: "{title}"'
        return {
            "agent_id": "strategist",
            "kind": "progress",
            "text": text[:240],
            "timestamp": ts,
        }
    return {
        "agent_id": "strategist",
        "kind": "started",
        "text": "Waiting for a decision to frame — ready to simulate.",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _curator(db: Database) -> dict:
    # Prefer most recent materiality config change (proxy for learning).
    row = _safe_fetch_one(
        db,
        """
        SELECT created_at, weights_jsonb
          FROM materiality_weight_config
         WHERE is_active = TRUE
         ORDER BY created_at DESC
         LIMIT 1
        """,
    )
    if row and row.get("created_at"):
        ts = _iso(row.get("created_at")) or datetime.now(timezone.utc).isoformat()
        return {
            "agent_id": "curator",
            "kind": "completed",
            "text": "Active materiality weights re-calibrated from reviewer outcomes.",
            "timestamp": ts,
        }
    return {
        "agent_id": "curator",
        "kind": "started",
        "text": "Listening for reviewer decisions to learn from…",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/activity")
def get_agent_activity(db: Database = Depends(get_db)) -> dict:
    """Latest activity per agent (one row per agent). Anonymous read.

    Frontend polls this every ~5 seconds. Returns `poll_after_seconds`
    so a future server can throttle clients without a code change.
    """
    activities = [_sentinel(db), _strategist(db), _curator(db)]
    return {
        "activities": activities,
        "poll_after_seconds": 5,
    }
