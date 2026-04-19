"""SPEC_014 Phase 4c — Document upload endpoint.

POST /upload accepts a multipart file, runs it through the UserDocumentConnector
(extract → NER → chunk → emit RawRecords), and (in v1) returns a summary of
records produced + entity mentions found.

In a follow-up commit the upload will also feed the IntegrationPipeline so the
chunks land in the knowledge_chunks table and entity links get created.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from api.deps import get_db, get_llm, require_role
from connectors.user_document import UserDocumentConnector
from services.document_extractor import UnsupportedFormatError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/upload", tags=["upload"])


@router.post("", dependencies=[Depends(require_role("uploader"))])
async def upload_document(
    file: UploadFile = File(...),
    llm = Depends(get_llm),
    db = Depends(get_db),
):
    """Upload a document for ingestion into the knowledge graph.

    Returns:
        {
          "filename": str,
          "format": str,
          "records_processed": int,
          "entity_mentions_total": int,
          "doc_hash": str
        }

    Errors:
        413 Payload Too Large — exceeds MZ_DOC_UPLOAD_MAX_MB
        415 Unsupported Media Type — unrecognized format
        422 Unprocessable — missing or empty file
    """
    if file is None or not file.filename:
        raise HTTPException(status_code=422, detail="no file provided")

    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=422, detail="empty file")

    try:
        connector = UserDocumentConnector(
            payload_bytes=payload,
            filename=file.filename,
            llm=llm,
        )
        records = connector.fetch()
    except UnsupportedFormatError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    except ValueError as exc:
        # Most ValueError from the extractor is the size-limit case
        msg = str(exc)
        if "exceeds" in msg.lower():
            raise HTTPException(status_code=413, detail=msg) from exc
        # Other ValueErrors (e.g. corrupt PDF) → 400
        raise HTTPException(status_code=400, detail=msg) from exc
    except Exception as exc:
        logger.exception("upload failed for %s", file.filename)
        raise HTTPException(status_code=500, detail=f"upload failed: {exc}") from exc

    # Aggregate response stats
    entity_mentions_total = sum(
        len(r.identifiers.get("entity_mentions", []) or []) for r in records
    )
    doc_hash = records[0].identifiers.get("doc_hash", "") if records else ""
    fmt = records[0].data.get("format", "") if records else ""

    # TODO (follow-up): feed records into IntegrationPipeline so they land in
    # the knowledge_chunks table + entity_links get created. For v1 we just
    # return the summary so the upload UI can show what was extracted.

    return {
        "filename": file.filename,
        "format": fmt,
        "records_processed": len(records),
        "entity_mentions_total": entity_mentions_total,
        "doc_hash": doc_hash,
    }
