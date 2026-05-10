"""BE-18 — source aggregation helper tests."""

from __future__ import annotations

import pytest


class TestAggregateBySource:
    def test_empty_returns_empty(self):
        from services.source_aggregation import aggregate_by_source
        assert aggregate_by_source([]) == []
        assert aggregate_by_source(None) == []

    def test_groups_repeated_sources(self):
        from services.source_aggregation import aggregate_by_source
        out = aggregate_by_source([
            {"source_id": "pubmed"},
            {"source_id": "pubmed"},
            {"source_id": "fda"},
        ])
        assert len(out) == 2
        by_sid = {r["source_id"]: r for r in out}
        assert by_sid["pubmed"]["cite_count"] == 2
        assert by_sid["fda"]["cite_count"] == 1

    def test_resolves_tier_via_registry(self):
        from services.source_aggregation import aggregate_by_source
        out = aggregate_by_source([
            {"source_id": "pubmed"},
            {"source_id": "fda"},
        ])
        by_sid = {r["source_id"]: r for r in out}
        assert by_sid["pubmed"]["tier"] == "T3"
        assert by_sid["fda"]["tier"] == "T1"
        assert by_sid["pubmed"]["source_name"] == "PubMed"
        assert by_sid["fda"]["source_name"] == "FDA"

    def test_explicit_fields_take_precedence(self):
        from services.source_aggregation import aggregate_by_source
        out = aggregate_by_source([
            {"source_id": "weird-source", "source_name": "Custom", "source_tier": "T2"},
        ])
        assert out[0]["tier"] == "T2"
        assert out[0]["source_name"] == "Custom"

    def test_sort_order_t1_first_then_cite_count(self):
        from services.source_aggregation import aggregate_by_source
        out = aggregate_by_source([
            {"source_id": "pubmed"},
            {"source_id": "pubmed"},
            {"source_id": "pubmed"},
            {"source_id": "fda"},
            {"source_id": "fda"},
            {"source_id": "sec_edgar"},
        ])
        assert [r["source_id"] for r in out] == ["fda", "sec_edgar", "pubmed"]

    def test_unknown_source_surfaces_as_unknown(self):
        from services.source_aggregation import aggregate_by_source
        out = aggregate_by_source([
            {"source_id": ""},
            {},
        ])
        assert len(out) == 1
        assert out[0]["source_id"] == "unknown"
        assert out[0]["cite_count"] == 2

    def test_secondary_sort_within_tier_by_count_then_alpha(self):
        from services.source_aggregation import aggregate_by_source
        out = aggregate_by_source([
            {"source_id": "fda"},
            {"source_id": "uspto"},
        ])
        # Both T1, both cite_count 1 → alphabetical
        assert [r["source_id"] for r in out] == ["fda", "uspto"]

    def test_higher_count_wins_within_tier(self):
        from services.source_aggregation import aggregate_by_source
        out = aggregate_by_source([
            {"source_id": "fda"},
            {"source_id": "uspto"},
            {"source_id": "uspto"},
        ])
        # Both T1; uspto has 2 cites, fda has 1 → uspto first
        assert out[0]["source_id"] == "uspto"
        assert out[1]["source_id"] == "fda"
