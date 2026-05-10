"""Agent Harness API -- events, sessions, registry, permissions."""

from __future__ import annotations

import logging
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, Field
from typing import Optional

from api.deps import get_db, require_role
from db import Database

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agent", tags=["agent"])
nudge_router = APIRouter(prefix="/agents", tags=["agents-nudge"])  # BE-5


# BE-3 — Phase 8 verification mandates the noun form for the public
# agent identity. Today event producers tag events with codename slugs
# like ``research_agent`` / ``data_steward``; this map normalises them
# to the three external names PB-201's AgentRail cares about.
_AGENT_NAME_MAP: dict[str, str] = {
    # Strategist — formulates strategy / runs simulations / drafts briefs
    "research_agent": "strategist",
    "researcher": "strategist",
    "strategist": "strategist",
    "war_game": "strategist",
    "framing_triggers": "strategist",
    # Curator — curates data, marks outcomes, scores evidence
    "data_steward": "curator",
    "steward": "curator",
    "curator": "curator",
    "feedback_loops": "curator",
    "learning_service": "curator",
    # Sentinel — sensing / monitoring / conversation_memory + everything else
    "conversation_memory": "sentinel",
    "memory": "sentinel",
    "sensing": "sentinel",
    "sentinel": "sentinel",
    "monitor": "sentinel",
}

VALID_AGENTS = ("sentinel", "strategist", "curator")


def _normalize_agent_name(agent_type: str | None) -> str:
    """Map a code-side agent_type slug to the public noun form.

    Unknown / empty → "sentinel" so events are never tagged as
    ``None`` (the AgentRail can't render a None tile)."""
    if not agent_type:
        return "sentinel"
    key = str(agent_type).lower()
    if key in _AGENT_NAME_MAP:
        return _AGENT_NAME_MAP[key]
    # Substring match for prefixed variants like research_agent_v2
    for slug, name in _AGENT_NAME_MAP.items():
        if slug in key:
            return name
    return "sentinel"


@router.get("/events")
def get_agent_events(
    event_type: Optional[str] = Query(None),
    agent_type: Optional[str] = Query(None),
    agent: Optional[str] = Query(None, description="sentinel|strategist|curator"),
    limit: int = Query(50, ge=1, le=200),
    db: Database = Depends(get_db),
):
    """Get recent agent events from the event stream.

    BE-3 — every returned event carries a non-null `agent` field with
    one of {sentinel, strategist, curator}. The legacy `agent_type`
    field stays in the payload for back-compat. Filtering by `agent`
    (the noun form) is preferred; `agent_type` filter is still honoured
    for callers that know the slug.
    """
    if agent and agent not in VALID_AGENTS:
        return {"events": [], "total": 0,
                "error": f"agent must be one of {VALID_AGENTS}"}
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
        events = []
        for r in rows:
            ev = dict(r)
            ev["agent"] = _normalize_agent_name(ev.get("agent_type"))
            events.append(ev)
        # Apply the optional public-name filter AFTER normalization so a
        # query like ?agent=curator catches events whose raw agent_type
        # is "data_steward".
        if agent:
            events = [e for e in events if e["agent"] == agent]
        return {"events": events, "total": len(events)}
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


# ════════════════════════════════════════════════════════════════════
# BE-5 · POST /agents/{agent}/nudge
# ════════════════════════════════════════════════════════════════════

class NudgeBody(BaseModel):
    intent: str = Field(min_length=1, max_length=80)
    payload: dict = Field(default_factory=dict)


@nudge_router.post("/{agent}/nudge")
def nudge_agent(
    body: NudgeBody,
    agent: str = Path(..., description="sentinel|strategist|curator"),
    user: dict = Depends(require_role("uploader")),
    db: Database = Depends(get_db),
):
    """Send a typed nudge to a specific agent.

    Per BE-5: each call is logged to ``agent_events`` with the intent
    in metadata; identical nudges from the same actor within 5 min
    are deduped (returns the prior event_id with deduped=true).
    """
    if agent not in VALID_AGENTS:
        raise HTTPException(404, f"unknown agent: {agent!r}")
    from services.agent import nudge_intents as svc

    try:
        result = svc.dispatch(
            db,
            agent=agent,
            intent=body.intent,
            payload=body.payload or {},
            actor=str(user.get("id") or user.get("email") or "anonymous"),
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return result.to_dict()


@nudge_router.get("/intents")
def list_nudge_intents(agent: Optional[str] = Query(None)):
    """Return the nudge-intent registry. Frontend renders the menu
    from this so nothing is hard-coded UI-side."""
    from services.agent import nudge_intents as svc
    return {"intents": svc.list_intents(agent)}
