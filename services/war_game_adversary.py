"""SPEC_028 — Multi-Agent War-Game Adversaries.

Orchestrates structured adversary panels (Competitor / Payer / Regulator / KOL)
that react to each Decision Brief option across N rounds. Every action MUST
cite an evidence_record (DB-enforced via NOT NULL FK).

The orchestrator is parameterized by an `AdversaryReactor` strategy. The
default `StubReactor` produces deterministic grounded actions (good for
tests and a useful "what-if" baseline). The follow-up `LLMGatewayReactor`
will use SPEC-026 to generate real adversary text — same persistence path,
same grounding rule.
"""

from __future__ import annotations

import json
import logging
import uuid as _uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional, Protocol

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────
# Constants
# ────────────────────────────────────────────────────────────────────

VALID_KINDS = {"competitor", "payer", "regulator", "kol"}
VALID_ACTION_KINDS = {"react", "escalate", "wait", "concede", "threat", "counter", "partner"}
VALID_STATUSES = {"pending", "running", "complete", "failed", "cancelled"}

MAX_ROUNDS = 10
MAX_ADVERSARIES = 12
MAX_OPTIONS_PER_BRIEF = 10  # service-level cap; brief itself permits more

# Brief states in which a war-game can be started
ALLOWED_BRIEF_STATES_FOR_START = {"simulation_pending", "simulation_complete", "human_review"}


# ────────────────────────────────────────────────────────────────────
# Domain dataclasses
# ────────────────────────────────────────────────────────────────────

@dataclass
class AdversarySpec:
    """Caller-provided spec for one adversary in a war-game."""
    kind: str
    name: str
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    persona: dict = field(default_factory=dict)
    grounding_evidence_ids: list[str] = field(default_factory=list)


@dataclass
class WarGameAdversary:
    adversary_id: str
    run_id: str
    kind: str
    name: str
    entity_type: Optional[str]
    entity_id: Optional[str]
    persona: dict
    grounding_evidence_ids: list[str]
    created_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            "adversary_id": str(self.adversary_id),
            "run_id": str(self.run_id),
            "kind": self.kind,
            "name": self.name,
            "entity_type": self.entity_type,
            "entity_id": str(self.entity_id) if self.entity_id else None,
            "persona": self.persona or {},
            "grounding_evidence_ids": [str(e) for e in (self.grounding_evidence_ids or [])],
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


@dataclass
class WarGameAction:
    action_id: str
    run_id: str
    adversary_id: str
    option_id: str
    round_num: int
    action_kind: str
    action_text: str
    grounding_evidence_id: str
    grounding_precedent: Optional[str]
    confidence: Optional[float]
    llm_call_id: Optional[str] = None
    created_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            "action_id": str(self.action_id),
            "run_id": str(self.run_id),
            "adversary_id": str(self.adversary_id),
            "option_id": str(self.option_id),
            "round_num": self.round_num,
            "action_kind": self.action_kind,
            "action_text": self.action_text,
            "grounding_evidence_id": str(self.grounding_evidence_id),
            "grounding_precedent": self.grounding_precedent,
            "confidence": self.confidence,
            "llm_call_id": str(self.llm_call_id) if self.llm_call_id else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


@dataclass
class WarGameRun:
    run_id: str
    brief_id: str
    status: str
    num_rounds: int
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    failure_reason: Optional[str]
    summary: dict = field(default_factory=dict)
    started_by_user_id: Optional[str] = None
    adversaries: list[WarGameAdversary] = field(default_factory=list)
    actions: list[WarGameAction] = field(default_factory=list)

    def to_dict(self, *, include_actions: bool = False) -> dict:
        out = {
            "run_id": str(self.run_id),
            "brief_id": str(self.brief_id),
            "status": self.status,
            "num_rounds": self.num_rounds,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "failure_reason": self.failure_reason,
            "summary": self.summary or {},
            "started_by_user_id": str(self.started_by_user_id) if self.started_by_user_id else None,
            "adversaries": [a.to_dict() for a in self.adversaries],
        }
        if include_actions:
            out["actions"] = [a.to_dict() for a in self.actions]
        return out


