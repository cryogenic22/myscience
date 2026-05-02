"""SPEC-021 — War game reaction engine.

Generates competitor reactions to a player move, grounded in our DB
(no fabrication). Borrows the move/reaction taxonomy from
specs/test.tsx and the dossier-based grounding pattern from
services/llm.py.

Public API:
    MOVE_TYPES, REACTION_TYPES, REACTION_DIMENSION_KEYS  — enums
    build_competitor_dossier(db, company_id) -> dict
    generate_reactions(db, llm, war_room, round_payload, competitors)
        -> list[dict]   (one per competitor)

The reaction dict shape matches what the API layer persists into
war_room_reactions: competitor_*, reaction_type, headline,
specific_action, asset_leveraged, rationale, evidence_basis, scores,
confidence.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────
# Taxonomy (mirror of specs/test.tsx)
# ────────────────────────────────────────────────────────────────────

MOVE_TYPES: tuple[str, ...] = (
    "price_cut",
    "new_indication",
    "label_expansion",
    "trial_readout",
    "acquisition",
    "formulation_switch",
    "geo_expansion",
    "segment_pivot",
)

REACTION_TYPES: tuple[str, ...] = (
    "match_price",
    "counter_launch",
    "accelerate_trial",
    "seek_partnership",
    "attack_label",
    "hold_position",
    "exit_segment",
    "differentiate",
)

REACTION_DIMENSION_KEYS: tuple[str, ...] = (
    "market_share_delta",      # -10..+10 (% pts)
    "time_to_execute_months",  # 1..36
    "capex_required_musd",     # 50..3000
    "regulatory_risk",         # 1..10
    "payer_acceptance",        # 1..10
)

_DIM_RANGES: dict[str, tuple[float, float]] = {
    "market_share_delta":     (-10.0, 10.0),
    "time_to_execute_months": (1.0, 36.0),
    "capex_required_musd":    (50.0, 3000.0),
    "regulatory_risk":        (1.0, 10.0),
    "payer_acceptance":       (1.0, 10.0),
}


def is_valid_move_type(move_type: str) -> bool:
    return move_type in MOVE_TYPES


# ────────────────────────────────────────────────────────────────────
# Dossier — what the prompt sees about a competitor
# ────────────────────────────────────────────────────────────────────

def build_competitor_dossier(db, company_id: Optional[str], *, max_drugs: int = 6,
                              max_trials: int = 5, max_events: int = 5) -> dict:
    """Pull a compact dossier from the live DB.

    Defensive: missing tables / queries return empty arrays so the
    engine still produces a `hold_position` reaction rather than
    crashing.
    """
    dossier: dict = {"company_id": company_id, "drugs": [], "trials": [], "events": []}
    if not company_id:
        return dossier

    try:
        rows = db.fetch_all(
            """SELECT id::text AS id, generic_name, brand_name, mechanism_id::text AS mechanism_id
               FROM drugs
               WHERE company_id = %s::uuid
               ORDER BY COALESCE(approval_date, created_at) DESC
               LIMIT %s""",
            [company_id, max_drugs],
        )
        dossier["drugs"] = [
            {
                "id": r.get("id"),
                "name": r.get("generic_name") or r.get("brand_name"),
                "mechanism_id": r.get("mechanism_id"),
            }
            for r in (rows or [])
        ]
    except Exception:
        logger.debug("dossier: drugs query failed for %s", company_id)

    try:
        rows = db.fetch_all(
            """SELECT id, COALESCE(brief_title, official_title) AS title,
                      phase, status
               FROM clinical_trials
               WHERE sponsor_name ILIKE
                     (SELECT '%%' || name || '%%' FROM companies WHERE id = %s::uuid LIMIT 1)
               ORDER BY last_update_posted DESC NULLS LAST
               LIMIT %s""",
            [company_id, max_trials],
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
        logger.debug("dossier: trials query failed for %s", company_id)

    try:
        rows = db.fetch_all(
            """SELECT event_type, event_date, description
               FROM market_events
               WHERE primary_entity_id = %s::uuid OR drug_id IN (
                   SELECT id FROM drugs WHERE company_id = %s::uuid
               )
               ORDER BY event_date DESC NULLS LAST
               LIMIT %s""",
            [company_id, company_id, max_events],
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
        logger.debug("dossier: events query failed for %s", company_id)

    return dossier


# ────────────────────────────────────────────────────────────────────
# Prompt construction
# ────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """You are a deterministic strategy engine playing as {competitor_name}.
{player_name} just executed a structured competitive move in the {game_phase} phase.

GROUNDING RULES (no-fabrication invariant):
1. Reactions MUST be derivable from {competitor_name}'s dossier — pick the asset
   (drug name, NCT, mechanism) that best enables the reaction.
2. Every numeric score must be justifiable from dossier evidence.
3. If no asset enables a credible reaction, choose hold_position. Do NOT invent
   capabilities, drugs, or trials that are not in the dossier.
4. Be deterministic and conservative. Do not optimise narratives.

REACTION ENUM (pick one): {reaction_types}

SCORING:
- market_share_delta: -10 to +10 (% pts; positive = {competitor_name} gains)
- time_to_execute_months: 1 to 36
- capex_required_musd: 50 to 3000
- regulatory_risk: 1 (low) to 10 (high)
- payer_acceptance: 1 (weak) to 10 (strong)

