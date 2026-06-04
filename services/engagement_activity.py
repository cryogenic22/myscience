"""UX11 / L12 — engagement activity timeline.

A read-time union over the engagement's own timestamped artifacts (briefs,
scenarios, insights, gap remediations, dossier snapshots) rather than a new
write path threaded through every action. This keeps it honest and immediately
populated: the timeline reflects what actually happened (real rows with real
authors), needs no cross-cutting instrumentation, and an engagement with no
activity shows an honest empty state.

Each source is queried independently and merged in Python, so a missing table
(a DB without a later migration) degrades to fewer rows instead of failing the
whole timeline. Both human and agent/system actions appear — `actor_kind`
distinguishes them so the UI can label "you" vs "an agent" vs "the system".
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

ACTOR_HUMAN = "human"
ACTOR_SYSTEM = "system"

# Actors that are not real people (the derive loops / emitters stamp these).
_SYSTEM_ACTORS = {"system", "fact_emitter", "scheduler", "agent", ""}


def _classify_actor(actor: Optional[str]) -> str:
    if not actor or str(actor).lower() in _SYSTEM_ACTORS:
        return ACTOR_SYSTEM
    return ACTOR_HUMAN


def _iso(v) -> Optional[str]:
    if v is None:
        return None
    return v.isoformat() if hasattr(v, "isoformat") else str(v)


def _item(at, actor, kind, summary, ref_type, ref_id) -> dict:
    return {
        "at": _iso(at),
        "actor": actor,
        "actor_kind": _classify_actor(actor),
        "kind": kind,
        "summary": summary,
        "ref_type": ref_type,
        "ref_id": str(ref_id) if ref_id is not None else None,
    }


def _safe(db, sql: str, params: list) -> list[dict]:
    try:
        return [dict(r) for r in db.fetch_all(sql, params)]
    except Exception:
        logger.debug("engagement activity source failed", exc_info=True)
        return []


# Per-source pulls. Each is bounded so one prolific source can't dominate the
# merged feed before the final cap.
_PER_SOURCE = 40


def _briefs(db, eid: str) -> list[dict]:
    rows = _safe(db, """
        SELECT created_at AS at, created_by AS actor, id AS ref_id,
               signed_off AS signed, signed_off_at AS signed_at, signed_off_by AS signed_by
          FROM business_context_briefs
         WHERE engagement_id = %s
         ORDER BY created_at DESC LIMIT %s
    """, [eid, _PER_SOURCE])
    out = []
    for r in rows:
        out.append(_item(r["at"], r.get("actor"), "brief",
                         "Brief authored", "brief", r.get("ref_id")))
        if r.get("signed") and r.get("signed_at"):
            out.append(_item(r["signed_at"], r.get("signed_by"), "brief",
                             "Brief signed off", "brief", r.get("ref_id")))
    return out


def _scenarios(db, eid: str) -> list[dict]:
    # Group a derive batch (same second) into one line so a re-derive of N
    # scenarios reads as one event, not N.
    rows = _safe(db, """
        SELECT date_trunc('second', created_at) AS at, created_by AS actor,
               COUNT(*) AS n
          FROM scenarios
         WHERE engagement_id = %s
         GROUP BY 1, 2
         ORDER BY 1 DESC LIMIT %s
    """, [eid, _PER_SOURCE])
    out = []
    for r in rows:
        n = int(r.get("n") or 0)
        out.append(_item(r["at"], r.get("actor"), "scenario",
                         f"Derived {n} scenario{'s' if n != 1 else ''}",
                         "scenarios", None))
    return out


def _insights(db, eid: str) -> list[dict]:
    rows = _safe(db, """
        SELECT created_at AS at, created_by AS actor, id AS ref_id, statement
          FROM insights
         WHERE engagement_id = %s
         ORDER BY created_at DESC LIMIT %s
    """, [eid, _PER_SOURCE])
    out = []
    for r in rows:
        stmt = (r.get("statement") or "").strip()
        label = stmt[:80] + ("…" if len(stmt) > 80 else "")
        out.append(_item(r["at"], r.get("actor"), "insight",
                         f"Insight: {label}" if label else "Insight added",
                         "insight", r.get("ref_id")))
    return out


def _gaps(db, eid: str) -> list[dict]:
    rows = _safe(db, """
        SELECT created_at AS at, updated_at, created_by AS actor, id AS ref_id,
               gap_domain, (updated_at IS DISTINCT FROM created_at) AS updated
          FROM gap_remediations
         WHERE engagement_id = %s
         ORDER BY GREATEST(created_at, updated_at) DESC LIMIT %s
    """, [eid, _PER_SOURCE])
    out = []
    for r in rows:
        domain = r.get("gap_domain") or "domain"
        if r.get("updated") and r.get("updated_at"):
            out.append(_item(r["updated_at"], r.get("actor"), "gap",
                             f"Gap remediation updated: {domain}", "gap", r.get("ref_id")))
        else:
            out.append(_item(r["at"], r.get("actor"), "gap",
                             f"Gap remediation set: {domain}", "gap", r.get("ref_id")))
    return out


def _dossiers(db, eid: str) -> list[dict]:
    rows = _safe(db, """
        SELECT assembled_at AS at, assembled_by AS actor, id AS ref_id, version
          FROM dossier_snapshots
         WHERE engagement_id = %s
         ORDER BY assembled_at DESC LIMIT %s
    """, [eid, _PER_SOURCE])
    return [
        _item(r["at"], r.get("actor"), "dossier",
              f"Dossier assembled (v{r.get('version')})", "dossier", r.get("ref_id"))
        for r in rows
    ]


def list_engagement_activity(db, engagement_id: str, limit: int = 60) -> list[dict]:
    """Merged, newest-first activity for one engagement. Never raises — a failing
    source contributes nothing rather than breaking the timeline."""
    items: list[dict] = []
    for fn in (_briefs, _scenarios, _insights, _gaps, _dossiers):
        try:
            items.extend(fn(db, engagement_id))
        except Exception:
            logger.debug("activity source %s failed", getattr(fn, "__name__", fn),
                         exc_info=True)
    items.sort(key=lambda a: a.get("at") or "", reverse=True)
    return items[:limit]