@dataclass
class ReactorOutput:
    """What an AdversaryReactor.react() must return."""
    action_kind: str
    action_text: str
    grounding_evidence_id: str
    grounding_precedent: Optional[str] = None
    confidence: Optional[float] = None
    llm_call_id: Optional[str] = None


# ────────────────────────────────────────────────────────────────────
# Errors
# ────────────────────────────────────────────────────────────────────

class WarGameError(Exception):
    pass


class BriefNotEligible(WarGameError):
    pass


class GroundingRuleViolation(WarGameError):
    """An adversary returned an action without grounding evidence."""
    pass


class WarGameNotFound(WarGameError):
    pass


class WarGameStateError(WarGameError):
    pass


# ────────────────────────────────────────────────────────────────────
# Reactor strategy interface
# ────────────────────────────────────────────────────────────────────

class AdversaryReactor(Protocol):
    """Strategy interface for producing one adversary action per panel slot."""

    def react(
        self,
        *,
        adversary: WarGameAdversary,
        option: dict,
        round_num: int,
        prior_actions: list[WarGameAction],
    ) -> ReactorOutput:
        ...


class StubReactor:
    """Deterministic reactor for tests + baseline. Always uses the first
    grounding_evidence_id from the adversary's persona; emits a templated
    action_text. The grounding rule is satisfied because adversaries are
    required to carry at least one grounding_evidence_id (validated at run
    start).
    """

    def react(
        self,
        *,
        adversary: WarGameAdversary,
        option: dict,
        round_num: int,
        prior_actions: list[WarGameAction],
    ) -> ReactorOutput:
        if not adversary.grounding_evidence_ids:
            raise GroundingRuleViolation(
                f"adversary {adversary.name!r} has no grounding evidence; "
                f"cannot react"
            )
        # Pick deterministic grounding: rotate through provided ids by round
        idx = (round_num - 1) % len(adversary.grounding_evidence_ids)
        ground_id = adversary.grounding_evidence_ids[idx]

        # Templated action text per kind. Real LLM reactor will replace this.
        templates = {
            "competitor": "Round {r}: {name} responds to '{label}' by adjusting positioning.",
            "payer":      "Round {r}: {name} signals tier-{tier} placement consideration for '{label}'.",
            "regulator":  "Round {r}: {name} flags '{label}' for additional review based on precedent.",
            "kol":        "Round {r}: {name} publicly comments on '{label}', citing prior literature.",
        }
        tier = (round_num % 3) + 1  # 1..3
        text = templates.get(adversary.kind, "Round {r}: {name} reacts to '{label}'.").format(
            r=round_num, name=adversary.name, label=option.get("label", "(option)"), tier=tier
        )

        return ReactorOutput(
            action_kind="react",
            action_text=text,
            grounding_evidence_id=ground_id,
            grounding_precedent=f"persona.evidence_grounding[{idx}]",
            confidence=0.6,  # stub default
        )


# ────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────

def _validate_adversary_specs(specs: list[AdversarySpec]) -> None:
    if not specs:
        raise ValueError("at least one adversary spec required")
    if len(specs) > MAX_ADVERSARIES:
        raise ValueError(f"max {MAX_ADVERSARIES} adversaries per run")
    for i, a in enumerate(specs):
        if a.kind not in VALID_KINDS:
            raise ValueError(f"adversaries[{i}].kind must be in {sorted(VALID_KINDS)}")
        if not a.name or not a.name.strip():
            raise ValueError(f"adversaries[{i}].name required")
        if not a.grounding_evidence_ids:
            raise ValueError(
                f"adversaries[{i}] ({a.name!r}) requires at least one grounding_evidence_id"
            )


