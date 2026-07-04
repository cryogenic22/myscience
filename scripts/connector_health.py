#!/usr/bin/env python
"""Connector health & sync-verification scorecard (D1).

The one command the team runs each morning. For every scheduled source it
scores four dimensions and rolls them into a RED / AMBER / GREEN verdict:

  FLOW      — target-table row count + newest-row age vs the per-source SLA.
              The antidote to the silent-failure mode that let openFDA
              Labels/FAERS go 105 days stale while logging SUCCESS (staleness
              is judged on newest-row age, NOT the run's self-reported status).
  STRENGTH  — volume + the share of rows that resolve onto the entity spine
              (FK-NULL share). A source that stores rows but never links them
              is half-broken.
  SYNC      — is it scheduled? does etl_runs show a recent terminal SUCCESS at
              the expected cadence, with no stuck-RUNNING orphans?
  E2E       — does the most-recent run actually persist rows (records_inserted
              + records_updated > 0), i.e. fetch→store path intact? A run that
              SUCCEEDs with 0 records every cycle (Open Targets schema drift,
              NADAC dead endpoint) is the canonical silent zero.

Read-only. Usage:
    python scripts/connector_health.py "<postgres url>"
    DATABASE_URL=... python scripts/connector_health.py
    python scripts/connector_health.py --json   # machine-readable

Exit code is non-zero when any source is RED (over SLA / no terminal status /
0 rows when scheduled / last run FAILED), so it can gate CI / a morning cron.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Optional

import psycopg2
import psycopg2.extras

# Allow `python scripts/connector_health.py` (not just `-m scripts.…`) by
# putting the repo root on the path.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scheduler.config import (  # noqa: E402
    CONNECTOR_SCHEDULES,
    FRESHNESS_SLA_DAYS,
    KNOWN_DEFERRED_SOURCES,
    LEDGER_FRESHNESS_SLA_DAYS,
)

# How long an etl_runs row may stay RUNNING before we treat it as an orphan
# left behind by a killed process (Railway restart / proxy drop). The pipeline
# sets a terminal status in a try/except, so a row older than this that is
# still RUNNING means the process died mid-run.
STUCK_RUNNING_HOURS = 12

# Spine-FK columns per target table: lets STRENGTH measure the share of stored
# rows that actually resolve onto the entity spine. Omitted tables score
# strength on volume alone.
SPINE_FK: dict[str, str] = {
    "clinical_trials": "drug_id",
    "adverse_events": "drug_id",
    "drug_labels": "drug_id",
    "pubmed_articles": "drug_id",
    "pmc_articles": "pubmed_id",
    "market_events": "primary_entity_id",
    "bioactivities": "drug_id",
    "regulatory_milestones": "drug_id",
}


# ── Pure verdict primitives (unit-testable, no DB) ──


@dataclass
class SourceHealth:
    source: str
    table: str
    rows: int
    newest: Optional[str]
    age_days: Optional[float]
    sla_days: int
    over_sla: bool
    last_run_status: Optional[str]
    last_run_at: Optional[str]
    last_error: Optional[str]
    healthy: bool


@dataclass
class SourceScore:
    """Full four-dimension scorecard row for one source."""
    source: str
    table: str
    scheduled: bool
    deferred: bool
    # flow
    rows: int = 0
    age_days: Optional[float] = None
    sla_days: int = 0
    flow: str = "RED"
    # strength
    linked_pct: Optional[float] = None      # share of rows resolving onto spine
    strength: str = "RED"
    # sync
    last_run_status: Optional[str] = None
    last_run_at: Optional[str] = None
    runs_7d: int = 0
    stuck_running: int = 0
    sync: str = "RED"
    # e2e
    last_inserted: Optional[int] = None
    last_updated: Optional[int] = None
    e2e: str = "RED"
    # roll-up
    verdict: str = "RED"
    notes: list[str] = field(default_factory=list)


# DLQ backlog: the fail-closed skip (#300) and the DLQ (failed_records) were
# SILENT to Lane-2 — open_targets bled 3,121 records over 18 days while every run
# logged SUCCESS, because a skip / DLQ insert surfaced nowhere. A backlog that
# GROWS is a live bleed (RED); a stable non-zero backlog is known debt awaiting
# the replay loops (AMBER — never silently GREEN); empty/draining is GREEN. The
# window is trailing so the existing static backlog does not pin RED forever.
DLQ_WINDOW_DAYS = 7
DLQ_GROWTH_RED = 100   # new pending OR fail-closed skips within the window → RED


@dataclass
class DLQHealth:
    """Live dead-letter-queue backlog snapshot for the Lane-2 health gate.

    Surfaces what was silent: pending failed_records, how fast the backlog is
    growing (records created in the trailing window), and the trailing-window
    fail-closed skip volume (the #300 path, which never reaches the DLQ)."""
    pending_total: int = 0
    pending_recent: int = 0          # failed_records created in the window
    skipped_recent: int = 0          # sum(etl_runs.records_skipped) in the window
    window_days: int = DLQ_WINDOW_DAYS
    verdict: str = "GREEN"
    top_causes: list[str] = field(default_factory=list)


def _age_days(newest: Optional[datetime], now: datetime) -> Optional[float]:
    if newest is None:
        return None
    if newest.tzinfo is None:
        newest = newest.replace(tzinfo=timezone.utc)
    return round((now - newest).total_seconds() / 86400.0, 1)


def evaluate_source_health(
    source: str,
    table: str,
    sla_days: int,
    rows: int,
    newest: Optional[datetime],
    last_run_status: Optional[str],
    last_run_at: Optional[datetime],
    last_error: Optional[str],
    now: Optional[datetime] = None,
) -> SourceHealth:
    """Pure SLA/health verdict for one source (unit-testable, no DB).

    A source is unhealthy if: no rows, no recency timestamp, age exceeds SLA,
    or its most-recent run terminally FAILED.
    """
    now = now or datetime.now(timezone.utc)
    age = _age_days(newest, now)
    over_sla = (
        rows == 0
        or age is None
        or age > sla_days
    )
    run_failed = bool(last_run_status) and last_run_status.upper() in {"FAILURE", "FAILED"}
    return SourceHealth(
        source=source,
        table=table,
        rows=rows,
        newest=newest.isoformat() if newest else None,
        age_days=age,
        sla_days=sla_days,
        over_sla=over_sla,
        last_run_status=last_run_status,
        last_run_at=last_run_at.isoformat() if last_run_at else None,
        last_error=(last_error[:160] if last_error else None),
        healthy=(not over_sla and not run_failed),
    )


def score_flow(rows: int, age_days: Optional[float], sla_days: int) -> str:
    """GREEN within SLA; AMBER stale but <2x SLA; RED empty or >=2x SLA."""
    if rows == 0 or age_days is None:
        return "RED"
    if age_days <= sla_days:
        return "GREEN"
    if age_days <= sla_days * 2:
        return "AMBER"
    return "RED"


def score_strength(rows: int, linked_pct: Optional[float]) -> str:
    """GREEN if rows present and >=80% resolve onto the spine (or no FK to
    measure); AMBER 50-80% linked; RED no rows or <50% linked."""
    if rows == 0:
        return "RED"
    if linked_pct is None:
        return "GREEN"  # no spine FK to measure — volume-only, not penalised
    if linked_pct >= 80.0:
        return "GREEN"
    if linked_pct >= 50.0:
        return "AMBER"
    return "RED"


def score_dlq(pending_total: int, pending_recent: int, skipped_recent: int) -> str:
    """Pure DLQ-backlog health verdict (no DB). See DLQ_GROWTH_RED / DLQ_WINDOW_DAYS.

    ``pending_recent`` / ``skipped_recent`` measure only the trailing window, so a
    real *bleed* (the open_targets signature) reds within ~a day while the known
    static backlog awaiting replay stays AMBER instead of pinning RED. Benign,
    self-healing causes (pubchem dup-key, ctgov disk-full) are not yet excluded —
    that classification is a follow-up loop; the 100/window threshold keeps
    today's ~10 benign/week comfortably under RED.
    """
    if pending_recent >= DLQ_GROWTH_RED or skipped_recent >= DLQ_GROWTH_RED:
        return "RED"
    if (pending_total or 0) > 0 or (skipped_recent or 0) > 0:
        return "AMBER"
    return "GREEN"


def score_sync(
    scheduled: bool,
    last_run_status: Optional[str],
    runs_7d: int,
    stuck_running: int,
) -> str:
    """RED if scheduled but never ran, last run FAILED, or it has stuck-RUNNING
    orphans; AMBER if scheduled but no terminal run in the last 7d; GREEN
    otherwise."""
    if not scheduled:
        return "AMBER"
    status = (last_run_status or "").upper()
    if not last_run_status:
        return "RED"
    if status in {"FAILURE", "FAILED"}:
        return "RED"
    if stuck_running > 0:
        return "RED"
    if runs_7d == 0:
        return "AMBER"
    return "GREEN"


def score_e2e(rows: int, last_inserted: Optional[int], last_updated: Optional[int]) -> str:
    """Did the most-recent run actually move data? GREEN if it inserted/updated
    rows; AMBER if it processed nothing but the table is non-empty (a quiet
    cycle is normal for slow sources); RED if the table is empty (never landed
    anything)."""
    if rows == 0:
        return "RED"
    moved = (last_inserted or 0) + (last_updated or 0)
    if moved > 0:
        return "GREEN"
    return "AMBER"


def roll_up(flow: str, strength: str, sync: str, e2e: str, deferred: bool) -> str:
    """Worst-of the four dimensions, except deferred sources cap at AMBER and
    are reported as DEFERRED (a documented dead source isn't a regression)."""
    if deferred:
        return "DEFERRED"
    order = {"GREEN": 0, "AMBER": 1, "RED": 2}
    worst = max((flow, strength, sync, e2e), key=lambda v: order.get(v, 2))
    return worst


# ── DB gather ──


def _get_db_url() -> str:
    for a in sys.argv[1:]:
        if a.startswith("postgres"):
            return a
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("Pass a postgres URL as an argument or set DATABASE_URL.")
    return url


def gather(conn) -> list[SourceHealth]:
    """Legacy flow-only health list (kept for callers/tests that use it)."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    now = datetime.now(timezone.utc)
    out: list[SourceHealth] = []
    for source_type, (table, recency_col, sla_days) in FRESHNESS_SLA_DAYS.items():
        source = source_type.value
        rows, newest = 0, None
        try:
            cur.execute(f"SELECT count(*) AS n, max({recency_col}) AS newest FROM {table}")
            r = cur.fetchone()
            rows, newest = r["n"], r["newest"]
        except Exception:
            conn.rollback()
        status = run_at = err = None
        try:
            cur.execute(
                """
                SELECT status, COALESCE(completed_at, started_at) AS run_at, error_message
                FROM etl_runs WHERE source_name = %s
                ORDER BY started_at DESC LIMIT 1
                """,
                [source],
            )
            row = cur.fetchone()
            if row:
                status, run_at, err = row["status"], row["run_at"], row["error_message"]
        except Exception:
            conn.rollback()
        out.append(
            evaluate_source_health(
                source, table, sla_days, rows, newest, status, run_at, err, now
            )
        )
    return out


def gather_scorecard(conn) -> list[SourceScore]:
    """Full four-dimension scorecard, one row per scheduled source."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    now = datetime.now(timezone.utc)
    out: list[SourceScore] = []

    for source_type in CONNECTOR_SCHEDULES:
        source = source_type.value
        sla = FRESHNESS_SLA_DAYS.get(source_type)
        deferred = source_type in KNOWN_DEFERRED_SOURCES
        table = sla[0] if sla else "—"
        recency_col = sla[1] if sla else None
        sla_days = sla[2] if sla else 0
        notes: list[str] = []
        if deferred:
            notes.append(KNOWN_DEFERRED_SOURCES[source_type])

        # ── FLOW ──
        rows, newest = 0, None
        if sla:
            try:
                cur.execute(
                    f"SELECT count(*) AS n, max({recency_col}) AS newest FROM {table}"
                )
                r = cur.fetchone()
                rows, newest = r["n"], r["newest"]
            except Exception as e:
                conn.rollback()
                notes.append(f"flow query failed: {str(e)[:80]}")
        age = _age_days(newest, now)
        flow = score_flow(rows, age, sla_days) if sla else "AMBER"
        if not sla:
            notes.append("no freshness SLA registered for this source")

        # ── STRENGTH (spine-FK resolution share) ──
        linked_pct = None
        fk = SPINE_FK.get(table)
        if fk and rows:
            try:
                cur.execute(
                    f"SELECT count(*) FILTER (WHERE {fk} IS NOT NULL)::float "
                    f"/ NULLIF(count(*),0) * 100 AS pct FROM {table}"
                )
                p = cur.fetchone()["pct"]
                linked_pct = round(p, 1) if p is not None else None
            except Exception:
                conn.rollback()
        strength = score_strength(rows, linked_pct)

        # ── SYNC ──
        status = run_at = None
        runs_7d = stuck = 0
        last_inserted = last_updated = None
        last_outcome = None
        try:
            cur.execute(
                """
                SELECT status, outcome, COALESCE(completed_at, started_at) AS run_at,
                       records_inserted, records_updated
                FROM etl_runs WHERE source_name = %s
                ORDER BY started_at DESC LIMIT 1
                """,
                [source],
            )
            row = cur.fetchone()
            if row:
                status, run_at = row["status"], row["run_at"]
                last_outcome = row["outcome"]
                last_inserted, last_updated = row["records_inserted"], row["records_updated"]
        except Exception:
            conn.rollback()
        try:
            cur.execute(
                """
                SELECT
                  count(*) FILTER (
                    WHERE status='SUCCESS' AND started_at > now() - interval '7 days'
                  ) AS ok7,
                  count(*) FILTER (
                    WHERE status='RUNNING' AND started_at < now() - interval '%s hours'
                  ) AS stuck
                FROM etl_runs WHERE source_name = %s
                """,
                [STUCK_RUNNING_HOURS, source],
            )
            row = cur.fetchone()
            if row:
                runs_7d, stuck = row["ok7"], row["stuck"]
        except Exception:
            conn.rollback()
        scheduled = True  # iterating CONNECTOR_SCHEDULES
        sync = score_sync(scheduled, status, runs_7d, stuck)
        if stuck:
            notes.append(f"{stuck} stuck-RUNNING etl_runs (>{STUCK_RUNNING_HOURS}h) - killed mid-run")

        # ── E2E ──
        e2e = score_e2e(rows, last_inserted, last_updated)
        # Sharpen the 0-row ambiguity with the run outcome (migration 088). A
        # SUCCESS_NO_CHANGE is a legitimate quiet cycle; a FAILURE_ZERO_ROWS is
        # the silent-zero bug (fetched nothing under a "success") → escalate.
        if last_outcome == "FAILURE_ZERO_ROWS" and not deferred:
            e2e = "RED"
            notes.append("last run fetched 0 rows (FAILURE_ZERO_ROWS — silent zero, check connector)")
        elif last_outcome == "SUCCESS_NO_CHANGE":
            notes.append("last run: no new data (SUCCESS_NO_CHANGE — legitimate quiet cycle)")
        elif e2e == "AMBER" and not deferred and rows:
            # pre-088 rows carry no outcome; keep the old ambiguous note.
            notes.append("last run moved 0 rows (quiet cycle or silent zero - check)")

        verdict = roll_up(flow, strength, sync, e2e, deferred)

        out.append(
            SourceScore(
                source=source,
                table=table,
                scheduled=scheduled,
                deferred=deferred,
                rows=rows,
                age_days=age,
                sla_days=sla_days,
                flow=flow,
                linked_pct=linked_pct,
                strength=strength,
                last_run_status=status,
                last_run_at=run_at.isoformat() if run_at else None,
                runs_7d=runs_7d,
                stuck_running=stuck,
                sync=sync,
                last_inserted=last_inserted,
                last_updated=last_updated,
                e2e=e2e,
                verdict=verdict,
                notes=notes,
            )
        )
    return out


def gather_dlq_health(conn) -> DLQHealth:
    """Live DLQ backlog snapshot (read-only). Degrades gracefully if the
    table/columns are absent (fresh DB / pre-098) — a health query hiccup must
    never crash the scorecard; it rolls back and reports what it could read."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    pending_total = pending_recent = skipped_recent = 0
    top_causes: list[str] = []
    try:
        cur.execute("SELECT count(*) AS n FROM failed_records WHERE status = 'pending'")
        pending_total = cur.fetchone()["n"] or 0
        cur.execute(
            "SELECT count(*) AS n FROM failed_records "
            "WHERE status = 'pending' AND created_at > now() - make_interval(days => %s)",
            [DLQ_WINDOW_DAYS],
        )
        pending_recent = cur.fetchone()["n"] or 0
        cur.execute(
            """
            SELECT source_type, count(*) AS n
            FROM failed_records WHERE status = 'pending'
            GROUP BY source_type ORDER BY n DESC LIMIT 4
            """
        )
        top_causes = [f"{r['source_type']}:{r['n']}" for r in cur.fetchall()]
    except Exception:
        conn.rollback()  # no failed_records table / column — report zeros
    try:
        cur.execute(
            "SELECT COALESCE(sum(records_skipped), 0) AS n FROM etl_runs "
            "WHERE started_at > now() - make_interval(days => %s)",
            [DLQ_WINDOW_DAYS],
        )
        skipped_recent = cur.fetchone()["n"] or 0
    except Exception:
        conn.rollback()  # pre-098: no records_skipped column — skip the skip-sum
    return DLQHealth(
        pending_total=pending_total,
        pending_recent=pending_recent,
        skipped_recent=skipped_recent,
        window_days=DLQ_WINDOW_DAYS,
        verdict=score_dlq(pending_total, pending_recent, skipped_recent),
        top_causes=top_causes,
    )


def gather_ledger_health(conn) -> list[SourceHealth]:
    """Freshness of the knowledge LEDGER (facts + evidence) — the spine every lens
    (dossier / KBQ / scenario / synthesis) reads. The ledger sits DOWNSTREAM of
    ingest and converges via the scheduled ledger-convergence job
    (runner._run_ledger_convergence); it had no freshness gate of its own, so it
    silently froze 12 days (27-Jun prod probe: 0 new facts/evidence) while every
    ingest connector logged SUCCESS. This is that gate, wired into the live Lane-2
    script (the follow-up LEDGER_FRESHNESS_SLA_DAYS's note deferred until the DLQ
    JSON reshape landed). Read-only; ages the newest-row timestamp against the SLA
    and reuses the pure evaluate_source_health verdict so a stale ledger reads
    unhealthy exactly the way a stale source does. Degrades gracefully if a
    table/column is absent (fresh DB) — a query hiccup must never crash the
    scorecard; it rolls back and reports the ledger as empty (which is itself
    unhealthy)."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    now = datetime.now(timezone.utc)
    out: list[SourceHealth] = []
    for label, (table, recency_col, sla_days) in LEDGER_FRESHNESS_SLA_DAYS.items():
        rows, newest = 0, None
        try:
            cur.execute(f"SELECT count(*) AS n, max({recency_col}) AS newest FROM {table}")
            r = cur.fetchone()
            rows, newest = r["n"], r["newest"]
        except Exception:
            conn.rollback()  # missing table/column (fresh DB) — reported as empty
        out.append(
            evaluate_source_health(
                label, table, sla_days, rows, newest,
                last_run_status=None, last_run_at=None, last_error=None, now=now,
            )
        )
    return out


def _cell(v: str) -> str:
    return {"GREEN": "GRN", "AMBER": "AMB", "RED": "RED", "DEFERRED": "DEF"}.get(v, v)


def main() -> None:
    as_json = "--json" in sys.argv
    conn = psycopg2.connect(_get_db_url())
    scores = gather_scorecard(conn)
    dlq = gather_dlq_health(conn)
    ledger = gather_ledger_health(conn)
    conn.close()

    if as_json:
        # Envelope: source scorecard + DLQ backlog + ledger freshness. This was a
        # bare list of source scores; it now carries dlq + ledger so a DLQ bleed or a
        # ledger freeze (both of which fail the gate via the exit code below) also
        # reach health_alert.py — the sole consumer — and open/annotate the tracking
        # issue instead of only reddening the CI tab. health_alert unwraps this and
        # still accepts the legacy bare list.
        print(json.dumps(
            {
                "sources": [asdict(s) for s in scores],
                "dlq": asdict(dlq),
                "ledger": [asdict(l) for l in ledger],
            },
            indent=2, default=str,
        ))
    else:
        print(
            f"{'SOURCE':22} {'TABLE':22} {'ROWS':>7} {'AGE':>7} "
            f"{'FLOW':>5} {'STR':>5} {'SYNC':>5} {'E2E':>5}  VERDICT"
        )
        print("-" * 100)
        for s in scores:
            age = f"{s.age_days}d" if s.age_days is not None else "—"
            link = f" link={s.linked_pct}%" if s.linked_pct is not None else ""
            print(
                f"{s.source:22} {s.table:22} {s.rows:>7} {age:>7} "
                f"{_cell(s.flow):>5} {_cell(s.strength):>5} {_cell(s.sync):>5} "
                f"{_cell(s.e2e):>5}  {s.verdict}{link}"
            )
            for n in s.notes:
                print(f"        - {n}")
        red = [s.source for s in scores if s.verdict == "RED"]
        deferred = [s.source for s in scores if s.verdict == "DEFERRED"]
        print("-" * 100)
        green = sum(1 for s in scores if s.verdict == "GREEN")
        amber = sum(1 for s in scores if s.verdict == "AMBER")
        print(
            f"{green} GREEN · {amber} AMBER · {len(red)} RED · {len(deferred)} DEFERRED "
            f"(of {len(scores)} scheduled sources)"
        )
        if red:
            print(f"RED: {', '.join(red)}")
        if deferred:
            print(f"DEFERRED: {', '.join(deferred)}")

        # DLQ backlog (fail-closed skips + failed_records) — was silent to Lane-2.
        print("-" * 100)
        print(
            f"DLQ: {dlq.pending_total} pending  "
            f"(+{dlq.pending_recent} new / {dlq.window_days}d, "
            f"{dlq.skipped_recent} skipped / {dlq.window_days}d)  {dlq.verdict}"
        )
        if dlq.top_causes:
            print(f"     causes: {', '.join(dlq.top_causes)}")
        if dlq.verdict == "RED":
            print("     DLQ RED — backlog is GROWING (a live bleed). Triage the newest cause.")
        elif dlq.verdict == "AMBER":
            print("     DLQ AMBER — non-zero backlog (known debt awaiting replay; not growing).")

        # Knowledge ledger (facts + evidence) — the spine downstream of ingest. It
        # froze 12 days silently once (27-Jun); this line makes a re-freeze loud.
        print("-" * 100)
        for l in ledger:
            age = f"{l.age_days}d" if l.age_days is not None else "—"
            print(
                f"LEDGER {l.source:16} {l.table:18} rows={l.rows:>8} "
                f"age={age:>7} / {l.sla_days}d  {'RED' if not l.healthy else 'GREEN'}"
            )
        ledger_stale = [l.source for l in ledger if not l.healthy]
        if ledger_stale:
            print(
                f"     LEDGER RED — {', '.join(ledger_stale)} over freshness SLA. The spine "
                "every lens reads has stopped converging; check the ledger-convergence "
                "job (runner._run_ledger_convergence)."
            )

    if (
        any(s.verdict == "RED" for s in scores)
        or dlq.verdict == "RED"
        or any(not l.healthy for l in ledger)
    ):
        sys.exit(1)


if __name__ == "__main__":
    main()
