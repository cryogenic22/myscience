"""GraphAnalytics: Advanced graph reasoning beyond basic traversal.

Provides PageRank-inspired influence scoring, competitive cluster detection,
and confidence-weighted path finding. Operates on the entity_links table
using pure SQL — no external graph database required.

Usage:
    analytics = GraphAnalytics(db)
    score = analytics.entity_influence(drug_id, "drug")
    clusters = analytics.competitive_clusters(mechanism_id="m001")
    path = analytics.weighted_path(source_id, target_id)
"""

from __future__ import annotations

import logging
from collections import defaultdict
from heapq import heappush, heappop
from typing import Optional

logger = logging.getLogger(__name__)


class GraphAnalytics:
    """Advanced graph operations beyond basic traversal."""

    def __init__(self, db):
        self.db = db

    # ── Influence scoring ──

    def entity_influence(self, entity_id: str, entity_type: str) -> float:
        """PageRank-inspired influence score (0-1).

        Score = normalized(connection_count * avg_confidence * type_diversity)

        Higher score = more connected, more diverse, higher confidence links.
        """
        row = self.db.fetch_one(
            """
            SELECT
                COUNT(*) AS connection_count,
                COALESCE(AVG(confidence), 0.5) AS avg_confidence,
                COUNT(DISTINCT link_type) AS type_diversity,
                COUNT(DISTINCT
                    CASE WHEN source_entity_id = %s THEN target_entity_type
                         ELSE source_entity_type END
                ) AS entity_type_diversity
            FROM entity_links
            WHERE source_entity_id = %s OR target_entity_id = %s
            """,
            [entity_id, entity_id, entity_id],
        )

        if not row or row["connection_count"] == 0:
            return 0.0

        raw_score = (
            row["connection_count"]
            * float(row["avg_confidence"])
            * row["type_diversity"]
        )

        # Normalize against the max raw score in the graph
        max_row = self.db.fetch_one(
            """
            SELECT MAX(raw) AS max_score FROM (
                SELECT
                    COUNT(*) * COALESCE(AVG(confidence), 0.5)
                    * COUNT(DISTINCT link_type) AS raw
                FROM entity_links
                GROUP BY CASE
                    WHEN source_entity_id IS NOT NULL THEN source_entity_id
                    ELSE target_entity_id
                END
            ) sub
            """,
        )

        max_score = float(max_row["max_score"]) if max_row and max_row["max_score"] else raw_score
        if max_score <= 0:
            return 0.0

        return min(raw_score / max_score, 1.0)

    # ── Competitive clusters ──

    def competitive_clusters(
        self,
        mechanism_id: str | None = None,
        therapeutic_area_id: str | None = None,
    ) -> list[dict]:
        """Group drugs into competitive clusters by shared mechanism + TA.

        Returns:
            [{"cluster_name": "GLP-1 RA in Diabetes", "mechanism_id": "...",
              "mechanism_name": "...", "therapeutic_area": "...",
              "drugs": ["semaglutide", ...], "drug_count": 3,
              "total_trials": 120, "concentration_hhi": 0.33}]
        """
        where_clauses = ["1=1"]
        params: list = []

        if mechanism_id:
            where_clauses.append("m.id::text = %s")
            params.append(mechanism_id)
        if therapeutic_area_id:
            where_clauses.append("ta.id::text = %s")
            params.append(therapeutic_area_id)

        where_sql = " AND ".join(where_clauses)

        rows = self.db.fetch_all(
            f"""
            SELECT
                m.id::text AS mechanism_id,
                m.name AS mechanism_name,
                ta.id::text AS ta_id,
                ta.name AS ta_name,
                STRING_AGG(DISTINCT d.id::text, ',') AS drug_ids,
                STRING_AGG(DISTINCT d.generic_name, ',') AS drug_names,
                COUNT(DISTINCT d.id) AS drug_count,
                COALESCE(SUM(trial_counts.cnt), 0)::int AS total_trials
            FROM drugs d
            JOIN mechanisms_of_action m ON m.id = d.mechanism_id
            JOIN entity_links el ON (
                (el.source_entity_id = d.id::text AND el.target_entity_type = 'therapeutic_area')
                OR (el.target_entity_id = d.id::text AND el.source_entity_type = 'therapeutic_area')
            )
            JOIN therapeutic_areas ta ON ta.id::text = CASE
                WHEN el.source_entity_type = 'therapeutic_area' THEN el.source_entity_id
                ELSE el.target_entity_id
            END
            LEFT JOIN LATERAL (
                SELECT COUNT(*) AS cnt
                FROM entity_links t
                WHERE t.link_type IN ('INVESTIGATES', 'TESTED_IN')
                  AND (t.source_entity_id = d.id::text OR t.target_entity_id = d.id::text)
                  AND (t.source_entity_type = 'trial' OR t.target_entity_type = 'trial')
            ) trial_counts ON TRUE
            WHERE (d.record_status IS NULL OR d.record_status = 'active')
              AND {where_sql}
            GROUP BY m.id, m.name, ta.id, ta.name
            HAVING COUNT(DISTINCT d.id) >= 2
            ORDER BY COUNT(DISTINCT d.id) DESC
            """,
            params if params else None,
        )

        clusters = []
        for row in rows:
            drug_names_list = (row["drug_names"] or "").split(",")
            drug_count = row["drug_count"]

            # Herfindahl-Hirschman Index: 1/N for equal market shares
            hhi = 1.0 / drug_count if drug_count > 0 else 0.0

            clusters.append({
                "cluster_name": f"{row['mechanism_name']} in {row['ta_name']}",
                "mechanism_id": row["mechanism_id"],
                "mechanism_name": row["mechanism_name"],
                "therapeutic_area_id": row["ta_id"],
                "therapeutic_area": row["ta_name"],
                "drugs": drug_names_list,
                "drug_count": drug_count,
                "total_trials": row["total_trials"],
                "concentration_hhi": round(hhi, 4),
            })

        return clusters

    # ── Weighted path finding ──

    def weighted_path(
        self,
        source_id: str,
        target_id: str,
        max_hops: int = 4,
    ) -> list[dict]:
        """Find path between entities weighted by link confidence.

        Unlike path_between() which uses hop count, this prefers
        high-confidence edges even if they require more hops.

        Uses Dijkstra with cost = 1 - confidence per edge.

        Returns:
            [{"source": {"id": ..., "type": ..., "label": ...},
              "edge": {"link_type": ..., "confidence": ..., "via": ...},
              "target": {"id": ..., "type": ..., "label": ...}}]
        """
        max_hops = min(max_hops, 6)

        # Load edges up to max_hops from source using BFS expansion
        edges = self._load_neighborhood_edges(source_id, target_id, max_hops)

        if not edges:
            return []

        # Build adjacency list
        adjacency: dict[str, list[dict]] = defaultdict(list)
        for e in edges:
            src = e["source_entity_id"]
            tgt = e["target_entity_id"]
            adjacency[src].append(e)
            # Treat graph as undirected for path finding
            adjacency[tgt].append({
                **e,
                "source_entity_id": tgt,
                "target_entity_id": src,
                "source_entity_type": e["target_entity_type"],
                "target_entity_type": e["source_entity_type"],
            })

        # Dijkstra: cost = sum(1 - confidence)
        # Priority queue: (cost, current_node, path_edges)
        visited: set[str] = set()
        heap: list[tuple[float, str, list[dict]]] = [(0.0, source_id, [])]

        while heap:
            cost, current, path_so_far = heappop(heap)

            if current == target_id:
                return self._format_path(path_so_far)

            if current in visited:
                continue
            visited.add(current)

            if len(path_so_far) >= max_hops:
                continue

            for edge in adjacency.get(current, []):
                neighbor = edge["target_entity_id"]
                if neighbor in visited:
                    continue
                edge_cost = 1.0 - float(edge.get("confidence") or 0.5)
                new_cost = cost + edge_cost
                heappush(heap, (new_cost, neighbor, path_so_far + [edge]))

        return []

    def _load_neighborhood_edges(
        self, source_id: str, target_id: str, max_hops: int,
    ) -> list[dict]:
        """Load edges in the neighborhood of source and target for path search."""
        return self.db.fetch_all(
            """
            SELECT DISTINCT
                source_entity_id, target_entity_id,
                source_entity_type, target_entity_type,
                link_type, COALESCE(confidence, 0.5) AS confidence,
                COALESCE(link_via, '') AS link_via
            FROM entity_links
            WHERE source_entity_id = ANY(
                SELECT DISTINCT unnest(ARRAY[source_entity_id, target_entity_id])
                FROM entity_links
                WHERE source_entity_id = %s OR target_entity_id = %s
                   OR source_entity_id = %s OR target_entity_id = %s
            )
            OR target_entity_id = ANY(
                SELECT DISTINCT unnest(ARRAY[source_entity_id, target_entity_id])
                FROM entity_links
                WHERE source_entity_id = %s OR target_entity_id = %s
                   OR source_entity_id = %s OR target_entity_id = %s
            )
            LIMIT 5000
            """,
            [source_id, source_id, target_id, target_id,
             source_id, source_id, target_id, target_id],
        )

    def _format_path(self, edges: list[dict]) -> list[dict]:
        """Format raw edge dicts into structured path hops with labels."""
        # Collect entity IDs for label resolution
        entity_ids = set()
        for e in edges:
            entity_ids.add(e["source_entity_id"])
            entity_ids.add(e["target_entity_id"])

        label_map = self._resolve_labels(entity_ids)

        path = []
        for e in edges:
            src_id = e["source_entity_id"]
            tgt_id = e["target_entity_id"]
            path.append({
                "source": {
                    "id": src_id,
                    "type": e.get("source_entity_type", "unknown"),
                    "label": label_map.get(src_id, {}).get("label", src_id[:12]),
                },
                "edge": {
                    "link_type": e["link_type"],
                    "confidence": float(e.get("confidence", 0.5)),
                    "via": e.get("link_via", ""),
                },
                "target": {
                    "id": tgt_id,
                    "type": e.get("target_entity_type", "unknown"),
                    "label": label_map.get(tgt_id, {}).get("label", tgt_id[:12]),
                },
            })
        return path

    def _resolve_labels(self, entity_ids: set[str]) -> dict[str, dict]:
        """Resolve human-readable labels for a set of entity IDs."""
        if not entity_ids:
            return {}

        rows = self.db.fetch_all(
            """
            SELECT entity_id, entity_type, label
            FROM v_entity_labels
            WHERE entity_id = ANY(%s)
            """,
            [list(entity_ids)],
        )
        return {r["entity_id"]: r for r in rows}

    # ── Batch centrality ──

    def entity_centrality_batch(
        self,
        entity_type: str = "drug",
        limit: int = 20,
    ) -> list[dict]:
        """Top entities by influence score for a given type.

        Returns:
            [{"entity_id": "...", "label": "...", "influence": 0.85,
              "connections": 47, "types_connected": 5}]
        """
        rows = self.db.fetch_all(
            """
            SELECT
                sub.entity_id,
                COALESCE(lbl.label, sub.entity_id) AS label,
                sub.connection_count,
                sub.avg_confidence,
                sub.type_diversity,
                sub.entity_type_diversity,
                sub.connection_count * sub.avg_confidence * sub.type_diversity AS raw_score
            FROM (
                SELECT
                    CASE
                        WHEN source_entity_type = %s THEN source_entity_id
                        ELSE target_entity_id
                    END AS entity_id,
                    COUNT(*) AS connection_count,
                    COALESCE(AVG(confidence), 0.5) AS avg_confidence,
                    COUNT(DISTINCT link_type) AS type_diversity,
                    COUNT(DISTINCT
                        CASE WHEN source_entity_type = %s THEN target_entity_type
                             ELSE source_entity_type END
                    ) AS entity_type_diversity
                FROM entity_links
                WHERE source_entity_type = %s OR target_entity_type = %s
                GROUP BY entity_id
            ) sub
            LEFT JOIN v_entity_labels lbl ON lbl.entity_id = sub.entity_id
            ORDER BY raw_score DESC
            LIMIT %s
            """,
            [entity_type, entity_type, entity_type, entity_type, limit],
        )

        if not rows:
            return []

        # Normalize scores to 0-1 using the top score
        max_score = float(rows[0]["raw_score"]) if rows[0]["raw_score"] else 1.0
        if max_score <= 0:
            max_score = 1.0

        results = []
        for r in rows:
            raw = float(r["raw_score"]) if r["raw_score"] else 0.0
            results.append({
                "entity_id": r["entity_id"],
                "label": r["label"],
                "influence": round(min(raw / max_score, 1.0), 4),
                "connections": r["connection_count"],
                "types_connected": r["entity_type_diversity"],
            })

        return results
