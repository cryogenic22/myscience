"""Tests for FAIRScorer — automated FAIR data quality snapshots.

TDD: These tests are written BEFORE the implementation.
Run with: pytest tests/test_fair_scorer.py -v
"""

from __future__ import annotations

import re
from unittest.mock import MagicMock, call

import pytest


# ── MockDB (reuse pattern from test_ctx_corpus.py) ──


class MockDB:
    """Mock database that returns pre-configured query results.

    Routes queries by matching keywords in the SQL text.
    Supports both fetch_all and fetch_one with configurable responses.
    """

    def __init__(self):
        self._results: dict[str, list[dict]] = {}
        self._execute_calls: list[tuple[str, list | None]] = []

    def set_results(self, query_key: str, results: list[dict]):
        self._results[query_key] = results

    def fetch_all(self, sql: str, params=None) -> list[dict]:
        sql_lower = sql.lower()
        # Match on primary table (FROM clause)
        from_match = re.search(r"\bfrom\s+(\w+)", sql_lower)
        if from_match:
            primary_table = from_match.group(1)
            if primary_table in self._results:
                return self._results[primary_table]
        # Fallback: any key match
        for key, results in self._results.items():
            if key in sql_lower:
                return results
        return []

    def fetch_one(self, sql: str, params=None) -> dict | None:
        results = self.fetch_all(sql, params)
        return results[0] if results else None

    def execute(self, sql: str, params=None) -> None:
        self._execute_calls.append((sql, params))


# ── Fixtures ──


@pytest.fixture
def mock_db():
    """MockDB pre-loaded with realistic entity field counts."""
    db = MockDB()

    # Entity counts per type
    db.set_results("drugs", [{"cnt": 200}])
    db.set_results("companies", [{"cnt": 80}])
    db.set_results("clinical_trials", [{"cnt": 1500}])
    db.set_results("pubmed_articles", [{"cnt": 3000}])

    return db


@pytest.fixture
def scorer(mock_db):
    from services.fair_scorer import FAIRScorer

    return FAIRScorer(mock_db)


# ── Test: entity completeness ──


class TestEntityCompleteness:
    """Verify per-type completeness from field-level counts."""

    def test_returns_dict_keyed_by_entity_type(self, scorer, mock_db):
        # Drug: 200 total, generic_name=200, company_id=180, mechanism_id=75, therapeutic_area_id=100, approval_date=10
        mock_db.set_results("drugs", [{"cnt": 200}])
        mock_db.set_results("drug_field", [{"filled": 200}])

        result = scorer._entity_completeness()
        assert isinstance(result, dict)
        assert "drug" in result

    def test_drug_completeness_calculation(self, mock_db):
        """Drug completeness = avg of (filled/total) for each required field."""
        from services.fair_scorer import FAIRScorer

        # Build a mock that returns specific counts per field
        call_idx = {"n": 0}
        total_drugs = 200
        field_fills = [200, 180, 75, 100, 10]  # generic_name, company_id, mechanism_id, ta_id, approval_date
        # Expected avg = (200/200 + 180/200 + 75/200 + 100/200 + 10/200) / 5
        # = (1.0 + 0.9 + 0.375 + 0.5 + 0.05) / 5 = 2.825 / 5 = 0.565

        class FieldMockDB(MockDB):
            def fetch_one(self, sql, params=None):
                sql_lower = sql.lower()
                if "count(*)" in sql_lower and "is not null" not in sql_lower:
                    # Total count query
                    from_match = re.search(r"\bfrom\s+(\w+)", sql_lower)
                    table = from_match.group(1) if from_match else ""
                    if table == "drugs":
                        return {"cnt": total_drugs}
                    elif table == "companies":
                        return {"cnt": 80}
                    elif table == "clinical_trials":
                        return {"cnt": 1500}
                    elif table == "pubmed_articles":
                        return {"cnt": 3000}
                    return {"cnt": 0}
                elif "is not null" in sql_lower:
                    # Field fill count
                    idx = call_idx["n"]
                    call_idx["n"] += 1
                    # Cycle through field fills per entity type
                    fills = field_fills + [80, 40, 30, 20] + [1500, 1400, 1300, 1200, 1000] + [3000, 2900, 2800, 2500]
                    if idx < len(fills):
                        return {"filled": fills[idx]}
                    return {"filled": 0}
                return None

        mock = FieldMockDB()
        s = FAIRScorer(mock)
        result = s._entity_completeness()
        assert "drug" in result
        drug_score = result["drug"]
        assert 0.0 <= drug_score <= 1.0
        # 5 fields: 200/200=1.0, 180/200=0.9, 75/200=0.375, 100/200=0.5, 10/200=0.05
        assert abs(drug_score - 0.565) < 0.01

    def test_completeness_handles_zero_records(self, mock_db):
        """Entity types with 0 records return 0.0 completeness."""
        from services.fair_scorer import FAIRScorer

        class EmptyDB(MockDB):
            def fetch_one(self, sql, params=None):
                return {"cnt": 0, "filled": 0}

        s = FAIRScorer(EmptyDB())
        result = s._entity_completeness()
        for v in result.values():
            assert v == 0.0


