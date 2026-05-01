"""SPEC-019 — Connector registry service.

Single source of truth for the connector listing and dossier views consumed by
the Connectors UI. Joins:

  - CONNECTOR_REGISTRY            (which connector classes exist)
  - CONNECTOR_SCHEDULES           (label + cron)
  - DATASET_DEFINITIONS           (description + license + api_base_url)
  - connector_config (DB)         (enabled, auto_approve_runs, manual_only)
  - etl_runs (DB)                 (last_run_at, last_status, recent history)

Defaults when no connector_config row exists:
  enabled=true, auto_approve_runs=false, manual_only=false.
"""

from __future__ import annotations

import logging
from typing import Optional

from connectors import CONNECTOR_REGISTRY
from scheduler.config import CONNECTOR_SCHEDULES
from integration.dataset_catalog import DATASET_DEFINITIONS

logger = logging.getLogger(__name__)


# Defaults applied when connector_config has no row for a key
_DEFAULT_CONFIG = {
    "enabled": True,
    "auto_approve_runs": False,
    "manual_only": False,
    "notes": None,
}


def _describe_schedule(cron: dict) -> str:
    """Human-readable schedule from an APScheduler cron dict."""
    if "day" in cron:
        return f"Monthly on day {cron['day']} at {cron.get('hour', 0):02d}:{cron.get('minute', 0):02d} UTC"
    if "day_of_week" in cron:
        return f"Weekly ({cron['day_of_week']}) at {cron.get('hour', 0):02d}:{cron.get('minute', 0):02d} UTC"
    return f"Daily at {cron.get('hour', 0):02d}:{cron.get('minute', 0):02d} UTC"


def _dataset_metadata(source_key: str) -> dict:
    """Pull description / license / api_base_url from DATASET_DEFINITIONS.

    A source can have multiple dataset entries (e.g. fda_orange_book has drugs
    + patents + regulatory_milestones); we collapse into one summary blurb.
    """
    matches = [d for d in DATASET_DEFINITIONS if d.get("source_type") == source_key]
    if not matches:
        return {"description": None, "license": None, "license_url": None, "api_base_url": None}
    # Use first match for display; could be richer later
    primary = matches[0]
    return {
        "description": primary.get("description"),
        "license": primary.get("license_name"),
        "license_url": primary.get("license_url"),
        "api_base_url": primary.get("api_base_url"),
    }


def _config_for(db, source_key: str) -> dict:
    """Read connector_config row or fall back to defaults."""
    try:
        row = db.fetch_one(
            """SELECT enabled, auto_approve_runs, manual_only, notes
               FROM connector_config WHERE source_key = %s""",
            [source_key],
        )
    except Exception:
        # connector_config table may not exist yet — fall back silently
        row = None
    if not row:
        return dict(_DEFAULT_CONFIG)
    return {
        "enabled": bool(row.get("enabled", True)),
        "auto_approve_runs": bool(row.get("auto_approve_runs", False)),
        "manual_only": bool(row.get("manual_only", False)),
        "notes": row.get("notes"),
    }


def _last_run_for(db, source_key: str) -> Optional[dict]:
    """Most recent successful (or partial) etl_runs row for this source."""
    try:
        row = db.fetch_one(
            """SELECT source_name, status, started_at, completed_at, records_inserted
               FROM etl_runs
               WHERE source_name = %s AND status IN ('SUCCESS','PARTIAL')
               ORDER BY completed_at DESC NULLS LAST
               LIMIT 1""",
            [source_key],
        )
    except Exception:
        row = None
    if not row:
        return None
    completed = row.get("completed_at")
    return {
        "status": row.get("status"),
        "completed_at": completed.isoformat() if completed and hasattr(completed, "isoformat") else completed,
        "records_inserted": row.get("records_inserted"),
    }


def _recent_runs_for(db, source_key: str, limit: int = 10) -> list:
    """Last N etl_runs rows (any status) for a source."""
    try:
        rows = db.fetch_all(
            """SELECT source_name, status, started_at, completed_at, records_inserted
               FROM etl_runs
               WHERE source_name = %s
               ORDER BY started_at DESC NULLS LAST
               LIMIT %s""",
            [source_key, limit],
        )
    except Exception:
        rows = []
    out = []
    for r in rows:
        started = r.get("started_at")
        completed = r.get("completed_at")
        out.append({
            "status": r.get("status"),
            "started_at": started.isoformat() if started and hasattr(started, "isoformat") else started,
            "completed_at": completed.isoformat() if completed and hasattr(completed, "isoformat") else completed,
            "records_inserted": r.get("records_inserted"),
        })
    return out


def list_connectors(db) -> list[dict]:
    """One row per registered connector for the sidebar listing.

    Returns list of dicts with: source_key, label, schedule, enabled,
    auto_approve_runs, manual_only, notes, connection_status, last_run,
    description, license.
    """
    out = []
    for source_type in CONNECTOR_REGISTRY.keys():
        key = source_type.value
        sched_entry = CONNECTOR_SCHEDULES.get(source_type)
        label = sched_entry["label"] if sched_entry else key
        schedule = _describe_schedule(sched_entry["cron"]) if sched_entry else "On-demand"

        cfg = _config_for(db, key)
        last_run = _last_run_for(db, key)
        meta = _dataset_metadata(key)

        connection_status = "connected" if last_run else "available"
        if not cfg["enabled"]:
            connection_status = "disabled"

        out.append({
            "source_key": key,
            "label": label,
            "schedule": schedule,
            "enabled": cfg["enabled"],
            "auto_approve_runs": cfg["auto_approve_runs"],
            "manual_only": cfg["manual_only"],
            "notes": cfg["notes"],
            "connection_status": connection_status,
            "last_run": last_run,
            "description": meta["description"],
            "license": meta["license"],
        })
    return out


def get_connector_detail(db, source_key: str) -> Optional[dict]:
    """Full dossier for a single connector. None if key is unknown."""
    # Validate against registry
    matched = None
    for source_type in CONNECTOR_REGISTRY.keys():
        if source_type.value == source_key:
            matched = source_type
            break
    if not matched:
        return None

    sched_entry = CONNECTOR_SCHEDULES.get(matched)
    label = sched_entry["label"] if sched_entry else source_key
    schedule = _describe_schedule(sched_entry["cron"]) if sched_entry else "On-demand"

    cfg = _config_for(db, source_key)
    last_run = _last_run_for(db, source_key)
    recent = _recent_runs_for(db, source_key, limit=10)
    meta = _dataset_metadata(source_key)

    connection_status = "connected" if last_run else "available"
    if not cfg["enabled"]:
        connection_status = "disabled"

    return {
        "source_key": source_key,
        "label": label,
        "schedule": schedule,
        "description": meta["description"],
        "license": meta["license"],
        "license_url": meta["license_url"],
        "api_base_url": meta["api_base_url"],
        "connection_status": connection_status,
        "config": cfg,
        "last_run": last_run,
        "recent_runs": recent,
    }
