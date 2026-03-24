"""Tests for ScenarioEngine — deterministic what-if operations on the knowledge graph.

TDD: Tests written BEFORE implementation.
Run with: pytest tests/test_scenario_primitives.py -v
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from services.scenario_engine import ScenarioEngine, ScenarioResult


# ── Test data ──

LANDSCAPE_ROWS = [
    {
        "mechanism_id": "m1",
        "mechanism_name": "GLP-1 Receptor Agonists",
        "therapeutic_area_id": "ta1",
        "therapeutic_area": "Diabetes Mellitus",
        "drug_count": 5,
        "trial_count": 120,
        "active_trial_count": 30,
        "top_drug": "semaglutide",
        "total_pipeline_score": 200.0,
        "market_share_pct": 50.0,
    },
    {
        "mechanism_id": "m2",
        "mechanism_name": "SGLT2 Inhibitors",
        "therapeutic_area_id": "ta1",
        "therapeutic_area": "Diabetes Mellitus",
        "drug_count": 3,
        "trial_count": 80,
        "active_trial_count": 15,
        "top_drug": "empagliflozin",
        "total_pipeline_score": 100.0,
        "market_share_pct": 30.0,
    },
    {
        "mechanism_id": "m3",
        "mechanism_name": "DPP-4 Inhibitors",
        "therapeutic_area_id": "ta1",
        "therapeutic_area": "Diabetes Mellitus",
        "drug_count": 2,
        "trial_count": 40,
        "active_trial_count": 5,
        "top_drug": "sitagliptin",
        "total_pipeline_score": 50.0,
        "market_share_pct": 20.0,
    },
]

PIPELINE_ROWS = [
    {
        "drug_id": "d1",
        "drug_name": "semaglutide",
        "brand_name": "Ozempic",
        "therapeutic_area": "Diabetes Mellitus",
        "mechanism": "GLP-1 Receptor Agonists",
        "p1_count": 2,
        "p2_count": 5,
        "p3_count": 10,
        "p4_count": 3,
        "total_trials": 60,
        "active_trials": 15,
        "pipeline_score": 85.0,
        "active_pipeline_score": 40.0,
        "last_trial_start": datetime(2025, 6, 1),
    },
    {
        "drug_id": "d2",
        "drug_name": "tirzepatide",
        "brand_name": "Mounjaro",
        "therapeutic_area": "Diabetes Mellitus",
        "mechanism": "GLP-1 Receptor Agonists",
        "p1_count": 1,
        "p2_count": 3,
        "p3_count": 8,
        "p4_count": 1,
        "total_trials": 40,
        "active_trials": 12,
        "pipeline_score": 65.0,
        "active_pipeline_score": 30.0,
        "last_trial_start": datetime(2025, 3, 1),
    },
    {
        "drug_id": "d3",
        "drug_name": "exenatide",
        "brand_name": "Byetta",
        "therapeutic_area": "Diabetes Mellitus",
        "mechanism": "GLP-1 Receptor Agonists",
        "p1_count": 0,
        "p2_count": 0,
        "p3_count": 0,
        "p4_count": 1,
        "total_trials": 20,
        "active_trials": 0,
        "pipeline_score": 10.0,
        "active_pipeline_score": 0.0,
        "last_trial_start": datetime(2020, 1, 1),
    },
]

COMPANY_LANDSCAPE_DRUGS = [
    # Drugs linked to company c1 (Novo Nordisk)
    {"drug_id": "d1", "drug_name": "semaglutide", "company_id": "c1"},
    {"drug_id": "d4", "drug_name": "liraglutide", "company_id": "c1"},
]


# ── Fixtures ──

class MockMetrics:
    """Minimal mock for PharmaMetrics returning canned data."""

    def __init__(self, landscape_rows=None, pipeline_rows=None):
        self._landscape = landscape_rows or []
        self._pipeline = pipeline_rows or []

    def competitive_landscape(self, **kwargs):
        return [dict(r) for r in self._landscape]

    def drug_pipeline_strength(self, **kwargs):
        return [dict(r) for r in self._pipeline]


class MockDB:
    """Mock DB that returns configurable results for scenario queries."""

    def __init__(self):
        self._queries: list[tuple[str, list]] = []
        self._company_drugs: list[dict] = []
        self._pipeline_rows: list[dict] = []

    def set_company_drugs(self, drugs: list[dict]):
        self._company_drugs = drugs

    def set_pipeline_rows(self, rows: list[dict]):
        self._pipeline_rows = rows

    def fetch_all(self, query: str, params=None):
        self._queries.append((query, params))
        q_lower = query.lower()
        if "company_id" in q_lower and "drug" in q_lower:
            return self._company_drugs
        if "mv_drug_pipeline_strength" in q_lower:
            return self._pipeline_rows
        return []

    def fetch_one(self, query: str, params=None):
        self._queries.append((query, params))
        return None

    def execute(self, query: str, params=None):
        self._queries.append((query, params))


@pytest.fixture
def mock_db():
    return MockDB()


@pytest.fixture
def mock_metrics():
    return MockMetrics(landscape_rows=LANDSCAPE_ROWS, pipeline_rows=PIPELINE_ROWS)


@pytest.fixture
def engine(mock_db, mock_metrics):
    return ScenarioEngine(db=mock_db, metrics=mock_metrics)


# ── 1. Entity Removal ──

class TestEntityRemoval:
    """Remove an entity from competitive calculations."""

    def test_landscape_without_drug(self, engine):
        """Removing a drug's mechanism row should reduce drug_count."""
        result = engine.landscape_without_entity(
            entity_id="m1",
            entity_type="mechanism",
            topic="Diabetes",
        )
        assert isinstance(result, ScenarioResult)
        assert result.scenario_type == "entity_removal"
        # Baseline had 3 mechanisms; modified should have 2
        baseline_count = len(result.baseline["rows"])
        modified_count = len(result.modified["rows"])
        assert modified_count == baseline_count - 1
        # The removed mechanism should not appear
        modified_ids = [r["mechanism_id"] for r in result.modified["rows"]]
        assert "m1" not in modified_ids

    def test_pipeline_without_drug(self, engine):
        """Removing a drug from pipeline should exclude it from ranking."""
        result = engine.pipeline_without_entity(
            entity_id="d1",
            therapeutic_area="Diabetes",
        )
        assert isinstance(result, ScenarioResult)
        assert result.scenario_type == "entity_removal"
        # d1 should not appear in modified pipeline
        modified_ids = [r["drug_id"] for r in result.modified["rows"]]
        assert "d1" not in modified_ids
        # Other drugs should still be present
        assert "d2" in modified_ids

    def test_removal_doesnt_modify_db(self, engine, mock_db):
        """Entity removal is a pure calculation — no DB writes."""
        engine.landscape_without_entity(
            entity_id="m1", entity_type="mechanism", topic="Diabetes",
        )
        # No INSERT/UPDATE/DELETE queries
        for query, _ in mock_db._queries:
            q_upper = query.strip().upper()
            assert not q_upper.startswith("INSERT")
            assert not q_upper.startswith("UPDATE")
            assert not q_upper.startswith("DELETE")


