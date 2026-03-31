"""
GraphTraversal: Navigate the entity_links knowledge graph via SQL.

Provides N-hop traversal, path finding, and rich entity summaries using
recursive CTEs on the entity_links table. No external graph database needed.

Usage:
    graph = GraphTraversal(db, config)
    subgraph = graph.traverse(drug_id, "drug", hops=2)
    summary = graph.entity_summary(drug_id, "drug")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class GraphNode:
    """A node in the knowledge graph."""

    entity_id: str
    entity_type: str
    label: str
    properties: dict = field(default_factory=dict)


@dataclass
class GraphEdge:
    """A directed edge in the knowledge graph."""

    source_id: str
    target_id: str
    link_type: str
    confidence: float = 1.0
    via: str = ""
    source: str = ""


@dataclass
class Subgraph:
    """A subgraph extracted from traversal."""

    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)
    center_entity_id: str = ""
    hops: int = 0


# Entity type -> (table, id_column, label_column, key_properties)
ENTITY_TABLE_MAP = {
    "drug": ("drugs", "id::text", "generic_name", ["brand_name", "approval_date", "supply_status", "canonical_smiles", "molecular_formula", "molecular_weight", "pubchem_cid", "mechanism_id"]),
    "company": ("companies", "id::text", "name", ["ticker", "cik", "country"]),
    "trial": ("clinical_trials", "id", "COALESCE(official_title, id)", ["phase", "status", "sponsor_name", "start_date"]),
    "literature": ("pubmed_articles", "id::text", "title", ["pmid", "journal", "publication_date"]),
    "event": ("market_events", "id::text", "LEFT(description, 100)", ["event_type", "event_date", "impact_score"]),
    "therapeutic_area": ("therapeutic_areas", "id::text", "name", ["mesh_id"]),
    "mechanism": ("mechanisms_of_action", "id::text", "name", ["mesh_id"]),
    "investigator": ("investigators", "id::text", "name", ["orcid", "affiliation", "affiliation_country"]),
    "patent": ("patents", "id::text", "patent_number", ["patent_type", "patent_expiry_date", "applicant_holder"]),
    "biomarker": ("biomarkers", "id::text", "name", ["abbreviation", "category", "unit", "clinical_significance"]),
    "adverse_event": ("adverse_events", "id::text", "COALESCE(drug_name, '') || ' - ' || COALESCE(reaction, '')", ["outcome", "severity", "reporter_type"]),
    "trial_outcome": ("trial_outcomes", "id::text", "COALESCE(outcome_type || ': ', '') || COALESCE(measure, '')", ["time_frame", "description"]),
    "trial_location": ("trial_locations", "id::text", "COALESCE(facility_name, '') || CASE WHEN city IS NOT NULL THEN ', ' || city ELSE '' END", ["country", "status"]),
}


def detect_truncation(node_count: int, max_nodes: int = 100) -> dict:
    """Check if graph traversal hit the node cap.

    Returns: {"truncated": bool, "max_nodes": int}
    """
    return {
        "truncated": node_count >= max_nodes,
        "max_nodes": max_nodes,
    }


class GraphTraversal:
    """Navigate the entity_links graph via SQL."""

    def __init__(self, db, config):
        self.db = db
        self.config = config

    def neighborhood(
        self,
        entity_id: str,
        entity_type: str,
        link_types: Optional[list[str]] = None,
        min_confidence: Optional[float] = None,
    ) -> Subgraph:
        """Get immediate 1-hop connections of an entity."""
        return self.traverse(
            entity_id, entity_type, hops=1,
            link_types=link_types, min_confidence=min_confidence,
        )

    def traverse(
        self,
        entity_id: str,
        entity_type: str,
        hops: int = 2,
        link_types: Optional[list[str]] = None,
        min_confidence: Optional[float] = None,
        max_nodes: int = 100,
    ) -> Subgraph:
        """N-hop BFS traversal from an entity.

        Args:
            entity_id: Starting entity ID.
            entity_type: Starting entity type.
            hops: Maximum traversal depth (1-4).
            link_types: If provided, only follow these link types.
            min_confidence: If provided, only include edges with confidence >= this value.
            max_nodes: Cap on total edges returned.

        Returns:
            Subgraph with nodes and edges.
        """
        hops = min(hops, 4)  # Safety cap
        entity_id = self._resolve_entity_id(entity_id, entity_type)

        rows = self.db.fetch_all(
            "SELECT * FROM traverse_graph(%s, %s, %s, %s)",
            [entity_id, hops, link_types, max_nodes],
        )

        # Collect unique entity IDs from edges, applying optional filters
        entity_ids = set()
        edges = []
        for row in rows:
            lt = row["link_type"]
            conf = float(row.get("confidence") or 1.0)
            # Apply filters if specified
            if link_types and lt not in link_types:
                continue
            if min_confidence is not None and conf < min_confidence:
                continue
            src = str(row["source_id"])
            tgt = str(row["target_id"])
            entity_ids.add(src)
            entity_ids.add(tgt)
            edges.append(GraphEdge(
                source_id=src,
                target_id=tgt,
                link_type=lt,
                confidence=conf,
                via=row.get("link_via") or "",
            ))

        # Resolve labels for all entities
        nodes = self._resolve_labels(entity_ids)

        return Subgraph(
            nodes=nodes,
            edges=edges,
            center_entity_id=entity_id,
            hops=hops,
        )

    def path_between(
        self,
        source_id: str,
        source_type: str,
        target_id: str,
        target_type: str,
        max_hops: int = 4,
    ) -> Optional[list[GraphEdge]]:
        """Find shortest path between two entities.

        Uses BFS. Returns ordered list of edges, or None if no path found.
        """
        max_hops = min(max_hops, 6)
        source_id = self._resolve_entity_id(source_id, source_type)
        target_id = self._resolve_entity_id(target_id, target_type)

        # Set statement timeout to prevent CTE explosion on large graphs
        self.db.execute("SET statement_timeout = '5s'")

        try:
            rows = self._path_query(source_id, target_id, max_hops)
        except Exception as e:
            logger.warning("Path query timed out or failed: %s", e)
            rows = []
        finally:
            self.db.execute("SET statement_timeout = '0'")  # Reset

        if not rows:
            return None

        # Reconstruct the path edges from the winning path
        winning = rows[0]
        path_ids = winning["path"]

        # Fetch actual edges along the path
        path_edges = []
        for i in range(len(path_ids) - 1):
            edge_row = self.db.fetch_one(
                """
                SELECT source_entity_id, target_entity_id, link_type, confidence, link_via
                FROM entity_links
                WHERE (source_entity_id = %s AND target_entity_id = %s)
                   OR (source_entity_id = %s AND target_entity_id = %s)
                LIMIT 1
                """,
                [path_ids[i], path_ids[i + 1], path_ids[i + 1], path_ids[i]],
            )
            if edge_row:
                path_edges.append(GraphEdge(
                    source_id=edge_row["source_entity_id"],
                    target_id=edge_row["target_entity_id"],
                    link_type=edge_row["link_type"],
                    confidence=float(edge_row.get("confidence") or 1.0),
                    via=edge_row.get("link_via") or "",
                ))

        return path_edges if path_edges else None

    def _path_query(self, source_id: str, target_id: str, max_hops: int) -> list[dict]:
        """Execute the path-finding CTE query."""
        rows = self.db.fetch_all(
            """
            WITH RECURSIVE path_bfs AS (
                SELECT
                    source_entity_id AS src, target_entity_id AS tgt,
                    link_type, confidence, link_via,
                    1 AS depth,
                    ARRAY[source_entity_id, target_entity_id] AS path,
                    CASE
                        WHEN target_entity_id = %s THEN TRUE
                        WHEN source_entity_id = %s AND target_entity_id = %s THEN TRUE
                        ELSE FALSE
                    END AS found
                FROM entity_links
                WHERE source_entity_id = %s OR target_entity_id = %s

                UNION ALL

                SELECT
                    el.source_entity_id, el.target_entity_id,
                    el.link_type, el.confidence, el.link_via,
                    p.depth + 1,
                    p.path || CASE
                        WHEN el.source_entity_id = ANY(p.path) THEN el.target_entity_id
                        ELSE el.source_entity_id
                    END,
                    CASE
                        WHEN el.source_entity_id = %s OR el.target_entity_id = %s THEN TRUE
                        ELSE FALSE
                    END AS found
                FROM entity_links el
                JOIN path_bfs p ON (
                    (el.source_entity_id = p.tgt AND NOT el.target_entity_id = ANY(p.path))
                    OR (el.target_entity_id = p.tgt AND NOT el.source_entity_id = ANY(p.path))
                )
                WHERE p.depth < %s AND NOT p.found
            )
            SELECT src, tgt, link_type, confidence, link_via, depth, path
            FROM path_bfs
            WHERE found
            ORDER BY depth
            LIMIT 1
            """,
            [target_id, source_id, target_id, source_id, source_id,
             target_id, target_id, max_hops],
        )
        return rows

    def entity_summary(self, entity_id: str, entity_type: str) -> dict:
        """Rich summary: entity properties + connection counts by link type.

        Returns:
            {
                "entity": GraphNode,
                "connections_by_type": {"INVESTIGATES": 12, "SPONSORS": 3, ...},
                "connections_by_entity_type": {"trial": 12, "company": 1, ...},
                "total_connections": 15,
            }
        """
        # Resolve name to UUID if needed
        entity_id = self._resolve_entity_id(entity_id, entity_type)

        # Get entity properties
        node = self._get_entity_node(entity_id, entity_type)

        # Count connections by link type
        link_counts = self.db.fetch_all(
            """
            SELECT link_type, COUNT(*) as cnt
            FROM entity_links
            WHERE source_entity_id = %s OR target_entity_id = %s
            GROUP BY link_type
            ORDER BY cnt DESC
            """,
            [entity_id, entity_id],
        )

        # Count connections by entity type
        entity_type_counts = self.db.fetch_all(
            """
            SELECT
                CASE
                    WHEN source_entity_id = %s THEN target_entity_type
                    ELSE source_entity_type
                END AS connected_type,
                COUNT(*) as cnt
            FROM entity_links
            WHERE source_entity_id = %s OR target_entity_id = %s
            GROUP BY connected_type
            ORDER BY cnt DESC
            """,
            [entity_id, entity_id, entity_id],
        )

        total = sum(r["cnt"] for r in link_counts)

        return {
            "entity": {
                "entity_id": node.entity_id,
                "entity_type": node.entity_type,
                "label": node.label,
                "properties": node.properties,
            } if node else None,
            "connections_by_type": {r["link_type"]: r["cnt"] for r in link_counts},
            "connections_by_entity_type": {r["connected_type"]: r["cnt"] for r in entity_type_counts},
            "total_connections": total,
        }

    def drugs_by_mechanism_class(self, mechanism_class: str) -> list[dict]:
        """Find all drugs linked to mechanisms in a given class.

        Uses the mechanism_class column and parent hierarchy to find
        drugs across related mechanisms (e.g., 'incretin_based' returns
        drugs linked to GLP-1 RA, GIP, Incretins, etc.).
        """
        return self.db.fetch_all(
            """
            SELECT d.id, d.generic_name, d.brand_name, m.name AS mechanism_name,
                   m.mechanism_class
            FROM drugs d
            JOIN mechanisms_of_action m ON m.id = d.mechanism_id
            WHERE m.mechanism_class = %s
              AND (d.record_status IS NULL OR d.record_status = 'active')
            ORDER BY d.generic_name
            """,
            [mechanism_class],
        )

    def mechanism_hierarchy(self, mechanism_id: str = None) -> list[dict]:
        """Return the full mechanism hierarchy or subtree from a given root."""
        if mechanism_id:
            return self.db.fetch_all(
                """
                WITH RECURSIVE tree AS (
                    SELECT id, name, mechanism_class, parent_mechanism_id, 0 AS depth
                    FROM mechanisms_of_action WHERE id = %s
                    UNION ALL
                    SELECT m.id, m.name, m.mechanism_class, m.parent_mechanism_id, t.depth + 1
                    FROM mechanisms_of_action m
                    JOIN tree t ON m.parent_mechanism_id = t.id
                )
                SELECT * FROM tree ORDER BY depth, name
                """,
                [mechanism_id],
            )
        return self.db.fetch_all(
            """
            SELECT id, name, mechanism_class, parent_mechanism_id,
                   (SELECT COUNT(*) FROM drugs d WHERE d.mechanism_id = m.id) AS drug_count
            FROM mechanisms_of_action m
            ORDER BY mechanism_class, name
            """,
        )

    # ---- Internal helpers ----

    # Maps entity_type -> (table, name_column) for name-based ID resolution
    _NAME_LOOKUP = {
        "drug": ("drugs", "generic_name"),
        "company": ("companies", "name"),
        "therapeutic_area": ("therapeutic_areas", "name"),
        "mechanism": ("mechanisms_of_action", "name"),
    }

    def _resolve_entity_id(self, entity_id: str, entity_type: str) -> str:
        """Resolve a human-readable name to a UUID if needed.

        If entity_id looks like a UUID or matches an id column directly,
        return it as-is. Otherwise, try case-insensitive name lookup
        on the appropriate table.
        """
        # Quick UUID check (32 hex chars with dashes)
        if len(entity_id) == 36 and entity_id.count("-") == 4:
            return entity_id

        # For trials (NCT IDs), return as-is
        if entity_type == "trial":
            return entity_id

        lookup = self._NAME_LOOKUP.get(entity_type)
        if not lookup:
            return entity_id

        table, name_col = lookup
        row = self.db.fetch_one(
            f"SELECT id::text AS entity_id FROM {table} WHERE LOWER({name_col}) = LOWER(%s)",
            [entity_id],
        )
        if row:
            return row["entity_id"]

        # Fuzzy fallback: try trigram similarity
        row = self.db.fetch_one(
            f"""
            SELECT id::text AS entity_id
            FROM {table}
            WHERE similarity({name_col}, %s) >= 0.4
            ORDER BY similarity({name_col}, %s) DESC
            LIMIT 1
            """,
            [entity_id, entity_id],
        )
        if row:
            return row["entity_id"]

        return entity_id  # Return original if nothing found

    def _resolve_labels(self, entity_ids: set[str]) -> list[GraphNode]:
        """Resolve human-readable labels for a set of entity IDs."""
        if not entity_ids:
            return []

        ids_list = list(entity_ids)
        rows = self.db.fetch_all(
            """
            SELECT entity_id, entity_type, label
            FROM v_entity_labels
            WHERE entity_id = ANY(%s)
            """,
            [ids_list],
        )

        label_map = {r["entity_id"]: r for r in rows}
        nodes = []
        for eid in ids_list:
            info = label_map.get(eid)
            if info:
                nodes.append(GraphNode(
                    entity_id=eid,
                    entity_type=info["entity_type"],
                    label=info["label"] or eid,
                ))
            else:
                nodes.append(GraphNode(
                    entity_id=eid,
                    entity_type="unknown",
                    label=eid[:12] + "...",
                ))

        return nodes

    def _get_entity_node(self, entity_id: str, entity_type: str) -> Optional[GraphNode]:
        """Fetch a single entity with its properties."""
        table_info = ENTITY_TABLE_MAP.get(entity_type)
        if not table_info:
            return None

        table, id_col, label_col, prop_cols = table_info
        props_select = ", ".join(prop_cols) if prop_cols else "'_' as _placeholder"

        row = self.db.fetch_one(
            f"""
            SELECT {id_col} AS entity_id, {label_col} AS label, {props_select}
            FROM {table}
            WHERE {id_col} = %s
            """,
            [entity_id],
        )

        if not row:
            return None

        properties = {}
        for col in prop_cols:
            val = row.get(col)
            if val is not None:
                properties[col] = val.isoformat() if hasattr(val, "isoformat") else val

        return GraphNode(
            entity_id=str(row["entity_id"]),
            entity_type=entity_type,
            label=str(row.get("label") or entity_id),
            properties=properties,
        )
