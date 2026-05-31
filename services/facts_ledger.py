"""PB-1307 — temporal, append-only facts ledger.

The semantic moat: typed, time-stamped, evidence-linked facts. The headline
capability is the ANTICIPATORY fact — a future-dated fact (valid_from in the
future) that is invisible today but visible when queried AS-OF its effective
date. That is what lets the war-game ask "what is the world like as of
2027-01-01?" and get Novo's announced $675 WAC.

Append-only: facts are never deleted (DB trigger enforces). Corrections
supersede — the prior fact stays for audit/replay.

See schema/migrations/065_facts_ledger.sql and docs/ci-critical-analysis.html §9.1.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

VALID_KINDS = ("point", "interval", "anticipatory")

# Z1 — the four-class taxonomy from the v7 design canon. Each class carries a
# differential agentic ceiling enforced at the publish boundary (Phase C).
FACT_CLASSES = ("reference", "corporate", "signal", "inferred")
DEFAULT_FACT_CLASS = "corporate"


class InvalidFact(ValueError):
    """Raised when a fact violates the ledger's invariants."""


def _coerce_dt(v: Any) -> Optional[datetime]:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    # ISO string
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _valid_at(fact: dict, as_of: datetime) -> bool:
    """Pure temporal predicate: is `fact` valid at instant `as_of`?

    Valid iff not superseded, and `as_of` falls within [valid_from, valid_to]
    (open bounds when null). Anticipatory facts use the same rule — they
    simply have a future valid_from, so they switch on at their effective date.
    """
    if fact.get("superseded_by"):
        return False
    vf = _coerce_dt(fact.get("valid_from"))
    vt = _coerce_dt(fact.get("valid_to"))
    if vf is not None and as_of < vf:
        return False
    if vt is not None and as_of > vt:
        return False
    return True


def _validate(kind: str, confidence: float, valid_from, valid_to,
              fact_class: str = DEFAULT_FACT_CLASS) -> None:
    if kind not in VALID_KINDS:
        raise InvalidFact(f"kind must be one of {VALID_KINDS}, got {kind!r}")
    if fact_class not in FACT_CLASSES:
        raise InvalidFact(f"fact_class must be one of {FACT_CLASSES}, got {fact_class!r}")
    if not (0.0 <= confidence <= 1.0):
        raise InvalidFact(f"confidence must be in [0,1], got {confidence}")
    if kind == "interval" and valid_to is None:
        raise InvalidFact("interval facts require valid_to")
    if kind == "anticipatory" and valid_from is None:
        raise InvalidFact("anticipatory facts require valid_from")


_INSERT_SQL = """
    INSERT INTO facts (
        kind, predicate, subject_entity_type, subject_entity_id, object_value,
        valid_from, valid_to, asserted_at, source_doc_id, confidence,
        created_by, tenant_scope, fact_class
    ) VALUES (
        %(kind)s, %(predicate)s, %(subject_entity_type)s, %(subject_entity_id)s,
        %(object_value)s::jsonb, %(valid_from)s, %(valid_to)s,
        COALESCE(%(asserted_at)s, NOW()), %(source_doc_id)s, %(confidence)s,
        %(created_by)s, %(tenant_scope)s, %(fact_class)s
    )
    RETURNING id
"""


def assert_fact(
    db,
    *,
    kind: str,
    predicate: str,
    subject_entity_type: str,
    subject_entity_id: str,
    object_value: dict,
    valid_from: Any = None,
    valid_to: Any = None,
    asserted_at: Any = None,
    source_doc_id: Optional[str] = None,
    confidence: float = 1.0,
    created_by: str = "system",
    tenant_scope: Optional[str] = None,
    fact_class: str = DEFAULT_FACT_CLASS,
) -> str:
    """Insert a fact; returns its id. Validates the ledger invariants."""
    import json
    import uuid

    _validate(kind, confidence, valid_from, valid_to, fact_class=fact_class)
    row = {
        "kind": kind,
        "predicate": predicate,
        "subject_entity_type": subject_entity_type,
        "subject_entity_id": str(subject_entity_id),
        "object_value": json.dumps(object_value or {}),
        "valid_from": valid_from,
        "valid_to": valid_to,
        "asserted_at": asserted_at,
        "source_doc_id": source_doc_id,
        "confidence": confidence,
        "created_by": created_by,
        "tenant_scope": tenant_scope,
        "fact_class": fact_class,
    }
    try:
        res = db.fetch_one(_INSERT_SQL, row) if hasattr(db, "fetch_one") else None
    except Exception:
        res = None
    if res and res.get("id"):
        return str(res["id"])
    # Fallback for execute-only paths / mocks: still issue the insert.
    db.execute(_INSERT_SQL, row)
    return str(uuid.uuid4())


def supersede_fact(db, old_fact_id: str, **new_fact_kwargs) -> str:
    """Insert a correcting fact and mark the old one superseded by it."""
    new_id = assert_fact(db, **new_fact_kwargs)
    db.execute(
        "UPDATE facts SET superseded_by = %s WHERE id = %s",
        [new_id, old_fact_id],
    )
    return new_id


_SELECT_SUBJECT_SQL = """
    SELECT id, kind, predicate, subject_entity_type, subject_entity_id,
           object_value, valid_from, valid_to, asserted_at, source_doc_id,
           confidence, created_by, superseded_by, tenant_scope
      FROM facts
     WHERE subject_entity_type = %s AND subject_entity_id = %s
       {predicate_clause}
     ORDER BY valid_from DESC NULLS LAST, asserted_at DESC
"""


def facts_as_of(
    db,
    subject_entity_type: str,
    subject_entity_id: str,
    as_of: Optional[datetime] = None,
    predicate: Optional[str] = None,
) -> list[dict]:
    """Facts about a subject valid AS-OF `as_of` (default now). Filters out
    superseded facts and (when as_of is now) future anticipatory facts; when
    as_of is a future date, anticipatory facts that have taken effect appear.
    """
    as_of = as_of or datetime.now(timezone.utc)
    params: list = [subject_entity_type, str(subject_entity_id)]
    pred_clause = ""
    if predicate:
        pred_clause = "AND predicate = %s"
        params.append(predicate)
    sql = _SELECT_SUBJECT_SQL.format(predicate_clause=pred_clause)
    try:
        rows = db.fetch_all(sql, params)
    except Exception:
        logger.exception("facts_as_of query failed for %s:%s", subject_entity_type, subject_entity_id)
        rows = []
    return [r for r in rows if _valid_at(r, as_of)]
