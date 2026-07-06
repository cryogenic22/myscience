"""SPEC_027 — Source Registry API.

Endpoints:
  POST   /sources                          uploader+
  GET    /sources                          viewer+
  GET    /sources/health-summary           viewer+
  GET    /sources/{source_id}              viewer+
  PATCH  /sources/{source_id}              uploader+
  GET    /sources/{source_id}/history      viewer+
  POST   /sources/{source_id}/recompute    uploader+
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from api.deps import get_db, require_role
from db import Database
from services.source_registry import (
    SourceNotFound,
    SourceRegistryService,
    VALID_KINDS,
    VALID_LICENSE_STATUSES,
    VALID_TIERS,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sources", tags=["sources"])


# ────────────────────────────────────────────────────────────────────
# Request schemas
# ────────────────────────────────────────────────────────────────────

class RegisterSourceBody(BaseModel):
    source_id: str = Field(min_length=1, max_length=100)
    display_name: str = Field(min_length=1, max_length=200)
    tier: int = Field(ge=1, le=4)
    kind: str = Field(default="free")
    base_url: Optional[str] = Field(default=None, max_length=2000)
    description: Optional[str] = Field(default=None, max_length=2000)
    license_status: str = Field(default="not_applicable")
    license_renewal_at: Optional[datetime] = None
    rate_limit_per_min: Optional[int] = Field(default=None, gt=0)
    usage_profile: Optional[dict] = None

    @field_validator("kind")
    @classmethod
    def _check_kind(cls, v: str) -> str:
        if v not in VALID_KINDS:
            raise ValueError(f"kind must be in {sorted(VALID_KINDS)}")
        return v

    @field_validator("license_status")
    @classmethod
    def _check_license(cls, v: str) -> str:
        if v not in VALID_LICENSE_STATUSES:
            raise ValueError(f"license_status must be in {sorted(VALID_LICENSE_STATUSES)}")
        return v


class PatchSourceBody(BaseModel):
    display_name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)
    active: Optional[bool] = None
    license_status: Optional[str] = None
    license_renewal_at: Optional[datetime] = None
    rate_limit_per_min: Optional[int] = Field(default=None, gt=0)
    usage_profile: Optional[dict] = None

    @field_validator("license_status")
    @classmethod
    def _check_license(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in VALID_LICENSE_STATUSES:
            raise ValueError(f"license_status must be in {sorted(VALID_LICENSE_STATUSES)}")
        return v


# ────────────────────────────────────────────────────────────────────
# Routes
# ────────────────────────────────────────────────────────────────────

@router.post("", status_code=201)
def register_source(
    body: RegisterSourceBody,
    user: dict = Depends(require_role("uploader")),
    db: Database = Depends(get_db),
):
    try:
        src = SourceRegistryService.register(
            db,
            source_id=body.source_id,
            display_name=body.display_name,
            tier=body.tier,
            kind=body.kind,
            base_url=body.base_url,
            description=body.description,
            license_status=body.license_status,
            license_renewal_at=body.license_renewal_at,
            rate_limit_per_min=body.rate_limit_per_min,
            usage_profile=body.usage_profile,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return src.to_dict()


@router.get("")
def list_sources(
    tier: Optional[int] = Query(default=None, ge=1, le=4),
    kind: Optional[str] = Query(default=None),
    active: Optional[bool] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    if kind is not None and kind not in VALID_KINDS:
        raise HTTPException(400, f"kind must be in {sorted(VALID_KINDS)}")
    try:
        sources = SourceRegistryService.list(
            db, tier=tier, kind=kind, active=active, limit=limit, offset=offset,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {
        "sources": [s.to_dict() for s in sources],
        "limit": limit, "offset": offset, "count": len(sources),
    }


# health-summary MUST come before /{source_id} so the path resolves correctly
@router.get("/health-summary")
def health_summary(
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    return SourceRegistryService.health_summary(db)


@router.get("/licences")
def list_licences(
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    """BE-25 — Licence health panel data (PB-807).

    Returns one row per source with annual_cost_usd / licence_type /
    renewal_at / health (active/expiring/expired) plus aggregate
    totals: ``total_today`` (everything currently in production) and
    ``projected_after_phase2`` (sum once phase=phase1+phase2 is on).

    Schema fields land via migration 070; pre-migration deployments
    return zeros so PB-807 still renders an empty state.
    """
    try:
        rows = db.fetch_all(
            """
            SELECT source_id, display_name, tier,
                   licence_type, license_status,
                   annual_cost_usd, license_renewal_at,
                   active, phase
              FROM sources
             ORDER BY annual_cost_usd DESC NULLS LAST, source_id
            """
        ) or []
    except Exception:
        logger.exception("list_licences: registry read failed; returning empty payload")
        rows = []

    items: list[dict] = []
    total_today = 0.0
    projected_after_phase2 = 0.0
    today = datetime.utcnow()

    for r in rows:
        cost = float(r["annual_cost_usd"]) if r.get("annual_cost_usd") is not None else 0.0
        renewal = r.get("license_renewal_at")
        status = r.get("license_status") or "not_applicable"
        # Health: active default; expired if past renewal; expiring if <60d.
        health = "active"
        if status in ("expired", "lapsed"):
            health = "expired"
        elif renewal and hasattr(renewal, "year"):
            days_left = (renewal - today).days
            if days_left < 0:
                health = "expired"
            elif days_left <= 60:
                health = "expiring"
        items.append({
            "source_id":         r.get("source_id"),
            "display_name":      r.get("display_name"),
            "tier":              r.get("tier"),
            "licence_type":      r.get("licence_type"),
            "license_status":    status,
            "annual_cost_usd":   cost,
            "license_renewal_at":
                renewal.isoformat() if renewal and hasattr(renewal, "isoformat") else None,
            "phase":             r.get("phase") or "now",
            "active":            bool(r.get("active") if r.get("active") is not None else True),
            "health":            health,
        })
        phase = (r.get("phase") or "now").lower()
        if phase in ("now", "phase1") and r.get("active") is not False:
            total_today += cost
        if phase in ("now", "phase1", "phase2"):
            projected_after_phase2 += cost

    return {
        "sources": items,
        "total_today": round(total_today, 2),
        "projected_after_phase2": round(projected_after_phase2, 2),
        "currency": "USD",
    }


@router.get("/{source_id}")
def get_source(
    source_id: str,
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    src = SourceRegistryService.get(db, source_id)
    if not src:
        raise HTTPException(404, f"source not found: {source_id}")
    return src.to_dict()


@router.patch("/{source_id}")
def patch_source(
    source_id: str,
    body: PatchSourceBody,
    user: dict = Depends(require_role("uploader")),
    db: Database = Depends(get_db),
):
    try:
        src = SourceRegistryService.update(
            db, source_id,
            display_name=body.display_name,
            description=body.description,
            active=body.active,
            license_status=body.license_status,
            license_renewal_at=body.license_renewal_at,
            rate_limit_per_min=body.rate_limit_per_min,
            usage_profile=body.usage_profile,
        )
    except SourceNotFound:
        raise HTTPException(404, f"source not found: {source_id}")
    except ValueError as e:
        raise HTTPException(400, str(e))
    return src.to_dict()


@router.get("/{source_id}/fair")
def source_fair(
    source_id: str,
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    """BE-24 — 5-dimension FAIR breakdown for PB-804 source detail.

    Per spec §8.3: coverage, latency, predictive_accuracy, stability,
    license_health. Reads from the source registry directly so no extra
    table is needed; missing dimensions surface as null + an explanation.
    """
    src = SourceRegistryService.get(db, source_id)
    if not src:
        raise HTTPException(404, f"source not found: {source_id}")
    d = src.to_dict()

    # Map registry fields to the 5 dimensions PB-804 renders. Each entry
    # has value (0..1 or null), weight (default contribution to composite),
    # explanation (one-line plain language).
    coverage = d.get("coverage_score")
    latency = d.get("latency_score")
    predictive = d.get("predictive_accuracy")
    stability = d.get("stability_score")
    license_health = d.get("license_health_score")

    fair = {
        "coverage": {
            "value": coverage, "weight": 0.25,
            "explanation": "fraction of expected entities present",
        },
        "latency": {
            "value": latency, "weight": 0.20,
            "explanation": "how quickly new records reach us after publication",
        },
        "predictive_accuracy": {
            "value": predictive, "weight": 0.20,
            "explanation": "historical hit rate from source contributions to correct predictions",
        },
        "stability": {
            "value": stability, "weight": 0.15,
            "explanation": "schema/payload-shape volatility over time",
        },
        "license_health": {
            "value": license_health, "weight": 0.20,
            "explanation": "renewal recency + cost-tier health",
        },
    }
    composite = d.get("fair_score") or d.get("quality_score")
    return {
        "source_id": source_id,
        "composite": composite,
        "by_dimension": fair,
    }


@router.get("/{source_id}/schema")
def source_schema(
    source_id: str,
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    """BE-24 — schema preview for PB-804: column types + 5 sample rows.

    Reads from the source registry's `schema_json` (column → type map)
    if present; samples are pulled from `source_samples` (5 most recent
    by retrieved_at) when that table exists. Missing data surfaces as
    empty arrays so the FE renders a "schema not yet captured"
    empty state instead of 500.
    """
    src = SourceRegistryService.get(db, source_id)
    if not src:
        raise HTTPException(404, f"source not found: {source_id}")

    columns: list[dict] = []
    raw_schema = (src.to_dict() or {}).get("schema_json") or {}
    if isinstance(raw_schema, dict):
        for col, col_type in raw_schema.items():
            columns.append({"name": str(col), "type": str(col_type)})

    samples: list[dict] = []
    try:
        rows = db.fetch_all(
            """
            SELECT sample_payload, retrieved_at
              FROM source_samples
             WHERE source_id = %s
             ORDER BY retrieved_at DESC
             LIMIT 5
            """,
            [source_id],
        ) or []
        for r in rows:
            samples.append({
                "payload":     r.get("sample_payload") or {},
                "retrieved_at": r["retrieved_at"].isoformat()
                                if r.get("retrieved_at") and hasattr(r["retrieved_at"], "isoformat")
                                else None,
            })
    except Exception:
        logger.debug("source_schema: source_samples unavailable")

    return {
        "source_id": source_id,
        "columns":   columns,
        "samples":   samples,
    }


@router.get("/{source_id}/history")
def source_history(
    source_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    # Verify source exists for nicer 404
    if not SourceRegistryService.get(db, source_id):
        raise HTTPException(404, f"source not found: {source_id}")
    try:
        history = SourceRegistryService.history(db, source_id, limit=limit)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"source_id": source_id, "history": history, "count": len(history)}


@router.post("/{source_id}/recompute", status_code=200)
def recompute_quality(
    source_id: str,
    user: dict = Depends(require_role("uploader")),
    db: Database = Depends(get_db),
):
    try:
        q = SourceRegistryService.recompute_quality(db, source_id)
    except SourceNotFound:
        raise HTTPException(404, f"source not found: {source_id}")
    return {"source_id": source_id, "quality": q.to_dict()}
