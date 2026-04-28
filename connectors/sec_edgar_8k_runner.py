"""SEC EDGAR ↔ 8-K pipeline runner — Cycle 1 (Epic 1 close-out).

Connector-side glue: takes filing text + metadata from connectors/
sec_edgar.py and runs it through the α1+α2+α3 pipeline. Handles:

  - Feature-flag gating (MZ_8K_PIPELINE_ENABLED)
  - LLM credentials gating (ANTHROPIC_API_KEY preferred, OPENAI_API_KEY fallback)
  - CIK → company_id resolution (against existing companies table)
  - Source document id derivation (deterministic from accession)
  - Build all 4 extractors via α1 factories
  - Call process_8k_filing() and return its ProcessResult

The connector calls run_8k_through_pipeline() inside _process_filing
when form_type matches 8-K. Errors are logged but don't propagate to
the connector — existing behaviour preserved end-to-end.
"""

from __future__ import annotations

import hashlib
import logging
import os
import uuid
from datetime import date
from typing import Any, Optional

from services.sec_8k_pipeline import process_8k_filing, ProcessResult
from services.db_adapter_8k import build_adapter
from services.extraction_llm import (
    StructuredCall,
    make_anthropic_structured_call,
    make_openai_structured_call,
    make_exec_change_extractor,
    make_deal_extractor,
    make_financial_extractor,
    make_crl_extractor,
)

logger = logging.getLogger(__name__)


_FEATURE_FLAG = "MZ_8K_PIPELINE_ENABLED"


# ────────────────────────────────────────────────────────────────────
# Form-type filter
# ────────────────────────────────────────────────────────────────────

def should_run_pipeline_for_form(form_type: Optional[str]) -> bool:
    """True iff this form type goes through the 8-K pipeline.

    Matches 8-K and amended 8-K/A. Other forms (10-K, 10-Q, DEF 14A,
    S-1, etc.) are out of scope for this pipeline (they have their
    own ETL paths in the existing connector).
    """
    if not form_type:
        return False
    canonical = form_type.strip().upper()
    return canonical == "8-K" or canonical == "8-K/A"


# ────────────────────────────────────────────────────────────────────
# Source-document-id derivation
# ────────────────────────────────────────────────────────────────────

# UUID namespace for SEC filings. Allows deterministic UUID derivation
# from accession numbers without DB round-trips.
_SEC_FILING_NAMESPACE = uuid.UUID("8e555000-aaaa-aaaa-aaaa-000000000001")


def _accession_to_uuid(accession: str) -> str:
    """Deterministic UUID from an SEC accession number.

    Same accession always yields same UUID; collision is cryptographically
    negligible. Used as source_document_id when the source_records row
    hasn't been written yet (or when we want to write market_events
    before source_records is populated).
    """
    return str(uuid.uuid5(_SEC_FILING_NAMESPACE, accession))


# ────────────────────────────────────────────────────────────────────
# Structured-call factory — picks Anthropic or OpenAI per env
# ────────────────────────────────────────────────────────────────────


def _build_structured_call() -> Optional[StructuredCall]:
    """Construct an LLM StructuredCall using whichever provider has
    credentials available. Returns None if neither is configured."""
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")

    if anthropic_key:
        try:
            from anthropic import Anthropic
            client = Anthropic(api_key=anthropic_key)
            model = os.environ.get(
                "MZ_8K_LLM_MODEL", "claude-opus-4-7",
            )
            return make_anthropic_structured_call(client=client, model=model)
        except ImportError:
            logger.warning(
                "anthropic SDK not installed; falling back to OpenAI",
            )
        except Exception as exc:
            logger.warning("anthropic client init failed: %s", exc)

    if openai_key:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=openai_key)
            model = os.environ.get(
                "MZ_8K_LLM_MODEL", "gpt-4o",
            )
            return make_openai_structured_call(client=client, model=model)
        except ImportError:
            logger.warning("openai SDK not installed")
        except Exception as exc:
            logger.warning("openai client init failed: %s", exc)

    return None


# ────────────────────────────────────────────────────────────────────
# CIK resolution
# ────────────────────────────────────────────────────────────────────


_RESOLVE_BY_CIK_SQL = """
    SELECT id FROM companies
    WHERE cik = %s
    LIMIT 1
"""


def _resolve_company_id_by_cik(db: Any, cik: str) -> Optional[str]:
    """Look up a company_id by CIK (zero-padded string). Returns None
    if not found."""
    if not cik:
        return None
    # Normalise CIK to canonical 10-digit padded form to match how the
    # existing SEC EDGAR connector stores it
    normalised = cik.lstrip("0").zfill(10) if cik.lstrip("0") else cik

    # Try the exact-as-passed first, then the normalised form
    for value in (cik, normalised):
        row = db.fetch_one(_RESOLVE_BY_CIK_SQL, [value])
        if row and row.get("id"):
            return str(row["id"])
    return None


# ────────────────────────────────────────────────────────────────────
# Public API — single entry point the connector calls
# ────────────────────────────────────────────────────────────────────


def run_8k_through_pipeline(
    *,
    filing_text: str,
    cik: str,
    company_name: str,
    accession: str,
    filing_date: date,
    db: Any,
) -> Optional[ProcessResult]:
    """Run a single 8-K filing through the α1+α2+α3 pipeline.

    Returns:
        - None when feature flag is off
        - None when no LLM credentials configured
        - None when CIK can't be resolved to a company_id
        - ProcessResult otherwise (with counts/errors)

    All errors logged. Never raises — the caller (sec_edgar connector)
    must keep working regardless.
    """
    if os.environ.get(_FEATURE_FLAG, "false").lower() != "true":
        return None

    structured_call = _build_structured_call()
    if structured_call is None:
        logger.info(
            "8-K pipeline: no LLM credentials configured (set "
            "ANTHROPIC_API_KEY or OPENAI_API_KEY); skipping",
        )
        return None

    company_id = _resolve_company_id_by_cik(db, cik)
    if not company_id:
        logger.warning(
            "8-K pipeline: cik %s does not resolve to a company; skipping",
            cik,
        )
        return None

    extractors = {
        "exec_change": make_exec_change_extractor(structured_call=structured_call),
        "deal":        make_deal_extractor(structured_call=structured_call),
        "financial":   make_financial_extractor(structured_call=structured_call),
        "crl":         make_crl_extractor(structured_call=structured_call),
    }

    source_document_id = _accession_to_uuid(accession)
    adapter = build_adapter(db)

    try:
        return process_8k_filing(
            filing_text=filing_text,
            filer_company_id=company_id,
            filer_company_name=company_name,
            source_document_id=source_document_id,
            disclosed_date=filing_date,
            db=adapter,
            extractors=extractors,
        )
    except Exception as exc:
        logger.error(
            "8-K pipeline failed unexpectedly for accession %s: %s",
            accession, exc,
        )
        # Surface as an inert ProcessResult so the connector can log
        # counts even on failure
        return ProcessResult(errors=[f"unhandled: {exc}"])
