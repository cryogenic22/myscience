"""SPL section-level diff service.

SPEC-016 §7 swimlane A4.2 (Cycle 6).

Compares the freshly-parsed sections of an SPL revision against
the stored snapshot of the previous revision. For each LOINC-coded
section that materially changed, emits one `label_change`
market_event and updates the snapshot.

Architecture
  - compute_section_changes(prev, fresh) is pure
  - process_spl_revision(setid, fresh, adapter, ...) is the
    orchestrator. It depends on an SPLAdapter Protocol so tests
    can inject a fake without touching the DB.

The Postgres-backed adapter lives separately; this module is
pure logic + the orchestrator.

Idempotency: comparison normalises whitespace before computing
hashes so cosmetic-only revisions don't trigger label_change events.
The event emitter further dedups via event_hash on the DB side.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal, Optional, Protocol

from services.event_emitters.label_change import build_event_row
from services.spl_section_parser import SplSection

logger = logging.getLogger(__name__)


ChangeKind = Literal["added", "modified", "removed"]


# ────────────────────────────────────────────────────────────────────
# SectionChange — one diff record
# ────────────────────────────────────────────────────────────────────


@dataclass
class SectionChange:
    loinc_code: str
    display_name: str
    kind: ChangeKind
    prev_text: Optional[str]
    new_text: Optional[str]


@dataclass
class DiffResult:
    setid: str = ""
    events_emitted: int = 0
    snapshot_initialised: bool = False
    skipped_reason: Optional[str] = None


# ────────────────────────────────────────────────────────────────────
# SPLAdapter Protocol — persistence boundary
# ────────────────────────────────────────────────────────────────────


class SPLAdapter(Protocol):
    """Persistence layer the orchestrator depends on."""

    def load_snapshot(self, *, setid: str) -> list[SplSection]: ...

    def save_snapshot(
        self, *, setid: str, sections: list[SplSection],
    ) -> None: ...

    def resolve_drug_for_setid(self, *, setid: str) -> Optional[str]: ...

    def resolve_company_for_drug(
        self, *, drug_id: str,
    ) -> Optional[str]: ...

    def insert_event(self, *, row: dict) -> bool: ...


# ────────────────────────────────────────────────────────────────────
# Whitespace normaliser
# ────────────────────────────────────────────────────────────────────


_WS_RE = re.compile(r"\s+")


def _normalise(text: Optional[str]) -> str:
    """Collapse runs of whitespace to a single space, strip ends.

    Cosmetic-only revisions (added newlines, trailing whitespace,
    column-wrap differences) won't trigger label_change events.
    Real edits — added/removed words, % numbers — will.
    """
    if not text:
        return ""
    return _WS_RE.sub(" ", text).strip()


# ────────────────────────────────────────────────────────────────────
# Pure diff
# ────────────────────────────────────────────────────────────────────


def compute_section_changes(
    prev: list[SplSection],
    fresh: list[SplSection],
) -> list[SectionChange]:
    """Compute the section-level diff between two SPL revisions.

    Comparison is whitespace-normalised. Sections are keyed by
    loinc_code. Returns one SectionChange per added / modified /
    removed section.
    """
    prev_by_code = {s.loinc_code: s for s in prev}
    fresh_by_code = {s.loinc_code: s for s in fresh}

    changes: list[SectionChange] = []

    # Added or modified
    for code, fresh_sec in fresh_by_code.items():
        prev_sec = prev_by_code.get(code)
        if prev_sec is None:
            changes.append(SectionChange(
                loinc_code=code,
                display_name=fresh_sec.display_name,
                kind="added",
                prev_text=None,
                new_text=fresh_sec.text,
            ))
        else:
            if _normalise(prev_sec.text) != _normalise(fresh_sec.text):
                changes.append(SectionChange(
                    loinc_code=code,
                    display_name=fresh_sec.display_name,
                    kind="modified",
                    prev_text=prev_sec.text,
                    new_text=fresh_sec.text,
                ))

    # Removed
    for code, prev_sec in prev_by_code.items():
        if code not in fresh_by_code:
            changes.append(SectionChange(
                loinc_code=code,
                display_name=prev_sec.display_name,
                kind="removed",
                prev_text=prev_sec.text,
                new_text=None,
            ))

    return changes


# ────────────────────────────────────────────────────────────────────
# Orchestrator
# ────────────────────────────────────────────────────────────────────


def process_spl_revision(
    *,
    setid: str,
    fresh_sections: list[SplSection],
    adapter: SPLAdapter,
    disclosed_date: date,
    source_document_id: str,
) -> DiffResult:
    """Run one SPL revision through the diff pipeline.

    Behaviour:
      - First-ever observation (empty snapshot) → write snapshot,
        emit no events. Initial labels become baseline.
      - Real change(s) → emit one label_change per change, write
        new snapshot.
      - No change → no events, snapshot left untouched.
      - Drug not resolvable → skip with reason="drug_not_resolved".
    """
    prev = adapter.load_snapshot(setid=setid)

    if not prev:
        adapter.save_snapshot(setid=setid, sections=fresh_sections)
        return DiffResult(setid=setid, snapshot_initialised=True)

    changes = compute_section_changes(prev, fresh_sections)
    if not changes:
        return DiffResult(setid=setid, events_emitted=0)

    drug_id = adapter.resolve_drug_for_setid(setid=setid)
    if not drug_id:
        return DiffResult(
            setid=setid,
            events_emitted=0,
            skipped_reason="drug_not_resolved",
        )

    company_id = adapter.resolve_company_for_drug(drug_id=drug_id) or ""
    drug_name = _drug_name_from_sections(fresh_sections)

    emitted = 0
    for change in changes:
        row = build_event_row(
            change=change,
            drug_id=drug_id,
            drug_name=drug_name,
            company_id=company_id,
            setid=setid,
            source_document_id=source_document_id,
            disclosed_date=disclosed_date,
        )
        if adapter.insert_event(row=row):
            emitted += 1

    adapter.save_snapshot(setid=setid, sections=fresh_sections)
    return DiffResult(setid=setid, events_emitted=emitted)


# ────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────


def _drug_name_from_sections(sections: list[SplSection]) -> str:
    """Best-effort drug name from the parsed sections.

    SPL stores the brand name in the document <title> not in any
    section, so the orchestrator's caller usually passes it in.
    For now we fall back to the first section's display_name when
    nothing better is available.
    """
    return ""
