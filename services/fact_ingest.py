"""A1 — assert facts from ingested market_events (spine convergence, Phase A).

Makes the temporal facts ledger load-bearing: every Knowledge-plane
market_event maps to a fact in the ledger, both as a one-time backfill over
existing events and going forward (wired into EventCollector._persist_event).

This is the Data Automaton's "publish" step — structured truth out. It does
NOT decide importance (that's the signal/Helix layer); it only emits
well-formed, provenance-bearing facts.

See specs/SPEC_A1_fact_assertion_on_ingest.md and services/facts_ledger.py.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from services.facts_ledger import assert_fact, DEFAULT_FACT_CLASS, FACT_CLASSES

logger = logging.getLogger(__name__)

CREATED_BY = "data_automaton"

# Z1 — predicate → fact_class taxonomy. Reference class (peer-reviewed
# scientific truth) does not arise from market_events; it comes from the
# scientific-literature pipeline. Inferred class is produced by the
# Intelligence Agent's synthesis, not by ingestion. Ingest emits only
# corporate (the default) and signal.
_PREDICATE_TO_CLASS: dict[str, str] = {
    "regulatory_approval":  "corporate",
    "regulatory_setback":   "corporate",
    "trial_result":         "corporate",
    "ma_deal":              "corporate",
    "patent_event":         "corporate",
    "safety_signal":        "signal",
    "pricing_intent":       "signal",
    "supply_disruption":    "signal",
    "market_event":         "corporate",  # fallback predicate from event_to_fact
}


def classify_predicate(predicate: Optional[str]) -> str:
    """Map a fact predicate to its fact_class. Unknown predicates default
    to corporate (the safe mid-ceiling class). Z1 / SPEC_Z1."""
    if not predicate:
        return DEFAULT_FACT_CLASS
    cls = _PREDICATE_TO_CLASS.get(predicate.lower(), DEFAULT_FACT_CLASS)
    return cls if cls in FACT_CLASSES else DEFAULT_FACT_CLASS

# market_event.event_type → fact predicate (the canonical claim name).
_EVENT_PREDICATE: dict[str, str] = {
    "approval": "regulatory_approval",
    "regulatory_setback": "regulatory_setback",
    "trial_readout": "trial_result",
    "safety_signal": "safety_signal",
    "ma_deal": "ma_deal",
    "pricing": "pricing_intent",
    "patent_ip": "patent_event",
    "supply_disruption": "supply_disruption",
}
_FALLBACK_PREDICATE = "market_event"


@dataclass
class FactDraft:
    """A pure, DB-free description of the fact an event maps to."""
    kind: str
    predicate: str
    subject_entity_type: str
    subject_entity_id: str
    object_value: dict
    valid_from: Optional[datetime]
    confidence: float
    fact_class: str = DEFAULT_FACT_CLASS


@dataclass
class BackfillStats:
    scanned: int = 0
    asserted: int = 0
    skipped_existing: int = 0
    skipped_no_subject: int = 0


def _coerce_dt(v: Any) -> Optional[datetime]:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _clamp_confidence(v: Any) -> float:
    try:
        c = float(v)
    except (TypeError, ValueError):
        return 0.5
    return min(1.0, max(0.0, c))


def event_to_fact(event: dict) -> Optional[FactDraft]:
    """Map a market_event row to a FactDraft, or None if it has no subject.

    A fact must be about something: entity_type and entity_id are both
    required. Future-dated events become anticipatory facts (invisible until
    their effective date) — the temporal capability the war-game depends on.
    """
    subj_type = event.get("entity_type")
    subj_id = event.get("entity_id")
    if not subj_type or not subj_id:
        return None

    etype = (event.get("event_type") or "").lower()
    predicate = _EVENT_PREDICATE.get(etype, _FALLBACK_PREDICATE)

    event_date = _coerce_dt(event.get("event_date")) or _coerce_dt(event.get("created_at"))
    is_future = event_date is not None and event_date > datetime.now(timezone.utc)
    kind = "anticipatory" if is_future else "point"
    # anticipatory facts require valid_from; is_future guarantees event_date set.
    valid_from = event_date

    object_value = {
        "event_type": etype,
        "description": event.get("description"),
        "source_url": event.get("source_url"),
        "source_feed": event.get("source_feed"),
        "event_id": str(event["id"]) if event.get("id") is not None else None,
    }
    return FactDraft(
        kind=kind,
        predicate=predicate,
        subject_entity_type=str(subj_type),
        subject_entity_id=str(subj_id),
        object_value=object_value,
        valid_from=valid_from,
        confidence=_clamp_confidence(event.get("trust_score")),
        fact_class=classify_predicate(predicate),
    )


_EXISTS_SQL = """
    SELECT id FROM facts
     WHERE subject_entity_type = %s
       AND subject_entity_id = %s
       AND predicate = %s
       AND object_value->>'event_id' = %s
       AND superseded_by IS NULL
     LIMIT 1
