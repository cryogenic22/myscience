"""Z3 — Engagement entity + 7-stage lifecycle FSM.

Engagement is the v7 design canon's unit of work: every meaningful piece of
the platform's work belongs to an Engagement, and the surfaces of /ci are
the stages of its lifecycle. This module is the back-end side of that
commitment — the table, the FSM, the audit log.

Lifecycle (from docs/helix-v7-gap-analysis.html §1.2):
  brief → sources → dossier → synthesis → gaps → scenarios → workshop

Status (orthogonal):
  draft → active → completed → archived

FSM rules (enforced here, not by convention):
  - Forward one stage at a time when status='active'.
  - Back-track to any earlier stage allowed, writes audit entry.
  - Skip-ahead rejected with InvalidStageTransition.
  - Stage changes blocked while status='draft'.
  - Status: draft→active any time; active→completed only from workshop;
    *→archived always allowed.

See specs/SPEC_Z3_engagement_entity.md.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)


# ── Errors ─────────────────────────────────────────────────────────


class InvalidStageTransition(ValueError):
    """Stage transition violates the FSM (skip-ahead, draft-status, etc.)."""


class InvalidStatusTransition(ValueError):
    """Status transition violates the FSM."""


class InvalidSituation(ValueError):
    """Engagement situation must be one of {launch, defense, lcm}."""


# ── Enums ──────────────────────────────────────────────────────────


class LifecycleStage(str, Enum):
    BRIEF     = "brief"
    SOURCES   = "sources"
    DOSSIER   = "dossier"
    SYNTHESIS = "synthesis"
    GAPS      = "gaps"
    SCENARIOS = "scenarios"
    WORKSHOP  = "workshop"


class EngagementStatus(str, Enum):
    DRAFT     = "draft"
    ACTIVE    = "active"
    COMPLETED = "completed"
    ARCHIVED  = "archived"


STAGE_ORDER: list[LifecycleStage] = [
    LifecycleStage.BRIEF,
    LifecycleStage.SOURCES,
    LifecycleStage.DOSSIER,
    LifecycleStage.SYNTHESIS,
    LifecycleStage.GAPS,
    LifecycleStage.SCENARIOS,
    LifecycleStage.WORKSHOP,
]

VALID_SITUATIONS = ("launch", "defense", "lcm")


# ── Dataclass ──────────────────────────────────────────────────────


@dataclass
class Engagement:
    id: str
    name: str
    asset: str
    sponsor: Optional[str]
    situation: str
    workshop_date: Optional[datetime]
    stage: LifecycleStage
    status: EngagementStatus
    scope: dict
    created_by: str
    created_at: datetime
    updated_at: datetime
    tenant_scope: Optional[str] = None

    def __post_init__(self):
        if not self.name or not self.name.strip():
            raise ValueError("Engagement name cannot be empty")
        if self.situation not in VALID_SITUATIONS:
            raise InvalidSituation(
                f"situation must be one of {VALID_SITUATIONS}, got {self.situation!r}"
            )


# ── Row → Engagement ───────────────────────────────────────────────


def _row_to_engagement(row: dict) -> Engagement:
    return Engagement(
        id=str(row["id"]),
        name=row["name"],
        asset=row["asset"],
        sponsor=row.get("sponsor"),
        situation=row["situation"],
        workshop_date=row.get("workshop_date"),
        stage=LifecycleStage(row["stage"]),
        status=EngagementStatus(row["status"]),
        scope=row.get("scope") or {},
        created_by=row["created_by"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        tenant_scope=row.get("tenant_scope"),
    )


# ── SQL ────────────────────────────────────────────────────────────


_INSERT_SQL = """
    INSERT INTO engagements (
        name, asset, sponsor, situation, workshop_date,
        stage, status, scope, created_by, tenant_scope
    ) VALUES (
        %(name)s, %(asset)s, %(sponsor)s, %(situation)s, %(workshop_date)s,
        %(stage)s, %(status)s, %(scope)s::jsonb,
        %(created_by)s, %(tenant_scope)s
    )
    RETURNING id
"""

_SELECT_ONE_SQL = """
    SELECT id, name, asset, sponsor, situation, workshop_date,
           stage, status, scope, created_by, created_at, updated_at,
           tenant_scope
      FROM engagements
     WHERE id = %s
"""

_LIST_SQL = """
    SELECT id, name, asset, sponsor, situation, workshop_date,
           stage, status, scope, created_by, created_at, updated_at,
           tenant_scope
      FROM engagements
     {where}
     ORDER BY created_at DESC
     LIMIT %s
