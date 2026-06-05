#!/usr/bin/env python
"""Connector health report (D1) — the one command the team runs each morning.

For every scheduled source it prints: target-table row count, newest-row age,
freshness SLA, OVER-SLA flag, and the last ETL run's terminal status + error.
It is the antidote to the silent-failure mode that let openFDA Labels/FAERS go
105 days stale while logging SUCCESS (0 rows fetched) — staleness is judged on
*newest row age vs SLA*, not on the run's self-reported status.

Read-only. Usage:
    python scripts/connector_health.py "<postgres url>"
    DATABASE_URL=... python scripts/connector_health.py
    python scripts/connector_health.py --json   # machine-readable

Exit code is non-zero when any source is OVER SLA or its last run FAILED, so it
can gate CI / a morning cron.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Optional

import psycopg2
import psycopg2.extras

# Allow `python scripts/connector_health.py` (not just `-m scripts.…`) by
# putting the repo root on the path.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scheduler.config import FRESHNESS_SLA_DAYS  # noqa: E402


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


def _get_db_url() -> str:
    for a in sys.argv[1:]:
        if a.startswith("postgres"):
            return a
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("Pass a postgres URL as an argument or set DATABASE_URL.")
    return url


def gather(conn) -> list[SourceHealth]:
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


def main() -> None:
    as_json = "--json" in sys.argv
    conn = psycopg2.connect(_get_db_url())
    healths = gather(conn)
    conn.close()

    if as_json:
        print(json.dumps([asdict(h) for h in healths], indent=2))
    else:
        print(f"{'SOURCE':24} {'TABLE':22} {'ROWS':>8} {'AGE':>7} {'SLA':>4}  {'RUN':9} STATUS")
        print("-" * 90)
        for h in healths:
            flag = "OK " if h.healthy else "!! "
            age = f"{h.age_days}d" if h.age_days is not None else "—"
            print(
                f"{flag}{h.source:21} {h.table:22} {h.rows:>8} {age:>7} {h.sla_days:>3}d  "
                f"{(h.last_run_status or '—'):9} "
                f"{'OVER_SLA ' if h.over_sla else ''}"
                f"{('ERR:'+h.last_error) if h.last_error else ''}"
            )
        bad = [h.source for h in healths if not h.healthy]
        print("-" * 90)
        print(f"{len(healths) - len(bad)}/{len(healths)} healthy."
              + (f" OVER/FAILED: {', '.join(bad)}" if bad else ""))

    if any(not h.healthy for h in healths):
        sys.exit(1)


if __name__ == "__main__":
    main()
