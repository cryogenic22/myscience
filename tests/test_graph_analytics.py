"""Tests for GraphAnalytics — influence scoring, competitive clusters, weighted paths.

TDD: These tests are written BEFORE the implementation.
Run with: pytest tests/test_graph_analytics.py -v
"""

from __future__ import annotations

import pytest


# ── MockDB for graph analytics ──

class MockDB:
    """Mock database that returns pre-configured query results.

    Routes queries by matching keywords in the SQL. Rules are checked in
    insertion order; the first matching rule wins.
    """

    def __init__(self):
        self._rules: list[tuple[str, list[dict]]] = []

    def add_rule(self, pattern: str, results: list[dict]):
        """Add a routing rule: if *pattern* appears in the SQL, return *results*."""
        self._rules.append((pattern.lower(), results))

    def fetch_all(self, sql: str, params=None) -> list[dict]:
        sql_lower = sql.lower()
        for pattern, results in self._rules:
            if pattern in sql_lower:
                return results
        return []

    def fetch_one(self, sql: str, params=None) -> dict | None:
        rows = self.fetch_all(sql, params)
        return rows[0] if rows else None

    def execute(self, sql: str, params=None) -> None:
        pass


# ── Fixtures ──

@pytest.fixture
def mock_db():
    return MockDB()


@pytest.fixture
def analytics(mock_db):
    from services.graph_analytics import GraphAnalytics
    return GraphAnalytics(mock_db)


# ── TestEntityInfluence ──

class TestEntityInfluence:
    """Influence scoring: PageRank-inspired 0-1 score."""

    def _setup_influence(self, mock_db, connection_count, avg_confidence,
                         type_diversity, entity_type_diversity, max_raw_score=None):
        """Wire mock_db for entity_influence calls.

        The implementation fires two queries:
        1. stats query with 'where source_entity_id' — entity-specific stats
        2. normalisation query with 'max(raw)' — global max
        """
        mock_db.add_rule("where source_entity_id", [
            {"connection_count": connection_count, "avg_confidence": avg_confidence,
             "type_diversity": type_diversity, "entity_type_diversity": entity_type_diversity},
        ])
        raw = connection_count * avg_confidence * type_diversity
        mock_db.add_rule("max(raw)", [
            {"max_score": max_raw_score if max_raw_score is not None else raw},
        ])

    def test_high_connection_entity_high_influence(self, mock_db, analytics):
        """Entity with 50 links should produce a high influence score."""
        self._setup_influence(mock_db, 50, 0.9, 5, 4, max_raw_score=50 * 0.9 * 5)

        score = analytics.entity_influence("ent-001", "drug")
        assert score > 0.5, f"Expected high influence, got {score}"
        assert 0.0 <= score <= 1.0

    def test_low_connection_entity_low_influence(self, mock_db, analytics):
        """Entity with 2 links should produce a low influence score."""
        self._setup_influence(mock_db, 2, 0.5, 1, 1, max_raw_score=50 * 0.9 * 5)

        score = analytics.entity_influence("ent-002", "drug")
        assert score < 0.5, f"Expected low influence, got {score}"

    def test_confidence_weighted(self):
        """High-confidence links should count more than low-confidence."""
        from services.graph_analytics import GraphAnalytics

        # High confidence entity
        db_high = MockDB()
        db_high.add_rule("where source_entity_id", [
            {"connection_count": 10, "avg_confidence": 0.95,
             "type_diversity": 3, "entity_type_diversity": 3},
        ])
        db_high.add_rule("max(raw)", [{"max_score": 10 * 0.95 * 3}])

        # Low confidence entity (same connections, lower confidence)
        db_low = MockDB()
        db_low.add_rule("where source_entity_id", [
            {"connection_count": 10, "avg_confidence": 0.2,
             "type_diversity": 3, "entity_type_diversity": 3},
        ])
        db_low.add_rule("max(raw)", [{"max_score": 10 * 0.95 * 3}])

        high_score = GraphAnalytics(db_high).entity_influence("ent-high", "drug")
        low_score = GraphAnalytics(db_low).entity_influence("ent-low", "drug")

        assert high_score > low_score, (
            f"High-confidence ({high_score}) should beat low-confidence ({low_score})"
        )

    def test_influence_normalized_0_to_1(self, mock_db, analytics):
        """Score must always be in [0, 1] range."""
        self._setup_influence(mock_db, 200, 1.0, 8, 6, max_raw_score=200 * 1.0 * 8)

        score = analytics.entity_influence("ent-max", "drug")
        assert 0.0 <= score <= 1.0, f"Score out of range: {score}"


