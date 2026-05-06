"""SPEC-021 Phase E — Inbox API.

Single-call aggregator for the /ci default landing surface. Returns
the four "needs my attention" sections in one response so the
frontend doesn't waterfall four queries at page load.

Sections:
  - pending_proposals: outcome_proposals awaiting confirm, joined to
    signal headline + decision title
  - overdue_decisions: my decisions past deadline, status open/in_progress
  - high_impact_signals: recent (<7 days) high-impact signals worth
    war-gaming, deduped by primary_entity_id
  - calibration_summary: trailing-30d aggregate of my captured outcomes
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends

from api.deps import get_db, require_role
from db import Database

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/inbox", tags=["inbox"])


def _iso(v):
    if v is None:
        return None
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return str(v)


def _pending_proposals(db: Database, user_id: str, limit: int = 10) -> list[dict]:
    """Outcome proposals awaiting confirm, scoped to my decisions only."""
    try:
        rows = db.fetch_all(
            """SELECT p.id AS proposal_id, p.decision_id, p.matched_signal_id,
                      p.match_score, p.match_components, p.proposed_at,
                      d.title AS decision_title,
                      d.status AS decision_status,
                      s.headline AS signal_headline,
                      s.summary AS signal_summary,
                      s.kbq_tags AS signal_kbq_tags,
                      s.primary_entity_name AS signal_entity
               FROM outcome_proposals p
               JOIN decisions d ON d.id = p.decision_id
               LEFT JOIN signals s ON s.id = p.matched_signal_id
               WHERE p.status = 'pending'
                 AND d.owner_user_id = %s::uuid
               ORDER BY p.match_score DESC, p.proposed_at DESC
               LIMIT %s""",
            [user_id, limit],
        ) or []
    except Exception:
        logger.exception("inbox.pending_proposals query failed")
        return []

    out = []
    for r in rows:
        components = r.get("match_components") or {}
        if isinstance(components, str):
            try:
                components = json.loads(components)
            except Exception:
                components = {}
        out.append({
            "proposal_id": str(r.get("proposal_id")),
            "decision_id": str(r.get("decision_id")),
            "decision_title": r.get("decision_title"),
            "decision_status": r.get("decision_status"),
            "matched_signal_id": str(r.get("matched_signal_id")),
            "signal_headline": r.get("signal_headline"),
            "signal_summary": r.get("signal_summary"),
            "signal_kbq_tags": list(r.get("signal_kbq_tags") or []),
            "signal_entity": r.get("signal_entity"),
            "match_score": r.get("match_score"),
            "match_components": components,
            "proposed_at": _iso(r.get("proposed_at")),
        })
    return out


def _overdue_decisions(db: Database, user_id: str, limit: int = 10) -> list[dict]:
    try:
        rows = db.fetch_all(
            """SELECT id, title, deadline, status, war_room_id,
                      target_metric, target_value, confidence_at_commit,
                      created_at
               FROM decisions
               WHERE owner_user_id = %s::uuid
                 AND status IN ('open', 'in_progress')
                 AND deadline IS NOT NULL
                 AND deadline < CURRENT_DATE
               ORDER BY deadline ASC
               LIMIT %s""",
            [user_id, limit],
        ) or []
    except Exception:
        logger.exception("inbox.overdue_decisions query failed")
        return []

    from datetime import date
    today = date.today()
    out = []
    for r in rows:
        d = r.get("deadline")
        days_overdue = None
        if d:
            try:
                days_overdue = (today - d).days
            except Exception:
                pass
        out.append({
            "id": str(r.get("id")),
            "title": r.get("title"),
            "deadline": _iso(d),
            "days_overdue": days_overdue,
            "status": r.get("status"),
            "war_room_id": str(r["war_room_id"]) if r.get("war_room_id") else None,
            "target_metric": r.get("target_metric"),
            "target_value": r.get("target_value"),
            "confidence_at_commit": r.get("confidence_at_commit"),
        })
    return out


def _high_impact_signals(db: Database, limit: int = 5) -> list[dict]:
    """Recent high-impact signals worth war-gaming.

    Deduped by primary_entity_id so we don't flood the inbox with 5
    signals about the same company.
    """
    try:
        rows = db.fetch_all(
            """SELECT DISTINCT ON (primary_entity_id)
                      id, headline, summary, kbq_tags,
                      primary_entity_id, primary_entity_type,
                      primary_entity_name, impact_tier, trust_score,
                      created_at
               FROM signals
               WHERE impact_tier = 'high'
                 AND status IN ('reviewed', 'shipped')
                 AND created_at >= NOW() - INTERVAL '7 days'
               ORDER BY primary_entity_id, created_at DESC
               LIMIT %s""",
            [limit],
        ) or []
    except Exception:
        logger.exception("inbox.high_impact_signals query failed")
        return []

    return [{
        "id": str(r.get("id")),
        "headline": r.get("headline"),
        "summary": r.get("summary"),
        "kbq_tags": list(r.get("kbq_tags") or []),
        "primary_entity_id": r.get("primary_entity_id"),
        "primary_entity_type": r.get("primary_entity_type"),
        "primary_entity_name": r.get("primary_entity_name"),
        "impact_tier": r.get("impact_tier"),
        "trust_score": r.get("trust_score"),
        "created_at": _iso(r.get("created_at")),
    } for r in rows]


def _calibration_summary(db: Database, user_id: str) -> dict:
    """Trailing-30d aggregate of my captured outcomes."""
    try:
        row = db.fetch_one(
            """SELECT COUNT(*) AS total,
                      AVG(calibration_score) AS mean_cal,
                      COUNT(*) FILTER (WHERE status = 'verified') AS verified,
                      COUNT(*) FILTER (WHERE status = 'missed') AS missed
               FROM decisions
               WHERE owner_user_id = %s::uuid
                 AND actual_outcome_recorded_at >= NOW() - INTERVAL '30 days'""",
            [user_id],
        )
    except Exception:
        logger.exception("inbox.calibration_summary query failed")
        return {"last_30d_mean": None, "verified_count": 0, "missed_count": 0, "total": 0}

    if not row:
        return {"last_30d_mean": None, "verified_count": 0, "missed_count": 0, "total": 0}

    mean = row.get("mean_cal")
    return {
        "last_30d_mean": float(mean) if mean is not None else None,
        "verified_count": int(row.get("verified") or 0),
        "missed_count": int(row.get("missed") or 0),
        "total": int(row.get("total") or 0),
    }


@router.get("")
def get_inbox(
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    """Return the four inbox sections in one call."""
    user_id = user.get("id")
    return {
        "pending_proposals": _pending_proposals(db, user_id),
        "overdue_decisions": _overdue_decisions(db, user_id),
        "high_impact_signals": _high_impact_signals(db),
        "calibration_summary": _calibration_summary(db, user_id),
    }


# ────────────────────────────────────────────────────────────────────
# Phase E — Insights (calibration trends + outcome stream)
# ────────────────────────────────────────────────────────────────────

def _calibration_trend(db: Database, user_id: str, months: int = 12) -> list[dict]:
    """Per-month aggregate of captured outcomes for the user."""
    try:
        rows = db.fetch_all(
            f"""SELECT date_trunc('month', actual_outcome_recorded_at) AS month,
                       COUNT(*) AS total,
                       AVG(calibration_score) AS mean_score,
                       COUNT(*) FILTER (WHERE status = 'verified') AS verified,
                       COUNT(*) FILTER (WHERE status = 'missed') AS missed
                FROM decisions
                WHERE owner_user_id = %s::uuid
                  AND actual_outcome_recorded_at >= NOW() - INTERVAL '{months} months'
                GROUP BY 1
                ORDER BY 1 ASC""",
            [user_id],
        ) or []
    except Exception:
        logger.exception("insights.calibration_trend query failed")
        return []
    return [{
        "month": _iso(r.get("month")),
        "total": int(r.get("total") or 0),
        "mean_score": float(r["mean_score"]) if r.get("mean_score") is not None else None,
        "verified": int(r.get("verified") or 0),
        "missed": int(r.get("missed") or 0),
    } for r in rows]


def _outcome_stream(db: Database, user_id: str, limit: int = 50) -> list[dict]:
    """Chronological feed of outcome events: captures + auto-proposals
    across the user's decisions. UNION'd in SQL to get a single
    ordered list."""
    try:
        rows = db.fetch_all(
            """(SELECT 'capture'::text AS event_type,
                       d.id AS decision_id, d.title AS decision_title,
                       d.status AS decision_status,
                       d.actual_outcome AS detail_text,
                       d.calibration_score AS detail_score,
                       NULL::uuid AS proposal_id, NULL::uuid AS signal_id,
                       NULL::text AS signal_headline,
                       d.actual_outcome_recorded_at AS event_at
                FROM decisions d
                WHERE d.owner_user_id = %s::uuid
                  AND d.actual_outcome_recorded_at IS NOT NULL)
               UNION ALL
               (SELECT 'proposal'::text AS event_type,
                       d.id AS decision_id, d.title AS decision_title,
                       d.status AS decision_status,
                       NULL AS detail_text,
                       p.match_score AS detail_score,
                       p.id AS proposal_id, p.matched_signal_id AS signal_id,
                       s.headline AS signal_headline,
                       p.proposed_at AS event_at
                FROM outcome_proposals p
                JOIN decisions d ON d.id = p.decision_id
                LEFT JOIN signals s ON s.id = p.matched_signal_id
                WHERE d.owner_user_id = %s::uuid)
               ORDER BY event_at DESC NULLS LAST
               LIMIT %s""",
            [user_id, user_id, limit],
        ) or []
    except Exception:
        logger.exception("insights.outcome_stream query failed")
        return []
    return [{
        "event_type": r.get("event_type"),
        "decision_id": str(r.get("decision_id")) if r.get("decision_id") else None,
        "decision_title": r.get("decision_title"),
        "decision_status": r.get("decision_status"),
        "detail_text": r.get("detail_text"),
        "detail_score": r.get("detail_score"),
        "proposal_id": str(r["proposal_id"]) if r.get("proposal_id") else None,
        "signal_id": str(r["signal_id"]) if r.get("signal_id") else None,
        "signal_headline": r.get("signal_headline"),
        "event_at": _iso(r.get("event_at")),
    } for r in rows]


# Separate route since it's a different surface
insights_router = APIRouter(prefix="/insights", tags=["insights"])


@insights_router.get("")
def get_insights(
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    """Phase E — calibration trends + outcome stream for the current user."""
    user_id = user.get("id")
    return {
        "calibration_trend": _calibration_trend(db, user_id),
        "outcome_stream": _outcome_stream(db, user_id),
        "summary": _calibration_summary(db, user_id),
    }
