"""SPEC-019 — Connector registry service tests.

Pure unit tests for services.connector_registry: list_connectors() and
get_connector_detail() must merge CONNECTOR_REGISTRY + CONNECTOR_SCHEDULES +
DATASET_DEFINITIONS + connector_config table + recent etl_runs.

DB is mocked; no live Postgres needed.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest


# ────────────────────────────────────────────────────────────────────
# Fake DB — table-aware so registry queries return sensible rows
# ────────────────────────────────────────────────────────────────────

def _make_fake_db(*, configs: dict | None = None, etl_runs: list | None = None,
                  record_counts: dict | None = None):
    """Build a MagicMock DB.

    configs        — {source_key: {enabled, auto_approve_runs, manual_only, notes}}
    etl_runs       — list of {source_name, status, started_at, completed_at, records_inserted}
    record_counts  — {source_key: total_records} returned by sum-over-tables query
    """
    configs = configs or {}
    etl_runs = etl_runs or []
    record_counts = record_counts or {}

    def fake_fetch_one(sql, params=None):
        sql_lower = (sql or "").lower()
        if "from connector_config" in sql_lower:
            key = (params or [None])[0]
            row = configs.get(key)
            if not row:
                return None
            # Echo back as a DB row
            return {
                "source_key": key,
                "enabled": row.get("enabled", True),
                "auto_approve_runs": row.get("auto_approve_runs", False),
                "manual_only": row.get("manual_only", False),
                "notes": row.get("notes"),
            }
        # Last successful ETL run for a source
        if "from etl_runs" in sql_lower and "limit 1" in sql_lower:
            key = (params or [None])[0]
            for r in reversed(etl_runs):
                if r.get("source_name") == key and r.get("status") in ("SUCCESS", "PARTIAL"):
                    return r
            return None
        return None

    def fake_fetch_all(sql, params=None):
        sql_lower = (sql or "").lower()
        if "from etl_runs" in sql_lower:
            key = (params or [None])[0] if params else None
            if key:
                return [r for r in etl_runs if r.get("source_name") == key][-10:]
            return etl_runs[-10:]
        # Record-count aggregate across entity tables (registry uses one query)
        if "from drugs" in sql_lower or "union all" in sql_lower:
            return [
                {"source_api": k, "records": v}
                for k, v in record_counts.items()
            ]
        return []

    db = MagicMock()
    db.fetch_one.side_effect = fake_fetch_one
    db.fetch_all.side_effect = fake_fetch_all
    db.execute = MagicMock()
    return db


# ────────────────────────────────────────────────────────────────────
# list_connectors()
# ────────────────────────────────────────────────────────────────────

def test_list_connectors_returns_all_registered():
    """Every key in CONNECTOR_REGISTRY must appear in the listing."""
    from services.connector_registry import list_connectors
    from connectors import CONNECTOR_REGISTRY

    db = _make_fake_db()
    rows = list_connectors(db)

    keys = {r["source_key"] for r in rows}
    expected = {st.value for st in CONNECTOR_REGISTRY.keys()}
    assert expected.issubset(keys), (
        f"Missing connectors in listing: {expected - keys}"
    )


def test_list_connectors_uses_defaults_when_no_config_row():
    """Connector with no connector_config row defaults to enabled=true,
    auto_approve_runs=false, manual_only=false."""
    from services.connector_registry import list_connectors

    db = _make_fake_db(configs={})  # no rows
    rows = list_connectors(db)

    # Pick any well-known connector
    fda = next(r for r in rows if r["source_key"] == "fda_orange_book")
    assert fda["enabled"] is True
    assert fda["auto_approve_runs"] is False
    assert fda["manual_only"] is False


def test_list_connectors_reflects_explicit_config_row():
    """When connector_config has a row, registry must use those values."""
    from services.connector_registry import list_connectors

    db = _make_fake_db(configs={
        "fda_orange_book": {
            "enabled": False,
            "auto_approve_runs": True,
            "manual_only": True,
            "notes": "Disabled pending license review",
        },
    })
    rows = list_connectors(db)

    fda = next(r for r in rows if r["source_key"] == "fda_orange_book")
    assert fda["enabled"] is False
    assert fda["auto_approve_runs"] is True
    assert fda["manual_only"] is True
    assert fda["notes"] == "Disabled pending license review"


def test_list_connectors_marks_connected_when_etl_run_exists():
    """status='Connected' if there is a successful etl_runs row."""
    from services.connector_registry import list_connectors

    db = _make_fake_db(etl_runs=[
        {
            "source_name": "fda_orange_book",
            "status": "SUCCESS",
            "started_at": datetime(2026, 4, 30, tzinfo=timezone.utc),
            "completed_at": datetime(2026, 4, 30, 0, 5, tzinfo=timezone.utc),
            "records_inserted": 100,
        },
    ])
    rows = list_connectors(db)

    fda = next(r for r in rows if r["source_key"] == "fda_orange_book")
    assert fda["connection_status"] == "connected"
    assert fda["last_run"] is not None


def test_list_connectors_marks_available_when_no_runs():
    """status='Available' for a registered connector with no etl_runs and
    no explicit disable."""
    from services.connector_registry import list_connectors

    db = _make_fake_db(etl_runs=[])
    rows = list_connectors(db)

    chembl = next(r for r in rows if r["source_key"] == "chembl")
    assert chembl["connection_status"] == "available"
    assert chembl["last_run"] is None


def test_list_connectors_includes_label_and_schedule():
    """Each row carries human-readable label + schedule (from scheduler.config)."""
    from services.connector_registry import list_connectors

    db = _make_fake_db()
    rows = list_connectors(db)

    fda = next(r for r in rows if r["source_key"] == "fda_orange_book")
    assert fda["label"]  # non-empty
    assert fda["schedule"]  # non-empty


# ────────────────────────────────────────────────────────────────────
# get_connector_detail()
# ────────────────────────────────────────────────────────────────────

def test_get_detail_returns_none_for_unknown_key():
    from services.connector_registry import get_connector_detail

    db = _make_fake_db()
    assert get_connector_detail(db, "not_a_real_connector") is None


def test_get_detail_includes_recent_etl_runs():
    from services.connector_registry import get_connector_detail

    runs = [
        {
            "source_name": "pubmed", "status": "SUCCESS",
            "started_at": datetime(2026, 4, 28, tzinfo=timezone.utc),
            "completed_at": datetime(2026, 4, 28, 0, 30, tzinfo=timezone.utc),
            "records_inserted": 500,
        },
        {
            "source_name": "pubmed", "status": "FAILED",
            "started_at": datetime(2026, 4, 29, tzinfo=timezone.utc),
            "completed_at": datetime(2026, 4, 29, 0, 1, tzinfo=timezone.utc),
            "records_inserted": 0,
        },
    ]
    db = _make_fake_db(etl_runs=runs)
    detail = get_connector_detail(db, "pubmed")

    assert detail is not None
    assert "recent_runs" in detail
    assert len(detail["recent_runs"]) == 2


def test_get_detail_includes_config_or_defaults():
    from services.connector_registry import get_connector_detail

    db = _make_fake_db()
    detail = get_connector_detail(db, "fda_orange_book")

    assert detail is not None
    assert "config" in detail
    cfg = detail["config"]
    assert cfg["enabled"] is True
    assert cfg["auto_approve_runs"] is False
    assert cfg["manual_only"] is False


def test_get_detail_includes_metadata_fields():
    """Detail should expose label, schedule, source_key, description, license."""
    from services.connector_registry import get_connector_detail

    db = _make_fake_db()
    detail = get_connector_detail(db, "clinical_trials_gov")

    assert detail is not None
    for field in ("source_key", "label", "schedule", "description", "license"):
        assert field in detail, f"detail missing field: {field}"
