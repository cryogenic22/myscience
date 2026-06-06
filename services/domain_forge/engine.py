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
    generate_critique_round,
    generate_routing_round,
    generate_signal_or_noise_round,
    generate_what_matters_round,
    grade_is_valid,
    option_for_key,
    reason_is_valid,
    routing_options_for_dimension,
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

# Round types that EDIT the playbook (consensus-gated): a lone answer is flagged,
# corroboration promotes. Other round types mint a labelling gold item (no pack
# edit), scored as a valid gold label on submission.
_PACK_EDITING_ROUND_TYPES = {"what_matters", "routing"}

# Labelling-round point award (a valid gold label — materiality / accuracy).
POINTS_LABEL = 5


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
        round_type: str = "what_matters",
        intent: Optional[str] = None,
        playbook_id: Optional[str] = None,
        entities: Optional[list[dict]] = None,
        created_by: Optional[str] = None,
        **kwargs: Any,
    ) -> dict:
        """Generate a round of `round_type` FROM real DB entities and persist it.

        Round types (DF-1 + DF-5):
          * what_matters    ① pick/rank the dimensions for a real compare.
          * signal_or_noise ② pick the most material of three real signals.
          * routing         ③ pick the fact-types/sources to trust for a dimension.
          * critique        ④ grade a real machine-generated cell.

        Returns the stored round as a dict. Raises ValueError when the DB lacks
        enough real rows to ground the round (never fabricates). `kwargs` carry
        round-type-specific params (e.g. dimension_key, predicate, signals).
        """
        spec = self._generate_spec(
            db, round_type=round_type, intent=intent, playbook_id=playbook_id,
            entities=entities, **kwargs,
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

    @staticmethod
    def _generate_spec(
        db: Any,
        *,
        round_type: str,
        intent: Optional[str],
        playbook_id: Optional[str],
        entities: Optional[list[dict]],
        **kwargs: Any,
    ) -> dict:
        """Dispatch to the round-type generator (all grounded in real DB rows)."""
        rt = (round_type or "what_matters").strip()
        if rt == "what_matters":
            return generate_what_matters_round(
                db,
                intent=intent or "compare",
                playbook_id=playbook_id or "compare.drug_x_drug",
                entities=entities,
            )
        if rt == "signal_or_noise":
            return generate_signal_or_noise_round(
                db,
                intent=intent or "materiality",
                playbook_id=playbook_id or "materiality.signal_triage",
                signals=kwargs.get("signals"),
            )
        if rt == "routing":
            return generate_routing_round(
                db,
                intent=intent or "dossier",
                playbook_id=playbook_id or "dossier.drug",
                dimension_key=kwargs.get("dimension_key", "safety"),
                entities=entities,
            )
        if rt == "critique":
            return generate_critique_round(
                db,
                intent=intent or "critique",
                playbook_id=playbook_id or "critique.cell_accuracy",
                predicate=kwargs.get("predicate", "mechanism_of_action"),
                cell=kwargs.get("cell"),
            )
        raise ValueError(
            f"domain_forge: unknown round_type '{round_type}' "
            f"(known: what_matters, signal_or_noise, routing, critique)"
        )

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

        Dispatches by the round's `round_type` (DF-1 + DF-5). Every type runs
        through the SAME persist-eval-item + score path; pack-editing types
        (what_matters / routing) additionally validate + consensus-gate a
        playbook edit, while labelling types (signal_or_noise / critique) mint a
        gold label scored on submission.

        Returns {round_id, validation, consensus, playbook_version, eval_item,
        score, ...}.
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

        rt = (round_row.get("round_type") or "what_matters").strip()
        if rt == "what_matters":
            result = self._submit_what_matters(db, round_row, answer, sme_id=sme_id)
        elif rt == "routing":
            result = self._submit_routing(db, round_row, answer, sme_id=sme_id)
        elif rt == "signal_or_noise":
            result = self._submit_signal_or_noise(db, round_row, answer, sme_id=sme_id)
        elif rt == "critique":
            result = self._submit_critique(db, round_row, answer, sme_id=sme_id)
        else:
            raise InvalidAnswer(f"unsupported round_type '{rt}'")

        # mark the round answered (one play) — common to every type.
        db.execute(
            "UPDATE forge_rounds SET status='answered', answered_at=NOW() WHERE id=%s",
            [round_id],
        )
        result["round_id"] = round_id
        return result

    # ── round-type handlers ───────────────────────────────────────────────

    def _submit_what_matters(
        self, db: Any, round_row: dict, answer: dict, *, sme_id: Optional[str],
    ) -> dict:
        """① "What matters?" — elicit + consensus-promote a dimension (DF-1/DF-2)."""
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
        validation = self._validate_dimension(db, playbook_id, elicited_dim)
        agree_count = self._consensus_count(
            db, playbook_id=playbook_id, dimension_key=top_key, this_sme=sme_id,
        )
        promoted_version, consensus_state = self._maybe_promote(
            db, playbook_id, elicited_dim, validation, agree_count, author=sme_id,
        )
        eval_item = self._persist_eval_item(
            db, round_row=round_row, answer=answer, sme_id=sme_id,
            validation=validation, consensus_state=consensus_state,
            promoted_version=promoted_version,
        )
        score = self._score_answer(
            db, eval_item_id=eval_item["id"], session_id=round_row["session_id"],
            sme_id=sme_id, valid=validation["valid"],
            promoted=(consensus_state == "promoted"),
        )
        return {
            "dimension": elicited_dim,
            "validation": validation,
            "consensus": {
                "state": consensus_state, "agree_count": agree_count,
                "threshold": self.consensus_threshold,
            },
            "playbook_version": promoted_version,
            "eval_item": eval_item,
            "score": score,
        }

    def _submit_routing(
        self, db: Any, round_row: dict, answer: dict, *, sme_id: Optional[str],
    ) -> dict:
        """③ "Where does the answer live?" — the SME's trusted route subset edits
        the dimension's routes (validated + consensus-gated, same engine path).

        `answer` shape: {"selected": ["predicate:x", "source:y", ...]}.
        Consensus keys on (playbook_id, dimension_key, sorted route set) so two
        SMEs who choose the SAME route set corroborate; the routes are validated
        before any pack edit (an unroutable selection → invalid → flagged)."""
        payload = _j(round_row.get("payload"), {})
        dim_key = (payload.get("dimension") or {}).get("key", "")
        dim_label = (payload.get("dimension") or {}).get("label", dim_key)
        allowed = {o["key"] for o in payload.get("options", [])}

        selected = [str(s).strip() for s in (answer.get("selected") or []) if str(s).strip()]
        if not selected:
            raise InvalidAnswer("routing answer selected no routes")
        bad = [s for s in selected if allowed and s not in allowed]
        if bad:
            raise InvalidAnswer(
                f"route(s) {bad} are not in the round's option set ({sorted(allowed)})"
            )
        # Stable, deduped route set (order-independent for consensus).
        routes = sorted(dict.fromkeys(selected))

        playbook_id = round_row["playbook_id"]
        edited_dim = {
            "key": dim_key,
            "label": dim_label,
            "sub_question": f"What is {{entity}}'s {dim_label.lower()}?",
            "routes": routes,
            "required": False,
            "weight": 0.7,
        }
        validation = self._validate_dimension(db, playbook_id, edited_dim)
        # Consensus on the (dimension, route-set) the SME proposed.
        consensus_key = dim_key + "|" + ",".join(routes)
        agree_count = self._consensus_count_routing(
            db, playbook_id=playbook_id, consensus_key=consensus_key, this_sme=sme_id,
        )
        promoted_version, consensus_state = self._maybe_promote(
            db, playbook_id, edited_dim, validation, agree_count, author=sme_id,
        )
        # Stamp the consensus key onto the persisted answer so a later SME's
        # identical route-set is counted (one JSONB comparison, no re-derivation).
        stored_answer = {**answer, "selected": routes, "consensus_key": consensus_key}
        eval_item = self._persist_eval_item(
            db, round_row=round_row, answer=stored_answer, sme_id=sme_id,
            validation=validation, consensus_state=consensus_state,
            promoted_version=promoted_version,
        )
        score = self._score_answer(
            db, eval_item_id=eval_item["id"], session_id=round_row["session_id"],
            sme_id=sme_id, valid=validation["valid"],
            promoted=(consensus_state == "promoted"),
        )
        return {
            "dimension": edited_dim,
            "validation": validation,
            "consensus": {
                "state": consensus_state, "agree_count": agree_count,
                "threshold": self.consensus_threshold,
            },
            "playbook_version": promoted_version,
            "eval_item": eval_item,
            "score": score,
        }

    def _submit_signal_or_noise(
        self, db: Any, round_row: dict, answer: dict, *, sme_id: Optional[str],
    ) -> dict:
        """② "Signal or noise?" — a materiality LABEL (no pack edit). The SME's
        chosen signal + reason is the gold label; valid → labelling reward.

        `answer` shape: {"signal_id": "...", "reason": "clinical_readout"}."""
        payload = _j(round_row.get("payload"), {})
        allowed_signal_ids = {s.get("signal_id") for s in payload.get("signals", [])}
        chosen = str(answer.get("signal_id") or "").strip()
        reason = str(answer.get("reason") or "").strip()
        if not chosen:
            raise InvalidAnswer("signal-or-noise answer selected no signal")
        if allowed_signal_ids and chosen not in allowed_signal_ids:
            raise InvalidAnswer(
                f"signal '{chosen}' is not in the round's candidate set"
            )
        if not reason_is_valid(reason):
            raise InvalidAnswer(f"reason '{reason}' is not a valid materiality reason")
        # A materiality label is "valid" when structurally well-formed (a real
        # signal + a constrained reason). There is no playbook edit, so it mints
        # a gold label and is scored on submission.
        validation = {"valid": True, "errors": []}
        eval_item = self._persist_eval_item(
            db, round_row=round_row, answer=answer, sme_id=sme_id,
            validation=validation, consensus_state="labelled", promoted_version=None,
        )
        score = self._score_label(
            db, eval_item_id=eval_item["id"], session_id=round_row["session_id"],
            sme_id=sme_id, reason="valid materiality label",
        )
        return {
            "label": {"signal_id": chosen, "reason": reason},
            "validation": validation,
            "consensus": {"state": "labelled", "agree_count": 1,
                          "threshold": self.consensus_threshold},
            "playbook_version": None,
            "eval_item": eval_item,
            "score": score,
        }

    def _submit_critique(
        self, db: Any, round_row: dict, answer: dict, *, sme_id: Optional[str],
    ) -> dict:
        """④ "Grade the machine" — a direct accuracy LABEL on a real cell.

        `answer` shape: {"grade": "correct|partial|wrong", "correction": "..."}."""
        payload = _j(round_row.get("payload"), {})
        cell = payload.get("cell") or {}
        grade = str(answer.get("grade") or "").strip()
        if not grade_is_valid(grade):
            raise InvalidAnswer(
                f"grade '{grade}' is not a valid critique grade "
                f"(correct / partial / wrong)"
            )
        validation = {"valid": True, "errors": []}
        eval_item = self._persist_eval_item(
            db, round_row=round_row, answer=answer, sme_id=sme_id,
            validation=validation, consensus_state="labelled", promoted_version=None,
        )
        score = self._score_label(
            db, eval_item_id=eval_item["id"], session_id=round_row["session_id"],
            sme_id=sme_id, reason=f"accuracy label: {grade}",
        )
        return {
            "label": {"fact_id": cell.get("fact_id"), "grade": grade,
                      "correction": str(answer.get("correction") or "")},
            "validation": validation,
            "consensus": {"state": "labelled", "agree_count": 1,
                          "threshold": self.consensus_threshold},
            "playbook_version": None,
            "eval_item": eval_item,
            "score": score,
        }

    def _maybe_promote(
        self, db: Any, playbook_id: str, dim: dict, validation: dict,
        agree_count: int, *, author: Optional[str],
    ) -> tuple[Optional[int], str]:
        """Shared promote-or-flag gate for pack-editing rounds: promote the
        dimension iff it validates AND consensus is met; else flag (not applied)."""
        if validation["valid"] and agree_count >= self.consensus_threshold:
            version = self._promote_dimension(db, playbook_id, dim, author=author)
            return version, "promoted"
        return None, "flagged"

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

    def _consensus_count_routing(
        self, db: Any, *, playbook_id: str, consensus_key: str,
        this_sme: Optional[str],
    ) -> int:
        """Distinct SMEs who proposed the SAME (dimension, route-set) for a
        routing round on this playbook, including the answer in flight.

        The consensus key is stored on each routing eval item's answer as
        `consensus_key` so a route-set match is a single JSONB comparison;
        distinct-by-sme so one SME cannot manufacture consensus."""
        rows = db.fetch_all(
            "SELECT DISTINCT sme_id FROM forge_eval_items "
            "WHERE playbook_id = %s AND answer->>'consensus_key' = %s",
            [playbook_id, consensus_key],
        ) or []
        smes = {r.get("sme_id") for r in rows}
        if this_sme is not None:
            smes.add(this_sme)
        elif None not in smes:
            smes.add(f"__anon__{consensus_key}__pending")
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
        return self._insert_score(
            db, eval_item_id=eval_item_id, session_id=session_id, sme_id=sme_id,
            points=points, reason=reason,
        )

    def _score_label(
        self, db: Any, *, eval_item_id: str, session_id: str,
        sme_id: Optional[str], reason: str,
    ) -> dict:
        """Award the labelling reward for a valid gold label (signal_or_noise /
        critique) — a well-formed label is the deliverable, scored on submission."""
        return self._insert_score(
            db, eval_item_id=eval_item_id, session_id=session_id, sme_id=sme_id,
            points=POINTS_LABEL, reason=reason,
        )

    def _insert_score(
        self, db: Any, *, eval_item_id: str, session_id: str,
        sme_id: Optional[str], points: int, reason: str,
    ) -> dict:
        """Idempotent score insert (one row per eval item)."""
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
