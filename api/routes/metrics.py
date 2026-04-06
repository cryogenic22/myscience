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


@router.get("/ctx-value-report")
def ctx_value_report(db: Database = Depends(get_db)):
    """CTX system value report — compression, cost savings, quality metrics.

    Use this to track whether CTX is delivering value over time.
    """
    # Check if telemetry table exists
    try:
        db.fetch_one("SELECT 1 FROM ctx_telemetry LIMIT 1")
    except Exception:
        return {
            "status": "no_telemetry",
            "message": "ctx_telemetry table not found. Run migration 014.",
            "summary": {}, "by_mode": [], "by_intent": [], "weekly_trend": [],
        }

    # Overall stats
    overall = db.fetch_one("""
        SELECT COUNT(*) as total_queries,
               ROUND(AVG(ctx_tokens)::numeric, 0) as avg_ctx_tokens,
               ROUND(AVG(NULLIF(legacy_tokens,0))::numeric, 0) as avg_legacy_tokens,
               ROUND(AVG(compression_ratio)::numeric, 3) as avg_compression,
               ROUND(AVG(build_time_ms)::numeric, 2) as avg_build_ms,
               SUM(CASE WHEN legacy_tokens > 0 THEN legacy_tokens - ctx_tokens ELSE 0 END) as total_tokens_saved
        FROM ctx_telemetry
    """) or {}

    # By mode
    by_mode = db.fetch_all("""
        SELECT mode, COUNT(*) as queries,
               ROUND(AVG(ctx_tokens)::numeric, 0) as avg_tokens,
               ROUND(AVG(compression_ratio)::numeric, 3) as avg_ratio
        FROM ctx_telemetry GROUP BY mode ORDER BY queries DESC
    """) or []

    # By intent
    by_intent = db.fetch_all("""
        SELECT intent, COUNT(*) as queries,
               ROUND(AVG(ctx_tokens)::numeric, 0) as avg_tokens,
               ROUND(AVG(compression_ratio)::numeric, 3) as avg_ratio
        FROM ctx_telemetry WHERE intent IS NOT NULL AND intent != ''
        GROUP BY intent ORDER BY queries DESC
    """) or []

    # Weekly trend
    weekly = db.fetch_all("""
        SELECT DATE_TRUNC('week', created_at)::date as week,
               COUNT(*) as queries,
               ROUND(AVG(ctx_tokens)::numeric, 0) as avg_tokens,
               ROUND(AVG(compression_ratio)::numeric, 3) as avg_ratio,
               SUM(CASE WHEN legacy_tokens > 0 THEN legacy_tokens - ctx_tokens ELSE 0 END) as tokens_saved
        FROM ctx_telemetry
        GROUP BY 1 ORDER BY 1 DESC LIMIT 12
    """) or []

    # Cost estimate (GPT-4o pricing: $2.50/1M input tokens)
    total_tokens_saved = overall.get('total_tokens_saved', 0) or 0
    estimated_savings_usd = round(total_tokens_saved * 2.50 / 1_000_000, 2)

    # CTX active status
    ctx_queries = sum(1 for m in by_mode if m.get('mode') == 'ctx')
    legacy_queries = sum(1 for m in by_mode if m.get('mode') == 'legacy')

    return {
        "status": "ctx_active" if ctx_queries > 0 else "legacy_only",
        "summary": {
            "total_queries": overall.get('total_queries', 0),
            "avg_ctx_tokens": overall.get('avg_ctx_tokens'),
            "avg_legacy_tokens": overall.get('avg_legacy_tokens'),
            "avg_compression_ratio": overall.get('avg_compression'),
            "avg_build_time_ms": overall.get('avg_build_ms'),
            "total_tokens_saved": total_tokens_saved,
            "estimated_cost_savings_usd": estimated_savings_usd,
        },
        "by_mode": by_mode,
        "by_intent": by_intent,
        "weekly_trend": weekly,
    }


@router.get("/unresolved-count")
def unresolved_count(db: Database = Depends(get_db)):
    """Count of pending unresolved entities in the HITL queue."""
    try:
        row = db.fetch_one(
            "SELECT COUNT(*) AS cnt FROM hitl_reviews WHERE status = 'pending'"
        )
        pending = row["cnt"] if row else 0
    except Exception:
        pending = 0

    try:
        by_type = db.fetch_all(
            "SELECT entity_type, COUNT(*) AS cnt FROM hitl_reviews "
            "WHERE status = 'pending' GROUP BY entity_type ORDER BY cnt DESC"
        )
    except Exception:
        by_type = []

    return {
        "total_pending": pending,
        "by_entity_type": {r["entity_type"]: r["cnt"] for r in by_type},
        "threshold": 50,
        "alert": pending > 50,
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
