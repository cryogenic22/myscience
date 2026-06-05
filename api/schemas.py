"""Pydantic request/response models for the Market-Zero API."""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


# ---- Request models ----

class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Natural language search query")
    entity_types: Optional[list[str]] = Field(None, description="Entity types to search")
    filters: Optional[dict] = Field(None, description="Metadata filters")
    date_range: Optional[list[str]] = Field(None, min_length=2, max_length=2)
    limit: int = Field(20, ge=1, le=100)
    offset: int = Field(0, ge=0, le=10000)


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, description="Natural language question")
    entity_hints: Optional[list[str]] = Field(None, description="Known entity names")
    focus_types: Optional[list[str]] = Field(None, description="Entity types to focus on")
    max_evidence: int = Field(15, ge=1, le=50)


class DossierRequest(BaseModel):
    entity_id: str = Field(..., description="Entity UUID")
    entity_type: str = Field(..., description="Entity type (drug, trial, company, etc.)")


class CompareRequest(BaseModel):
    entity_ids: list[str] = Field(..., min_length=2, max_length=10)
    entity_type: str


# ---- Response models ----

class SearchResultItem(BaseModel):
    entity_id: str
    entity_type: str
    title: str
    snippet: str
    similarity: float
    metadata: dict
    provenance: dict
    quality_score: Optional[float] = None


class SearchResponse(BaseModel):
    results: list[SearchResultItem]
    total: int
    limit: int = 20
    offset: int = 0


class EvidenceItemResponse(BaseModel):
    source: str
    entity_type: str
    entity_id: str
    content: str
    relevance: float
    provenance: dict


class QueryResponse(BaseModel):
    question: str
    evidence: list[EvidenceItemResponse]
    graph_context: dict
    metrics_context: dict
    entity_focus: list[dict]
    provenance_summary: dict


class EntityResponse(BaseModel):
    entity_id: str
    entity_type: str
    label: str
    properties: dict = Field(default_factory=dict)


class GraphNodeResponse(BaseModel):
    entity_id: str
    entity_type: str
    label: str


class GraphEdgeResponse(BaseModel):
    source_id: str
    target_id: str
    link_type: str
    confidence: float
    via: str = ""
    source: str = ""
    # D6 — edge provenance for citeable graph claims
    provenance_source: str = ""
    as_of: str = ""


class SubgraphResponse(BaseModel):
    nodes: list[GraphNodeResponse]
    edges: list[GraphEdgeResponse]
    center_entity_id: str
    node_count: int
    edge_count: int


class EntitySummaryResponse(BaseModel):
    entity: Optional[dict] = None
    connections_by_type: dict
    connections_by_entity_type: dict
    total_connections: int


class SourceCoverageItem(BaseModel):
    source: str
    records: int
    total_records: Optional[int] = None
    last_pull_records: Optional[int] = None
    last_retrieved: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    database: str
    tables: dict
    services: list[str]
    total_records: int = 0
    source_coverage: list[SourceCoverageItem] = Field(default_factory=list)
    last_updated: Optional[str] = None
