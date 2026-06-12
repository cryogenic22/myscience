"""PB-SL07 — mint signals from high-impact facts (unify the two sensing stores).

Until now `signals` derived only from `market_events`. This lifts the *other*
direction: when the fact ledger gains a genuinely news-worthy, evidence-backed
fact (a trial readout from an uploaded deck, a boxed-warning safety signal), we
mint a signal that ``produces`` it and link the two via ``signal_facts``
(migration 078). The signal layer becomes a curated lens over the unified
knowledge store — the structural payoff of
``docs/sensing-layer-knowledge-abstraction-spec.html``.

Selective by design — NOT every fact becomes a signal:
  * predicate must be in ``SIGNAL_WORTHY`` (events, not reference rows like
    mechanism_of_action or the 1,000s of clinical_trial / key_publication facts),
  * the fact must carry evidence (``source_doc_id``) so the minted signal
    satisfies ``evidence_document_ids >= 1`` and is provenance-traceable,
  * idempotent: facts already linked in ``signal_facts`` are skipped.

Pure ``build_signal_row`` (DB-free, unit-testable); only ``fetch_facts`` and the
inserts touch the DB.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from services.dossier_kb import route_predicate_to_domain

logger = logging.getLogger(__name__)

RULE_VERSION = "fact_signal_v1"

# Only these predicates are "events" worth surfacing as signals. Reference rows
# (mechanism_of_action) and high-volume corroboration (clinical_trial,
# key_publication) stay facts; they enrich the dossier, not the stream.
SIGNAL_WORTHY: tuple[str, ...] = (
    "trial_result",        # DR-9 deck/PR readouts
    "safety_signal",       # DR-4 boxed warnings
    "regulatory_approval",
    "regulatory_setback",
    "fda_approval_date",
    "competitor_launch",
    "ma_deal",
)

# fact_class → signals.confidence_tier (CHECK: confirmed/reported/inferred/disputed)
_CLASS_TO_TIER = {
    "reference": "confirmed",
    "corporate": "reported",
    "signal": "reported",
    "inferred": "inferred",
    "internal": "reported",
}

# predicate → (impact_tier, impact_score). Safety + regulatory setbacks are the
# highest-impact; readouts high; the rest medium.
_IMPACT = {
    "safety_signal": ("high", 0.85),
    "regulatory_setback": ("high", 0.85),
    "trial_result": ("high", 0.75),
    "regulatory_approval": ("high", 0.75),
    "fda_approval_date": ("medium", 0.6),
    "competitor_launch": ("high", 0.7),
    "ma_deal": ("high", 0.7),
}

# predicate → signal polarity (signals.direction CHECK: positive|negative|
# neutral|mixed). Polarity is relative to the signal's SUBJECT: a setback is
# negative for the drug it hits; an approval is positive for the drug approved.
# This is what lets calibration treat a rival's setback as evidence AGAINST a
# competitive-pressure scenario (Loop 1 / OQ3). TA-general — keyed off predicate.
_DIRECTION_BY_PREDICATE: dict[str, str] = {
    "safety_signal": "negative",
    "regulatory_setback": "negative",
    "regulatory_approval": "positive",
    "fda_approval_date": "positive",
    "competitor_launch": "positive",
    "ma_deal": "positive",
    # trial_result is resolved from its outcome text below (a readout can be a
    # hit or a miss); default neutral when the language isn't directional.
}
_NEG_OUTCOME_RE = re.compile(
    r"\b(did not meet|didn'?t meet|failed|fail to|missed|did not achieve|"
    r"not superior|non[- ]?inferior(?:ity)? (?:not met|miss)|discontinu|"
    r"terminat|halt|negative|setback|reject)\w*", re.IGNORECASE,
)
_POS_OUTCOME_RE = re.compile(
    r"\b(met (?:its )?primary|achieved|superior|positive|significant(?:ly)?|"
    r"success|win|hit (?:its )?primary|demonstrat\w* (?:efficacy|benefit))",
    re.IGNORECASE,
)


def signal_direction(predicate: Optional[str], object_value: Optional[dict]) -> str:
    """Pure: polarity of a signal toward its subject — 'positive'|'negative'|
    'neutral'. Directional predicates map straight through; an ambiguous
    'trial_result' is read from its outcome text (never guessed — defaults to
    'neutral' when the language isn't directional)."""
    pred = (predicate or "").strip()
    fixed = _DIRECTION_BY_PREDICATE.get(pred)
    if fixed:
        return fixed
    if pred == "trial_result":
        obj = object_value or {}
        text = " ".join(str(obj.get(k) or "") for k in ("description", "title", "indication"))
        neg, pos = bool(_NEG_OUTCOME_RE.search(text)), bool(_POS_OUTCOME_RE.search(text))
        if neg and not pos:
            return "negative"
        if pos and not neg:
            return "positive"
    return "neutral"


# dossier domain → KBQ tag (so fact-signals are filterable in the Signals DB)
_DOMAIN_TO_KBQ = {
    "clinical_profile": "clinical",
    "pricing_and_access": "pricing_access",
    "competitive": "strategic",
    "pipeline_and_macro": "regulatory",
    "commercial_operational": "financial",
    "disease_and_patient": "clinical",
    "hcp_and_patient": "strategic",
}


@dataclass
class MintStats:
    scanned: int = 0
    minted: int = 0
    skipped_linked: int = 0
    skipped_no_evidence: int = 0


def _clip(s: Optional[str], n: int) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def build_signal_row(fact: dict) -> Optional[dict]:
    """Pure: map a fact row → a signals INSERT dict, or None if not mintable.

    ``fact`` keys: id, predicate, subject_entity_type, subject_entity_id,
    object_value (dict), fact_class, confidence, source_doc_id, entity_name.
    """
    predicate = fact.get("predicate")
    if predicate not in SIGNAL_WORTHY:
        return None
    source_doc_id = fact.get("source_doc_id")
    if not source_doc_id:
        return None  # no evidence → can't satisfy evidence_document_ids >= 1
    obj = fact.get("object_value") or {}
    if isinstance(obj, str):
        try:
            obj = json.loads(obj)
        except (ValueError, TypeError):
            obj = {}
    headline = _clip(obj.get("description") or predicate.replace("_", " ").title(), 120)
    impact_tier, impact_score = _IMPACT.get(predicate, ("medium", 0.5))
    domain = route_predicate_to_domain(predicate)
    kbq = _DOMAIN_TO_KBQ.get(domain, "strategic")
    fact_class = fact.get("fact_class") or "signal"
    try:
        trust = float(fact.get("confidence") or 0.6)
    except (TypeError, ValueError):
        trust = 0.6
    return {
        "headline": headline,
        "summary": _clip(obj.get("title") or obj.get("indication"), 480) or None,
        "confidence_tier": _CLASS_TO_TIER.get(fact_class, "reported"),
        "trust_score": max(0.0, min(1.0, trust)),
        "impact_tier": impact_tier,
        "impact_score": impact_score,
        "rule_version_id": RULE_VERSION,
        "kbq_tags": [kbq],
        "primary_entity_type": fact.get("subject_entity_type") or "drug",
        "primary_entity_id": str(fact.get("subject_entity_id") or ""),
        "primary_entity_name": fact.get("entity_name"),
        "evidence_document_ids": [str(source_doc_id)],
        # Signal polarity — a general enrichment (consumed by calibration's
        # contradiction handling, and available to chat / feed / future launch
        # use-cases), not a CI-specific field.
        "direction": signal_direction(predicate, obj),
        # Auto-minted → 'candidate' (awaits review; the system proposes, a human
        # ships). 'reviewed'/'shipped' require a reviewer per the
        # signals_review_state_paired constraint. The reviewer surface lists
        # candidates; PB-SL08 adds a status filter to the main Signals DB.
        "status": "candidate",
    }


_FETCH_SQL = """
    SELECT f.id, f.predicate, f.subject_entity_type, f.subject_entity_id,
           f.object_value, f.fact_class, f.confidence, f.source_doc_id,
           d.generic_name AS entity_name
      FROM facts f
      LEFT JOIN drugs d ON d.id::text = f.subject_entity_id
     WHERE f.predicate = ANY(%s)
       AND f.superseded_by IS NULL
       AND f.source_doc_id IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM signal_facts sf WHERE sf.fact_id = f.id)
     ORDER BY f.valid_from DESC NULLS LAST
     {limit_clause}
"""

_INSERT_SIGNAL_SQL = """
    INSERT INTO signals (
        headline, summary, confidence_tier, trust_score, impact_tier,
        impact_score, rule_version_id, kbq_tags, primary_entity_type,
        primary_entity_id, primary_entity_name, evidence_document_ids, status,
        direction
    ) VALUES (
        %(headline)s, %(summary)s, %(confidence_tier)s, %(trust_score)s,
        %(impact_tier)s, %(impact_score)s, %(rule_version_id)s, %(kbq_tags)s,
        %(primary_entity_type)s, %(primary_entity_id)s, %(primary_entity_name)s,
        %(evidence_document_ids)s::uuid[], %(status)s, %(direction)s
    ) RETURNING id
"""


def fetch_facts(db, *, predicates: tuple[str, ...] = SIGNAL_WORTHY,
                limit: Optional[int] = None) -> list[dict]:
    limit_clause = "LIMIT %s" if limit is not None else ""
    sql = _FETCH_SQL.format(limit_clause=limit_clause)
    params: list = [list(predicates)]
    if limit is not None:
        params.append(int(limit))
    try:
        return db.fetch_all(sql, params)
    except Exception:
        logger.exception("fact-signal fetch failed")
        return []


def mint_signals_from_facts(db, *, predicates: tuple[str, ...] = SIGNAL_WORTHY,
                            limit: Optional[int] = None) -> MintStats:
    """Mint a signal per signal-worthy, evidence-backed, not-yet-linked fact and
    link it via signal_facts(role='produces'). Idempotent."""
    stats = MintStats()
    for fact in fetch_facts(db, predicates=predicates, limit=limit):
        stats.scanned += 1
        if not fact.get("source_doc_id"):
            stats.skipped_no_evidence += 1
            continue
        row = build_signal_row(fact)
        if row is None:
            stats.skipped_no_evidence += 1
            continue
        try:
            sid_row = db.fetch_one(_INSERT_SIGNAL_SQL, row)
            signal_id = sid_row["id"] if sid_row else None
            if not signal_id:
                continue
            db.execute(
                "INSERT INTO signal_facts (signal_id, fact_id, role) "
                "VALUES (%s, %s, 'produces') ON CONFLICT DO NOTHING",
                [str(signal_id), str(fact["id"])],
            )
            stats.minted += 1
        except Exception:
            logger.exception("mint failed for fact %s", fact.get("id"))
    logger.info(
        "fact-signals: scanned=%d minted=%d skipped_linked=%d no_evidence=%d",
        stats.scanned, stats.minted, stats.skipped_linked,
        stats.skipped_no_evidence,
    )
    return stats
