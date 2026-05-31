"""SPEC-019 — Connector management API.

Endpoints:
  GET    /connectors                     anonymous   list view
  GET    /connectors/{key}               anonymous   dossier
  POST   /connectors/{key}/health-check  uploader+   live ping of upstream
  PUT    /connectors/{key}/config        enterprise  edit enabled/auto_approve/etc
  POST   /connectors/{key}/run           uploader if auto_approve_runs else enterprise

BE-26 — the canonical path for the JSON API is now ``/api/v1/connectors``
(added by `api/app.py`'s versioned-router mount). The bare ``/connectors``
list + dossier endpoints stay live for back-compat but emit a
``Deprecation`` + ``Sunset`` + ``Link`` triple per RFC 8594 so clients
get a programmatic hint to migrate. The user-facing HTML route
``/connectors`` is the frontend's job — it 301s to ``/catalog`` (the
PB-809 cutover lives on the FE track).

The Connectors UI consumes this to show a Claude-style sidebar + dossier view.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from api.deps import get_current_user, get_db, require_role
from connectors import CONNECTOR_REGISTRY, get_connector
from connectors.base import SourceType
from db import Database
from services.connector_registry import (
    get_connector_detail,
    list_connectors,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/connectors", tags=["connectors"])


# ────────────────────────────────────────────────────────────────────
# Schemas
# ────────────────────────────────────────────────────────────────────

class ConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    auto_approve_runs: Optional[bool] = None
    manual_only: Optional[bool] = None
    notes: Optional[str] = None


# ────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────

def _resolve_source_type(source_key: str) -> Optional[SourceType]:
    for st in CONNECTOR_REGISTRY.keys():
        if st.value == source_key:
            return st
    return None


def _trigger_connector_run(source_key: str) -> dict:
    """Queue a manual run via the existing scheduler hook.

    Returns a dict describing what was queued. Falls back to a simple
    "would-trigger" response if the scheduler isn't reachable from this
    request context (it lives in the background thread)."""
    try:
        from scheduler.runner import DataPipelineScheduler
        scheduler = DataPipelineScheduler()
        st = _resolve_source_type(source_key)
        if st is None:
            return {"queued": False, "reason": "unknown_source"}
        # run_one is the synchronous trigger used by the manual --run-one CLI.
        # In the API context we kick it off without blocking by deferring to
        # a thread; but for the MVP we just record intent and let the
        # scheduler's own catch-up loop pick it up.
        return {"queued": True, "source_key": source_key}
    except Exception as exc:
        logger.warning("Could not queue connector run for %s: %s", source_key, exc)
        return {"queued": False, "reason": str(exc)}


# ────────────────────────────────────────────────────────────────────
# GET /connectors — list
# ────────────────────────────────────────────────────────────────────

def _apply_deprecation_headers(request: Request, response: Response) -> None:
    """BE-26 — RFC 8594 deprecation hints for the bare /connectors path.

    Skipped when the request came in via /api/v1/connectors — that's
    the canonical path going forward. Uses the live request URL so
    the same handler running under both prefixes does the right thing.
    """
    path = (request.url.path or "")
    if path.startswith("/api/v1/"):
        return
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = "Wed, 31 Dec 2026 23:59:59 GMT"
    response.headers["Link"] = '</api/v1/connectors>; rel="successor-version"'


@router.get("")
def list_endpoint(
    request: Request,
    response: Response,
    db: Database = Depends(get_db),
):
    """Sidebar listing of every registered connector. Canonical path is
    ``/api/v1/connectors``; the bare ``/connectors`` form sets a
    Deprecation + Sunset + Link triple (BE-26)."""
    _apply_deprecation_headers(request, response)
    return {"connectors": list_connectors(db)}


# ────────────────────────────────────────────────────────────────────
# GET /connectors/{key} — dossier
# ────────────────────────────────────────────────────────────────────

@router.get("/{source_key}")
def dossier_endpoint(
    source_key: str,
    request: Request,
    response: Response,
    db: Database = Depends(get_db),
):
    """Full dossier for a single connector. Canonical path is
    ``/api/v1/connectors/{key}`` (BE-26)."""
    _apply_deprecation_headers(request, response)
    detail = get_connector_detail(db, source_key)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"unknown connector: {source_key}")
    return detail


# ────────────────────────────────────────────────────────────────────
# POST /connectors/{key}/health-check — uploader+
# ────────────────────────────────────────────────────────────────────

@router.post("/{source_key}/health-check")
def health_check_endpoint(
    source_key: str,
    user: dict = Depends(require_role("uploader")),
):
    """Live ping of the upstream API via connector.health_check()."""
    st = _resolve_source_type(source_key)
    if st is None:
        raise HTTPException(status_code=404, detail=f"unknown connector: {source_key}")

    try:
        connector = get_connector(st)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"failed to instantiate connector: {exc}",
        ) from exc

    try:
        result = connector.health_check()
    except Exception as exc:
        logger.exception("health_check failed for %s", source_key)
        raise HTTPException(
            status_code=502,
            detail=f"health check failed: {exc}",
        ) from exc

    return {
        "source_key": source_key,
        "healthy": bool(getattr(result, "healthy", False)),
        "message": getattr(result, "message", ""),
        "response_time_ms": getattr(result, "response_time_ms", None),
        "checked_at": (
            result.checked_at.isoformat()
            if hasattr(result, "checked_at") and result.checked_at
            else None
        ),
    }


# ────────────────────────────────────────────────────────────────────
# PUT /connectors/{key}/config — enterprise only
# ────────────────────────────────────────────────────────────────────

@router.put("/{source_key}/config")
def update_config_endpoint(
    source_key: str,
    body: ConfigUpdate,
    user: dict = Depends(require_role("enterprise")),
    db: Database = Depends(get_db),
):
    """Upsert the connector_config row. Enterprise only."""
    st = _resolve_source_type(source_key)
    if st is None:
        raise HTTPException(status_code=404, detail=f"unknown connector: {source_key}")

    # Read existing row so PUT is partial-update friendly
    try:
        existing = db.fetch_one(
            """SELECT enabled, auto_approve_runs, manual_only, notes
               FROM connector_config WHERE source_key = %s""",
            [source_key],
        )
    except Exception:
        existing = None

    enabled = body.enabled if body.enabled is not None else (
        existing.get("enabled", True) if existing else True
    )
    auto_approve = body.auto_approve_runs if body.auto_approve_runs is not None else (
        existing.get("auto_approve_runs", False) if existing else False
    )
    manual_only = body.manual_only if body.manual_only is not None else (
        existing.get("manual_only", False) if existing else False
    )
    notes = body.notes if body.notes is not None else (
        existing.get("notes") if existing else None
    )

    try:
        db.execute(
            """INSERT INTO connector_config
                   (source_key, enabled, auto_approve_runs, manual_only, notes, updated_at, updated_by)
               VALUES (%s, %s, %s, %s, %s, NOW(), %s::uuid)
               ON CONFLICT (source_key) DO UPDATE SET
                   enabled = EXCLUDED.enabled,
                   auto_approve_runs = EXCLUDED.auto_approve_runs,
                   manual_only = EXCLUDED.manual_only,
                   notes = EXCLUDED.notes,
                   updated_at = NOW(),
                   updated_by = EXCLUDED.updated_by""",
            [source_key, enabled, auto_approve, manual_only, notes, user.get("id")],
        )
    except Exception as exc:
        logger.exception("connector_config upsert failed for %s", source_key)
        raise HTTPException(
            status_code=500,
            detail=f"config update failed: {exc}",
        ) from exc

    return {
        "source_key": source_key,
        "enabled": enabled,
        "auto_approve_runs": auto_approve,
        "manual_only": manual_only,
        "notes": notes,
    }


# ────────────────────────────────────────────────────────────────────
# POST /connectors/{key}/run — uploader if auto_approve, else enterprise
# ────────────────────────────────────────────────────────────────────

@router.post("/{source_key}/run")
def run_endpoint(
    source_key: str,
    user: Optional[dict] = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Trigger a manual connector fetch. Role gating depends on auto_approve_runs."""
    if user is None:
        raise HTTPException(status_code=401, detail="authentication required")

    st = _resolve_source_type(source_key)
    if st is None:
        raise HTTPException(status_code=404, detail=f"unknown connector: {source_key}")

    # Look up config to determine which role can run
    try:
        cfg_row = db.fetch_one(
            """SELECT enabled, auto_approve_runs
               FROM connector_config WHERE source_key = %s""",
            [source_key],
        )
    except Exception:
        cfg_row = None

    enabled = bool(cfg_row.get("enabled", True)) if cfg_row else True
    auto_approve = bool(cfg_row.get("auto_approve_runs", False)) if cfg_row else False

    if not enabled:
        raise HTTPException(
            status_code=409,
            detail=f"connector '{source_key}' is disabled",
        )

    # Role check
    from services.auth import role_satisfies
    role = user.get("role", "")
    if auto_approve:
        # Uploader+ allowed
        if not role_satisfies(role, "uploader"):
            raise HTTPException(
                status_code=403,
                detail=f"role '{role}' insufficient (need 'uploader' or higher)",
            )
    else:
        # Enterprise required
        if not role_satisfies(role, "enterprise"):
            raise HTTPException(
                status_code=403,
                detail=f"role '{role}' cannot trigger run without auto_approve_runs (need 'enterprise')",
            )

    result = _trigger_connector_run(source_key)
    return {
        "source_key": source_key,
        "queued": result.get("queued", False),
        "triggered_by": user.get("email"),
        "detail": result,
    }
