"""D6 — metric & graph provenance.

Materialized-view metrics and graph edges were real but unciteable (no source /
as-of). These tests pin that every metric row now carries a `_provenance` block
and every graph edge carries provenance_source / as_of, so the synthesis layer
can cite a derivation + as-of date instead of emitting bare prose.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from services.metrics import PharmaMetrics, stamp_metric_provenance
from services.graph import GraphEdge, GraphTraversal


class TestStampMetricProvenance:
    def test_attaches_provenance_block(self):
        rows = [{"drug_id": "d1", "total_trials": 23, "pipeline_score": 42.0}]
        out = stamp_metric_provenance(rows, "drug_pipeline_strength")
        prov = out[0]["_provenance"]
        assert prov["source"] == "mv_drug_pipeline_strength"
        assert "phase-weighted" in prov["derivation"]
        assert prov["record_basis"] == 23           # from total_trials basis_field
        assert prov["computed_at"]                   # ISO timestamp present
        assert prov["realtime_fallback"] is False

    def test_realtime_flag_changes_source(self):
        rows = [{"drug_count": 5}]
        out = stamp_metric_provenance(rows, "competitive_landscape", realtime=True)
        prov = out[0]["_provenance"]
        assert prov["realtime_fallback"] is True
        assert "realtime" in prov["source"].lower()
        assert prov["record_basis"] == 5

    def test_handles_missing_basis_field(self):
        rows = [{"drug_id": "d1"}]  # no total_trials
        out = stamp_metric_provenance(rows, "drug_pipeline_strength")
        assert out[0]["_provenance"]["record_basis"] is None


class TestMetricMethodsStamp:
    def test_pipeline_strength_rows_carry_provenance(self):
        db = MagicMock()
        db.fetch_all.return_value = [
            {"drug_id": "d1", "drug_name": "x", "total_trials": 10,
             "pipeline_score": 5.0, "p1_count": 1, "p2_count": 1,
             "p3_count": 1, "p4_count": 0},
        ]
        pm = PharmaMetrics(db, MagicMock())
        rows = pm.drug_pipeline_strength(drug_id="d1")
        assert rows[0]["_provenance"]["source"] == "mv_drug_pipeline_strength"

    def test_evidence_density_rows_carry_provenance(self):
        db = MagicMock()
        db.fetch_all.return_value = [
            {"drug_id": "d1", "total_articles": 7, "weighted_score": 3.2},
        ]
        pm = PharmaMetrics(db, MagicMock())
        rows = pm.evidence_density(drug_id="d1")
        assert rows[0]["_provenance"]["record_basis"] == 7


class TestGraphEdgeProvenance:
    def test_edge_has_provenance_fields(self):
        e = GraphEdge(source_id="a", target_id="b", link_type="INVESTIGATES")
        assert hasattr(e, "provenance_source")
        assert hasattr(e, "as_of")

    def test_path_between_stamps_edge_provenance(self):
        db = MagicMock()
        # path query returns one winning path of two nodes
        db.fetch_all.return_value = [{"path": ["a", "b"], "depth": 1}]

        def fetch_one(sql, params=None):
            s = sql.lower()
            if "from entity_links" in s and "source_entity_id = %s and target" in s:
                return {
                    "source_entity_id": "a", "target_entity_id": "b",
                    "link_type": "INVESTIGATES", "confidence": 0.9,
                    "link_via": "ctgov", "provenance_source": "clinical_trials_gov",
                    "created_at": __import__("datetime").datetime(2026, 6, 1),
                }
            return None

        db.fetch_one.side_effect = fetch_one
        g = GraphTraversal(db, MagicMock())
        edges = g.path_between("a", "drug", "b", "trial")
        assert edges and edges[0].provenance_source == "clinical_trials_gov"
        assert edges[0].as_of.startswith("2026-06-01")
        assert edges[0].source == "clinical_trials_gov"

    def test_entity_summary_carries_provenance(self):
        db = MagicMock()

        def fetch_all(sql, params=None):
            s = sql.lower()
            if "group by link_type" in s:
                return [{"link_type": "INVESTIGATES", "cnt": 12}]
            if "connected_type" in s:
                return [{"connected_type": "trial", "cnt": 12}]
            return []

        db.fetch_all.side_effect = fetch_all
        db.fetch_one.return_value = {
            "entity_id": "d1", "label": "semaglutide",
        }
        g = GraphTraversal(db, MagicMock())
        out = g.entity_summary("d1", "drug")
        assert out["_provenance"]["source"] == "entity_links"
        assert out["_provenance"]["record_basis"] == 12