# ── TestCompetitiveClusters ──

class TestCompetitiveClusters:
    """Competitive cluster detection by shared mechanism + TA."""

    def test_finds_cluster_by_mechanism_and_ta(self, mock_db, analytics):
        """Drugs sharing mechanism+TA should be grouped into a cluster."""
        mock_db.add_rule("group by", [
            {
                "mechanism_id": "m001", "mechanism_name": "GLP-1 RA",
                "ta_id": "ta001", "ta_name": "Diabetes",
                "drug_ids": "d001,d002,d003",
                "drug_names": "semaglutide,tirzepatide,dulaglutide",
                "drug_count": 3, "total_trials": 120,
            },
        ])

        clusters = analytics.competitive_clusters()
        assert len(clusters) >= 1
        cluster = clusters[0]
        assert cluster["mechanism_name"] == "GLP-1 RA"
        assert cluster["therapeutic_area"] == "Diabetes"
        assert cluster["drug_count"] == 3

    def test_cluster_includes_drug_names(self, mock_db, analytics):
        """Cluster members should include drug names."""
        mock_db.add_rule("group by", [
            {
                "mechanism_id": "m001", "mechanism_name": "GLP-1 RA",
                "ta_id": "ta001", "ta_name": "Diabetes",
                "drug_ids": "d001,d002",
                "drug_names": "semaglutide,tirzepatide",
                "drug_count": 2, "total_trials": 80,
            },
        ])

        clusters = analytics.competitive_clusters()
        drugs = clusters[0]["drugs"]
        assert "semaglutide" in drugs
        assert "tirzepatide" in drugs

    def test_empty_when_no_shared_mechanism(self, mock_db, analytics):
        """Unrelated drugs should yield no clusters."""
        mock_db.add_rule("group by", [])

        clusters = analytics.competitive_clusters()
        assert clusters == []

    def test_multiple_clusters_returned(self, mock_db, analytics):
        """Different mechanisms should produce separate clusters."""
        mock_db.add_rule("group by", [
            {
                "mechanism_id": "m001", "mechanism_name": "GLP-1 RA",
                "ta_id": "ta001", "ta_name": "Diabetes",
                "drug_ids": "d001,d002",
                "drug_names": "semaglutide,tirzepatide",
                "drug_count": 2, "total_trials": 80,
            },
            {
                "mechanism_id": "m002", "mechanism_name": "SGLT2 Inhibitor",
                "ta_id": "ta001", "ta_name": "Diabetes",
                "drug_ids": "d004,d005",
                "drug_names": "empagliflozin,dapagliflozin",
                "drug_count": 2, "total_trials": 60,
            },
        ])

        clusters = analytics.competitive_clusters()
        assert len(clusters) == 2
        mechanism_names = {c["mechanism_name"] for c in clusters}
        assert "GLP-1 RA" in mechanism_names
        assert "SGLT2 Inhibitor" in mechanism_names


# ── TestWeightedPath ──

