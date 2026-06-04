"""SPEC-021 — War Room API.

CRUD over war_rooms + the run-round endpoint that generates competitor
reactions. Mutations are owner-only; reads are anonymous (so a war
room URL is shareable).

Phase B adds: rename/archive (PATCH), threaded comments (CRUD), and
list filters (status, archived, search by title, by entity).
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field

from api.deps import get_current_user, get_db, get_llm, require_role
from db import Database
from services.guided_mode import GuidedModeBlocked, assert_guided
from services.move_suggester import (
    SUGGESTER_RULE_VERSION,
    suggest_moves as _engine_suggest_moves,
)
from services.scenario_state import (
    InvalidScenarioMode,
    ScenarioNotFound,
    transition_mode as _transition_scenario_mode,
)
from services.war_game_autonomous import (
    DEFAULT_MOVES as AUTOPLAY_DEFAULT_MOVES,
    autoplay as _autoplay,
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


class PatchRoomBody(BaseModel):
    """Partial update. All fields optional; only provided fields are written."""
    title: Optional[str] = Field(default=None, min_length=1, max_length=300)
    scenario_question: Optional[str] = Field(default=None, max_length=2000)
    status: Optional[str] = None  # 'active' | 'closed' (re-open or close)
    archived: Optional[bool] = None  # true → set archived_at=NOW; false → NULL


class CommentBody(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    round_id: Optional[str] = None


class CommentPatchBody(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class PatchModeBody(BaseModel):
    """W1 — switch the war room's scenario mode.

    The string is validated against `services.scenario_state.ScenarioMode`
    inside the service layer; a typo here returns 400 from the route.
    """
    mode: str = Field(min_length=1, max_length=32)


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
        # W1 — scenario mode toggle. Default 'guided' so pre-W1 rows that
        # haven't backfilled the column still emit a sensible value.
        "mode": row.get("mode") or "guided",
        "mode_changed_at": _iso(row.get("mode_changed_at")),
        "archived_at": _iso(row.get("archived_at")),
        "created_at": _iso(row.get("created_at")),
        "updated_at": _iso(row.get("updated_at")),
    }


def _comment_to_dict(row: dict) -> dict:
    return {
        "id": str(row.get("id")),
        "war_room_id": str(row.get("war_room_id")),
        "round_id": str(row["round_id"]) if row.get("round_id") else None,
        "author_user_id": str(row["author_user_id"]) if row.get("author_user_id") else None,
        "author_display_name": row.get("author_display_name"),
        "body": row.get("body"),
        "created_at": _iso(row.get("created_at")),
        "edited_at": _iso(row.get("edited_at")),
    }


_ROOM_COLS = """id, title, owner_user_id, scenario_question,
                primary_entity_type, primary_entity_id, primary_entity_name,
                source_signal_id, game_phase, status, mode, mode_changed_at,
                archived_at, created_at, updated_at"""


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
            f"SELECT {_ROOM_COLS} FROM war_rooms WHERE id::text = %s",
            [room_id],
        )
    except Exception:
        logger.exception("war room fetch failed")
        return None


def _fetch_comments(db: Database, room_id: str) -> list[dict]:
    try:
        rows = db.fetch_all(
            """SELECT id, war_room_id, round_id, author_user_id,
                      author_display_name, body, created_at, edited_at
               FROM war_room_comments
               WHERE war_room_id = %s::uuid
               ORDER BY created_at ASC""",
            [room_id],
        ) or []
    except Exception:
        rows = []
    return [_comment_to_dict(r) for r in rows]


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

    # INSERT ... RETURNING id — replaces the title-based read-back race
    # (Phase A audit fix). fetch_one runs the INSERT and returns the row.
    try:
        new = db.fetch_one(
            """INSERT INTO war_rooms
                   (title, owner_user_id, scenario_question,
                    primary_entity_type, primary_entity_id, primary_entity_name,
                    source_signal_id, game_phase)
               VALUES (%s, %s::uuid, %s, %s, %s, %s, %s, %s)
               RETURNING id""",
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

    if not new or not new.get("id"):
        raise HTTPException(500, "create succeeded but RETURNING id was empty")

    row = _fetch_room(db, str(new["id"]))
    if not row:
        raise HTTPException(500, "create succeeded but read-back failed")
    return _room_to_dict(row)


# ────────────────────────────────────────────────────────────────────
# GET /war-rooms — list (current user's)
# ────────────────────────────────────────────────────────────────────

@router.get("")
def list_rooms(
    status: Optional[str] = Query(default=None, description="active | closed"),
    archived: Optional[bool] = Query(default=None, description="true | false; omit for both"),
    q: Optional[str] = Query(default=None, description="title substring (ILIKE)"),
    entity_id: Optional[str] = Query(default=None, description="primary_entity_id exact match"),
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    """List the current user's war rooms with optional filters.

    Default (no filters): returns all of the user's non-archived rooms in
    descending creation order. Pass `archived=true` to see only archived,
    `archived=false` to explicitly exclude them, or omit to include both.
    """
    where = ["owner_user_id = %s::uuid"]
    params: list[Any] = [user.get("id")]

    if status:
        where.append("status = %s")
        params.append(status)

    if archived is True:
        where.append("archived_at IS NOT NULL")
    elif archived is False:
        where.append("archived_at IS NULL")
    # archived is None → no filter (show both)

    if q:
        where.append("title ILIKE %s")
        params.append(f"%{q}%")

    if entity_id:
        where.append("primary_entity_id = %s")
        params.append(entity_id)

    sql = (
        f"SELECT {_ROOM_COLS} FROM war_rooms "
        f"WHERE {' AND '.join(where)} "
        "ORDER BY created_at DESC"
    )
    try:
        rows = db.fetch_all(sql, params)
    except Exception:
        logger.exception("war room list query failed")
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
    out["comments"] = _fetch_comments(db, room_id)
    return out


# ────────────────────────────────────────────────────────────────────
# PATCH /war-rooms/{id} — partial update (rename / archive / re-open)
# ────────────────────────────────────────────────────────────────────

@router.patch("/{room_id}")
def patch_room(
    room_id: str,
    body: PatchRoomBody,
    user: Optional[dict] = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    if user is None:
        raise HTTPException(401, "authentication required")

    room = _fetch_room(db, room_id)
    if not room:
        raise HTTPException(404, f"war room not found: {room_id}")
    if str(room.get("owner_user_id")) != str(user.get("id")):
        raise HTTPException(403, "only the room owner can update")

    sets: list[str] = []
    params: list[Any] = []

    if body.title is not None:
        sets.append("title = %s")
        params.append(body.title)
    if body.scenario_question is not None:
        sets.append("scenario_question = %s")
        params.append(body.scenario_question)
    if body.status is not None:
        if body.status not in ("active", "closed"):
            raise HTTPException(400, f"invalid status: {body.status}")
        sets.append("status = %s")
        params.append(body.status)
    if body.archived is not None:
        if body.archived:
            sets.append("archived_at = NOW()")
        else:
            sets.append("archived_at = NULL")

    if not sets:
        # No-op patch — return current state
        return _room_to_dict(room)

    sets.append("updated_at = NOW()")
    sql = f"UPDATE war_rooms SET {', '.join(sets)} WHERE id::text = %s"
    params.append(room_id)

    try:
        db.execute(sql, params)
    except Exception as exc:
        logger.exception("war room patch failed")
        raise HTTPException(500, f"patch failed: {exc}") from exc

    updated = _fetch_room(db, room_id)
    return _room_to_dict(updated) if updated else _room_to_dict(room)


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

    # W2 — Guided-mode gate. Submitting a round is Guided-only; the
    # autonomous loop (W3) and game-theoretic matrix (W4) have their own
    # surfaces. We use the mode already loaded on the room row rather
    # than a second DB roundtrip via load_scenario_state.
    try:
        assert_guided(room.get("mode", "guided"))
    except GuidedModeBlocked as exc:
        raise HTTPException(409, str(exc)) from exc

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

    # Insert round + read back via RETURNING (avoids the
    # (war_room_id, round_number) read-back race — Phase A audit fix).
    try:
        new = db.fetch_one(
            """INSERT INTO war_room_rounds
                   (war_room_id, round_number, player_company_id,
                    player_company_name, move_type, move_payload, notes)
               VALUES (%s::uuid, %s, %s, %s, %s, %s::jsonb, %s)
               RETURNING id""",
            [
                room_id, next_round, body.player_company_id,
                body.player_company_name, body.move_type,
                json.dumps(body.move_payload or {}), body.notes,
            ],
        )
    except Exception as exc:
        logger.exception("round insert failed")
        raise HTTPException(500, f"round create failed: {exc}") from exc

    if not new or not new.get("id"):
        raise HTTPException(500, "round insert succeeded but RETURNING id was empty")
    round_id = str(new["id"])

    # Hydrate the row for the response (full set of columns)
    try:
        rnd_row = db.fetch_one(
            """SELECT id, war_room_id, round_number, player_company_id,
                      player_company_name, move_type, move_payload, notes, created_at
               FROM war_room_rounds
               WHERE id::text = %s""",
            [round_id],
        )
    except Exception:
        rnd_row = None
    if not rnd_row:
        raise HTTPException(500, "round insert succeeded but read-back failed")

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
# W3 · POST /war-rooms/{id}/run-autonomous — autonomous N-round play (PB-H13)
# ────────────────────────────────────────────────────────────────────

class AutonomousBody(BaseModel):
    rounds: int = Field(default=3, ge=1, le=8)
    our_moves: Optional[list[str]] = Field(default=None, max_length=8)
    player_company_id: Optional[str] = None
    player_company_name: Optional[str] = None


@router.post("/{room_id}/run-autonomous", status_code=200)
def run_autonomous(
    room_id: str,
    body: AutonomousBody,
    user: Optional[dict] = Depends(get_current_user),
    db: Database = Depends(get_db),
    llm = Depends(get_llm),
):
    """Run an autonomous N-round war-game campaign (PB-H13).

    Owner-only. The agents play every round; each move's adversary reactions
    come from the SAME DB-grounded `generate_reactions` the Guided path uses,
    so nothing is fabricated. The transcript is returned (ephemeral) — no
    schema change; the Learn loop (PB-H14) and persistence are separate.
    """
    if user is None:
        raise HTTPException(401, "authentication required")

    room = _fetch_room(db, room_id)
    if not room:
        raise HTTPException(404, f"war room not found: {room_id}")
    if str(room.get("owner_user_id")) != str(user.get("id")):
        raise HTTPException(403, "only the room owner can run autonomous play")

    moves = body.our_moves or list(AUTOPLAY_DEFAULT_MOVES)
    invalid = [m for m in moves if not is_valid_move_type(m)]
    if invalid:
        raise HTTPException(
            400, f"invalid move_type(s): {', '.join(invalid)} (allowed: {', '.join(MOVE_TYPES)})"
        )

    player_name = body.player_company_name or room.get("primary_entity_name") or "Player"
    competitors = _fetch_competitors(
        db, body.player_company_id, body.player_company_name or room.get("primary_entity_name")
    )

    def _reactor(move_type: str, round_num: int, history: list[dict]) -> list[dict]:
        return _generate_reactions(
            db, llm,
            player_name=player_name,
            move_type=move_type,
            move_payload={},
            competitors=competitors,
            game_phase=room.get("game_phase") or "launch",
            history=history,
        )

    try:
        result = _autoplay(
            our_moves=moves, reactor=_reactor, rounds=body.rounds, player_name=player_name
        )
    except ValueError as e:
        raise HTTPException(400, str(e))

    result["mode"] = "autonomous"
    result["war_room_id"] = room_id
    return result


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

    # W2 — move suggestions are Guided-only (they're recommendations for the
    # human to play next, which is the Guided contract). Autonomous mode
    # doesn't need them; game-theoretic mode shows a payoff matrix instead.
    try:
        assert_guided(room.get("mode", "guided"))
    except GuidedModeBlocked as exc:
        raise HTTPException(409, str(exc)) from exc

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


# ────────────────────────────────────────────────────────────────────
# COMMENTS — anon read, viewer-write, author-edit, author-or-owner-delete
# ────────────────────────────────────────────────────────────────────

@router.get("/{room_id}/comments")
def list_comments(
    room_id: str,
    round_id: Optional[str] = Query(default=None),
    db: Database = Depends(get_db),
):
    """Anon read. Optional ?round_id= filters to comments on a single round."""
    room = _fetch_room(db, room_id)
    if not room:
        raise HTTPException(404, f"war room not found: {room_id}")

    if round_id:
        try:
            rows = db.fetch_all(
                """SELECT id, war_room_id, round_id, author_user_id,
                          author_display_name, body, created_at, edited_at
                   FROM war_room_comments
                   WHERE war_room_id = %s::uuid AND round_id = %s::uuid
                   ORDER BY created_at ASC""",
                [room_id, round_id],
            ) or []
        except Exception:
            rows = []
        comments = [_comment_to_dict(r) for r in rows]
    else:
        comments = _fetch_comments(db, room_id)

    return {"war_room_id": room_id, "comments": comments, "count": len(comments)}


@router.post("/{room_id}/comments", status_code=201)
def create_comment(
    room_id: str,
    body: CommentBody,
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    """viewer+ can comment on any war room (rooms are anon-readable)."""
    room = _fetch_room(db, room_id)
    if not room:
        raise HTTPException(404, f"war room not found: {room_id}")

    # If round_id provided, sanity-check it belongs to this room (cheap).
    if body.round_id:
        try:
            rnd = db.fetch_one(
                "SELECT war_room_id FROM war_room_rounds WHERE id::text = %s",
                [body.round_id],
            )
        except Exception:
            rnd = None
        if not rnd or str(rnd.get("war_room_id")) != str(room.get("id")):
            raise HTTPException(400, f"round_id {body.round_id} not in this room")

    display_name = (
        user.get("display_name")
        or user.get("email", "").split("@")[0]
        or "anonymous"
    )

    try:
        new = db.fetch_one(
            """INSERT INTO war_room_comments
                   (war_room_id, round_id, author_user_id, author_display_name, body)
               VALUES (%s::uuid, %s, %s::uuid, %s, %s)
               RETURNING id, war_room_id, round_id, author_user_id,
                         author_display_name, body, created_at, edited_at""",
            [
                room_id,
                body.round_id,
                user.get("id"),
                display_name,
                body.body,
            ],
        )
    except Exception as exc:
        logger.exception("comment insert failed")
        raise HTTPException(500, f"comment create failed: {exc}") from exc

    if not new:
        raise HTTPException(500, "comment insert succeeded but RETURNING was empty")
    return _comment_to_dict(new)


def _fetch_comment(db: Database, comment_id: str) -> Optional[dict]:
    try:
        return db.fetch_one(
            """SELECT id, war_room_id, round_id, author_user_id,
                      author_display_name, body, created_at, edited_at
               FROM war_room_comments WHERE id::text = %s""",
            [comment_id],
        )
    except Exception:
        return None


@router.patch("/{room_id}/comments/{comment_id}")
def patch_comment(
    room_id: str,
    comment_id: str,
    body: CommentPatchBody,
    user: Optional[dict] = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Edit your own comment. Sets edited_at."""
    if user is None:
        raise HTTPException(401, "authentication required")

    comment = _fetch_comment(db, comment_id)
    if not comment or str(comment.get("war_room_id")) != room_id:
        raise HTTPException(404, f"comment not found in room {room_id}")
    if str(comment.get("author_user_id")) != str(user.get("id")):
        raise HTTPException(403, "only the author can edit a comment")

    try:
        db.execute(
            """UPDATE war_room_comments
               SET body = %s, edited_at = NOW()
               WHERE id::text = %s""",
            [body.body, comment_id],
        )
    except Exception as exc:
        logger.exception("comment patch failed")
        raise HTTPException(500, f"edit failed: {exc}") from exc

    updated = _fetch_comment(db, comment_id)
    return _comment_to_dict(updated) if updated else _comment_to_dict(comment)


