"""SPEC_014 follow-up — upload route must persist via IntegrationPipeline.

Today: POST /upload calls connector.fetch() and returns a summary, but
chunks do NOT land in knowledge_chunks and entity links are NOT created.

After this change: /upload calls IntegrationPipeline.run(connector) so the
full normalize → resolve → embed → store → cross-link flow runs.

Tests are TDD-first: assertions about what the route DOES (calls pipeline,
returns pipeline summary fields), not just what it returns.
"""

from __future__ import annotations

import io
import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _make_test_client_with_pipeline_mock(pipeline_summary: dict | None = None):
    """TestClient with auth bypassed and a mocked IntegrationPipeline.

    Returns (client, pipeline_mock) so tests can assert calls.
    """
    from fastapi.testclient import TestClient
    from api.app import create_app
    from api.deps import get_db, get_llm, get_current_user

    # Will need to add get_integration_pipeline once it exists
    try:
        from api.deps import get_integration_pipeline
    except ImportError:
        get_integration_pipeline = None

    app = create_app()
    app.dependency_overrides[get_db] = lambda: MagicMock(name="MockDB")
    app.dependency_overrides[get_llm] = lambda: None
    app.dependency_overrides[get_current_user] = lambda: {
        "id": "u", "email": "u@x", "role": "uploader", "is_active": True,
    }

    pipeline_mock = MagicMock()
    pipeline_mock.run.return_value = MagicMock(
        summary=lambda: pipeline_summary or {
            "etl_run_id": "fake-run",
            "source": "user_document",
            "processed": 1,
            "inserted": 1,
            "updated": 0,
            "unchanged": 0,
            "skipped": 0,
            "failed": 0,
            "links_created": 0,
            "hitl_items": 0,
            "avg_quality": None,
            "errors": [],
            "duration_seconds": 0.1,
        },
        records_processed=1,
        records_inserted=1,
        links_created=0,
    )
    if get_integration_pipeline is not None:
        app.dependency_overrides[get_integration_pipeline] = lambda: pipeline_mock

    return TestClient(app), pipeline_mock


# ────────────────────────────────────────────────────────────────────
# Dependency exists
# ────────────────────────────────────────────────────────────────────

def test_get_integration_pipeline_dep_exists():
    """SPEC_014 follow-up: api/deps.py must expose get_integration_pipeline()."""
    src = (REPO_ROOT / "api" / "deps.py").read_text(encoding="utf-8")
    assert re.search(r"def\s+get_integration_pipeline\s*\(", src), (
        "api/deps.py must define get_integration_pipeline() so the upload "
        "route can inject it"
    )


# ────────────────────────────────────────────────────────────────────
# Upload route calls IntegrationPipeline
# ────────────────────────────────────────────────────────────────────

def test_upload_calls_integration_pipeline():
    """The /upload route must call pipeline.run(connector) — not just
    connector.fetch(). This is the difference between extracting text and
    persisting it into the knowledge graph."""
    client, pipeline_mock = _make_test_client_with_pipeline_mock()
    r = client.post(
        "/upload",
        files={"file": ("trial.txt", io.BytesIO(b"semaglutide trial data"), "text/plain")},
    )
    assert r.status_code == 200, r.text
    assert pipeline_mock.run.called, (
        "/upload must call IntegrationPipeline.run() to persist records"
    )


def test_upload_passes_user_document_connector_to_pipeline():
    """The first arg to pipeline.run() must be a UserDocumentConnector."""
    from connectors.user_document import UserDocumentConnector
    client, pipeline_mock = _make_test_client_with_pipeline_mock()
    client.post(
        "/upload",
        files={"file": ("x.txt", io.BytesIO(b"data"), "text/plain")},
    )
    assert pipeline_mock.run.called
    args, kwargs = pipeline_mock.run.call_args
    connector_arg = args[0] if args else kwargs.get("connector")
    assert isinstance(connector_arg, UserDocumentConnector)


# ────────────────────────────────────────────────────────────────────
# Response shape includes pipeline summary
# ────────────────────────────────────────────────────────────────────

def test_upload_response_includes_etl_run_id():
    client, _ = _make_test_client_with_pipeline_mock(pipeline_summary={
        "etl_run_id": "abc-123",
        "source": "user_document",
        "processed": 2,
        "inserted": 2,
        "updated": 0, "unchanged": 0, "skipped": 0, "failed": 0,
        "links_created": 5,
        "hitl_items": 0, "avg_quality": None, "errors": [],
        "duration_seconds": 0.5,
    })
    r = client.post(
        "/upload",
        files={"file": ("x.txt", io.BytesIO(b"data"), "text/plain")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("etl_run_id") == "abc-123"


def test_upload_response_includes_records_inserted():
    client, _ = _make_test_client_with_pipeline_mock(pipeline_summary={
        "etl_run_id": "x",
        "source": "user_document",
        "processed": 3, "inserted": 3,
        "updated": 0, "unchanged": 0, "skipped": 0, "failed": 0,
        "links_created": 7, "hitl_items": 0, "avg_quality": None,
        "errors": [], "duration_seconds": 0.1,
    })
    r = client.post(
        "/upload",
        files={"file": ("x.txt", io.BytesIO(b"data"), "text/plain")},
    )
    body = r.json()
    assert body.get("records_inserted") == 3
    assert body.get("links_created") == 7


def test_upload_returns_500_on_pipeline_failure():
    """If the pipeline raises, surface a clean error rather than crashing."""
    client, pipeline_mock = _make_test_client_with_pipeline_mock()
    pipeline_mock.run.side_effect = RuntimeError("boom")
    r = client.post(
        "/upload",
        files={"file": ("x.txt", io.BytesIO(b"data"), "text/plain")},
    )
    assert r.status_code == 500
    assert "boom" in r.text or "failed" in r.text.lower()


# ────────────────────────────────────────────────────────────────────
# Static check — route file references the pipeline
# ────────────────────────────────────────────────────────────────────

def test_upload_route_imports_pipeline_dep():
    src = (REPO_ROOT / "api" / "routes" / "upload.py").read_text(encoding="utf-8")
    assert "get_integration_pipeline" in src or "IntegrationPipeline" in src, (
        "upload.py must wire in IntegrationPipeline (via get_integration_pipeline dep)"
    )


def test_upload_route_calls_pipeline_run():
    src = (REPO_ROOT / "api" / "routes" / "upload.py").read_text(encoding="utf-8")
    has_call = re.search(r"pipeline\.run\s*\(", src)
    assert has_call, "upload.py must call pipeline.run(connector)"
