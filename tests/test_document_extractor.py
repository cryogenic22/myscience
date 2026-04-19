"""SPEC_014 Phase 4c — Document Extractor TDD test contract.

Tests for services/document_extractor.py: text extraction from PDF/DOCX/HTML/text
with per-page output, size limit enforcement, and format detection.

Per the reuse catalog (SPEC_017), this is a port from Proto_Demo's
FormattingExtractor (simplified — we drop the FormattedDocument IR and just
return pages of plain text).

All tests must FAIL before implementation. TDD discipline.
"""

from __future__ import annotations

import io
import os
from pathlib import Path

import pytest


# ────────────────────────────────────────────────────────────────────
# Test fixtures (generated programmatically to avoid binary commits)
# ────────────────────────────────────────────────────────────────────

def _make_pdf_bytes(pages: list[str]) -> bytes:
    """Build a minimal PDF in memory using pdfplumber's underlying lib.

    pdfplumber doesn't provide a writer; use reportlab if installed,
    else skip — pdf-write is not a hard requirement for tests.
    """
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import letter
    except ImportError:
        pytest.skip("reportlab not installed — install for PDF write fixtures")
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    for page_text in pages:
        c.drawString(72, 720, page_text)
        c.showPage()
    c.save()
    return buf.getvalue()


def _make_docx_bytes(paragraphs: list[str]) -> bytes:
    """Build a minimal DOCX in memory using python-docx."""
    from docx import Document
    doc = Document()
    for para in paragraphs:
        doc.add_paragraph(para)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ────────────────────────────────────────────────────────────────────
# Module / class existence
# ────────────────────────────────────────────────────────────────────

def test_module_exists():
    """SPEC_014: services/document_extractor.py must exist."""
    p = Path("services/document_extractor.py")
    assert p.exists(), "Create services/document_extractor.py"


def test_extract_text_function_exists():
    from services.document_extractor import extract_text
    assert callable(extract_text)


def test_extracted_document_dataclass():
    from services.document_extractor import ExtractedDocument
    fields = ExtractedDocument.__dataclass_fields__
    required = {"format", "pages", "full_text", "metadata"}
    assert required.issubset(set(fields))


def test_unsupported_format_error_class():
    from services.document_extractor import UnsupportedFormatError
    assert issubclass(UnsupportedFormatError, Exception)


# ────────────────────────────────────────────────────────────────────
# Plain text extraction
# ────────────────────────────────────────────────────────────────────

def test_extract_plain_text():
    from services.document_extractor import extract_text
    payload = b"Semaglutide is a GLP-1 receptor agonist."
    doc = extract_text(payload, filename="notes.txt")
    assert doc.format == "txt"
    assert "Semaglutide" in doc.full_text
    assert len(doc.pages) >= 1


def test_extract_plain_text_utf8():
    from services.document_extractor import extract_text
    payload = "Drug: tirzepatide™".encode("utf-8")
    doc = extract_text(payload, filename="notes.txt")
    assert "tirzepatide" in doc.full_text


# ────────────────────────────────────────────────────────────────────
# HTML extraction
# ────────────────────────────────────────────────────────────────────

def test_extract_html_strips_tags():
    from services.document_extractor import extract_text
    html = b"<html><body><h1>Trial</h1><p>Tirzepatide weight loss</p></body></html>"
    doc = extract_text(html, filename="page.html")
    assert doc.format == "html"
    assert "Tirzepatide weight loss" in doc.full_text
    assert "<p>" not in doc.full_text
    assert "<html>" not in doc.full_text


def test_extract_html_preserves_text_with_entities():
    from services.document_extractor import extract_text
    html = b"<html><body><p>Drug &amp; mechanism</p></body></html>"
    doc = extract_text(html, filename="page.html")
    assert "Drug" in doc.full_text
    assert "mechanism" in doc.full_text


# ────────────────────────────────────────────────────────────────────
# DOCX extraction
# ────────────────────────────────────────────────────────────────────

def test_extract_docx_returns_paragraphs():
    from services.document_extractor import extract_text
    docx_bytes = _make_docx_bytes([
        "Trial Protocol: Semaglutide vs Placebo",
        "Phase 3 multicentre randomised study.",
    ])
    doc = extract_text(docx_bytes, filename="protocol.docx")
    assert doc.format == "docx"
    assert "Semaglutide" in doc.full_text
    assert "multicentre" in doc.full_text