"""

_UPDATE_STAGE_SQL = """
    UPDATE engagements
       SET stage = %s, updated_at = NOW()
     WHERE id = %s
     RETURNING id, name, asset, sponsor, situation, workshop_date,
               stage, status, scope, created_by, created_at, updated_at,
               tenant_scope
"""

_UPDATE_STATUS_SQL = """
    UPDATE engagements
       SET status = %s, updated_at = NOW()
     WHERE id = %s
     RETURNING id, name, asset, sponsor, situation, workshop_date,
               stage, status, scope, created_by, created_at, updated_at,
               tenant_scope
"""

_AUDIT_SQL = """
    INSERT INTO engagement_audit_log (
        engagement_id, actor, event_type, from_value, to_value, rationale
    ) VALUES (
        %(engagement_id)s, %(actor)s, %(event_type)s,
        %(from_value)s, %(to_value)s, %(rationale)s
    )
"""


# ── Audit ──────────────────────────────────────────────────────────


def _audit(db, engagement_id: str, actor: str, event_type: str,
           from_value: Optional[str], to_value: str, rationale: str) -> None:
    """Best-effort audit write. Audit MUST attempt to log; if persistence
    fails we surface the error to the caller because a missed audit entry
    is a procurement-grade failure (Phase C makes this strict)."""
    db.execute(_AUDIT_SQL, {
        "engagement_id": engagement_id,
        "actor": actor,
        "event_type": event_type,
        "from_value": from_value,
        "to_value": to_value,
        "rationale": rationale,
    })


# ── Public API ─────────────────────────────────────────────────────


def create_engagement(
    db,
    *,
    name: str,
    asset: str,
    situation: str,
    sponsor: Optional[str] = None,
    workshop_date: Optional[datetime] = None,
    scope: Optional[dict] = None,
    created_by: str,
    tenant_scope: Optional[str] = None,
) -> str:
    """Create an engagement in draft/brief. Returns the new id."""
    import json
    if situation not in VALID_SITUATIONS:
        raise InvalidSituation(
            f"situation must be one of {VALID_SITUATIONS}, got {situation!r}"
        )
    if not name or not name.strip():
        raise ValueError("name cannot be empty")
    row = {
        "name": name,
        "asset": asset,
        "sponsor": sponsor,
        "situation": situation,
        "workshop_date": workshop_date,
        "stage": LifecycleStage.BRIEF.value,
        "status": EngagementStatus.DRAFT.value,
        "scope": json.dumps(scope or {}),
        "created_by": created_by,
        "tenant_scope": tenant_scope,
    }
    res = _exec_returning(db, _INSERT_SQL, row)
    eid = str(res["id"]) if res and res.get("id") else str(uuid4())
    _audit(db, eid, created_by, "created", None, "brief/draft",
           rationale=f"engagement created: {name}")
    logger.info("created engagement %s (%s, %s)", eid, situation, name)
    return eid


def get_engagement(db, eid: str) -> Optional[Engagement]:
    try:
        row = db.fetch_one(_SELECT_ONE_SQL, [eid])
    except Exception:
        logger.exception("get_engagement query failed for %s", eid)
        return None
    if not row:
        return None
    return _row_to_engagement(row)


def list_engagements(
    db,
    *,
    status: Optional[str] = None,
    situation: Optional[str] = None,
    limit: int = 50,
) -> list[Engagement]:
    clauses: list[str] = []
    params: list[Any] = []
    if status:
        clauses.append("status = %s")
        params.append(status)
    if situation:
        clauses.append("situation = %s")
        params.append(situation)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(int(limit))
    sql = _LIST_SQL.format(where=where)
    try:
        rows = db.fetch_all(sql, params)
    except Exception:
        logger.exception("list_engagements query failed")
        return []
    out: list[Engagement] = []
    for r in rows:
        try:
            out.append(_row_to_engagement(r))
        except (ValueError, KeyError) as exc:
            logger.warning("skipping malformed engagement row: %s", exc)
    return out


def advance_stage(
    db,
    eid: str,
    *,
    to_stage: str,
    rationale: str,
    actor: str,
) -> Engagement:
    """Move an engagement to `to_stage`. Enforces the FSM:
      - skip-ahead rejected
      - draft-status rejected
      - empty rationale rejected
      - back-track allowed (with audit)
    Writes audit entry on every successful transition.
    """
    if not rationale or not rationale.strip():
        raise InvalidStageTransition(
            "advance_stage requires a non-empty rationale (procurement-grade audit)"
        )
    try:
        to_stage_enum = LifecycleStage(to_stage)
    except ValueError as exc:
        raise InvalidStageTransition(f"unknown stage {to_stage!r}") from exc

    current = get_engagement(db, eid)
    if current is None:
        raise InvalidStageTransition(f"engagement {eid!r} not found")
    if current.status is not EngagementStatus.ACTIVE:
        raise InvalidStageTransition(
            f"stage changes require status=active (current={current.status.value})"
        )

    cur_idx = STAGE_ORDER.index(current.stage)
    new_idx = STAGE_ORDER.index(to_stage_enum)
    if new_idx > cur_idx + 1:
        raise InvalidStageTransition(
            f"skip-ahead not allowed: {current.stage.value} → {to_stage_enum.value}"
        )
    if new_idx == cur_idx:
        raise InvalidStageTransition(
            f"already at stage {current.stage.value}"
        )
    # new_idx < cur_idx → back-track (allowed, with audit)
    # new_idx == cur_idx + 1 → forward one step (allowed)

    _exec_returning(db, _UPDATE_STAGE_SQL, [to_stage_enum.value, eid])
    _audit(
        db, eid, actor, "stage_change",
        from_value=current.stage.value,
        to_value=to_stage_enum.value,
        rationale=rationale,
    )
    logger.info(
        "engagement %s stage: %s → %s (by %s)",
        eid, current.stage.value, to_stage_enum.value, actor,
    )
    # Return the locally-computed updated form. We do not trust the
    # RETURNING row to reflect the new state because it could come from a
    # stale snapshot under concurrent updates; the locally-computed value
    # is what we just told the DB to set.
    return Engagement(
        id=current.id, name=current.name, asset=current.asset,
        sponsor=current.sponsor, situation=current.situation,
        workshop_date=current.workshop_date,
        stage=to_stage_enum, status=current.status,
        scope=current.scope, created_by=current.created_by,
        created_at=current.created_at, updated_at=datetime.now(timezone.utc),
        tenant_scope=current.tenant_scope,
    )


def set_status(
    db,
    eid: str,
    *,
    to_status: str,
    actor: str,
) -> Engagement:
    """Move an engagement's status. Enforces:
      - draft → active (always allowed)
      - active → completed (only from workshop stage)
      - * → archived (always allowed)
      - any other transition rejected
    """
    try:
        to_status_enum = EngagementStatus(to_status)
    except ValueError as exc:
        raise InvalidStatusTransition(f"unknown status {to_status!r}") from exc

    current = get_engagement(db, eid)
    if current is None:
        raise InvalidStatusTransition(f"engagement {eid!r} not found")

    cur = current.status
    nxt = to_status_enum

    allowed = False
    if nxt is EngagementStatus.ARCHIVED:
        allowed = True
    elif cur is EngagementStatus.DRAFT and nxt is EngagementStatus.ACTIVE:
        allowed = True
    elif cur is EngagementStatus.ACTIVE and nxt is EngagementStatus.COMPLETED:
        allowed = current.stage is LifecycleStage.WORKSHOP

    if not allowed:
        raise InvalidStatusTransition(
            f"{cur.value} → {nxt.value} not allowed "
            f"(stage={current.stage.value})"
        )

    _exec_returning(db, _UPDATE_STATUS_SQL, [nxt.value, eid])
    _audit(
        db, eid, actor, "status_change",
        from_value=cur.value, to_value=nxt.value,
        rationale=f"status: {cur.value} → {nxt.value}",
    )
    logger.info(
        "engagement %s status: %s → %s (by %s)",
        eid, cur.value, nxt.value, actor,
    )
    return Engagement(
        id=current.id, name=current.name, asset=current.asset,
        sponsor=current.sponsor, situation=current.situation,
        workshop_date=current.workshop_date,
        stage=current.stage, status=nxt,
        scope=current.scope, created_by=current.created_by,
        created_at=current.created_at, updated_at=datetime.now(timezone.utc),
        tenant_scope=current.tenant_scope,
    )


def _exec_returning(db, sql: str, params: Any) -> Optional[dict]:
    """Best-effort: prefer fetch_one (RETURNING), fall back to execute."""
    try:
        if hasattr(db, "fetch_one"):
            return db.fetch_one(sql, params)
    except Exception:
        logger.exception("engagement persist fetch_one failed")
    try:
        db.execute(sql, params)
    except Exception:
        logger.exception("engagement persist execute failed")
    return None
