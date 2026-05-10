"""Agent Harness API -- events, sessions, registry, permissions."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from typing import Optional

from api.deps import get_db
from db import Database

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agent", tags=["agent"])
stream_router = APIRouter(prefix="/agents", tags=["agents"])  # BE-4


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
# BE-4 · GET /agents/stream — Server-Sent Events
# ════════════════════════════════════════════════════════════════════

DEFAULT_HEARTBEAT_S = 15
DEFAULT_POLL_S = 3
SSE_MAX_DURATION_S = 600  # 10-minute max stream so a stuck client doesn't pin a worker


def _serialize_event_for_sse(row: dict) -> dict:
    """Reshape an agent_events row for SSE consumption."""
    ts = row.get("created_at")
    iso = ts.isoformat() if hasattr(ts, "isoformat") else (ts or "")
    refs = []
    md = row.get("metadata") or {}
    if isinstance(md, str):
        try:
            md = json.loads(md)
        except (TypeError, ValueError):
            md = {}
    if isinstance(md, dict):
        for key in ("entity_refs", "entity_ref", "entity"):
            v = md.get(key)
            if isinstance(v, list):
                refs.extend(str(x) for x in v if x)
            elif isinstance(v, str):
                refs.append(v)
    return {
        "id":           str(row.get("id") or ""),
        "agent":        _normalize_agent_name(row.get("agent_type")),
        "agent_type":   row.get("agent_type"),
        "kind":         row.get("event_type"),
        "activity":     (md.get("activity") if isinstance(md, dict) else None) or row.get("tool_name") or "",
        "ts":           iso,
        "session_id":   row.get("session_id"),
        "result_status": row.get("result_status"),
        "entity_refs":  refs,
    }


@stream_router.get("/stream")
async def stream_events(
    since: Optional[str] = Query(None, description="ISO-8601 timestamp; only events created after"),
    agents: Optional[str] = Query(None, description="comma-separated subset of sentinel,strategist,curator"),
    db: Database = Depends(get_db),
):
    """SSE feed of agent events as they're persisted (BE-4 / PB-202).

    Heartbeats every ``DEFAULT_HEARTBEAT_S`` seconds keep the connection
    alive through proxies. Stream auto-closes after
    ``SSE_MAX_DURATION_S`` so a hung client doesn't pin a worker — the
    frontend's reconnect logic just opens a new stream.
    """
    requested_agents: set[str] | None = None
    if agents:
        requested_agents = {a.strip().lower() for a in agents.split(",") if a.strip()}
        bad = requested_agents - set(VALID_AGENTS)
        if bad:
            requested_agents = requested_agents - bad
            logger.info("stream_events: dropping unknown agents %s", sorted(bad))

    last_ts = since
    seen_ids: set[str] = set()

    async def event_gen():
        nonlocal last_ts, seen_ids
        start = time.monotonic()
        # Send an initial heartbeat so the client receives headers + first
        # byte immediately. Without this the TestClient (and some proxies)
        # block waiting for the first chunk of the stream.
        yield ": heartbeat\n\n"
        last_heartbeat = start
        while time.monotonic() - start < SSE_MAX_DURATION_S:
            try:
                params: list = []
                conditions: list[str] = []
                if last_ts:
                    conditions.append("created_at > %s")
                    params.append(last_ts)
                where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
                params.append(50)
                rows = db.fetch_all(
                    f"""SELECT id, session_id, event_type, agent_type, tool_name,
                               trust_tier, args_hash, result_status, metadata, created_at
                          FROM agent_events
                          {where}
                          ORDER BY created_at ASC
                          LIMIT %s""",
                    params,
                ) or []
                for r in rows:
                    eid = str(r.get("id") or "")
                    if eid and eid in seen_ids:
                        continue
                    if eid:
                        seen_ids.add(eid)
                    payload = _serialize_event_for_sse(r)
                    if requested_agents is not None and payload["agent"] not in requested_agents:
                        continue
                    yield f"data: {json.dumps(payload)}\n\n"
                    if r.get("created_at"):
                        last_ts = r["created_at"].isoformat() if hasattr(r["created_at"], "isoformat") else str(r["created_at"])
                # Heartbeat
                if time.monotonic() - last_heartbeat >= DEFAULT_HEARTBEAT_S:
                    yield ": heartbeat\n\n"
                    last_heartbeat = time.monotonic()
            except Exception as exc:
                logger.warning("stream_events poll failed: %s", exc)
            await asyncio.sleep(DEFAULT_POLL_S)
        # Tell the client to reconnect cleanly
        yield "event: close\ndata: max_duration_reached\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # nginx: don't buffer
            "Connection": "keep-alive",
        },
    )
