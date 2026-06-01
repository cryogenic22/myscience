"""Loop A — Engagements CRUD API.

HTTP layer over the Z3/Z4/Z5 service modules (engagement, BCB, priority
matrix). Owner-scoped via the existing auth tiers — viewer can list/read,
uploader+ can create/mutate.

FSM violations map to 409 (the resource state precludes the operation),
not 400 (your input is bad). Missing resources map to 404. Validation
errors at the door (empty name, invalid situation, malformed body) map
to 400.

See specs/SPEC_A_engagements_api.md for the full contract.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.deps import get_db, require_role
from db import Database
from services.business_context_brief import (
    BCBContractError,
    create_bcb,
    get_bcb,
    get_bcb_for_engagement,
    sign_off_bcb,
)
from services.engagement import (
    Engagement,
    EngagementStatus,
    InvalidSituation,
    InvalidStageTransition,
    InvalidStatusTransition,
    LifecycleStage,
    advance_stage as _advance_stage,
    create_engagement,
    get_engagement,
    list_engagements,
    set_status as _set_status,
)
from services.priority_matrix import (
    DossierDomain,
    Priority,
    PriorityMatrix,
    PriorityMatrixError,
    default_matrix_for,
    get_priority_matrix,
    set_priority_matrix,
)
from services.dossier_kb import (
    EngagementNotFound,
    assemble_and_persist,
    get_latest_snapshot,
    list_snapshot_versions,
)
from services.scenarios import (
    assemble_and_persist as assemble_scenarios_and_persist,
    list_scenarios,
)
from services.insights import (
    assemble_and_persist_insights,
    list_engagement_synthesis,
)
from services.gap_remediation import (
    set_remediation as set_gap_remediation,
    list_remediations as list_gap_remediations,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["engagements"])


# ────────────────────────────────────────────────────────────────────
# Schemas
# ────────────────────────────────────────────────────────────────────


class CreateEngagementBody(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    asset: str = Field(min_length=1, max_length=200)
    situation: str  # validated by service layer (launch / defense / lcm)
    sponsor: Optional[str] = None
    workshop_date: Optional[str] = None  # ISO-8601 string; coerced server-side
    scope: Optional[dict] = None


class AdvanceStageBody(BaseModel):
    to_stage: str = Field(min_length=1)  # validated by service layer
    rationale: str = Field(min_length=1, max_length=2000)


class SetStatusBody(BaseModel):
    status: str  # draft / active / completed / archived
    rationale: Optional[str] = None


class StrategicDecisionIn(BaseModel):
    statement: str = Field(min_length=1, max_length=500)
    rationale: str = Field(min_length=1, max_length=2000)


class CompetitorThreatIn(BaseModel):
    entity_ref: str = Field(min_length=1, max_length=200)
    threat_level: str  # validated by service layer
    note: Optional[str] = ""


class CreateBCBBody(BaseModel):
    focal_asset: str = Field(min_length=1, max_length=200)
    situation: str
    strategic_decisions: list[StrategicDecisionIn] = Field(min_length=1)
    competitive_set: list[CompetitorThreatIn] = Field(default_factory=list)
    success_criteria: Optional[list[str]] = None
    constraints: Optional[list[str]] = None


class PriorityMatrixBody(BaseModel):
    cells: dict[str, str]  # domain → priority; service validates completeness


# ────────────────────────────────────────────────────────────────────
# Serialization helpers
# ────────────────────────────────────────────────────────────────────


def _iso(v: Any) -> Optional[str]:
    if v is None:
        return None
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return str(v)


def _engagement_to_dict(e: Engagement) -> dict:
    return {
        "id": e.id,
        "name": e.name,
        "asset": e.asset,
        "sponsor": e.sponsor,
        "situation": e.situation,
        "workshop_date": _iso(e.workshop_date),
        "stage": e.stage.value if hasattr(e.stage, "value") else str(e.stage),
        "status": e.status.value if hasattr(e.status, "value") else str(e.status),
        "scope": e.scope,
        "created_by": e.created_by,
        "created_at": _iso(e.created_at),
        "updated_at": _iso(e.updated_at),
        "tenant_scope": e.tenant_scope,
    }


def _bcb_to_dict(b) -> dict:
    return {
        "id": b.id,
        "engagement_id": b.engagement_id,
        "focal_asset": b.focal_asset,
        "situation": b.situation,
        "strategic_decisions": [
            {"statement": d.statement, "rationale": d.rationale}
            for d in b.strategic_decisions
        ],
        "competitive_set": [
            {"entity_ref": t.entity_ref, "threat_level": t.threat_level, "note": t.note}
            for t in b.competitive_set
        ],
        "success_criteria": list(b.success_criteria or []),
        "constraints": list(b.constraints or []),
        "created_by": b.created_by,
        "created_at": _iso(b.created_at),
        "signed_off": b.signed_off,
        "signed_off_by": b.signed_off_by,
        "signed_off_at": _iso(b.signed_off_at),
    }


def _matrix_to_dict(m: PriorityMatrix) -> dict:
    return {
        "bcb_id": m.bcb_id,
        "cells": {d.value: p.value for d, p in m.cells.items()},
    }


# ────────────────────────────────────────────────────────────────────
# Engagement CRUD
# ────────────────────────────────────────────────────────────────────


@router.post("/engagements", status_code=201)
def create(
    body: CreateEngagementBody,
    user: dict = Depends(require_role("uploader")),
    db: Database = Depends(get_db),
):
    try:
        eid = create_engagement(
            db,
            name=body.name,
            asset=body.asset,
            situation=body.situation,
            sponsor=body.sponsor,
            scope=body.scope,
            created_by=str(user["id"]),
        )
    except InvalidSituation as e:
        raise HTTPException(400, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        logger.exception("create_engagement failed")
        raise HTTPException(500, f"create failed: {e}") from e

    eng = get_engagement(db, eid)
    if not eng:
        raise HTTPException(500, "create succeeded but read-back failed")
    return _engagement_to_dict(eng)


@router.get("/engagements")
def list_all(
    status: Optional[str] = Query(default=None),
    situation: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    items = list_engagements(db, status=status, situation=situation, limit=limit)
    return {
        "engagements": [_engagement_to_dict(e) for e in items],
        "count": len(items),
    }


@router.get("/engagements/{eid}")
def get_one(
    eid: str,
    include_brief: bool = Query(default=False),
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    eng = get_engagement(db, eid)
    if not eng:
        raise HTTPException(404, f"engagement not found: {eid}")
    out = _engagement_to_dict(eng)
    if include_brief:
        bcb = get_bcb_for_engagement(db, eid)
        out["brief"] = _bcb_to_dict(bcb) if bcb else None
    return out


@router.post("/engagements/{eid}/advance")
def advance(
    eid: str,
    body: AdvanceStageBody,
    user: dict = Depends(require_role("uploader")),
    db: Database = Depends(get_db),
):
    # Confirm exists (so 404 takes precedence over 409 / 400).
    if not get_engagement(db, eid):
        raise HTTPException(404, f"engagement not found: {eid}")
    try:
        eng = _advance_stage(
            db, eid,
            to_stage=body.to_stage,
            rationale=body.rationale,
            actor=str(user["id"]),
        )
    except InvalidStageTransition as e:
        raise HTTPException(409, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return _engagement_to_dict(eng)


@router.patch("/engagements/{eid}/status")
def patch_status(
    eid: str,
    body: SetStatusBody,
    user: dict = Depends(require_role("uploader")),
    db: Database = Depends(get_db),
):
    if not get_engagement(db, eid):
        raise HTTPException(404, f"engagement not found: {eid}")
    try:
        # Note: rationale is accepted by the route for forward-compat /
        # audit-trail richness but the underlying service doesn't take it
        # yet. Logged at the route layer for now.
        if body.rationale:
            logger.info("status change rationale (eid=%s): %s",
                        eid, body.rationale)
        eng = _set_status(
            db, eid,
            to_status=body.status,
            actor=str(user["id"]),
        )
    except InvalidStatusTransition as e:
        raise HTTPException(409, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return _engagement_to_dict(eng)


# ────────────────────────────────────────────────────────────────────
# Business Context Brief (BCB)
# ────────────────────────────────────────────────────────────────────


@router.post("/engagements/{eid}/brief", status_code=201)
def create_brief(
    eid: str,
    body: CreateBCBBody,
    user: dict = Depends(require_role("uploader")),
    db: Database = Depends(get_db),
):
    if not get_engagement(db, eid):
        raise HTTPException(404, f"engagement not found: {eid}")
    try:
        bid = create_bcb(
            db,
            engagement_id=eid,
            focal_asset=body.focal_asset,
            situation=body.situation,
            strategic_decisions=[d.model_dump() for d in body.strategic_decisions],
            competitive_set=[t.model_dump() for t in body.competitive_set],
            success_criteria=body.success_criteria,
            constraints=body.constraints,
            created_by=str(user["id"]),
        )
    except BCBContractError as e:
        raise HTTPException(400, str(e)) from e
    bcb = get_bcb(db, bid)
    if not bcb:
        raise HTTPException(500, "BCB create succeeded but read-back failed")
    return _bcb_to_dict(bcb)


@router.get("/engagements/{eid}/brief")
def get_brief(
    eid: str,
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    if not get_engagement(db, eid):
        raise HTTPException(404, f"engagement not found: {eid}")
    bcb = get_bcb_for_engagement(db, eid)
    if not bcb:
        raise HTTPException(404, f"brief not found for engagement: {eid}")
    return _bcb_to_dict(bcb)


@router.post("/briefs/{bcb_id}/sign-off")
def signoff_brief(
    bcb_id: str,
    user: dict = Depends(require_role("uploader")),
    db: Database = Depends(get_db),
):
    if not get_bcb(db, bcb_id):
        raise HTTPException(404, f"brief not found: {bcb_id}")
    try:
        bcb = sign_off_bcb(db, bcb_id, by=str(user["id"]))
    except BCBContractError as e:
        raise HTTPException(409, str(e)) from e
    return _bcb_to_dict(bcb)


# ────────────────────────────────────────────────────────────────────
# Priority Matrix (lives on the BCB)
# ────────────────────────────────────────────────────────────────────


@router.put("/briefs/{bcb_id}/priority-matrix")
def put_matrix(
    bcb_id: str,
    body: PriorityMatrixBody,
    user: dict = Depends(require_role("uploader")),
    db: Database = Depends(get_db),
):
    if not get_bcb(db, bcb_id):
        raise HTTPException(404, f"brief not found: {bcb_id}")
    # Coerce string keys/values to enum domain.
    try:
        cells: dict[DossierDomain, Priority] = {
            DossierDomain(k): Priority(v) for k, v in body.cells.items()
        }
    except ValueError as e:
        raise HTTPException(400, f"invalid domain or priority: {e}") from e
    try:
        matrix = set_priority_matrix(db, bcb_id, cells)
    except PriorityMatrixError as e:
        raise HTTPException(400, str(e)) from e
    return _matrix_to_dict(matrix)


@router.get("/briefs/{bcb_id}/priority-matrix")
def fetch_matrix(
    bcb_id: str,
    fallback_default: bool = Query(
        default=False,
        description="If true and no matrix is set, return the situation default.",
    ),
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    bcb = get_bcb(db, bcb_id)
    if not bcb:
        raise HTTPException(404, f"brief not found: {bcb_id}")
    matrix = get_priority_matrix(db, bcb_id)
    if matrix is None and fallback_default:
        # Return the canonical default without persisting it.
        cells = default_matrix_for(bcb.situation)
        return _matrix_to_dict(PriorityMatrix(bcb_id=bcb_id, cells=cells))
    if matrix is None:
        raise HTTPException(404, f"priority matrix not set for brief {bcb_id}")
    return _matrix_to_dict(matrix)


# ────────────────────────────────────────────────────────────────────
# Dossier Knowledge Base (KB)
#
# The dossier stage, made durable. POST assembles a new VERSIONED snapshot
# from the facts ledger / signals / evidence; GET serves the current head
# (the 8-domain payload the EngagementDossierPage renders directly). Gaps
# surface thin domains so the sense layer knows what to collect next.
# ────────────────────────────────────────────────────────────────────


@router.post("/engagements/{eid}/dossier/assemble", status_code=201)
def assemble_dossier_endpoint(
    eid: str,
    user: dict = Depends(require_role("uploader")),
    db: Database = Depends(get_db),
):
    try:
        snapshot = assemble_and_persist(db, eid, assembled_by=str(user["id"]))
    except EngagementNotFound as e:
        raise HTTPException(404, f"engagement not found: {eid}") from e
    return snapshot.to_dict()


@router.get("/engagements/{eid}/dossier")
def get_dossier(
    eid: str,
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    if not get_engagement(db, eid):
        raise HTTPException(404, f"engagement not found: {eid}")
    snapshot = get_latest_snapshot(db, eid)
    if snapshot is None:
        raise HTTPException(404, f"no dossier assembled yet for engagement {eid}")
    return snapshot.to_dict()


@router.get("/engagements/{eid}/dossier/versions")
def list_dossier_versions(
    eid: str,
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    if not get_engagement(db, eid):
        raise HTTPException(404, f"engagement not found: {eid}")
    versions = list_snapshot_versions(db, eid)
    return {"versions": versions, "count": len(versions)}


@router.get("/engagements/{eid}/sources")
def get_engagement_sources(
    eid: str,
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    """UX07: per-source coverage for the engagement's latest dossier — which
    sources feed it, fact counts, domains touched, confidence-class mix."""
    if not get_engagement(db, eid):
        raise HTTPException(404, f"engagement not found: {eid}")
    snapshot = get_latest_snapshot(db, eid)
    if snapshot is None:
        raise HTTPException(404, f"no dossier assembled yet for engagement {eid}")
    sources = snapshot.source_coverage()
    return {
        "sources": sources,
        "source_count": len(sources),
        "total_facts": sum(s["fact_count"] for s in sources),
        "coverage_score": round(snapshot.coverage_score, 3),
    }


@router.get("/engagements/{eid}/dossier/gaps")
def get_dossier_gaps(
    eid: str,
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    if not get_engagement(db, eid):
        raise HTTPException(404, f"engagement not found: {eid}")
    snapshot = get_latest_snapshot(db, eid)
    if snapshot is None:
        raise HTTPException(404, f"no dossier assembled yet for engagement {eid}")
    return {
        "gaps": snapshot.gaps(),
        "coverage_score": round(snapshot.coverage_score, 3),
    }


# ── Gap remediation persistence (UX05b) ──


class GapRemediationBody(BaseModel):
    remediation: str
    note: Optional[str] = None


@router.get("/engagements/{eid}/gaps/remediations")
def get_gap_remediations(
    eid: str,
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    """The persisted remediation choices for an engagement's gaps,
    keyed by gap domain."""
    if not get_engagement(db, eid):
        raise HTTPException(404, f"engagement not found: {eid}")
    return {"remediations": list_gap_remediations(db, eid)}


@router.put("/engagements/{eid}/gaps/{gap_domain}/remediation")
def put_gap_remediation(
    eid: str,
    gap_domain: str,
    body: GapRemediationBody,
    user: dict = Depends(require_role("uploader")),
    db: Database = Depends(get_db),
):
    """Persist (upsert) the remediation choice for one gap domain."""
    if not get_engagement(db, eid):
        raise HTTPException(404, f"engagement not found: {eid}")
    try:
        return set_gap_remediation(
            db, eid, gap_domain, body.remediation,
            note=body.note, created_by=str(user["id"]))
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


# ── Scenarios (PB-H09): probabilistic futures derived from the dossier ──


@router.post("/engagements/{eid}/scenarios/assemble", status_code=201)
def assemble_scenarios_endpoint(
    eid: str,
    narrative: bool = Query(
        False,
        description="If true, synthesise a grounded decision_output per scenario "
                    "via LLM (PB-H16). No-op when the LLM is unconfigured.",
    ),
    user: dict = Depends(require_role("uploader")),
    db: Database = Depends(get_db),
):
    """Derive + persist scenarios for an engagement from its latest dossier
    (assembling one if none exists). Returns the live scenario set. With
    ?narrative=true, each scenario gets a fact-grounded decision_output."""
    synthesizer = get_llm() if narrative else None
    try:
        scenarios = assemble_scenarios_and_persist(
            db, eid, assembled_by=str(user["id"]), synthesizer=synthesizer)
    except EngagementNotFound as e:
        raise HTTPException(404, f"engagement not found: {eid}") from e
    return {"scenarios": [s.to_dict() for s in scenarios], "count": len(scenarios)}


@router.get("/engagements/{eid}/scenarios")
def get_scenarios(
    eid: str,
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    if not get_engagement(db, eid):
        raise HTTPException(404, f"engagement not found: {eid}")
    scenarios = list_scenarios(db, eid)
    return {"scenarios": [s.to_dict() for s in scenarios], "count": len(scenarios)}


# ── Synthesis (PB-UX06): typed insights derived from the dossier ──


@router.post("/engagements/{eid}/synthesis/assemble", status_code=201)
def assemble_synthesis_endpoint(
    eid: str,
    user: dict = Depends(require_role("uploader")),
    db: Database = Depends(get_db),
):
    """Derive + persist synthesis insights for an engagement from its latest
    dossier (assembling one if none exists). Each insight passes the synthesis
    test (>=1 fact citation, valid strategic frame); failures are logged to
    rejected_insights as the audit artifact. Returns the live synthesis set."""
    if not get_engagement(db, eid):
        raise HTTPException(404, f"engagement not found: {eid}")
    return assemble_and_persist_insights(db, eid, created_by=str(user["id"]))


@router.get("/engagements/{eid}/synthesis")
def get_synthesis(
    eid: str,
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    if not get_engagement(db, eid):
        raise HTTPException(404, f"engagement not found: {eid}")
    return list_engagement_synthesis(db, eid)
