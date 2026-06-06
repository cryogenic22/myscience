"""DF-1 + DF-2 — the round engine.

The playable loop, end to end:

  create_round(...)   generate a prompt FROM real DB entities and persist it
                      (forge_rounds). DF-1.

  submit_answer(...)  capture the SME's CONSTRAINED answer to a round and, in
                      one transaction-like flow:
                        1. shape the elicited dimension from the SME's top pick
                           (DF-1) — its routes come from the constrained option
                           set, so it is always plannable.
                        2. VALIDATE it against the current playbook (DF-2, reuse
                           services.domain_intelligence.validation).
                        3. CONSENSUS (DF-2): if enough SMEs independently picked
                           the same top dimension, PROMOTE it — apply it to a new
                           playbook version via the existing
                           PlaybookAuthoringService. A lone / dissenting answer is
                           FLAGGED (recorded), never auto-applied.
                        4. persist a GOLD eval item (prompt → answer) for the
                           eval harness (forge_eval_items).
                        5. SCORE the answer, GATED on validation + consensus —
                           reward correctness, not volume (forge_scores).

Reuse, not duplication: authoring + validation already exist and are CALLED
here; the playbook model shapes the dimension. The engine only owns the
round / eval / score rows (migration 083).
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from services.domain_intelligence.authoring import PlaybookAuthoringService
from services.domain_intelligence.playbook import Dimension, Playbook
from services.domain_intelligence.validation import (
    PlaybookValidationError,
    validate_playbook,
)
from services.domain_forge.prompts import (
    generate_what_matters_round,
    option_for_key,
)

logger = logging.getLogger(__name__)

# How many distinct SMEs must independently rank a dimension top before it is
# PROMOTED (auto-applied to the playbook). Below this, the answer is FLAGGED as a
# proposal for review — dissent is captured, never silently applied.
DEFAULT_CONSENSUS_THRESHOLD = 2

# Score awarded for a valid answer that promotes (consensus correctness) vs a
# valid-but-not-yet-corroborated answer (still useful — a labelled gold item)
# vs an invalid answer (no reward). Rewards correctness, not volume.
POINTS_PROMOTED = 10
POINTS_VALID_PENDING = 3
POINTS_INVALID = 0


class RoundNotFound(Exception):
    """Raised when a round_id has no row."""


class RoundAlreadyAnswered(Exception):
    """Raised when submitting against a round that is already answered (idempotent
    re-submit guard — a round is one play)."""


class InvalidAnswer(Exception):
    """Raised when the SME's answer is structurally unusable (e.g. no selected
    dimension, or a selection outside the round's constrained option set)."""


def _j(v: Any, default: Any) -> Any:
    """Coerce a JSONB column that may arrive as str under some drivers."""
    if isinstance(v, str):
        try:
            return json.loads(v)
        except (TypeError, ValueError):
            return default
    return v if v is not None else default