@router.delete("/{room_id}/comments/{comment_id}", status_code=204)
def delete_comment(
    room_id: str,
    comment_id: str,
    user: Optional[dict] = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Author OR room owner can delete."""
    if user is None:
        raise HTTPException(401, "authentication required")

    comment = _fetch_comment(db, comment_id)
    if not comment or str(comment.get("war_room_id")) != room_id:
        raise HTTPException(404, f"comment not found in room {room_id}")

    is_author = str(comment.get("author_user_id")) == str(user.get("id"))
    is_owner = False
    room = _fetch_room(db, room_id)
    if room:
        is_owner = str(room.get("owner_user_id")) == str(user.get("id"))

    if not (is_author or is_owner):
        raise HTTPException(403, "only the author or room owner can delete")

    try:
        db.execute(
            "DELETE FROM war_room_comments WHERE id::text = %s",
            [comment_id],
        )
    except Exception as exc:
        logger.exception("comment delete failed")
        raise HTTPException(500, f"delete failed: {exc}") from exc

    return Response(status_code=204)


# ════════════════════════════════════════════════════════════════════
# BE-8 · POST /war-rooms/{id}/payoff-matrix
# ════════════════════════════════════════════════════════════════════


class PayoffMatrixBody(BaseModel):
    # PB-H12 — 2..5 per dim (3×3 is the benchmark target; 2×2 the default).
    our_moves: list[str] = Field(min_length=2, max_length=5)
    adversary_states: list[str] = Field(min_length=2, max_length=5)
    samples: int = Field(default=1200, ge=100, le=10000)


@router.post("/{room_id}/payoff-matrix", status_code=200)
def payoff_matrix(
    room_id: str,
    body: PayoffMatrixBody,
    user: dict = Depends(require_role("uploader")),
    db: Database = Depends(get_db),
):
    """BE-8 — 2x2 payoff matrix composer (PB-501)."""
    room = _fetch_room(db, room_id)
    if not room:
        raise HTTPException(404, f"war room not found: {room_id}")

    from services.simulation.payoff import build_payoff_matrix

    def _runner(*, war_room_id, our_move, adversary_state, samples):
        try:
            from services.game_theory import run_bayesian
            return run_bayesian(
                db=db,
                war_room_id=war_room_id,
                our_move=our_move,
                adversary_state=adversary_state,
                samples=samples,
            )
        except Exception as exc:
            logger.warning("run_bayesian failed (%s, %s): %s", our_move, adversary_state, exc)
            return {}

    try:
        out = build_payoff_matrix(
            our_moves=body.our_moves,
            adversary_states=body.adversary_states,
            bayesian_runner=_runner,
            war_room_id=room_id,
            samples=body.samples,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return out


# ════════════════════════════════════════════════════════════════════
# W1 · PATCH /war-rooms/{id}/mode — scenario mode toggle
# ════════════════════════════════════════════════════════════════════

@router.patch("/{room_id}/mode")
def patch_room_mode(
    room_id: str,
    body: PatchModeBody,
    user: Optional[dict] = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Switch the war room's scenario mode (W1).

    Owner-only. Returns the scenario state dict (war_room_id, mode,
    round_count, mode_changed_at). Same-mode transitions are no-ops
    that return the current state without a DB write.
    """
    if user is None:
        raise HTTPException(401, "authentication required")

    # Ownership check piggy-backs on the existing room fetch so we get
    # a 404 for missing rooms and 403 for non-owners — same surface as
    # patch_room. Without this, transition_mode would raise
    # ScenarioNotFound (correct) but skip the owner guard.
    room = _fetch_room(db, room_id)
    if not room:
        raise HTTPException(404, f"war room not found: {room_id}")
    if str(room.get("owner_user_id")) != str(user.get("id")):
        raise HTTPException(403, "only the room owner can change mode")

    try:
        state = _transition_scenario_mode(db, room_id, body.mode)
    except InvalidScenarioMode as e:
        raise HTTPException(400, str(e)) from e
    except ScenarioNotFound as e:
        # Race: the room was deleted between our owner-check and the
        # transition. Surface as 404; the audit trail will show the close.
        raise HTTPException(404, str(e)) from e

    return state.to_dict()
