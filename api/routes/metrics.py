"""Metrics API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from typing import Optional

from api.deps import get_db, get_fair_scorer, get_metrics
from db import Database
from services.fair_scorer import FAIRScorer
from services.metrics import PharmaMetrics

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("/pipeline")
def pipeline_strength(
    drug_id: Optional[str] = None,
    therapeutic_area: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    svc: PharmaMetrics = Depends(get_metrics),
):
    """Drug pipeline strength: trials by phase with weighted score."""
    return svc.drug_pipeline_strength(drug_id=drug_id, therapeutic_area=therapeutic_area, limit=limit)


@router.get("/success-rate")
def success_rate(
    drug_id: Optional[str] = None,
    therapeutic_area: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    svc: PharmaMetrics = Depends(get_metrics),
):
    """Trial success rate per drug: completed vs terminated/withdrawn."""
    return svc.trial_success_rate(drug_id=drug_id, therapeutic_area=therapeutic_area, limit=limit)


@router.get("/evidence")
def evidence_density(
    drug_id: Optional[str] = None,
    min_articles: int = Query(1, ge=0),
    limit: int = Query(50, ge=1, le=200),
    svc: PharmaMetrics = Depends(get_metrics),
):
    """Evidence density: PubMed articles per drug, recency-weighted."""
    return svc.evidence_density(drug_id=drug_id, min_articles=min_articles, limit=limit)


@router.get("/competitive")
def competitive_landscape(
    therapeutic_area_id: Optional[str] = None,
    mechanism_id: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    svc: PharmaMetrics = Depends(get_metrics),
):
    """Competitive landscape: drugs per mechanism per therapeutic area."""
    return svc.competitive_landscape(
        therapeutic_area_id=therapeutic_area_id, mechanism_id=mechanism_id, limit=limit,
    )


@router.get("/portfolio")
def company_portfolio(
    company_id: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    svc: PharmaMetrics = Depends(get_metrics),
):
    """Company portfolio: drugs, trials, TAs, pipeline score rollup."""
    return svc.company_portfolio(company_id=company_id, limit=limit)


@router.post("/refresh")
def refresh_views(svc: PharmaMetrics = Depends(get_metrics)):
    """Refresh all materialized views."""
    return svc.refresh()


@router.get("/safety-signals")
def safety_signals(
    drug: Optional[str] = None,
    significant_only: bool = Query(True),
    limit: int = Query(50, ge=1, le=500),
    db: Database = Depends(get_db),
):
    """Safety signal scoring: PRR and ROR from FAERS disproportionality analysis.

    Signals with ROR lower CI > 1 are statistically significant.
    """
    conditions = []
    params = []

    if drug:
        conditions.append("LOWER(drug_name) = LOWER(%s)")
        params.append(drug)
    if significant_only:
        conditions.append("ror_lower_ci > 1")

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)

    rows = db.fetch_all(
        f"""
        SELECT drug_name, drug_id, reaction, a AS case_count,
               ROUND(prr::numeric, 2) AS prr,
               ROUND(ror::numeric, 2) AS ror,
               ROUND(ror_lower_ci::numeric, 2) AS ror_lower_ci,
               drug_total, reaction_total, total_reports
        FROM mv_safety_signals
        {where}
        ORDER BY ror DESC NULLS LAST
        LIMIT %s
        """,
        params,
    )
    return {
        "signals": rows,
        "count": len(rows),
        "methodology": "Disproportionality analysis (PRR/ROR) from FAERS adverse event reports. "
                        "Signals with ROR lower 95% CI > 1.0 are statistically significant.",
    }


@router.get("/ctx-telemetry")
def ctx_telemetry(db: Database = Depends(get_db)):
    """CTX context-building telemetry: compression ratios, token savings, build times."""
    rows = db.fetch_all(
        """SELECT
               COUNT(*) AS total_queries,
               AVG(compression_ratio) AS avg_compression,
               AVG(build_time_ms) AS avg_build_ms,
               SUM(CASE WHEN legacy_tokens > 0
                        THEN legacy_tokens - ctx_tokens
                        ELSE 0 END) AS total_tokens_saved,
               mode,
               DATE(created_at) AS day
           FROM ctx_telemetry
           GROUP BY mode, DATE(created_at)
           ORDER BY day DESC
           LIMIT 30"""
    )
    return {"telemetry": rows}


@router.get("/fair-score")
def fair_score(scorer: FAIRScorer = Depends(get_fair_scorer)):
    """Latest FAIR data quality snapshot with trend (last 5 snapshots).

    Returns the most recent computed snapshot plus historical trend
    for tracking quality improvements over time.
    """
    latest = scorer.latest()
    trend = scorer.trend(n=5)
    return {
        "latest": latest,
        "trend": trend,
    }


@router.post("/fair-score/compute")
def compute_fair_score(scorer: FAIRScorer = Depends(get_fair_scorer)):
    """Compute a fresh FAIR score, persist it, and return the snapshot.

    Use this after pipeline runs or data backfills to record a new
    quality checkpoint.
    """
    snapshot = scorer.compute()
    try:
        scorer.persist(snapshot)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("Failed to persist FAIR snapshot: %s", exc)
    return snapshot


@router.post("/refresh-views")
def refresh_views_with_timestamp(
    svc: PharmaMetrics = Depends(get_metrics),
    db: Database = Depends(get_db),
):
    """Refresh all materialized views and log timestamp.

    Calls PharmaMetrics.refresh() and records when the refresh occurred.
    """
    import logging
    from datetime import datetime, timezone

    result = svc.refresh()
    ts = datetime.now(timezone.utc).isoformat()
    logging.getLogger(__name__).info("Materialized views refreshed at %s", ts)
    return {
        "refreshed_at": ts,
        "views": result,
    }
