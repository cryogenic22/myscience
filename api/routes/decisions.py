"""SPEC-021 Phase C — Decision Ledger API.

A decision is a promoted war-room round: the moment a hypothesis becomes
a commitment with owner, deadline, and target outcome. Decisions outlive
their source room (FK SET NULL).

Endpoints:
  POST   /decisions/from-round/{round_id}   viewer+ (room owner)
  GET    /decisions                         viewer+ (lists current user's)
  GET    /decisions/{id}                    anon
  PATCH  /decisions/{id}                    owner
  DELETE /decisions/{id}                    owner
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field

from api.deps import get_current_user, get_db, require_role
from db import Database

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/decisions", tags=["decisions"])


VALID_STATUSES = ("open", "in_progress", "verified", "missed", "cancelled")


# ────────────────────────────────────────────────────────────────────
# Schemas
# ────────────────────────────────────────────────────────────────────

class PromoteBody(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    rationale: Optional[str] = Field(default=None, max_length=4000)
    target_metric: Optional[str] = Field(default=None, max_length=200)
    target_value: Optional[str] = Field(default=None, max_length=200)
    deadline: Optional[str] = None  # ISO date "YYYY-MM-DD"
    owner_display_name: Optional[str] = Field(default=None, max_length=200)


class PatchDecisionBody(BaseModel):
    status: Optional[str] = None
    notes: Optional[str] = Field(default=None, max_length=4000)
    deadline: Optional[str] = None  # ISO date or empty string to clear
    target_metric: Optional[str] = Field(default=None, max_length=200)
    target_value: Optional[str] = Field(default=None, max_length=200)
    actual_outcome: Optional[str] = Field(default=None, max_length=4000)


# ────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────

def _iso(v):
    if v is None:
        return None
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return str(v)


_DECISION_COLS = """id, war_room_round_id, war_room_id, source_signal_id,
                    title, rationale, move_type, move_payload_snapshot,
                    owner_user_id, owner_display_name,
                    target_metric, target_value, deadline,
                    confidence_at_commit, status,
                    actual_outcome, actual_outcome_recorded_at,
                    calibration_score, notes,
                    created_at, updated_at"""


def _decision_to_dict(row: dict) -> dict:
    payload = row.get("move_payload_snapshot") or {}
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            payload = {}
    deadline = row.get("deadline")
    overdue = False
    days_to_deadline: Optional[int] = None
    if deadline and row.get("status") in ("open", "in_progress"):
        try:
            d = deadline if isinstance(deadline, date) else datetime.fromisoformat(str(deadline)).date()
            delta = (d - date.today()).days
            days_to_deadline = delta
            overdue = delta < 0
        except Exception:
            pass
    return {
        "id": str(row.get("id")),
        "war_room_round_id": str(row["war_room_round_id"]) if row.get("war_room_round_id") else None,
        "war_room_id": str(row["war_room_id"]) if row.get("war_room_id") else None,
        "source_signal_id": str(row["source_signal_id"]) if row.get("source_signal_id") else None,
        "title": row.get("title"),
        "rationale": row.get("rationale"),
        "move_type": row.get("move_type"),
        "move_payload_snapshot": payload,
        "owner_user_id": str(row["owner_user_id"]) if row.get("owner_user_id") else None,
        "owner_display_name": row.get("owner_display_name"),
        "target_metric": row.get("target_metric"),
        "target_value": row.get("target_value"),
        "deadline": _iso(row.get("deadline")),
        "confidence_at_commit": row.get("confidence_at_commit"),
        "status": row.get("status"),
        "actual_outcome": row.get("actual_outcome"),
        "actual_outcome_recorded_at": _iso(row.get("actual_outcome_recorded_at")),
        "calibration_score": row.get("calibration_score"),
        "notes": row.get("notes"),
        "created_at": _iso(row.get("created_at")),
        "updated_at": _iso(row.get("updated_at")),
        # Computed fields the UI uses (not persisted)
        "overdue": overdue,
        "days_to_deadline": days_to_deadline,
    }


def _fetch_decision(db: Database, decision_id: str) -> Optional[dict]:
    try:
        return db.fetch_one(
            f"SELECT {_DECISION_COLS} FROM decisions WHERE id::text = %s",
            [decision_id],
        )
    except Exception:
        logger.exception("decision fetch failed")
        return None


def _parse_deadline(raw: Optional[str]) -> Optional[date]:
    """Parse YYYY-MM-DD; reject obviously bad input.

    Returns None for None/empty (caller decides whether that means
    'clear' or 'unset'). Allows past dates (Phase D may need to set them
    retroactively); only rejects malformed strings.
    """
    if raw is None or raw == "":
        return None
    try:
        return datetime.fromisoformat(raw).date()
    except Exception:
        raise HTTPException(400, f"deadline must be YYYY-MM-DD (got: {raw!r})")


def _round_with_room(db: Database, round_id: str) -> Optional[dict]:
    """Pull the round + parent room (for owner check + snapshot)."""
    try:
        return db.fetch_one(
            """SELECT r.id AS round_id, r.war_room_id, r.move_type,
                      r.move_payload, w.owner_user_id, w.title AS room_title,
                      w.source_signal_id
               FROM war_room_rounds r
               JOIN war_rooms w ON w.id = r.war_room_id
               WHERE r.id::text = %s""",
            [round_id],
        )
    except Exception:
        logger.exception("round+room fetch failed")
        return None


def _mean_confidence(db: Database, round_id: str) -> Optional[float]:
    """Mean of confidence_score over the round's reactions, NULL-safe."""
    try:
        row = db.fetch_one(
            """SELECT AVG(confidence_score) AS avg_conf
               FROM war_room_reactions
               WHERE round_id = %s::uuid AND confidence_score IS NOT NULL""",
            [round_id],
        )
    except Exception:
        return None
    if not row or row.get("avg_conf") is None:
        return None
    try:
        return float(row["avg_conf"])
    except (TypeError, ValueError):
        return None


