"""DF-1 — round prompt generation FROM real DB entities.

Round type ① "What matters?": the SME is shown a REAL compare question (two
real drugs pulled from the DB) and asked to pick / rank the analytical
dimensions that matter for answering it. Their constrained choice becomes
both a playbook edit (the elicited dimension) and a gold eval label.

The candidate dimensions (DIMENSION_OPTIONS) are the SAME analytical
dimensions the compare playbook already encodes — each maps to a real,
validated ledger predicate route — so an SME pick is always a routable
dimension, never free text the planner can't execute.

Reuse: drug entities come straight from the `drugs` spine (the same table
dossier_kb resolves against); the option→route map mirrors the compare
seed playbook so a forged dimension is immediately plannable.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


# Candidate analytical dimensions for a drug-vs-drug compare. Each carries the
# routable predicate(s) it elicits into a playbook (mirrors the compare seed).
# The SME picks/ranks FROM this constrained set — so every pick is plannable.
DIMENSION_OPTIONS: list[dict[str, Any]] = [
    {"key": "mechanism", "label": "Mechanism of action",
     "routes": ["predicate:mechanism_of_action"],
     "sub_question": "What is {entity}'s mechanism of action / molecular target?"},
    {"key": "efficacy", "label": "Efficacy / endpoints",
     "routes": ["predicate:trial_result", "predicate:clinical_trial"],
     "sub_question": "What efficacy did {entity} show on its primary trial endpoints?"},
    {"key": "safety", "label": "Safety profile",
     "routes": ["predicate:adverse_event", "predicate:safety_signal"],
     "sub_question": "What is {entity}'s safety profile — adverse events and warnings?"},
    {"key": "dosing", "label": "Dosing & administration",
     "routes": ["predicate:label_indication"],
     "sub_question": "How is {entity} dosed and administered?"},
    {"key": "regulatory", "label": "Regulatory status",
     "routes": ["predicate:regulatory_approval", "source:regulatory_milestones"],
     "sub_question": "What is {entity}'s regulatory / approval status and timeline?"},
    {"key": "pricing_access", "label": "Pricing & access",
     "routes": ["predicate:wac_usd", "predicate:product_sales"],
     "sub_question": "What is known about {entity}'s pricing, sales, and payer access?"},
    {"key": "competition", "label": "Competitive position",
     "routes": ["predicate:competitor", "link:COMPETES_WITH"],
     "sub_question": "Who does {entity} compete with and what is its market position?"},
]

_OPTIONS_BY_KEY = {o["key"]: o for o in DIMENSION_OPTIONS}


def option_for_key(key: str) -> Optional[dict[str, Any]]:
    """The dimension option spec for a key (its routes + sub_question), or None."""
    return _OPTIONS_BY_KEY.get((key or "").strip())


def _pick_compare_entities(db: Any, limit: int = 2) -> list[dict[str, Any]]:
    """Two real, fact-rich drugs from the spine to build a grounded compare
    question. Richness-ranked (most facts first) so the round is about drugs the
    system can actually answer for — never a hollow pairing."""
    rows = db.fetch_all(
        "SELECT d.id::text AS entity_id, d.generic_name AS label, "
        "COUNT(f.id) AS nf "
        "FROM drugs d "
        "LEFT JOIN facts f ON f.subject_entity_id = d.id::text "
        "WHERE d.record_status IS DISTINCT FROM 'superseded' "
        "  AND d.generic_name IS NOT NULL "
        "GROUP BY d.id, d.generic_name "
        "ORDER BY nf DESC NULLS LAST "
        "LIMIT %s",
        [max(limit, 2)],
    ) or []
    out: list[dict[str, Any]] = []
    for r in rows[:limit]:
        out.append({
            "entity_id": r["entity_id"],
            "entity_type": "drug",
            "label": r.get("label") or r["entity_id"],
        })
    return out


def generate_what_matters_round(
    db: Any,
    *,
    intent: str = "compare",
    playbook_id: str = "compare.drug_x_drug",
    entities: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Build a "What matters?" round payload FROM real DB entities.

    Returns {round_type, intent, playbook_id, prompt, payload} ready to persist.
    `entities` may be supplied (e.g. for a deterministic test); otherwise two
    fact-rich real drugs are pulled from the spine.

    Raises ValueError if fewer than two real entities are available — we never
    fabricate a compare pairing.
    """
    ents = entities or _pick_compare_entities(db, limit=2)
    if len(ents) < 2:
        raise ValueError(
            "domain_forge: need at least two real drug entities to build a "
            "compare round (none/one found in the spine)"
        )
    a, b = ents[0]["label"], ents[1]["label"]
    prompt = (
        f"To compare {a} vs {b}, which analytical dimensions matter most — "
        f"and in what priority order?"
    )
    payload = {
        "entities": ents,
        # The constrained choice set: the SME picks/ranks FROM these. Each option
        # carries its routable predicate(s) so a pick is immediately plannable.
        "options": [
            {"key": o["key"], "label": o["label"], "routes": list(o["routes"])}
            for o in DIMENSION_OPTIONS
        ],
        "instructions": (
            "Select the dimensions that matter and rank them (most important "
            "first). Your top pick is forged into the answer playbook."
        ),
    }
    return {
        "round_type": "what_matters",
        "intent": intent,
        "playbook_id": playbook_id,
        "prompt": prompt,
        "payload": payload,
    }
