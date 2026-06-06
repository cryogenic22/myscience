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


# ════════════════════════════════════════════════════════════════════
# DF-5 round ② — "Signal or noise?" (materiality)
# ════════════════════════════════════════════════════════════════════
#
# The SME is shown THREE REAL signals/events pulled from the DB and asked which
# is the MOST MATERIAL (and why). Their pick persists a materiality LABEL as a
# gold eval item and feeds the materiality model's expectations (the chosen
# signal's claim_type is the gold "this is what a senior analyst flags first").
#
# Grounded: the candidate signals are real `signals` rows (richest/highest-impact
# first). Raise rather than fabricate when too few real signals exist.

# Why an SME might flag a signal as material — a constrained reason set so the
# label is structured (maps onto the materiality scorer's claim_type / criticality
# vocabularies), never free text the model can't learn from.
MATERIALITY_REASONS: list[dict[str, str]] = [
    {"key": "clinical_readout", "label": "Clinical readout / efficacy result"},
    {"key": "regulatory_action", "label": "Regulatory action (approval / CRL / label)"},
    {"key": "safety_signal", "label": "Safety signal (AE / warning)"},
    {"key": "pricing_change", "label": "Pricing / access change"},
    {"key": "competitive_move", "label": "Competitive / deal move"},
    {"key": "noise", "label": "Routine / low-materiality (noise)"},
]

_REASONS_BY_KEY = {r["key"] for r in MATERIALITY_REASONS}


def reason_is_valid(key: str) -> bool:
    """Is `key` one of the constrained materiality reasons?"""
    return (key or "").strip() in _REASONS_BY_KEY


def _pick_candidate_signals(db: Any, limit: int = 3) -> list[dict[str, Any]]:
    """Three real signals to judge for materiality. Highest-impact / newest first
    so the round is about signals worth an analyst's attention — never fabricated."""
    rows = db.fetch_all(
        "SELECT id::text AS signal_id, headline, summary, "
        "       primary_entity_name, primary_entity_type, kbq_tags, "
        "       impact_tier, confidence_tier, created_at "
        "FROM signals "
        "WHERE headline IS NOT NULL AND headline <> '' "
        "ORDER BY (impact_tier = 'high') DESC NULLS LAST, created_at DESC "
        "LIMIT %s",
        [max(limit, 3)],
    ) or []
    out: list[dict[str, Any]] = []
    for r in rows[:limit]:
        out.append({
            "signal_id": r["signal_id"],
            "headline": r.get("headline") or "",
            "summary": (r.get("summary") or "")[:280],
            "entity_name": r.get("primary_entity_name"),
            "entity_type": r.get("primary_entity_type"),
            "kbq_tags": list(r.get("kbq_tags") or []),
            "impact_tier": r.get("impact_tier"),
        })
    return out


