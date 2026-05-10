"""BE-36 — Per-source SLA monitoring + graceful degradation hint.

PB-A03 needs:
1. A periodic check that detects when a source has stopped
   reporting / is degraded.
2. A "missing because" hint user-facing answers can render when a
   degraded source would have been the primary contributor.

This module exposes:
- ``check_health(db)`` — runs once per cycle (cron); marks each
  source's health state in the registry.
- ``degradation_notice(db, source_ids)`` — returns the
  human-readable string the synthesis layer splices into a chat
  response when a degraded source was relevant.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional

logger = logging.getLogger(__name__)


# SLA thresholds (hours since last successful run)
HEALTHY_HOURS    = 24
DEGRADED_HOURS   = 72
DOWN_HOURS       = 168  # 7 days

VALID_HEALTH = ("healthy", "degraded", "down", "unknown")


@dataclass
class HealthState:
    source_id: str
    health: str
    last_run_at: Optional[datetime]
    hours_stale: Optional[float]

    def to_dict(self) -> dict:
        return {
            "source_id":    self.source_id,
            "health":       self.health,
            "last_run_at":  self.last_run_at.isoformat() if self.last_run_at and hasattr(self.last_run_at, "isoformat") else None,
            "hours_stale":  None if self.hours_stale is None else round(float(self.hours_stale), 2),
        }


def _classify(hours_stale: Optional[float]) -> str:
    if hours_stale is None:
        return "unknown"
    if hours_stale <= HEALTHY_HOURS:
        return "healthy"
    if hours_stale <= DEGRADED_HOURS:
        return "degraded"
    return "down"


def check_health(db: Any) -> list[HealthState]:
    """Compute (and persist) the current health for every registered
    source. Reads ``connector_runs.started_at`` to find each source's
    most-recent successful cycle.
    """
    rows = db.fetch_all(
        """
        SELECT s.source_id,
               MAX(r.started_at) FILTER (WHERE r.failures = 0 OR r.failures IS NULL)
                   AS last_success_at
          FROM sources s
          LEFT JOIN connector_runs r
                 ON r.source_key = s.source_id
         GROUP BY s.source_id
        """
    ) or []

    now = datetime.now(timezone.utc)
    out: list[HealthState] = []
    for r in rows:
        ts = r.get("last_success_at")
        hours = None
        if ts and hasattr(ts, "tzinfo"):
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            hours = (now - ts).total_seconds() / 3600.0
        st = HealthState(
            source_id=r["source_id"],
            last_run_at=ts,
            hours_stale=hours,
            health=_classify(hours),
        )
        out.append(st)

        # Best-effort persist on the registry row so the health
        # surfaces in /sources without a join. Failure is non-fatal.
        try:
            db.execute(
                "UPDATE sources SET health = %s, updated_at = NOW() WHERE source_id = %s",
                [st.health, st.source_id],
            )
        except Exception:
            logger.debug("source_health: persist failed for %s", st.source_id, exc_info=True)
    return out


def degradation_notice(db: Any, source_ids: Iterable[str]) -> Optional[str]:
    """Return a one-sentence "missing because …" string when any of
    the supplied sources is degraded or down. Returns None when all
    are healthy or unknown — caller should NOT splice anything in.

    Used by the synthesis layer when assembling a chat response.
    """
    ids = [s for s in source_ids if s]
    if not ids:
        return None
    rows = db.fetch_all(
        "SELECT source_id, COALESCE(health,'unknown') AS health "
        "FROM sources WHERE source_id = ANY(%s)",
        [ids],
    ) or []
    bad = [r for r in rows if r.get("health") in ("degraded", "down")]
    if not bad:
        return None
    names = ", ".join(sorted({str(r["source_id"]) for r in bad}))
    plural = "source" if len(bad) == 1 else "sources"
    return f"Note: {plural} {names} {'is' if len(bad) == 1 else 'are'} currently degraded — coverage may be incomplete."