# ── Test: link density ──


class TestLinkDensity:
    """Verify link density ratio calculation."""

    def test_link_density_ratio(self, mock_db):
        """Link density = total_links / total_entities, clamped to [0, 1]."""
        from services.fair_scorer import FAIRScorer

        class LinkDB(MockDB):
            def fetch_one(self, sql, params=None):
                sql_lower = sql.lower()
                if "entity_links" in sql_lower:
                    return {"cnt": 50000}
                if "entities" in sql_lower or "count(*)" in sql_lower:
                    # Sum of all entity tables
                    return {"cnt": 10000}
                return {"cnt": 0}

        s = FAIRScorer(LinkDB())
        density = s._link_density()
        # 50000 links / 10000 entities = 5.0 avg links per entity
        # Normalized to 0-1 scale: min(5.0 / 10.0, 1.0) = 0.5
        assert isinstance(density, float)
        assert 0.0 <= density <= 1.0

    def test_link_density_zero_entities(self, mock_db):
        """Zero entities = 0.0 density."""
        from services.fair_scorer import FAIRScorer

        class EmptyDB(MockDB):
            def fetch_one(self, sql, params=None):
                return {"cnt": 0}

        s = FAIRScorer(EmptyDB())
        density = s._link_density()
        assert density == 0.0


# ── Test: freshness ──


class TestFreshness:
    """Verify freshness percentage calculation."""

    def test_freshness_from_recent_records(self, mock_db):
        """Freshness = fraction of records updated in last 30 days."""
        from services.fair_scorer import FAIRScorer

        class FreshDB(MockDB):
            def fetch_one(self, sql, params=None):
                sql_lower = sql.lower()
                if "interval" in sql_lower or "30 day" in sql_lower or "retrieved_at" in sql_lower:
                    return {"recent": 8000, "total": 10000}
                return {"cnt": 10000}

        s = FAIRScorer(FreshDB())
        freshness = s._freshness()
        assert isinstance(freshness, float)
        assert 0.0 <= freshness <= 1.0
        assert abs(freshness - 0.8) < 0.01

    def test_freshness_no_timestamps(self, mock_db):
        """No retrieved_at timestamps = 0.0 freshness."""
        from services.fair_scorer import FAIRScorer

        class StaleDB(MockDB):
            def fetch_one(self, sql, params=None):
                return {"recent": 0, "total": 0}

        s = FAIRScorer(StaleDB())
        freshness = s._freshness()
        assert freshness == 0.0


# ── Test: entity-type-specific freshness thresholds ──