def generate_signal_or_noise_round(
    db: Any,
    *,
    intent: str = "materiality",
    playbook_id: str = "materiality.signal_triage",
    signals: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Build a "Signal or noise?" round FROM real DB signals.

    The SME picks the MOST MATERIAL of three real signals + a constrained reason.
    Returns {round_type, intent, playbook_id, prompt, payload}.

    Raises ValueError if fewer than three real signals are available — we never
    fabricate a candidate signal."""
    sigs = signals or _pick_candidate_signals(db, limit=3)
    if len(sigs) < 3:
        raise ValueError(
            "domain_forge: need at least three real signals to build a "
            "signal-or-noise round (found fewer in the signals table)"
        )
    prompt = (
        "Of these three real signals, which is the MOST MATERIAL to act on — "
        "and why? (Your pick labels what a senior analyst flags first.)"
    )
    payload = {
        # The constrained choice set: pick ONE signal_id + ONE reason.
        "signals": sigs,
        "reasons": [dict(r) for r in MATERIALITY_REASONS],
        "instructions": (
            "Select the single most material signal and the reason it matters. "
            "Your label trains the materiality model's expectations."
        ),
    }
    return {
        "round_type": "signal_or_noise",
        "intent": intent,
        "playbook_id": playbook_id,
        "prompt": prompt,
        "payload": payload,
    }


# ════════════════════════════════════════════════════════════════════
# DF-5 round ③ — "Where does the answer live?" (routing)
# ════════════════════════════════════════════════════════════════════
#
# Given a REAL entity + a dimension on a real playbook, the SME picks which
# fact-types / sources they'd TRUST to answer that dimension. Their pick
# validates/edits the dimension's `routes` on the playbook (via the existing
# authoring + validation), so an SME directly tunes where the planner looks.
#
# The candidate routes are the union of the predicates the ledger actually
# routes for the dimension's domain + the whitelisted source for it — every
# option is plannable (validation gate), never free text.

# Candidate routable options per dimension, drawn from the live ledger predicate
# map + whitelisted sources/links. The SME selects a SUBSET they trust; the
# selection becomes the dimension's routes (validated before any pack edit).
ROUTING_OPTIONS_BY_DIMENSION: dict[str, list[dict[str, Any]]] = {
    "mechanism": [
        {"key": "predicate:mechanism_of_action", "label": "Mechanism-of-action facts"},
        {"key": "predicate:target_activity", "label": "Molecular target / activity facts"},
    ],
    "efficacy": [
        {"key": "predicate:trial_result", "label": "Trial-result facts"},
        {"key": "predicate:clinical_trial", "label": "Registered clinical-trial facts"},
        {"key": "predicate:key_publication", "label": "Key-publication facts"},
    ],
    "safety": [
        {"key": "predicate:adverse_event", "label": "Adverse-event facts"},
        {"key": "predicate:safety_signal", "label": "Safety-signal / boxed-warning facts"},
        {"key": "predicate:label_indication", "label": "Label-indication facts"},
    ],
    "dosing": [
        {"key": "predicate:label_indication", "label": "Label-indication facts"},
    ],
    "indication": [
        {"key": "predicate:label_indication", "label": "Label-indication facts"},
        {"key": "predicate:disease_evidence", "label": "Disease / epidemiology facts"},
    ],
    "regulatory": [
        {"key": "predicate:regulatory_approval", "label": "Regulatory-approval facts"},
        {"key": "predicate:fda_approval_date", "label": "FDA approval-date facts"},
        {"key": "source:regulatory_milestones", "label": "Regulatory-milestones table"},
    ],
    "pricing_access": [
        {"key": "predicate:wac_usd", "label": "WAC list-price facts"},
        {"key": "predicate:pricing_intent", "label": "Pricing-intent facts"},
        {"key": "predicate:product_sales", "label": "Product-sales facts"},
    ],
    "competition": [
        {"key": "predicate:competitor", "label": "Competitor facts"},
        {"key": "predicate:market_share", "label": "Market-share facts"},
        {"key": "link:COMPETES_WITH", "label": "Competes-with graph edges"},
    ],
}


def routing_options_for_dimension(dimension_key: str) -> list[dict[str, Any]]:
    """The constrained, plannable route options offered for a dimension."""
    return [dict(o) for o in ROUTING_OPTIONS_BY_DIMENSION.get(
        (dimension_key or "").strip(), [])]


_DIMENSION_LABELS = {o["key"]: o["label"] for o in DIMENSION_OPTIONS}
_DIMENSION_LABELS.update({"indication": "Indications", "dosing": "Dosing & administration"})


def generate_routing_round(
    db: Any,
    *,
    intent: str = "dossier",
    playbook_id: str = "dossier.drug",
    dimension_key: str = "safety",
    entities: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Build a "Where does the answer live?" round FROM a real entity + dimension.

    The SME picks which fact-types/sources they trust for the dimension; the
    selection edits the dimension's `routes` on the playbook (consensus-gated).
    Returns {round_type, intent, playbook_id, prompt, payload}.

    Raises ValueError if no real entity is available, or the dimension offers no
    routable options (never fabricates a route)."""
    options = routing_options_for_dimension(dimension_key)
    if not options:
        raise ValueError(
            f"domain_forge: no routable options for dimension '{dimension_key}' "
            f"(known: {sorted(ROUTING_OPTIONS_BY_DIMENSION)})"
        )
    ents = entities or _pick_compare_entities(db, limit=1)
    if not ents:
        raise ValueError(
            "domain_forge: need a real entity to build a routing round "
            "(none found in the spine)"
        )
    ent = ents[0]
    dim_label = _DIMENSION_LABELS.get(dimension_key, dimension_key)
    prompt = (
        f"To answer the '{dim_label}' question about {ent['label']}, which "
        f"fact-types and sources would you TRUST? Pick the ones the system "
        f"should rely on."
    )
    payload = {
        "entity": ent,
        "dimension": {"key": dimension_key, "label": dim_label},
        # The SME selects a subset of these route keys; each is plannable.
        "options": options,
        "instructions": (
            "Select every fact-type / source you would trust for this "
            "dimension. Your selection becomes the playbook's routes."
        ),
    }
    return {
        "round_type": "routing",
        "intent": intent,
        "playbook_id": playbook_id,
        "prompt": prompt,
        "payload": payload,
    }


# ════════════════════════════════════════════════════════════════════
# DF-5 round ④ — "Grade the machine" (critique)
# ════════════════════════════════════════════════════════════════════
#
# The SME is shown a REAL machine-generated comparison cell (a fact the ledger
# actually emitted for an entity) and asked to GRADE it — correct / partially
# correct / wrong (+ an optional correction). Their grade is a direct accuracy
# eval label on real model output.
#
# Grounded: the cell is a real `facts` row rendered as a claim. Raise rather
# than fabricate when no such fact exists.

# The constrained grade set — a direct accuracy label.
CRITIQUE_GRADES: list[dict[str, str]] = [
    {"key": "correct", "label": "Correct"},
    {"key": "partial", "label": "Partially correct"},
    {"key": "wrong", "label": "Wrong"},
]

_GRADES_BY_KEY = {g["key"] for g in CRITIQUE_GRADES}


def grade_is_valid(key: str) -> bool:
    """Is `key` one of the constrained critique grades?"""
    return (key or "").strip() in _GRADES_BY_KEY


def _render_fact_claim(predicate: str, object_value: Any) -> str:
    """Render a real fact row as a short human-readable machine claim."""
    label = (predicate or "fact").replace("_", " ")
    val: Any = object_value
    if isinstance(val, dict):
        # Prefer the most claim-like field a fact_emitter writes.
        for k in ("mechanism", "claim", "value", "text", "summary", "name"):
            if val.get(k):
                val = val[k]
                break
        else:
            val = ", ".join(f"{k}={v}" for k, v in val.items() if k != "emitter")
    return f"{label}: {val}"[:300]


def _pick_machine_cell(
    db: Any, *, predicate: str = "mechanism_of_action",
) -> Optional[dict[str, Any]]:
    """A real machine-generated cell: one ledger fact for an entity, rendered."""
    row = db.fetch_one(
        "SELECT f.id::text AS fact_id, f.predicate, f.object_value, f.fact_class, "
        "       f.subject_entity_id::text AS entity_id, d.generic_name AS entity_label "
        "FROM facts f "
        "LEFT JOIN drugs d ON d.id::text = f.subject_entity_id "
        "WHERE f.predicate = %s AND f.subject_entity_id IS NOT NULL "
        "  AND f.object_value IS NOT NULL "
        "ORDER BY f.created_at DESC NULLS LAST "
        "LIMIT 1",
        [predicate],
    )
    if not row:
        return None
    return {
        "fact_id": row["fact_id"],
        "predicate": row.get("predicate"),
        "entity_id": row.get("entity_id"),
        "entity_label": row.get("entity_label") or row.get("entity_id"),
        "claim": _render_fact_claim(row.get("predicate"), row.get("object_value")),
        "fact_class": row.get("fact_class"),
    }


def generate_critique_round(
    db: Any,
    *,
    intent: str = "critique",
    playbook_id: str = "critique.cell_accuracy",
    predicate: str = "mechanism_of_action",
    cell: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Build a "Grade the machine" round FROM a real ledger fact.

    The SME grades a real machine-generated cell (correct / partial / wrong +
    optional correction) → a direct accuracy eval label.
    Returns {round_type, intent, playbook_id, prompt, payload}.

    Raises ValueError if no real fact is available for the predicate (never
    fabricates a cell to grade)."""
    cell = cell or _pick_machine_cell(db, predicate=predicate)
    if not cell:
        raise ValueError(
            f"domain_forge: no real ledger fact for predicate '{predicate}' to "
            f"build a critique round (nothing to grade)"
        )
    prompt = (
        f"The system generated this cell for {cell.get('entity_label')}:\n\n"
        f"  “{cell.get('claim')}”\n\n"
        f"Grade it — is it correct, partially correct, or wrong? Add a "
        f"correction if needed."
    )
    payload = {
        "cell": cell,
        "grades": [dict(g) for g in CRITIQUE_GRADES],
        "instructions": (
            "Grade the machine-generated cell. Your grade is a direct accuracy "
            "label on real model output."
        ),
    }
    return {
        "round_type": "critique",
        "intent": intent,
        "playbook_id": playbook_id,
        "prompt": prompt,
        "payload": payload,
    }
