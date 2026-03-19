"""
QueryEngine: GraphRAG orchestration composing search + graph + metrics.

Answers complex pharma questions by combining vector search (find relevant
evidence), graph traversal (structural relationships), and pre-computed
metrics (quantified KPIs) into a single context package with provenance.

Usage:
    engine = QueryEngine(db, config, search, graph, metrics)
    result = engine.query("competitive landscape for GLP-1 agonists in obesity")
    dossier = engine.entity_dossier(drug_id, "drug")
    comparison = engine.compare_entities([drug_a, drug_b], "drug")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from services.search import HybridSearch, SearchResult
from services.graph import GraphTraversal
from services.metrics import PharmaMetrics

logger = logging.getLogger(__name__)


@dataclass
class EvidenceItem:
    """A single piece of evidence with provenance."""

    source: str          # "search", "graph", "metrics"
    entity_type: str
    entity_id: str
    content: str
    relevance: float     # 0-1
    provenance: dict = field(default_factory=dict)


@dataclass
class QueryResult:
    """Assembled result from a GraphRAG query."""

    question: str
    evidence: list[EvidenceItem] = field(default_factory=list)
    graph_context: dict = field(default_factory=dict)
    metrics_context: dict = field(default_factory=dict)
    entity_focus: list[dict] = field(default_factory=list)
    provenance_summary: dict = field(default_factory=dict)


# Maps entity types to metrics methods and their relevant parameters
ENTITY_METRICS_MAP = {
    "drug": ["drug_pipeline_strength", "trial_success_rate", "evidence_density"],
    "company": ["company_portfolio"],
}


class QueryEngine:
    """GraphRAG orchestration: search + graph + metrics → unified context."""

    def __init__(
        self,
        db,
        config,
        search: HybridSearch,
        graph: GraphTraversal,
        metrics: PharmaMetrics,
    ):
        self.db = db
        self.config = config
        self.search = search
        self.graph = graph
        self.metrics = metrics

    def query(
        self,
        question: str,
        entity_hints: Optional[list[str]] = None,
        focus_types: Optional[list[str]] = None,
        max_evidence: int = 15,
        include_graph: bool = True,
        include_metrics: bool = True,
    ) -> QueryResult:
        """Full GraphRAG query pipeline.

        1. Hybrid search across relevant entity types
        2. For top results, expand via graph traversal (1 hop)
        3. Pull relevant metrics for identified entities
        4. Package everything with provenance

        Args:
            question: Natural language query.
            entity_hints: Known entity names to resolve (e.g., ["semaglutide"]).
            focus_types: Entity types to search (default: all).
            max_evidence: Maximum evidence items to return.

        Returns:
            QueryResult with evidence, graph context, and metrics.
        """
        result = QueryResult(question=question)

        # Step 1: Hybrid search
        search_results = self.search.search(
            query=question,
            entity_types=focus_types,
            limit=max_evidence,
        )

        # Step 2: If entity hints provided, also resolve and search those
        if entity_hints:
            hint_results = self._resolve_entity_hints(entity_hints)
            # Merge hint results, deduplicating by entity_id
            seen_ids = {r.entity_id for r in search_results}
            for r in hint_results:
                if r.entity_id not in seen_ids:
                    search_results.append(r)
                    seen_ids.add(r.entity_id)

        # Convert search results to evidence items
        for sr in search_results[:max_evidence]:
            result.evidence.append(EvidenceItem(
                source="search",
                entity_type=sr.entity_type,
                entity_id=sr.entity_id,
                content=f"{sr.title}: {sr.snippet}" if sr.snippet != sr.title else sr.title,
                relevance=sr.similarity,
                provenance=sr.provenance,
            ))

        primary_entities = self._extract_primary_entities(search_results[:5])
        if include_graph:
            graph_nodes = {}
            graph_edges = []

            for entity in primary_entities:
                try:
                    subgraph = self.graph.neighborhood(
                        entity["entity_id"], entity["entity_type"]
                    )
                    for node in subgraph.nodes:
                        graph_nodes[node.entity_id] = {
                            "entity_id": node.entity_id,
                            "entity_type": node.entity_type,
                            "label": node.label,
                        }
                    for edge in subgraph.edges:
                        graph_edges.append({
                            "source": edge.source_id,
                            "target": edge.target_id,
                            "type": edge.link_type,
                            "confidence": edge.confidence,
                        })
                except Exception as e:
                    logger.warning("Graph expansion failed for %s: %s", entity["entity_id"], e)

            result.graph_context = {
                "nodes": list(graph_nodes.values()),
                "edges": graph_edges,
                "node_count": len(graph_nodes),
                "edge_count": len(graph_edges),
            }
        else:
            result.graph_context = {
                "nodes": [],
                "edges": [],
                "node_count": 0,
                "edge_count": 0,
            }

        if include_metrics:
            metrics_data = {}
            for entity in primary_entities:
                etype = entity["entity_type"]
                eid = entity["entity_id"]
                if etype in ENTITY_METRICS_MAP:
                    entity_metrics = self._get_entity_metrics(eid, etype)
                    if entity_metrics:
                        metrics_data[eid] = entity_metrics
            result.metrics_context = metrics_data
        else:
            result.metrics_context = {}

        result.entity_focus = primary_entities

        # Step 5: Provenance summary
        result.provenance_summary = self._build_provenance_summary(result.evidence)

        return result

    def entity_dossier(
        self,
        entity_id: str,
        entity_type: str,
    ) -> QueryResult:
        """Comprehensive dossier for a single entity.

        Combines: entity details, graph neighborhood, metrics, recent evidence.
        This is the "tell me everything about X" query.
        """
        result = QueryResult(question=f"Dossier for {entity_type} {entity_id}")

        # Entity summary from graph service
        summary = self.graph.entity_summary(entity_id, entity_type)
        entity_node = summary.get("entity")

        if entity_node:
            result.entity_focus = [{
                "entity_id": entity_node["entity_id"],
                "entity_type": entity_node["entity_type"],
                "label": entity_node["label"],
                "properties": entity_node.get("properties", {}),
            }]

        # Graph neighborhood (2 hops for dossier)
        try:
            subgraph = self.graph.traverse(entity_id, entity_type, hops=2, max_nodes=50)
            result.graph_context = {
                "nodes": [
                    {"entity_id": n.entity_id, "entity_type": n.entity_type, "label": n.label}
                    for n in subgraph.nodes
                ],
                "edges": [
                    {"source": e.source_id, "target": e.target_id,
                     "type": e.link_type, "confidence": e.confidence}
                    for e in subgraph.edges
                ],
                "node_count": len(subgraph.nodes),
                "edge_count": len(subgraph.edges),
                "connections_by_type": summary.get("connections_by_type", {}),
                "connections_by_entity_type": summary.get("connections_by_entity_type", {}),
                "total_connections": summary.get("total_connections", 0),
            }
        except Exception as e:
            logger.warning("Graph traversal failed for dossier: %s", e)

        # Metrics
        if entity_type in ENTITY_METRICS_MAP:
            entity_metrics = self._get_entity_metrics(entity_id, entity_type)
            if entity_metrics:
                result.metrics_context = {entity_id: entity_metrics}

        # Similar entities via vector search
        try:
            similar = self.search.find_similar(entity_id, entity_type, limit=5)
            for sr in similar:
                result.evidence.append(EvidenceItem(
                    source="search",
                    entity_type=sr.entity_type,
                    entity_id=sr.entity_id,
                    content=f"Similar {sr.entity_type}: {sr.title}",
                    relevance=sr.similarity,
                    provenance=sr.provenance,
                ))
        except Exception as e:
            logger.warning("Similar entity search failed: %s", e)

        # Recent related evidence (search by entity label)
        if entity_node:
            try:
                label = entity_node["label"]
                evidence_types = ["trial", "literature"]
                if entity_type in evidence_types:
                    evidence_types = [t for t in evidence_types if t != entity_type]
                evidence_results = self.search.search(
                    query=label,
                    entity_types=evidence_types,
                    limit=10,
                )
                for sr in evidence_results:
                    result.evidence.append(EvidenceItem(
                        source="search",
                        entity_type=sr.entity_type,
                        entity_id=sr.entity_id,
                        content=f"{sr.title}: {sr.snippet}" if sr.snippet and sr.snippet != sr.title else sr.title,
                        relevance=sr.similarity,
                        provenance=sr.provenance,
                    ))
            except Exception as e:
                logger.warning("Evidence search failed for dossier: %s", e)

        result.provenance_summary = self._build_provenance_summary(result.evidence)
        return result

    def compare_entities(
        self,
        entity_ids: list[str],
        entity_type: str,
    ) -> dict:
        """Side-by-side comparison of entities (e.g., two drugs).

        Returns:
            {
                "entities": [{entity details}],
                "metrics_comparison": {entity_id: {metrics}},
                "shared_connections": [{shared graph neighbors}],
                "unique_connections": {entity_id: [{unique neighbors}]},
            }
        """
        entities = []
        all_metrics = {}
        all_neighbors = {}  # entity_id -> set of connected entity_ids

        for eid in entity_ids:
            # Entity summary
            summary = self.graph.entity_summary(eid, entity_type)
            entity_node = summary.get("entity")
            if entity_node:
                entities.append({
                    **entity_node,
                    "connections_by_type": summary.get("connections_by_type", {}),
                    "total_connections": summary.get("total_connections", 0),
                })

            # Metrics
            if entity_type in ENTITY_METRICS_MAP:
                entity_metrics = self._get_entity_metrics(eid, entity_type)
                if entity_metrics:
                    all_metrics[eid] = entity_metrics

            # 1-hop neighbors for overlap analysis
            try:
                subgraph = self.graph.neighborhood(eid, entity_type)
                all_neighbors[eid] = {
                    n.entity_id: {"entity_id": n.entity_id, "entity_type": n.entity_type, "label": n.label}
                    for n in subgraph.nodes
                    if n.entity_id != eid
                }
            except Exception as e:
                logger.warning("Neighborhood fetch failed for %s: %s", eid, e)
                all_neighbors[eid] = {}

        # Find shared vs unique connections
        shared_ids = set()
        if len(entity_ids) >= 2:
            neighbor_sets = [set(all_neighbors.get(eid, {}).keys()) for eid in entity_ids]
            shared_ids = neighbor_sets[0]
            for ns in neighbor_sets[1:]:
                shared_ids = shared_ids & ns

        shared_connections = []
        for sid in shared_ids:
            # Use the first entity's neighbor info
            for eid in entity_ids:
                if sid in all_neighbors.get(eid, {}):
                    shared_connections.append(all_neighbors[eid][sid])
                    break

        unique_connections = {}
        for eid in entity_ids:
            unique_ids = set(all_neighbors.get(eid, {}).keys()) - shared_ids
            unique_connections[eid] = [
                all_neighbors[eid][uid] for uid in list(unique_ids)[:10]
            ]

        return {
            "entities": entities,
            "metrics_comparison": all_metrics,
            "shared_connections": shared_connections,
            "unique_connections": unique_connections,
        }

    # ---- Internal helpers ----

    def _resolve_entity_hints(self, hints: list[str]) -> list[SearchResult]:
        """Resolve entity name hints to search results."""
        all_results = []
        for hint in hints:
            results = self.search.search(
                query=hint,
                limit=3,
            )
            all_results.extend(results)
        return all_results

    def _extract_primary_entities(self, search_results: list[SearchResult]) -> list[dict]:
        """Extract unique primary entities from search results."""
        seen = set()
        entities = []
        for sr in search_results:
            if sr.entity_id not in seen:
                seen.add(sr.entity_id)
                entities.append({
                    "entity_id": sr.entity_id,
                    "entity_type": sr.entity_type,
                    "label": sr.title,
                })
        return entities

    def _resolve_id(self, entity_id: str, entity_type: str) -> str:
        """Resolve a name-based entity_id to a UUID using the graph service."""
        return self.graph._resolve_entity_id(entity_id, entity_type)

    def _get_entity_metrics(self, entity_id: str, entity_type: str) -> dict:
        """Fetch relevant metrics for an entity."""
        # Resolve name to UUID for materialized view lookups
        resolved_id = self._resolve_id(entity_id, entity_type)
        metrics_data = {}

        if entity_type == "drug":
            try:
                pipeline = self.metrics.drug_pipeline_strength(drug_id=resolved_id, limit=1)
                if pipeline:
                    metrics_data["pipeline"] = pipeline[0]
            except Exception as e:
                logger.debug("Pipeline metrics failed for %s: %s", entity_id, e)

            try:
                success = self.metrics.trial_success_rate(drug_id=resolved_id, limit=1)
                if success:
                    metrics_data["success_rate"] = success[0]
            except Exception as e:
                logger.debug("Success rate metrics failed for %s: %s", entity_id, e)

            try:
                evidence = self.metrics.evidence_density(drug_id=resolved_id, limit=1)
                if evidence:
                    metrics_data["evidence"] = evidence[0]
            except Exception as e:
                logger.debug("Evidence metrics failed for %s: %s", entity_id, e)

        elif entity_type == "company":
            try:
                portfolio = self.metrics.company_portfolio(company_id=resolved_id, limit=1)
                if portfolio:
                    metrics_data["portfolio"] = portfolio[0]
            except Exception as e:
                logger.debug("Portfolio metrics failed for %s: %s", entity_id, e)

        return metrics_data

    @staticmethod
    def _build_provenance_summary(evidence: list[EvidenceItem]) -> dict:
        """Summarize provenance across all evidence items."""
        sources = {}
        entity_types = {}
        for item in evidence:
            sources[item.source] = sources.get(item.source, 0) + 1
            entity_types[item.entity_type] = entity_types.get(item.entity_type, 0) + 1

        return {
            "total_evidence_items": len(evidence),
            "by_source": sources,
            "by_entity_type": entity_types,
        }
