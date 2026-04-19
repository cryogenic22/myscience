"""SPEC_014 Phase 4c — Document upload endpoint.

POST /upload accepts a multipart file, builds a UserDocumentConnector, then
hands it to IntegrationPipeline.run() so the document flows through the
standard 5-step pipeline (normalize → resolve → embed → store → cross-link).
Chunks land in knowledge_chunks; entity mentions become entity_links via
the existing 6-strategy resolver cascade.

Auth: requires `uploader` role (SPEC_018).
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from api.deps import (
    get_integration_pipeline,
    get_llm,
    require_role,
)
from connectors.user_document import UserDocumentConnector
from services.document_extractor import UnsupportedFormatError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/upload", tags=["upload"])


@router.post("", dependencies=[Depends(require_role("uploader"))])
async def upload_document(
    file: UploadFile = File(...),
    llm = Depends(get_llm),
    pipeline = Depends(get_integration_pipeline),
):
    """Upload a document for ingestion into the knowledge graph.

    Returns the IntegrationPipeline summary plus filename + doc_hash + format
    + entity_mentions_total. Errors:
        413 Payload Too Large — exceeds MZ_DOC_UPLOAD_MAX_MB
        415 Unsupported Media Type — unrecognized format
        422 Unprocessable — missing or empty file
        500 — pipeline run failed
    """
    if file is None or not file.filename:
        raise HTTPException(status_code=422, detail="no file provided")

    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=422, detail="empty file")

    # Build the connector (validates format + size BEFORE running the pipeline).
    # We build a fresh instance per upload so each document gets isolated
    # provenance; the pipeline calls connector.fetch() exactly once.
    try:
        connector = UserDocumentConnector(
            payload_bytes=payload,
            filename=file.filename,
            llm=llm,
        )
        # Eager fetch to surface format/size errors as 4xx BEFORE the pipeline
        # opens an etl_run record. Pipeline will fetch again — that's fine
        # since extraction is deterministic.
        preview_records = connector.fetch()
    except UnsupportedFormatError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    except ValueError as exc:
        msg = str(exc)
        if "exceeds" in msg.lower():
            raise HTTPException(status_code=413, detail=msg) from exc
        raise HTTPException(status_code=400, detail=msg) from exc

    # Capture stats from the fetch (before pipeline mutates state)
    entity_mentions_total = sum(
        len(r.identifiers.get("entity_mentions", []) or []) for r in preview_records
    )
    doc_hash = preview_records[0].identifiers.get("doc_hash", "") if preview_records else ""
    fmt = preview_records[0].data.get("format", "") if preview_records else ""

    # Run through the integration pipeline — persists chunks + creates links
    try:
        result = pipeline.run(connector)
    except Exception as exc:
        logger.exception("pipeline failed for upload %s", file.filename)
        raise HTTPException(
            status_code=500,
            detail=f"upload pipeline failed: {exc}",
        ) from exc

    summary = result.summary() if hasattr(result, "summary") else {}

    return {
        "filename": file.filename,
        "format": fmt,
        "doc_hash": doc_hash,
        "entity_mentions_total": entity_mentions_total,
        # Pipeline result fields
        "etl_run_id": summary.get("etl_run_id"),
        "records_processed": summary.get("processed", len(preview_records)),
        "records_inserted": summary.get("inserted", 0),
        "records_updated": summary.get("updated", 0),
        "links_created": summary.get("links_created", 0),
        "errors": summary.get("errors", []),
    }

