"""SPEC-021 Phase A.5 — Autonomous Move Suggester.

Generates N ranked competitive moves the player could make, given the
war-room context (player entity + optional source signal). Mirrors the
reactor architecture (engine pre-fetches dossier, single LLM call,
parse + validate + persist) but reasons from the player's side.

Public API:
    SUGGESTER_RULE_VERSION
    build_player_dossier(db, entity_type, entity_id) -> dict
    suggest_moves(db, llm, *, war_room, signal_context, n, ...) -> list[dict]

The output dict shape matches what the API persists into move_suggestions
and what the UI renders as ranked cards:
    {move_type, move_payload, rationale, expected_impact_score,
     confidence_score, evidence_basis, evidence_validated,
     stripped_citations}
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from services.war_game_engine import (
    MOVE_TYPES,
    _coerce_confidence_score,
    _parse_json_loose,
    categorize_confidence,
    validate_evidence_basis,
)

logger = logging.getLogger(__name__)


# Bump when the prompt or scoring logic changes — Phase D recalibration
# joins on this column to know which version produced a suggestion.
SUGGESTER_RULE_VERSION = "v1.0.0"


# ────────────────────────────────────────────────────────────────────
# Player dossier
# ────────────────────────────────────────────────────────────────────

def build_player_dossier(
    db,
    entity_type: Optional[str],
    entity_id: Optional[str],
    *,
    max_drugs: int = 8,
    max_trials: int = 6,
    max_events: int = 5,
) -> dict:
    """Pull the player's pipeline + competitive position from DB.

    Mirrors `war_game_engine.build_competitor_dossier` but with a few
    additions tailored to *our* side: pipeline-strength hint, recent
    approvals, mechanism diversity. Defensive — empty arrays + a clear
    coverage statement if data is sparse.
    """
    dossier: dict = {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "drugs": [],
        "trials": [],
        "events": [],
        "pipeline_summary": {},
        "coverage_statement": "No player data available — DB lookup skipped.",
    }
    if not entity_id or entity_type != "company":
        return dossier

    # Drugs the player owns
    try:
        rows = db.fetch_all(
            """SELECT id::text AS id, generic_name, brand_name,
                      mechanism_id::text AS mechanism_id,
                      approval_date
               FROM drugs
               WHERE company_id = %s::uuid
               ORDER BY COALESCE(approval_date, created_at) DESC
               LIMIT %s""",
            [entity_id, max_drugs],
        )
        dossier["drugs"] = [
            {
                "id": r.get("id"),
                "name": r.get("generic_name") or r.get("brand_name"),
                "mechanism_id": r.get("mechanism_id"),
                "approval_date": (
                    r["approval_date"].isoformat()
                    if r.get("approval_date") and hasattr(r["approval_date"], "isoformat")
                    else r.get("approval_date")
                ),
            }
            for r in (rows or [])
        ]
    except Exception:
        logger.debug("player dossier: drugs query failed for %s", entity_id)

    # Active trials (sponsor name match — same heuristic as competitor)
    try:
        rows = db.fetch_all(
            """SELECT id, COALESCE(brief_title, official_title) AS title,
                      phase, status
               FROM clinical_trials
               WHERE sponsor_name ILIKE
                     (SELECT '%%' || name || '%%' FROM companies WHERE id = %s::uuid LIMIT 1)
               ORDER BY last_update_posted DESC NULLS LAST
               LIMIT %s""",
            [entity_id, max_trials],
        )
        dossier["trials"] = [
            {
                "nct": r.get("id"),
                "title": (r.get("title") or "")[:160],
                "phase": r.get("phase"),
                "status": r.get("status"),
            }
            for r in (rows or [])
        ]
    except Exception:
        logger.debug("player dossier: trials query failed for %s", entity_id)

    # Recent events affecting the player
    try:
        rows = db.fetch_all(
            """SELECT event_type, event_date, description
               FROM market_events
               WHERE primary_entity_id = %s::uuid OR drug_id IN (
                   SELECT id FROM drugs WHERE company_id = %s::uuid
               )
               ORDER BY event_date DESC NULLS LAST
               LIMIT %s""",
            [entity_id, entity_id, max_events],
        )
        dossier["events"] = [
            {
                "type": r.get("event_type"),
                "date": (
                    r["event_date"].isoformat()
                    if r.get("event_date") and hasattr(r["event_date"], "isoformat")
                    else r.get("event_date")
                ),
                "description": (r.get("description") or "")[:200],
            }
            for r in (rows or [])
        ]
    except Exception:
        logger.debug("player dossier: events query failed for %s", entity_id)

    # Pipeline summary — phase distribution
    try:
        phase_rows = db.fetch_all(
            """SELECT ct.phase, COUNT(DISTINCT ct.id) AS n
               FROM clinical_trials ct
               JOIN drugs d ON d.id = ct.drug_id
               WHERE d.company_id = %s::uuid
                 AND ct.phase IS NOT NULL
               GROUP BY ct.phase
               ORDER BY ct.phase""",
            [entity_id],
        )
        dossier["pipeline_summary"] = {
            r["phase"]: int(r["n"]) for r in (phase_rows or []) if r.get("phase")
        }
    except Exception:
        logger.debug("player dossier: pipeline summary failed for %s", entity_id)

    # Coverage
    try:
        total_drugs_row = db.fetch_one(
            "SELECT COUNT(*) AS c FROM drugs WHERE company_id = %s::uuid",
            [entity_id],
        )
        total_trials_row = db.fetch_one(
            """SELECT COUNT(*) AS c FROM clinical_trials
               WHERE sponsor_name ILIKE
                     (SELECT '%%' || name || '%%' FROM companies WHERE id = %s::uuid LIMIT 1)""",
            [entity_id],
        )
        total_drugs = (total_drugs_row or {}).get("c", 0) or 0
        total_trials = (total_trials_row or {}).get("c", 0) or 0
        shown_drugs = len(dossier["drugs"])
        shown_trials = len(dossier["trials"])
        dossier["coverage_statement"] = (
            f"Showing {shown_drugs} of {total_drugs} known drugs and "
            f"{shown_trials} of {total_trials} known trials. Real-world "
            f"counts may be higher; reason conservatively about what the "
            f"player actually has available."
        )
    except Exception:
        logger.debug("player dossier: coverage query failed for %s", entity_id)

    return dossier


# ────────────────────────────────────────────────────────────────────
# Prompt
# ────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """You are a competitive strategy advisor to {player_name}.

