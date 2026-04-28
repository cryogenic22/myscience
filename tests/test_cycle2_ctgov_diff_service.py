"""Cycle 2 — CT.gov diff service → trial_status_change events (TDD).

The diff service is the bridge between the existing CT.gov connector
(which fetches fresh trial snapshots) and the events table. For each
incoming snapshot it:

  1. Resolves the trial_id from nct_id (via DB lookup)
  2. Reads the trial's status_history JSONB
  3. Builds a candidate history entry from the snapshot
  4. Calls services.trial_status_history.should_append() — skip no-ops
  5. Calls diff_summary() to describe what changed
  6. Builds a market_events row (trial_status_change) and inserts it
  7. Appends the new entry to status_history (atomic per trial)

Key contract decisions tested here:

  - Initial observation (empty history) appends a baseline entry but
    does NOT emit an event. Events represent CHANGES, not the first
    snapshot. (Migration 039 backfills history for existing trials, so
    every trial we touch already has a baseline.)
  - Status change → event with payload.status_changed=True
  - Phase change → event
  - PCD slip → event with payload.pcd_slip_days populated
  - No change → no event, no history append (idempotent)
  - Unresolved nct_id → silently skip
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Optional

import pytest


# ────────────────────────────────────────────────────────────────────
# Mock DB — captures inserts + serves trial-history reads
# ────────────────────────────────────────────────────────────────────


class MockDB:
    """In-memory stand-in for db.Database.

    The diff service needs:
      - fetch_one(SELECT id, status_history FROM clinical_trials WHERE nct_id=...)
      - fetch_one(INSERT INTO market_events ... RETURNING id)
      - execute(UPDATE clinical_trials SET status_history=...)
    """

    def __init__(self):
        self.trials_by_nct: dict[str, dict] = {}
        self.events_inserted: list[dict] = []
        self.history_updates: list[tuple[str, list]] = []
        self.executed_queries: list[str] = []

    # ---- Reads -------------------------------------------------------

    def fetch_one(self, query: str, params=None):
        self.executed_queries.append(query)
        q = query.lower()
        if "from clinical_trials" in q and "nct_id" in q:
            nct = params[0] if params else None
            return self.trials_by_nct.get(nct)
        if "insert into market_events" in q:
            row_payload = self._extract_event_row(query, params)
            self.events_inserted.append(row_payload)
            return {"id": "00000000-0000-0000-0000-{:012d}".format(
                len(self.events_inserted))}
        return None

    # ---- Writes ------------------------------------------------------

    def execute(self, query: str, params=None):
        self.executed_queries.append(query)
        q = query.lower()
        if "update clinical_trials" in q and "status_history" in q:
            history_json, nct_id = params[0], params[1]
            import json
            history = json.loads(history_json) if isinstance(
                history_json, str) else history_json
            self.history_updates.append((nct_id, history))
            if nct_id in self.trials_by_nct:
                self.trials_by_nct[nct_id]["status_history"] = history

    # ---- Helpers -----------------------------------------------------

    @staticmethod
    def _extract_event_row(query: str, params) -> dict:
        """Map positional INSERT params to a dict for assertion convenience."""
        cols = [
            "event_type", "description", "primary_entity_type",
            "primary_entity_id", "primary_entity_name",
            "event_date", "disclosed_date",
            "source_tier", "trust_score", "status",
            "event_hash", "source_feed", "payload",
            "source_document_id", "corroborating_sources",
        ]
        row = {}
        for i, col in enumerate(cols):
            if i < len(params):
                row[col] = params[i]
        # payload arrives as JSON string — keep both for assertions
        if isinstance(row.get("payload"), str):
            import json
            try:
                row["payload_dict"] = json.loads(row["payload"])
            except Exception:
                pass
        return row


@pytest.fixture
def mock_db():
    return MockDB()


def _seed_trial(
    db: MockDB,
    nct_id: str,
    history: Optional[list[dict]] = None,
    trial_id: str = "00000000-0000-0000-0000-aaaaaaaaaaaa",
) -> None:
    db.trials_by_nct[nct_id] = {
        "id": trial_id,
        "nct_id": nct_id,
        "status_history": history or [],
    }


def _snapshot(
    nct_id: str,
    status: str,
    phase: str | None = "Phase 3",
    primary_completion_date: str | None = "2026-12-31",
) -> dict:
    return {
        "nct_id": nct_id,
        "overall_status": status,
        "phase": phase,
        "primary_completion_date": primary_completion_date,
    }


# ────────────────────────────────────────────────────────────────────
# Cat 1 — Module exists
# ────────────────────────────────────────────────────────────────────


class TestModuleExists:

    def test_module_imports(self):
        from services.ctgov_diff_service import process_trial_snapshot  # noqa: F401

    def test_diff_result_dataclass_exists(self):
        from services.ctgov_diff_service import DiffResult
        r = DiffResult()
        assert r.event_emitted is False
        assert r.history_appended is False
        assert r.skipped_reason is None


# ────────────────────────────────────────────────────────────────────
# Cat 2 — Trial resolution
# ────────────────────────────────────────────────────────────────────


class TestTrialResolution:

    def test_unresolved_nct_id_is_skipped(self, mock_db):
        from services.ctgov_diff_service import process_trial_snapshot
        result = process_trial_snapshot(
            snapshot=_snapshot("NCT99999999", "Recruiting"),
            db=mock_db,
        )
        assert result.event_emitted is False
        assert result.skipped_reason == "trial_not_found"

    def test_resolved_trial_proceeds(self, mock_db):
        from services.ctgov_diff_service import process_trial_snapshot
        _seed_trial(mock_db, "NCT00000001", history=[
            {"status": "Recruiting", "phase": "Phase 3",
             "primary_completion_date": "2026-12-31",
             "observed_at": "2026-01-01T00:00:00+00:00"},
        ])
        # No change in snapshot vs. history → still proceeds (returns
        # a no-op DiffResult, doesn't error)
        result = process_trial_snapshot(
            snapshot=_snapshot("NCT00000001", "Recruiting"),
            db=mock_db,
        )
        assert result.skipped_reason in (None, "no_change")


# ────────────────────────────────────────────────────────────────────
# Cat 3 — No-change observations
# ────────────────────────────────────────────────────────────────────


class TestNoChange:

    def test_identical_snapshot_emits_nothing(self, mock_db):
        from services.ctgov_diff_service import process_trial_snapshot
        _seed_trial(mock_db, "NCT001", history=[
            {"status": "Recruiting", "phase": "Phase 3",
             "primary_completion_date": "2026-12-31",
             "observed_at": "2026-01-01T00:00:00+00:00"},
        ])
        result = process_trial_snapshot(
            snapshot=_snapshot("NCT001", "Recruiting"),
            db=mock_db,
        )
        assert result.event_emitted is False
        assert result.history_appended is False
        assert mock_db.events_inserted == []
        assert mock_db.history_updates == []


# ────────────────────────────────────────────────────────────────────
# Cat 4 — Status changes
# ────────────────────────────────────────────────────────────────────


class TestStatusChange:

    def test_recruiting_to_terminated_emits_event(self, mock_db):
        from services.ctgov_diff_service import process_trial_snapshot
        _seed_trial(mock_db, "NCT002", history=[
            {"status": "Recruiting", "phase": "Phase 3",
             "primary_completion_date": "2026-12-31",
             "observed_at": "2026-01-01T00:00:00+00:00"},
        ])
        result = process_trial_snapshot(
            snapshot=_snapshot("NCT002", "Terminated"),
            db=mock_db,
        )
        assert result.event_emitted is True
        assert result.history_appended is True
        assert len(mock_db.events_inserted) == 1
        ev = mock_db.events_inserted[0]
        assert ev["event_type"] == "trial_status_change"
        assert ev["primary_entity_type"] == "trial"
        payload = ev["payload_dict"]
        assert payload["status_changed"] is True
        assert payload["prev_status"] == "Recruiting"
        assert payload["new_status"] == "Terminated"
        assert payload["nct_id"] == "NCT002"

    def test_phase_change_emits_event(self, mock_db):
        from services.ctgov_diff_service import process_trial_snapshot
        _seed_trial(mock_db, "NCT003", history=[
            {"status": "Recruiting", "phase": "Phase 2",
             "primary_completion_date": "2026-12-31",
             "observed_at": "2026-01-01T00:00:00+00:00"},
        ])
        result = process_trial_snapshot(
            snapshot=_snapshot("NCT003", "Recruiting", phase="Phase 3"),
            db=mock_db,
        )
        assert result.event_emitted is True
        ev = mock_db.events_inserted[0]
        payload = ev["payload_dict"]
        assert payload["phase_changed"] is True
        assert payload["prev_phase"] == "Phase 2"
        assert payload["new_phase"] == "Phase 3"


# ────────────────────────────────────────────────────────────────────
# Cat 5 — PCD slips
# ────────────────────────────────────────────────────────────────────


class TestPCDSlip:

    def test_pcd_slip_populates_slip_days(self, mock_db):
        from services.ctgov_diff_service import process_trial_snapshot
        _seed_trial(mock_db, "NCT004", history=[
            {"status": "Recruiting", "phase": "Phase 3",
             "primary_completion_date": "2026-06-30",
             "observed_at": "2026-01-01T00:00:00+00:00"},
        ])
        result = process_trial_snapshot(
            snapshot=_snapshot("NCT004", "Recruiting",
                               primary_completion_date="2026-12-31"),
            db=mock_db,
        )
        assert result.event_emitted is True
        ev = mock_db.events_inserted[0]
        payload = ev["payload_dict"]
        assert payload["pcd_changed"] is True
        assert payload["prev_pcd"] == "2026-06-30"
        assert payload["new_pcd"] == "2026-12-31"
        assert payload["pcd_slip_days"] == 184  # June 30 → Dec 31

    def test_pcd_pulled_in_negative_slip(self, mock_db):
        from services.ctgov_diff_service import process_trial_snapshot
        _seed_trial(mock_db, "NCT005", history=[
            {"status": "Recruiting", "phase": "Phase 3",
             "primary_completion_date": "2026-12-31",
             "observed_at": "2026-01-01T00:00:00+00:00"},
        ])
        result = process_trial_snapshot(
            snapshot=_snapshot("NCT005", "Recruiting",
                               primary_completion_date="2026-09-30"),
            db=mock_db,
        )
        assert result.event_emitted is True
        ev = mock_db.events_inserted[0]
        assert ev["payload_dict"]["pcd_slip_days"] < 0


# ────────────────────────────────────────────────────────────────────
# Cat 6 — Initial baseline (empty history)
# ────────────────────────────────────────────────────────────────────


class TestInitialBaseline:

    def test_empty_history_appends_baseline_no_event(self, mock_db):
        from services.ctgov_diff_service import process_trial_snapshot
        _seed_trial(mock_db, "NCT006", history=[])
        result = process_trial_snapshot(
            snapshot=_snapshot("NCT006", "Recruiting"),
            db=mock_db,
        )
        assert result.event_emitted is False
        assert result.history_appended is True
        assert mock_db.events_inserted == []
        assert len(mock_db.history_updates) == 1
        nct_id, history = mock_db.history_updates[0]
        assert nct_id == "NCT006"
        assert len(history) == 1
        assert history[0]["status"] == "Recruiting"


# ────────────────────────────────────────────────────────────────────
# Cat 7 — Event payload structure
# ────────────────────────────────────────────────────────────────────


class TestEventPayloadStructure:

    def test_event_has_idempotency_hash(self, mock_db):
        from services.ctgov_diff_service import process_trial_snapshot
        _seed_trial(mock_db, "NCT007", history=[
            {"status": "Recruiting", "phase": "Phase 3",
             "primary_completion_date": "2026-12-31",
             "observed_at": "2026-01-01T00:00:00+00:00"},
        ])
        result = process_trial_snapshot(
            snapshot=_snapshot("NCT007", "Completed"),
            db=mock_db,
        )
        ev = mock_db.events_inserted[0]
        assert "event_hash" in ev
        assert ev["event_hash"]
        assert len(ev["event_hash"]) == 64  # SHA-256 hex

    def test_event_carries_source_metadata(self, mock_db):
        from services.ctgov_diff_service import process_trial_snapshot
        _seed_trial(mock_db, "NCT008", history=[
            {"status": "Recruiting", "phase": "Phase 3",
             "primary_completion_date": "2026-12-31",
             "observed_at": "2026-01-01T00:00:00+00:00"},
        ])
        process_trial_snapshot(
            snapshot=_snapshot("NCT008", "Active, not recruiting"),
            db=mock_db,
        )
        ev = mock_db.events_inserted[0]
        assert ev["source_feed"] == "ctgov_diff_service"
        assert ev["source_tier"] == "tier_1"
        assert ev["status"] == "new"

    def test_event_description_human_readable(self, mock_db):
        from services.ctgov_diff_service import process_trial_snapshot
        _seed_trial(mock_db, "NCT009", history=[
            {"status": "Recruiting", "phase": "Phase 3",
             "primary_completion_date": "2026-12-31",
             "observed_at": "2026-01-01T00:00:00+00:00"},
        ])
        process_trial_snapshot(
            snapshot=_snapshot("NCT009", "Terminated"),
            db=mock_db,
        )
        ev = mock_db.events_inserted[0]
        assert "NCT009" in ev["description"]
        assert "Terminated" in ev["description"] or \
               "terminated" in ev["description"].lower()


# ────────────────────────────────────────────────────────────────────
# Cat 8 — Idempotency (same snapshot twice → only one event)
# ────────────────────────────────────────────────────────────────────


class TestIdempotency:

    def test_same_snapshot_emits_once_per_change(self, mock_db):
        """Run the same snapshot twice. The first call emits + appends.
        The second call sees the change is already in history → no-op."""
        from services.ctgov_diff_service import process_trial_snapshot

        _seed_trial(mock_db, "NCT010", history=[
            {"status": "Recruiting", "phase": "Phase 3",
             "primary_completion_date": "2026-12-31",
             "observed_at": "2026-01-01T00:00:00+00:00"},
        ])
        snap = _snapshot("NCT010", "Terminated")

        r1 = process_trial_snapshot(snapshot=snap, db=mock_db)
        assert r1.event_emitted is True
        assert r1.history_appended is True

        r2 = process_trial_snapshot(snapshot=snap, db=mock_db)
        assert r2.event_emitted is False
        assert r2.history_appended is False

        assert len(mock_db.events_inserted) == 1
        assert len(mock_db.history_updates) == 1