class ForgeEngine:
    """The round engine. Stateless service; pass the db handle to each call
    (mirrors PlaybookAuthoringService)."""

    def __init__(self, consensus_threshold: int = DEFAULT_CONSENSUS_THRESHOLD) -> None:
        self.consensus_threshold = max(1, int(consensus_threshold))

    # ── DF-1: create a round ──────────────────────────────────────────────

    def create_round(
        self,
        db: Any,
        *,
        session_id: str,
        intent: str = "compare",
        playbook_id: str = "compare.drug_x_drug",
        entities: Optional[list[dict]] = None,
        created_by: Optional[str] = None,
    ) -> dict:
        """Generate a "What matters?" round FROM real DB entities and persist it.

        Returns the stored round as a dict. Raises ValueError if the spine has
        too few real entities to build a grounded compare (never fabricates)."""
        spec = generate_what_matters_round(
            db, intent=intent, playbook_id=playbook_id, entities=entities
        )
        row = db.fetch_one(
            "INSERT INTO forge_rounds "
            "(session_id, round_type, playbook_id, intent, prompt, payload, "
            " status, created_by) "
            "VALUES (%s, %s, %s, %s, %s, %s::jsonb, 'open', %s) "
            "RETURNING id, session_id, round_type, playbook_id, intent, prompt, "
            "          payload, status, created_by, created_at",
            [
                session_id, spec["round_type"], spec["playbook_id"], spec["intent"],
                spec["prompt"], json.dumps(spec["payload"]), created_by,
            ],
        )
        if not row:
            raise RuntimeError("create_round: insert returned no row")
        return self._round_to_dict(row)

    def get_round(self, db: Any, round_id: str) -> Optional[dict]:
        row = db.fetch_one(
            "SELECT id, session_id, round_type, playbook_id, intent, prompt, "
            "       payload, status, created_by, created_at, answered_at "
            "FROM forge_rounds WHERE id = %s",
            [round_id],
        )
        return self._round_to_dict(row) if row else None

    # ── DF-1 + DF-2: submit an answer ─────────────────────────────────────

    def submit_answer(
        self,
        db: Any,
        round_id: str,
        answer: dict,
        *,
        sme_id: Optional[str] = None,
    ) -> dict:
        """Submit an SME's constrained answer to a round.

        `answer` shape: {"selected": ["key", ...], "ranking": ["key", ...]}.
        The TOP-ranked (or first selected) dimension is the elicited one.

        Returns {eval_item, validation, consensus, score, playbook_version}.
        """
        round_row = db.fetch_one(
            "SELECT id, session_id, round_type, playbook_id, intent, prompt, "
            "       payload, status FROM forge_rounds WHERE id = %s",
            [round_id],
        )
        if not round_row:
            raise RoundNotFound(f"round not found: {round_id}")
        if (round_row.get("status") or "open") == "answered":
            raise RoundAlreadyAnswered(f"round already answered: {round_id}")

        payload = _j(round_row.get("payload"), {})
        allowed_keys = {o["key"] for o in payload.get("options", [])}
        top_key = self._top_dimension_key(answer, allowed_keys)

        playbook_id = round_row["playbook_id"]
        opt = option_for_key(top_key)
        if opt is None:
            raise InvalidAnswer(f"no routable option for dimension '{top_key}'")

        elicited_dim = {
            "key": opt["key"],
            "label": opt["label"],
            "sub_question": opt.get("sub_question", ""),
            "routes": list(opt["routes"]),
            "required": False,
            "weight": 0.7,
        }

        # 2. VALIDATE the elicited dimension against the current playbook (DF-2).
        validation = self._validate_dimension(db, playbook_id, elicited_dim)

        # 3. CONSENSUS (DF-2): count distinct SMEs (incl. this answer) whose top
        #    pick is this dimension on this playbook. Promote iff threshold met
        #    AND valid; otherwise flag as a proposal (not applied).
        agree_count = self._consensus_count(
            db, playbook_id=playbook_id, dimension_key=top_key,
            this_sme=sme_id,
        )
        promoted_version: Optional[int] = None
        if validation["valid"] and agree_count >= self.consensus_threshold:
            promoted_version = self._promote_dimension(
                db, playbook_id, elicited_dim, author=sme_id
            )
            consensus_state = "promoted"
        else:
            consensus_state = "flagged"  # lone / dissenting / invalid → proposal only

        # 4. persist the GOLD eval item (prompt → answer).
        eval_item = self._persist_eval_item(
            db,
            round_row=round_row,
            answer=answer,
            sme_id=sme_id,
            validation=validation,
            consensus_state=consensus_state,
            promoted_version=promoted_version,
        )

        # 5. SCORE — gated on validation + consensus (reward correctness).
        score = self._score_answer(
            db,
            eval_item_id=eval_item["id"],
            session_id=round_row["session_id"],
            sme_id=sme_id,
            valid=validation["valid"],
            promoted=(consensus_state == "promoted"),
        )

        # mark the round answered (one play).
        db.execute(
            "UPDATE forge_rounds SET status='answered', answered_at=NOW() WHERE id=%s",
            [round_id],
        )

        return {
            "round_id": round_id,
            "dimension": elicited_dim,
            "validation": validation,
            "consensus": {
                "state": consensus_state,
                "agree_count": agree_count,
                "threshold": self.consensus_threshold,
            },
            "playbook_version": promoted_version,
            "eval_item": eval_item,
            "score": score,
        }

    # ── session / score reads ─────────────────────────────────────────────

    def session_summary(self, db: Any, session_id: str) -> dict:
        """Rounds played, eval items minted, total score for a session."""
        rounds = db.fetch_one(
            "SELECT COUNT(*) AS n, "
            "       COUNT(*) FILTER (WHERE status='answered') AS answered "
            "FROM forge_rounds WHERE session_id = %s",
            [session_id],
        ) or {}
        evals = db.fetch_one(
            "SELECT COUNT(*) AS n, "
            "       COUNT(*) FILTER (WHERE consensus_state='promoted') AS promoted "
            "FROM forge_eval_items WHERE session_id = %s",
            [session_id],
        ) or {}
        score = db.fetch_one(
            "SELECT COALESCE(SUM(points), 0) AS total FROM forge_scores "
            "WHERE session_id = %s",
            [session_id],
        ) or {}
        return {
            "session_id": session_id,
            "rounds": int(rounds.get("n") or 0),
            "rounds_answered": int(rounds.get("answered") or 0),
            "eval_items": int(evals.get("n") or 0),
            "promoted": int(evals.get("promoted") or 0),
            "score": int(score.get("total") or 0),
        }

    def list_eval_items(self, db: Any, *, playbook_id: Optional[str] = None,
                        session_id: Optional[str] = None) -> list[dict]:
        """Gold eval items (newest first), optionally filtered. The eval harness
        consumes these as labelled prompt→answer gold."""
        where, params = [], []
        if playbook_id:
            where.append("playbook_id = %s"); params.append(playbook_id)
        if session_id:
            where.append("session_id = %s"); params.append(session_id)
        clause = (" WHERE " + " AND ".join(where)) if where else ""
        rows = db.fetch_all(
            "SELECT id, round_id, session_id, playbook_id, intent, prompt, answer, "
            "       sme_id, validation, consensus_state, promoted_version, created_at "
            "FROM forge_eval_items" + clause + " ORDER BY created_at DESC",
            params,
        ) or []
        return [self._eval_to_dict(r) for r in rows]

    # ── internals ─────────────────────────────────────────────────────────

    @staticmethod
    def _top_dimension_key(answer: dict, allowed_keys: set[str]) -> str:
        """The SME's top dimension: first of `ranking`, else first `selected`.
        Must be within the round's constrained option set."""
        if not isinstance(answer, dict):
            raise InvalidAnswer("answer must be an object")
        ranking = answer.get("ranking") or []
        selected = answer.get("selected") or []
        top = (ranking[0] if ranking else (selected[0] if selected else "")) or ""
        top = str(top).strip()
        if not top:
            raise InvalidAnswer("answer selected no dimension")
        if allowed_keys and top not in allowed_keys:
            raise InvalidAnswer(
                f"dimension '{top}' is not in the round's option set "
                f"({sorted(allowed_keys)})"
            )
        return top

    @staticmethod
    def _current_playbook(db: Any, playbook_id: str) -> Playbook:
        """The current playbook (DB row if any, else the YAML seed). Used to
        validate the elicited dimension in context + carry dims on promotion."""
        from services.domain_intelligence.playbook import get_playbook_registry
        row = PlaybookAuthoringService.get_row(db, playbook_id)
        if row:
            return Playbook.from_dict(
                PlaybookAuthoringService.get(db, playbook_id)["playbook"]
            )
        seed = get_playbook_registry().get(playbook_id)
        if seed is not None:
            return seed
        # No DB row and no seed → a fresh playbook shell the dimension seeds.
        return Playbook(id=playbook_id, trigger={}, dimensions=[])

    def _validate_dimension(self, db: Any, playbook_id: str, dim: dict) -> dict:
        """Validate the elicited dimension by validating the playbook it would
        produce (reuse validate_playbook). Returns {valid, errors}."""
        current = self._current_playbook(db, playbook_id)
        dims = {d.key: d for d in current.dimensions}
        dims[dim["key"]] = Dimension.from_dict(dim)  # add/replace
        candidate = Playbook(
            id=playbook_id,
            pack=current.pack,
            trigger=dict(current.trigger) or {"intent": "compare", "entities": "drug x drug"},
            dimensions=list(dims.values()),
            synthesis=dict(current.synthesis),
        )
        try:
            validate_playbook(candidate)  # no overlap check (editing one playbook)
            return {"valid": True, "errors": []}
        except PlaybookValidationError as e:
            return {"valid": False, "errors": list(e.errors)}

    def _consensus_count(
        self, db: Any, *, playbook_id: str, dimension_key: str,
        this_sme: Optional[str],
    ) -> int:
        """Distinct SMEs whose TOP pick was this dimension on this playbook,
        including the answer in flight. Prior agreement is read from already
        persisted eval items; the current SME is added if not already counted.

        Distinct by sme_id so one SME spamming the same answer does NOT
        manufacture consensus (reward correctness, not volume)."""
        rows = db.fetch_all(
            "SELECT DISTINCT sme_id FROM forge_eval_items "
            "WHERE playbook_id = %s AND answer->'ranking'->>0 = %s",
            [playbook_id, dimension_key],
        ) or []
        smes = {r.get("sme_id") for r in rows}
        # Fallback for answers that used `selected` without `ranking`.
        rows2 = db.fetch_all(
            "SELECT DISTINCT sme_id FROM forge_eval_items "
            "WHERE playbook_id = %s AND answer->'selected'->>0 = %s "
            "AND (answer->'ranking') IS NULL",
            [playbook_id, dimension_key],
        ) or []
        smes |= {r.get("sme_id") for r in rows2}
        if this_sme is not None:
            smes.add(this_sme)
        elif None not in smes:
            # anonymous answer counts as one additional voice
            smes.add(f"__anon__{dimension_key}__pending")
        return len({s for s in smes if s is not None})

    def _promote_dimension(
        self, db: Any, playbook_id: str, dim: dict, *, author: Optional[str],
    ) -> Optional[int]:
        """Apply the elicited dimension to a NEW playbook version via the
        existing PlaybookAuthoringService (create if no DB row yet, else update).
        Returns the new version number."""
        current = self._current_playbook(db, playbook_id)
        dims = [d.to_dict() for d in current.dimensions]
        # add or replace the elicited dimension
        dims = [d for d in dims if d.get("key") != dim["key"]] + [dim]
        trigger = dict(current.trigger) or {"intent": "compare", "entities": "drug x drug"}

        note = f"forge: SME consensus promoted dimension '{dim['key']}'"
        if PlaybookAuthoringService.get_row(db, playbook_id):
            res = PlaybookAuthoringService.update(
                db, playbook_id, {"dimensions": dims}, author=author, note=note,
            )
        else:
            res = PlaybookAuthoringService.create(
                db,
                {
                    "id": playbook_id,
                    "pack": current.pack,
                    "trigger": trigger,
                    "dimensions": dims,
                    "synthesis": dict(current.synthesis) or {"shape": "matrix"},
                },
                author=author,
            )
        return res.get("meta", {}).get("version")

    def _persist_eval_item(
        self, db: Any, *, round_row: dict, answer: dict, sme_id: Optional[str],
        validation: dict, consensus_state: str, promoted_version: Optional[int],
    ) -> dict:
        row = db.fetch_one(
            "INSERT INTO forge_eval_items "
            "(round_id, session_id, playbook_id, intent, prompt, answer, sme_id, "
            " validation, consensus_state, promoted_version) "
            "VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s::jsonb, %s, %s) "
            "RETURNING id, round_id, session_id, playbook_id, intent, prompt, "
            "          answer, sme_id, validation, consensus_state, "
            "          promoted_version, created_at",
            [
                round_row["id"], round_row["session_id"], round_row["playbook_id"],
                round_row["intent"], round_row["prompt"], json.dumps(answer), sme_id,
                json.dumps(validation), consensus_state, promoted_version,
            ],
        )
        if not row:
            raise RuntimeError("submit_answer: eval item insert returned no row")
        return self._eval_to_dict(row)

    def _score_answer(
        self, db: Any, *, eval_item_id: str, session_id: str,
        sme_id: Optional[str], valid: bool, promoted: bool,
    ) -> dict:
        """Award points GATED on validation + consensus (reward correctness)."""
        if not valid:
            points, reason = POINTS_INVALID, "invalid: dimension did not validate"
        elif promoted:
            points, reason = POINTS_PROMOTED, "valid + consensus promoted to playbook"
        else:
            points, reason = POINTS_VALID_PENDING, "valid gold label; awaiting consensus"
        row = db.fetch_one(
            "INSERT INTO forge_scores (eval_item_id, session_id, sme_id, points, reason) "
            "VALUES (%s, %s, %s, %s, %s) "
            "ON CONFLICT (eval_item_id) DO NOTHING "
            "RETURNING id, eval_item_id, session_id, sme_id, points, reason, created_at",
            [eval_item_id, session_id, sme_id, points, reason],
        )
        if row:
            return self._score_to_dict(row)
        existing = db.fetch_one(
            "SELECT id, eval_item_id, session_id, sme_id, points, reason, created_at "
            "FROM forge_scores WHERE eval_item_id = %s",
            [eval_item_id],
        )
        return self._score_to_dict(existing) if existing else {"points": points, "reason": reason}

    # ── row → dict ──

    @staticmethod
    def _round_to_dict(row: dict) -> dict:
        return {
            "id": str(row["id"]),
            "session_id": row.get("session_id"),
            "round_type": row.get("round_type"),
            "playbook_id": row.get("playbook_id"),
            "intent": row.get("intent"),
            "prompt": row.get("prompt"),
            "payload": _j(row.get("payload"), {}),
            "status": row.get("status"),
            "created_by": row.get("created_by"),
            "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
            "answered_at": row["answered_at"].isoformat() if row.get("answered_at") else None,
        }

    @staticmethod
    def _eval_to_dict(row: dict) -> dict:
        return {
            "id": str(row["id"]),
            "round_id": str(row.get("round_id")) if row.get("round_id") else None,
            "session_id": row.get("session_id"),
            "playbook_id": row.get("playbook_id"),
            "intent": row.get("intent"),
            "prompt": row.get("prompt"),
            "answer": _j(row.get("answer"), {}),
            "sme_id": row.get("sme_id"),
            "validation": _j(row.get("validation"), {}),
            "consensus_state": row.get("consensus_state"),
            "promoted_version": row.get("promoted_version"),
            "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
        }

    @staticmethod
    def _score_to_dict(row: dict) -> dict:
        return {
            "id": str(row["id"]),
            "eval_item_id": str(row.get("eval_item_id")) if row.get("eval_item_id") else None,
            "session_id": row.get("session_id"),
            "sme_id": row.get("sme_id"),
            "points": int(row.get("points") or 0),
            "reason": row.get("reason"),
            "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
        }
