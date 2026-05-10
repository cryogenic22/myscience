"""SPEC_035 — /ask graph-traversal API.

Endpoints:
  POST  /ask              viewer+
  GET   /ask/templates    viewer+
  GET   /ask/history      viewer+
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.deps import get_db, require_role
from db import Database
from services import ask_engine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ask", tags=["ask"])


class SubgraphContext(BaseModel):
    """BE-20 — optional selection from PB-701 'ask this subgraph'."""
    node_ids: Optional[list[str]] = None
    edge_types: Optional[list[str]] = None


class AskContext(BaseModel):
    subgraph: Optional[SubgraphContext] = None


class AskBody(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    context: Optional[AskContext] = None  # BE-20


@router.post("", status_code=200)
def ask(
    body: AskBody,
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    engine = ask_engine.AskEngine()
    subgraph_context = None
    if body.context and body.context.subgraph:
        subgraph_context = {
            "node_ids":   body.context.subgraph.node_ids or [],
            "edge_types": body.context.subgraph.edge_types or [],
        }
    try:
        result = engine.ask(
            db,
            question=body.question,
            user_id=str(user["id"]),
            subgraph_context=subgraph_context,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return result.to_dict()


@router.get("/templates")
def get_templates(
    user: dict = Depends(require_role("viewer")),
):
    return {"templates": ask_engine.list_templates()}


@router.get("/history")
def get_history(
    limit: int = Query(default=20, ge=1, le=50),
    user: dict = Depends(require_role("viewer")),
    db: Database = Depends(get_db),
):
    try:
        return {"history": ask_engine.list_history(db, user_id=str(user["id"]), limit=limit)}
    except ValueError as e:
        raise HTTPException(400, str(e))
