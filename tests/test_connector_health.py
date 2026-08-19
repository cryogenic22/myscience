"""D1: connector-health SLA verdict tests (pure, no DB).

Pins the staleness logic that catches silent connector death — a source whose
newest target-table row is older than its per-source SLA is flagged OVER_SLA
even when its last ETL run says SUCCESS (the exact failure mode that hid the
105-day labels/FAERS outage).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from scripts.connector_health import (
    evaluate_source_health,
    gather_ledger_health,
    roll_up,
    score_e2e,
    score_flow,
    score_strength,
    score_sync,
)

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


# ── Four-dimension scorecard primitives ──


def test_score_flow_green_amber_red():
    assert score_flow(rows=100, age_days=3, sla_days=14) == "GREEN"
    assert score_flow(rows=100, age_days=20, sla_days=14) == "AMBER"   # stale <2x
    assert score_flow(rows=100, age_days=40, sla_days=14) == "RED"     # >=2x SLA
    assert score_flow(rows=0, age_days=None, sla_days=14) == "RED"     # empty


def test_score_strength_uses_link_share():
    assert score_strength(rows=100, linked_pct=95.0) == "GREEN"
    assert score_strength(rows=100, linked_pct=65.0) == "AMBER"
    assert score_strength(rows=100, linked_pct=3.6) == "RED"           # EMA-style
    assert score_strength(rows=0, linked_pct=None) == "RED"
    # no FK to measure -> not penalised
    assert score_strength(rows=100, linked_pct=None) == "GREEN"


def test_score_sync_flags_stuck_and_never_ran():
    assert score_sync(True, "SUCCESS", runs_7d=3, stuck_running=0) == "GREEN"
    assert score_sync(True, "SUCCESS", runs_7d=3, stuck_running=2) == "RED"   # orphans
    assert score_sync(True, None, runs_7d=0, stuck_running=0) == "RED"        # never ran
    assert score_sync(True, "FAILED", runs_7d=1, stuck_running=0) == "RED"
    assert score_sync(True, "SUCCESS", runs_7d=0, stuck_running=0) == "AMBER" # cadence drift


def test_score_e2e_detects_silent_zero_vs_quiet_cycle():
    assert score_e2e(rows=100, last_inserted=5, last_updated=0) == "GREEN"
    assert score_e2e(rows=100, last_inserted=0, last_updated=0) == "AMBER"  # quiet/zero
    assert score_e2e(rows=0, last_inserted=0, last_updated=0) == "RED"      # never landed


def test_roll_up_is_worst_of_four_with_deferred_override():
    assert roll_up("GREEN", "GREEN", "GREEN", "GREEN", deferred=False) == "GREEN"
    assert roll_up("GREEN", "RED", "GREEN", "AMBER", deferred=False) == "RED"
    assert roll_up("GREEN", "AMBER", "GREEN", "GREEN", deferred=False) == "AMBER"
    # a documented dead source is DEFERRED, not a RED regression
    assert roll_up("RED", "RED", "GREEN", "RED", deferred=True) == "DEFERRED"


# ── Ledger-freshness Lane-2 wiring (gather_ledger_health) ──
#
# The pure verdict is already pinned in test_ledger_convergence_scheduling.py; these
# exercise the LIVE gather that reads facts/evidence_records and the graceful-degrade
# path, using a minimal RealDictCursor stand-in so they stay DB-free.


class _FakeLedgerCursor:
    """Answers gather_ledger_health's `SELECT count(*), max(<col>) FROM <table>` per
    ledger table from a fixture; a table mapped to ``None`` raises (missing table)."""

    def __init__(self, table_rows):
        self._table_rows = table_rows      # {table: (count, newest_dt) | None}
        self._hit = None

    def execute(self, sql, params=None):
        self._hit = None
        for table, val in self._table_rows.items():
            if f"FROM {table}" in sql:
                if val is None:
                    raise RuntimeError(f"relation {table} does not exist")
                self._hit = table
                return

    def fetchone(self):
        n, newest = self._table_rows[self._hit]
        return {"n": n, "newest": newest}


class _FakeLedgerConn:
    def __init__(self, table_rows):
        self._table_rows = table_rows
        self.rollbacks = 0

    def cursor(self, cursor_factory=None):
        return _FakeLedgerCursor(self._table_rows)

    def rollback(self):
        self.rollbacks += 1


def test_gather_ledger_health_flags_frozen_facts_ledger():
    """The 27-Jun freeze: facts 12 days stale (>3d SLA) must read unhealthy even
    while evidence is fresh — a re-freeze can no longer hide behind green ingest."""
    now = datetime.now(timezone.utc)
    conn = _FakeLedgerConn({
        "facts": (15051, now - timedelta(days=12)),
        "evidence_records": (14980, now - timedelta(hours=6)),
    })
    out = {h.source: h for h in gather_ledger_health(conn)}
    assert set(out) == {"facts_ledger", "evidence_ledger"}
    assert out["facts_ledger"].over_sla and not out["facts_ledger"].healthy
    assert out["evidence_ledger"].healthy and not out["evidence_ledger"].over_sla


def test_gather_ledger_health_all_fresh_is_healthy():
    now = datetime.now(timezone.utc)
    conn = _FakeLedgerConn({
        "facts": (15051, now - timedelta(hours=3)),
        "evidence_records": (14980, now - timedelta(hours=3)),
    })
    assert all(h.healthy for h in gather_ledger_health(conn))


def test_gather_ledger_health_empty_ledger_is_unhealthy():
    conn = _FakeLedgerConn({"facts": (0, None), "evidence_records": (0, None)})
    assert all(not h.healthy for h in gather_ledger_health(conn))


def test_gather_ledger_health_degrades_gracefully_on_missing_table():
    """A missing table/column (fresh DB) rolls back and reports empty→unhealthy —
    it must never crash the scorecard."""
    conn = _FakeLedgerConn({"facts": None, "evidence_records": None})
    out = gather_ledger_health(conn)
    assert len(out) == 2 and all(not h.healthy for h in out)
    assert conn.rollbacks == 2
