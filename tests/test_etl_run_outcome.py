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
