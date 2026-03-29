"""Tests for SPEC-008 Phase 1 — ontology wiring.

Verifies that all entity types are registered in ENTITY_TABLE_MAP and
that filtered traversal parameters are correctly propagated.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, call


class TestEntityTableMap:
    """Verify ENTITY_TABLE_MAP contains all expected entity types."""

    def test_all_expected_types_present(self):
        from services.graph import ENTITY_TABLE_MAP

        expected = [
            "drug", "company", "trial", "literature", "event",
            "therapeutic_area", "mechanism",
            "investigator", "patent", "biomarker",
            "adverse_event", "trial_outcome", "trial_location",
        ]
        for etype in expected:
            assert etype in ENTITY_TABLE_MAP, f"Missing entity type: {etype}"

    def test_each_entry_has_four_elements(self):
        from services.graph import ENTITY_TABLE_MAP

        for etype, entry in ENTITY_TABLE_MAP.items():
            assert isinstance(entry, tuple), f"{etype}: expected tuple, got {type(entry)}"
            assert len(entry) == 4, f"{etype}: expected 4 elements, got {len(entry)}"
            table, id_col, label_col, props = entry
            assert isinstance(table, str), f"{etype}: table should be str"
            assert isinstance(id_col, str), f"{etype}: id_col should be str"
            assert isinstance(label_col, str), f"{etype}: label_col should be str"
            assert isinstance(props, list), f"{etype}: props should be list"

    def test_original_types_unchanged(self):
        """Ensure we did not break existing entries."""
        from services.graph import ENTITY_TABLE_MAP

        assert ENTITY_TABLE_MAP["drug"][0] == "drugs"
        assert ENTITY_TABLE_MAP["company"][0] == "companies"
        assert ENTITY_TABLE_MAP["trial"][0] == "clinical_trials"
        assert ENTITY_TABLE_MAP["literature"][0] == "pubmed_articles"
        assert ENTITY_TABLE_MAP["event"][0] == "market_events"
        assert ENTITY_TABLE_MAP["therapeutic_area"][0] == "therapeutic_areas"
        assert ENTITY_TABLE_MAP["mechanism"][0] == "mechanisms_of_action"

    def test_new_types_table_names(self):
        from services.graph import ENTITY_TABLE_MAP

        assert ENTITY_TABLE_MAP["investigator"][0] == "investigators"
        assert ENTITY_TABLE_MAP["patent"][0] == "patents"
        assert ENTITY_TABLE_MAP["biomarker"][0] == "biomarkers"
        assert ENTITY_TABLE_MAP["adverse_event"][0] == "adverse_events"
        assert ENTITY_TABLE_MAP["trial_outcome"][0] == "trial_outcomes"
        assert ENTITY_TABLE_MAP["trial_location"][0] == "trial_locations"


class TestFilteredTraversal:
    """Verify filtered traversal parameters propagate to DB calls."""

    def _make_graph(self):
        from services.graph import GraphTraversal

        mock_db = MagicMock()
        mock_db.fetch_all.return_value = []
        mock_db.fetch_one.return_value = None
        mock_config = MagicMock()
        return GraphTraversal(mock_db, mock_config), mock_db

    def test_min_confidence_filters_in_python(self):
        """min_confidence is applied as a Python filter on results, not passed to DB."""
        graph, mock_db = self._make_graph()
        entity_id = "12345678-1234-1234-1234-123456789abc"
        graph.traverse(entity_id, "drug", min_confidence=0.8)
        mock_db.fetch_all.assert_called_once()

    def test_link_type_filter_passed_to_db(self):
        graph, mock_db = self._make_graph()
        entity_id = "12345678-1234-1234-1234-123456789abc"
        graph.traverse(entity_id, "drug", link_types=["OWNS", "SPONSORS"])

        mock_db.fetch_all.assert_called_once()
        args = mock_db.fetch_all.call_args
        params = args[0][1]
        # link_types is 3rd param (index 2) passed to traverse_graph
        assert ["OWNS", "SPONSORS"] in params, f"link_types not found in params: {params}"

    def test_no_filter_when_none(self):
        graph, mock_db = self._make_graph()
        entity_id = "12345678-1234-1234-1234-123456789abc"
        graph.traverse(entity_id, "drug")

        mock_db.fetch_all.assert_called_once()
        args = mock_db.fetch_all.call_args
        params = args[0][1]
        # traverse_graph(entity_id, hops, link_types, max_nodes) — 4 params
        assert len(params) == 4, f"Expected 4 params, got {len(params)}"
        assert params[2] is None, f"link_types should be None, got {params[2]}"

    def test_neighborhood_passes_link_types(self):
        graph, mock_db = self._make_graph()
        entity_id = "12345678-1234-1234-1234-123456789abc"
        graph.neighborhood(
            entity_id, "drug",
            link_types=["OWNS"], min_confidence=0.5,
        )

        mock_db.fetch_all.assert_called_once()
        args = mock_db.fetch_all.call_args
        params = args[0][1]
        assert ["OWNS"] in params

    def test_neighborhood_defaults_to_1_hop(self):
        graph, mock_db = self._make_graph()
        entity_id = "12345678-1234-1234-1234-123456789abc"
        graph.neighborhood(entity_id, "drug")

        mock_db.fetch_all.assert_called_once()
        args = mock_db.fetch_all.call_args
        params = args[0][1]
        # hops=1 should be the 2nd parameter
        assert params[1] == 1, f"Expected hops=1, got {params[1]}"
