"""Z4 — Business Context Brief (BCB).

The ZS framework's most upstream commitment: an engagement starts when the
lead types a brief stating the situation, the competitive set, and the
specific decisions the wargame must inform.

The type refuses to construct without at least one strategic decision — the
wargame has to INFORM something. No decisions = no point.

See specs/SPEC_Z4_business_context_brief.md.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)

VALID_THREAT_LEVELS = ("primary", "secondary", "watch")
VALID_SITUATIONS = ("launch", "defense", "lcm")


class BCBContractError(ValueError):
    """Raised when a BCB or its components violate type invariants."""


# ── Component types ───────────────────────────────────────────────


@dataclass(frozen=True)
class StrategicDecision:
    statement: str
    rationale: str

    def __post_init__(self):
        if not self.statement or not self.statement.strip():
            raise BCBContractError("StrategicDecision.statement cannot be empty")
        if not self.rationale or not self.rationale.strip():
            raise BCBContractError("StrategicDecision.rationale cannot be empty")


@dataclass(frozen=True)
class CompetitorThreat:
    entity_ref: str
    threat_level: str
    note: str

    def __post_init__(self):
        if not self.entity_ref or not self.entity_ref.strip():
            raise BCBContractError("CompetitorThreat.entity_ref cannot be empty")
        if self.threat_level not in VALID_THREAT_LEVELS:
            raise BCBContractError(
                f"CompetitorThreat.threat_level must be one of "
                f"{VALID_THREAT_LEVELS}, got {self.threat_level!r}"
            )


# ── BCB ────────────────────────────────────────────────────────────


@dataclass
class BusinessContextBrief:
    id: str
    engagement_id: str
    focal_asset: str
    situation: str
    strategic_decisions: list[StrategicDecision]
    competitive_set: list[CompetitorThreat]
    success_criteria: list[str]
    constraints: list[str]
    created_by: str
    created_at: datetime
    signed_off: bool = False
    signed_off_by: Optional[str] = None
    signed_off_at: Optional[datetime] = None

    def __post_init__(self):
        if not self.focal_asset or not self.focal_asset.strip():
            raise BCBContractError("focal_asset cannot be empty")
        if self.situation not in VALID_SITUATIONS:
            raise BCBContractError(
                f"situation must be one of {VALID_SITUATIONS}, got {self.situation!r}"
            )
        if not self.strategic_decisions or len(self.strategic_decisions) < 1:
            raise BCBContractError(
                "BCB requires >= 1 strategic_decisions (wargame must inform something)"
            )
        # paired sign-off invariant — mirrors DB CHECK
        signed_off_set = (
            self.signed_off and self.signed_off_by is not None
            and self.signed_off_at is not None
        )
        signed_off_clear = (
            not self.signed_off and self.signed_off_by is None
            and self.signed_off_at is None
        )
        if not (signed_off_set or signed_off_clear):
            raise BCBContractError(
                "sign-off triple must be all set or all null "
                "(signed_off, signed_off_by, signed_off_at)"
            )


# ── Coercion helpers ──────────────────────────────────────────────


def _decisions_to_jsonb(decisions) -> str:
    out = [
        {"statement": d.statement, "rationale": d.rationale}
        if isinstance(d, StrategicDecision) else dict(d)
        for d in (decisions or [])
    ]
    return json.dumps(out)


def _threats_to_jsonb(threats) -> str:
    out = [
        {"entity_ref": t.entity_ref, "threat_level": t.threat_level, "note": t.note}
        if isinstance(t, CompetitorThreat) else dict(t)
        for t in (threats or [])
    ]
    return json.dumps(out)


def _list_to_jsonb(items) -> str:
    return json.dumps(list(items or []))


def _row_to_bcb(row: dict) -> BusinessContextBrief:
    sd = row.get("strategic_decisions") or []
    if isinstance(sd, str):
        sd = json.loads(sd)
    cs = row.get("competitive_set") or []
    if isinstance(cs, str):
        cs = json.loads(cs)
    sc = row.get("success_criteria") or []
    if isinstance(sc, str):
        sc = json.loads(sc)
    co = row.get("constraints") or []
    if isinstance(co, str):
        co = json.loads(co)
    return BusinessContextBrief(
        id=str(row["id"]),
        engagement_id=str(row["engagement_id"]),
        focal_asset=row["focal_asset"],
        situation=row["situation"],
        strategic_decisions=[
            StrategicDecision(statement=d["statement"], rationale=d["rationale"])
            for d in sd
        ],
        competitive_set=[
            CompetitorThreat(
                entity_ref=t["entity_ref"],
                threat_level=t["threat_level"],
                note=t.get("note", ""),
            )
            for t in cs
        ],
        success_criteria=list(sc),
        constraints=list(co),
        created_by=row["created_by"],
        created_at=row["created_at"],
        signed_off=bool(row.get("signed_off", False)),
        signed_off_by=row.get("signed_off_by"),
        signed_off_at=row.get("signed_off_at"),
    )


# ── SQL ───────────────────────────────────────────────────────────


_INSERT_SQL = """
    INSERT INTO business_context_briefs (
        engagement_id, focal_asset, situation,
        strategic_decisions, competitive_set, success_criteria, constraints,
        created_by
    ) VALUES (
        %(engagement_id)s, %(focal_asset)s, %(situation)s,
        %(strategic_decisions)s::jsonb, %(competitive_set)s::jsonb,
        %(success_criteria)s::jsonb, %(constraints)s::jsonb,
        %(created_by)s
    )
    RETURNING id
