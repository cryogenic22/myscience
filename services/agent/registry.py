"""Centralized, metadata-first tool registry for the agent harness."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ToolDefinition:
    """Metadata-first tool registration."""
    name: str
    version: str = "1.0.0"
    description: str = ""
    input_schema: dict = field(default_factory=dict)
    output_schema: dict = field(default_factory=dict)
    side_effects: str = "none"  # none | read | write | external
    trust_tier: str = "standard"  # public | standard | elevated | system
    timeout_ms: int = 5000
    retryable: bool = True
    tags: list[str] = field(default_factory=list)


class ToolRegistry:
    """Centralized, metadata-first tool registry."""

    def __init__(self):
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        """Register a tool. Overwrites if same name exists."""
        self._tools[tool.name] = tool
        logger.debug("Registered tool: %s (tier=%s, effects=%s)", tool.name, tool.trust_tier, tool.side_effects)

    def get(self, name: str) -> Optional[ToolDefinition]:
        """Get tool by name."""
        return self._tools.get(name)

    def get_by_tags(self, tags: list[str]) -> list[ToolDefinition]:
        """Get tools matching ANY of the given tags."""
        tag_set = set(tags)
        return [t for t in self._tools.values() if tag_set & set(t.tags)]

    def get_by_tier(self, max_tier: str) -> list[ToolDefinition]:
        """Get tools at or below the given trust tier."""
        tier_order = {"public": 0, "standard": 1, "elevated": 2, "system": 3}
        max_level = tier_order.get(max_tier, 1)
        return [t for t in self._tools.values() if tier_order.get(t.trust_tier, 1) <= max_level]

    def list_all(self) -> list[ToolDefinition]:
        """List all registered tools."""
        return list(self._tools.values())

    def count(self) -> int:
        return len(self._tools)


def create_default_registry() -> ToolRegistry:
    """Create a registry with all Market Zero tools pre-registered."""
    registry = ToolRegistry()

    # Agent query tools (read-only, used in chat)
    registry.register(ToolDefinition(
        name="graph_search",
        description="Search the knowledge graph for entity neighborhoods and paths. Use when the query involves relationships between entities.",
        side_effects="read",
        trust_tier="public",
        tags=["query", "graph", "search"],
    ))
    registry.register(ToolDefinition(
        name="metrics_query",
        description="Query pre-computed pharma metrics: pipeline strength, competitive landscape, evidence density. Use for quantitative questions about drug pipelines or market positioning.",
        side_effects="read",
        trust_tier="public",
        tags=["query", "metrics"],
    ))
    registry.register(ToolDefinition(
        name="rag_search",
        description="Semantic search across the knowledge base using pgvector embeddings. Use for finding similar entities or evidence by meaning, not exact keywords.",
        side_effects="read",
        trust_tier="public",
        tags=["query", "search", "semantic"],
    ))
    registry.register(ToolDefinition(
        name="sql_query",
        description="Execute read-only SQL queries against the database. Use for structured data retrieval when graph traversal or metrics are insufficient. Do NOT use for writes.",
        side_effects="read",
        trust_tier="standard",
        tags=["query", "sql", "structured"],
    ))

    # Data pipeline tools (write, used by steward/scheduler)
    registry.register(ToolDefinition(
        name="pipeline_run",
        description="Execute a data connector through the full ETL pipeline (fetch \u2192 normalize \u2192 resolve \u2192 embed \u2192 store). Use to refresh data from external sources.",
        side_effects="write",
        trust_tier="elevated",
        timeout_ms=300000,
        tags=["pipeline", "etl", "connector"],
    ))
    registry.register(ToolDefinition(
        name="source_refresh",
        description="Trigger a refresh of a specific data source connector. Runs in background.",
        side_effects="write",
        trust_tier="standard",
        tags=["pipeline", "connector", "refresh"],
    ))

    # Curation tools (write, used by steward)
    registry.register(ToolDefinition(
        name="steward_curate",
        description="Run the data steward curation loop: signal collection, quality checks, auto-fixes. Modifies entity records based on quality rules.",
        side_effects="write",
        trust_tier="standard",
        tags=["curation", "steward", "quality"],
    ))
    registry.register(ToolDefinition(
        name="entity_merge",
        description="Merge two duplicate entity records into one canonical record. Destructive: the merged record is marked as 'merged' status.",
        side_effects="write",
        trust_tier="elevated",
        tags=["curation", "dedup", "merge"],
    ))
    registry.register(ToolDefinition(
        name="entity_exclude",
        description="Mark an entity record as excluded (garbage data). The record remains but is hidden from search and browse.",
        side_effects="write",
        trust_tier="standard",
        tags=["curation", "cleanup"],
    ))
    registry.register(ToolDefinition(
        name="mv_refresh",
        description="Refresh all materialized views (pipeline strength, company portfolio, etc). Rebuilds cached aggregations.",
        side_effects="write",
        trust_tier="standard",
        tags=["maintenance", "cache"],
    ))

    # Analysis tools (read, used in chat/research)
    registry.register(ToolDefinition(
        name="entity_influence",
        description="Compute influence score for an entity using PageRank-inspired algorithm on the knowledge graph.",
        side_effects="read",
        trust_tier="public",
        tags=["analytics", "graph", "influence"],
    ))
    registry.register(ToolDefinition(
        name="competitive_clusters",
        description="Detect competitive clusters in a therapeutic area using mechanism-based grouping and HHI concentration index.",
        side_effects="read",
        trust_tier="public",
        tags=["analytics", "competitive", "landscape"],
    ))
    registry.register(ToolDefinition(
        name="fair_score",
        description="Compute FAIR quality score for an entity or the entire knowledge base. Returns completeness, link density, source diversity, freshness, resolution dimensions.",
        side_effects="read",
        trust_tier="public",
        tags=["quality", "fair", "scoring"],
    ))

    return registry
