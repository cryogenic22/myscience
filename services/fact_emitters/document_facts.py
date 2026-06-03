"""DR-9 Phase 2 — decks/PDFs → structured facts.

Phase 1 (services/document_extractor.py) turned an uploaded deck/PDF into text +
tables and fed the chunk→NER→embed→entity-link pipeline. Phase 2 closes the
loop to the *facts ledger*: it runs the existing LLM structured-extraction layer
(services/extraction_llm.extract_structured) over the extracted text and emits
typed, evidence-bearing facts — so a conference readout deck (v8 source class 5)
becomes a ``trial_result`` fact in the dossier's clinical_profile domain, the
same shape DR-1/6/7 produce.

Reuses, does not duplicate:
  - ``TrialReadoutExtraction`` schema (services/extraction/trial_readout.py)
  - ``extract_structured`` + ``StructuredCall`` (services/extraction_llm.py)
  - ``EmittedFact`` / ``emit_one`` (services/fact_emitters/base.py)
  - ``resolve_asset_to_subject`` (services/dossier_kb.py) for drug → subject

The LLM call is injected (``StructuredCall``) so this is unit-testable with a
fake callable and provider-agnostic in prod. A company deck is self-reported, so
facts are ``corporate``-class at moderate confidence; the corroboration loop can
later upgrade them when CT.gov / a journal confirms.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Callable, Optional

from services.extraction.trial_readout import TrialReadoutExtraction
from services.extraction_llm import StructuredCall, extract_structured
from services.fact_emitters.base import EmittedFact, EmitStats, emit_one

logger = logging.getLogger(__name__)

CREATED_BY = "document_facts"

_SYSTEM_PROMPT = (
    "You extract a single clinical-trial readout from the text of a pharma "
    "conference slide deck or press release. Only extract what is explicitly "
    "stated — never invent numbers, dates, or endpoints. If the text is not a "
    "trial readout (e.g. a financial or corporate slide), return no structured "
    "output. Dates must be the announcement/readout date as stated."
)

# A resolver maps a drug name -> (entity_type, entity_id) or None. Defaults to
# the dossier resolver so facts land on the same canonical rows the dossier reads.
DrugResolver = Callable[[str], Optional[tuple[str, str]]]


def _default_resolver(db) -> DrugResolver:
    from services.dossier_kb import resolve_asset_to_subject

    def _resolve(name: str) -> Optional[tuple[str, str]]:
        try:
            return resolve_asset_to_subject(db, name)
        except Exception:
            logger.debug("drug resolve failed for %r", name)
            return None

    return _resolve


def _source_row_id(drug_id: str, readout: TrialReadoutExtraction) -> str:
    """Deterministic idempotency key so re-uploading the same deck doesn't
    duplicate: (drug, trial id, readout date)."""
    raw = f"{drug_id}|{readout.trial_identifier}|{readout.readout_date.isoformat()}"
    return "doc-" + hashlib.sha1(raw.encode()).hexdigest()[:16]


def build_readout_fact(
    readout: TrialReadoutExtraction,
    *,
    subject_entity_id: str,
    subject_entity_type: str = "drug",
    source_url: Optional[str] = None,
    source_id: str = "user_document",
) -> EmittedFact:
    """Map a validated TrialReadoutExtraction → one EmittedFact (pure)."""
    bits = [readout.phase] if readout.phase and readout.phase != "N/A" else []
    bits.append("primary endpoint met" if readout.primary_endpoint_met
                else "primary endpoint not met")
    if readout.indication:
        bits.append(f"in {readout.indication}")
    claim = f"{', '.join(bits)} ({readout.trial_identifier})"
    object_value = {
        "description": claim,
        "trial_identifier": readout.trial_identifier,
        "phase": readout.phase,
        "indication": readout.indication,
        "primary_endpoint_met": readout.primary_endpoint_met,
        "sample_size": readout.sample_size,
        "drug_name": readout.drug_name,
        "sponsor": readout.sponsor_name,
        "outcomes": [o.model_dump(exclude_none=True)
                     for o in readout.efficacy_outcomes],
        "source_url": source_url,
    }
    evidence = readout.headline_summary
    if readout.safety_summary:
        evidence = f"{evidence}\n\nSafety: {readout.safety_summary}"
    return EmittedFact(
        predicate="trial_result",                 # routes to clinical_profile
        subject_entity_type=subject_entity_type,
        subject_entity_id=subject_entity_id,
        object_value=object_value,
        source_row_id=_source_row_id(subject_entity_id, readout),
        kind="point",
        valid_from=None,  # set by caller from readout_date if desired
        confidence=0.7,                           # company self-reported deck
        fact_class="corporate",
        evidence_text=evidence,
        source_id=source_id,
        source_url=source_url,
    )


def extract_document_facts(
    text: str,
    *,
    structured_call: StructuredCall,
    resolver: DrugResolver,
    source_url: Optional[str] = None,
) -> list[EmittedFact]:
    """Run LLM extraction over deck/PDF text → list[EmittedFact] (no DB writes).

    Returns [] when the text isn't a trial readout, the LLM returns nothing,
    or the drug can't be resolved to a subject (never raises)."""
    if not (text or "").strip():
        return []
    try:
        readout = extract_structured(
            text,
            system_prompt=_SYSTEM_PROMPT,
            schema_class=TrialReadoutExtraction,
            structured_call=structured_call,
        )
    except Exception:
        logger.exception("document fact extraction failed")
        return []
    if readout is None:
        return []

    resolved = resolver(readout.drug_name)
    if not resolved:
        logger.info("document readout for %r — drug unresolved, skipping",
                    readout.drug_name)
        return []
    entity_type, entity_id = resolved
    fact = build_readout_fact(
        readout,
        subject_entity_id=str(entity_id),
        subject_entity_type=str(entity_type),
        source_url=source_url,
    )
    fact.valid_from = None  # readout_date is a date; coerce_dt handles it if set
    return [fact]


def emit_document_facts(
    db,
    text: str,
    *,
    structured_call: StructuredCall,
    resolver: Optional[DrugResolver] = None,
    source_url: Optional[str] = None,
    write_evidence: bool = True,
) -> EmitStats:
    """Extract + idempotently persist facts from one document. Reuses emit_one
    (dedup on source_row_id, DR-5 evidence)."""
    stats = EmitStats(emitter=CREATED_BY)
    resolver = resolver or _default_resolver(db)
    facts = extract_document_facts(
        text, structured_call=structured_call, resolver=resolver,
        source_url=source_url,
    )
    for fact in facts:
        stats.scanned += 1
        status, _ = emit_one(db, CREATED_BY, fact, write_evidence=write_evidence)
        if status == "asserted":
            stats.asserted += 1
            if write_evidence and fact.evidence_text:
                stats.evidence_written += 1
        elif status == "skipped_existing":
            stats.skipped_existing += 1
        elif status == "skipped_no_subject":
            stats.skipped_no_subject += 1
    return stats
