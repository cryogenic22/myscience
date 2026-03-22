"""Tests for scripts/backfill_ta_links.py — TA linkage and trial labels.

TDD: Verify backfill logic with MockDB (no real database needed).
"""

from __future__ import annotations

import re
from unittest.mock import MagicMock

import pytest


# ── MockDB with write tracking ──

class MockDB:
    """Mock database that tracks reads and writes."""

    def __init__(self):
        self._results: dict[str, list[dict]] = {}
        self.executed: list[tuple[str, list]] = []

    def set_results(self, key: str, results: list[dict]):
        self._results[key] = results

    def fetch_all(self, sql: str, params=None) -> list[dict]:
        sql_lower = sql.lower()
        from_match = re.search(r'\bfrom\s+(\w+)', sql_lower)
        if from_match:
            primary = from_match.group(1)
            if primary in self._results:
                return self._results[primary]
        for key, results in self._results.items():
            if key in sql_lower:
                return results
        return []

    def fetch_one(self, sql: str, params=None) -> dict | None:
        results = self.fetch_all(sql, params)
        return results[0] if results else None

    def execute(self, sql: str, params=None) -> None:
        self.executed.append((sql, params or []))


@pytest.fixture
def db():
    mock = MockDB()
    # Simulate 'label' column existing in clinical_trials
    mock.set_results("information_schema", [{"column_name": "label"}])
    return mock


# ── Tests for fill_trial_labels ──

class TestFillTrialLabels:
    def test_fills_label_from_official_title(self, db):
        db.set_results("clinical_trials", [
            {"id": "NCT001", "official_title": "A study of X"},
        ])

        from scripts.backfill_ta_links import fill_trial_labels
        count = fill_trial_labels(db, dry_run=False)

        assert count == 1
        # Should have issued UPDATE + INSERT into change_log
        updates = [s for s, _ in db.executed if "UPDATE clinical_trials" in s]
        assert len(updates) == 1

    def test_fills_label_from_official_title_when_present(self, db):
        db.set_results("clinical_trials", [
            {"id": "NCT002", "official_title": "Official title here"},
        ])

        from scripts.backfill_ta_links import fill_trial_labels
        count = fill_trial_labels(db, dry_run=False)

        assert count == 1

    def test_falls_back_to_nct_id(self, db):
        db.set_results("clinical_trials", [
            {"id": "NCT003", "official_title": None},
        ])

        from scripts.backfill_ta_links import fill_trial_labels
        count = fill_trial_labels(db, dry_run=False)

        assert count == 1
        # The label should be the NCT ID
        update_params = [p for s, p in db.executed if "UPDATE clinical_trials" in s]
        assert update_params[0][0] == "NCT003"

    def test_dry_run_does_not_write(self, db):
        db.set_results("clinical_trials", [
            {"id": "NCT004", "official_title": "Test"},
        ])

        from scripts.backfill_ta_links import fill_trial_labels
        count = fill_trial_labels(db, dry_run=True)

        assert count == 1
        assert len(db.executed) == 0

    def test_truncates_long_titles(self, db):
        long_title = "A" * 400
        db.set_results("clinical_trials", [
            {"id": "NCT005", "official_title": long_title},
        ])

        from scripts.backfill_ta_links import fill_trial_labels
        fill_trial_labels(db, dry_run=False)

        update_params = [p for s, p in db.executed if "UPDATE clinical_trials" in s]
        assert len(update_params[0][0]) == 300  # 297 + "..."


# ── Tests for TA keyword matching ──

class TestTAConditionKeywords:
    def test_type1_diabetes_keywords(self):
        from scripts.backfill_ta_links import TA_CONDITION_KEYWORDS
        keywords = TA_CONDITION_KEYWORDS["Diabetes Mellitus, Type 1"]
        assert "type 1 diabetes" in keywords
        assert "t1dm" in keywords

    def test_hfpef_keywords(self):
        from scripts.backfill_ta_links import TA_CONDITION_KEYWORDS
        keywords = TA_CONDITION_KEYWORDS["Heart Failure, Diastolic"]
        assert "hfpef" in keywords
        assert "preserved ejection fraction" in keywords

    def test_ckd_keywords(self):
        from scripts.backfill_ta_links import TA_CONDITION_KEYWORDS
        keywords = TA_CONDITION_KEYWORDS["Renal Insufficiency, Chronic"]
        assert "chronic kidney disease" in keywords
        assert "ckd" in keywords


# ── Tests for link creation helpers ──

class TestLinkHelpers:
    def test_link_exists_returns_false_when_empty(self, db):
        from scripts.backfill_ta_links import _link_exists
        assert not _link_exists(db, "a", "drug", "b", "ta", "IN_THERAPEUTIC_AREA")

    def test_link_exists_returns_true_when_found(self, db):
        db.set_results("entity_links", [{"id": 1}])
        from scripts.backfill_ta_links import _link_exists
        assert _link_exists(db, "a", "drug", "b", "ta", "IN_THERAPEUTIC_AREA")

    def test_create_link_skips_duplicate(self, db):
        db.set_results("entity_links", [{"id": 1}])
        from scripts.backfill_ta_links import _create_link
        _create_link(db, "a", "drug", "b", "ta", "IN_THERAPEUTIC_AREA")
        # Should not insert since link already exists
        inserts = [s for s, _ in db.executed if "INSERT INTO entity_links" in s]
        assert len(inserts) == 0
