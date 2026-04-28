"""Build a market_events row dict for an exec_change extraction.

SPEC-016 §7 swimlane A2.1.

Pure function. Returns a dict shaped for INSERT INTO market_events. The
caller (connectors/sec_8k/item_5_02.py orchestrator → A7 connector
runner) is responsible for actually writing it.

Idempotency: event_hash is SHA-256 over the canonical inputs (company_id
+ person_name + change_type + effective_date + functional_area +
source_document_id). Re-running produces the same hash, hits the UNIQUE
index, and is a safe no-op.

Impact-tier hint follows SPEC-016 §5.4 + CI HR2.3:
  - C-suite or board → high
  - EVP/SVP          → medium
  - VP / Director    → low

This is a HINT only — the intelligence-layer scoring service (sprint B3)
re-evaluates impact with corroboration, magnitude, entity priority, etc.
But shipping a hint here means the steward / reviewer queue can sort
sensibly even before scoring runs.
"""

from __future__ import annotations

import hashlib
from datetime import date
from typing import Any

from services.extraction.exec_change import ExecChangeExtraction
from services.person_roles import classify_seniority, classify_functional_area


# ────────────────────────────────────────────────────────────────────
# Impact-tier hint (heuristic — final tier set by B3 scoring service)
# ────────────────────────────────────────────────────────────────────

_HIGH_IMPACT_AREAS = frozenset({"CEO", "CFO", "CSO", "CMO", "CCO", "board"})


def _impact_hint(extraction: ExecChangeExtraction) -> str:
    """Map the extraction onto high|medium|low for the steward / reviewer
    sort order. Re-evaluated by B3 with corroboration + entity priority."""
    fa = extraction.functional_area
    if fa is None and extraction.prior_role:
        fa = classify_functional_area(extraction.prior_role)
    if fa is None and extraction.new_role:
        fa = classify_functional_area(extraction.new_role)

    if fa in _HIGH_IMPACT_AREAS:
        return "high"

    title = extraction.prior_role or extraction.new_role or ""
    seniority = classify_seniority(title)
    if seniority == "C-suite":
        return "high"
    if seniority == "EVP/SVP":
        return "medium"
    return "low"


# ────────────────────────────────────────────────────────────────────
# Event hash — idempotency key
# ────────────────────────────────────────────────────────────────────


def _compute_event_hash(
    *,
    company_id: str,
    extraction: ExecChangeExtraction,
    source_document_id: str,
) -> str:
    """SHA-256 over canonical inputs. Stable across re-parses."""
    parts = [
        "exec_change",
        company_id or "",
        extraction.person_name.strip().lower(),
        extraction.change_type,
        extraction.effective_date.isoformat(),
        (extraction.functional_area or ""),
        (extraction.prior_role or "").strip().lower(),
        (extraction.new_role or "").strip().lower(),
        source_document_id or "",
    ]
    payload = "|".join(parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ────────────────────────────────────────────────────────────────────
# Description (human-readable summary stored on the event)
# ────────────────────────────────────────────────────────────────────


def _build_description(
    extraction: ExecChangeExtraction,
    company_name: str,
) -> str:
    role = extraction.prior_role or extraction.new_role or "(role undisclosed)"
    if extraction.change_type == "departure":
        d = f"{extraction.person_name} departure from {role} at {company_name}"
        if extraction.successor_name:
            d += f" (successor: {extraction.successor_name})"
    elif extraction.change_type == "appointment":
        d = f"{extraction.person_name} appointment to {role} at {company_name}"
    elif extraction.change_type == "promotion":
        d = f"{extraction.person_name} promoted to {role} at {company_name}"
    elif extraction.change_type == "role_change":
        d = (
            f"{extraction.person_name} role change at {company_name}: "
            f"{extraction.prior_role} → {extraction.new_role}"
        )
    elif extraction.change_type == "board_election":
        d = f"{extraction.person_name} elected to board of {company_name}"
    elif extraction.change_type == "board_resignation":
        d = f"{extraction.person_name} resigned from board of {company_name}"
    else:
        d = f"{extraction.person_name} change at {company_name}"
    if extraction.reason:
        d += f" — reason: {extraction.reason}"
    return d


# ────────────────────────────────────────────────────────────────────
# Public API
# ────────────────────────────────────────────────────────────────────


def build_event_row(
    *,
    extraction: ExecChangeExtraction,
    company_id: str,
    company_name: str,
    source_document_id: str,
    disclosed_date: date,
) -> dict[str, Any]:
    """Construct the dict to INSERT INTO market_events.

    Caller passes the resolved company_id + company_name (entity
    resolution lives in the orchestrator, not here). Caller writes the
    row to the DB and is responsible for handling UNIQUE-violation on
    event_hash (which means the event is already recorded — safe no-op).
    """
    return {
        "event_type": "exec_change",
        "description": _build_description(extraction, company_name),
        "primary_entity_type": "company",
        "primary_entity_id": company_id,
        "primary_entity_name": company_name,
        "event_date": extraction.effective_date,
        "disclosed_date": disclosed_date,
        "source_tier": "tier_1",   # SEC = tier 1 by SPEC-016 §5.4
        "trust_score": 0.95,       # confirmed-tier source; B2 may downgrade
        "status": "new",
        "event_hash": _compute_event_hash(
            company_id=company_id,
            extraction=extraction,
            source_document_id=source_document_id,
        ),
        "source_feed": "sec_8k_item_5_02",
        # Hint fields (read by reviewer queue / steward sort):
        "impact_hint": _impact_hint(extraction),
        # Payload for downstream consumers (clustering, signal builder):
        "payload": {
            "person_name": extraction.person_name,
            "change_type": extraction.change_type,
            "prior_role": extraction.prior_role,
            "new_role": extraction.new_role,
            "functional_area": extraction.functional_area,
            "successor_name": extraction.successor_name,
            "reason": extraction.reason,
            "transition_id": extraction.transition_id,
        },
        "source_document_id": source_document_id,
    }