# ────────────────────────────────────────────────────────────────────
# PDF extraction (per-page)
# ────────────────────────────────────────────────────────────────────

def test_extract_pdf_returns_pages():
    from services.document_extractor import extract_text
    pdf_bytes = _make_pdf_bytes(["Page one: tirzepatide", "Page two: SURMOUNT-5"])
    doc = extract_text(pdf_bytes, filename="trial.pdf")
    assert doc.format == "pdf"
    assert len(doc.pages) == 2
    assert "tirzepatide" in doc.pages[0]
    assert "SURMOUNT-5" in doc.pages[1]
    assert "tirzepatide" in doc.full_text
    assert "SURMOUNT-5" in doc.full_text


def test_extract_pdf_metadata_includes_page_count():
    from services.document_extractor import extract_text
    pdf_bytes = _make_pdf_bytes(["A", "B", "C"])
    doc = extract_text(pdf_bytes, filename="multi.pdf")
    assert doc.metadata.get("page_count") == 3


# ────────────────────────────────────────────────────────────────────
# Format detection
# ────────────────────────────────────────────────────────────────────

def test_format_detection_by_extension():
    from services.document_extractor import _detect_format
    assert _detect_format(b"x", "doc.pdf") == "pdf"
    assert _detect_format(b"x", "doc.PDF") == "pdf"  # case-insensitive
    assert _detect_format(b"x", "doc.docx") == "docx"
    assert _detect_format(b"x", "doc.html") == "html"
    assert _detect_format(b"x", "doc.htm") == "html"
    assert _detect_format(b"x", "doc.txt") == "txt"


def test_format_detection_by_magic_bytes_when_no_extension():
    """PDF starts with %PDF-, even without .pdf extension we should detect."""
    from services.document_extractor import _detect_format
    pdf_magic = b"%PDF-1.4 ..."
    # When extension is missing or .bin, magic bytes should be checked
    assert _detect_format(pdf_magic, "anonymous") == "pdf"


# ────────────────────────────────────────────────────────────────────
# Size limit
# ────────────────────────────────────────────────────────────────────

def test_size_limit_enforced(monkeypatch):
    from services.document_extractor import extract_text
    monkeypatch.setenv("MZ_DOC_UPLOAD_MAX_MB", "1")
    big = b"x" * (2 * 1024 * 1024)  # 2 MB
    with pytest.raises(ValueError, match="exceeds.*1 MB"):
        extract_text(big, filename="big.txt")


def test_size_limit_default_25mb(monkeypatch):
    from services.document_extractor import extract_text
    monkeypatch.delenv("MZ_DOC_UPLOAD_MAX_MB", raising=False)
    # 1 MB should be fine under default 25 MB
    payload = b"x" * (1024 * 1024)
    # Plain text doesn't fail on size — just on format
    doc = extract_text(payload, filename="ok.txt")
    assert doc.format == "txt"


# ────────────────────────────────────────────────────────────────────
# Unsupported format
# ────────────────────────────────────────────────────────────────────

def test_unsupported_format_raises():
    from services.document_extractor import extract_text, UnsupportedFormatError
    with pytest.raises(UnsupportedFormatError):
        extract_text(b"PK\x03\x04", filename="archive.zip")


def test_unsupported_with_no_extension():
    from services.document_extractor import extract_text, UnsupportedFormatError
    with pytest.raises(UnsupportedFormatError):
        extract_text(b"\x00\x01\x02 binary garbage", filename="mystery")


# ────────────────────────────────────────────────────────────────────
# Defensive: empty / corrupt input
# ────────────────────────────────────────────────────────────────────

def test_empty_payload_returns_empty_document():
    from services.document_extractor import extract_text
    doc = extract_text(b"", filename="empty.txt")
    assert doc.format == "txt"
    assert doc.full_text == ""
    assert doc.pages in ([], [""])


def test_corrupt_pdf_raises_descriptively():
    from services.document_extractor import extract_text
    # Has the %PDF- magic but garbage body
    payload = b"%PDF-1.4\nthis is not actually a valid pdf"
    with pytest.raises(Exception) as excinfo:
        extract_text(payload, filename="broken.pdf")
    # Message should not be a generic "list index out of range" type error
    msg = str(excinfo.value).lower()
    assert any(word in msg for word in ("pdf", "parse", "invalid", "corrupt"))
