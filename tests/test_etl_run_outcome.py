"""Connector run-outcome classifier (migration 088) — deterministic, DB-free.

Encodes the truth table that makes the SILENT-ZERO visible: a run that
"succeeds" but fetched nothing is FAILURE_ZERO_ROWS, not green. This is the
connector-level fix for the class that let Open Targets/EMA return 0 records and
feeds go 105 days stale under a SUCCESS status. Lane-1 conservation gate.
"""
from __future__ import annotations

import pytest

from integration.pipeline import (
    RUN_OUTCOME_FAILURE,
    RUN_OUTCOME_LANDED,
    RUN_OUTCOME_NO_CHANGE,
    RUN_OUTCOME_PARTIAL,
    RUN_OUTCOME_ZERO_ROWS,
    classify_run_outcome,
)


@pytest.mark.parametrize(
    "success,processed,inserted,updated,expected",
    [
        # fresh data landed
        (True, 100, 100, 0, RUN_OUTCOME_LANDED),
        (True, 100, 0, 40, RUN_OUTCOME_LANDED),
        (True, 100, 10, 5, RUN_OUTCOME_LANDED),
        # fetched rows, nothing changed → legitimate quiet cycle
        (True, 100, 0, 0, RUN_OUTCOME_NO_CHANGE),
        (True, 1, 0, 0, RUN_OUTCOME_NO_CHANGE),
        # the silent-zero: succeeded but fetched nothing
        (True, 0, 0, 0, RUN_OUTCOME_ZERO_ROWS),
        # partial / failed runs
        (False, 50, 50, 0, RUN_OUTCOME_PARTIAL),
        (False, 0, 0, 0, RUN_OUTCOME_PARTIAL),
    ],
)
def test_classify_run_outcome(success, processed, inserted, updated, expected):
    assert classify_run_outcome(success, processed, inserted, updated) == expected


def test_zero_rows_is_not_a_green_success():
    """The whole point: a 0-row successful run must be a FAILURE_* outcome so it
    can never read as healthy. Guards the regression that hid silent deaths."""
    out = classify_run_outcome(success=True, processed=0, inserted=0, updated=0)
    assert out.startswith("FAILURE"), f"silent-zero classified as {out!r} — would read green"


def test_handles_none_counts_defensively():
    """Counts may arrive as None from a partially-populated result; must not raise."""
    assert classify_run_outcome(True, None, None, None) == RUN_OUTCOME_ZERO_ROWS
    assert classify_run_outcome(True, 5, None, None) == RUN_OUTCOME_NO_CHANGE


# ============================================================
# Incremental quiet-window vs broken-empty (openFDA FAERS/labels false-RED fix).
# A source that has landed before, fetched incrementally, returning 0 is a
# legitimate no-change window (FAERS lags months; labels rarely change) — NOT a
# failure. Staleness stays a connector_health Lane-2 verdict (migration 088), so
# this does not re-hide the 105-day-stale disease.
# ============================================================

def test_incremental_zero_with_history_is_no_change_not_failure():
    out = classify_run_outcome(True, 0, 0, 0, incremental=True, has_history=True)
    assert out == RUN_OUTCOME_NO_CHANGE


def test_full_fetch_zero_is_still_failure_regardless_of_history():
    """A non-incremental (full) fetch returning 0 is genuinely broken."""
    assert classify_run_outcome(True, 0, 0, 0, incremental=False, has_history=True) == RUN_OUTCOME_ZERO_ROWS


def test_incremental_zero_without_history_is_failure():
    """A source that has NEVER landed, fetched incrementally, returning 0 is broken
    (never-landed), not a quiet window."""
    assert classify_run_outcome(True, 0, 0, 0, incremental=True, has_history=False) == RUN_OUTCOME_ZERO_ROWS


def test_default_params_preserve_legacy_behavior():
    """Old call sites (no incremental/history) keep the strict silent-zero verdict."""
    assert classify_run_outcome(True, 0, 0, 0) == RUN_OUTCOME_ZERO_ROWS


def test_incremental_no_change_does_not_mask_landed_or_partial():
    # landed still wins over the quiet-window path
    assert classify_run_outcome(True, 0, 5, 0, incremental=True, has_history=True) == RUN_OUTCOME_LANDED
    # a failed run is still PARTIAL even if incremental+history
    assert classify_run_outcome(False, 0, 0, 0, incremental=True, has_history=True) == RUN_OUTCOME_PARTIAL


# ============================================================
# _source_has_landed_before (DB-read path) — the has_history signal + fail-closed.
# ============================================================

class _StubDB:
    def __init__(self, row=None, raises=False):
        self._row, self._raises = row, raises
        self.last_params = None

    def fetch_one(self, sql, params=None):
        if self._raises:
            raise RuntimeError("db down")
        self.last_params = params
        return self._row


def _bare_pipeline(db):
    """A pipeline instance without the heavy __init__ (we only test one method)."""
    from integration.pipeline import IntegrationPipeline
    p = IntegrationPipeline.__new__(IntegrationPipeline)
    p.db = db
    return p


def test_source_has_landed_before_true_when_prior_landed():
    p = _bare_pipeline(_StubDB(row={"?column?": 1}))
    assert p._source_has_landed_before("openfda_faers", "run-1") is True
    assert "openfda_faers" in p.db.last_params and "run-1" in p.db.last_params


def test_source_has_landed_before_false_when_never_landed():
    assert _bare_pipeline(_StubDB(row=None))._source_has_landed_before("x", "run-1") is False


def test_source_has_landed_before_fails_closed_on_db_error():
    """A health-query error must fail CLOSED (no history -> strict ZERO_ROWS)."""
    assert _bare_pipeline(_StubDB(raises=True))._source_has_landed_before("x", "run-1") is False
