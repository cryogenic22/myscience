"""SPEC_014 Phase 4c — UserDocumentConnector + /upload endpoint TDD contract.

Tests for connectors/user_document.py: wraps document_extractor + document_ner
into the BaseConnector pattern. Yields DOCUMENT_CHUNK RawRecords with embedded
entity_mentions for the entity_resolver to pick up downstream.

Tests for /upload endpoint: multipart file upload, format validation, size
limit enforcement, error handling.

All tests must FAIL before implementation. TDD discipline.
"""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ────────────────────────────────────────────────────────────────────
# Module / class existence
# ────────────────────────────────────────────────────────────────────

def test_connector_module_exists():
    assert Path("connectors/user_document.py").exists()


def test_user_document_connector_class():
    from connectors.user_document import UserDocumentConnector
    from connectors.base import BaseConnector
    assert issubclass(UserDocumentConnector, BaseConnector)


def test_connector_source_type():
    from connectors.user_document import UserDocumentConnector
    from connectors.base import SourceType
    c = UserDocumentConnector(payload_bytes=b"hi", filename="x.txt")
    assert c.source_type() == SourceType.USER_DOCUMENT


def test_connector_health_check_always_ok():
    """USER_DOCUMENT connector has no upstream dependency to check."""
    from connectors.user_document import UserDocumentConnector
    c = UserDocumentConnector(payload_bytes=b"hi", filename="x.txt")
    result = c.health_check()
    assert result.healthy is True


# ────────────────────────────────────────────────────────────────────
# Fetch produces DOCUMENT_CHUNK records
# ────────────────────────────────────────────────────────────────────

def test_fetch_produces_chunk_records():
    """A simple text document yields at least one DOCUMENT_CHUNK record."""
    from connectors.user_document import UserDocumentConnector
    from connectors.base import RecordType
    text = "Semaglutide is a GLP-1 receptor agonist used to treat type 2 diabetes."
    c = UserDocumentConnector(payload_bytes=text.encode(), filename="note.txt")
    records = c.fetch()
    chunks = [r for r in records if r.record_type == RecordType.DOCUMENT_CHUNK]
    assert len(chunks) >= 1


def test_fetch_text_content_matches_input():
    """Each chunk's text_content should contain text from the document."""
    from connectors.user_document import UserDocumentConnector
    text = "Tirzepatide (Mounjaro) is sold by Eli Lilly."
    c = UserDocumentConnector(payload_bytes=text.encode(), filename="note.txt")
    records = c.fetch()
    combined = " ".join(r.text_content or "" for r in records)
    assert "Tirzepatide" in combined


def test_fetch_provenance_set():
    """Each record must carry provenance with source=USER_DOCUMENT."""
    from connectors.user_document import UserDocumentConnector
    from connectors.base import SourceType
    c = UserDocumentConnector(payload_bytes=b"semaglutide trial data", filename="x.txt")
    records = c.fetch()
    assert all(r.provenance.source_type == SourceType.USER_DOCUMENT for r in records)


def test_fetch_includes_entity_mentions_when_llm_available():
    """When an LLM is provided, NER mentions get embedded in record identifiers
    so the integration pipeline's entity resolver can pick them up."""
    from connectors.user_document import UserDocumentConnector
    fake_llm = MagicMock()
    fake_llm.complete_json.return_value = {
        "mentions": [
            {"text": "Semaglutide", "entity_type": "drug", "start": 0, "end": 11},
        ]
    }
    text = "Semaglutide is a drug."
    c = UserDocumentConnector(
        payload_bytes=text.encode(),
        filename="note.txt",
        llm=fake_llm,
    )
    records = c.fetch()
    # At least one chunk should have entity mentions in its identifiers
    has_mentions = any(
        "Semaglutide" in (r.identifiers.get("entity_mentions", []) or [])
        for r in records
    )
    assert has_mentions, (
        "expected at least one chunk with 'Semaglutide' in entity_mentions; "
        f"identifiers seen: {[r.identifiers for r in records]}"
    )


def test_fetch_works_without_llm():
    """No LLM → no NER, but extraction + chunking still succeeds."""
    from connectors.user_document import UserDocumentConnector
    text = "Some text without entity extraction."
    c = UserDocumentConnector(payload_bytes=text.encode(), filename="x.txt")
    records = c.fetch()
    assert len(records) >= 1


# ────────────────────────────────────────────────────────────────────
# /upload endpoint
# ────────────────────────────────────────────────────────────────────

def test_upload_route_module_exists():
    assert Path("api/routes/upload.py").exists()


