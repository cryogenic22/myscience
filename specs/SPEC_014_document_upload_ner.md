# SPEC-014: Document Upload Connector + LLM-Based NER

*Date: 19 April 2026*
*Priority: P2*
*Effort: 1 week*

---

## Goal

Implement the user-document ingestion path that the architecture has long anticipated but never wired. Accept PDF / DOCX / HTML / plain-text uploads, extract text, run an LLM-based NER stage to identify drug / company / trial / mechanism / TA mentions, then feed the resulting RawRecords through the existing 5-step integration pipeline so they get embedded, entity-resolved, and cross-linked exactly like API-sourced data.

This is the lead's #1 highest-impact recommendation (Section 7.1) — turning Market Zero from "ingester of structured pharma APIs" into "ingester of arbitrary pharma dark data."

## Why This Matters

From the lead's review:

> Build a document ingestion connector that accepts PDF uploads, extracts text, chunks it, and feeds it through the existing integration pipeline. Add a lightweight NER stage that identifies drug names, company mentions, trial references, and therapeutic area terms in free text. **This turns any uploaded document into structured, linked, searchable knowledge — which is the core dark data promise.**

Current state:
- `SourceType.USER_DOCUMENT` and `SourceType.USER_URL` exist in the enum
- No connector class registered
- No upload endpoint
- No NER stage in the pipeline
- The architectural support is there (universal RawRecord, entity resolution cascade, knowledge_chunks table) but unwired

## Tests First

This spec has the largest surface, so tests are split across 3 files. Write all of them before any implementation.

### `tests/test_document_extractor.py`

```python
"""TDD for document text extraction."""
import pytest
from pathlib import Path

from services.document_extractor import (
    extract_text, ExtractedDocument, UnsupportedFormatError
)

FIXTURES = Path("tests/fixtures/documents")


def test_extract_pdf_returns_pages_and_text():
    """SPEC_014: PDF extraction must return per-page text + metadata."""
    pdf = FIXTURES / "sample_drug_report.pdf"
    doc = extract_text(pdf.read_bytes(), filename="sample_drug_report.pdf")
    assert isinstance(doc, ExtractedDocument)
    assert doc.format == "pdf"
    assert len(doc.pages) >= 1
    assert any("semaglutide" in p.lower() for p in doc.pages)


def test_extract_docx_returns_paragraphs():
    docx = FIXTURES / "trial_protocol.docx"
    doc = extract_text(docx.read_bytes(), filename="trial_protocol.docx")
    assert doc.format == "docx"
    assert doc.full_text != ""


def test_extract_html_strips_tags():
    html = b"<html><body><h1>Title</h1><p>Tirzepatide trial</p></body></html>"
    doc = extract_text(html, filename="page.html")
    assert doc.format == "html"
    assert "Tirzepatide trial" in doc.full_text
    assert "<p>" not in doc.full_text


def test_extract_plaintext_passes_through():
    text = b"Empagliflozin 10mg daily."
    doc = extract_text(text, filename="notes.txt")
    assert doc.format == "txt"
    assert "Empagliflozin" in doc.full_text


def test_unknown_format_raises():
    with pytest.raises(UnsupportedFormatError):
        extract_text(b"binary garbage", filename="archive.zip")


def test_size_limit_enforced(monkeypatch):
    monkeypatch.setenv("MZ_DOC_UPLOAD_MAX_MB", "1")
    big = b"x" * (2 * 1024 * 1024)  # 2 MB
    with pytest.raises(ValueError, match="exceeds.*1 MB"):
        extract_text(big, filename="big.txt")
```

### `tests/test_document_ner.py`

