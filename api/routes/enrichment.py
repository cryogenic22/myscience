"""Enrichment and autonomous research API routes.

Provides endpoints to trigger deterministic enrichment, run the
autonomous research agent, and check enrichment status.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from api.deps import get_db, require_role
from db import Database

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/enrichment", tags=["enrichment"])


@router.post("/run")
def run_enrichment(
    db: Database = Depends(get_db),
    user: dict = Depends(require_role("enterprise")),
):
    """Trigger deterministic enrichment pipeline."""
    from connectors.enrichment_runner import EnrichmentRunner

    runner = EnrichmentRunner(db)
    results = runner.run_all()
    return {
        "results": [
            {
                "source": r.source,
                "total": r.total,
                "matched": r.matched,
                "errors": r.errors,
                "details": r.details,
            }
            for r in results
        ],
        "total_enriched": sum(r.matched for r in results),
    }


@router.post("/research")
def run_research(
    max_iterations: int = 10,
    db: Database = Depends(get_db),
    user: dict = Depends(require_role("enterprise")),
):
    """Run autonomous research agent loop."""
    from services.research_agent import AutonomousResearchAgent

    agent = AutonomousResearchAgent(db=db, max_api_calls_per_iteration=5)
    summary = agent.run_loop(max_iterations=max_iterations)
    return {
        "iterations": summary.iterations,
        "improvements": summary.improvements,
        "rejections": summary.rejections,
        "hitl_flagged": summary.hitl_flagged,
        "total_api_calls": summary.total_api_calls,
        "mean_fair_delta": round(summary.mean_fair_delta, 3),
    }


@router.post("/derive-competition")
def derive_competition(
    dry_run: bool = False,
    db: Database = Depends(get_db),
    user: dict = Depends(require_role("enterprise")),
):
    """Derive COMPETES_WITH links from shared mechanism + TA pairs."""
    from scripts.derive_competition import derive_competition as run_derivation
    result = run_derivation(db, dry_run=dry_run)
    return result


@router.post("/refresh-source/{source_key}")
def refresh_source(
    source_key: str,
    db: Database = Depends(get_db),
    user: dict = Depends(require_role("enterprise")),
):
    """Re-run a single data connector to refresh stale records."""
    from scheduler.runner import DataPipelineScheduler
    scheduler = DataPipelineScheduler()
    try:
        result = scheduler.run_one(source_key)
        return {"source": source_key, "status": "ok", "result": str(result)}
    except Exception as e:
        return {"source": source_key, "status": "error", "error": str(e)}


@router.post("/curate")
def run_curation(
    db: Database = Depends(get_db),
    user: dict = Depends(require_role("enterprise")),
):
    """Run 5-pass deterministic data curation pipeline.

    Passes:
      1. Company enrichment via SEC EDGAR (ticker, CIK)
      2. Orphan company linking (find trial sponsors)
      3. Resolution sweep with MentionNormalizer
      4. HITL auto-resolve (substring heuristic, no LLM)
      5. Compute and persist FAIR score
    """
    from scripts.auto_curate_v2 import run_all_curation

    results = run_all_curation(db)
    return {
        "results": results,
        "total_enriched": sum(
            r.get("enriched", r.get("resolved", r.get("linked", 0)))
            for r in results
            if isinstance(r.get("enriched", r.get("resolved", r.get("linked", 0))), int)
        ),
    }


@router.get("/status")
def enrichment_status(db: Database = Depends(get_db)):
    """Current enrichment status: unresolved count, company gaps, etc."""
    unresolved = db.fetch_one(
        "SELECT COUNT(*) as cnt FROM unresolved_entities WHERE status = 'pending'"
    )
    companies_missing_cik = db.fetch_one(
        "SELECT COUNT(*) as cnt FROM companies WHERE cik IS NULL OR cik = ''"
    )
    patents_count = db.fetch_one("SELECT COUNT(*) as cnt FROM patents")
    return {
        "unresolved_entities": unresolved["cnt"] if unresolved else 0,
        "companies_missing_cik": companies_missing_cik["cnt"] if companies_missing_cik else 0,
        "patents_populated": patents_count["cnt"] if patents_count else 0,
    }