Given the player's dossier and (optional) signal context, propose {n}
ranked competitive moves the player could make. Each move must be
derivable from the player's dossier — pick assets the player actually
owns. Do NOT invent drugs, trials, or capabilities not in the dossier.

If the dossier is sparse or no asset enables a credible move, return
fewer than {n} suggestions. Honesty beats false optimism.

ALLOWED MOVE TYPES (pick from): {move_types}

For each suggestion, rate:
- expected_impact_score: 0.0 (no impact) to 1.0 (transformational)
  Should reflect both magnitude and probability of the predicted impact.
- confidence_score: 0.0 (no data supports this) to 1.0 (high-confidence
  recommendation backed by dossier evidence)

EVIDENCE_BASIS:
List the dossier IDs/names that support each suggestion. Use REAL
values from the dossier (NCT IDs, drug names, drug_ids). Anything you
can't cite from the dossier will be stripped post-hoc and your
confidence_score downgraded.

Output ONLY a single JSON object, no markdown, no preamble:
{{
  "suggestions": [
    {{
      "move_type": "<one of the move types>",
      "move_payload": {{ /* fields appropriate to the move type */ }},
      "rationale": "2-3 sentences explaining why this move + which assets enable it",
      "evidence_basis": ["NCT...", "drug_name", "drug_id"],
      "expected_impact_score": <number 0.0..1.0>,
      "confidence_score": <number 0.0..1.0>
    }},
    ...
  ]
}}

