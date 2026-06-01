"""PB-H18 — market_events writers must target the LIVE schema.

Regression net for the class of bug fixed here: a writer's INSERT column list
drifts from the real table schema and throws on prod, while fake-DB unit tests
(which don't validate columns) stay green — the same blind spot as the A1 bug.
This pins each writer's INSERT columns against the verified prod schema so the
drift can't silently return.
"""
from __future__ import annotations

import re

# Live market_events columns — verified twice via information_schema on the
# Railway prod DB (1 Jun 2026). If a migration changes the table, update this
# set in the SAME commit and the writers will be checked against it.
REAL_MARKET_EVENTS_COLUMNS = {
    "id", "drug_id", "event_type", "event_date", "description", "impact_score",
    "source_api", "source_url", "etl_run_id", "retrieved_at", "created_at",
    "content_hash", "last_verified_at", "record_status", "quality_score",
    "source_tier", "trust_score", "primary_entity_type", "primary_entity_name",
    "status", "event_hash", "corroborating_sources", "verified_at",
    "primary_entity_id",
}

_INSERT_COLS_RE = re.compile(r"INSERT\s+INTO\s+market_events\s*\(([^)]*)\)", re.I | re.S)


def _insert_columns(sql: str) -> set[str]:
    m = _INSERT_COLS_RE.search(sql)
    assert m, "no `INSERT INTO market_events (...)` found in SQL"
    return {c.strip() for c in m.group(1).split(",") if c.strip()}


def test_event_collector_insert_targets_real_columns():
    from services.event_collector import _INSERT_EVENT_SQL
    drift = _insert_columns(_INSERT_EVENT_SQL) - REAL_MARKET_EVENTS_COLUMNS
    assert not drift, f"event_collector INSERT targets non-existent columns: {drift}"


def test_db_adapter_8k_insert_targets_real_columns():
    from services.db_adapter_8k import _PostgresDBAdapter
    drift = _insert_columns(_PostgresDBAdapter._EVENT_INSERT_SQL) - REAL_MARKET_EVENTS_COLUMNS
    assert not drift, f"db_adapter_8k INSERT targets non-existent columns: {drift}"


def test_required_not_null_columns_present_in_both_writers():
    # event_type/event_date/source_api/source_url/retrieved_at are NOT NULL with
    # no default — every writer must supply them (event_date/source_url may be
    # COALESCE'd, so check the column is named).
    from services.event_collector import _INSERT_EVENT_SQL
    from services.db_adapter_8k import _PostgresDBAdapter
    required = {"event_type", "event_date", "source_api", "source_url", "retrieved_at"}
    for name, sql in (("event_collector", _INSERT_EVENT_SQL),
                      ("db_adapter_8k", _PostgresDBAdapter._EVENT_INSERT_SQL)):
        missing = required - _insert_columns(sql)
        assert not missing, f"{name} INSERT omits NOT NULL columns: {missing}"
