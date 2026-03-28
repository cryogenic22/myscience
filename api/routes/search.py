"""Search API routes."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query

from api.deps import get_db, get_search, get_graph, get_graph_analytics
from api.schemas import SearchRequest, SearchResponse, SearchResultItem
from api.utils import normalize_provenance
from db import Database
from services.graph import GraphTraversal
from services.graph_analytics import GraphAnalytics
from services.search import HybridSearch

logger = logging.getLogger(__name__)

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


# ── Typeahead suggestions ──

@router.get("/suggest")
def search_suggest(
    q: str = Query(..., min_length=2),
    limit: int = Query(8, ge=1, le=20),
    db: Database = Depends(get_db),
):
    """Typeahead suggestions using trigram similarity on entity labels."""
    try:
        rows = db.fetch_all(
            """SELECT entity_id, entity_type, label,
                      similarity(LOWER(label), LOWER(%s)) AS sim
               FROM v_entity_labels
               WHERE LOWER(label) %% %s
               ORDER BY sim DESC
               LIMIT %s""",
            [q, q, limit],
        )
    except Exception:
        # pg_trgm not available — fall back to ILIKE prefix match
        logger.debug("pg_trgm unavailable, falling back to ILIKE prefix match")
        rows = db.fetch_all(
            """SELECT entity_id, entity_type, label, 1.0 AS sim
               FROM v_entity_labels
               WHERE LOWER(label) LIKE LOWER(%s) || '%%'
               ORDER BY label
               LIMIT %s""",
            [q, limit],
        )

    suggestions = [
        {
            "entity_id": r["entity_id"],
            "entity_type": r["entity_type"],
            "label": r["label"],
            "similarity": float(r["sim"]),
        }
        for r in rows
    ]
    return {"suggestions": suggestions}


# ── Search with facets ──

def search_with_facets(
    query: str,
    entity_types: Optional[list[str]],
    filters: Optional[dict],
    date_range: Optional[tuple],
    limit: int,
    offset: int,
    search_svc: HybridSearch,
    db: Database,
) -> dict:
    """Run search and compute facet counts over the full result set.

    This is a helper called by both the POST /search/faceted endpoint and tests.
    Separated from the FastAPI route for testability.
    """
    results, total = search_svc.search_paginated(
        query=query,
        entity_types=entity_types,
        filters=filters,
        date_range=date_range,
        limit=limit,
        offset=offset,
    )

    # Compute entity_type facets from results
    entity_type_counts: dict[str, int] = {}
    drug_entity_ids: list[str] = []
    for r in results:
        et = r.entity_type
        entity_type_counts[et] = entity_type_counts.get(et, 0) + 1
        if et == "drug":
            drug_entity_ids.append(r.entity_id)

    facets: dict = {"entity_type": entity_type_counts}

    # Mechanism and TA facets for drug results
    if drug_entity_ids:
        try:
            mech_rows = db.fetch_all(
                """SELECT m.name, COUNT(*) AS cnt
                   FROM drugs d
                   JOIN mechanisms_of_action m ON m.id = d.mechanism_id
                   WHERE d.id::text = ANY(%s)
                   GROUP BY m.name
                   ORDER BY cnt DESC""",
                [drug_entity_ids],
            )
            facets["mechanism"] = {r["name"]: r["cnt"] for r in mech_rows}
        except Exception:
            facets["mechanism"] = {}

        try:
            ta_rows = db.fetch_all(
                """SELECT ta.name, COUNT(*) AS cnt
                   FROM entity_links el
                   JOIN therapeutic_areas ta ON ta.id::text = CASE
                       WHEN el.source_entity_type = 'therapeutic_area' THEN el.source_entity_id
                       ELSE el.target_entity_id END
                   WHERE (el.source_entity_id = ANY(%s) OR el.target_entity_id = ANY(%s))
                     AND (el.source_entity_type = 'therapeutic_area'
                          OR el.target_entity_type = 'therapeutic_area')
                   GROUP BY ta.name
                   ORDER BY cnt DESC""",
                [drug_entity_ids, drug_entity_ids],
            )
            facets["therapeutic_area"] = {r["name"]: r["cnt"] for r in ta_rows}
        except Exception:
            facets["therapeutic_area"] = {}

    items = [_to_response_item(r) for r in results]
    return {
        "results": [item.model_dump() for item in items],
        "total": total,
        "limit": limit,
        "offset": offset,
        "facets": facets,
    }


@router.post("/faceted")
def search_faceted(
    req: SearchRequest,
    svc: HybridSearch = Depends(get_search),
    db: Database = Depends(get_db),
):
    """Hybrid search with facet counts for entity_type, mechanism, and TA."""
    date_range = tuple(req.date_range) if req.date_range else None
    return search_with_facets(
        query=req.query,
        entity_types=req.entity_types,
        filters=req.filters,
        date_range=date_range,
        limit=req.limit,
        offset=req.offset,
        search_svc=svc,
        db=db,
    )


# ── Enriched search ──

_ENRICHMENT_CAP = 30  # Max results to graph-enrich per request


def search_enriched(
    body: dict,
    search_svc: HybridSearch = Depends(get_search),
    graph: GraphTraversal = Depends(get_graph),
    graph_analytics: GraphAnalytics = Depends(get_graph_analytics),
) -> dict:
    """Search with per-result graph enrichment (connection counts, influence)."""
    query = body.get("query", "")
    limit = min(body.get("limit", 20), _ENRICHMENT_CAP)
    entity_types = body.get("entity_types")
    filters = body.get("filters")

    results = search_svc.search(
        query=query,
        entity_types=entity_types,
        filters=filters,
        limit=limit,
    )

    # Cap at _ENRICHMENT_CAP to prevent slow graph queries
    results = results[:_ENRICHMENT_CAP]

    # Build influence lookup from batch centrality
    influence_map: dict[str, float] = {}
    try:
        # Collect entity types present in results for batch query
        result_types = {r.entity_type for r in results}
        for etype in result_types:
            centrality = graph_analytics.entity_centrality_batch(
                entity_type=etype, limit=100,
            )
            for entry in centrality:
                influence_map[entry["entity_id"]] = entry["influence"]
    except Exception as exc:
        logger.warning("Centrality batch failed: %s", exc)

    # Enrich each result with graph data
    enriched = []
    for r in results:
        try:
            summary = graph.entity_summary(r.entity_id, r.entity_type)
        except Exception:
            summary = {
                "entity": None,
                "connections_by_type": {},
                "connections_by_entity_type": {},
                "total_connections": 0,
            }

        enriched.append({
            "entity_id": r.entity_id,
            "entity_type": r.entity_type,
            "title": r.title,
            "snippet": r.snippet,
            "similarity": r.similarity,
            "metadata": r.metadata,
            "provenance": r.provenance,
            "quality_score": r.quality_score,
            "connection_counts": {
                "by_type": summary["connections_by_type"],
                "by_entity_type": summary["connections_by_entity_type"],
                "total_connections": summary["total_connections"],
            },
            "influence_score": influence_map.get(r.entity_id, 0.0),
        })

    return {"results": enriched, "total": len(enriched)}


@router.post("/enriched")
def search_enriched_endpoint(
    body: dict,
    search_svc: HybridSearch = Depends(get_search),
    graph: GraphTraversal = Depends(get_graph),
    graph_analytics: GraphAnalytics = Depends(get_graph_analytics),
):
    """Search with per-result graph enrichment (connection counts, influence)."""
    return search_enriched(
        body=body,
        search_svc=search_svc,
        graph=graph,
        graph_analytics=graph_analytics,
    )