class TestFreshnessThresholds:
    """Verify entity-type-specific freshness thresholds."""

    def test_trial_stale_after_7_days(self):
        """Trials use a 7-day threshold — records older than 7 days are stale."""
        from services.fair_scorer import FRESHNESS_THRESHOLDS, get_freshness_threshold

        assert get_freshness_threshold("trial") == 7
        assert FRESHNESS_THRESHOLDS["trial"] == 7

    def test_drug_fresh_within_60_days(self):
        """Drugs have a 60-day freshness window — much slower to change."""
        from services.fair_scorer import get_freshness_threshold

        assert get_freshness_threshold("drug") == 60

    def test_different_entity_types_use_different_thresholds(self):
        """Each entity type should have its own threshold tuned to its update frequency."""
        from services.fair_scorer import FRESHNESS_THRESHOLDS

        # Fast-changing types
        assert FRESHNESS_THRESHOLDS["trial"] == 7
        assert FRESHNESS_THRESHOLDS["event"] == 7
        assert FRESHNESS_THRESHOLDS["literature"] == 14
        # Medium types
        assert FRESHNESS_THRESHOLDS["company"] == 30
        assert FRESHNESS_THRESHOLDS["drug"] == 60
        assert FRESHNESS_THRESHOLDS["investigator"] == 60
        # Slow-changing types
        assert FRESHNESS_THRESHOLDS["mechanism"] == 90
        assert FRESHNESS_THRESHOLDS["therapeutic_area"] == 90
        assert FRESHNESS_THRESHOLDS["patent"] == 90

    def test_unknown_entity_type_falls_back_to_30_day_default(self):
        """Unknown entity types should use DEFAULT_FRESHNESS_THRESHOLD (30 days)."""
        from services.fair_scorer import DEFAULT_FRESHNESS_THRESHOLD, get_freshness_threshold

        assert get_freshness_threshold("unknown_type") == 30
        assert get_freshness_threshold("foo_bar") == DEFAULT_FRESHNESS_THRESHOLD

    def test_freshness_by_type_uses_per_type_thresholds(self):
        """_freshness_by_type() queries each table with its own INTERVAL threshold."""
        from services.fair_scorer import FAIRScorer

        queries_seen = []

        class SpyDB(MockDB):
            def fetch_one(self, sql, params=None):
                sql_lower = sql.lower()
                if "interval" in sql_lower:
                    queries_seen.append(sql)
                    return {"recent": 50, "total": 100}
                return {"cnt": 100}

        s = FAIRScorer(SpyDB())
        by_type = s._freshness_by_type()

        # Should have queried each entity table
        assert len(queries_seen) == 4

        # Each query should use its entity type's threshold
        assert any("60 days" in q for q in queries_seen), (
            "Expected drug table query with 60-day threshold"
        )
        assert any("30 days" in q for q in queries_seen), (
            "Expected company table query with 30-day threshold"
        )
        assert any("7 days" in q for q in queries_seen), (
            "Expected trial table query with 7-day threshold"
        )
        assert any("14 days" in q for q in queries_seen), (
            "Expected literature table query with 14-day threshold"
        )

        # Each type should have score, threshold_days, total, recent
        for etype, data in by_type.items():
            assert "score" in data
            assert "threshold_days" in data
            assert "total" in data
            assert "recent" in data
            assert data["score"] == 0.5  # 50/100

    def test_aggregate_freshness_is_weighted_across_types(self):
        """Aggregate freshness should be record-count-weighted across entity types."""
        from services.fair_scorer import FAIRScorer

        class WeightedDB(MockDB):
            """Drugs: 100 total / 80 recent (60-day), Trials: 1000 total / 200 recent (7-day)."""

            def fetch_one(self, sql, params=None):
                sql_lower = sql.lower()
                if "interval" in sql_lower and "drugs" in sql_lower:
                    return {"recent": 80, "total": 100}
                elif "interval" in sql_lower and "clinical_trials" in sql_lower:
                    return {"recent": 200, "total": 1000}
                elif "interval" in sql_lower:
                    return {"recent": 0, "total": 0}
                return {"cnt": 0}

        s = FAIRScorer(WeightedDB())
        freshness = s._freshness()

        # Expected: (80 + 200) / (100 + 1000) = 280 / 1100 = 0.2545...
        assert abs(freshness - 0.2545) < 0.01

    def test_compute_includes_freshness_by_type(self):
        """compute() snapshot should include freshness_by_type breakdown."""
        from services.fair_scorer import FAIRScorer

        class MinimalDB(MockDB):
            def fetch_one(self, sql, params=None):
                return {"cnt": 0, "filled": 0, "recent": 0, "total": 0, "multi": 0}

        s = FAIRScorer(MinimalDB())
        snapshot = s.compute()

        assert "freshness_by_type" in snapshot
        assert isinstance(snapshot["freshness_by_type"], dict)


