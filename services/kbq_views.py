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
from collections import OrderedDict, defaultdict

logger = logging.getLogger(__name__)

_MAX_ITEMS_PER_KBQ = 10
_MAX_FACTS_FETCH = 400  # bound the ledger pull before per-KBQ capping

# PB-SL11 — route the FACT LEDGER into the KBQ surface so it is a true lens over
# the knowledge store, not just the (thin) curated signals table. Each known
# predicate maps to the KBQ it answers; unmapped predicates (e.g. the noisy
# market_event bulk — recalls/shortages) are deliberately skipped so they don't
# flood a KBQ. Facts complement signals: signals are the scored/curated subset,
# facts are the underlying evidence the dossier is built from.
_PREDICATE_KBQ: dict[str, int] = {
    "label_indication": 1,      # Indications
    "disease_evidence": 1,      # epidemiology / disease context
    "competitor": 2,            # Competitors (L6 — entity-graph rivals)
    "clinical_trial": 3,        # Clinical
    "trial_result": 3,
    "adverse_event": 3,         # safety
    "safety_signal": 3,
    "key_publication": 3,
    "mechanism_of_action": 3,
    "wac_usd": 7,               # Pricing
    "drug_pricing": 7,          # future-proof (no rows yet)
}

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
        "source": "signal",
        "signal_id": str(sig.get("id")),
        "fact_id": None,
        "fact_class": None,  # frontend derives the glyph from confidence_tier
        "evidence_ids": [str(e) for e in (sig.get("evidence_document_ids") or [])],
        "impact_tier": sig.get("impact_tier"),
        "confidence_tier": sig.get("confidence_tier"),
        "date": sig.get("created_at"),
        "source_label": None,
        "source_url": None,
    }


def _item_from_fact(f: dict) -> dict:
    """A KBQ item drawn from the fact ledger (PB-SL11). Carries its fact_class
    (for the glyph) + source link (provenance) rather than a signal id."""
    date = f.get("valid_from")
    return {
        "claim": (f.get("claim") or f.get("predicate") or "").strip(),
        "source": "fact",
        "signal_id": None,
        "fact_id": str(f.get("id")),
        "fact_class": f.get("fact_class"),
        "evidence_ids": [],
        "impact_tier": None,
        "confidence_tier": None,  # facts carry numeric confidence, not a tier
        "date": date.isoformat() if hasattr(date, "isoformat") else (str(date) if date else None),
        "source_label": f.get("source_id"),
        "source_url": f.get("source_url"),
    }


def _diversify_by_predicate(facts: list[dict]) -> list[dict]:
    """Round-robin facts by predicate so a KBQ shows a MIX (a trial, an adverse
    event, a label, a publication) rather than 10 near-identical trial rows.
    Preserves the within-predicate order (confidence DESC) the query produced."""
    groups: "OrderedDict[str, list]" = OrderedDict()
    for f in facts:
        groups.setdefault(f.get("predicate") or "", []).append(f)
    out: list[dict] = []
    while any(groups.values()):
        for q in list(groups.keys()):
            bucket = groups[q]
            if bucket:
                out.append(bucket.pop(0))
    return out


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


def _fetch_entity_facts(db, entity_type: str, entity_id: str) -> list[dict]:
    """Pull the entity's ledger facts for the KBQ-mapped predicates (PB-SL11).
    Joins evidence_records for the source link (provenance)."""
    sql = """
        SELECT f.id::text AS id, f.predicate, f.fact_class,
               f.object_value->>'description' AS claim,
               f.confidence, f.valid_from,
               e.source_id, e.source_url
          FROM facts f
          LEFT JOIN evidence_records e ON e.evidence_id = f.source_doc_id
         WHERE f.subject_entity_type = %s
           AND f.subject_entity_id = %s
           AND f.superseded_by IS NULL
           AND f.predicate = ANY(%s)
         ORDER BY f.confidence DESC NULLS LAST, f.valid_from DESC
         LIMIT %s
    """
    try:
        return db.fetch_all(
            sql, [entity_type, entity_id, list(_PREDICATE_KBQ.keys()), _MAX_FACTS_FETCH],
        )
    except Exception:
        logger.exception("kbq_views: fact query failed for %s:%s", entity_type, entity_id)
        return []


