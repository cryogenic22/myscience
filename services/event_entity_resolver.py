"""PB-H19 — resolve orphaned market_events to entities so they become facts.

The strategically valuable event types (approval, trial_readout, ma_deal,
regulatory_setback, supply_disruption, pricing, safety_signal, patent_ip) are
ingested with NO primary_entity_id and NO drug_id — their drug/company is
named only in the free-text description (e.g. "FDA approves Lilly's Foundayo
(orforglipron)"). `event_to_fact()` then returns None (no subject), so these
events NEVER enter the facts ledger; only RECALL_CLASS_I (which carries
drug_id) becomes facts. Live audit (4 Jun 2026): 264/264 trial_readout,
246/246 approval, 100/100 ma_deal, 68/68 regulatory_setback fully orphaned.

This module resolves the entity from the event text against the existing
drug / company / alias vocabulary and backfills the FK, so the
events→facts backfill (`scripts/backfill_facts.py`) then lifts them.

Deterministic name-matching (no LLM): longest, whole-word, case-insensitive
match against known names. Grounded in the entity spine; an LLM/NER extraction
pass is a future enhancement. Reuses the drugs/companies/entity_aliases spine.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# Event types whose entity lives only in the description. (RECALL_CLASS_I and
# general are excluded: recalls already carry drug_id; "general" is too vague.)
HIGH_VALUE_EVENT_TYPES: tuple[str, ...] = (
    "approval",
    "trial_readout",
    "ma_deal",
    "regulatory_setback",
    "supply_disruption",
    "pricing",
    "safety_signal",
    "patent_ip",
)

# Names shorter than this are too ambiguous to match safely in free text.
MIN_NAME_LEN = 5


@dataclass(frozen=True)
class VocabEntry:
    name: str          # original display name
    name_lower: str
    entity_type: str   # 'drug' | 'company'
    entity_id: str


def load_vocabulary(db) -> list[VocabEntry]:
    """Build the match vocabulary from drugs + companies + verified aliases.

    Sorted longest-name-first so the most specific match wins (e.g. a brand
    "Foundayo" beats a generic substring). Names < MIN_NAME_LEN or purely
    numeric are dropped to avoid false positives.
    """
    entries: dict[tuple[str, str, str], VocabEntry] = {}

    def _add(name: Optional[str], etype: str, eid) -> None:
        if not name or eid is None:
            return
        nm = str(name).strip()
        if len(nm) < MIN_NAME_LEN or nm.isdigit():
            return
        key = (nm.lower(), etype, str(eid))
        entries.setdefault(key, VocabEntry(nm, nm.lower(), etype, str(eid)))

    # Drugs carry brand_name + generic_name (no single 'name' column); both
    # map to the same drug id so either spelling in the text resolves.
    try:
        for row in db.fetch_all(
            "SELECT id, brand_name, generic_name FROM drugs"
        ) or []:
            _add(row.get("brand_name"), "drug", row.get("id"))
            _add(row.get("generic_name"), "drug", row.get("id"))
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("vocab load failed for drugs: %s", exc)

    try:
        for row in db.fetch_all(
            "SELECT id, name FROM companies WHERE name IS NOT NULL"
        ) or []:
            _add(row.get("name"), "company", row.get("id"))
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("vocab load failed for companies: %s", exc)

    # Verified / high-confidence aliases sharpen brand→generic resolution.
    try:
        rows = db.fetch_all(
            """SELECT entity_type, entity_id, alias_text
                 FROM entity_aliases
                WHERE alias_text IS NOT NULL
                  AND entity_type IN ('drug','company')
                  AND (verified IS TRUE OR confidence >= 0.8)"""
        ) or []
        for row in rows:
            _add(row.get("alias_text"), row.get("entity_type"), row.get("entity_id"))
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("alias vocab load failed: %s", exc)

    vocab = sorted(entries.values(), key=lambda v: len(v.name_lower), reverse=True)
    logger.info("event_entity_resolver vocabulary: %d names", len(vocab))
    return vocab


def resolve_from_text(text: str, vocab: list[VocabEntry]) -> Optional[tuple[str, str, str]]:
    """Return (entity_type, entity_id, matched_name) for the longest whole-word
    name found in ``text``, or None. Case-insensitive; word-boundary anchored
    so 'Lilly' does not match inside 'Lillybrook'."""
    if not text:
        return None
    haystack = text.lower()
    for entry in vocab:            # longest-first
        if entry.name_lower not in haystack:
            continue
        if re.search(rf"\b{re.escape(entry.name_lower)}\b", haystack):
            return (entry.entity_type, entry.entity_id, entry.name)
    return None


def backfill_orphaned_events(
    db,
    *,
    event_types: tuple[str, ...] = HIGH_VALUE_EVENT_TYPES,
    limit: int = 200,
    vocab: Optional[list[VocabEntry]] = None,
) -> dict:
    """Resolve + backfill orphaned high-value events.

    For each event with NULL drug_id AND NULL primary_entity_id, resolve the
    entity from (description, title) and UPDATE primary_entity_* (+ drug_id
    when the match is a drug, so the existing drug_id fallback in event_to_fact
    works). Idempotent: only touches still-orphaned rows.
    """
    if vocab is None:
        vocab = load_vocabulary(db)

    rows = db.fetch_all(
        """SELECT id, event_type, description
             FROM market_events
            WHERE drug_id IS NULL
              AND primary_entity_id IS NULL
              AND event_type = ANY(%s)
            ORDER BY event_date DESC NULLS LAST
            LIMIT %s""",
        [list(event_types), limit],
    ) or []

    scanned = len(rows)
    resolved = 0
    by_type: dict[str, int] = {}
    for row in rows:
        text = str(row.get("description") or "")
        hit = resolve_from_text(text, vocab)
        if not hit:
            continue
        etype, eid, name = hit
        drug_id = eid if etype == "drug" else None
        try:
            db.execute(
                """UPDATE market_events
                      SET primary_entity_id = %s::uuid,
                          primary_entity_type = %s,
                          primary_entity_name = %s,
                          drug_id = COALESCE(drug_id, %s::uuid)
                    WHERE id = %s""",
                [eid, etype, name, drug_id, row.get("id")],
            )
        except Exception as exc:
            logger.warning("backfill update failed for event %s: %s", row.get("id"), exc)
            continue
        resolved += 1
        et = str(row.get("event_type"))
        by_type[et] = by_type.get(et, 0) + 1

    return {"scanned": scanned, "resolved": resolved, "by_type": by_type}
