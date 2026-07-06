"""BE-41 — Outcome-to-prompt-weight backpropagation.

PB-C02: when a decision's outcome is verified, attribute the
result to the prompt versions that produced its recommendation
and update each prompt's calibration score. Flagged-prompt
rollback is then a one-click admin action — pick the prompt
with the lowest calibration, demote ``is_active``.

Inputs:
  - decisions whose outcome has been marked verified (status =
    'verified_correct' | 'verified_incorrect')
  - llm_call_log rows joined to decision_id (SPEC-026 ties each
    LLM call to a prompt_id + version)

Outputs:
  - per (prompt_id) calibration score in
    ``prompt_calibration`` (one row per prompt, EWMA-updated)
  - flag set on prompt_registry.is_active = FALSE for any prompt
    with calibration < ROLLBACK_THRESHOLD over ≥ FLAG_MIN_OUTCOMES
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)


LEARNING_RATE = 0.10  # EWMA step
ROLLBACK_THRESHOLD = 0.40  # demote prompt below this
FLAG_MIN_OUTCOMES = 5      # need at least this many before demoting
DEFAULT_BASELINE = 0.65


@dataclass
class PromptCalibration:
    prompt_id: str
    name: str
    version: int
    calibration_score: float
    outcomes_seen: int
    flagged: bool

    def to_dict(self) -> dict:
        return {
            "prompt_id":         str(self.prompt_id),
            "name":              self.name,
            "version":           int(self.version),
            "calibration_score": round(float(self.calibration_score), 4),
            "outcomes_seen":     int(self.outcomes_seen),
            "flagged":           bool(self.flagged),
        }


def aggregate(rows: list[dict]) -> dict[str, dict]:
    """Group ``rows`` (one per (prompt_id, decision_id, outcome_correct))
    into per-prompt {hits, total}."""
    out: dict[str, dict] = {}
    for r in rows or []:
        pid = r.get("prompt_id")
        if not pid:
            continue
        bucket = out.setdefault(str(pid), {"hits": 0, "total": 0})
        bucket["total"] += 1
        if r.get("outcome_correct"):
            bucket["hits"] += 1
    return out


def update_one(
    *,
    prompt_id: str,
    hits: int,
    total: int,
    current_score: float,
    current_outcomes: int,
    learning_rate: float = LEARNING_RATE,
) -> tuple[float, int]:
    """Apply EWMA update toward observed hit_rate. Returns
    (new_score, new_outcomes_total)."""
    if total <= 0:
        return current_score, current_outcomes
    hit_rate = hits / total
    new_score = current_score + learning_rate * (hit_rate - current_score)
    new_score = max(0.0, min(1.0, new_score))
    return new_score, current_outcomes + total


def run_recalibration(db: Any, *, since_days: int = 7) -> dict:
    """Top-level cron entry for BE-41.

    Pulls verified outcomes from the last ``since_days``, joins to
    llm_call_log to find the prompt_ids that contributed, applies
    EWMA updates, and demotes prompts below ROLLBACK_THRESHOLD.
    """
    rows = db.fetch_all(
        f"""
        SELECT lcl.prompt_id::text AS prompt_id,
               d.decision_id::text AS decision_id,
               (d.outcome_status = 'verified_correct') AS outcome_correct
          FROM decisions d
          JOIN llm_call_log lcl ON lcl.decision_id = d.decision_id
         WHERE d.outcome_verified_at > NOW() - INTERVAL '%s days'
           AND d.outcome_status IN ('verified_correct','verified_incorrect')
        """ % int(since_days)
    ) or []
    aggregates = aggregate([dict(r) for r in rows])
    if not aggregates:
        return {"verified_outcomes": 0, "prompts_updated": 0,
                "flagged": 0, "details": []}

    # Pull current calibrations
    cur_rows = db.fetch_all(
        "SELECT prompt_id::text AS prompt_id, calibration_score, outcomes_seen "
        "FROM prompt_calibration"
    ) or []
    current = {r["prompt_id"]: (
        float(r.get("calibration_score") or DEFAULT_BASELINE),
        int(r.get("outcomes_seen") or 0),
    ) for r in cur_rows}

    updated = 0
    flagged = 0
    details: list[dict] = []
    for pid, agg in aggregates.items():
        old_score, old_n = current.get(pid, (DEFAULT_BASELINE, 0))
        new_score, new_n = update_one(
            prompt_id=pid, hits=agg["hits"], total=agg["total"],
            current_score=old_score, current_outcomes=old_n,
        )
        try:
            db.execute(
                """INSERT INTO prompt_calibration
                       (prompt_id, calibration_score, outcomes_seen, updated_at)
                   VALUES (%s::uuid, %s, %s, NOW())
                   ON CONFLICT (prompt_id) DO UPDATE
                       SET calibration_score = EXCLUDED.calibration_score,
                           outcomes_seen     = EXCLUDED.outcomes_seen,
                           updated_at        = NOW()""",
                [pid, new_score, new_n],
            )
            updated += 1
        except Exception as exc:
            logger.warning("prompt_calibration update failed for %s: %s", pid, exc)
            continue

        # Demote? Only after enough outcomes.
        if new_score < ROLLBACK_THRESHOLD and new_n >= FLAG_MIN_OUTCOMES:
            try:
                db.execute(
                    "UPDATE prompt_registry SET is_active = FALSE "
                    "WHERE prompt_id::text = %s",
                    [pid],
                )
                flagged += 1
            except Exception:
                logger.debug("failed to demote prompt %s", pid, exc_info=True)

        details.append({
            "prompt_id": pid, "old_score": round(old_score, 4),
            "new_score": round(new_score, 4),
            "outcomes_seen": new_n,
            "flagged": (new_score < ROLLBACK_THRESHOLD and new_n >= FLAG_MIN_OUTCOMES),
        })

    return {
        "verified_outcomes": sum(a["total"] for a in aggregates.values()),
        "prompts_updated": updated,
        "flagged": flagged,
        "details": details,
    }
