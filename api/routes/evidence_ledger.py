"""SPEC_024 — Evidence Ledger API.

Endpoints:
  POST   /claims                                      uploader+
  GET    /claims                                      viewer+
  GET    /claims/{claim_id}                           viewer+
  POST   /claims/{claim_id}/evidence                  uploader+
  GET    /evidence/{evidence_id}                      viewer+
  POST   /briefs/{brief_id}/evidence-snapshot         uploader+
  GET    /evidence-snapshots/{snapshot_hash}          viewer+

A Claim is a structured assertion about an entity. Evidence records back
claims and are append-only. Snapshots are content-addressed frozen views
of (claim → evidence) used to make Decisions reproducible.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from api.deps import get_db, require_role
from db import Database
from services.evidence_ledger import (
    AppendOnlyViolation,
    ClaimNotFound,
    EvidenceLedgerService,
    EvidenceNotFound,
    SnapshotNotFound,
    VALID_CLAIM_TYPES,
    VALID_ENTITY_TYPES,
    VALID_RELATIONS,
    MAX_CLAIM_TEXT_LEN,
    MAX_EXTRACTED_TEXT_LEN,
)

logger = logging.getLogger(__name__)

# Two routers — claims+evidence are at top-level, snapshots get a namespace.
claims_router = APIRouter(tags=["evidence-ledger"])
snapshots_router = APIRouter(prefix="/evidence-snapshots", tags=["evidence-ledger"])


# ────────────────────────────────────────────────────────────────────
# Request schemas
# ────────────────────────────────────────────────────────────────────

class CreateClaimBody(BaseModel):
    claim_text: str = Field(min_length=1, max_length=MAX_CLAIM_TEXT_LEN)
    claim_type: str = Field(default="other")
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)

    @field_validator("claim_type")
    @classmethod
    def _check_claim_type(cls, v: str) -> str:
        if v not in VALID_CLAIM_TYPES:
            raise ValueError(f"claim_type must be one of {sorted(VALID_CLAIM_TYPES)}")
        return v

    @field_validator("entity_type")
    @classmethod
    def _check_entity_type(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in VALID_ENTITY_TYPES:
            raise ValueError(f"entity_type must be one of {sorted(VALID_ENTITY_TYPES)} or null")
        return v


class AppendEvidenceBody(BaseModel):
    source_id: str = Field(min_length=1, max_length=200)
    extracted_text: str = Field(min_length=1, max_length=MAX_EXTRACTED_TEXT_LEN)
    retrieved_at: Optional[datetime] = None
    source_url: Optional[str] = Field(default=None, max_length=4000)
    extraction_method: Optional[dict] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    relation: str = Field(default="supports")

    @field_validator("relation")
    @classmethod
    def _check_relation(cls, v: str) -> str:
        if v not in VALID_RELATIONS:
            raise ValueError(f"relation must be one of {sorted(VALID_RELATIONS)}")
        return v


class CreateSnapshotBody(BaseModel):
    claim_ids: list[str] = Field(min_length=1, max_length=10000)
    decision_id: Optional[str] = None


# ────────────────────────────────────────────────────────────────────
# Claims routes
# ────────────────────────────────────────────────────────────────────

@claims_router.post("/claims", status_code=201)
def create_claim(
    body: CreateClaimBody,
    user: dict = Depends(require_role("uploader")),
    db: Database = Depends(get_db),
):
    """Create or return existing claim. Dedup on (text_hash, entity_type,
    entity_id) — same claim about the same entity returns existing claim_id
    (not a new one). Use 200 vs 201 to disambiguate."""
    try:
        claim = EvidenceLedgerService.upsert_claim(
            db,
            claim_text=body.claim_text,
            claim_type=body.claim_type,
            entity_type=body.entity_type,
            entity_id=body.entity_id,
            confidence=body.confidence,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return claim.to_dict()


@claims_router.get("/claims")
def list_claims(
    entity_type: Optional[str] = Query(default=None),
    entity_id: Optional[str] = Query(default=None),
    claim_type: Optional[str] = Query(default=None),
    text_query: Optional[str] = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    try:
        claims = EvidenceLedgerService.list_claims(
            db,
            entity_type=entity_type,
            entity_id=entity_id,
            claim_type=claim_type,
            text_query=text_query,
            limit=limit,
            offset=offset,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {
        "claims": [c.to_dict() for c in claims],
        "limit": limit,
        "offset": offset,
        "count": len(claims),
    }


@claims_router.get("/claims/{claim_id}")
def get_claim(
    claim_id: str,
    include_evidence: bool = Query(default=True),
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    claim = EvidenceLedgerService.get_claim(db, claim_id, include_evidence=include_evidence)
    if not claim:
        raise HTTPException(404, f"claim not found: {claim_id}")
    return claim.to_dict()


@claims_router.post("/claims/{claim_id}/evidence", status_code=201)
def append_evidence(
    claim_id: str,
    body: AppendEvidenceBody,
    user: dict = Depends(require_role("uploader")),
    db: Database = Depends(get_db),
):
    try:
        evidence = EvidenceLedgerService.append_evidence(
            db,
            claim_id,
            source_id=body.source_id,
            extracted_text=body.extracted_text,
            retrieved_at=body.retrieved_at,
            source_url=body.source_url,
            extraction_method=body.extraction_method,
            confidence=body.confidence,
            retrieved_by_user_id=str(user["id"]),
            relation=body.relation,
        )
    except ClaimNotFound:
        raise HTTPException(404, f"claim not found: {claim_id}")
    except ValueError as e:
        raise HTTPException(400, str(e))
    return evidence.to_dict()


@claims_router.get("/evidence/{evidence_id}")
def get_evidence(
    evidence_id: str,
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    evidence = EvidenceLedgerService.get_evidence(db, evidence_id)
    if not evidence:
        raise HTTPException(404, f"evidence not found: {evidence_id}")
    return evidence.to_dict()


# ────────────────────────────────────────────────────────────────────
# Snapshot routes
# ────────────────────────────────────────────────────────────────────

@claims_router.post("/briefs/{brief_id}/evidence-snapshot", status_code=201)
def snapshot_brief(
    brief_id: str,
    body: CreateSnapshotBody,
    user: dict = Depends(require_role("uploader")),
    db: Database = Depends(get_db),
):
    """Freeze the claims+evidence for a brief into an immutable snapshot.
    Idempotent — re-snapshotting the same set returns the same hash.

    The caller passes claim_ids explicitly rather than us walking
    `decision_briefs.evidence_refs` because:
      - Briefs may reference evidence by signal/document/kbq_view types
        that are not yet claim-shaped
      - Callers may want to snapshot a subset (e.g. only `claim`-typed refs)
    Frontend computes the claim_ids list from brief.evidence_refs filter."""
    try:
        snapshot = EvidenceLedgerService.snapshot_for_claims(
            db,
            claim_ids=body.claim_ids,
            brief_id=brief_id,
            decision_id=body.decision_id,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return snapshot.to_dict()


@snapshots_router.get("/{snapshot_hash}")
def get_snapshot(
    snapshot_hash: str,
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    try:
        snapshot = EvidenceLedgerService.get_snapshot(db, snapshot_hash)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not snapshot:
        raise HTTPException(404, f"snapshot not found: {snapshot_hash}")
    return snapshot.to_dict()
