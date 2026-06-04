"""Loop ② — per-entity KBQ living views endpoint.

GET /entities/{entity_type}/{entity_id}/kbq → the 8 KBQs answered for one
entity, with parity + completeness. Anonymous read (signals are readable
anonymously). The per-competitor dossier surface consumes this.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query

from api.deps import get_db
from db import Database
from services.kbq_views import build_entity_kbqs, build_entity_kbqs_for_asset

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/entities", tags=["kbq"])

# PB-SL10 — the by-asset query surface lives on its OWN mount, NOT under
# /entities. The entities router defines GET /entities/{entity_type}, which would
# SHADOW a 2-segment /entities/kbq (capturing entity_type="kbq"). A dedicated
# /kbq mount is unambiguous regardless of router registration order.
asset_router = APIRouter(prefix="/kbq", tags=["kbq"])


@asset_router.get("")
def get_kbqs_by_asset(
    asset: str = Query(..., description="asset slug, e.g. 'semaglutide' or 'drug:wegovy'"),
    db: Database = Depends(get_db),
) -> dict:
    """PB-SL10 — KBQ-as-query-surface.

    Resolve a typed asset to its canonical entity (richness-ranked, the same
    resolver the dossier uses) and return the 8 KBQ views. This is the backend
    for the cockpit's KBQ query surface: type an asset → get the questions
    answered, each item drillable to its signal + evidence.
    """
    return build_entity_kbqs_for_asset(db, asset)


@router.get("/{entity_type}/{entity_id}/kbq")
def get_entity_kbqs(
    entity_type: str,
    entity_id: str,
    db: Database = Depends(get_db),
) -> dict:
    """Return the 8 KBQ views for an entity (parity structure + completeness)."""
    return build_entity_kbqs(db, entity_type, entity_id)