# ── 2. Temporal Filtering ──

class TestTemporalFiltering:
    """Filter out drugs with no recent trial activity."""

    def test_pipeline_excluding_inactive(self, engine):
        """Drugs with last_trial_start > N years ago should be excluded."""
        result = engine.pipeline_excluding_inactive(
            therapeutic_area="Diabetes",
            inactive_years=2,
        )
        assert isinstance(result, ScenarioResult)
        assert result.scenario_type == "temporal_filter"
        # exenatide (last trial 2020) should be excluded (>2 years from baseline)
        modified_names = [r["drug_name"] for r in result.modified["rows"]]
        assert "exenatide" not in modified_names
        # semaglutide and tirzepatide should remain
        assert "semaglutide" in modified_names
        assert "tirzepatide" in modified_names

    def test_only_recent_trials_counted(self, engine):
        """Modified result should only contain drugs with recent activity."""
        result = engine.pipeline_excluding_inactive(
            therapeutic_area="Diabetes",
            inactive_years=2,
        )
        for row in result.modified["rows"]:
            last_start = row.get("last_trial_start")
            if last_start:
                # Should be within inactive_years window
                cutoff = datetime.now() - timedelta(days=2 * 365)
                assert last_start >= cutoff

    def test_all_inactive_returns_empty(self, engine, mock_metrics):
        """If all drugs are old, modified result is empty."""
        # Override pipeline to only have old drugs
        old_pipeline = [
            {
                "drug_id": "d_old",
                "drug_name": "old_drug",
                "therapeutic_area": "Diabetes",
                "pipeline_score": 5.0,
                "last_trial_start": datetime(2018, 1, 1),
                "p1_count": 0, "p2_count": 0, "p3_count": 0, "p4_count": 0,
                "total_trials": 5, "active_trials": 0,
                "active_pipeline_score": 0, "mechanism": "X",
                "brand_name": "OldBrand",
            }
        ]
        engine_with_old = ScenarioEngine(
            db=MagicMock(),
            metrics=MockMetrics(pipeline_rows=old_pipeline),
        )
        result = engine_with_old.pipeline_excluding_inactive(
            therapeutic_area="Diabetes",
            inactive_years=2,
        )
        assert len(result.modified["rows"]) == 0
        assert result.entities_affected == 1  # 1 drug was filtered out


