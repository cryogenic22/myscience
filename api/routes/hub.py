"""DataHub D-API-1 (docs/SPEC_DATA_HUB.md §5.1, COORDINATION §7.3) — REST surface
over the L2 connector-taxonomy + onboarding service.

The L2 service (`services/connector_taxonomy.py`, #245) holds the taxonomy + the
onboarding state machine but had no HTTP surface, so the frontend Connect wizard
(F5) had nothing to call. This router exposes it under `/hub`, a new namespace
(the `api/` layer is Platform's lane — this is purely additive, touches no
existing route, and needs no migration).

Endpoints:
  GET  /hub/connector-types                     viewer+   list the taxonomy
  GET  /hub/connector-types/{name}              viewer+   one type (404 if unknown)
  GET  /hub/onboarding                           viewer+   list (optional ?status=)
  GET  /hub/onboarding/{source_id}               viewer+   one record (404 if none)
  POST /hub/onboarding/{source_id}               uploader+ start onboarding (draft)
  POST /hub/onboarding/{source_id}/advance       uploader+ move through the lifecycle

Status mapping: UnknownConnectorType → 400, InvalidTransition → 400,
OnboardingNotFound → 404, unknown source → 404 (a cheap existence probe so the
wizard gets a clean error instead of a raw FK violation).
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from api.deps import get_db, require_role
from db import Database
from connectors.spec import ConnectorSpec
from services.connector_taxonomy import (
    INITIAL_STATUS,
    ONBOARDING_STATUSES,
    InvalidTransition,
    OnboardingNotFound,
    UnknownConnectorType,
    advance_onboarding,
    get_connector_type,
    get_onboarding,
    list_connector_types,
    list_onboarding,
    set_onboarding_contract,
    start_onboarding,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/hub", tags=["datahub"])


# ────────────────────────────────────────────────────────────────────
# Request schemas
# ────────────────────────────────────────────────────────────────────

class StartOnboardingBody(BaseModel):
    owner: Optional[str] = Field(default=None, max_length=200)
    contact: Optional[str] = Field(default=None, max_length=200)
    connector_type: Optional[str] = Field(default=None, max_length=50)
    go_live_date: Optional[date] = None
    escalation: Optional[str] = Field(default=None, max_length=500)
    # Connector contract (099) — all optional + back-compatible. When any contract
    # field is present the body is validated as a ConnectorSpec (lint) before it is
    # persisted, so a malformed connector fails closed with clear errors.
    record_type: Optional[str] = Field(default=None, max_length=50)
    config: Optional[dict] = None
    field_mappings: Optional[list] = None
    trust_tier: Optional[int] = Field(default=None, ge=1, le=3)
    must_capture: Optional[list[str]] = None
    license: Optional[str] = Field(default=None, max_length=200)
    cadence: Optional[dict] = None


class AdvanceOnboardingBody(BaseModel):
    to_status: str = Field(min_length=1, max_length=50)

    @field_validator("to_status")
    @classmethod
    def _check_status(cls, v: str) -> str:
        if v not in ONBOARDING_STATUSES:
            raise ValueError(f"to_status must be one of {list(ONBOARDING_STATUSES)}")
        return v


def _source_exists(db, source_id: str) -> bool:
    """Cheap existence probe so onboarding-start returns a clean 404 instead of a
    raw FK violation when the source was never registered."""
    return db.fetch_one(
        "SELECT 1 FROM sources WHERE source_id = %s", (source_id,)
    ) is not None


# ────────────────────────────────────────────────────────────────────
# Connector-type taxonomy
# ────────────────────────────────────────────────────────────────────

@router.get("/connector-types")
def list_connector_types_route(
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    types = list_connector_types(db)
    return {"connector_types": [t.to_dict() for t in types], "count": len(types)}


@router.get("/connector-types/{name}")
def get_connector_type_route(
    name: str,
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    ct = get_connector_type(db, name)
    if ct is None:
        raise HTTPException(404, f"unknown connector_type: {name}")
    return ct.to_dict()


# ────────────────────────────────────────────────────────────────────
# Onboarding lifecycle
# ────────────────────────────────────────────────────────────────────

@router.get("/onboarding")
def list_onboarding_route(
    status: Optional[str] = Query(default=None),
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    try:
        records = list_onboarding(db, status=status)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"onboarding": [r.to_dict() for r in records], "count": len(records)}


@router.get("/onboarding/{source_id}")
def get_onboarding_route(
    source_id: str,
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    rec = get_onboarding(db, source_id)
    if rec is None:
        raise HTTPException(404, f"no onboarding record for source: {source_id}")
    return rec.to_dict()


@router.post("/onboarding/{source_id}", status_code=201)
def start_onboarding_route(
    source_id: str,
    body: StartOnboardingBody,
    user: dict = Depends(require_role("uploader")),
    db: Database = Depends(get_db),
):
    src = db.fetch_one(
        "SELECT display_name FROM sources WHERE source_id = %s", (source_id,)
    )
    if not src:
        raise HTTPException(404, f"source not found: {source_id} (register it first)")

    # A full contract (config/mappings/record_type/…) is validated as a
    # ConnectorSpec before anything is written — fail closed on a bad connector.
    has_contract = any(
        v is not None for v in (body.record_type, body.config, body.trust_tier, body.license)
    ) or bool(body.field_mappings) or bool(body.must_capture)
    if has_contract:
        issues = ConnectorSpec(
            source_id=source_id,
            source_name=src["display_name"],
            connector_type=body.connector_type or "",
            record_type=body.record_type or "",
            config=body.config or {},
            trust_tier=body.trust_tier,
            must_capture=body.must_capture or [],
            license=body.license,
            cadence=body.cadence,
        ).lint()
        if issues:
            raise HTTPException(422, {"errors": issues})

    try:
        rec = start_onboarding(
            db, source_id,
            owner=body.owner,
            contact=body.contact,
            connector_type=body.connector_type,
            go_live_date=body.go_live_date,
            escalation=body.escalation,
        )
    except UnknownConnectorType as e:
        raise HTTPException(400, str(e))

    if has_contract:
        rec = set_onboarding_contract(
            db, source_id,
            record_type=body.record_type,
            config=body.config,
            field_mappings=body.field_mappings,
            trust_tier=body.trust_tier,
            must_capture=body.must_capture,
            license=body.license,
            cadence=body.cadence,
        )
    return rec.to_dict()


@router.post("/onboarding/{source_id}/advance")
def advance_onboarding_route(
    source_id: str,
    body: AdvanceOnboardingBody,
    user: dict = Depends(require_role("uploader")),
    db: Database = Depends(get_db),
):
    try:
        rec = advance_onboarding(db, source_id, body.to_status)
    except OnboardingNotFound:
        raise HTTPException(
            404, f"no onboarding record for source: {source_id} "
            f"(POST /hub/onboarding/{source_id} to start it in {INITIAL_STATUS!r})"
        )
    except InvalidTransition as e:
        raise HTTPException(400, str(e))
    return rec.to_dict()
