"""BE-6 — Dossier composer endpoint."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from api.deps import get_db
from db import Database
from services.dossier import VALID_ENTITY_TYPES, compose_dossier

logger = logging.getLogger(__name__)

router = APIRouter(tags=["dossier"])


@router.get("/dossier-preview")
def dossier_preview(
    asset: str = Query(..., description="asset slug, e.g. 'drug:semaglutide' or 'semaglutide'"),
    db: Database = Depends(get_db),
):
    """IX-3: assemble an 8-domain dossier for any asset WITHOUT an engagement —
    the standalone 'build a dossier' light path. Ephemeral (not persisted);
    promote to a full engagement to keep it. Same engine as the engagement
    dossier stage."""
    from services.dossier_kb import assemble_dossier_for_asset
    try:
        snap = assemble_dossier_for_asset(db, asset)
    except Exception as e:
        logger.exception("dossier-preview failed for %s", asset)
        raise HTTPException(500, f"dossier preview failed: {e}") from e
    return snap.to_dict()


@router.get("/dossier/{entity_type}/{slug_or_id}")
def get_dossier(
    entity_type: str,
    slug_or_id: str,
    db: Database = Depends(get_db),
):
    """Single composer payload that PB-301..305 render without further
    backend calls. Accepts either a UUID or a slug-style name."""
    if entity_type not in VALID_ENTITY_TYPES:
        raise HTTPException(
            400,
            f"entity_type must be one of {VALID_ENTITY_TYPES}, got {entity_type!r}",
        )
    try:
        result = compose_dossier(db, entity_type=entity_type, slug_or_id=slug_or_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if result is None:
        raise HTTPException(404, f"{entity_type} not found: {slug_or_id}")
    return result.to_dict()