Order suggestions by expected_impact_score DESCENDING (highest impact first).
"""


def _build_user_content(
    player_dossier: dict,
    signal_context: Optional[dict],
    n: int,
) -> str:
    coverage = player_dossier.get("coverage_statement") or ""
    parts = [
        f"PLAYER DOSSIER ({player_dossier.get('entity_id')}):",
        f"  COVERAGE: {coverage}",
        json.dumps(player_dossier, indent=2, default=str),
    ]
    if signal_context:
        parts.append("")
        parts.append("TRIGGERING SIGNAL CONTEXT:")
        parts.append(json.dumps(signal_context, indent=2, default=str))
    parts.append("")
    parts.append(f"Generate up to {n} ranked move suggestions for this player. "
                 f"Ground in the dossier; honesty beats coverage.")
    return "\n".join(parts)


# ────────────────────────────────────────────────────────────────────
# Validation helpers
# ────────────────────────────────────────────────────────────────────

def _normalize_suggestion(parsed: dict, db=None) -> Optional[dict]:
    """Normalize one LLM-suggested move; return None if the move_type
    is not in the allowed enum (drop the suggestion rather than guess)."""
    move_type = parsed.get("move_type")
    if move_type not in MOVE_TYPES:
        return None

    move_payload = parsed.get("move_payload")
    if not isinstance(move_payload, dict):
        move_payload = {}

    evidence_raw = parsed.get("evidence_basis") or []
    if not isinstance(evidence_raw, list):
        evidence_raw = []
    evidence_raw = [str(e)[:200] for e in evidence_raw][:10]

    if db is not None and evidence_raw:
        validated, stripped = validate_evidence_basis(db, evidence_raw)
    else:
        validated, stripped = list(evidence_raw), []

    confidence_score = _coerce_confidence_score(parsed)
    if stripped:
        confidence_score = max(0.0, confidence_score - 0.2 * len(stripped))

    impact_raw = parsed.get("expected_impact_score")
    try:
        impact_score = max(0.0, min(1.0, float(impact_raw)))
    except (TypeError, ValueError):
        impact_score = 0.5

    return {
        "move_type": move_type,
        "move_payload": move_payload,
        "rationale": (parsed.get("rationale") or "")[:1000],
        "expected_impact_score": impact_score,
        "confidence_score": confidence_score,
        "confidence": categorize_confidence(confidence_score),
        "evidence_basis": validated,
        "stripped_citations": stripped,
        "evidence_validated": len(stripped) == 0,
    }


# ────────────────────────────────────────────────────────────────────
# Public entry point
# ────────────────────────────────────────────────────────────────────

def suggest_moves(
    db,
    llm,
    *,
    player_entity_type: Optional[str],
    player_entity_id: Optional[str],
    player_name: str,
    signal_context: Optional[dict] = None,
    n: int = 3,
) -> list[dict]:
    """Generate up to N ranked move suggestions for the player.

    Returns a list (possibly empty if LLM unavailable / parse failed /
    no move_type matched). Caller persists into move_suggestions table.
    """
    dossier = build_player_dossier(db, player_entity_type, player_entity_id)

    if llm is None or not getattr(llm, "enabled", False):
        logger.info("Move suggester: LLM unavailable, returning empty list")
        return []

    system_prompt = _SYSTEM_PROMPT.format(
        player_name=player_name,
        n=n,
        move_types=" | ".join(MOVE_TYPES),
    )
    user_content = _build_user_content(dossier, signal_context, n)

    try:
        # SPEC-021 D2: telemetry + timeout wrapper. Same shape as war_game_engine.
        try:
            from services.llm_telemetry import chat_with_telemetry
            reply = chat_with_telemetry(
                llm, db,
                system=system_prompt,
                user=user_content,
                caller="suggester",
                prompt_version=f"suggester-{SUGGESTER_RULE_VERSION}",
                max_tokens=1500,
                timeout_seconds=45.0,
            )
        except Exception:
            reply = llm.raw_chat(system=system_prompt, user=user_content, max_tokens=1500)
    except Exception as exc:
        logger.warning("Move suggester LLM call failed: %s", exc)
        return []

    parsed = _parse_json_loose(reply or "")
    if not parsed or "suggestions" not in parsed:
        logger.warning("Move suggester: could not parse JSON suggestions")
        return []

    raw_list = parsed.get("suggestions") or []
    if not isinstance(raw_list, list):
        return []

    out: list[dict] = []
    for raw in raw_list[:n]:
        if not isinstance(raw, dict):
            continue
        norm = _normalize_suggestion(raw, db=db)
        if norm is not None:
            out.append(norm)

    # Stable sort by expected_impact_score DESC (LLM may not have)
    out.sort(key=lambda s: s["expected_impact_score"], reverse=True)
    return out
