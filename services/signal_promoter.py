"""Signal Producer — promote market_events into candidate signals.

The `signals` table (migration 037) is the unit-of-output the CI vision
surfaces read (Signals DB, Reviewer, materiality drawer, evidence cards,
agent activity). Migration 037 created the schema but the producer was
never built, so the table is empty in prod while 569 market_events sit
unpromoted. This module is that producer.

Deterministic, no LLM: same event row → same signal fields. See
specs/SPEC_LOOP_signal_producer.md for the source→target mapping.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from services.impact_router import classify_impact_direction

logger = logging.getLogger(__name__)

RULE_VERSION_ID = "signal_promoter_v1"

# Synthetic reviewer for auto-shipped (high-impact) signals. Satisfies the
# signals_review_state_paired / shipped_state_paired constraints. Represents
# "promoted by the Sentinel agent" rather than a human reviewer.
SYSTEM_REVIEWER_ID = "00000000-0000-0000-0000-0000000000a1"

# Event types that warrant a real signal. RECALL_CLASS_I (96% of the corpus)
# is recall noise — deprioritized, never auto-shipped (see significance map).
HIGH_SIGNIFICANCE_EVENT_TYPES = (
    "approval", "trial_readout", "ma_deal", "regulatory_setback",
    "safety_signal", "pricing", "patent_ip", "supply_disruption",
)

# ── KBQ classification ────────────────────────────────────────────
# Tags use the canonical vocabulary the frontend KBQ filter expects
# (KBQFilter.tsx): financial, governance, strategic, clinical, product,
# regulatory, m_and_a, pricing_access, ai_digital, esg_supply.

_EVENT_TYPE_KBQ: dict[str, list[str]] = {
    "approval": ["regulatory"],
    "regulatory_setback": ["regulatory"],
    "trial_readout": ["clinical"],
    "safety_signal": ["clinical"],
    "ma_deal": ["m_and_a", "strategic"],
    "supply_disruption": ["pricing_access", "product"],
    "pricing": ["pricing_access"],
    "patent_ip": ["regulatory", "strategic"],
}

# Keyword → kbq tag for `general`/uncategorized events (all matches kept).
_KBQ_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("regulatory", ("fda", "approval", "approved", "label", "ema", "chmp", "recall", "regulatory")),
    ("clinical", ("trial", "phase", "endpoint", "readout", "efficacy", "study", "data")),
    ("pricing_access", ("price", "pricing", "wac", "formulary", "payer", "access", "coverage", "rebate")),
    ("financial", ("revenue", "guidance", "earnings", "sales", "quarter", "eps", "profit")),
    ("m_and_a", ("acquisition", "acquire", "merger", "deal", "buyout", "licensing")),
]


def classify_kbq(event_type: str, description: str | None) -> list[str]:
    """Return >=1 KBQ tag for an event. event_type first, then keyword scan
    of the description for uncategorized events. Defaults to ['strategic']."""
    direct = _EVENT_TYPE_KBQ.get((event_type or "").lower())
    if direct:
        return list(direct)

    tags: list[str] = []
    text = (description or "").lower()
    for tag, keywords in _KBQ_KEYWORDS:
        if any(k in text for k in keywords):
            tags.append(tag)
    return tags or ["strategic"]


# ── Confidence tier ───────────────────────────────────────────────

_TIER_CONFIDENCE = {
    "tier_1": "confirmed",
    "tier_2": "reported",
    "tier_3": "inferred",
}
_LOW_TRUST_FLOOR = 0.3


def confidence_tier_for(source_tier: str | None, trust_score: float) -> str:
    """ADR-002 mapping: source tier → confidence tier, downgraded to
    'disputed' when trust is below the floor."""
    if trust_score < _LOW_TRUST_FLOOR:
        return "disputed"
    return _TIER_CONFIDENCE.get((source_tier or "").lower(), "inferred")


# ── Impact ────────────────────────────────────────────────────────

# Event-type significance base (0–1) before blending with trust.
_EVENT_TYPE_SIGNIFICANCE: dict[str, float] = {
    "approval": 0.85,
    "safety_signal": 0.85,
    "trial_readout": 0.8,
    "regulatory_setback": 0.8,
    "ma_deal": 0.7,
    "pricing": 0.7,
    "patent_ip": 0.6,
    "supply_disruption": 0.55,
    "general": 0.4,
    "recall_class_i": 0.3,  # recall noise — stays low, never auto-ships
}
_DEFAULT_SIGNIFICANCE = 0.4


def _tier_from_score(score: float) -> str:
    if score >= 0.66:
        return "high"
    if score >= 0.33:
        return "medium"
    return "low"


def impact_for(event_type: str, trust_score: float) -> tuple[float, str]:
    """Blend event-type significance with trust into a 0–1 impact score and
    its tier. Deterministic; weighted 70% significance / 30% trust."""
    base = _EVENT_TYPE_SIGNIFICANCE.get((event_type or "").lower(), _DEFAULT_SIGNIFICANCE)
    ts = max(0.0, min(1.0, trust_score))
    score = round(0.7 * base + 0.3 * ts, 4)
    score = max(0.0, min(1.0, score))
    return score, _tier_from_score(score)


# ── Row builder ───────────────────────────────────────────────────

def _humanize(event_type: str) -> str:
    return (event_type or "market update").replace("_", " ").strip().capitalize()


_LINK_MIN_CONFIDENCE = 0.6


def _resolve_entity(event: dict, linker=None) -> tuple[str, str, str | None]:
    """(type, id, name). Prefers structured fields, then a gazetteer link
    mined from the headline (Loop ①), then an honest 'market' fallback.
    'market' is "unresolved", not a fabricated entity; the headline carries
    the content regardless.
    """
    etype = event.get("primary_entity_type")
    eid = event.get("primary_entity_id")
    if eid:
        return (etype or "drug", str(eid), event.get("primary_entity_name"))
    drug_id = event.get("drug_id")
    if drug_id:
        return ("drug", str(drug_id), event.get("primary_entity_name"))
    # Loop ① — mine the headline/description for a known entity.
    if linker is not None:
        text = " ".join(filter(None, [event.get("description"), event.get("event_type")]))
        hit = linker.link(text)
        if hit is not None and hit.confidence >= _LINK_MIN_CONFIDENCE:
            return (hit.entity_type, hit.entity_id, hit.canonical_name)
    return ("market", "market", event.get("primary_entity_name"))


def build_signal_row(event: dict, linker=None) -> dict | None:
    """Map one market_events row → a signals insert row. Returns None only when
    the event has no id; entityless events are linked via the gazetteer
    (Loop ①) or fall back to a 'market' bucket."""
    if not event.get("id"):
        return None
    entity_type, entity_id, entity_name = _resolve_entity(event, linker)

    event_type = event.get("event_type") or "general"
    description = event.get("description")
    trust_score = event.get("trust_score")
    trust_score = 0.5 if trust_score is None else max(0.0, min(1.0, float(trust_score)))

    headline = (description or _humanize(event_type)).strip()[:120] or _humanize(event_type)
    summary = description.strip()[:500] if description else None
    impact_score, impact_tier = impact_for(event_type, trust_score)

    # High-impact signals auto-ship so they appear on the curated surfaces
    # (Signals DB, Sentinel, Bridge) immediately; medium/low stay candidate
    # for the Reviewer queue. Shipping requires the paired audit fields
    # (signals_review_state_paired + shipped_state_paired constraints).
    now_iso = datetime.now(timezone.utc).isoformat()
    if impact_tier == "high":
        status = "shipped"
        reviewed_by, reviewed_at, shipped_at = SYSTEM_REVIEWER_ID, now_iso, now_iso
    else:
        status = "candidate"
        reviewed_by = reviewed_at = shipped_at = None

    return {
        "event_id": str(event["id"]),
        "kbq_tags": classify_kbq(event_type, description),
        "headline": headline,
        "summary": summary,
        "direction": classify_impact_direction(event_type),
        "confidence_tier": confidence_tier_for(event.get("source_tier"), trust_score),
        "trust_score": trust_score,
        "impact_tier": impact_tier,
        "impact_score": impact_score,
        "rule_version_id": RULE_VERSION_ID,
        "primary_entity_type": entity_type,
        "primary_entity_id": entity_id,
        "primary_entity_name": entity_name,
        "related_entity_ids": [],
        "evidence_document_ids": [str(event["id"])],
        "status": status,
        "reviewed_by": reviewed_by,
        "reviewed_at": reviewed_at,
        "shipped_at": shipped_at,
    }


# ── Orchestrator ──────────────────────────────────────────────────

@dataclass
class PromoteResult:
    scanned: int = 0
    promoted: int = 0
    skipped_existing: int = 0
    skipped_no_entity: int = 0


_INSERT_SQL = """
    INSERT INTO signals (
        event_id, kbq_tags, headline, summary, direction,
        confidence_tier, trust_score, impact_tier, impact_score,
        rule_version_id, primary_entity_type, primary_entity_id,
        primary_entity_name, related_entity_ids, evidence_document_ids,
        status, reviewed_by, reviewed_at, shipped_at
    ) VALUES (
        %(event_id)s, %(kbq_tags)s, %(headline)s, %(summary)s, %(direction)s,
        %(confidence_tier)s, %(trust_score)s, %(impact_tier)s, %(impact_score)s,
        %(rule_version_id)s, %(primary_entity_type)s, %(primary_entity_id)s,
        %(primary_entity_name)s, %(related_entity_ids)s::text[],
        %(evidence_document_ids)s::uuid[], %(status)s,
        %(reviewed_by)s, %(reviewed_at)s, %(shipped_at)s
    )
    ON CONFLICT DO NOTHING
