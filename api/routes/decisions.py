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
from services.calibration_math import compute_numeric_calibration
from services.outcome_detector import (
    DETECTOR_RULE_VERSION,
    compute_calibration_score,
    match_signals_to_decision,
    suggest_weight_delta,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/decisions", tags=["decisions"])


VALID_STATUSES = ("open", "in_progress", "verified", "missed", "cancelled")
VALID_OUTCOME_VERDICTS = ("verified", "missed", "cancelled")


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


class CaptureOutcomeBody(BaseModel):
    signal_id: str
    verdict: str
    actual_outcome: str = Field(min_length=1, max_length=4000)
    notes: Optional[str] = Field(default=None, max_length=4000)


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
    response: Response,
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    """Promote a war-room round to a committed decision.

    Snapshots the round's move_type, move_payload, and mean confidence
    score so the ledger entry is immutable even if the source room is
    later edited or archived.

    Idempotent: a second POST for the same round_id returns the
    existing decision with HTTP 200 (not 201). Enforced by the
    UNIQUE partial index on `decisions(war_room_round_id)` from
    migration 051.
    """
    deadline = _parse_deadline(body.deadline)

    rnd = _round_with_room(db, round_id)
    if not rnd:
        raise HTTPException(404, f"round not found: {round_id}")
    if str(rnd.get("owner_user_id")) != str(user.get("id")):
        raise HTTPException(403, "only the room owner can promote a round")

    # Idempotency check — return existing decision if this round was
    # already promoted (UNIQUE index will reject on INSERT either way,
    # but we'd rather not hit the constraint when we can short-circuit).
    try:
        existing = db.fetch_one(
            f"SELECT {_DECISION_COLS} FROM decisions WHERE war_room_round_id = %s::uuid",
            [round_id],
        )
    except Exception:
        existing = None
    if existing:
        response.status_code = 200
        return _decision_to_dict(existing)

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

    # When an outcome is recorded together with (or onto) a terminal
    # verdict, compute the calibration_score so the learning loop has its
    # input. Previously PATCH left calibration NULL — the decision then
    # never reached find_decisions_with_outcomes and the Learn arc stayed
    # open. (capture-outcome already did this; PATCH is the simpler path
    # users actually hit, so it must close the loop too.) F6/C6.
    cal_score: Optional[float] = None
    if body.actual_outcome is not None:
        sets.append("actual_outcome = %s")
        sets.append("actual_outcome_recorded_at = NOW()")
        params.append(body.actual_outcome)

        # Effective verdict = the status being set, else the current status.
        verdict = body.status if body.status is not None else row.get("status")
        if verdict in VALID_OUTCOME_VERDICTS:
            numeric_cal = compute_numeric_calibration(
                target_value=(
                    body.target_value if body.target_value is not None
                    else row.get("target_value")
                ),
                actual_outcome=body.actual_outcome,
            )
            cal_score = numeric_cal if numeric_cal is not None else compute_calibration_score(
                verdict=verdict,
                confidence_at_commit=row.get("confidence_at_commit"),
            )
            sets.append("calibration_score = %s")
            params.append(cal_score)

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

    # Close the loop: a recorded outcome with calibration emits a learning
    # row (signal_score_adjustments) immediately — not just on the next
    # scheduler tick. Idempotent + best-effort: outcome capture must not
    # fail if learning emission does.
    if cal_score is not None and updated:
        try:
            from services.learning_service import emit_signal_score_adjustment
            emit_signal_score_adjustment(
                db, decision=updated, calibration_score=cal_score,
            )
        except Exception:
            logger.warning("learning emission failed for decision %s", decision_id, exc_info=True)

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


# ────────────────────────────────────────────────────────────────────
# Phase D — outcome detection + capture
# ────────────────────────────────────────────────────────────────────

def _entity_id_for_decision(db: Database, decision: dict) -> Optional[str]:
    """Decisions don't carry primary_entity_id — pull it from the
    source war_room. Falls back to None if the war_room is gone (FK
    SET NULL)."""
    war_room_id = decision.get("war_room_id")
    if not war_room_id:
        return None
    try:
        row = db.fetch_one(
            "SELECT primary_entity_id FROM war_rooms WHERE id::text = %s",
            [str(war_room_id)],
        )
    except Exception:
        return None
    return row.get("primary_entity_id") if row else None


@router.post("/{decision_id}/suggest-outcome")
def suggest_outcome(
    decision_id: str,
    user: Optional[dict] = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Run the outcome matcher for a decision; return ranked candidates.

    Owner-only. The matcher reads from the live `signals` table — what
    DataSteward has surfaced — and scores each candidate signal on
    entity overlap, KBQ overlap, and temporal proximity to the
    decision's window. Threshold and cap defined in
    `services.outcome_detector`.
    """
    if user is None:
        raise HTTPException(401, "authentication required")

    decision = _fetch_decision(db, decision_id)
    if not decision:
        raise HTTPException(404, f"decision not found: {decision_id}")
    if str(decision.get("owner_user_id")) != str(user.get("id")):
        raise HTTPException(403, "only the decision owner can detect outcomes")

    entity_id = _entity_id_for_decision(db, decision)

    candidates = match_signals_to_decision(
        db,
        decision=decision,
        entity_id_for_matching=entity_id,
    )

    return {
        "decision_id": decision_id,
        "rule_version_id": DETECTOR_RULE_VERSION,
        "candidates": candidates,
        "count": len(candidates),
    }


@router.post("/{decision_id}/capture-outcome")
def capture_outcome(
    decision_id: str,
    body: CaptureOutcomeBody,
    force: bool = Query(default=False, description="Override 409 if already captured"),
    user: Optional[dict] = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Record the actual outcome for a decision and compute calibration.

    Writes:
      - decisions.actual_outcome, actual_outcome_recorded_at, status,
        calibration_score
      - signal_score_adjustments row (one per capture) — feeds D Phase 2
        recalibration job

    Idempotent guard: once `actual_outcome_recorded_at` is set, returns
    409 unless `?force=true` (owner-only escape hatch for typo correction).
    """
    if user is None:
        raise HTTPException(401, "authentication required")

    if body.verdict not in VALID_OUTCOME_VERDICTS:
        raise HTTPException(
            400,
            f"verdict must be one of {VALID_OUTCOME_VERDICTS} (got {body.verdict!r})",
        )

    decision = _fetch_decision(db, decision_id)
    if not decision:
        raise HTTPException(404, f"decision not found: {decision_id}")
    if str(decision.get("owner_user_id")) != str(user.get("id")):
        raise HTTPException(403, "only the decision owner can capture outcomes")

    if decision.get("actual_outcome_recorded_at") and not force:
        raise HTTPException(
            409,
            "Outcome already captured for this decision. "
            "Pass ?force=true to overwrite (owner-only).",
        )

    # Verify the signal exists (cheap lookup; we also pull rule_version
    # + kbq_tags for the learning-ledger row)
    try:
        sig = db.fetch_one(
            """SELECT id, kbq_tags, rule_version_id, primary_entity_name
               FROM signals WHERE id::text = %s""",
            [body.signal_id],
        )
    except Exception:
        sig = None
    if not sig:
        raise HTTPException(400, f"signal_id {body.signal_id} not found")

    # Calibration math — try numeric first (D2 upgrade), fall back to
    # the categorical heuristic from D MVP when target_value can't be parsed
    # or the actual_outcome is free text we can't extract a magnitude from.
    confidence = decision.get("confidence_at_commit")
    numeric_cal = compute_numeric_calibration(
        target_value=decision.get("target_value"),
        actual_outcome=body.actual_outcome,
    )
    if numeric_cal is not None:
        cal_score = numeric_cal
    else:
        cal_score = compute_calibration_score(
            verdict=body.verdict,
            confidence_at_commit=confidence,
        )
    delta = suggest_weight_delta(calibration_score=cal_score, verdict=body.verdict)

    # Update the decision
    try:
        db.execute(
            """UPDATE decisions
               SET actual_outcome = %s,
                   actual_outcome_recorded_at = NOW(),
                   status = %s,
                   calibration_score = %s,
                   notes = COALESCE(%s, notes),
                   updated_at = NOW()
               WHERE id::text = %s""",
            [
                body.actual_outcome,
                body.verdict,
                cal_score,
                body.notes,
                decision_id,
            ],
        )
    except Exception as exc:
        logger.exception("decision outcome update failed")
        raise HTTPException(500, f"outcome update failed: {exc}") from exc

    # Append to learning ledger — one row per kbq_tag of the matched
    # signal, since weights are per-(rule_version, kbq_tag).
    rule_version = sig.get("rule_version_id") or "unknown"
    kbq_tags = list(sig.get("kbq_tags") or [])
    if not kbq_tags:
        kbq_tags = ["uncategorized"]
    for tag in kbq_tags:
        try:
            db.execute(
                """INSERT INTO signal_score_adjustments
                       (rule_version_id, kbq_tag, decision_id,
                        matched_signal_id, calibration_score,
                        weight_delta_suggested, notes)
                   VALUES (%s, %s, %s::uuid, %s::uuid, %s, %s, %s)""",
                [
                    rule_version, tag, decision_id, body.signal_id,
                    cal_score, delta, body.notes,
                ],
            )
        except Exception as exc:
            # Non-fatal — outcome is captured even if the learning row fails.
            logger.warning("signal_score_adjustments insert failed (kbq=%s): %s", tag, exc)

    updated = _fetch_decision(db, decision_id)
    return _decision_to_dict(updated) if updated else _decision_to_dict(decision)


# ────────────────────────────────────────────────────────────────────
# E — single-call detail bundle for the full Decision Detail page
# ────────────────────────────────────────────────────────────────────

@router.get("/{decision_id}/full")
def get_decision_full(decision_id: str, db: Database = Depends(get_db)):
    """Single-response bundle for the Decision Detail page.

    Returns the decision + war_room summary + source signal headline +
    comments scoped to the decision's war_room + pending proposals.
    Anon read so URLs are shareable. Replaces 4-5 client waterfall
    requests with one round-trip.
    """
    decision = _fetch_decision(db, decision_id)
    if not decision:
        raise HTTPException(404, f"decision not found: {decision_id}")

    out = _decision_to_dict(decision)

    # War room summary (light — title, primary_entity, source_signal_id)
    war_room_summary = None
    war_room_id = decision.get("war_room_id")
    if war_room_id:
        try:
            wr = db.fetch_one(
                """SELECT id, title, primary_entity_type, primary_entity_id,
                          primary_entity_name, source_signal_id, status,
                          archived_at
                   FROM war_rooms WHERE id::text = %s""",
                [str(war_room_id)],
            )
        except Exception:
            wr = None
        if wr:
            war_room_summary = {
                "id": str(wr["id"]),
                "title": wr.get("title"),
                "primary_entity_name": wr.get("primary_entity_name"),
                "primary_entity_id": wr.get("primary_entity_id"),
                "primary_entity_type": wr.get("primary_entity_type"),
                "source_signal_id": str(wr["source_signal_id"]) if wr.get("source_signal_id") else None,
                "status": wr.get("status"),
                "archived_at": _iso(wr.get("archived_at")),
            }
    out["war_room"] = war_room_summary

    # Source signal (the seed — what triggered the war room → decision chain)
    source_signal = None
    sig_id = decision.get("source_signal_id") or (war_room_summary and war_room_summary.get("source_signal_id"))
    if sig_id:
        try:
            sig = db.fetch_one(
                """SELECT id, headline, summary, kbq_tags, primary_entity_name,
                          confidence_tier, impact_tier, created_at
                   FROM signals WHERE id::text = %s""",
                [str(sig_id)],
            )
        except Exception:
            sig = None
        if sig:
            source_signal = {
                "id": str(sig["id"]),
                "headline": sig.get("headline"),
                "summary": sig.get("summary"),
                "kbq_tags": list(sig.get("kbq_tags") or []),
                "primary_entity_name": sig.get("primary_entity_name"),
                "confidence_tier": sig.get("confidence_tier"),
                "impact_tier": sig.get("impact_tier"),
                "created_at": _iso(sig.get("created_at")),
            }
    out["source_signal"] = source_signal

    # Comments scoped to the source war room (Phase B reused — comment
    # threads aren't decision-scoped in MVP since the discussion really
    # belongs to the room that produced the decision)
    comments = []
    if war_room_id:
        try:
            rows = db.fetch_all(
                """SELECT id, war_room_id, round_id, author_user_id,
                          author_display_name, body, created_at, edited_at
                   FROM war_room_comments
                   WHERE war_room_id = %s::uuid
                   ORDER BY created_at ASC""",
                [str(war_room_id)],
            ) or []
        except Exception:
            rows = []
        comments = [{
            "id": str(r.get("id")),
            "war_room_id": str(r.get("war_room_id")),
            "round_id": str(r["round_id"]) if r.get("round_id") else None,
            "author_user_id": str(r["author_user_id"]) if r.get("author_user_id") else None,
            "author_display_name": r.get("author_display_name"),
            "body": r.get("body"),
            "created_at": _iso(r.get("created_at")),
            "edited_at": _iso(r.get("edited_at")),
        } for r in rows]
    out["comments"] = comments

    # Pending outcome proposals
    try:
        prop_rows = db.fetch_all(
            """SELECT p.id, p.matched_signal_id, p.match_score,
                      p.match_components, p.proposed_at,
                      s.headline AS signal_headline,
                      s.summary AS signal_summary,
                      s.kbq_tags AS signal_kbq_tags,
                      s.primary_entity_name AS signal_entity
               FROM outcome_proposals p
               LEFT JOIN signals s ON s.id = p.matched_signal_id
               WHERE p.decision_id::text = %s AND p.status = 'pending'
               ORDER BY p.match_score DESC""",
            [decision_id],
        ) or []
    except Exception:
        prop_rows = []
    proposals = []
    for r in prop_rows:
        components = r.get("match_components") or {}
        if isinstance(components, str):
            try:
                components = json.loads(components)
            except Exception:
                components = {}
        proposals.append({
            "id": str(r.get("id")),
            "matched_signal_id": str(r.get("matched_signal_id")),
            "match_score": r.get("match_score"),
            "match_components": components,
            "proposed_at": _iso(r.get("proposed_at")),
            "signal_headline": r.get("signal_headline"),
            "signal_summary": r.get("signal_summary"),
            "signal_kbq_tags": list(r.get("signal_kbq_tags") or []),
            "signal_entity": r.get("signal_entity"),
        })
    out["pending_proposals"] = proposals

    return out


# ────────────────────────────────────────────────────────────────────
# D2 — outcome_proposals (autonomous detection awaiting confirm)
# ────────────────────────────────────────────────────────────────────

def _proposal_to_dict(row: dict) -> dict:
    components = row.get("match_components") or {}
    if isinstance(components, str):
        try:
            components = json.loads(components)
        except Exception:
            components = {}
    return {
        "id": str(row.get("id")),
        "decision_id": str(row.get("decision_id")),
        "matched_signal_id": str(row.get("matched_signal_id")),
        "match_score": row.get("match_score"),
        "match_components": components,
        "status": row.get("status"),
        "proposed_at": _iso(row.get("proposed_at")),
        "resolved_at": _iso(row.get("resolved_at")),
        "resolved_by": str(row["resolved_by"]) if row.get("resolved_by") else None,
        # Joined signal fields for the UI
        "signal_headline": row.get("signal_headline"),
        "signal_summary": row.get("signal_summary"),
        "signal_kbq_tags": list(row.get("signal_kbq_tags") or []),
        "signal_primary_entity_name": row.get("signal_primary_entity_name"),
        "signal_created_at": _iso(row.get("signal_created_at")),
    }


@router.get("/{decision_id}/proposals")
def list_proposals(
    decision_id: str,
    status: Optional[str] = Query(default="pending"),
    db: Database = Depends(get_db),
):
    """List autonomous outcome-detection proposals for a decision.
    Anon read so share-by-URL keeps working. Default filter: pending."""
    if not _fetch_decision(db, decision_id):
        raise HTTPException(404, f"decision not found: {decision_id}")

    if status and status not in ("pending", "confirmed", "dismissed", "all"):
        raise HTTPException(400, f"invalid status: {status}")

    where = ["p.decision_id = %s::uuid"]
    params: list[Any] = [decision_id]
    if status and status != "all":
        where.append("p.status = %s")
        params.append(status)

    sql = f"""
        SELECT p.id, p.decision_id, p.matched_signal_id, p.match_score,
               p.match_components, p.status, p.proposed_at, p.resolved_at,
               p.resolved_by,
               s.headline AS signal_headline, s.summary AS signal_summary,
               s.kbq_tags AS signal_kbq_tags,
               s.primary_entity_name AS signal_primary_entity_name,
               s.created_at AS signal_created_at
        FROM outcome_proposals p
        LEFT JOIN signals s ON s.id = p.matched_signal_id
        WHERE {' AND '.join(where)}
        ORDER BY p.match_score DESC, p.proposed_at DESC
    """
    try:
        rows = db.fetch_all(sql, params)
    except Exception:
        logger.exception("list_proposals query failed")
        rows = []

    return {
        "decision_id": decision_id,
        "proposals": [_proposal_to_dict(r) for r in rows],
        "count": len(rows),
    }


@router.post("/{decision_id}/proposals/{proposal_id}/confirm")
def confirm_proposal(
    decision_id: str,
    proposal_id: str,
    body: CaptureOutcomeBody = None,  # type: ignore[assignment]
    user: Optional[dict] = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Owner accepts a proposal — calls capture_outcome internally with
    the proposal's signal_id, then marks the proposal confirmed.

    Body fields are optional: defaults pull from the proposed signal's
    headline (actual_outcome) and verdict='verified'.
    """
    if user is None:
        raise HTTPException(401, "authentication required")

    decision = _fetch_decision(db, decision_id)
    if not decision:
        raise HTTPException(404, f"decision not found: {decision_id}")
    if str(decision.get("owner_user_id")) != str(user.get("id")):
        raise HTTPException(403, "only the decision owner can confirm")

    try:
        prop = db.fetch_one(
            """SELECT p.id, p.matched_signal_id, p.status,
                      s.headline AS signal_headline,
                      s.kbq_tags AS signal_kbq_tags,
                      s.rule_version_id AS signal_rule_version
               FROM outcome_proposals p
               LEFT JOIN signals s ON s.id = p.matched_signal_id
               WHERE p.id::text = %s AND p.decision_id::text = %s""",
            [proposal_id, decision_id],
        )
    except Exception:
        prop = None
    if not prop:
        raise HTTPException(404, f"proposal not found: {proposal_id}")
    if prop.get("status") != "pending":
        raise HTTPException(409, f"proposal already resolved (status={prop.get('status')})")

    # Build the capture body — caller may override
    actual = (body.actual_outcome if body else None) or prop.get("signal_headline") or ""
    verdict = (body.verdict if body else None) or "verified"
    if verdict not in VALID_OUTCOME_VERDICTS:
        raise HTTPException(400, f"invalid verdict: {verdict}")

    # Compute calibration (numeric first)
    numeric_cal = compute_numeric_calibration(
        target_value=decision.get("target_value"),
        actual_outcome=actual,
    )
    cal_score = numeric_cal if numeric_cal is not None else compute_calibration_score(
        verdict=verdict, confidence_at_commit=decision.get("confidence_at_commit"),
    )
    delta = suggest_weight_delta(calibration_score=cal_score, verdict=verdict)

    notes = body.notes if body else None
    sig_id = str(prop["matched_signal_id"])
    rule_version = prop.get("signal_rule_version") or "unknown"
    kbq_tags = list(prop.get("signal_kbq_tags") or []) or ["uncategorized"]

    try:
        db.execute(
            """UPDATE decisions
                  SET actual_outcome = %s,
                      actual_outcome_recorded_at = NOW(),
                      status = %s,
                      calibration_score = %s,
                      notes = COALESCE(%s, notes),
                      updated_at = NOW()
                WHERE id::text = %s""",
            [actual, verdict, cal_score, notes, decision_id],
        )
    except Exception as exc:
        logger.exception("confirm_proposal: decision update failed")
        raise HTTPException(500, f"capture failed: {exc}") from exc

    # Learning ledger rows
    for tag in kbq_tags:
        try:
            db.execute(
                """INSERT INTO signal_score_adjustments
                       (rule_version_id, kbq_tag, decision_id,
                        matched_signal_id, calibration_score,
                        weight_delta_suggested, notes)
                   VALUES (%s, %s, %s::uuid, %s::uuid, %s, %s, %s)""",
                [rule_version, tag, decision_id, sig_id, cal_score, delta, notes],
            )
        except Exception as exc:
            logger.warning("signal_score_adjustments insert failed (kbq=%s): %s", tag, exc)

    # Mark the proposal resolved
    try:
        db.execute(
            """UPDATE outcome_proposals
               SET status = 'confirmed', resolved_at = NOW(), resolved_by = %s::uuid
               WHERE id::text = %s""",
            [user.get("id"), proposal_id],
        )
    except Exception:
        logger.exception("confirm_proposal: status update failed")

    updated = _fetch_decision(db, decision_id)
    return _decision_to_dict(updated) if updated else _decision_to_dict(decision)


@router.post("/{decision_id}/proposals/{proposal_id}/dismiss")
def dismiss_proposal(
    decision_id: str,
    proposal_id: str,
    user: Optional[dict] = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Owner rejects a proposal — won't be re-proposed (UNIQUE on
    decision_id+matched_signal_id ensures the scheduler skips it
    next tick because of ON CONFLICT DO NOTHING)."""
    if user is None:
        raise HTTPException(401, "authentication required")

    decision = _fetch_decision(db, decision_id)
    if not decision:
        raise HTTPException(404, f"decision not found: {decision_id}")
    if str(decision.get("owner_user_id")) != str(user.get("id")):
        raise HTTPException(403, "only the decision owner can dismiss")

    try:
        prop = db.fetch_one(
            """SELECT id, status FROM outcome_proposals
               WHERE id::text = %s AND decision_id::text = %s""",
            [proposal_id, decision_id],
        )
    except Exception:
        prop = None
    if not prop:
        raise HTTPException(404, f"proposal not found: {proposal_id}")
    if prop.get("status") != "pending":
        raise HTTPException(409, f"proposal already resolved (status={prop.get('status')})")

    try:
        db.execute(
            """UPDATE outcome_proposals
               SET status = 'dismissed', resolved_at = NOW(), resolved_by = %s::uuid
               WHERE id::text = %s""",
            [user.get("id"), proposal_id],
        )
    except Exception as exc:
        logger.exception("dismiss_proposal failed")
        raise HTTPException(500, f"dismiss failed: {exc}") from exc

    return Response(status_code=204)
