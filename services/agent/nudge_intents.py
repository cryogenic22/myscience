"""BE-5 — Per-agent nudge intent registry + dispatcher.

PB-203's NudgeMenu lets the user address an agent ("Sentinel, watch
this entity", "Strategist, rerun the simulation"). This module
defines the typed intents per agent and dispatches them.

Each intent is a callable that takes the agent's existing service
state + a payload and produces a side effect (logged via the event
stream so the AgentRail reflects it).

Idempotency: same nudge intent + payload from the same caller within
``IDEMPOTENCY_WINDOW_S`` is a no-op (returns the cached result).
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


IDEMPOTENCY_WINDOW_S = 5 * 60  # 5 minutes per BE-5 acceptance


_INTENTS: dict[str, dict] = {
    "sentinel": {
        "watch_entity": {
            "description": "Add an entity to the watchlist",
            "required": ["entity_type", "entity_id"],
        },
        "ignore_source": {
            "description": "Suppress signals from a specific source",
            "required": ["source_id"],
        },
        "boost_source": {
            "description": "Increase weight of a specific source for materiality scoring",
            "required": ["source_id"],
        },
    },
    "strategist": {
        "rerun_simulation": {
            "description": "Re-execute a war-room simulation with current evidence",
            "required": ["war_room_id"],
        },
        "draft_counter_recommendation": {
            "description": "Generate a counter-recommendation for a brief",
            "required": ["brief_id"],
        },
    },
    "curator": {
        "explain_score": {
            "description": "Produce a human-readable explanation of a materiality / quality score",
            "required": ["signal_id"],
        },
        "mark_outcome_verified": {
            "description": "Mark a decision outcome as verified by the curator",
            "required": ["decision_id"],
        },
    },
}


def list_intents(agent: str | None = None) -> dict:
    """Return the public intent registry, optionally scoped to one agent."""
    if agent is None:
        return {a: dict(intents) for a, intents in _INTENTS.items()}
    return dict(_INTENTS.get(agent, {}))


def validate(agent: str, intent: str, payload: dict | None) -> None:
    """Raise ValueError unless agent/intent/payload satisfies the registry."""
    if agent not in _INTENTS:
        raise ValueError(f"unknown agent: {agent!r}")
    if intent not in _INTENTS[agent]:
        raise ValueError(
            f"intent {intent!r} is not valid for agent {agent!r}; "
            f"allowed: {sorted(_INTENTS[agent])}"
        )
    required = _INTENTS[agent][intent]["required"]
    if not payload:
        payload = {}
    missing = [k for k in required if not payload.get(k)]
    if missing:
        raise ValueError(
            f"nudge {agent}.{intent} missing required payload keys: {missing}"
        )


# ───────────────────────────────────────────────────────────────────
# Dispatcher — single entry point used by the route
# ───────────────────────────────────────────────────────────────────

@dataclass
class NudgeResult:
    accepted: bool
    intent: str
    agent: str
    event_id: Optional[str]
    deduped: bool
    message: str

    def to_dict(self) -> dict:
        return {
            "accepted": self.accepted,
            "intent": self.intent,
            "agent": self.agent,
            "event_id": self.event_id,
            "deduped": self.deduped,
            "message": self.message,
        }


# Per-process idempotency cache. Key is a hash of (agent, intent,
# payload, actor); value is (timestamp, NudgeResult). For multi-worker
# deploys this becomes per-worker — the agent_events INSERT serves as
# the durable record. The cache is a best-effort optimisation.
_IDEMPOTENCY_CACHE: dict[str, tuple[float, NudgeResult]] = {}


def _idempotency_key(*, agent: str, intent: str, payload: dict, actor: str) -> str:
    blob = json.dumps(
        {"agent": agent, "intent": intent, "payload": payload, "actor": actor},
        sort_keys=True,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def dispatch(
    db: Any,
    *,
    agent: str,
    intent: str,
    payload: dict | None,
    actor: str = "anonymous",
    now: Optional[float] = None,
) -> NudgeResult:
    """Validate, dedup, log to agent_events, return a NudgeResult.

    Side effect is logged-only here; downstream agent services pick up
    the event and act on it (no synchronous coupling so a slow
    research_agent doesn't 503 the user click).
    """
    validate(agent, intent, payload or {})
    payload = payload or {}
    eff_now = float(now) if now is not None else time.time()

    cache_key = _idempotency_key(
        agent=agent, intent=intent, payload=payload, actor=actor,
    )
    cached = _IDEMPOTENCY_CACHE.get(cache_key)
    if cached and (eff_now - cached[0]) < IDEMPOTENCY_WINDOW_S:
        prev = cached[1]
        return NudgeResult(
            accepted=True, intent=intent, agent=agent,
            event_id=prev.event_id, deduped=True,
            message="idempotent — same nudge within 5 min",
        )

    event_id = None
    try:
        row = db.fetch_one(
            """INSERT INTO agent_events
                   (id, session_id, event_type, agent_type, tool_name,
                    trust_tier, args_hash, result_status, metadata, created_at)
               VALUES (gen_random_uuid(), %s, %s, %s, %s, %s, %s, %s, %s::jsonb, NOW())
               RETURNING id::text AS id""",
            [
                actor,
                "nudge",
                agent,
                intent,
                None,
                "ok",
                cache_key[:16],
                json.dumps({"nudge_intent": intent,
                            "agent": agent,
                            "actor": actor,
                            "payload": payload}),
            ],
        )
        if row:
            event_id = row.get("id")
    except Exception as exc:
        logger.warning("nudge.dispatch agent_events insert failed: %s", exc)

    result = NudgeResult(
        accepted=True,
        intent=intent,
        agent=agent,
        event_id=event_id,
        deduped=False,
        message=f"{agent}.{intent} acknowledged",
    )
    _IDEMPOTENCY_CACHE[cache_key] = (eff_now, result)
    return result
