"""SPEC-021 — War Room API.

CRUD over war_rooms + the run-round endpoint that generates competitor
reactions. Mutations are owner-only; reads are anonymous (so a war
room URL is shareable).
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from api.deps import get_current_user, get_db, get_llm, require_role
from db import Database
from services.move_suggester import (
    SUGGESTER_RULE_VERSION,
    suggest_moves as _engine_suggest_moves,
)
from services.war_game_engine import (
    MOVE_TYPES,
    generate_reactions as _engine_generate,
    is_valid_move_type,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/war-rooms", tags=["war-room"])


# ────────────────────────────────────────────────────────────────────
# Schemas
# ────────────────────────────────────────────────────────────────────

class CreateRoomBody(BaseModel):
    title: str
    scenario_question: Optional[str] = None
    primary_entity_type: Optional[str] = None
    primary_entity_id: Optional[str] = None
    primary_entity_name: Optional[str] = None
    source_signal_id: Optional[str] = None
    game_phase: str = "launch"


class RoundBody(BaseModel):
    move_type: str
    move_payload: dict = {}
    notes: Optional[str] = None
    player_company_id: Optional[str] = None
    player_company_name: Optional[str] = None


class SuggestMovesBody(BaseModel):
    n: int = 3
    signal_context: Optional[dict] = None


# ────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────

def _iso(v):
    if v is None:
        return None
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return str(v)


def _room_to_dict(row: dict) -> dict:
    return {
        "id": str(row.get("id")),
        "title": row.get("title"),
        "owner_user_id": str(row["owner_user_id"]) if row.get("owner_user_id") else None,
        "scenario_question": row.get("scenario_question"),
        "primary_entity_type": row.get("primary_entity_type"),
        "primary_entity_id": row.get("primary_entity_id"),
        "primary_entity_name": row.get("primary_entity_name"),
        "source_signal_id": str(row["source_signal_id"]) if row.get("source_signal_id") else None,
        "game_phase": row.get("game_phase"),
        "status": row.get("status"),
        "created_at": _iso(row.get("created_at")),
        "updated_at": _iso(row.get("updated_at")),
    }


def _round_to_dict(row: dict) -> dict:
    payload = row.get("move_payload") or {}
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            payload = {}
    return {
        "id": str(row.get("id")),
        "war_room_id": str(row.get("war_room_id")),
        "round_number": row.get("round_number"),
        "player_company_id": str(row["player_company_id"]) if row.get("player_company_id") else None,
        "player_company_name": row.get("player_company_name"),
        "move_type": row.get("move_type"),
        "move_payload": payload,
        "notes": row.get("notes"),
        "created_at": _iso(row.get("created_at")),
    }


def _reaction_to_dict(row: dict) -> dict:
    asset = row.get("asset_leveraged")
    if isinstance(asset, str):
        try:
            asset = json.loads(asset)
        except Exception:
            asset = None
    scores = row.get("scores")
    if isinstance(scores, str):
        try:
            scores = json.loads(scores)
        except Exception:
            scores = {}
    return {
        "id": str(row.get("id")),
        "round_id": str(row.get("round_id")),
        "competitor_company_id": (
            str(row["competitor_company_id"])
            if row.get("competitor_company_id") else None
        ),
        "competitor_company_name": row.get("competitor_company_name"),
        "reaction_type": row.get("reaction_type"),
        "headline": row.get("headline"),
        "specific_action": row.get("specific_action"),
        "asset_leveraged": asset,
        "rationale": row.get("rationale"),
        "evidence_basis": list(row.get("evidence_basis") or []),
        "stripped_citations": list(row.get("stripped_citations") or []),
        "evidence_validated": bool(row.get("evidence_validated", True)),
        "scores": scores or {},
        "confidence_score": row.get("confidence_score"),
        "confidence": row.get("confidence"),
        "created_at": _iso(row.get("created_at")),
    }


def _fetch_room(db: Database, room_id: str) -> Optional[dict]:
    try:
        return db.fetch_one(
            """SELECT id, title, owner_user_id, scenario_question,
                      primary_entity_type, primary_entity_id, primary_entity_name,
                      source_signal_id, game_phase, status, created_at, updated_at
               FROM war_rooms WHERE id::text = %s""",
            [room_id],
        )
    except Exception:
        logger.exception("war room fetch failed")
        return None


def _fetch_competitors(
    db: Database,
    exclude_company_id: Optional[str],
    exclude_company_name: Optional[str] = None,
    *,
    limit: int = 4,
) -> list[dict]:
    """Pick top-N competitor companies for the simulation.

    Heuristic: companies with the most drugs (rough proxy for competitive
    relevance). Excludes the player by id when available, otherwise by
    ILIKE on name (handles the demo case where the player isn't a real
    DB company id).
    """
    name_pattern = None
    if exclude_company_name:
        # Match either direction: stored name contains player or vice-versa
        # Take the first 2-3 distinct word(s) for fuzzy match (e.g. "Novo Nordisk Inc"
        # matches "Novo Nordisk")
        first_words = " ".join(exclude_company_name.split()[:2])
        name_pattern = f"%{first_words}%"

    try:
        rows = db.fetch_all(
            """SELECT c.id::text AS id, c.name, COUNT(d.id) AS drug_count
               FROM companies c
               LEFT JOIN drugs d ON d.company_id = c.id
               WHERE (%s::text IS NULL OR c.id::text != %s)
                 AND (%s::text IS NULL OR c.name NOT ILIKE %s)
               GROUP BY c.id, c.name
               HAVING COUNT(d.id) > 0
               ORDER BY drug_count DESC NULLS LAST
               LIMIT %s""",
            [
                exclude_company_id, exclude_company_id,
                name_pattern, name_pattern,
                limit,
            ],
        )
        return [{"id": r["id"], "name": r["name"]} for r in (rows or [])]
    except Exception:
        logger.debug("competitor fetch failed; returning empty list")
        return []


# Stubable — tests patch this name
def _generate_reactions(db, llm, *, player_name, move_type, move_payload,
                        competitors, game_phase, history):
    return _engine_generate(
        db, llm,
        player_name=player_name,
        move_type=move_type,
        move_payload=move_payload,
        competitors=competitors,
        game_phase=game_phase,
        history=history,
    )


# Stubable — tests patch this name
def _suggest_moves(db, llm, *, player_entity_type, player_entity_id, player_name,
                   signal_context, n):
    return _engine_suggest_moves(
        db, llm,
        player_entity_type=player_entity_type,
        player_entity_id=player_entity_id,
        player_name=player_name,
        signal_context=signal_context,
        n=n,
    )


# ────────────────────────────────────────────────────────────────────
# POST /war-rooms — create
# ────────────────────────────────────────────────────────────────────

@router.post("", status_code=201)
def create_room(
    body: CreateRoomBody,
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    if body.game_phase not in ("prelaunch", "launch", "postlaunch"):
        raise HTTPException(400, f"invalid game_phase: {body.game_phase}")

    try:
        db.execute(
            """INSERT INTO war_rooms
                   (title, owner_user_id, scenario_question,
                    primary_entity_type, primary_entity_id, primary_entity_name,
                    source_signal_id, game_phase)
               VALUES (%s, %s::uuid, %s, %s, %s, %s, %s, %s)""",
            [
                body.title, user.get("id"), body.scenario_question,
                body.primary_entity_type, body.primary_entity_id,
                body.primary_entity_name, body.source_signal_id,
                body.game_phase,
            ],
        )
    except Exception as exc:
        logger.exception("war room insert failed")
        raise HTTPException(500, f"create failed: {exc}") from exc

    # Read back — most recent room owned by this user with this title
    try:
        row = db.fetch_one(
            """SELECT id, title, owner_user_id, scenario_question,
                      primary_entity_type, primary_entity_id, primary_entity_name,
                      source_signal_id, game_phase, status, created_at, updated_at
               FROM war_rooms
               WHERE owner_user_id = %s::uuid AND title = %s
               ORDER BY created_at DESC LIMIT 1""",
            [user.get("id"), body.title],
        )
    except Exception:
        row = None

    if not row:
        raise HTTPException(500, "create succeeded but read-back failed")
    return _room_to_dict(row)


# ────────────────────────────────────────────────────────────────────
# GET /war-rooms — list (current user's)
# ────────────────────────────────────────────────────────────────────

@router.get("")
def list_rooms(
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    try:
        rows = db.fetch_all(
            """SELECT id, title, owner_user_id, scenario_question,
                      primary_entity_type, primary_entity_id, primary_entity_name,
                      source_signal_id, game_phase, status, created_at, updated_at
               FROM war_rooms
               WHERE owner_user_id = %s::uuid
               ORDER BY created_at DESC""",
            [user.get("id")],
        )
    except Exception:
        rows = []
    return {"war_rooms": [_room_to_dict(r) for r in rows]}


# ────────────────────────────────────────────────────────────────────
# GET /war-rooms/{id} — anon detail
# ────────────────────────────────────────────────────────────────────

@router.get("/{room_id}")
def get_room(room_id: str, db: Database = Depends(get_db)):
    room = _fetch_room(db, room_id)
    if not room:
        raise HTTPException(404, f"war room not found: {room_id}")

    try:
        round_rows = db.fetch_all(
            """SELECT id, war_room_id, round_number, player_company_id,
                      player_company_name, move_type, move_payload, notes, created_at
               FROM war_room_rounds WHERE war_room_id = %s::uuid
               ORDER BY round_number ASC""",
            [room_id],
        ) or []
    except Exception:
        round_rows = []

    rounds_out = []
    for rnd in round_rows:
        rnd_dict = _round_to_dict(rnd)
        try:
            reaction_rows = db.fetch_all(
                """SELECT id, round_id, competitor_company_id, competitor_company_name,
                          reaction_type, headline, specific_action, asset_leveraged,
                          rationale, evidence_basis, stripped_citations,
                          evidence_validated, scores, confidence_score, confidence,
                          created_at
                   FROM war_room_reactions WHERE round_id = %s::uuid
                   ORDER BY created_at ASC""",
                [rnd_dict["id"]],
            ) or []
        except Exception:
            reaction_rows = []
        rnd_dict["reactions"] = [_reaction_to_dict(r) for r in reaction_rows]
        rounds_out.append(rnd_dict)

    out = _room_to_dict(room)
    out["rounds"] = rounds_out
    return out


# ────────────────────────────────────────────────────────────────────
# POST /war-rooms/{id}/rounds — submit player move
# ────────────────────────────────────────────────────────────────────

@router.post("/{room_id}/rounds")
def submit_round(
    room_id: str,
    body: RoundBody,
    user: Optional[dict] = Depends(get_current_user),
    db: Database = Depends(get_db),
    llm = Depends(get_llm),
):
    if user is None:
        raise HTTPException(401, "authentication required")

    if not is_valid_move_type(body.move_type):
        raise HTTPException(
            400,
            f"invalid move_type: {body.move_type} (allowed: {', '.join(MOVE_TYPES)})",
        )

    room = _fetch_room(db, room_id)
    if not room:
        raise HTTPException(404, f"war room not found: {room_id}")
    if str(room.get("owner_user_id")) != str(user.get("id")):
        raise HTTPException(403, "only the room owner can submit moves")

    # Determine round_number = max + 1
    try:
        mx_row = db.fetch_one(
            "SELECT MAX(round_number) AS max_round FROM war_room_rounds WHERE war_room_id = %s::uuid",
            [room_id],
        )
    except Exception:
        mx_row = None
    next_round = (mx_row.get("max_round") if mx_row else 0) or 0
    next_round = int(next_round) + 1

    # Insert round
    try:
        db.execute(
            """INSERT INTO war_room_rounds
                   (war_room_id, round_number, player_company_id,
                    player_company_name, move_type, move_payload, notes)
               VALUES (%s::uuid, %s, %s, %s, %s, %s::jsonb, %s)""",
            [
                room_id, next_round, body.player_company_id,
                body.player_company_name, body.move_type,
                json.dumps(body.move_payload or {}), body.notes,
            ],
        )
    except Exception as exc:
        logger.exception("round insert failed")
        raise HTTPException(500, f"round create failed: {exc}") from exc

    # Read back round id
    try:
        rnd_row = db.fetch_one(
            """SELECT id, war_room_id, round_number, player_company_id,
                      player_company_name, move_type, move_payload, notes, created_at
               FROM war_room_rounds
               WHERE war_room_id = %s::uuid AND round_number = %s""",
            [room_id, next_round],
        )
    except Exception:
        rnd_row = None
    if not rnd_row:
        raise HTTPException(500, "round insert succeeded but read-back failed")
    round_id = str(rnd_row["id"])

    # Pull recent history for prompt context
    try:
        history_rows = db.fetch_all(
            """SELECT round_number, move_type, move_payload, player_company_name
               FROM war_room_rounds
               WHERE war_room_id = %s::uuid AND round_number < %s
               ORDER BY round_number DESC LIMIT 4""",
            [room_id, next_round],
        ) or []
    except Exception:
        history_rows = []
    history = [
        {
            "round": r.get("round_number"),
            "player": r.get("player_company_name"),
            "move_type": r.get("move_type"),
            "move_payload": r.get("move_payload"),
        }
        for r in history_rows
    ]

    competitors = _fetch_competitors(
        db,
        body.player_company_id,
        body.player_company_name or room.get("primary_entity_name"),
    )

    reactions = _generate_reactions(
        db, llm,
        player_name=body.player_company_name or "Player",
        move_type=body.move_type,
        move_payload=body.move_payload or {},
        competitors=competitors,
        game_phase=room.get("game_phase") or "launch",
        history=history,
    )

    # Persist reactions; track partial failures so the UI can surface them
    saved_reactions: list[dict] = []
    persistence_errors: list[dict] = []
    for rxn in reactions:
        try:
            db.execute(
                """INSERT INTO war_room_reactions
                       (round_id, competitor_company_id, competitor_company_name,
                        reaction_type, headline, specific_action, asset_leveraged,
                        rationale, evidence_basis, stripped_citations,
                        evidence_validated, scores, confidence_score, confidence)
                   VALUES (%s::uuid, %s::uuid, %s, %s, %s, %s, %s::jsonb,
                           %s, %s, %s, %s, %s::jsonb, %s, %s)""",
                [
                    round_id,
                    rxn.get("competitor_company_id"),
                    rxn.get("competitor_company_name"),
                    rxn.get("reaction_type"),
                    rxn.get("headline"),
                    rxn.get("specific_action"),
                    json.dumps(rxn.get("asset_leveraged") or {}),
                    rxn.get("rationale"),
                    rxn.get("evidence_basis") or [],
                    rxn.get("stripped_citations") or [],
                    bool(rxn.get("evidence_validated", True)),
                    json.dumps(rxn.get("scores") or {}),
                    rxn.get("confidence_score"),
                    rxn.get("confidence"),
                ],
            )
        except Exception as exc:
            logger.warning("reaction insert failed (round=%s competitor=%s): %s",
                           round_id, rxn.get("competitor_company_name"), exc)
            persistence_errors.append({
                "competitor_company_name": rxn.get("competitor_company_name"),
                "error": str(exc)[:200],
            })
            continue
        # Echo into the response (no separate read-back — tests verify)
        saved_reactions.append({
            "id": None,
            "round_id": round_id,
            **rxn,
        })

    out = _round_to_dict(rnd_row)
    out["reactions"] = saved_reactions
    out["competitors_attempted"] = len(reactions)
    out["competitors_persisted"] = len(saved_reactions)
    if persistence_errors:
        out["persistence_errors"] = persistence_errors
    return out


# ────────────────────────────────────────────────────────────────────
# POST /war-rooms/{id}/suggest-moves — Phase A.5 autonomous move suggester
# ────────────────────────────────────────────────────────────────────

@router.post("/{room_id}/suggest-moves")
def suggest_moves_endpoint(
    room_id: str,
    body: SuggestMovesBody,
    user: Optional[dict] = Depends(get_current_user),
    db: Database = Depends(get_db),
    llm = Depends(get_llm),
):
    """Generate N ranked move suggestions for the war room owner.

    Owner-only. Persists the batch into move_suggestions for audit + the
    Phase D learning loop. Returns the suggestions in ranked order
    (highest expected_impact_score first).
    """
    if user is None:
        raise HTTPException(401, "authentication required")

    if body.n < 1 or body.n > 8:
        raise HTTPException(400, f"n must be between 1 and 8 (got {body.n})")

    room = _fetch_room(db, room_id)
    if not room:
        raise HTTPException(404, f"war room not found: {room_id}")
    if str(room.get("owner_user_id")) != str(user.get("id")):
        raise HTTPException(403, "only the room owner can request suggestions")

    suggestions = _suggest_moves(
        db, llm,
        player_entity_type=room.get("primary_entity_type"),
        player_entity_id=room.get("primary_entity_id"),
        player_name=room.get("primary_entity_name") or "Player",
        signal_context=body.signal_context,
        n=body.n,
    )

    # Persist for audit / Phase D — failure here is non-fatal
    try:
        db.execute(
            """INSERT INTO move_suggestions
                   (war_room_id, source_signal_id, suggestions,
                    rule_version_id, requested_by)
               VALUES (%s::uuid, %s, %s::jsonb, %s, %s::uuid)""",
            [
                room_id,
                room.get("source_signal_id"),
                json.dumps(suggestions),
                SUGGESTER_RULE_VERSION,
                user.get("id"),
            ],
        )
    except Exception as exc:
        logger.warning("move_suggestions audit insert failed: %s", exc)

    return {
        "war_room_id": room_id,
        "suggestions": suggestions,
        "count": len(suggestions),
        "rule_version_id": SUGGESTER_RULE_VERSION,
    }


# ────────────────────────────────────────────────────────────────────
# DELETE /war-rooms/{id} — soft delete (status='closed')
# ────────────────────────────────────────────────────────────────────

@router.delete("/{room_id}", status_code=204)
def delete_room(
    room_id: str,
    user: Optional[dict] = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    if user is None:
        raise HTTPException(401, "authentication required")

    room = _fetch_room(db, room_id)
    if not room:
        raise HTTPException(404, f"war room not found: {room_id}")
    if str(room.get("owner_user_id")) != str(user.get("id")):
        raise HTTPException(403, "only the room owner can delete")

    try:
        db.execute(
            "UPDATE war_rooms SET status = 'closed', updated_at = NOW() WHERE id::text = %s",
            [room_id],
        )
    except Exception as exc:
        logger.exception("room close failed")
        raise HTTPException(500, f"close failed: {exc}") from exc

    return Response(status_code=204)
