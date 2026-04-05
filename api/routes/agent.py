"""Agent Harness API -- events, sessions, registry, permissions."""

from __future__ import annotations

import logging
from fastapi import APIRouter, Depends, Query
from typing import Optional

from api.deps import get_db
from db import Database

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agent", tags=["agent"])


@router.get("/events")
def get_agent_events(
    event_type: Optional[str] = Query(None),
    agent_type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: Database = Depends(get_db),
):
    """Get recent agent events from the event stream."""
    try:
        conditions = []
        params = []
        if event_type:
            conditions.append("event_type = %s")
            params.append(event_type)
        if agent_type:
            conditions.append("agent_type = %s")
            params.append(agent_type)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)

        rows = db.fetch_all(
            f"""SELECT id, session_id, event_type, agent_type, tool_name,
                       trust_tier, args_hash, result_status, metadata, created_at
                FROM agent_events
                {where}
                ORDER BY created_at DESC
                LIMIT %s""",
            params,
        )
        return {"events": [dict(r) for r in rows], "total": len(rows)}
    except Exception:
        return {"events": [], "total": 0}


@router.get("/sessions")
def get_agent_sessions(
    agent_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: Database = Depends(get_db),
):
    """Get recent agent sessions."""
    try:
        conditions = []
        params = []
        if agent_type:
            conditions.append("agent_type = %s")
            params.append(agent_type)
        if status:
            conditions.append("status = %s")
            params.append(status)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)

        rows = db.fetch_all(
            f"""SELECT id, agent_type, goal, status, current_step, total_steps,
                       started_at, last_checkpoint, completed_at, error_message
                FROM agent_sessions
                {where}
                ORDER BY started_at DESC
                LIMIT %s""",
            params,
        )
        return {"sessions": [dict(r) for r in rows], "total": len(rows)}
    except Exception:
        return {"sessions": [], "total": 0}


@router.get("/registry")
def get_tool_registry():
    """List all registered tools in the harness."""
    from services.agent.registry import create_default_registry
    registry = create_default_registry()
    tools = registry.list_all()
    return {
        "tools": [
            {
                "name": t.name,
                "version": t.version,
                "description": t.description,
                "side_effects": t.side_effects,
                "trust_tier": t.trust_tier,
                "tags": t.tags,
                "timeout_ms": t.timeout_ms,
                "retryable": t.retryable,
            }
            for t in tools
        ],
        "total": len(tools),
    }