def _row_to_run(row: dict) -> WarGameRun:
    summary = row.get("summary_jsonb") or {}
    if isinstance(summary, str):
        try: summary = json.loads(summary)
        except (TypeError, ValueError): summary = {}
    return WarGameRun(
        run_id=str(row["run_id"]),
        brief_id=str(row["brief_id"]),
        status=row["status"],
        num_rounds=row["num_rounds"],
        started_at=row.get("started_at"),
        completed_at=row.get("completed_at"),
        failure_reason=row.get("failure_reason"),
        summary=summary,
        started_by_user_id=str(row["started_by_user_id"]) if row.get("started_by_user_id") else None,
    )


def _row_to_adversary(row: dict) -> WarGameAdversary:
    persona = row.get("persona_jsonb") or {}
    if isinstance(persona, str):
        try: persona = json.loads(persona)
        except (TypeError, ValueError): persona = {}
    grounding = row.get("grounding_evidence_ids") or []
    return WarGameAdversary(
        adversary_id=str(row["adversary_id"]),
        run_id=str(row["run_id"]),
        kind=row["kind"],
        name=row["name"],
        entity_type=row.get("entity_type"),
        entity_id=str(row["entity_id"]) if row.get("entity_id") else None,
        persona=persona,
        grounding_evidence_ids=[str(g) for g in grounding],
        created_at=row.get("created_at"),
    )


def _row_to_action(row: dict) -> WarGameAction:
    return WarGameAction(
        action_id=str(row["action_id"]),
        run_id=str(row["run_id"]),
        adversary_id=str(row["adversary_id"]),
        option_id=str(row["option_id"]),
        round_num=row["round_num"],
        action_kind=row["action_kind"],
        action_text=row["action_text"],
        grounding_evidence_id=str(row["grounding_evidence_id"]),
        grounding_precedent=row.get("grounding_precedent"),
        confidence=row.get("confidence"),
        llm_call_id=str(row["llm_call_id"]) if row.get("llm_call_id") else None,
        created_at=row.get("created_at"),
    )


# ────────────────────────────────────────────────────────────────────
# Orchestrator
# ────────────────────────────────────────────────────────────────────