```python
"""TDD for LLM-based NER stage."""
from unittest.mock import MagicMock
from services.document_ner import extract_entities, EntityMention


def test_extracts_drug_mentions():
    """LLM must identify drug names in free text."""
    fake_llm = MagicMock()
    fake_llm.complete_json.return_value = {
        "mentions": [
            {"text": "semaglutide", "type": "drug", "start": 0, "end": 11},
            {"text": "Novo Nordisk", "type": "company", "start": 25, "end": 37},
        ]
    }
    text = "semaglutide is sold by Novo Nordisk for type 2 diabetes."
    mentions = extract_entities(text, llm=fake_llm)
    assert len(mentions) == 2
    types = {m.entity_type for m in mentions}
    assert {"drug", "company"} <= types


def test_extract_returns_empty_for_irrelevant_text():
    fake_llm = MagicMock()
    fake_llm.complete_json.return_value = {"mentions": []}
    assert extract_entities("the weather is nice today", llm=fake_llm) == []


def test_extract_chunks_long_text():
    """Documents longer than the LLM context window must be chunked."""
    fake_llm = MagicMock()
    fake_llm.complete_json.return_value = {"mentions": []}
    long = "drug mention. " * 5000  # ~75K chars
    extract_entities(long, llm=fake_llm)
    # Verify the LLM was called multiple times (chunked)
    assert fake_llm.complete_json.call_count > 1


def test_extract_dedupes_mentions_across_chunks():
    fake_llm = MagicMock()
    fake_llm.complete_json.side_effect = [
        {"mentions": [{"text": "Ozempic", "type": "drug", "start": 0, "end": 7}]},
        {"mentions": [{"text": "Ozempic", "type": "drug", "start": 0, "end": 7}]},
    ]
    long = "x" * 30000
    mentions = extract_entities(long, llm=fake_llm, chunk_size=15000)
    assert len([m for m in mentions if m.text == "Ozempic"]) == 1


def test_invalid_llm_response_returns_empty_not_raises():
    """Defensive: malformed LLM JSON should not crash the upload."""
    fake_llm = MagicMock()
    fake_llm.complete_json.return_value = {"unexpected": "shape"}
    assert extract_entities("text", llm=fake_llm) == []
```

### `tests/test_user_document_connector.py`

```python
"""TDD for the end-to-end USER_DOCUMENT connector."""
from io import BytesIO
from fastapi.testclient import TestClient
from unittest.mock import patch

from api.app import create_app
from connectors.user_document import UserDocumentConnector
from connectors.base import SourceType, RecordType


def test_source_type():
    c = UserDocumentConnector(payload_bytes=b"hi", filename="x.txt")
    assert c.source_type() == SourceType.USER_DOCUMENT


def test_fetch_yields_chunks_and_entity_records(monkeypatch):
    """A document with drug mentions must yield DOCUMENT_CHUNK + entity records."""
    text = "Semaglutide reduces A1C in patients with type 2 diabetes mellitus."
    monkeypatch.setattr(
        "services.document_ner.extract_entities",
        lambda t, llm=None, **kw: [
            type("M", (), {"text": "Semaglutide", "entity_type": "drug",
                          "start": 0, "end": 11})()
        ],
    )
    c = UserDocumentConnector(payload_bytes=text.encode(), filename="note.txt")
    records = c.fetch()

    chunks = [r for r in records if r.record_type == RecordType.DOCUMENT_CHUNK]
    assert len(chunks) >= 1
    assert any("Semaglutide" in r.text_content for r in chunks)

    # Entity mentions should be embedded in the chunk's identifiers for resolution
    assert any("Semaglutide" in (r.identifiers.get("entity_mentions", []))
               for r in chunks)


def test_upload_endpoint_accepts_pdf():
    """POST /upload with multipart file goes through the connector."""
    app = create_app()
    client = TestClient(app)
    fake_pdf = b"%PDF-1.4 test content"
    with patch("connectors.user_document.UserDocumentConnector.fetch", return_value=[]):
        r = client.post(
            "/upload",
            files={"file": ("test.pdf", BytesIO(fake_pdf), "application/pdf")},
        )
    assert r.status_code in (200, 202)
    body = r.json()
    assert "job_id" in body or "records_processed" in body


def test_upload_endpoint_rejects_oversized(monkeypatch):
    monkeypatch.setenv("MZ_DOC_UPLOAD_MAX_MB", "1")
    app = create_app()
    client = TestClient(app)
    big = b"x" * (2 * 1024 * 1024)
    r = client.post(
        "/upload",
        files={"file": ("big.txt", BytesIO(big), "text/plain")},
    )
    assert r.status_code == 413  # Payload Too Large


def test_upload_endpoint_rejects_unsupported_format():
    app = create_app()
    client = TestClient(app)
    r = client.post(
        "/upload",
        files={"file": ("archive.zip", BytesIO(b"PK\x03\x04"), "application/zip")},
    )
    assert r.status_code == 415  # Unsupported Media Type
```

**Run them**: `python -m pytest tests/test_document_extractor.py tests/test_document_ner.py tests/test_user_document_connector.py -v`. All must FAIL.

You will need to add fixture files under `tests/fixtures/documents/`:
- `sample_drug_report.pdf` (a small 1-page PDF mentioning a drug)
- `trial_protocol.docx` (a small Word doc)