"""


def _fact_exists(db, draft: FactDraft, event_id: str) -> bool:
    try:
        rows = db.fetch_all(
            _EXISTS_SQL,
            [draft.subject_entity_type, draft.subject_entity_id, draft.predicate, str(event_id)],
        )
        return bool(rows)
    except Exception:
        logger.exception("fact existence check failed for event %s", event_id)
        return False


def _assert_with_status(db, event: dict) -> tuple[str, Optional[str]]:
    """Returns (status, fact_id). status ∈ {asserted, skipped_existing, skipped_no_subject}."""
    draft = event_to_fact(event)
    if draft is None:
        return ("skipped_no_subject", None)

    event_id = draft.object_value.get("event_id")
    if event_id and _fact_exists(db, draft, event_id):
        return ("skipped_existing", None)

    fid = assert_fact(
        db,
        kind=draft.kind,
        predicate=draft.predicate,
        subject_entity_type=draft.subject_entity_type,
        subject_entity_id=draft.subject_entity_id,
        object_value=draft.object_value,
        valid_from=draft.valid_from,
        confidence=draft.confidence,
        created_by=CREATED_BY,
        fact_class=draft.fact_class,
    )
    return ("asserted", fid)


def assert_event_fact(db, event: dict) -> Optional[str]:
    """Idempotently assert the fact for one event. Returns the fact id, or
    None if skipped (already present, or no resolvable subject)."""
    return _assert_with_status(db, event)[1]


_FETCH_SQL = """
    SELECT id, event_type, description, source_feed, source_url, trust_score,
           entity_id, entity_type, event_date, created_at
      FROM market_events
     {where}
     ORDER BY created_at DESC
     {limit}
"""


def _fetch_events(db, limit, since_days, event_types) -> list[dict]:
    clauses: list[str] = []
    params: list[Any] = []
    if since_days is not None:
        clauses.append("created_at >= NOW() - (%s || ' days')::interval")
        params.append(str(int(since_days)))
    if event_types:
        clauses.append("event_type = ANY(%s)")
        params.append(list(event_types))
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    limit_sql = ""
    if limit is not None:
        limit_sql = "LIMIT %s"
        params.append(int(limit))
    sql = _FETCH_SQL.format(where=where, limit=limit_sql)
    try:
        return db.fetch_all(sql, params)
    except Exception:
        logger.exception("failed to fetch market_events for backfill")
        return []


def backfill_facts_from_events(
    db,
    *,
    limit: Optional[int] = None,
    since_days: Optional[int] = None,
    event_types: Optional[list[str]] = None,
) -> BackfillStats:
    """Assert facts for existing market_events. Idempotent — safe to re-run."""
    stats = BackfillStats()
    for event in _fetch_events(db, limit, since_days, event_types):
        stats.scanned += 1
        status, _ = _assert_with_status(db, event)
        if status == "asserted":
            stats.asserted += 1
        elif status == "skipped_existing":
            stats.skipped_existing += 1
        elif status == "skipped_no_subject":
            stats.skipped_no_subject += 1
    logger.info(
        "fact backfill: scanned=%d asserted=%d skipped_existing=%d skipped_no_subject=%d",
        stats.scanned, stats.asserted, stats.skipped_existing, stats.skipped_no_subject,
    )
    return stats
