"""Event-row builder for SPL label-change events.

SPEC-016 §7 swimlane A4.2 (Cycle 6).

Source = FDA-published SPL revision via DailyMed → tier_1 trust score
(0.95). Boxed Warning / Contraindications / Warnings additions get
high-impact hint. Indications additions are medium. Anything else
is low.

Idempotency: event_hash is SHA-256 over (drug_id, setid, loinc_code,
change_kind, prev_text_hash, new_text_hash, source_document_id).
Re-running on the same revision-pair yields the same hash.
"""

from __future__ import annotations

import hashlib
from datetime import date
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from services.spl_diff_service import SectionChange


# ────────────────────────────────────────────────────────────────────
# Impact-tier hint
# ────────────────────────────────────────────────────────────────────


_HIGH_IMPACT_LOINCS = {
    "34066-1",  # BOXED WARNING
    "34070-3",  # CONTRAINDICATIONS
    "43685-7",  # WARNINGS AND PRECAUTIONS
}

_MEDIUM_IMPACT_LOINCS = {
    "34067-9",  # INDICATIONS AND USAGE
    "34068-7",  # DOSAGE AND ADMINISTRATION
    "34071-1",  # ADVERSE REACTIONS
}


def _impact_hint(change: "SectionChange") -> str:
    if change.loinc_code in _HIGH_IMPACT_LOINCS:
        return "high"
    if change.loinc_code in _MEDIUM_IMPACT_LOINCS:
        return "medium"
    return "low"


# ────────────────────────────────────────────────────────────────────
# Event hash
# ────────────────────────────────────────────────────────────────────


def _hash_text(text: Optional[str]) -> str:
    if not text:
        return ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _compute_event_hash(
    *,
    drug_id: str,
    setid: str,
    change: "SectionChange",
    source_document_id: str,
) -> str:
    parts = [
        "label_change",
        drug_id or "",
        setid or "",
        change.loinc_code,
        change.kind,
        _hash_text(change.prev_text),
        _hash_text(change.new_text),
        source_document_id or "",
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


# ────────────────────────────────────────────────────────────────────
# Description
# ────────────────────────────────────────────────────────────────────


def _build_description(
    change: "SectionChange",
    drug_name: str,
) -> str:
    verb = {
        "added": "added",
        "modified": "modified",
        "removed": "removed",
    }.get(change.kind, change.kind)
    return f"{drug_name} label: {change.display_name} {verb}"


# ────────────────────────────────────────────────────────────────────
# Public API
# ────────────────────────────────────────────────────────────────────


def build_event_row(
    *,
    change: "SectionChange",
    drug_id: str,
    drug_name: str,
    company_id: str,
    setid: str,
    source_document_id: str,
    disclosed_date: date,
) -> dict[str, Any]:
    payload = {
        "loinc_code": change.loinc_code,
        "section_display_name": change.display_name,
        "change_kind": change.kind,
        "prev_text": change.prev_text,
        "new_text": change.new_text,
        "setid": setid,
        "drug_name": drug_name,
        "company_id": company_id,
    }

    return {
        "event_type": "label_change",
        "description": _build_description(change, drug_name),
        "primary_entity_type": "drug",
        "primary_entity_id": drug_id,
        "primary_entity_name": drug_name,
        "event_date": disclosed_date,
        "disclosed_date": disclosed_date,
        "source_tier": "tier_1",   # FDA-published label
        "trust_score": 0.95,
        "status": "new",
        "event_hash": _compute_event_hash(
            drug_id=drug_id,
            setid=setid,
            change=change,
            source_document_id=source_document_id,
        ),
        "source_feed": "dailymed_spl_diff",
        "impact_hint": _impact_hint(change),
        "payload": payload,
        "source_document_id": source_document_id,
    }