class TestWeightedPath:
    """Weighted path finding: prefers high-confidence edges."""

    def test_finds_path_weighted_by_confidence(self, mock_db, analytics):
        """Should return a path between connected entities."""
        mock_db.add_rule("entity_links", [
            {"source_entity_id": "e001", "target_entity_id": "e002",
             "source_entity_type": "drug", "target_entity_type": "company",
             "link_type": "MANUFACTURED_BY", "confidence": 0.95, "link_via": "resolver"},
            {"source_entity_id": "e002", "target_entity_id": "e003",
             "source_entity_type": "company", "target_entity_type": "trial",
             "link_type": "SPONSORS", "confidence": 0.9, "link_via": "resolver"},
        ])
        mock_db.add_rule("v_entity_labels", [
            {"entity_id": "e001", "entity_type": "drug", "label": "DrugA"},
            {"entity_id": "e002", "entity_type": "company", "label": "CompanyB"},
            {"entity_id": "e003", "entity_type": "trial", "label": "TrialC"},
        ])

        path = analytics.weighted_path("e001", "e003", max_hops=3)
        assert len(path) >= 1, "Should find at least one hop"

    def test_returns_path_nodes_and_edges(self, mock_db, analytics):
        """Path should contain source, edge, and target info per hop."""
        mock_db.add_rule("entity_links", [
            {"source_entity_id": "e001", "target_entity_id": "e002",
             "source_entity_type": "drug", "target_entity_type": "company",
             "link_type": "MANUFACTURED_BY", "confidence": 0.85, "link_via": "resolver"},
        ])
        mock_db.add_rule("v_entity_labels", [
            {"entity_id": "e001", "entity_type": "drug", "label": "DrugA"},
            {"entity_id": "e002", "entity_type": "company", "label": "CompanyB"},
        ])

        path = analytics.weighted_path("e001", "e002", max_hops=2)
        assert len(path) == 1, "Direct connection = 1 hop"
        hop = path[0]
        assert "source" in hop
        assert "edge" in hop
        assert "target" in hop
        assert hop["edge"]["link_type"] == "MANUFACTURED_BY"

    def test_no_path_returns_empty(self, mock_db, analytics):
        """Disconnected entities should return empty list."""
        mock_db.add_rule("entity_links", [])

        path = analytics.weighted_path("e001", "e999", max_hops=4)
        assert path == []

    def test_direct_connection_returns_single_hop(self, mock_db, analytics):
        """Two directly connected entities should yield exactly 1-hop path."""
        mock_db.add_rule("entity_links", [
            {"source_entity_id": "e001", "target_entity_id": "e002",
             "source_entity_type": "drug", "target_entity_type": "company",
             "link_type": "MANUFACTURED_BY", "confidence": 0.9, "link_via": "resolver"},
        ])
        mock_db.add_rule("v_entity_labels", [
            {"entity_id": "e001", "entity_type": "drug", "label": "DrugA"},
            {"entity_id": "e002", "entity_type": "company", "label": "CompanyB"},
        ])

        path = analytics.weighted_path("e001", "e002", max_hops=4)
        assert len(path) == 1


# ── TestEntityCentralityBatch ──

class TestEntityCentralityBatch:
    """Batch centrality ranking."""

    def test_returns_ranked_entities(self, mock_db, analytics):
        """Should return entities ranked by influence."""
        # The centrality batch query joins entity_links with v_entity_labels.
        # The mock needs to return rows with raw_score computed.
        mock_db.add_rule("raw_score", [
            {"entity_id": "d001", "label": "semaglutide",
             "connection_count": 50, "avg_confidence": 0.9,
             "type_diversity": 5, "entity_type_diversity": 4,
             "raw_score": 50 * 0.9 * 5},
            {"entity_id": "d002", "label": "tirzepatide",
             "connection_count": 30, "avg_confidence": 0.85,
             "type_diversity": 4, "entity_type_diversity": 3,
             "raw_score": 30 * 0.85 * 4},
        ])

        results = analytics.entity_centrality_batch(entity_type="drug", limit=20)
        assert len(results) == 2
        assert results[0]["influence"] >= results[1]["influence"]
        assert "entity_id" in results[0]
        assert "label" in results[0]
        assert "connections" in results[0]
