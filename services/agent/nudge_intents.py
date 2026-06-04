"""PB-203 — agent nudge intents: address an agent with a bounded action.

Each of the three named agents (Sentinel · Strategist · Curator) exposes a
small, fixed set of nudge intents a reviewer can issue from the UI. A nudge is
an *instruction*, not a synchronous RPC: the agents run as background loops
(scheduler tasks), so a nudge is RECORDED (queued, append-only) for the agent to
consume on its next pass — honest about the fact that the work happens
out-of-band rather than faking an immediate result.

This registry is the single source of truth the API and the frontend NudgeMenu
both read, so the menu can never offer an intent the backend would reject.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from typing import Optional

logger = logging.getLogger(__name__)


class NudgeError(ValueError):
    """Raised when a nudge names an unknown agent/intent or omits a required
    target. Carried to the API as a 400."""


@dataclass(frozen=True)
class NudgeIntent:
    key: str
    label: str
    description: str
    requires_target: bool = False
    # What KIND of thing the target identifies, so the UI can prompt for it.
    target_kind: Optional[str] = None  # entity|signal|source|scenario|outcome

    def to_dict(self) -> dict:
        return asdict(self)


# Intents mirror PB-203 exactly. Every intent points at a concrete object so the
# queued nudge is actionable (no free-floating "do something" requests).
AGENT_INTENTS: dict[str, tuple[NudgeIntent, ...]] = {
    "sentinel": (
        NudgeIntent("watch", "Watch",
                    "Prioritise sensing on this entity.", True, "entity"),
        NudgeIntent("ignore", "Ignore",
                    "Mute a noisy signal so it stops surfacing.", True, "signal"),
        NudgeIntent("boost_source", "Boost source",
                    "Raise a source's trust weighting in scoring.", True, "source"),
    ),
    "strategist": (
        NudgeIntent("rerun_sim", "Re-run simulation",
                    "Re-run the war-game on this scenario.", True, "scenario"),
        NudgeIntent("draft_counter", "Draft counter-move",
                    "Draft a counter-recommendation for this scenario.", True, "scenario"),
    ),
    "curator": (
        NudgeIntent("explain_score", "Explain score",
                    "Explain how this evidence score was derived.", True, "signal"),
        NudgeIntent("mark_outcome_verified", "Mark outcome verified",
                    "Confirm a predicted outcome actually occurred.", True, "outcome"),
    ),
}

VALID_AGENTS: tuple[str, ...] = tuple(AGENT_INTENTS.keys())
VALID_STATUSES = ("queued", "acknowledged", "done", "dismissed")


def list_intents(agent: str) -> list[NudgeIntent]:
    """The intents available for one agent ([] for an unknown agent)."""
    return list(AGENT_INTENTS.get((agent or "").lower(), ()))


def get_intent(agent: str, key: str) -> Optional[NudgeIntent]:
    target = (key or "").lower()
    for it in list_intents(agent):
        if it.key == target:
            return it
    return None


def validate_nudge(agent: str, intent_key: str,
                   target: Optional[dict] = None) -> NudgeIntent:
    """Return the resolved NudgeIntent, or raise NudgeError. Pure — the API and
    the persistence layer both gate on this so an invalid nudge never reaches
    the DB."""
    a = (agent or "").lower()
    if a not in AGENT_INTENTS:
        raise NudgeError(
            f"unknown agent '{agent}' (expected one of {', '.join(VALID_AGENTS)})")
    it = get_intent(a, intent_key)
    if it is None:
        offered = ", ".join(i.key for i in list_intents(a))
        raise NudgeError(f"agent '{a}' has no intent '{intent_key}' (offers: {offered})")
    if it.requires_target and not target:
        raise NudgeError(f"intent '{it.key}' requires a target ({it.target_kind})")
    return it


_INSERT_SQL = """
    INSERT INTO agent_nudges (agent, intent, target, note, status, created_by)
    VALUES (%s, %s, %s::jsonb, %s, 'queued', %s)
    RETURNING id, agent, intent, target, note, status, created_by, created_at
"""

_LIST_SQL = """
    SELECT id, agent, intent, target, note, status, created_by, created_at
      FROM agent_nudges
     {where}
     ORDER BY created_at DESC
     LIMIT %s
"""


def record_nudge(db, *, agent: str, intent_key: str,
                 target: Optional[dict] = None, note: Optional[str] = None,
                 created_by: str = "system") -> dict:
    """Validate then queue a nudge (append-only). Returns the persisted row.
    Raises NudgeError BEFORE any DB write when the nudge is invalid."""
    it = validate_nudge(agent, intent_key, target)
    row = db.fetch_one(
        _INSERT_SQL,
        [agent.lower(), it.key,
         json.dumps(target) if target is not None else None,
         note, created_by],
    )
    return dict(row) if row else {}


def list_nudges(db, agent: Optional[str] = None, limit: int = 20) -> list[dict]:
    """Recent queued nudges, newest first; optionally scoped to one agent."""
    if agent:
        sql = _LIST_SQL.format(where="WHERE agent = %s")
        params = [agent.lower(), limit]
    else:
        sql = _LIST_SQL.format(where="")
        params = [limit]
    try:
        return [dict(r) for r in db.fetch_all(sql, params)]
    except Exception:
        logger.exception("list_nudges failed")
        return []
