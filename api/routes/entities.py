"""Entity lookup API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, HTTPException
from typing import Optional

from api.deps import get_db, get_graph
from db import Database
from services.graph import GraphTraversal, ENTITY_TABLE_MAP

router = APIRouter(prefix="/entities", tags=["entities"])

# Valid entity types
VALID_TYPES = set(ENTITY_TABLE_MAP.keys())


@router.get("/{entity_type}")
def list_entities(
    entity_type: str,
    search: Optional[str] = Query(None, description="Text search on label"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Database = Depends(get_db),
):
    """List entities of a given type with optional text search."""
    if entity_type not in VALID_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid entity type: {entity_type}")

    table, id_col, label_col, prop_cols = ENTITY_TABLE_MAP[entity_type]
    props_select = ", ".join(prop_cols) if prop_cols else ""
    props_clause = f", {props_select}" if props_select else ""

    conditions = []
    params = []

    if search:
        conditions.append(f"{label_col} ILIKE %s")
        params.append(f"%{search}%")

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.extend([limit, offset])

    rows = db.fetch_all(
        f"""
        SELECT {id_col} AS entity_id, {label_col} AS label{props_clause}
        FROM {table}
        {where}
        ORDER BY {label_col}
        LIMIT %s OFFSET %s
        """,
        params,
    )

    return {"entity_type": entity_type, "results": rows, "count": len(rows)}


@router.get("/{entity_type}/{entity_id}")
def get_entity(
    entity_type: str,
    entity_id: str,
    graph_svc: GraphTraversal = Depends(get_graph),
):
    """Get a single entity with full details and graph summary."""
    if entity_type not in VALID_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid entity type: {entity_type}")

    summary = graph_svc.entity_summary(entity_id, entity_type)
    if not summary.get("entity"):
        raise HTTPException(status_code=404, detail="Entity not found")

    return summary
