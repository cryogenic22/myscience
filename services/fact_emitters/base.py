"""DR-0 — fact-emitter framework: entity rows → typed, evidence-bearing facts.

The facts ledger the dossier reads is a news-event monoculture (`market_event`
/ `wac_usd`) while thousands of clinical_trials / adverse_events / drug_labels
sit in entity tables and never become domain facts
(docs/state-of-build-and-data-richness.html, 2 Jun 2026). This is plumbing,
not sourcing: a thin layer that maps each entity row → one or more
``EmittedFact`` whose predicate ``route_predicate_to_domain()`` lands in the
right ZS dossier domain.

Reuses ``services.facts_ledger.assert_fact`` (append-only ledger) and, for
DR-5, writes a standalone ``evidence_record`` per newly-asserted fact and links
it via ``facts.source_doc_id`` (which has no FK, so the link is clean) —
turning evidence_records from a single row into one per grounded fact.

Each emitter is pure where it can be: ``row_to_facts(row)`` is DB-free and
unit-testable; only ``fetch_rows`` and the assert/evidence writes touch the DB.
Idempotency: every emitted fact stamps ``object_value.source_row_id`` (the
originating entity-row id) + ``object_value.emitter``; re-runs that find a
non-superseded fact with the same (subject, predicate, source_row_id) skip.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from services.evidence_ledger import hash_source_content
from services.facts_ledger import DEFAULT_FACT_CLASS, assert_fact

logger = logging.getLogger(__name__)

CREATED_BY = "fact_emitter"
_MAX_EVIDENCE_CHARS = 65536  # evidence_records.extracted_text CHECK ceiling


# ── D-Q1 (COORDINATION §8.2, Design A): fact_class by SOURCE ──────────────────
# A registry/regulatory record is authoritative ground truth = `reference`-grade,
# not the `corporate` default these emitters historically declared. resolve_fact_class
# UPGRADES the corporate default to `reference` for these sources only; any class set
# DELIBERATELY (`signal` FAERS, `inferred` derivations, genuine `corporate` news) is
# returned unchanged, so it never over-upgrades. Single source of truth for the
# source→class policy — also used by scripts/backfill_fact_class.py to reconcile
# existing rows. Classifying by SOURCE (not predicate) is what distinguishes a
# registry trial readout from a news mention of the same trial.
AUTHORITATIVE_SOURCES = frozenset({
    "clinical_trials_gov",   # ClinicalTrials.gov registry (trials, phase transitions)
    "fda_orange_book",       # FDA Orange Book / regulatory submissions
    "openfda_labels",        # openFDA structured product labels (SPL)
    "fda_shortages",         # FDA drug-shortage records — anticipatory (no corporate-emitter yet)
    "ema",                   # EMA regulatory (§8.2 "FDA/EMA") — anticipatory (no EMA facts yet)
    "fda_spl",               # drug_labels code-default fallback when source_api is NULL;
                             # canonical value is `openfda_labels` above — NOT a SourceType enum member.
})


def resolve_fact_class(source_id: Optional[str], declared_class: str) -> str:
    """Final stored fact_class for an emitted fact (D-Q1, §8.2 Design A).

    A fact that fell into the `corporate` default but originates from an
    authoritative registry/regulatory source is reference-grade ground truth, so
    it is upgraded to `reference`. A class the emitter set deliberately (`signal`,
    `inferred`, or `corporate` from a non-authoritative source) is returned
    unchanged — this only rescues the default catch-all, never over-upgrades."""
    if declared_class == DEFAULT_FACT_CLASS \
            and (source_id or "").strip().lower() in AUTHORITATIVE_SOURCES:
        return "reference"
    return declared_class


@dataclass
class EmittedFact:
    """A pure, DB-free description of a fact lifted from an entity row."""

    predicate: str
    subject_entity_type: str
    subject_entity_id: str
    object_value: dict
    source_row_id: str                       # idempotency key (entity row id)
    kind: str = "point"
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    confidence: float = 0.8
    fact_class: str = DEFAULT_FACT_CLASS
    evidence_text: Optional[str] = None      # DR-5: snippet to attest
    source_id: Optional[str] = None          # DR-5: source connector id
    source_url: Optional[str] = None


@dataclass
class EmitStats:
    emitter: str = ""
    scanned: int = 0
    asserted: int = 0
    skipped_existing: int = 0
    skipped_no_subject: int = 0
    evidence_written: int = 0

    def merge(self, other: "EmitStats") -> None:
        self.scanned += other.scanned
        self.asserted += other.asserted
        self.skipped_existing += other.skipped_existing
        self.skipped_no_subject += other.skipped_no_subject
        self.evidence_written += other.evidence_written


class FactEmitter:
    """Base class for a per-source lift. Subclasses set ``name`` and implement
    ``fetch_rows`` (DB) + ``row_to_facts`` (pure)."""

    name: str = "base"

    def fetch_rows(self, db, *, drug_id: Optional[str] = None,
                   limit: Optional[int] = None) -> list[dict]:
        raise NotImplementedError

    def row_to_facts(self, row: dict) -> list[EmittedFact]:
        raise NotImplementedError


def coerce_dt(v: Any) -> Optional[datetime]:
    """Coerce a date/datetime/ISO-string (entity tables use ``date`` columns)
    to a tz-aware datetime, or None."""
    if v is None:
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def clamp_confidence(v: Any, default: float = 0.8) -> float:
    """Clamp to [0,1]. Quality scores sometimes arrive on a 0–100 scale; a
    value >1 is rescaled by /100 before clamping."""
    try:
        c = float(v)
    except (TypeError, ValueError):
        return default
    if c > 1.0:
        c = c / 100.0
    return min(1.0, max(0.0, c))


_EXISTS_SQL = """
    SELECT id FROM facts
     WHERE subject_entity_type = %s
       AND subject_entity_id = %s
       AND predicate = %s
       AND object_value->>'source_row_id' = %s
       AND superseded_by IS NULL
     LIMIT 1