Output ONLY a single JSON object, no markdown, no preamble:
{{
  "reaction_type": "<one of the enum>",
  "headline": "8-12 word headline",
  "specific_action": "concrete action with target asset name",
  "asset_leveraged": {{"id": "drug_id or NCT", "name": "asset name", "rationale": "why this asset"}},
  "rationale": "2-3 sentences citing dossier IDs/names",
  "evidence_basis": ["NCT...", "drug_id ...", "..."],
  "scores": {{
    "market_share_delta": <number>,
    "time_to_execute_months": <number>,
    "capex_required_musd": <number>,
    "regulatory_risk": <number>,
    "payer_acceptance": <number>
  }},
  "confidence": "high|medium|low"
}}
"""


def _build_user_content(player_name: str, move_type: str, move_payload: dict,
                         competitor_dossier: dict, history: list) -> str:
    return (
        f"PLAYER MOVE ({player_name}):\n"
        f"  type: {move_type}\n"
        f"  payload: {json.dumps(move_payload, default=str)}\n\n"
        f"YOUR DOSSIER ({competitor_dossier.get('company_id')}):\n"
        f"{json.dumps(competitor_dossier, indent=2, default=str)}\n\n"
        f"RECENT HISTORY (last few rounds):\n"
        f"{json.dumps(history[-4:], indent=2, default=str)}\n\n"
        f"Generate your reaction. Pick from enum, ground in dossier, score conservatively."
    )


# ────────────────────────────────────────────────────────────────────
# JSON parsing + clamping
# ────────────────────────────────────────────────────────────────────

def _parse_json_loose(text: str) -> Optional[dict]:
    if not text:
        return None
    cleaned = text.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    # Try to find a JSON object substring
    start = cleaned.find("{")
    if start == -1:
        return None
    depth = 0
    for i, ch in enumerate(cleaned[start:], start=start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(cleaned[start:i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def _clamp_scores(scores: Any) -> dict:
    if not isinstance(scores, dict):
        scores = {}
    out: dict = {}
    for key, (lo, hi) in _DIM_RANGES.items():
        v = scores.get(key)
        try:
            num = float(v)
        except (TypeError, ValueError):
            num = (lo + hi) / 2
        out[key] = max(lo, min(hi, num))
    return out


def _hold_position(competitor_name: str, reason: str) -> dict:
    return {
        "reaction_type": "hold_position",
        "headline": "Holding position pending data",
        "specific_action": "Monitor",
        "asset_leveraged": {"id": "n/a", "name": "n/a", "rationale": reason},
        "rationale": reason,
        "evidence_basis": [],
        "scores": {
            "market_share_delta": 0.0,
            "time_to_execute_months": 6.0,
            "capex_required_musd": 50.0,
            "regulatory_risk": 5.0,
            "payer_acceptance": 5.0,
        },
        "confidence": "low",
    }


def _normalize_reaction(parsed: dict, competitor: dict) -> dict:
    rxn_type = parsed.get("reaction_type")
    if rxn_type not in REACTION_TYPES:
        rxn_type = "hold_position"

    asset = parsed.get("asset_leveraged")
    if not isinstance(asset, dict):
        asset = {"id": "", "name": "", "rationale": ""}

    evidence = parsed.get("evidence_basis") or []
    if not isinstance(evidence, list):
        evidence = []

    confidence = parsed.get("confidence")
    if confidence not in ("high", "medium", "low"):
        confidence = "low"

    return {
        "competitor_company_id": competitor.get("id"),
        "competitor_company_name": competitor.get("name"),
        "reaction_type": rxn_type,
        "headline": (parsed.get("headline") or "")[:200],
        "specific_action": (parsed.get("specific_action") or "")[:500],
        "asset_leveraged": asset,
        "rationale": (parsed.get("rationale") or "")[:1000],
        "evidence_basis": [str(e)[:200] for e in evidence][:10],
        "scores": _clamp_scores(parsed.get("scores")),
        "confidence": confidence,
    }


# ────────────────────────────────────────────────────────────────────
# Public entry point
# ────────────────────────────────────────────────────────────────────

def generate_reactions(
    db,
    llm,
    *,
    player_name: str,
    move_type: str,
    move_payload: dict,
    competitors: list[dict],
    game_phase: str = "launch",
    history: Optional[list] = None,
) -> list[dict]:
    """Run reaction generation for each competitor.

    competitors: list of dicts with at least {id, name}.
    Returns list of reaction dicts (one per competitor) in the same order.
    """
    history = history or []
    out: list[dict] = []

    for competitor in competitors:
        comp_name = competitor.get("name") or "Unknown"
        comp_id = competitor.get("id")
        dossier = build_competitor_dossier(db, comp_id)

        if llm is None or not getattr(llm, "enabled", False):
            out.append({
                **_hold_position(comp_name, "LLM not available — fallback hold"),
                "competitor_company_id": comp_id,
                "competitor_company_name": comp_name,
            })
            continue

        system_prompt = _SYSTEM_PROMPT.format(
            competitor_name=comp_name,
            player_name=player_name,
            game_phase=game_phase,
            reaction_types=" | ".join(REACTION_TYPES),
        )
        user_content = _build_user_content(
            player_name, move_type, move_payload, dossier, history,
        )

        try:
            reply = llm.synthesize(
                system_prompt=system_prompt,
                user_content=user_content,
                max_tokens=900,
            )
        except Exception as exc:
            logger.warning("LLM reaction call failed for %s: %s", comp_name, exc)
            out.append({
                **_hold_position(comp_name, "LLM call failed — fallback hold"),
                "competitor_company_id": comp_id,
                "competitor_company_name": comp_name,
            })
            continue

        parsed = _parse_json_loose(reply or "")
        if not parsed:
            out.append({
                **_hold_position(comp_name, "Could not parse LLM JSON"),
                "competitor_company_id": comp_id,
                "competitor_company_name": comp_name,
            })
            continue

        out.append(_normalize_reaction(parsed, {"id": comp_id, "name": comp_name}))

    return out
