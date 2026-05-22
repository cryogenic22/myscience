"""Loop ② — per-entity KBQ living views endpoint.

GET /entities/{entity_type}/{entity_id}/kbq → the 8 KBQs answered for one
entity, with parity + completeness. Anonymous read (signals are readable
anonymously). The per-competitor dossier surface consumes this.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from api.deps import get_db
from db import Database
from services.kbq_views import build_entity_kbqs

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/entities", tags=["kbq"])


@router.get("/{entity_type}/{entity_id}/kbq")
def get_entity_kbqs(
    entity_type: str,
    entity_id: str,
    db: Database = Depends(get_db),
) -> dict:
    """Return the 8 KBQ views for an entity (parity structure + completeness)."""
    return build_entity_kbqs(db, entity_type, entity_id)