Generate these with a script (don't commit large binaries beyond ~50 KB each).

## Implementation Plan

### Step 1 — Add dependencies

In `pyproject.toml` (or `requirements.txt`):
```
pdfplumber>=0.11
python-docx>=1.1
beautifulsoup4>=4.12
```

### Step 2 — Build `services/document_extractor.py`

```python
"""Extract text from uploaded documents.

Supports: PDF (pdfplumber), DOCX (python-docx), HTML (BeautifulSoup),
plain text. Returns a uniform ExtractedDocument."""

import io
import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ExtractedDocument:
    format: str
    pages: list[str] = field(default_factory=list)
    full_text: str = ""
    metadata: dict = field(default_factory=dict)


class UnsupportedFormatError(Exception):
    pass


def extract_text(payload: bytes, filename: str) -> ExtractedDocument:
    max_mb = int(os.getenv("MZ_DOC_UPLOAD_MAX_MB", "25"))
    if len(payload) > max_mb * 1024 * 1024:
        raise ValueError(f"document size exceeds {max_mb} MB limit")

    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if ext == "pdf":
        return _extract_pdf(payload)
    if ext == "docx":
        return _extract_docx(payload)
    if ext in ("html", "htm"):
        return _extract_html(payload)
    if ext == "txt":
        return _extract_txt(payload)
    raise UnsupportedFormatError(f"unsupported format: {ext}")


def _extract_pdf(payload: bytes) -> ExtractedDocument:
    import pdfplumber
    pages = []
    with pdfplumber.open(io.BytesIO(payload)) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_text() or "")
    return ExtractedDocument(
        format="pdf",
        pages=pages,
        full_text="\n\n".join(pages),
        metadata={"page_count": len(pages)},
    )


# ... _extract_docx, _extract_html, _extract_txt
```

### Step 3 — Build `services/document_ner.py`

```python
"""LLM-based NER for drug/company/trial/mechanism/TA mentions in free text."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class EntityMention:
    text: str
    entity_type: str
    start: int
    end: int


NER_PROMPT = """Identify all pharmaceutical entities in the following text.
Return JSON with a "mentions" array. Each mention has: text, type, start, end.

Valid types: drug, company, trial, mechanism, therapeutic_area, investigator.

Only include entities that are clearly named (not generic terms like "the drug").

Text:
{text}
"""


def extract_entities(
    text: str,
    llm,
    chunk_size: int = 12000,
    overlap: int = 500,
) -> list[EntityMention]:
    """Run LLM-NER over text. Chunks long inputs, dedupes mentions."""
    if not text.strip():
        return []

    chunks = _chunk(text, chunk_size, overlap)
    seen: set[tuple[str, str]] = set()
    out: list[EntityMention] = []

    for chunk in chunks:
        try:
            resp = llm.complete_json(NER_PROMPT.format(text=chunk))
            for m in resp.get("mentions", []):
                key = (m["text"].lower(), m["type"])
                if key in seen:
                    continue
                seen.add(key)
                out.append(EntityMention(
                    text=m["text"],
                    entity_type=m["type"],
                    start=m["start"],
                    end=m["end"],
                ))
        except (KeyError, TypeError):
            continue
    return out


def _chunk(text: str, size: int, overlap: int) -> list[str]:
    if len(text) <= size:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        chunks.append(text[start:start + size])
        start += size - overlap
    return chunks
```

### Step 4 — Build `connectors/user_document.py`

```python
"""User-uploaded document connector. Wraps document extraction + NER
into the standard BaseConnector contract."""

import hashlib
from datetime import datetime
from typing import Optional

from connectors.base import (
    BaseConnector, HealthCheckResult, Provenance,
    RawRecord, RecordType, SourceType,
)
from services.document_extractor import extract_text
from services.document_ner import extract_entities


class UserDocumentConnector(BaseConnector):
    def __init__(
        self,
        payload_bytes: bytes,
        filename: str,
        uploader: Optional[str] = None,
        llm=None,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
    ):
        self.payload = payload_bytes
        self.filename = filename
        self.uploader = uploader
        self.llm = llm
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def source_type(self) -> SourceType:
        return SourceType.USER_DOCUMENT

    def health_check(self) -> HealthCheckResult:
        return HealthCheckResult(
            healthy=True,
            source_type=SourceType.USER_DOCUMENT,
            message="upload accepted",
        )

    def fetch(self, since: Optional[datetime] = None) -> list[RawRecord]:
        doc = extract_text(self.payload, self.filename)
        mentions = extract_entities(doc.full_text, llm=self.llm) if self.llm else []

        doc_hash = hashlib.sha256(self.payload).hexdigest()
        external_id = f"USERDOC|{doc_hash[:16]}|{self.filename}"

        prov = Provenance(
            source_type=SourceType.USER_DOCUMENT,
            api_endpoint=f"upload://{self.filename}",
            query_params={"uploader": self.uploader or ""},
            retrieved_at=datetime.utcnow(),
            raw_response_hash=doc_hash,
        )

        records = []
        chunks = _chunk_text(doc.full_text, self.chunk_size, self.chunk_overlap)
        mentions_by_chunk = _assign_mentions(mentions, chunks)

        for i, (chunk_text, chunk_mentions) in enumerate(zip(chunks, mentions_by_chunk)):
            records.append(RawRecord(
                record_type=RecordType.DOCUMENT_CHUNK,
                external_id=f"{external_id}|chunk{i}",
                source_name="UserUpload",
                provenance=prov,
                data={
                    "filename": self.filename,
                    "chunk_index": i,
                    "uploader": self.uploader,
                },
                text_content=chunk_text,
                identifiers={
                    "doc_hash": doc_hash,
                    "entity_mentions": [m.text for m in chunk_mentions],
                    "mention_types": [m.entity_type for m in chunk_mentions],
                },
            ))
        return records


def _chunk_text(text, size, overlap):
    ...

def _assign_mentions(mentions, chunks):
    ...
```

### Step 5 — Wire `RecordType.DOCUMENT_CHUNK`

If not already in `RecordType` enum, add it. The integration pipeline already handles arbitrary text records (as evidenced by the existing `knowledge_chunks` table usage for SEC EDGAR + PMC).

### Step 6 — Add `/upload` endpoint

In `api/routes/` create `upload.py`:

```python
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends

router = APIRouter()


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    pipeline: IntegrationPipeline = Depends(get_pipeline),
    llm = Depends(get_llm),
):
    payload = await file.read()
    try:
        connector = UserDocumentConnector(
            payload_bytes=payload,
            filename=file.filename,
            llm=llm,
        )
        records = connector.fetch()
    except UnsupportedFormatError:
        raise HTTPException(status_code=415, detail="unsupported format")
    except ValueError as e:
        if "exceeds" in str(e):
            raise HTTPException(status_code=413, detail=str(e))
        raise

    pipeline.process(records, source=SourceType.USER_DOCUMENT)
    return {
        "records_processed": len(records),
        "filename": file.filename,
        "entity_mentions": sum(
            len(r.identifiers.get("entity_mentions", [])) for r in records
        ),
    }
```

Register the router in `api/app.py`.

### Step 7 — Wire NER mentions into entity resolution

The `EntityResolver` cascade can already handle name-only mentions. The DOCUMENT_CHUNK records produced above carry `entity_mentions` in identifiers; the post-store hook should iterate these and call resolver to create entity links to the chunk.

This is the only nontrivial wiring step — confirm by reading existing PMC/SEC handling for reference patterns.

### Step 8 — Add a small upload UI panel (frontend, separate PR)

Out of scope for this spec. A new `frontend/src/components/upload/UploadPanel.tsx` will be a separate task.

## Acceptance Criteria

- [ ] All tests in `tests/test_document_extractor.py`, `tests/test_document_ner.py`, `tests/test_user_document_connector.py` pass
- [ ] Existing test suite has zero regressions
- [ ] End-to-end manual test: upload a 5-page pharma PDF, verify:
  - `/upload` returns 200 with `records_processed > 0`
  - Document chunks land in `knowledge_chunks` (or equivalent)
  - At least one entity mention from the doc gets resolved to an existing entity
  - The chunk is searchable via vector similarity for a query that mentions the doc's content
- [ ] Upload of >25 MB returns 413
- [ ] Upload of `.zip` returns 415
- [ ] LLM NER cost: < $0.05 per typical 10-page document (track via telemetry)

## Rollout / Rollback

**Rollout:**
1. Local tests pass.
2. Deploy to Railway with `MZ_DOC_UPLOAD_MAX_MB=25`.
3. Manually upload 3 representative documents (drug label PDF, trial protocol DOCX, news HTML).
4. Verify entity resolution links got created for each.
5. Watch LLM cost telemetry for 24h.

**Rollback:**
- Remove the `/upload` route registration → endpoint vanishes immediately.
- Document chunks already in DB are safe (don't break anything else).
- No schema migration needed if `RecordType.DOCUMENT_CHUNK` already exists.

## Out of Scope

- Frontend upload UI (separate task)
- OCR for image-based PDFs (defer — start with text-PDF only)
- Async background processing (`/upload` is synchronous in v1; large docs accepted but block the request — set client timeout accordingly)
- URL-based ingestion (`SourceType.USER_URL`) — separate spec, builds on this
- Per-user quotas / auth (current upload is open; add when user accounts ship)