def test_upload_endpoint_registered():
    """The chat app must include the upload router."""
    from api.app import create_app
    app = create_app()
    # FastAPI routes have .path
    paths = {getattr(r, "path", None) for r in app.routes}
    assert any(p and "/upload" in p for p in paths), (
        f"expected /upload route registered; got paths: "
        f"{[p for p in paths if p and 'upload' in str(p).lower()]}"
    )


def _make_test_client():
    """Build a TestClient with DB, LLM, auth, and pipeline dependencies stubbed.

    These tests focus on the upload route's extraction + response shape, not on
    persistence (covered by tests/test_upload_persistence.py) or auth (covered
    by tests/test_role_gates.py). Mock the integration pipeline to a no-op so
    these tests exercise just the format detection / NER / response building.
    """
    from fastapi.testclient import TestClient
    from api.app import create_app
    from api.deps import get_db, get_llm, get_current_user, get_integration_pipeline

    app = create_app()
    app.dependency_overrides[get_db] = lambda: MagicMock(name="MockDB")
    app.dependency_overrides[get_llm] = lambda: None
    fake_user = {
        "id": "test-uploader",
        "email": "test-uploader@example.io",
        "role": "uploader",
        "is_active": True,
    }
    app.dependency_overrides[get_current_user] = lambda: fake_user

    # Mock pipeline so /upload doesn't try to talk to a real DB
    pipeline_mock = MagicMock()
    pipeline_mock.run.return_value = MagicMock(
        summary=lambda: {
            "etl_run_id": "test-run",
            "source": "user_document",
            "processed": 1, "inserted": 1, "updated": 0,
            "unchanged": 0, "skipped": 0, "failed": 0,
            "links_created": 0, "hitl_items": 0,
            "avg_quality": None, "errors": [], "duration_seconds": 0.01,
        },
    )
    app.dependency_overrides[get_integration_pipeline] = lambda: pipeline_mock

    return TestClient(app)


def test_upload_accepts_text_file():
    """POST /upload with a text file returns 200 with records_processed."""
    client = _make_test_client()
    payload = b"Tirzepatide is a GIP/GLP-1 dual agonist."
    r = client.post(
        "/upload",
        files={"file": ("test.txt", io.BytesIO(payload), "text/plain")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "records_processed" in body
    assert body["records_processed"] >= 1
    assert body.get("filename") == "test.txt"


def test_upload_rejects_oversized(monkeypatch):
    monkeypatch.setenv("MZ_DOC_UPLOAD_MAX_MB", "1")
    client = _make_test_client()
    big = b"x" * (2 * 1024 * 1024)
    r = client.post(
        "/upload",
        files={"file": ("big.txt", io.BytesIO(big), "text/plain")},
    )
    assert r.status_code == 413  # Payload Too Large


def test_upload_rejects_unsupported_format():
    client = _make_test_client()
    r = client.post(
        "/upload",
        files={"file": ("archive.zip", io.BytesIO(b"PK\x03\x04bogus"), "application/zip")},
    )
    assert r.status_code == 415  # Unsupported Media Type


def test_upload_returns_entity_count_when_llm_available():
    """When LLM is wired, response includes entity count from NER mentions."""
    from connectors.base import RawRecord, RecordType, SourceType, Provenance
    from datetime import datetime

    fake_records = [
        RawRecord(
            record_type=RecordType.DOCUMENT_CHUNK,
            external_id="USERDOC|abc|test.txt|chunk0",
            source_name="UserUpload",
            provenance=Provenance(
                source_type=SourceType.USER_DOCUMENT,
                api_endpoint="upload://test.txt",
                query_params={},
                retrieved_at=datetime.utcnow(),
                raw_response_hash="abc",
            ),
            data={"filename": "test.txt", "chunk_index": 0, "format": "txt"},
            text_content="Semaglutide is a drug.",
            identifiers={"entity_mentions": ["Semaglutide"], "doc_hash": "abc"},
        ),
    ]
    with patch("connectors.user_document.UserDocumentConnector.fetch", return_value=fake_records):
        client = _make_test_client()
        r = client.post(
            "/upload",
            files={"file": ("test.txt", io.BytesIO(b"Semaglutide is a drug."), "text/plain")},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("entity_mentions_total", 0) >= 1


# ────────────────────────────────────────────────────────────────────
# Defensive: bad inputs
# ────────────────────────────────────────────────────────────────────

def test_upload_no_file_returns_422():
    client = _make_test_client()
    r = client.post("/upload", files={})
    assert r.status_code in (400, 422)
