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
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel

from api.deps import get_db, require_role
from db import Database
from services.agent.nudge_intents import (
    NudgeError,
    VALID_AGENTS,
    list_intents,
    list_nudges,
    record_nudge,
)

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


# ── PB-203: agent nudges ─────────────────────────────────────────────────────


class NudgeBody(BaseModel):
    intent: str
    target: Optional[dict] = None
    note: Optional[str] = None


@router.get("/{agent}/intents")
def get_agent_intents(agent: str = Path(...)) -> dict:
    """List the nudge intents available for one agent. Anonymous read — this is
    static registry data the NudgeMenu renders. 404 for an unknown agent."""
    if agent.lower() not in VALID_AGENTS:
        raise HTTPException(404, f"unknown agent '{agent}'")
    return {"agent": agent.lower(),
            "intents": [i.to_dict() for i in list_intents(agent)]}


@router.post("/{agent}/nudge", status_code=201)
def post_agent_nudge(
    agent: str = Path(...),
    body: NudgeBody = ...,
    user: dict = Depends(require_role("uploader")),
    db: Database = Depends(get_db),
) -> dict:
    """Queue a nudge for an agent (append-only). The agent consumes it on its
    next background pass — this records the instruction, it does not execute it
    synchronously. 400 for an unknown agent/intent or a missing required
    target."""
    try:
        nudge = record_nudge(
            db, agent=agent, intent_key=body.intent, target=body.target,
            note=body.note, created_by=str(user.get("id") or user.get("username") or "user"),
        )
    except NudgeError as e:
        raise HTTPException(400, str(e)) from e
    for k in ("created_at",):
        if hasattr(nudge.get(k), "isoformat"):
            nudge[k] = nudge[k].isoformat()
    return {"nudge": nudge}


@router.get("/{agent}/nudges")
def get_agent_nudges(
    agent: str = Path(...),
    limit: int = Query(20, ge=1, le=100),
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
) -> dict:
    """Recent nudges queued for an agent (newest first)."""
    if agent.lower() not in VALID_AGENTS:
        raise HTTPException(404, f"unknown agent '{agent}'")
    rows = list_nudges(db, agent=agent, limit=limit)
    for r in rows:
        if hasattr(r.get("created_at"), "isoformat"):
            r["created_at"] = r["created_at"].isoformat()
    return {"agent": agent.lower(), "nudges": rows, "total": len(rows)}
