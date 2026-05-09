"""SPEC_023 — Decision Brief service.

A Decision Brief is the canonical handoff from sensing → simulation. It owns:
  - the question being asked (in plain language)
  - structured options (≥2 to leave human_review)
  - stakeholders, time horizon, success criteria
  - an explicit state machine across 8 stages
  - a complete state-transition audit log

The service enforces all state-machine and option-count invariants. The
DB layer enforces type/value constraints (CHECK on state name, ordinal ≥1,
confidence_to_proceed ∈ [0,1]).
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────
# State machine
# ────────────────────────────────────────────────────────────────────

class BriefState(str, Enum):
    DRAFT = "draft"
    HUMAN_REVIEW = "human_review"
    SIMULATION_PENDING = "simulation_pending"
    SIMULATION_COMPLETE = "simulation_complete"
    DECISION_PENDING = "decision_pending"
    COMMITTED = "committed"
    IN_REVIEW = "in_review"
    CLOSED = "closed"


# Per-state allowed forward transitions. Closed is terminal.
LEGAL_TRANSITIONS: dict[BriefState, set[BriefState]] = {
    BriefState.DRAFT:               {BriefState.HUMAN_REVIEW, BriefState.CLOSED},
    BriefState.HUMAN_REVIEW:        {BriefState.DRAFT, BriefState.SIMULATION_PENDING, BriefState.CLOSED},
    BriefState.SIMULATION_PENDING:  {BriefState.SIMULATION_COMPLETE, BriefState.HUMAN_REVIEW},
    BriefState.SIMULATION_COMPLETE: {BriefState.DECISION_PENDING, BriefState.HUMAN_REVIEW},
    BriefState.DECISION_PENDING:    {BriefState.COMMITTED, BriefState.HUMAN_REVIEW},
    BriefState.COMMITTED:           {BriefState.IN_REVIEW},
    BriefState.IN_REVIEW:           {BriefState.CLOSED},
    BriefState.CLOSED:              set(),
}

# Editable fields (PATCH allowed) only in these states.
EDITABLE_STATES = {BriefState.DRAFT, BriefState.HUMAN_REVIEW}

VALID_TRIGGER_KINDS = {"manual", "threshold", "cluster", "calendar"}


# ────────────────────────────────────────────────────────────────────
# Domain dataclasses
# ────────────────────────────────────────────────────────────────────

@dataclass
class DecisionBriefOption:
    option_id: str
    brief_id: str
    ordinal: int
    label: str
    description: Optional[str] = None
    predicted_outcome: Optional[str] = None
    cost_estimate: Optional[str] = None
    risk_notes: Optional[str] = None
    created_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            "option_id": str(self.option_id),
            "brief_id": str(self.brief_id),
            "ordinal": self.ordinal,
            "label": self.label,
            "description": self.description,
            "predicted_outcome": self.predicted_outcome,
            "cost_estimate": self.cost_estimate,
            "risk_notes": self.risk_notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


@dataclass
class StateLogEntry:
    log_id: str
    brief_id: str
    from_state: Optional[str]
    to_state: str
    actor_user_id: Optional[str]
    reason: Optional[str]
    transitioned_at: datetime

    def to_dict(self) -> dict:
        return {
            "log_id": str(self.log_id),
            "brief_id": str(self.brief_id),
            "from_state": self.from_state,
            "to_state": self.to_state,
            "actor_user_id": str(self.actor_user_id) if self.actor_user_id else None,
            "reason": self.reason,
            "transitioned_at": self.transitioned_at.isoformat() if self.transitioned_at else None,
        }


@dataclass
class DecisionBrief:
    brief_id: str
    question: str
    trigger_kind: str
    trigger_signal_ids: list[str] = field(default_factory=list)
    trigger_metadata: dict = field(default_factory=dict)
    stakeholders: list[str] = field(default_factory=list)
    time_horizon_days: Optional[int] = None
    evidence_refs: list[dict] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    success_criteria: Optional[str] = None
    confidence_to_proceed: Optional[float] = None
    state: str = BriefState.DRAFT.value
    owner_user_id: Optional[str] = None
    war_room_id: Optional[str] = None
    decision_id: Optional[str] = None
    archived_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    options: list[DecisionBriefOption] = field(default_factory=list)
    state_log: list[StateLogEntry] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "brief_id": str(self.brief_id),
            "question": self.question,
            "trigger_kind": self.trigger_kind,
            "trigger_signal_ids": [str(s) for s in (self.trigger_signal_ids or [])],
            "trigger_metadata": self.trigger_metadata or {},
            "stakeholders": list(self.stakeholders or []),
            "time_horizon_days": self.time_horizon_days,
            "evidence_refs": list(self.evidence_refs or []),
            "constraints": list(self.constraints or []),
            "success_criteria": self.success_criteria,
            "confidence_to_proceed": self.confidence_to_proceed,
            "state": self.state,
            "owner_user_id": str(self.owner_user_id) if self.owner_user_id else None,
            "war_room_id": str(self.war_room_id) if self.war_room_id else None,
            "decision_id": str(self.decision_id) if self.decision_id else None,
            "archived_at": self.archived_at.isoformat() if self.archived_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "options": [o.to_dict() for o in self.options],
            "state_log": [s.to_dict() for s in self.state_log],
        }


# ────────────────────────────────────────────────────────────────────
# Errors raised by service for the route to translate into HTTP codes
# ────────────────────────────────────────────────────────────────────

class BriefNotFound(Exception):
    pass


class InvalidStateTransition(Exception):
    """Illegal state machine transition; route returns 409."""
    pass


class BriefImmutable(Exception):
    """Edit attempted on brief in a non-editable state; route returns 409."""
    pass


class InsufficientOptions(Exception):
    """Transition to simulation_pending requires ≥2 options; route returns 409."""
    pass


class InvalidTriggerKind(Exception):
    pass


# ────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────

def _row_to_brief(row: dict, options: list[DecisionBriefOption] | None = None,
                  state_log: list[StateLogEntry] | None = None) -> DecisionBrief:
    """Hydrate a brief from a DB row + optional eagerly-loaded children."""

    def _parse_jsonb(v, default):
        if v is None:
            return default
        if isinstance(v, (list, dict)):
            return v
        if isinstance(v, str):
            try:
                return json.loads(v)
            except (TypeError, ValueError):
                return default
        return default

    def _stringify_uuids(arr):
        if arr is None:
            return []
        # Some psycopg2 cursor configs return Postgres array literals as
        # the string "{}" or "{uuid1,uuid2}" instead of a Python list.
        # Detect and parse those rather than splitting char-by-char (which
        # would yield ["{", "}"] for an empty array).
        if isinstance(arr, str):
            stripped = arr.strip()
            if stripped in ("", "{}"):
                return []
            if stripped.startswith("{") and stripped.endswith("}"):
                inner = stripped[1:-1]
                if not inner:
                    return []
                return [x.strip().strip('"') for x in inner.split(",") if x.strip()]
            return []
        if not arr:
            return []
        return [str(x) for x in arr]

    return DecisionBrief(
        brief_id=str(row["brief_id"]),
        question=row["question"],
        trigger_kind=row.get("trigger_kind") or "manual",
        trigger_signal_ids=_stringify_uuids(row.get("trigger_signal_ids") or []),
        trigger_metadata=_parse_jsonb(row.get("trigger_metadata"), {}),
        stakeholders=list(row.get("stakeholders") or []),
        time_horizon_days=row.get("time_horizon_days"),
        evidence_refs=_parse_jsonb(row.get("evidence_refs"), []),
        constraints=list(row.get("constraints") or []),
        success_criteria=row.get("success_criteria"),
        confidence_to_proceed=row.get("confidence_to_proceed"),
        state=row.get("state") or BriefState.DRAFT.value,
        owner_user_id=str(row["owner_user_id"]) if row.get("owner_user_id") else None,
        war_room_id=str(row["war_room_id"]) if row.get("war_room_id") else None,
        decision_id=str(row["decision_id"]) if row.get("decision_id") else None,
        archived_at=row.get("archived_at"),
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
        options=options or [],
        state_log=state_log or [],
    )


def _validate_trigger_kind(kind: str) -> None:
    if kind not in VALID_TRIGGER_KINDS:
        raise InvalidTriggerKind(
            f"trigger_kind must be one of {sorted(VALID_TRIGGER_KINDS)}, got {kind!r}"
        )


def _validate_evidence_refs(refs: list[dict]) -> None:
    """Each evidence ref must have a `type` and `id`. Type must be a known kind."""
    if refs is None:
        return
    valid_types = {"kbq_view", "signal", "entity", "document", "war_room", "trial", "publication"}
    for i, r in enumerate(refs):
        if not isinstance(r, dict):
            raise ValueError(f"evidence_refs[{i}] must be an object, got {type(r).__name__}")
        if "type" not in r or "id" not in r:
            raise ValueError(f"evidence_refs[{i}] missing required keys 'type' and 'id'")
        if r["type"] not in valid_types:
            raise ValueError(
                f"evidence_refs[{i}].type must be one of {sorted(valid_types)}, got {r['type']!r}"
            )


# ────────────────────────────────────────────────────────────────────
# Service
# ────────────────────────────────────────────────────────────────────

class DecisionBriefService:
    """Stateless service; pass the DB on each call. Mirrors patterns used by
    other services in this codebase (no instance-level DB binding)."""

    # ── Create ──

    @staticmethod
    def create_draft(
        db,
        *,
        question: str,
        trigger_kind: str = "manual",
        trigger_signal_ids: Optional[list[str]] = None,
        trigger_metadata: Optional[dict] = None,
        stakeholders: Optional[list[str]] = None,
        time_horizon_days: Optional[int] = None,
        evidence_refs: Optional[list[dict]] = None,
        constraints: Optional[list[str]] = None,
        success_criteria: Optional[str] = None,
        confidence_to_proceed: Optional[float] = None,
        owner_user_id: Optional[str] = None,
        war_room_id: Optional[str] = None,
        actor_user_id: Optional[str] = None,
    ) -> DecisionBrief:
        """Create a brief in `draft` state. Raises:
          - ValueError on bad evidence_refs / constraints
          - InvalidTriggerKind on bad trigger_kind
          - DB-level CHECK violations propagate as DB errors
        """
        _validate_trigger_kind(trigger_kind)
        _validate_evidence_refs(evidence_refs or [])
        if not question or not question.strip():
            raise ValueError("question must be non-empty")
        if confidence_to_proceed is not None:
            if not (0.0 <= confidence_to_proceed <= 1.0):
                raise ValueError("confidence_to_proceed must be in [0, 1]")

        sig_ids = trigger_signal_ids or []
        # Pre-stringify UUIDs so MagicMock-fed tests don't choke on UUID objects
        sig_ids_clean = [str(s) for s in sig_ids if s]

        row = db.fetch_one(
            """
            INSERT INTO decision_briefs (
                question, trigger_kind, trigger_signal_ids, trigger_metadata,
                stakeholders, time_horizon_days, evidence_refs, constraints,
                success_criteria, confidence_to_proceed, owner_user_id, war_room_id
            ) VALUES (
                %s, %s, %s::uuid[], %s::jsonb, %s, %s, %s::jsonb, %s, %s, %s, %s, %s
            )
            RETURNING brief_id, question, trigger_kind, trigger_signal_ids,
                      trigger_metadata, stakeholders, time_horizon_days,
                      evidence_refs, constraints, success_criteria,
                      confidence_to_proceed, state, owner_user_id, war_room_id,
                      decision_id, archived_at, created_at, updated_at
            """,
            (
                question.strip(),
                trigger_kind,
                sig_ids_clean,
                json.dumps(trigger_metadata or {}),
                stakeholders or [],
                time_horizon_days,
                json.dumps(evidence_refs or []),
                constraints or [],
                success_criteria,
                confidence_to_proceed,
                owner_user_id,
                war_room_id,
            ),
        )
        if not row:
            raise RuntimeError("Insert returned no row")

        brief = _row_to_brief(row)
        # Seed initial state log
        DecisionBriefService._log_transition(
            db,
            brief_id=brief.brief_id,
            from_state=None,
            to_state=brief.state,
            actor_user_id=actor_user_id,
            reason="Created",
        )
        # Reload to include the log entry
        return DecisionBriefService.get(db, brief.brief_id) or brief

    # ── Read ──

    @staticmethod
    def get(db, brief_id: str, *, include_archived: bool = False) -> Optional[DecisionBrief]:
        """Get a brief with its options + state log. Returns None if not found
        (or if archived and include_archived=False)."""
        row = db.fetch_one(
            """
            SELECT brief_id, question, trigger_kind, trigger_signal_ids,
                   trigger_metadata, stakeholders, time_horizon_days,
                   evidence_refs, constraints, success_criteria,
                   confidence_to_proceed, state, owner_user_id, war_room_id,
                   decision_id, archived_at, created_at, updated_at
              FROM decision_briefs
             WHERE brief_id::text = %s
            """,
            (str(brief_id),),
        )
        if not row:
            return None
        if row.get("archived_at") and not include_archived:
            return None

        opt_rows = db.fetch_all(
            """
            SELECT option_id, brief_id, ordinal, label, description,
                   predicted_outcome, cost_estimate, risk_notes, created_at
              FROM decision_brief_options
             WHERE brief_id::text = %s
             ORDER BY ordinal ASC
            """,
            (str(brief_id),),
        ) or []
        options = [
            DecisionBriefOption(
                option_id=str(o["option_id"]),
                brief_id=str(o["brief_id"]),
                ordinal=o["ordinal"],
                label=o["label"],
                description=o.get("description"),
                predicted_outcome=o.get("predicted_outcome"),
                cost_estimate=o.get("cost_estimate"),
                risk_notes=o.get("risk_notes"),
                created_at=o.get("created_at"),
            )
            for o in opt_rows
        ]

        log_rows = db.fetch_all(
            """
            SELECT log_id, brief_id, from_state, to_state, actor_user_id,
                   reason, transitioned_at
              FROM decision_brief_state_log
             WHERE brief_id::text = %s
             ORDER BY transitioned_at ASC
            """,
            (str(brief_id),),
        ) or []
        state_log = [
            StateLogEntry(
                log_id=str(l["log_id"]),
                brief_id=str(l["brief_id"]),
                from_state=l.get("from_state"),
                to_state=l["to_state"],
                actor_user_id=str(l["actor_user_id"]) if l.get("actor_user_id") else None,
                reason=l.get("reason"),
                transitioned_at=l.get("transitioned_at"),
            )
            for l in log_rows
        ]

        return _row_to_brief(row, options=options, state_log=state_log)

    @staticmethod
    def list(
        db,
        *,
        state: Optional[str] = None,
        owner_user_id: Optional[str] = None,
        trigger_kind: Optional[str] = None,
        include_archived: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[DecisionBrief]:
        """List briefs (without options/state_log eagerly loaded — those come
        from `get`). Filters compose with AND semantics."""
        if limit < 1 or limit > 500:
            raise ValueError("limit must be in [1, 500]")

        where = ["1=1"]
        params: list[Any] = []
        if state is not None:
            where.append("state = %s")
            params.append(state)
        if owner_user_id is not None:
            where.append("owner_user_id::text = %s")
            params.append(str(owner_user_id))
        if trigger_kind is not None:
            _validate_trigger_kind(trigger_kind)
            where.append("trigger_kind = %s")
            params.append(trigger_kind)
        if not include_archived:
            where.append("archived_at IS NULL")

        params.extend([limit, offset])
        rows = db.fetch_all(
            f"""
            SELECT brief_id, question, trigger_kind, trigger_signal_ids,
                   trigger_metadata, stakeholders, time_horizon_days,
                   evidence_refs, constraints, success_criteria,
                   confidence_to_proceed, state, owner_user_id, war_room_id,
                   decision_id, archived_at, created_at, updated_at
              FROM decision_briefs
             WHERE {' AND '.join(where)}
             ORDER BY created_at DESC
             LIMIT %s OFFSET %s
            """,
            tuple(params),
        ) or []
        return [_row_to_brief(r) for r in rows]

    # ── Mutate (PATCH) ──

    @staticmethod
    def update(
        db,
        brief_id: str,
        *,
        question: Optional[str] = None,
        stakeholders: Optional[list[str]] = None,
        time_horizon_days: Optional[int] = None,
        evidence_refs: Optional[list[dict]] = None,
        constraints: Optional[list[str]] = None,
        success_criteria: Optional[str] = None,
        confidence_to_proceed: Optional[float] = None,
    ) -> DecisionBrief:
        """Edit fields. Only allowed in `draft` or `human_review`."""
        existing = DecisionBriefService.get(db, brief_id)
        if not existing:
            raise BriefNotFound(brief_id)
        if BriefState(existing.state) not in EDITABLE_STATES:
            raise BriefImmutable(
                f"Brief in state {existing.state!r} is immutable; "
                f"transition to {BriefState.DRAFT.value!r} or {BriefState.HUMAN_REVIEW.value!r} first"
            )
        if evidence_refs is not None:
            _validate_evidence_refs(evidence_refs)
        if confidence_to_proceed is not None:
            if not (0.0 <= confidence_to_proceed <= 1.0):
                raise ValueError("confidence_to_proceed must be in [0, 1]")

        sets: list[str] = []
        params: list[Any] = []
        if question is not None:
            if not question.strip():
                raise ValueError("question must be non-empty")
            sets.append("question = %s")
            params.append(question.strip())
        if stakeholders is not None:
            sets.append("stakeholders = %s")
            params.append(stakeholders)
        if time_horizon_days is not None:
            sets.append("time_horizon_days = %s")
            params.append(time_horizon_days)
        if evidence_refs is not None:
            sets.append("evidence_refs = %s::jsonb")
            params.append(json.dumps(evidence_refs))
        if constraints is not None:
            sets.append("constraints = %s")
            params.append(constraints)
        if success_criteria is not None:
            sets.append("success_criteria = %s")
            params.append(success_criteria)
        if confidence_to_proceed is not None:
            sets.append("confidence_to_proceed = %s")
            params.append(confidence_to_proceed)

        if not sets:
            return existing

        params.append(str(brief_id))
        db.execute(
            f"UPDATE decision_briefs SET {', '.join(sets)} WHERE brief_id::text = %s",
            tuple(params),
        )
        return DecisionBriefService.get(db, brief_id) or existing

    # ── State machine ──

    @staticmethod
    def transition(
        db,
        brief_id: str,
        to_state: str,
        *,
        actor_user_id: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> DecisionBrief:
        """Transition a brief to a new state. Enforces:
          - LEGAL_TRANSITIONS membership (raises InvalidStateTransition)
          - simulation_pending requires ≥2 options (raises InsufficientOptions)
          - committed requires decision_id to be set (raises ValueError)
        """
        existing = DecisionBriefService.get(db, brief_id)
        if not existing:
            raise BriefNotFound(brief_id)

        try:
            from_state_enum = BriefState(existing.state)
            to_state_enum = BriefState(to_state)
        except ValueError as e:
            raise InvalidStateTransition(f"Unknown state: {e}")

        if to_state_enum not in LEGAL_TRANSITIONS[from_state_enum]:
            raise InvalidStateTransition(
                f"Illegal transition: {existing.state!r} → {to_state!r}. "
                f"Allowed from {existing.state!r}: "
                f"{sorted(s.value for s in LEGAL_TRANSITIONS[from_state_enum])}"
            )

        # Invariants gating specific target states
        if to_state_enum is BriefState.SIMULATION_PENDING and len(existing.options) < 2:
            raise InsufficientOptions(
                f"Transition to {BriefState.SIMULATION_PENDING.value} requires ≥2 options "
                f"(brief has {len(existing.options)})"
            )
        if to_state_enum is BriefState.COMMITTED and not existing.decision_id:
            raise ValueError(
                "Transition to committed requires decision_id to be set on the brief; "
                "set via attach_decision() before transitioning"
            )

        db.execute(
            "UPDATE decision_briefs SET state = %s WHERE brief_id::text = %s",
            (to_state_enum.value, str(brief_id)),
        )
        DecisionBriefService._log_transition(
            db,
            brief_id=brief_id,
            from_state=existing.state,
            to_state=to_state_enum.value,
            actor_user_id=actor_user_id,
            reason=reason,
        )
        return DecisionBriefService.get(db, brief_id) or existing

    @staticmethod
    def archive(db, brief_id: str, *, actor_user_id: Optional[str] = None) -> DecisionBrief:
        """Archive a brief (set archived_at). Only legal for non-terminal,
        non-committed states. Archived briefs are read-only."""
        existing = DecisionBriefService.get(db, brief_id, include_archived=True)
        if not existing:
            raise BriefNotFound(brief_id)
        if existing.archived_at is not None:
            return existing
        terminal_or_committed = {BriefState.COMMITTED, BriefState.IN_REVIEW, BriefState.CLOSED}
        if BriefState(existing.state) in terminal_or_committed:
            raise BriefImmutable(
                f"Brief in state {existing.state!r} cannot be archived; only abandon by "
                f"transitioning to closed"
            )
        db.execute(
            "UPDATE decision_briefs SET archived_at = NOW() WHERE brief_id::text = %s",
            (str(brief_id),),
        )
        DecisionBriefService._log_transition(
            db,
            brief_id=brief_id,
            from_state=existing.state,
            to_state=existing.state,
            actor_user_id=actor_user_id,
            reason="archived",
        )
        return DecisionBriefService.get(db, brief_id, include_archived=True) or existing

    @staticmethod
    def attach_decision(db, brief_id: str, decision_id: str) -> DecisionBrief:
        """Bind a Decision (from /decisions/from-round) to this brief. Used
        between transition→decision_pending and transition→committed."""
        existing = DecisionBriefService.get(db, brief_id)
        if not existing:
            raise BriefNotFound(brief_id)
        db.execute(
            "UPDATE decision_briefs SET decision_id = %s WHERE brief_id::text = %s",
            (str(decision_id), str(brief_id)),
        )
        return DecisionBriefService.get(db, brief_id) or existing

    # ── Options ──

    @staticmethod
    def add_option(
        db,
        brief_id: str,
        *,
        label: str,
        description: Optional[str] = None,
        predicted_outcome: Optional[str] = None,
        cost_estimate: Optional[str] = None,
        risk_notes: Optional[str] = None,
    ) -> DecisionBriefOption:
        """Append an option. Ordinal is auto-assigned (max+1).
        Only allowed in editable states."""
        existing = DecisionBriefService.get(db, brief_id)
        if not existing:
            raise BriefNotFound(brief_id)
        if BriefState(existing.state) not in EDITABLE_STATES:
            raise BriefImmutable(
                f"Cannot add option in state {existing.state!r}"
            )
        if not label or not label.strip():
            raise ValueError("option.label must be non-empty")

        next_ordinal = (max((o.ordinal for o in existing.options), default=0)) + 1
        row = db.fetch_one(
            """
            INSERT INTO decision_brief_options (
                brief_id, ordinal, label, description, predicted_outcome,
                cost_estimate, risk_notes
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING option_id, brief_id, ordinal, label, description,
                      predicted_outcome, cost_estimate, risk_notes, created_at
            """,
            (
                str(brief_id),
                next_ordinal,
                label.strip(),
                description,
                predicted_outcome,
                cost_estimate,
                risk_notes,
            ),
        )
        if not row:
            raise RuntimeError("Insert returned no row")
        return DecisionBriefOption(
            option_id=str(row["option_id"]),
            brief_id=str(row["brief_id"]),
            ordinal=row["ordinal"],
            label=row["label"],
            description=row.get("description"),
            predicted_outcome=row.get("predicted_outcome"),
            cost_estimate=row.get("cost_estimate"),
            risk_notes=row.get("risk_notes"),
            created_at=row.get("created_at"),
        )

    @staticmethod
    def remove_option(db, brief_id: str, option_id: str) -> None:
        """Remove an option. Only allowed in editable states."""
        existing = DecisionBriefService.get(db, brief_id)
        if not existing:
            raise BriefNotFound(brief_id)
        if BriefState(existing.state) not in EDITABLE_STATES:
            raise BriefImmutable(
                f"Cannot remove option in state {existing.state!r}"
            )
        db.execute(
            """
            DELETE FROM decision_brief_options
             WHERE brief_id::text = %s AND option_id::text = %s
            """,
            (str(brief_id), str(option_id)),
        )

    # ── Internal ──

    @staticmethod
    def _log_transition(
        db,
        *,
        brief_id: str,
        from_state: Optional[str],
        to_state: str,
        actor_user_id: Optional[str],
        reason: Optional[str],
    ) -> None:
        db.execute(
            """
            INSERT INTO decision_brief_state_log (
                brief_id, from_state, to_state, actor_user_id, reason
            ) VALUES (%s, %s, %s, %s, %s)
            """,
            (str(brief_id), from_state, to_state, actor_user_id, reason),
        )