# ── 3. Segment Isolation ──

class TestSegmentIsolation:
    """Isolate specific segments of the landscape."""

    def test_landscape_without_company(self, engine, mock_db):
        """Remove all drugs belonging to a specific company."""
        # Set up company drug lookup
        mock_db.set_company_drugs(COMPANY_LANDSCAPE_DRUGS)

        result = engine.landscape_without_company(
            company_id="c1",
            topic="Diabetes",
        )
        assert isinstance(result, ScenarioResult)
        assert result.scenario_type == "segment_isolation"
        # Should have filtered landscape data
        assert "rows" in result.modified

    def test_landscape_single_mechanism(self, engine):
        """Isolate landscape to a single mechanism."""
        result = engine.landscape_single_mechanism(
            mechanism_id="m1",
            topic="Diabetes",
        )
        assert isinstance(result, ScenarioResult)
        assert result.scenario_type == "segment_isolation"
        # Modified should only contain the target mechanism
        for row in result.modified["rows"]:
            assert row["mechanism_id"] == "m1"


# ── 4. Threshold Alerts ──

class TestThresholdAlerts:
    """Flag entities exceeding metric thresholds."""

    def test_detects_score_above_threshold(self, engine):
        """Drugs with pipeline_score > threshold should be flagged."""
        alerts = engine.threshold_alert(
            metric="pipeline_score",
            threshold=50.0,
            entity_type="drug",
        )
        assert isinstance(alerts, list)
        assert len(alerts) > 0
        # semaglutide (85) and tirzepatide (65) should be flagged
        flagged_names = [a["drug_name"] for a in alerts]
        assert "semaglutide" in flagged_names
        assert "tirzepatide" in flagged_names

    def test_no_alert_below_threshold(self, engine):
        """No alerts when all drugs are below threshold."""
        alerts = engine.threshold_alert(
            metric="pipeline_score",
            threshold=1000.0,  # Very high threshold
            entity_type="drug",
        )
        assert isinstance(alerts, list)
        assert len(alerts) == 0

    def test_custom_threshold(self, engine):
        """Threshold is configurable — different values yield different results."""
        # Threshold = 80 should only flag semaglutide (85)
        alerts_80 = engine.threshold_alert(
            metric="pipeline_score",
            threshold=80.0,
            entity_type="drug",
        )
        assert len(alerts_80) == 1
        assert alerts_80[0]["drug_name"] == "semaglutide"

        # Threshold = 10 should flag semaglutide (85), tirzepatide (65), exenatide (10)
        # Note: exenatide has score=10 which is not > 10, so 2 flagged
        alerts_10 = engine.threshold_alert(
            metric="pipeline_score",
            threshold=10.0,
            entity_type="drug",
        )
        assert len(alerts_10) == 2  # 85 and 65 are > 10; 10 is not > 10


# ── 5. Scenario Engine Orchestration ──

class TestScenarioEngine:
    """Verify the orchestrator routes correctly and returns deltas."""

    def test_runs_entity_removal_scenario(self, engine):
        """ScenarioEngine.run() routes to the correct handler."""
        result = engine.run(
            scenario_type="landscape_without_entity",
            params={
                "entity_id": "m2",
                "entity_type": "mechanism",
                "topic": "Diabetes",
            },
        )
        assert isinstance(result, ScenarioResult)
        assert result.scenario_type == "entity_removal"

    def test_returns_before_after_comparison(self, engine):
        """Result must include baseline, modified, and delta."""
        result = engine.landscape_without_entity(
            entity_id="m1",
            entity_type="mechanism",
            topic="Diabetes",
        )
        assert result.baseline is not None
        assert result.modified is not None
        assert result.delta is not None
        # Delta should show the change in total rows
        assert "row_count_change" in result.delta
        assert result.delta["row_count_change"] == -1  # removed 1 mechanism

    def test_delta_shows_pipeline_score_change(self, engine):
        """Delta captures the pipeline score change from entity removal."""
        result = engine.landscape_without_entity(
            entity_id="m1",
            entity_type="mechanism",
            topic="Diabetes",
        )
        assert "total_pipeline_score_change" in result.delta
        # Removing m1 (score=200) should reduce total by 200
        assert result.delta["total_pipeline_score_change"] == -200.0

    def test_result_has_description(self, engine):
        """ScenarioResult includes a human-readable description."""
        result = engine.landscape_without_entity(
            entity_id="m1",
            entity_type="mechanism",
            topic="Diabetes",
        )
        assert result.description
        assert len(result.description) > 0

    def test_unknown_scenario_raises(self, engine):
        """Unknown scenario type should raise ValueError."""
        with pytest.raises(ValueError, match="Unknown scenario"):
            engine.run(scenario_type="nonexistent_scenario", params={})
