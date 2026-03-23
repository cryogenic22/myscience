"""Tests for compare handler graph emission fix — SPEC-004 R5.

TDD: Verify shared/unique connections are converted to graph_context nodes/edges.
"""

from __future__ import annotations

import pytest


class TestBuildCompareGraph:
    """Verify graph_context built from shared/unique connections."""

    def test_shared_connections_become_nodes(self):
        from services.chat_handlers.formatting import build_compare_graph
        shared = [
            {"entity_id": "m1", "entity_type": "mechanism", "label": "GLP-1 RA"},
            {"entity_id": "ta1", "entity_type": "therapeutic_area", "label": "Diabetes"},
        ]
        unique = {}
        entities = [
            {"entity_id": "d1", "entity_type": "drug", "label": "semaglutide"},
            {"entity_id": "d2", "entity_type": "drug", "label": "tirzepatide"},
        ]
        gc = build_compare_graph(entities, shared, unique)
        node_ids = {n["entity_id"] for n in gc["nodes"]}
        assert "m1" in node_ids
        assert "ta1" in node_ids
        assert "d1" in node_ids
        assert "d2" in node_ids
        assert gc["node_count"] == 4

    def test_shared_connections_create_edges_to_both(self):
        from services.chat_handlers.formatting import build_compare_graph
        shared = [{"entity_id": "m1", "entity_type": "mechanism", "label": "GLP-1 RA"}]
        unique = {}
        entities = [
            {"entity_id": "d1", "entity_type": "drug", "label": "semaglutide"},
            {"entity_id": "d2", "entity_type": "drug", "label": "tirzepatide"},
        ]
        gc = build_compare_graph(entities, shared, unique)
        # Shared connection should have edges to BOTH compared entities
        edges_to_m1 = [e for e in gc["edges"] if e["target_id"] == "m1" or e["source_id"] == "m1"]
        assert len(edges_to_m1) == 2  # d1→m1, d2→m1

    def test_unique_connections_create_single_edge(self):
        from services.chat_handlers.formatting import build_compare_graph
        shared = []
        unique = {
            "d1": [{"entity_id": "c1", "entity_type": "company", "label": "Novo Nordisk"}],
            "d2": [{"entity_id": "c2", "entity_type": "company", "label": "Eli Lilly"}],
        }
        entities = [
            {"entity_id": "d1", "entity_type": "drug", "label": "semaglutide"},
            {"entity_id": "d2", "entity_type": "drug", "label": "tirzepatide"},
        ]
        gc = build_compare_graph(entities, shared, unique)
        edges_to_c1 = [e for e in gc["edges"] if e["target_id"] == "c1"]
        assert len(edges_to_c1) == 1  # only d1→c1

    def test_empty_connections_returns_entity_nodes_only(self):
        from services.chat_handlers.formatting import build_compare_graph
        entities = [
            {"entity_id": "d1", "entity_type": "drug", "label": "semaglutide"},
            {"entity_id": "d2", "entity_type": "drug", "label": "tirzepatide"},
        ]
        gc = build_compare_graph(entities, [], {})
        assert gc["node_count"] == 2
        assert gc["edge_count"] == 0

    def test_no_duplicate_nodes(self):
        from services.chat_handlers.formatting import build_compare_graph
        shared = [{"entity_id": "m1", "entity_type": "mechanism", "label": "GLP-1 RA"}]
        unique = {
            "d1": [{"entity_id": "m1", "entity_type": "mechanism", "label": "GLP-1 RA"}],
        }
        entities = [
            {"entity_id": "d1", "entity_type": "drug", "label": "semaglutide"},
            {"entity_id": "d2", "entity_type": "drug", "label": "tirzepatide"},
        ]
        gc = build_compare_graph(entities, shared, unique)
        node_ids = [n["entity_id"] for n in gc["nodes"]]
        assert len(node_ids) == len(set(node_ids))