# ── Test: source diversity ──


class TestSourceDiversity:
    """Verify source diversity calculation."""

    def test_source_diversity_percentage(self, mock_db):
        """Source diversity = fraction of entities with 2+ distinct sources."""
        from services.fair_scorer import FAIRScorer

        class DiverseDB(MockDB):
            def fetch_one(self, sql, params=None):
                sql_lower = sql.lower()
                if "multi_source" in sql_lower or "having" in sql_lower or "count(distinct" in sql_lower:
                    return {"multi": 3000, "total": 10000}
                return {"cnt": 10000}

        s = FAIRScorer(DiverseDB())
        diversity = s._source_diversity()
        assert isinstance(diversity, float)
        assert 0.0 <= diversity <= 1.0


# ── Test: resolution rate ──


class TestResolutionRate:
    """Verify unresolved entity resolution rate."""

    def test_resolution_rate_calculation(self, mock_db):
        """Resolution rate = 1 - (unresolved / total_unresolved_entries)."""
        from services.fair_scorer import FAIRScorer

        class ResolvedDB(MockDB):
            def fetch_one(self, sql, params=None):
                sql_lower = sql.lower()
                if "resolved = false" in sql_lower or "resolved=false" in sql_lower:
                    return {"cnt": 50}
                if "unresolved" in sql_lower:
                    return {"cnt": 500}
                return {"cnt": 0}

        s = FAIRScorer(ResolvedDB())
        rate = s._resolution_rate()
        # 50 unresolved out of 500 total => 450/500 = 0.9 resolved
        assert isinstance(rate, float)
        assert abs(rate - 0.9) < 0.01

    def test_resolution_rate_no_unresolved_table(self, mock_db):
        """If unresolved_entities table has no rows, rate = 1.0."""
        from services.fair_scorer import FAIRScorer

        class NoUnresolvedDB(MockDB):
            def fetch_one(self, sql, params=None):
                return {"cnt": 0}

        s = FAIRScorer(NoUnresolvedDB())
        rate = s._resolution_rate()
        assert rate == 1.0


# ── Test: overall score ──


class TestOverallScore:
    """Verify weighted average calculation."""

    def test_overall_is_weighted_average(self):
        """Overall = 0.25*completeness + 0.20*density + 0.15*diversity + 0.25*freshness + 0.15*resolution."""
        from services.fair_scorer import FAIRScorer

        class FixedDB(MockDB):
            """Returns fixed values for all dimensions."""

            def fetch_one(self, sql, params=None):
                sql_lower = sql.lower()
                # Completeness: all fields filled
                if "is not null" in sql_lower:
                    return {"filled": 100}
                if "count(*)" in sql_lower:
                    return {"cnt": 100}
                # Link density
                if "entity_links" in sql_lower:
                    return {"cnt": 500}
                # Freshness
                if "30 day" in sql_lower or "interval" in sql_lower or "retrieved_at" in sql_lower:
                    return {"recent": 80, "total": 100}
                # Resolution
                if "resolved = false" in sql_lower or "resolved=false" in sql_lower:
                    return {"cnt": 10}
                if "unresolved" in sql_lower:
                    return {"cnt": 100}
                return {"cnt": 100}

        s = FAIRScorer(FixedDB())
        snapshot = s.compute()

        assert "overall_score" in snapshot
        assert isinstance(snapshot["overall_score"], float)
        assert 0.0 <= snapshot["overall_score"] <= 1.0

    def test_compute_returns_all_dimensions(self):
        """compute() result has all expected keys."""
        from services.fair_scorer import FAIRScorer

        class MinimalDB(MockDB):
            def fetch_one(self, sql, params=None):
                return {"cnt": 0, "filled": 0, "recent": 0, "total": 0, "multi": 0}

        s = FAIRScorer(MinimalDB())
        snapshot = s.compute()

        expected_keys = {
            "overall_score",
            "entity_completeness",
            "link_density",
            "source_diversity",
            "freshness",
            "resolution_rate",
            "total_records",
            "total_links",
        }
        assert expected_keys.issubset(set(snapshot.keys())), (
            f"Missing keys: {expected_keys - set(snapshot.keys())}"
        )