def build_entity_kbqs(db, entity_type: str, entity_id: str) -> dict:
    """Return the 8 KBQ views for one entity, with parity + completeness.

    Each KBQ collects (a) the entity's signals whose kbq_tags overlap the KBQ's
    mapped tags — the curated, scored layer — and (b) the entity's ledger facts
    whose predicate maps to the KBQ (PB-SL11) — the underlying knowledge store.
    Signals lead (curated first), facts fill, deduped by claim. KBQ-6 (SWOT) is
    synthesized from the top signals as a starting point.
    """
    signals = _fetch_entity_signals(db, entity_type, entity_id)
    facts = _fetch_entity_facts(db, entity_type, entity_id)

    facts_by_kbq: dict[int, list[dict]] = defaultdict(list)
    for f in facts:
        kbq = _PREDICATE_KBQ.get(f.get("predicate") or "")
        if kbq:
            facts_by_kbq[kbq].append(f)

    views: list[dict] = []
    for spec in KBQ_CATALOG:
        kbq = spec["kbq"]
        tags = set(spec["tags"])
        if tags:
            matched = [s for s in signals if tags & set(s.get("kbq_tags") or [])]
        elif kbq == 6:
            # SWOT synthesis v1 — top signals overall (already impact-sorted).
            matched = signals
        else:
            matched = []

        sig_items = [_item_from_signal(s) for s in matched]
        # Dedup facts already surfaced as signals (a fact minted into a signal via
        # SL07 would otherwise appear twice) — match on normalized claim text.
        seen_claims = {(it["claim"] or "").strip().lower() for it in sig_items}
        fact_items = [
            _item_from_fact(f)
            for f in _diversify_by_predicate(facts_by_kbq.get(kbq, []))
            if ((f.get("claim") or "").strip().lower() not in seen_claims)
        ]

        # Signals first (curated/scored), then facts to fill, capped.
        items = (sig_items + fact_items)[:_MAX_ITEMS_PER_KBQ]
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


def build_entity_kbqs_for_asset(db, asset: str) -> dict:
    """PB-SL10 — KBQ-as-query-surface.

    The query surface lets a user type an asset ('semaglutide', 'drug:wegovy')
    and get the 8 KBQs answered. Signals are keyed by the canonical entity id
    (a UUID), not the slug, so resolve the asset first — reusing the same
    richness-ranked resolver the dossier uses — then build the parity view.
    The raw `asset` string is echoed back so the UI can label the surface.
    """
    entity_type, entity_id = resolve_asset_to_subject(db, asset)
    out = build_entity_kbqs(db, entity_type, entity_id)

    # parse_asset_ref defaults a bare name to a DRUG. But the KBQ surface is
    # competitor intelligence, which is company-centric ("Novo Nordisk"), so if a
    # bare name found no drug evidence, try it as a company before giving up.
    if ":" not in asset and out["completeness"] == 0.0:
        c_type, c_id = resolve_asset_to_subject(db, f"company:{asset}")
        if c_id and c_id != asset:  # resolved to a real company row
            c_out = build_entity_kbqs(db, c_type, c_id)
            if c_out["completeness"] > 0.0 or _entity_display_name(db, c_type, c_id):
                out, entity_type, entity_id = c_out, c_type, c_id

    out["asset"] = asset
    # Fall back to the typed asset as a label when no signal carried a name.
    if not out["entity"].get("name"):
        out["entity"]["name"] = _entity_display_name(db, entity_type, entity_id) or asset
    return out


# Resolve the asset slug → (type, id) and a display name. Imported lazily-ish
# at module load; dossier_kb owns the canonical, richness-ranked resolver.
from services.dossier_kb import resolve_asset_to_subject  # noqa: E402


_NAME_TABLE = {
    "drug": ("drugs", "COALESCE(brand_name, generic_name)"),
    "company": ("companies", "name"),
    # clinical_trials has official_title (NOT title) — 006_schema_expansion.
    "trial": ("clinical_trials", "COALESCE(official_title, 'Trial ' || id::text)"),
}


def _entity_display_name(db, entity_type: str, entity_id: str) -> str | None:
    """Best-effort human label for an entity that has no signals yet."""
    info = _NAME_TABLE.get(entity_type)
    if not info:
        return None
    table, name_expr = info
    try:
        row = db.fetch_one(
            f"SELECT {name_expr} AS name FROM {table} WHERE id::text = %s LIMIT 1",
            [entity_id],
        )
        return row.get("name") if row else None
    except Exception:
        logger.debug("kbq_views: name lookup failed for %s:%s", entity_type, entity_id, exc_info=True)
        return None
