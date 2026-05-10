"""BE-9 — Adversary digital twin model.

Per-competitor twin storing a behavioural posterior + the last 5
evidence updates that shifted it. Powers PB-502's posterior side
panel.

Posterior shape: a 3-component mixture summing to 1.0::

    {"aggressive": 0.55, "defensive": 0.25, "cash_constrained": 0.20}

Evidence log entries::

    {"ts": ISO8601, "evidence_id": str, "what_shifted": str, "magnitude": float}

The log is bounded to the most recent 5 entries — older history
lives in agent_events for audit but is not surfaced via this API.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


VALID_KINDS = ("competitor", "regulator", "payer", "kol")
VALID_AXES = ("aggressive", "defensive", "cash_constrained")
EVIDENCE_LOG_MAX = 5
LEARNING_RATE = 0.10  # exponential update step


@dataclass
class AdversaryTwin:
    twin_id: str
    name: str
    kind: str
    posterior: dict
    last_updated_at: Optional[datetime]
    evidence_log: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "twin_id": str(self.twin_id),
            "name": self.name,
            "kind": self.kind,
            "posterior": dict(self.posterior),
            "last_updated_at": self.last_updated_at.isoformat()
                              if self.last_updated_at and hasattr(self.last_updated_at, "isoformat")
                              else None,
            "last_5_evidence_updates": list(self.evidence_log[:EVIDENCE_LOG_MAX]),
        }


class TwinNotFound(Exception):
    pass


def _normalize(p: dict) -> dict:
    """Project to the 3-axis simplex (clamp >=0, normalize to 1.0)."""
    cleaned = {a: max(0.0, float(p.get(a, 0.0))) for a in VALID_AXES}
    total = sum(cleaned.values())
    if total <= 0:
        return {"aggressive": 1/3, "defensive": 1/3, "cash_constrained": 1/3}
    return {a: v / total for a, v in cleaned.items()}


def _row_to_twin(row: dict) -> AdversaryTwin:
    posterior = row.get("posterior") or {}
    if isinstance(posterior, str):
        try:
            posterior = json.loads(posterior)
        except (TypeError, ValueError):
            posterior = {}
    log = row.get("evidence_log") or []
    if isinstance(log, str):
        try:
            log = json.loads(log)
        except (TypeError, ValueError):
            log = []
    return AdversaryTwin(
        twin_id=str(row["twin_id"]),
        name=row["name"],
        kind=row["kind"],
        posterior=_normalize(posterior),
        last_updated_at=row.get("last_updated_at"),
        evidence_log=list(log)[:EVIDENCE_LOG_MAX],
    )


def get(db: Any, twin_id: str) -> Optional[AdversaryTwin]:
    row = db.fetch_one(
        """SELECT twin_id, name, kind, posterior, last_updated_at, evidence_log
             FROM adversary_twins
            WHERE twin_id::text = %s""",
        [str(twin_id)],
    )
    return _row_to_twin(row) if row else None


def list_twins(db: Any, *, kind: Optional[str] = None) -> list[AdversaryTwin]:
    if kind is not None and kind not in VALID_KINDS:
        raise ValueError(f"kind must be in {VALID_KINDS}")
    sql = (
        "SELECT twin_id, name, kind, posterior, last_updated_at, evidence_log "
        "FROM adversary_twins"
    )
    params: list = []
    if kind:
        sql += " WHERE kind = %s"
        params.append(kind)
    sql += " ORDER BY kind, name"
    rows = db.fetch_all(sql, params) or []
    return [_row_to_twin(r) for r in rows]


def update_with_evidence(
    db: Any,
    *,
    twin_id: str,
    evidence_id: str,
    target_axis: str,
    magnitude: float,
    what_shifted: str,
) -> AdversaryTwin:
    """Apply an exponential update toward ``target_axis``.

    new[axis] = (1 - lr*magnitude) * old[axis] for off-axis
    new[target] += lr * magnitude * (1 - old[target])

    Magnitude is clamped to [0, 1]; the result is renormalized.
    Caller supplies a one-line ``what_shifted`` for the log.
    """
    if target_axis not in VALID_AXES:
        raise ValueError(f"target_axis must be in {VALID_AXES}")
    twin = get(db, twin_id)
    if twin is None:
        raise TwinNotFound(twin_id)
    mag = max(0.0, min(1.0, float(magnitude)))
    new_post = dict(twin.posterior)
    target_old = new_post.get(target_axis, 0.0)
    # Pull off-axis weight toward the target proportionally.
    new_post[target_axis] = target_old + LEARNING_RATE * mag * (1.0 - target_old)
    for axis in VALID_AXES:
        if axis == target_axis:
            continue
        new_post[axis] = new_post.get(axis, 0.0) * (1.0 - LEARNING_RATE * mag)
    new_post = _normalize(new_post)

    new_entry = {
        "ts":            datetime.now(timezone.utc).isoformat(),
        "evidence_id":   str(evidence_id),
        "what_shifted":  what_shifted[:500],
        "magnitude":     round(mag, 4),
        "target_axis":   target_axis,
    }
    new_log = ([new_entry] + list(twin.evidence_log))[:EVIDENCE_LOG_MAX]

    row = db.fetch_one(
        """
        UPDATE adversary_twins
           SET posterior = %s::jsonb,
               last_updated_at = NOW(),
               evidence_log = %s::jsonb
         WHERE twin_id::text = %s
        RETURNING twin_id, name, kind, posterior, last_updated_at, evidence_log
        """,
        [json.dumps(new_post), json.dumps(new_log), str(twin_id)],
    )
    if not row:
        raise TwinNotFound(twin_id)
    return _row_to_twin(row)
