"""UserDocumentConnector — ingests user-uploaded documents into the pipeline.

SPEC_014 Phase 4c. Wraps:
  - services/document_extractor.extract_text() — PDF/DOCX/HTML/text extraction
  - services/document_ner.extract_entities() — LLM-based NER

Produces DOCUMENT_CHUNK RawRecords. Each chunk carries:
  - text_content for embedding
  - identifiers["entity_mentions"] = list of canonical entity texts mentioned
  - identifiers["mention_types"] = parallel list of entity types
  - identifiers["doc_hash"] = SHA-256 of original payload (for dedup across uploads)

The integration pipeline's entity_resolver uses the entity_mentions to create
links between this DOCUMENT_CHUNK record and the canonical entities in our DB.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from typing import Any, Optional

from connectors.base import (
    BaseConnector,
    HealthCheckResult,
    Provenance,
    RawRecord,
    RecordType,
    SourceType,
)
from services.document_extractor import extract_text
from services.document_ner import extract_entities

logger = logging.getLogger(__name__)


_DEFAULT_CHUNK_TOKENS = 500
_DEFAULT_CHUNK_OVERLAP_TOKENS = 50
# Cheap heuristic — average ~4 chars per token for English prose.
# Used only for chunking long documents; precise token count not needed.
_CHARS_PER_TOKEN = 4


class UserDocumentConnector(BaseConnector):
    """Ingests a single uploaded document. One connector instance per upload.

    Unlike other connectors which fetch from external APIs, this connector
    receives its payload at construction time. The fetch() method runs
    text extraction + NER + chunking, then yields DOCUMENT_CHUNK records.
    """

    def __init__(
        self,
        payload_bytes: bytes,
        filename: str,
        uploader: Optional[str] = None,
        llm: Any = None,
        chunk_tokens: int = _DEFAULT_CHUNK_TOKENS,
        chunk_overlap_tokens: int = _DEFAULT_CHUNK_OVERLAP_TOKENS,
    ):
        self._payload = payload_bytes
        self._filename = filename or "unnamed"
        self._uploader = uploader
        self._llm = llm
        self._chunk_tokens = chunk_tokens
        self._chunk_overlap_tokens = chunk_overlap_tokens

    # ── BaseConnector interface ────────────────────────────────

    def source_type(self) -> SourceType:
        return SourceType.USER_DOCUMENT

    def health_check(self) -> HealthCheckResult:
        # No upstream dependency — connector is purely local processing.
        return HealthCheckResult(
            healthy=True,
            source_type=SourceType.USER_DOCUMENT,
            message="user document upload (no remote dependency)",
        )

    def fetch(self, since: Optional[datetime] = None) -> list[RawRecord]:
        """Extract text → run NER → chunk → emit RawRecords."""
        # 1. Extract text from the document
        doc = extract_text(self._payload, filename=self._filename)

        # 2. Run NER on full text (defensive — returns [] if no LLM)
        try:
            mentions = extract_entities(doc.full_text, llm=self._llm)
        except Exception as exc:
            logger.warning("NER failed on %s: %s", self._filename, exc)
            mentions = []

        # 3. Chunk the text
        chunk_chars = max(self._chunk_tokens * _CHARS_PER_TOKEN, 100)
        overlap_chars = self._chunk_overlap_tokens * _CHARS_PER_TOKEN
        chunks = _chunk_text(doc.full_text, chunk_chars, overlap_chars)

        # 4. Build provenance — same for all chunks of this upload
        doc_hash = hashlib.sha256(self._payload).hexdigest()
        external_id_base = f"USERDOC|{doc_hash[:16]}|{self._filename}"
        prov = Provenance(
            source_type=SourceType.USER_DOCUMENT,
            api_endpoint=f"upload://{self._filename}",
            query_params={"uploader": self._uploader or ""},
            retrieved_at=datetime.utcnow(),
            raw_response_hash=doc_hash,
        )

        # 5. Assign mentions to chunks by character offset
        mentions_by_chunk = _assign_mentions_to_chunks(
            mentions, chunks, doc.full_text, chunk_chars, overlap_chars,
        )

        # 6. Emit RawRecord per chunk
        records: list[RawRecord] = []
        for i, (chunk_text, chunk_mentions) in enumerate(zip(chunks, mentions_by_chunk)):
            mention_texts = [m.text for m in chunk_mentions]
            mention_types = [m.entity_type for m in chunk_mentions]
            records.append(RawRecord(
                record_type=RecordType.DOCUMENT_CHUNK,
                external_id=f"{external_id_base}|chunk{i}",
                source_name="UserUpload",
                provenance=prov,
                data={
                    "filename": self._filename,
                    "chunk_index": i,
                    "chunk_count": len(chunks),
                    "uploader": self._uploader,
                    "format": doc.format,
                },
                text_content=chunk_text,
                identifiers={
                    "doc_hash": doc_hash,
                    "entity_mentions": mention_texts,
                    "mention_types": mention_types,
                },
            ))

        if not records:
            # Degenerate case (empty document) — emit a single empty chunk so
            # downstream pipeline still tracks the upload.
            records.append(RawRecord(
                record_type=RecordType.DOCUMENT_CHUNK,
                external_id=f"{external_id_base}|chunk0",
                source_name="UserUpload",
                provenance=prov,
                data={
                    "filename": self._filename,
                    "chunk_index": 0,
                    "chunk_count": 0,
                    "uploader": self._uploader,
                    "format": doc.format,
                    "empty": True,
                },
                text_content="",
                identifiers={"doc_hash": doc_hash, "entity_mentions": [], "mention_types": []},
            ))

        return records


# ── Helpers ────────────────────────────────────────────────────────

def _chunk_text(text: str, size: int, overlap: int) -> list[str]:
    """Split text into overlapping chunks. Returns single chunk if text fits."""
    if not text:
        return []
    if len(text) <= size:
        return [text]
    chunks: list[str] = []
    start = 0
    step = max(1, size - overlap)
    while start < len(text):
        chunks.append(text[start:start + size])
        start += step
    return chunks


def _assign_mentions_to_chunks(
    mentions, chunks: list[str], full_text: str, size: int, overlap: int,
) -> list[list]:
    """Assign each mention to chunk(s) it falls within based on char offsets."""
    if not chunks:
        return []
    if len(chunks) == 1:
        return [list(mentions)]

    step = max(1, size - overlap)
    out: list[list] = [[] for _ in chunks]
    for m in mentions:
        # A mention at offset `m.start` belongs in any chunk whose [start, start+size)
        # window contains it. With overlap, a single mention can land in 1-2 chunks.
        for i in range(len(chunks)):
            chunk_start = i * step
            chunk_end = chunk_start + size
            if chunk_start <= m.start < chunk_end:
                out[i].append(m)
    return out
