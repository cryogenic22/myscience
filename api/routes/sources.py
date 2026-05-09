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