class WarGameOrchestrator:
    """Synchronous war-game runner. Initialize with an AdversaryReactor;
    call run() for each brief. Persists run + adversaries + actions and
    enforces the grounding rule before insert."""

    def __init__(self, reactor: Optional[AdversaryReactor] = None):
        self.reactor = reactor or StubReactor()

    def run(
        self,
        db,
        *,
        brief_id: str,
        adversaries: list[AdversarySpec],
        num_rounds: int = 3,
        started_by_user_id: Optional[str] = None,
    ) -> WarGameRun:
        if num_rounds < 1 or num_rounds > MAX_ROUNDS:
            raise ValueError(f"num_rounds must be in [1, {MAX_ROUNDS}]")
        _validate_adversary_specs(adversaries)

        # Verify brief exists + is in eligible state + load options
        brief_row = db.fetch_one(
            """
            SELECT brief_id, state, decision_id
              FROM decision_briefs WHERE brief_id::text = %s
            """,
            (str(brief_id),),
        )
        if not brief_row:
            raise WarGameNotFound(f"brief not found: {brief_id}")
        if brief_row["state"] not in ALLOWED_BRIEF_STATES_FOR_START:
            raise BriefNotEligible(
                f"brief in state {brief_row['state']!r}; allowed states: "
                f"{sorted(ALLOWED_BRIEF_STATES_FOR_START)}"
            )

        opt_rows = db.fetch_all(
            """
            SELECT option_id, ordinal, label, description
              FROM decision_brief_options
             WHERE brief_id::text = %s
             ORDER BY ordinal ASC
            """,
            (str(brief_id),),
        ) or []
        if not opt_rows:
            raise BriefNotEligible(f"brief {brief_id} has no options to react to")
        if len(opt_rows) > MAX_OPTIONS_PER_BRIEF:
            raise BriefNotEligible(
                f"brief has {len(opt_rows)} options; cap is {MAX_OPTIONS_PER_BRIEF}"
            )
        options = [
            {"option_id": str(o["option_id"]), "ordinal": o["ordinal"],
             "label": o["label"], "description": o.get("description")}
            for o in opt_rows
        ]

        # Insert run
        run_row = db.fetch_one(
            """
            INSERT INTO war_game_runs (brief_id, status, num_rounds, started_by_user_id)
            VALUES (%s::uuid, 'running', %s, %s)
            RETURNING run_id, brief_id, status, num_rounds, started_at,
                      completed_at, failure_reason, summary_jsonb, started_by_user_id
            """,
            (str(brief_id), num_rounds, started_by_user_id),
        )
        if not run_row:
            raise RuntimeError("war-game run insert returned no row")
        run = _row_to_run(run_row)
        run_id = run.run_id

        # Insert adversaries
        adv_objs: list[WarGameAdversary] = []
        for spec in adversaries:
            row = db.fetch_one(
                """
                INSERT INTO war_game_adversaries (
                    run_id, kind, name, entity_type, entity_id,
                    persona_jsonb, grounding_evidence_ids
                ) VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::uuid[])
                RETURNING adversary_id, run_id, kind, name, entity_type, entity_id,
                          persona_jsonb, grounding_evidence_ids, created_at
                """,
                (
                    run_id, spec.kind, spec.name, spec.entity_type, spec.entity_id,
                    json.dumps(spec.persona or {}),
                    spec.grounding_evidence_ids,
                ),
            )
            adv_objs.append(_row_to_adversary(row))

        run.adversaries = adv_objs

        # Drive panel: for each option × adversary × round, ask reactor
        all_actions: list[WarGameAction] = []
        try:
            for option in options:
                for adversary in adv_objs:
                    for r in range(1, num_rounds + 1):
                        out = self.reactor.react(
                            adversary=adversary,
                            option=option,
                            round_num=r,
                            prior_actions=all_actions,
                        )
                        if not out.grounding_evidence_id:
                            raise GroundingRuleViolation(
                                f"reactor returned action without grounding_evidence_id "
                                f"(adversary={adversary.name!r}, option={option['label']!r}, round={r})"
                            )
                        if out.action_kind not in VALID_ACTION_KINDS:
                            raise ValueError(
                                f"reactor returned invalid action_kind {out.action_kind!r}; "
                                f"must be in {sorted(VALID_ACTION_KINDS)}"
                            )
                        action_row = db.fetch_one(
                            """
                            INSERT INTO war_game_actions (
                                run_id, adversary_id, option_id, round_num,
                                action_kind, action_text, grounding_evidence_id,
                                grounding_precedent, confidence, llm_call_id
                            ) VALUES (%s, %s, %s::uuid, %s, %s, %s, %s, %s, %s, %s)
                            RETURNING action_id, run_id, adversary_id, option_id,
                                      round_num, action_kind, action_text,
                                      grounding_evidence_id, grounding_precedent,
                                      confidence, llm_call_id, created_at
                            """,
                            (
                                run_id, adversary.adversary_id, option["option_id"], r,
                                out.action_kind, out.action_text, out.grounding_evidence_id,
                                out.grounding_precedent, out.confidence, out.llm_call_id,
                            ),
                        )
                        all_actions.append(_row_to_action(action_row))
        except (GroundingRuleViolation, ValueError) as exc:
            db.execute(
                """
                UPDATE war_game_runs
                   SET status = 'failed', failure_reason = %s, completed_at = NOW()
                 WHERE run_id::text = %s
                """,
                (str(exc)[:500], run_id),
            )
            raise

        # Build a lightweight summary: per-option action counts + dominant kind
        per_option: dict[str, dict] = {}
        for a in all_actions:
            b = per_option.setdefault(a.option_id, {"action_count": 0, "kinds": {}})
            b["action_count"] += 1
            b["kinds"][a.action_kind] = b["kinds"].get(a.action_kind, 0) + 1
        summary = {
            "options": [
                {
                    "option_id": k,
                    "action_count": v["action_count"],
                    "dominant_kind": max(v["kinds"].items(), key=lambda kv: kv[1])[0],
                }
                for k, v in per_option.items()
            ],
            "total_actions": len(all_actions),
            "rounds": num_rounds,
            "adversary_count": len(adv_objs),
        }

        # Mark complete
        db.execute(
            """
            UPDATE war_game_runs
               SET status = 'complete', completed_at = NOW(), summary_jsonb = %s::jsonb
             WHERE run_id::text = %s
            """,
            (json.dumps(summary), run_id),
        )
        run.status = "complete"
        run.summary = summary
        run.actions = all_actions
        return run


