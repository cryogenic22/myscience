"""BE-35 — Curator-driven source weight learning service.

PB-A02 — outcome-to-weight feedback loop. Each verified outcome
contributes to a delta on the contributing source's weight; the
weekly recalibration job applies the deltas in batch and writes
an audit row per change.

Inputs:
  - decisions whose outcome has been marked verified (decisions
    table; per SPEC-021)
  - the evidence_records cited in each decision's evidence_snapshot
  - existing source weights from sources.predictive_accuracy

Outputs:
  - new sources.predictive_accuracy values
  - one row per change in source_weight_audit_log
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)


# Single recalibration step size. Small enough to avoid swings on a
# single bad/good outcome; large enough to converge in <30 verified
# decisions.
LEARNING_RATE = 0.05
DEFAULT_BASELINE = 0.7  # curated-source prior
MIN_WEIGHT = 0.0
MAX_WEIGHT = 1.0


@dataclass
class WeightChange:
    source_id: str
    old_weight: float
    new_weight: float
    contributing_decisions: int

    def delta(self) -> float:
        return self.new_weight - self.old_weight

    def to_dict(self) -> dict:
        return {
            "source_id":              self.source_id,
            "old_weight":             round(float(self.old_weight), 4),
            "new_weight":             round(float(self.new_weight), 4),
            "delta":                  round(float(self.delta()), 4),
            "contributing_decisions": int(self.contributing_decisions),
        }


def _clip(v: float) -> float:
    return max(MIN_WEIGHT, min(MAX_WEIGHT, v))


def aggregate_outcomes(
    rows: list[dict],
) -> dict[str, dict]:
    """Group ``rows`` (one per (source_id, decision_id, outcome_correct))
    into per-source { hits: int, total: int } counts.

    ``rows`` shape::

        [{"source_id": "fda", "decision_id": "d-1", "outcome_correct": True}, ...]
    """
    out: dict[str, dict] = {}
    for r in rows or []:
        sid = r.get("source_id")
        if not sid:
            continue
        bucket = out.setdefault(sid, {"hits": 0, "total": 0})
        bucket["total"] += 1
        if r.get("outcome_correct"):
            bucket["hits"] += 1
    return out


def compute_changes(
    *,
    aggregates: dict[str, dict],
    current_weights: dict[str, float],
    learning_rate: float = LEARNING_RATE,
) -> list[WeightChange]:
    """Apply hit-rate-toward-old-weight pull per source.

    new = old + lr * (hit_rate - old). lr=0 → no change; lr=1 →
    immediate replacement. Default lr=0.05 nudges weights gently.
    """
    changes: list[WeightChange] = []
    for sid, agg in aggregates.items():
        if agg["total"] <= 0:
            continue
        hit_rate = agg["hits"] / agg["total"]
        old = float(current_weights.get(sid, DEFAULT_BASELINE))
        new = _clip(old + learning_rate * (hit_rate - old))
        # Skip zero-delta updates so the audit log isn't noisy.
        if abs(new - old) < 1e-6:
            continue
        changes.append(WeightChange(
            source_id=sid, old_weight=old, new_weight=new,
            contributing_decisions=agg["total"],
        ))
    return changes


def apply_and_audit(db: Any, changes: list[WeightChange]) -> int:
    """Write each change to ``sources.predictive_accuracy`` + log a
    row in ``source_weight_audit_log``. Returns number applied."""
    applied = 0
    for ch in changes:
        try:
            db.execute(
                """UPDATE sources
                      SET predictive_accuracy = %s,
                          updated_at = NOW()
                    WHERE source_id = %s""",
                [float(ch.new_weight), ch.source_id],
            )
            db.execute(
                """INSERT INTO source_weight_audit_log
                       (source_id, old_weight, new_weight, delta,
                        contributing_decisions, actor)
                   VALUES (%s, %s, %s, %s, %s, 'curator-weekly')""",
                [ch.source_id, ch.old_weight, ch.new_weight,
                 ch.delta(), ch.contributing_decisions],
            )
            applied += 1
        except Exception as exc:
            logger.warning("apply_and_audit: source %s failed: %s",
                           ch.source_id, exc)
    return applied


def run_weekly_recalibration(db: Any) -> dict:
    """Top-level: pull outcomes from the last 7 days, compute changes,
    apply, and return a summary. Designed for the cron / scheduler
    to call once per week."""
    rows = db.fetch_all(
        """
        SELECT er.source_id,
               d.decision_id::text AS decision_id,
               (d.outcome_status = 'verified_correct') AS outcome_correct
          FROM decisions d
          JOIN evidence_snapshots es ON es.decision_id = d.decision_id
         CROSS JOIN LATERAL jsonb_array_elements(es.body -> 'claims') AS c
          JOIN claim_evidence_links cel ON cel.claim_id = (c->>'claim_id')::uuid
          JOIN evidence_records er ON er.evidence_id = cel.evidence_id
         WHERE d.outcome_verified_at > NOW() - INTERVAL '7 days'
           AND d.outcome_status IN ('verified_correct', 'verified_incorrect')
        """
    ) or []
    aggregates = aggregate_outcomes([dict(r) for r in rows])

    weight_rows = db.fetch_all(
        "SELECT source_id, predictive_accuracy FROM sources"
    ) or []
    current = {r["source_id"]: float(r.get("predictive_accuracy") or DEFAULT_BASELINE)
               for r in weight_rows if r.get("source_id")}

    changes = compute_changes(aggregates=aggregates, current_weights=current)
    applied = apply_and_audit(db, changes)
    return {
        "verified_outcomes":      sum(a["total"] for a in aggregates.values()),
        "sources_evaluated":      len(aggregates),
        "weight_changes_applied": applied,
        "changes":                [c.to_dict() for c in changes],
    }
