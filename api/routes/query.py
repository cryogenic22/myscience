"""Query engine (GraphRAG) API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.deps import get_query_engine
from api.schemas import (
    QueryRequest, DossierRequest, CompareRequest,
    QueryResponse, EvidenceItemResponse,
)
from services.query_engine import QueryEngine

router = APIRouter(prefix="/query", tags=["query"])


def _to_query_response(result) -> QueryResponse:
    return QueryResponse(
        question=result.question,
        evidence=[
            EvidenceItemResponse(
                source=e.source,
                entity_type=e.entity_type,
                entity_id=e.entity_id,
                content=e.content,
                relevance=e.relevance,
                provenance=e.provenance,
            )
            for e in result.evidence
        ],
        graph_context=result.graph_context,
        metrics_context=result.metrics_context,
        entity_focus=result.entity_focus,
        provenance_summary=result.provenance_summary,
    )


@router.post("", response_model=QueryResponse)
def query(req: QueryRequest, engine: QueryEngine = Depends(get_query_engine)):
    """Full GraphRAG query: search + graph + metrics composed into unified context."""
    result = engine.query(
        question=req.question,
        entity_hints=req.entity_hints,
        focus_types=req.focus_types,
        max_evidence=req.max_evidence,
    )
    return _to_query_response(result)


@router.post("/dossier", response_model=QueryResponse)
def dossier(req: DossierRequest, engine: QueryEngine = Depends(get_query_engine)):
    """Comprehensive dossier for a single entity."""
    result = engine.entity_dossier(req.entity_id, req.entity_type)
    return _to_query_response(result)


@router.post("/compare")
def compare(req: CompareRequest, engine: QueryEngine = Depends(get_query_engine)):
    """Side-by-side comparison of entities."""
    return engine.compare_entities(req.entity_ids, req.entity_type)