"""


def _fact_exists(db, fact: EmittedFact) -> bool:
    try:
        rows = db.fetch_all(
            _EXISTS_SQL,
            [fact.subject_entity_type, fact.subject_entity_id,
             fact.predicate, str(fact.source_row_id)],
        )
        return bool(rows)
    except Exception:
        logger.exception("fact existence check failed for %s", fact.source_row_id)
        return False


_EVIDENCE_EXISTS_SQL = """
    SELECT evidence_id FROM evidence_records
     WHERE source_content_hash = %s AND source_id = %s
     LIMIT 1
"""

_EVIDENCE_INSERT_SQL = """
    INSERT INTO evidence_records (
        source_id, source_url, source_content_hash, retrieved_at,
        extraction_method, extracted_text, confidence
    ) VALUES (%s, %s, %s, NOW(), %s::jsonb, %s, %s)
    RETURNING evidence_id
"""


def _write_evidence(db, fact: EmittedFact) -> Optional[str]:
    """DR-5: persist a standalone evidence_record for ``fact`` and return its
    id, or None if there is nothing to attest. Idempotent on
    (source_content_hash, source_id) — re-runs reuse the existing record."""
    text = (fact.evidence_text or "").strip()
    if not text:
        return None
    text = text[:_MAX_EVIDENCE_CHARS]
    source_id = (fact.source_id or fact.predicate or "fact_emitter")[:200]
    content_hash = hash_source_content(text)
    try:
        existing = db.fetch_one(_EVIDENCE_EXISTS_SQL, (content_hash, source_id))
        if existing and existing.get("evidence_id"):
            return str(existing["evidence_id"])
        row = db.fetch_one(
            _EVIDENCE_INSERT_SQL,
            (source_id, fact.source_url, content_hash,
             json.dumps({"method": "fact_emitter", "emitter": fact.predicate}),
             text, fact.confidence),
        )
        return str(row["evidence_id"]) if row and row.get("evidence_id") else None
    except Exception:
        logger.exception("evidence write failed for %s", fact.source_row_id)
        return None


def emit_one(db, emitter_name: str, fact: EmittedFact, *,
             write_evidence: bool = True) -> tuple[str, Optional[str]]:
    """Idempotently assert one emitted fact (and, when enabled, its evidence).
    Returns (status, fact_id). status ∈
    {asserted, skipped_existing, skipped_no_subject}."""
    if not fact.subject_entity_id or not fact.subject_entity_type:
        return ("skipped_no_subject", None)

    if _fact_exists(db, fact):
        return ("skipped_existing", None)

    object_value = dict(fact.object_value or {})
    object_value.setdefault("source_row_id", str(fact.source_row_id))
    object_value.setdefault("emitter", emitter_name)
    if fact.source_url and not object_value.get("source_url"):
        object_value["source_url"] = fact.source_url

    source_doc_id = _write_evidence(db, fact) if write_evidence else None

    fid = assert_fact(
        db,
        kind=fact.kind,
        predicate=fact.predicate,
        subject_entity_type=fact.subject_entity_type,
        subject_entity_id=fact.subject_entity_id,
        object_value=object_value,
        valid_from=fact.valid_from,
        valid_to=fact.valid_to,
        confidence=fact.confidence,
        source_doc_id=source_doc_id,
        created_by=CREATED_BY,
        # D-Q1 §8.2: the stored class is resolved by SOURCE — an authoritative
        # registry/regulatory fact is `reference`, not the `corporate` default.
        fact_class=resolve_fact_class(fact.source_id, fact.fact_class),
    )
    return ("asserted", fid)


def run_emitter(db, emitter: FactEmitter, *, drug_id: Optional[str] = None,
                limit: Optional[int] = None,
                write_evidence: bool = True) -> EmitStats:
    """Run one emitter over its rows. Idempotent — safe to re-run."""
    stats = EmitStats(emitter=emitter.name)
    for row in emitter.fetch_rows(db, drug_id=drug_id, limit=limit):
        for fact in emitter.row_to_facts(row) or []:
            stats.scanned += 1
            status, fid = emit_one(db, emitter.name, fact,
                                   write_evidence=write_evidence)
            if status == "asserted":
                stats.asserted += 1
                if write_evidence and fact.evidence_text:
                    stats.evidence_written += 1
            elif status == "skipped_existing":
                stats.skipped_existing += 1
            elif status == "skipped_no_subject":
                stats.skipped_no_subject += 1
    logger.info(
        "fact emitter %s: scanned=%d asserted=%d existing=%d no_subject=%d evidence=%d",
        emitter.name, stats.scanned, stats.asserted, stats.skipped_existing,
        stats.skipped_no_subject, stats.evidence_written,
    )
    return stats


def get_emitters() -> dict[str, FactEmitter]:
    """Registry of available emitters. Imported lazily to avoid import cycles."""
    from services.fact_emitters.adverse_events import AdverseEventEmitter
    from services.fact_emitters.clinical_trials import ClinicalTrialEmitter
    from services.fact_emitters.competition import CompetitionEmitter
    from services.fact_emitters.drug_labels import DrugLabelEmitter
    from services.fact_emitters.literature import LiteratureEmitter
    from services.fact_emitters.mechanisms import (
        BioactivityEmitter,
        MechanismEmitter,
    )
    from services.fact_emitters.phase_transitions import PhaseTransitionEmitter
    from services.fact_emitters.regulatory_milestones import RegulatoryMilestoneEmitter

    emitters: tuple[FactEmitter, ...] = (
        ClinicalTrialEmitter(),
        AdverseEventEmitter(),
        DrugLabelEmitter(),
        MechanismEmitter(),
        BioactivityEmitter(),
        LiteratureEmitter(),
        CompetitionEmitter(),
        PhaseTransitionEmitter(),
        RegulatoryMilestoneEmitter(),
    )
    return {e.name: e for e in emitters}


def run_all_emitters(db, *, drug_id: Optional[str] = None,
                     limit: Optional[int] = None,
                     write_evidence: bool = True) -> dict[str, EmitStats]:
    """Run every registered emitter; returns {name: EmitStats}."""
    return {
        name: run_emitter(db, em, drug_id=drug_id, limit=limit,
                          write_evidence=write_evidence)
        for name, em in get_emitters().items()
    }