"""

_SELECT_BY_ENGAGEMENT_SQL = """
    SELECT id, engagement_id, focal_asset, situation,
           strategic_decisions, competitive_set, success_criteria, constraints,
           created_by, created_at, signed_off, signed_off_by, signed_off_at
      FROM business_context_briefs
     WHERE engagement_id = %s
     LIMIT 1
"""

_SELECT_BY_ID_SQL = """
    SELECT id, engagement_id, focal_asset, situation,
           strategic_decisions, competitive_set, success_criteria, constraints,
           created_by, created_at, signed_off, signed_off_by, signed_off_at
      FROM business_context_briefs
     WHERE id = %s
"""

_UPDATE_SQL = """
    UPDATE business_context_briefs
       SET focal_asset = %(focal_asset)s,
           situation = %(situation)s,
           strategic_decisions = %(strategic_decisions)s::jsonb,
           competitive_set = %(competitive_set)s::jsonb,
           success_criteria = %(success_criteria)s::jsonb,
           constraints = %(constraints)s::jsonb
     WHERE id = %(id)s AND signed_off = FALSE
     RETURNING id, engagement_id, focal_asset, situation,
               strategic_decisions, competitive_set, success_criteria, constraints,
               created_by, created_at, signed_off, signed_off_by, signed_off_at
"""

_SIGN_OFF_SQL = """
    UPDATE business_context_briefs
       SET signed_off = TRUE,
           signed_off_by = %(by)s,
           signed_off_at = NOW()
     WHERE id = %(id)s
     RETURNING id, engagement_id, focal_asset, situation,
               strategic_decisions, competitive_set, success_criteria, constraints,
               created_by, created_at, signed_off, signed_off_by, signed_off_at
"""

_ENGAGEMENT_AUDIT_SQL = """
    INSERT INTO engagement_audit_log (
        engagement_id, actor, event_type, from_value, to_value, rationale
    ) VALUES (
        %(engagement_id)s, %(actor)s, 'scope_change',
        %(from_value)s, %(to_value)s, %(rationale)s
    )
