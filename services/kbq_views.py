"""Loop ② — per-entity KBQ living views.

The deliverable both specs describe (CI_Agent_Reimagined_Spec, comp_intel_2)
is the 8 Key Business Questions answered per competitor, with parity. v1
builds each KBQ view from the entity's KBQ-tagged signals (Loop ① linked
them to entities). Structured enrichment from the entity graph/facts layer
comes later (critical-path ⓪).

Parity: every entity returns the same 8 slots; empty slots are marked
'insufficient' rather than dropped, so two competitors compare apples-to-
apples. Every item carries its signal + evidence ids (the trust spine).

KBQ → signal-tag mapping below is v1 and needs Riya sign-off (strategy-doc
input #2). Tags use the canonical frontend vocabulary (financial,
governance, strategic, clinical, product, regulatory, m_and_a,
pricing_access, ai_digital, esg_supply).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_MAX_ITEMS_PER_KBQ = 10

# The 8 KBQs, each mapped to the signal tags that feed it. SWOT (6) is a
# synthesis over the others rather than a tag, so it has no direct tags in v1.
KBQ_CATALOG: list[dict] = [
    {"kbq": 1, "title": "Indications", "tags": ["regulatory", "clinical"]},
    {"kbq": 2, "title": "Competitors", "tags": ["m_and_a", "strategic"]},
    {"kbq": 3, "title": "Clinical", "tags": ["clinical"]},
    {"kbq": 4, "title": "Positioning", "tags": ["strategic", "product"]},
    {"kbq": 5, "title": "Sales & Sentiment", "tags": ["financial", "governance"]},
    {"kbq": 6, "title": "SWOT", "tags": []},  # synthesis over 1–5
    {"kbq": 7, "title": "Pricing", "tags": ["pricing_access"]},
    {"kbq": 8, "title": "Access", "tags": ["pricing_access", "esg_supply"]},
]

_BY_ID = {k["kbq"]: k for k in KBQ_CATALOG}


def kbq_tags_for(kbq: int) -> list[str]:
    return list(_BY_ID.get(kbq, {}).get("tags", []))


def _item_from_signal(sig: dict) -> dict:
    return {
        "claim": sig.get("headline") or "",
        "signal_id": str(sig.get("id")),
        "evidence_ids": [str(e) for e in (sig.get("evidence_document_ids") or [])],
        "impact_tier": sig.get("impact_tier"),
        "confidence_tier": sig.get("confidence_tier"),
        "date": sig.get("created_at"),
    }


def _fetch_entity_signals(db, entity_type: str, entity_id: str) -> list[dict]:
    sql = """
        SELECT id, kbq_tags, headline, impact_tier, impact_score,
               confidence_tier, evidence_document_ids, created_at, status,
               primary_entity_name
          FROM signals
         WHERE primary_entity_type = %s
           AND primary_entity_id = %s
           AND status IN ('shipped', 'reviewed', 'candidate')
         ORDER BY impact_score DESC NULLS LAST, created_at DESC
    """
    try:
        return db.fetch_all(sql, [entity_type, entity_id])
    except Exception:
        logger.exception("kbq_views: signal query failed for %s:%s", entity_type, entity_id)
        return []


def build_entity_kbqs(db, entity_type: str, entity_id: str) -> dict:
    """Return the 8 KBQ views for one entity, with parity + completeness.

    Each KBQ collects the entity's signals whose kbq_tags overlap the KBQ's
    mapped tags. KBQ-6 (SWOT) is synthesized: in v1 it surfaces the highest-
    impact items across the other KBQs as a starting point.
    """
    signals = _fetch_entity_signals(db, entity_type, entity_id)

    views: list[dict] = []
    for spec in KBQ_CATALOG:
        kbq = spec["kbq"]
        tags = set(spec["tags"])
        if tags:
            matched = [s for s in signals if tags & set(s.get("kbq_tags") or [])]
        elif kbq == 6:
            # SWOT synthesis v1 — top signals overall (signals already sorted
            # by impact desc). A real synthesis lands once decisions exist.
            matched = signals
        else:
            matched = []

        items = [_item_from_signal(s) for s in matched[:_MAX_ITEMS_PER_KBQ]]
        views.append({
            "kbq": kbq,
            "title": spec["title"],
            "status": "fresh" if items else "insufficient",
            "items": items,
        })

    filled = sum(1 for v in views if v["items"])
    name = next((s.get("primary_entity_name") for s in signals if s.get("primary_entity_name")), None)
    return {
        "entity": {"type": entity_type, "id": entity_id, "name": name},
        "kbqs": views,
        "completeness": round(filled / len(KBQ_CATALOG), 4),
    }