# ────────────────────────────────────────────────────────────────────
# POST /decisions/from-round/{round_id}
# ────────────────────────────────────────────────────────────────────

@router.post("/from-round/{round_id}", status_code=201)
def promote_round(
    round_id: str,
    body: PromoteBody,
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    """Promote a war-room round to a committed decision.

    Snapshots the round's move_type, move_payload, and mean confidence
    score so the ledger entry is immutable even if the source room is
    later edited or archived.
    """
    deadline = _parse_deadline(body.deadline)

    rnd = _round_with_room(db, round_id)
    if not rnd:
        raise HTTPException(404, f"round not found: {round_id}")
    if str(rnd.get("owner_user_id")) != str(user.get("id")):
        raise HTTPException(403, "only the room owner can promote a round")

    confidence = _mean_confidence(db, round_id)
    payload_snapshot = rnd.get("move_payload") or {}
    if isinstance(payload_snapshot, str):
        try:
            payload_snapshot = json.loads(payload_snapshot)
        except Exception:
            payload_snapshot = {}

    owner_name = (
        body.owner_display_name
        or user.get("display_name")
        or user.get("email", "").split("@")[0]
        or "owner"
    )

    try:
        new = db.fetch_one(
            f"""INSERT INTO decisions
                    (war_room_round_id, war_room_id, source_signal_id,
                     title, rationale, move_type, move_payload_snapshot,
                     owner_user_id, owner_display_name,
                     target_metric, target_value, deadline,
                     confidence_at_commit, status)
                VALUES (%s::uuid, %s::uuid, %s,
                        %s, %s, %s, %s::jsonb,
                        %s::uuid, %s,
                        %s, %s, %s,
                        %s, 'open')
                RETURNING {_DECISION_COLS}""",
            [
                round_id, str(rnd["war_room_id"]), rnd.get("source_signal_id"),
                body.title, body.rationale, rnd["move_type"], json.dumps(payload_snapshot),
                user.get("id"), owner_name,
                body.target_metric, body.target_value, deadline,
                confidence,
            ],
        )
    except Exception as exc:
        logger.exception("decision insert failed")
        raise HTTPException(500, f"promote failed: {exc}") from exc

    if not new:
        raise HTTPException(500, "decision insert succeeded but RETURNING was empty")
    return _decision_to_dict(new)


# ────────────────────────────────────────────────────────────────────
# GET /decisions — list current user's
# ────────────────────────────────────────────────────────────────────

@router.get("")
def list_decisions(
    status: Optional[str] = Query(default=None),
    war_room_id: Optional[str] = Query(default=None),
    overdue: Optional[bool] = Query(default=None),
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    where = ["owner_user_id = %s::uuid"]
    params: list[Any] = [user.get("id")]

    if status:
        if status not in VALID_STATUSES:
            raise HTTPException(400, f"invalid status: {status}")
        where.append("status = %s")
        params.append(status)

    if war_room_id:
        where.append("war_room_id::text = %s")
        params.append(war_room_id)

    if overdue is True:
        # Past deadline + still open/in_progress
        where.append("deadline IS NOT NULL AND deadline < CURRENT_DATE")
        where.append("status IN ('open', 'in_progress')")

    sql = (
        f"SELECT {_DECISION_COLS} FROM decisions "
        f"WHERE {' AND '.join(where)} "
        "ORDER BY "
        "  CASE status WHEN 'open' THEN 0 WHEN 'in_progress' THEN 1 ELSE 2 END, "
        "  deadline NULLS LAST, created_at DESC"
    )
    try:
        rows = db.fetch_all(sql, params)
    except Exception:
        logger.exception("decision list query failed")
        rows = []
    return {"decisions": [_decision_to_dict(r) for r in rows]}


# ────────────────────────────────────────────────────────────────────
# GET /decisions/{id} — anon (shareable like war rooms)
# ────────────────────────────────────────────────────────────────────

@router.get("/{decision_id}")
def get_decision(decision_id: str, db: Database = Depends(get_db)):
    row = _fetch_decision(db, decision_id)
    if not row:
        raise HTTPException(404, f"decision not found: {decision_id}")
    return _decision_to_dict(row)


# ────────────────────────────────────────────────────────────────────
# PATCH /decisions/{id} — owner
# ────────────────────────────────────────────────────────────────────

@router.patch("/{decision_id}")
def patch_decision(
    decision_id: str,
    body: PatchDecisionBody,
    user: Optional[dict] = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    if user is None:
        raise HTTPException(401, "authentication required")

    row = _fetch_decision(db, decision_id)
    if not row:
        raise HTTPException(404, f"decision not found: {decision_id}")
    if str(row.get("owner_user_id")) != str(user.get("id")):
        raise HTTPException(403, "only the decision owner can update")

    sets: list[str] = []
    params: list[Any] = []

    if body.status is not None:
        if body.status not in VALID_STATUSES:
            raise HTTPException(400, f"invalid status: {body.status}")
        sets.append("status = %s")
        params.append(body.status)

    if body.notes is not None:
        sets.append("notes = %s")
        params.append(body.notes)

    if body.deadline is not None:
        # Empty string clears the deadline; otherwise parse strictly
        if body.deadline == "":
            sets.append("deadline = NULL")
        else:
            d = _parse_deadline(body.deadline)
            sets.append("deadline = %s")
            params.append(d)

    if body.target_metric is not None:
        sets.append("target_metric = %s")
        params.append(body.target_metric)

    if body.target_value is not None:
        sets.append("target_value = %s")
        params.append(body.target_value)

    if body.actual_outcome is not None:
        sets.append("actual_outcome = %s")
        sets.append("actual_outcome_recorded_at = NOW()")
        params.append(body.actual_outcome)

    if not sets:
        return _decision_to_dict(row)

    sets.append("updated_at = NOW()")
    sql = f"UPDATE decisions SET {', '.join(sets)} WHERE id::text = %s"
    params.append(decision_id)

    try:
        db.execute(sql, params)
    except Exception as exc:
        logger.exception("decision patch failed")
        raise HTTPException(500, f"patch failed: {exc}") from exc

    updated = _fetch_decision(db, decision_id)
    return _decision_to_dict(updated) if updated else _decision_to_dict(row)


# ────────────────────────────────────────────────────────────────────
# DELETE /decisions/{id} — owner (hard delete; rare)
# ────────────────────────────────────────────────────────────────────

@router.delete("/{decision_id}", status_code=204)
def delete_decision(
    decision_id: str,
    user: Optional[dict] = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    if user is None:
        raise HTTPException(401, "authentication required")

    row = _fetch_decision(db, decision_id)
    if not row:
        raise HTTPException(404, f"decision not found: {decision_id}")
    if str(row.get("owner_user_id")) != str(user.get("id")):
        raise HTTPException(403, "only the decision owner can delete")

    try:
        db.execute(
            "DELETE FROM decisions WHERE id::text = %s",
            [decision_id],
        )
    except Exception as exc:
        logger.exception("decision delete failed")
        raise HTTPException(500, f"delete failed: {exc}") from exc

    return Response(status_code=204)