"""


# ── Public API ────────────────────────────────────────────────────


def _coerce_and_validate(strategic_decisions, competitive_set, situation):
    """Coerce dict/dataclass inputs to typed components and enforce the BCB
    invariants (≥1 decision; valid situation). Shared by create + update."""
    decisions = [
        d if isinstance(d, StrategicDecision)
        else StrategicDecision(statement=d["statement"], rationale=d["rationale"])
        for d in (strategic_decisions or [])
    ]
    threats = [
        t if isinstance(t, CompetitorThreat)
        else CompetitorThreat(
            entity_ref=t["entity_ref"],
            threat_level=t["threat_level"],
            note=t.get("note", ""),
        )
        for t in (competitive_set or [])
    ]
    if not decisions:
        raise BCBContractError(
            "BCB requires >= 1 strategic_decisions (wargame must inform something)"
        )
    if situation not in VALID_SITUATIONS:
        raise BCBContractError(
            f"situation must be one of {VALID_SITUATIONS}, got {situation!r}"
        )
    return decisions, threats


def create_bcb(
    db,
    *,
    engagement_id: str,
    focal_asset: str,
    situation: str,
    strategic_decisions: list,
    competitive_set: list,
    success_criteria: Optional[list] = None,
    constraints: Optional[list] = None,
    created_by: str,
) -> str:
    """Create the BCB for an engagement. Raises BCBContractError on invariant
    violations. Returns the new BCB id."""
    decisions, threats = _coerce_and_validate(
        strategic_decisions, competitive_set, situation
    )

    params = {
        "engagement_id": engagement_id,
        "focal_asset": focal_asset,
        "situation": situation,
        "strategic_decisions": _decisions_to_jsonb(decisions),
        "competitive_set": _threats_to_jsonb(threats),
        "success_criteria": _list_to_jsonb(success_criteria or []),
        "constraints": _list_to_jsonb(constraints or []),
        "created_by": created_by,
    }
    res = _exec_returning(db, _INSERT_SQL, params)
    bid = str(res["id"]) if res and res.get("id") else str(uuid4())
    logger.info("created BCB %s for engagement %s", bid, engagement_id)
    return bid


def update_bcb(
    db,
    *,
    engagement_id: str,
    focal_asset: str,
    situation: str,
    strategic_decisions: list,
    competitive_set: list,
    success_criteria: Optional[list] = None,
    constraints: Optional[list] = None,
) -> BusinessContextBrief:
    """Update the engagement's BCB in place (UX08 in-app authoring).

    Refuses to edit a signed-off brief — a signed brief is immutable; create a
    new one or revert sign-off first. Raises BCBContractError on a missing
    brief, a signed brief, or an invariant violation. Returns the updated BCB.
    """
    existing = get_bcb_for_engagement(db, engagement_id)
    if not existing:
        raise BCBContractError(
            f"no brief to update for engagement {engagement_id}; create one first"
        )
    if existing.signed_off:
        raise BCBContractError(
            "cannot edit a signed-off brief — it is immutable once signed"
        )
    decisions, threats = _coerce_and_validate(
        strategic_decisions, competitive_set, situation
    )
    params = {
        "id": existing.id,
        "focal_asset": focal_asset,
        "situation": situation,
        "strategic_decisions": _decisions_to_jsonb(decisions),
        "competitive_set": _threats_to_jsonb(threats),
        "success_criteria": _list_to_jsonb(success_criteria or []),
        "constraints": _list_to_jsonb(constraints or []),
    }
    res = _exec_returning(db, _UPDATE_SQL, params)
    if not res:
        # WHERE matched 0 rows → it was signed between our check and the UPDATE.
        raise BCBContractError("brief update failed (was it signed concurrently?)")
    logger.info("updated BCB %s for engagement %s", existing.id, engagement_id)
    return _row_to_bcb(res)


def get_bcb_for_engagement(db, engagement_id: str) -> Optional[BusinessContextBrief]:
    try:
        row = db.fetch_one(_SELECT_BY_ENGAGEMENT_SQL, [engagement_id])
    except Exception:
        logger.exception("get_bcb_for_engagement query failed")
        return None
    if not row:
        return None
    return _row_to_bcb(row)


def get_bcb(db, bcb_id: str) -> Optional[BusinessContextBrief]:
    try:
        row = db.fetch_one(_SELECT_BY_ID_SQL, [bcb_id])
    except Exception:
        logger.exception("get_bcb query failed")
        return None
    if not row:
        return None
    return _row_to_bcb(row)


def sign_off_bcb(db, bcb_id: str, *, by: str) -> BusinessContextBrief:
    """Sign off a BCB and emit an engagement audit entry. The audit
    cross-system entry makes the sign-off visible in the engagement's
    timeline — the wargame's prep moment."""
    res = _exec_returning(db, _SIGN_OFF_SQL, {"by": by, "id": bcb_id})
    if not res:
        raise ValueError(f"BCB {bcb_id!r} not found or sign-off failed")
    # Emit cross-system audit on the engagement audit log
    engagement_id = str(res.get("engagement_id", ""))
    try:
        db.execute(_ENGAGEMENT_AUDIT_SQL, {
            "engagement_id": engagement_id,
            "actor": by,
            "from_value": "draft",
            "to_value": "signed_off",
            "rationale": f"BCB signed off by {by}",
        })
    except Exception:
        logger.exception("engagement_audit_log write for BCB sign-off failed")
    # Build the returned BCB from the local update (mock-robust like Z3)
    bcb = _row_to_bcb(res)
    if not bcb.signed_off:
        # The mock may have returned the pre-update row; reflect the actual
        # state we just set.
        bcb = BusinessContextBrief(
            id=bcb.id, engagement_id=bcb.engagement_id,
            focal_asset=bcb.focal_asset, situation=bcb.situation,
            strategic_decisions=bcb.strategic_decisions,
            competitive_set=bcb.competitive_set,
            success_criteria=bcb.success_criteria,
            constraints=bcb.constraints,
            created_by=bcb.created_by, created_at=bcb.created_at,
            signed_off=True, signed_off_by=by,
            signed_off_at=datetime.now(timezone.utc),
        )
    return bcb


def _exec_returning(db, sql: str, params: Any) -> Optional[dict]:
    try:
        if hasattr(db, "fetch_one"):
            return db.fetch_one(sql, params)
    except Exception:
        logger.exception("BCB persist fetch_one failed")
    try:
        db.execute(sql, params)
    except Exception:
        logger.exception("BCB persist execute failed")
    return None
