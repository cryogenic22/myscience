"""Search API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from api.deps import get_search
from api.schemas import SearchRequest, SearchResponse, SearchResultItem
from api.utils import normalize_provenance
from services.search import HybridSearch

router = APIRouter(prefix="/search", tags=["search"])


def _to_response_item(sr) -> SearchResultItem:
    return SearchResultItem(
        entity_id=sr.entity_id,
        entity_type=sr.entity_type,
        title=sr.title,
        snippet=sr.snippet,
        similarity=sr.similarity,
        metadata=sr.metadata,
        provenance=normalize_provenance(sr.provenance, sr.entity_type, sr.entity_id),
        quality_score=sr.quality_score,
    )


@router.post("", response_model=SearchResponse)
def search(req: SearchRequest, svc: HybridSearch = Depends(get_search)):
    """Hybrid search: metadata filtering + vector similarity across entity types."""
    date_range = tuple(req.date_range) if req.date_range else None
    results, total = svc.search_paginated(
        query=req.query,
        entity_types=req.entity_types,
        filters=req.filters,
        date_range=date_range,
        offset=req.offset,
        limit=req.limit,
    )
    items = [_to_response_item(r) for r in results]
    return SearchResponse(results=items, total=total, limit=req.limit, offset=req.offset)


@router.get("/similar/{entity_type}/{entity_id}", response_model=SearchResponse)
def find_similar(
    entity_type: str,
    entity_id: str,
    limit: int = Query(10, ge=1, le=50),
    svc: HybridSearch = Depends(get_search),
):
    """Find entities similar to a given entity by embedding proximity."""
    results = svc.find_similar(entity_id, entity_type, limit=limit)
    items = [_to_response_item(r) for r in results]
    return SearchResponse(results=items, total=len(items), limit=limit, offset=0)