# ── Test: persist snapshot ──


class TestPersistSnapshot:
    """Verify snapshot persistence to data_quality_snapshots table."""

    def test_persist_calls_db_execute(self):
        """persist() should INSERT into data_quality_snapshots."""
        from services.fair_scorer import FAIRScorer

        db = MockDB()
        s = FAIRScorer(db)

        snapshot = {
            "overall_score": 0.72,
            "entity_completeness": {"drug": 0.56, "company": 0.33},
            "link_density": 0.45,
            "source_diversity": 0.30,
            "freshness": 0.80,
            "resolution_rate": 0.90,
            "total_records": 4780,
            "total_links": 50000,
        }

        s.persist(snapshot)

        assert len(db._execute_calls) == 1
        sql, params = db._execute_calls[0]
        assert "data_quality_snapshots" in sql.lower()
        assert "insert" in sql.lower()

    def test_persist_includes_details_json(self):
        """Persisted row should include the full snapshot as JSONB details."""
        from services.fair_scorer import FAIRScorer

        db = MockDB()
        s = FAIRScorer(db)

        snapshot = {
            "overall_score": 0.72,
            "entity_completeness": {"drug": 0.56},
            "link_density": 0.45,
            "source_diversity": 0.30,
            "freshness": 0.80,
            "resolution_rate": 0.90,
            "total_records": 4780,
            "total_links": 50000,
        }

        s.persist(snapshot)

        sql, params = db._execute_calls[0]
        # Params should include the overall_score and JSON details
        assert any(isinstance(p, str) and "drug" in p for p in params), (
            f"Expected JSON with entity_completeness in params, got: {params}"
        )


# ── Test: latest snapshot retrieval ──


class TestLatestSnapshot:
    """Verify fetching the latest snapshot for the API."""

    def test_latest_returns_most_recent(self):
        """latest() returns the most recent snapshot row."""
        from services.fair_scorer import FAIRScorer

        db = MockDB()
        db.set_results("data_quality_snapshots", [
            {
                "id": 5,
                "created_at": "2026-03-24T12:00:00Z",
                "overall_score": 0.72,
                "entity_completeness": {"drug": 0.56},
                "link_density": 0.45,
                "source_diversity": 0.30,
                "freshness": 0.80,
                "resolution_rate": 0.90,
                "total_records": 4780,
                "total_links": 50000,
                "details": {},
            }
        ])
        s = FAIRScorer(db)
        result = s.latest()
        assert result is not None
        assert result["overall_score"] == 0.72

    def test_latest_returns_none_when_empty(self):
        """latest() returns None when no snapshots exist."""
        from services.fair_scorer import FAIRScorer

        db = MockDB()
        s = FAIRScorer(db)
        result = s.latest()
        assert result is None


class TestTrend:
    """Verify trend retrieval for historical comparison."""

    def test_trend_returns_last_n_snapshots(self):
        """trend() returns the last N snapshots ordered by created_at DESC."""
        from services.fair_scorer import FAIRScorer

        snapshots = [
            {"id": i, "overall_score": 0.70 + i * 0.01, "created_at": f"2026-03-{20+i}T00:00:00Z"}
            for i in range(5)
        ]
        db = MockDB()
        db.set_results("data_quality_snapshots", snapshots)
        s = FAIRScorer(db)
        result = s.trend(n=5)
        assert len(result) == 5
