"""Metrics API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from typing import Optional

from api.deps import get_metrics
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
