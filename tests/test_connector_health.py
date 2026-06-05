"""D1: connector-health SLA verdict tests (pure, no DB).

Pins the staleness logic that catches silent connector death — a source whose
newest target-table row is older than its per-source SLA is flagged OVER_SLA
even when its last ETL run says SUCCESS (the exact failure mode that hid the
105-day labels/FAERS outage).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from scripts.connector_health import evaluate_source_health

NOW = datetime(2026, 6, 5, 12, 0, tzinfo=timezone.utc)


def _h(rows, age_days, status="SUCCESS", sla=14):
    newest = NOW - timedelta(days=age_days) if age_days is not None else None
    return evaluate_source_health(
        "openfda_labels", "drug_labels", sla, rows, newest, status, NOW, None, now=NOW
    )


def test_fresh_source_within_sla_is_healthy():
    h = _h(rows=185, age_days=3, sla=14)
    assert not h.over_sla
    assert h.healthy
    assert h.age_days == 3.0


def test_stale_source_over_sla_despite_success_is_unhealthy():
    """The labels/FAERS failure mode: SUCCESS run, but 105-day-old data."""
    h = _h(rows=185, age_days=105, status="SUCCESS", sla=14)
    assert h.over_sla
    assert not h.healthy


def test_empty_table_is_over_sla():
    h = _h(rows=0, age_days=None, status="SUCCESS")
    assert h.over_sla
    assert not h.healthy


def test_failed_last_run_is_unhealthy_even_if_fresh():
    h = _h(rows=185, age_days=1, status="FAILURE", sla=14)
    assert not h.over_sla  # data is fresh
    assert not h.healthy   # but the run failed


def test_failed_variant_spelling_recognized():
    assert not _h(rows=10, age_days=1, status="FAILED").healthy


def test_age_exactly_at_sla_boundary_is_ok():
    # age == sla is within SLA (strictly greater is over)
    assert not _h(rows=5, age_days=14, sla=14).over_sla