# ────────────────────────────────────────────────────────────────────
# Read-side service (independent of orchestration)
# ────────────────────────────────────────────────────────────────────

class WarGameRepository:

    @staticmethod
    def get(db, run_id: str, *, include_actions: bool = False) -> Optional[WarGameRun]:
        row = db.fetch_one(
            """
            SELECT run_id, brief_id, status, num_rounds, started_at,
                   completed_at, failure_reason, summary_jsonb, started_by_user_id
              FROM war_game_runs WHERE run_id::text = %s
            """,
            (str(run_id),),
        )
        if not row:
            return None
        run = _row_to_run(row)
        adv_rows = db.fetch_all(
            """
            SELECT adversary_id, run_id, kind, name, entity_type, entity_id,
                   persona_jsonb, grounding_evidence_ids, created_at
              FROM war_game_adversaries WHERE run_id::text = %s
             ORDER BY created_at ASC
            """,
            (str(run_id),),
        ) or []
        run.adversaries = [_row_to_adversary(r) for r in adv_rows]
        if include_actions:
            act_rows = db.fetch_all(
                """
                SELECT action_id, run_id, adversary_id, option_id, round_num,
                       action_kind, action_text, grounding_evidence_id,
                       grounding_precedent, confidence, llm_call_id, created_at
                  FROM war_game_actions WHERE run_id::text = %s
                 ORDER BY round_num ASC, adversary_id ASC, created_at ASC
                """,
                (str(run_id),),
            ) or []
            run.actions = [_row_to_action(r) for r in act_rows]
        return run

    @staticmethod
    def list(
        db,
        *,
        brief_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[WarGameRun]:
        if limit < 1 or limit > 500:
            raise ValueError("limit must be in [1, 500]")
        if status is not None and status not in VALID_STATUSES:
            raise ValueError(f"status must be in {sorted(VALID_STATUSES)}")
        where = ["1=1"]
        params: list[Any] = []
        if brief_id is not None:
            where.append("brief_id::text = %s"); params.append(str(brief_id))
        if status is not None:
            where.append("status = %s"); params.append(status)
        params.extend([limit, offset])
        rows = db.fetch_all(
            f"""
            SELECT run_id, brief_id, status, num_rounds, started_at,
                   completed_at, failure_reason, summary_jsonb, started_by_user_id
              FROM war_game_runs
             WHERE {' AND '.join(where)}
             ORDER BY started_at DESC
             LIMIT %s OFFSET %s
            """,
            tuple(params),
        ) or []
        return [_row_to_run(r) for r in rows]

    @staticmethod
    def cancel(db, run_id: str) -> WarGameRun:
        existing = WarGameRepository.get(db, run_id)
        if not existing:
            raise WarGameNotFound(run_id)
        if existing.status not in ("pending", "running"):
            raise WarGameStateError(
                f"cannot cancel run in state {existing.status!r}"
            )
        db.execute(
            """
            UPDATE war_game_runs
               SET status = 'cancelled', completed_at = NOW(),
                   failure_reason = 'cancelled by user'
             WHERE run_id::text = %s
            """,
            (str(run_id),),
        )
        return WarGameRepository.get(db, run_id) or existing
