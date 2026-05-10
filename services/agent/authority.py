"""BE-12 — Agent authority spectrum + promotion engine.

Per (agent, scenario_type), tracks current authority level (1-5) +
rolling calibration. Auto-promotes when calibration ≥ 0.70 over the
last ``WINDOW_SIZE`` scenarios.

5-level spectrum (per spec):
  L1 watch              — observe only, never surface to UI
  L2 suggest            — surface as background ideas
  L3 recommend          — top-of-rail, requires user click to act
  L4 act_with_notice    — auto-act, notify user
  L5 auto_audit         — auto-act, audit-only review

Promotion rules:
  - Earned promotion: calibration ≥ 0.70 over WINDOW_SIZE scenarios
    auto-bumps the level by +1 (capped at L5).
  - Demotion: calibration < 0.50 over the same window auto-drops -1
    (floored at L1).
  - Manual override allowed via update_authority(actor=user_id).
  - Each transition rows a record in agent_authority_promotions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)


WINDOW_SIZE = 14
PROMOTE_THRESHOLD = 0.70
DEMOTE_THRESHOLD = 0.50
MIN_LEVEL = 1
MAX_LEVEL = 5


@dataclass
class Authority:
    agent: str
    scenario_type: str
    current_level: int
    calibration_score: float
    scenario_count: int
    last_promoted_at: Optional[Any]

    def to_dict(self) -> dict:
        return {
            "agent":             self.agent,
            "scenario_type":     self.scenario_type,
            "current_level":     int(self.current_level),
            "calibration_score": round(float(self.calibration_score), 4),
            "scenario_count":    int(self.scenario_count),
            "last_promoted_at":  self.last_promoted_at.isoformat()
                                 if self.last_promoted_at and hasattr(self.last_promoted_at, "isoformat")
                                 else None,
        }


def _row_to_auth(row: dict) -> Authority:
    return Authority(
        agent=row["agent"],
        scenario_type=row["scenario_type"],
        current_level=int(row.get("current_level") or 1),
        calibration_score=float(row.get("calibration_score") or 0.5),
        scenario_count=int(row.get("scenario_count") or 0),
        last_promoted_at=row.get("last_promoted_at"),
    )


def get(db: Any, *, agent: str, scenario_type: str) -> Optional[Authority]:
    row = db.fetch_one(
        """SELECT agent, scenario_type, current_level, calibration_score,
                  scenario_count, last_promoted_at
             FROM agent_authority
            WHERE agent = %s AND scenario_type = %s""",
        [agent, scenario_type],
    )
    return _row_to_auth(row) if row else None


def list_all(db: Any) -> list[Authority]:
    rows = db.fetch_all(
        """SELECT agent, scenario_type, current_level, calibration_score,
                  scenario_count, last_promoted_at
             FROM agent_authority
            ORDER BY agent, scenario_type"""
    ) or []
    return [_row_to_auth(r) for r in rows]


def record_outcome(
    db: Any,
    *,
    agent: str,
    scenario_type: str,
    correct: bool,
) -> Authority:
    """Record one outcome and return the updated row.

    Maintains an EWMA-like calibration: new = (count*old + correct) /
    (count + 1). Then runs the promotion engine.
    """
    existing = get(db, agent=agent, scenario_type=scenario_type)
    if existing is None:
        # Insert fresh row at level 1 with the first datapoint.
        new_count = 1
        new_score = 1.0 if correct else 0.0
        new_level = 1
        db.execute(
            """INSERT INTO agent_authority
                   (agent, scenario_type, current_level,
                    calibration_score, scenario_count)
               VALUES (%s, %s, %s, %s, %s)""",
            [agent, scenario_type, new_level, new_score, new_count],
        )
        return Authority(
            agent=agent, scenario_type=scenario_type,
            current_level=new_level, calibration_score=new_score,
            scenario_count=new_count, last_promoted_at=None,
        )

    n = existing.scenario_count + 1
    score = (existing.calibration_score * existing.scenario_count + (1.0 if correct else 0.0)) / n

    # Run promotion / demotion engine
    new_level = existing.current_level
    promoted_at_clause = ""
    promote = False
    if n >= WINDOW_SIZE:
        if score >= PROMOTE_THRESHOLD and existing.current_level < MAX_LEVEL:
            new_level = existing.current_level + 1
            promote = True
            promoted_at_clause = ", last_promoted_at = NOW()"
        elif score < DEMOTE_THRESHOLD and existing.current_level > MIN_LEVEL:
            new_level = existing.current_level - 1
            promote = True
            promoted_at_clause = ", last_promoted_at = NOW()"

    row = db.fetch_one(
        f"""
        UPDATE agent_authority
           SET current_level = %s,
               calibration_score = %s,
               scenario_count = %s,
               updated_at = NOW()
               {promoted_at_clause}
         WHERE agent = %s AND scenario_type = %s
        RETURNING agent, scenario_type, current_level,
                  calibration_score, scenario_count, last_promoted_at
        """,
        [new_level, score, n, agent, scenario_type],
    )

    if promote:
        try:
            db.execute(
                """INSERT INTO agent_authority_promotions
                       (agent, scenario_type, from_level, to_level,
                        calibration_score, scenario_count, actor)
                   VALUES (%s, %s, %s, %s, %s, %s, 'auto')""",
                [agent, scenario_type, existing.current_level, new_level, score, n],
            )
        except Exception:
            logger.warning("authority: failed to log auto-promotion", exc_info=True)

    return _row_to_auth(row)


def update_authority(
    db: Any,
    *,
    agent: str,
    scenario_type: str,
    new_level: int,
    actor_user_id: str,
) -> Authority:
    """Manual override (admin / steward). Logs the transition with
    actor=user_id rather than ``auto``."""
    if not (MIN_LEVEL <= new_level <= MAX_LEVEL):
        raise ValueError(f"new_level must be in [{MIN_LEVEL}, {MAX_LEVEL}]")

    existing = get(db, agent=agent, scenario_type=scenario_type)
    from_level = existing.current_level if existing else 1
    if existing is None:
        db.execute(
            """INSERT INTO agent_authority
                   (agent, scenario_type, current_level,
                    last_promoted_at)
               VALUES (%s, %s, %s, NOW())""",
            [agent, scenario_type, new_level],
        )
    else:
        db.execute(
            """UPDATE agent_authority
                  SET current_level = %s,
                      last_promoted_at = NOW(),
                      updated_at = NOW()
                WHERE agent = %s AND scenario_type = %s""",
            [new_level, agent, scenario_type],
        )

    try:
        db.execute(
            """INSERT INTO agent_authority_promotions
                   (agent, scenario_type, from_level, to_level,
                    calibration_score, scenario_count, actor)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            [agent, scenario_type, from_level, new_level,
             existing.calibration_score if existing else 0.5,
             existing.scenario_count if existing else 0,
             actor_user_id],
        )
    except Exception:
        logger.warning("authority: failed to log manual override", exc_info=True)

    return get(db, agent=agent, scenario_type=scenario_type)


def list_promotions(db: Any, *, limit: int = 100) -> list[dict]:
    rows = db.fetch_all(
        """SELECT id, agent, scenario_type, from_level, to_level,
                  calibration_score, scenario_count, actor, created_at
             FROM agent_authority_promotions
            ORDER BY created_at DESC
            LIMIT %s""",
        [max(1, min(int(limit), 500))],
    ) or []
    out = []
    for r in rows:
        d = dict(r)
        if d.get("created_at") and hasattr(d["created_at"], "isoformat"):
            d["created_at"] = d["created_at"].isoformat()
        out.append(d)
    return out
