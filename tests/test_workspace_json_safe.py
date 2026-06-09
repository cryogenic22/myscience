"""P1 — ChatWorkspaceService must persist DB-sourced payloads that contain
``Decimal`` / ``datetime`` values.

psycopg2's RealDictCursor returns numeric columns as ``Decimal`` and timestamps
as ``datetime``. A gap-research result payload built from such rows hit a bare
``json.dumps`` in ``complete_research_job`` and raised
``TypeError: Object of type Decimal is not JSON serializable`` on every chat
query that auto-spawned a research job (the response still returned 200, but the
job-completion write crashed and the log filled with tracebacks).

These tests reproduce that (RED before the fix) and pin the faithful encoding:
Decimal -> JSON number (not a string), datetime -> ISO 8601.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

from services.workspace import ChatWorkspaceService


def _persisted_json(db_execute_mock) -> str:
    """The JSON string passed as the first bind param to db.execute."""
    args, _ = db_execute_mock.call_args
    # execute(sql, [payload_json, job_id])
    return args[1][0]


def test_complete_research_job_serializes_decimals():
    db = MagicMock()
    svc = ChatWorkspaceService(db)
    payload = {
        "npv": Decimal("123.45"),
        "rows": [{"score": Decimal("0.9")}],
        "nested": {"x": Decimal("1")},
    }
    svc.complete_research_job(job_id="job-1", payload=payload)
    parsed = json.loads(_persisted_json(db.execute))
    # Decimals persist as JSON numbers (faithful), not strings.
    assert parsed["npv"] == 123.45 and isinstance(parsed["npv"], float)
    assert parsed["rows"][0]["score"] == 0.9
    assert parsed["nested"]["x"] == 1


def test_complete_research_job_serializes_datetime():
    db = MagicMock()
    svc = ChatWorkspaceService(db)
    svc.complete_research_job(
        job_id="job-2",
        payload={"computed_at": datetime(2026, 6, 9, 12, 0, tzinfo=timezone.utc)},
    )
    parsed = json.loads(_persisted_json(db.execute))
    assert parsed["computed_at"].startswith("2026-06-09")


def test_save_session_tolerates_decimal_in_transcript():
    db = MagicMock()
    db.fetch_one.return_value = None  # no existing session -> insert path
    svc = ChatWorkspaceService(db)
    # A transcript message that embedded a DB-derived metric (Decimal) must not crash.
    out = svc.save_session(
        scope_key="default",
        title="t",
        transcript=[{"role": "assistant", "content": "x", "metric": Decimal("4.2")}],
        session_id="11111111-1111-1111-1111-111111111111",
    )
    assert out is not None


def test_create_research_job_tolerates_decimal_options():
    db = MagicMock()
    db.fetch_one.return_value = {
        "id": "22222222-2222-2222-2222-222222222222",
        "scope_key": "default", "question": "q", "options": {}, "status": "queued",
    }
    svc = ChatWorkspaceService(db)
    job = svc.create_research_job(
        scope_key="default", question="q", options={"weight": Decimal("0.5")},
    )
    assert job is not None