"""


def promote_events(
    db,
    *,
    limit: int = 1000,
    since_days: int | None = None,
    event_types: list[str] | None = None,
) -> PromoteResult:
    """Promote market_events not yet present in signals into signals.

    Idempotent: events whose id already appears as signals.event_id are
    skipped and counted. Dedup is done in Python so the counts are accurate.
    `event_types` restricts to specific types (e.g. high-significance ones),
    avoiding the RECALL_CLASS_I noise that dominates the corpus.
    """
    res = PromoteResult()

    # Existing signalled event_ids (idempotency set).
    try:
        existing_rows = db.fetch_all("SELECT event_id FROM signals", [])
    except Exception:
        logger.exception("signal promoter: existing-signals query failed")
        existing_rows = []
    existing = {str(r["event_id"]) for r in existing_rows if r.get("event_id") is not None}

    where = ["TRUE"]
    params: list = []
    if since_days is not None:
        where.append("me.event_date >= (CURRENT_DATE - %s::int)")
        params.append(since_days)
    if event_types:
        where.append("me.event_type = ANY(%s)")
        params.append(list(event_types))
    where_sql = " AND ".join(where)

    sql = f"""
        SELECT me.id, me.event_type, me.description, me.source_tier,
               me.trust_score, me.primary_entity_type, me.primary_entity_id,
               me.primary_entity_name, me.drug_id, me.event_date
          FROM market_events me
         WHERE {where_sql}
         ORDER BY me.event_date DESC
         LIMIT %s
    """
    params.append(limit)

    try:
        events = db.fetch_all(sql, params)
    except Exception:
        logger.exception("signal promoter: market_events query failed")
        events = []

    # Loop ① — build the gazetteer once for this batch.
    linker = None
    try:
        from services.entity_linker import EntityLinker
        linker = EntityLinker(db).load()
    except Exception:
        logger.exception("signal promoter: entity linker unavailable; using market fallback")

    res.scanned = len(events)
    for event in events:
        if str(event["id"]) in existing:
            res.skipped_existing += 1
            continue
        row = build_signal_row(event, linker)
        if row is None:
            res.skipped_no_entity += 1
            continue
        try:
            db.execute(_INSERT_SQL, row)
            res.promoted += 1
        except Exception:
            logger.exception("signal promoter: insert failed for event %s", event.get("id"))

    logger.info(
        "signal promoter: scanned=%d promoted=%d skipped_existing=%d skipped_no_entity=%d",
        res.scanned, res.promoted, res.skipped_existing, res.skipped_no_entity,
    )
    return res


def relink_market_signals(db, *, limit: int = 5000) -> dict:
    """Backfill: re-resolve existing signals stuck in the 'market' bucket by
    mining their headline. Idempotent; only updates rows that newly resolve.
    """
    from services.entity_linker import EntityLinker

    linker = EntityLinker(db).load()
    try:
        rows = db.fetch_all(
            """SELECT id, headline, summary FROM signals
                WHERE primary_entity_id = 'market'
                LIMIT %s""",
            [limit],
        )
    except Exception:
        logger.exception("relink: market-signals query failed")
        rows = []

    scanned = relinked = 0
    for r in rows:
        scanned += 1
        text = " ".join(filter(None, [r.get("headline"), r.get("summary")]))
        hit = linker.link(text)
        if hit is None or hit.confidence < _LINK_MIN_CONFIDENCE:
            continue
        try:
            db.execute(
                """UPDATE signals
                      SET primary_entity_type = %s,
                          primary_entity_id   = %s,
                          primary_entity_name = %s
                    WHERE id = %s""",
                [hit.entity_type, hit.entity_id, hit.canonical_name, r["id"]],
            )
            relinked += 1
        except Exception:
            logger.exception("relink: update failed for signal %s", r.get("id"))

    logger.info("relink: scanned=%d relinked=%d", scanned, relinked)
    return {"scanned": scanned, "relinked": relinked}
