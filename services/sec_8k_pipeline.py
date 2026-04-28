"""SEC 8-K orchestration pipeline — Epic 1 α2.

The bridge from "unit-tested parsers" to "real events flowing." Wires
together everything from A2.1–A2.4 + α1:

  filing text + filer entity
    → 4 parsers (via α1 extractors)
    → event_row builders
    → DB writes (market_events, deals, investigators.roles_history)

After α2, a connector calls process_8k_filing() once per fetched
filing. The right rows land in the right tables.

Design choices

  - Idempotency by event_hash. The DB adapter returns False on
    duplicate hash; the pipeline counts those as duplicates_skipped
    rather than emitted.

  - Per-Item error isolation. If one extractor explodes, the others
    still run and their events still persist. The error is recorded
    on the result but never raised.

  - Feature-flagged via MZ_8K_PIPELINE_ENABLED env var. Off by default
    until the schema migrations land in prod (deals + roles_history
    columns must exist).

  - DB is an Adapter (insert_event, insert_deal, append_roles_history,
    resolve_drug_id). The MockDB in tests implements the adapter.
    Real Database class implements it in services/db_adapter_8k.py
    (separate PR — keeps this orchestrator pure-logic).

  - transition_id pairing happens on the exec_change list BEFORE
    event-row construction so the transition_id is captured on every
    row.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional, Protocol

from connectors.sec_8k.item_5_02 import (
    parse_item_5_02,
    assign_transition_ids,
)
from connectors.sec_8k.item_1_01 import parse_item_1_01
from connectors.sec_8k.item_2_02 import parse_item_2_02
from connectors.sec_8k.item_8_01 import parse_item_8_01

from services.event_emitters.exec_change import build_event_row as build_exec_row
from services.event_emitters.deal_announced import (
    build_event_row as build_deal_event_row,
    build_deals_row,
)
from services.event_emitters.financial_disclosure import (
    build_financial_disclosure_row,
    build_guidance_change_row,
)
from services.event_emitters.regulatory_crl import (
    build_event_row as build_crl_event_row,
)

from services.person_roles import build_role_entry

logger = logging.getLogger(__name__)


_FEATURE_FLAG_ENV = "MZ_8K_PIPELINE_ENABLED"


# ────────────────────────────────────────────────────────────────────
# DB adapter Protocol
# ────────────────────────────────────────────────────────────────────


class DBAdapter(Protocol):
    """The pipeline only needs these four operations from the DB.

    Real implementation (services/db_adapter_8k.py) wraps the existing
    Database class. Tests pass a MockDB that records calls.
    """

    def insert_event(self, row: dict[str, Any]) -> bool:
        """Insert one market_events row.
        Returns True if inserted, False if event_hash already exists.
        """
        ...

    def insert_deal(self, row: dict[str, Any]) -> str:
        """Insert one deals row. Returns deal_id (uuid string)."""
        ...

    def append_roles_history(
        self,
        person_name: str,
        entry: dict[str, Any],
        *,
        company_id: str,
    ) -> bool:
        """Append `entry` to investigators.roles_history for the named
        person (creating the investigator row if absent)."""
        ...

    def resolve_drug_id(self, drug_name: str) -> Optional[str]:
        """Resolve a drug code/name to a drugs.id, or None if not found."""
        ...


# ────────────────────────────────────────────────────────────────────
# Result type
# ────────────────────────────────────────────────────────────────────


@dataclass
class ProcessResult:
    events_emitted: int = 0
    deals_emitted: int = 0
    roles_appended: int = 0
    duplicates_skipped: int = 0
    errors: list[str] = field(default_factory=list)
    disabled: bool = False


# ────────────────────────────────────────────────────────────────────
# Public API
# ────────────────────────────────────────────────────────────────────


def process_8k_filing(
    *,
    filing_text: str,
    filer_company_id: str,
    filer_company_name: str,
    source_document_id: str,
    disclosed_date: date,
    db: DBAdapter,
    extractors: dict[str, Any],
) -> ProcessResult:
    """Process a single 8-K filing end-to-end.

    Runs all 4 Item-code parsers (1.01, 2.02, 5.02, 8.01) over the
    filing text using the LLM extractors (typically built via α1's
    factory functions). Writes events / deals / roles_history.

    Args:
        filing_text: Full text of the 8-K (already HTML-stripped by the
                     SEC connector).
        filer_company_id: UUID of the filer company (already resolved
                          via the SEC EDGAR connector's CIK lookup).
        filer_company_name: Display name for descriptions.
        source_document_id: source_records.id for this filing.
        disclosed_date: Filing date — used as `disclosed_date` on every
                        event_row.
        db: A DBAdapter implementation.
        extractors: Dict with keys "exec_change", "deal", "financial",
                    "crl" — each value is the corresponding factory
                    output from services.extraction_llm.

    Returns:
        ProcessResult with counts + errors. Never raises.
    """
    result = ProcessResult()

    # Feature flag — early bail-out
    if os.environ.get(_FEATURE_FLAG_ENV, "false").lower() != "true":
        result.disabled = True
        return result

    # Item 5.02 — exec_change events + roles_history append
    _process_item_5_02(
        filing_text=filing_text,
        filer_company_id=filer_company_id,
        filer_company_name=filer_company_name,
        source_document_id=source_document_id,
        disclosed_date=disclosed_date,
        db=db,
        extractor=extractors.get("exec_change"),
        result=result,
    )

    # Item 1.01 — deal_announced events + deals row
    _process_item_1_01(
        filing_text=filing_text,
        filer_company_id=filer_company_id,
        filer_company_name=filer_company_name,
        source_document_id=source_document_id,
        disclosed_date=disclosed_date,
        db=db,
        extractor=extractors.get("deal"),
        result=result,
    )

    # Item 2.02 — financial_disclosure + guidance_change events
    _process_item_2_02(
        filing_text=filing_text,
        filer_company_id=filer_company_id,
        filer_company_name=filer_company_name,
        source_document_id=source_document_id,
        disclosed_date=disclosed_date,
        db=db,
        extractor=extractors.get("financial"),
        result=result,
    )

    # Item 8.01 — regulatory_crl events
    _process_item_8_01(
        filing_text=filing_text,
        filer_company_id=filer_company_id,
        filer_company_name=filer_company_name,
        source_document_id=source_document_id,
        disclosed_date=disclosed_date,
        db=db,
        extractor=extractors.get("crl"),
        result=result,
    )

    return result


# ────────────────────────────────────────────────────────────────────
# Per-Item handlers — error-isolated
# ────────────────────────────────────────────────────────────────────


def _process_item_5_02(
    *, filing_text, filer_company_id, filer_company_name,
    source_document_id, disclosed_date, db, extractor, result: ProcessResult,
) -> None:
    if extractor is None:
        return
    try:
        items = parse_item_5_02(filing_text, extractor=extractor)
        if not items:
            return
        # transition_id pairing — must happen BEFORE row construction
        items = assign_transition_ids(items, company_id=filer_company_id)
        for ec in items:
            row = build_exec_row(
                extraction=ec,
                company_id=filer_company_id,
                company_name=filer_company_name,
                source_document_id=source_document_id,
                disclosed_date=disclosed_date,
            )
            inserted = db.insert_event(row)
            if inserted:
                result.events_emitted += 1
                # Append a roles_history entry for the person.
                # Title: prior_role on departure / role_change /
                # board_resignation; new_role on appointment / promotion /
                # board_election.
                title = ec.prior_role or ec.new_role or ""
                start_date = (
                    ec.effective_date.isoformat()
                    if ec.change_type in (
                        "appointment", "promotion", "board_election",
                    )
                    else None
                )
                end_date = (
                    ec.effective_date.isoformat()
                    if ec.change_type in (
                        "departure", "role_change", "board_resignation",
                    )
                    else None
                )
                entry = build_role_entry(
                    company_id=filer_company_id,
                    company_name=filer_company_name,
                    title=title,
                    start_date=start_date,
                    end_date=end_date,
                    transition_id=ec.transition_id,
                    source_document_id=source_document_id,
                    confirmed=True,   # SEC = confirmed tier
                )
                if db.append_roles_history(
                    ec.person_name, entry, company_id=filer_company_id,
                ):
                    result.roles_appended += 1
            else:
                result.duplicates_skipped += 1
    except Exception as exc:
        logger.warning("Item 5.02 processing failed: %s", exc)
        result.errors.append(f"exec_change: {exc}")


def _process_item_1_01(
    *, filing_text, filer_company_id, filer_company_name,
    source_document_id, disclosed_date, db, extractor, result: ProcessResult,
) -> None:
    if extractor is None:
        return
    try:
        items = parse_item_1_01(filing_text, extractor=extractor)
        for d in items:
            event_row = build_deal_event_row(
                extraction=d,
                primary_company_id=filer_company_id,
                primary_company_name=filer_company_name,
                counterparty_company_id=None,
                counterparty_company_name=(
                    d.licensor_name if d.licensee_name == filer_company_name
                    else d.licensee_name
                    or d.target_name
                    or d.acquirer_name
                ),
                source_document_id=source_document_id,
                disclosed_date=disclosed_date,
            )
            inserted = db.insert_event(event_row)
            if inserted:
                result.events_emitted += 1
                # Build the deals row. Direction-aware party assignment.
                # The filer is the licensee (when license_in) or licensor
                # (when license_out) or acquirer (acquisition) etc.
                acquirer_id = (
                    filer_company_id
                    if "acquisition" in d.deal_types and d.acquirer_name == filer_company_name
                    else None
                )
                target_id = (
                    filer_company_id
                    if "acquisition" in d.deal_types and d.target_name == filer_company_name
                    else None
                )
                # For licenses, infer licensee/licensor by name match
                licensee_id = (
                    filer_company_id
                    if d.licensee_name == filer_company_name
                    else None
                )
                licensor_id = (
                    filer_company_id
                    if d.licensor_name == filer_company_name
                    else None
                )
                deals_row = build_deals_row(
                    extraction=d,
                    acquirer_id=acquirer_id,
                    target_id=target_id,
                    licensor_id=licensor_id,
                    licensee_id=licensee_id,
                    source_document_id=source_document_id,
                )
                deal_id = db.insert_deal(deals_row)
                if deal_id:
                    result.deals_emitted += 1
            else:
                result.duplicates_skipped += 1
    except Exception as exc:
        logger.warning("Item 1.01 processing failed: %s", exc)
        result.errors.append(f"deal_announced: {exc}")


def _process_item_2_02(
    *, filing_text, filer_company_id, filer_company_name,
    source_document_id, disclosed_date, db, extractor, result: ProcessResult,
) -> None:
    if extractor is None:
        return
    try:
        parse_result = parse_item_2_02(filing_text, extractor=extractor)
        if parse_result.financial_disclosure is not None:
            row = build_financial_disclosure_row(
                extraction=parse_result.financial_disclosure,
                company_id=filer_company_id,
                company_name=filer_company_name,
                source_document_id=source_document_id,
                disclosed_date=disclosed_date,
            )
            inserted = db.insert_event(row)
            if inserted:
                result.events_emitted += 1
            else:
                result.duplicates_skipped += 1
        for issuance in parse_result.guidance_issuances:
            row = build_guidance_change_row(
                issuance=issuance,
                company_id=filer_company_id,
                company_name=filer_company_name,
                source_document_id=source_document_id,
                disclosed_date=disclosed_date,
            )
            inserted = db.insert_event(row)
            if inserted:
                result.events_emitted += 1
            else:
                result.duplicates_skipped += 1
    except Exception as exc:
        logger.warning("Item 2.02 processing failed: %s", exc)
        result.errors.append(f"financial: {exc}")


def _process_item_8_01(
    *, filing_text, filer_company_id, filer_company_name,
    source_document_id, disclosed_date, db, extractor, result: ProcessResult,
) -> None:
    if extractor is None:
        return
    try:
        items = parse_item_8_01(filing_text, extractor=extractor)
        for c in items:
            # Drug entity resolution attempt
            drug_id: Optional[str] = None
            if c.drug_name:
                try:
                    drug_id = db.resolve_drug_id(c.drug_name)
                except Exception as exc:
                    logger.warning(
                        "drug resolution failed for %s: %s",
                        c.drug_name, exc,
                    )
            row = build_crl_event_row(
                extraction=c,
                company_id=filer_company_id,
                company_name=filer_company_name,
                drug_id=drug_id,
                source_document_id=source_document_id,
                disclosed_date=disclosed_date,
            )
            inserted = db.insert_event(row)
            if inserted:
                result.events_emitted += 1
            else:
                result.duplicates_skipped += 1
    except Exception as exc:
        logger.warning("Item 8.01 processing failed: %s", exc)
        result.errors.append(f"regulatory_crl: {exc}")
