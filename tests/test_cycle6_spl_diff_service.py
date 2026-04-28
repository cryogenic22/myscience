"""Cycle 6 — SPL section-level diff service → label_change events (A4.2).

Compares the freshly-parsed SPL sections against the stored snapshot
of the previous revision and emits one market_event per modified
section.

Covered units:

  1. services.spl_diff_service.compute_section_changes()
     pure function (prev_sections, fresh_sections) → list[Change]

  2. services.event_emitters.label_change.build_event_row()
     dict shaped for INSERT INTO market_events

  3. services.spl_diff_service.process_spl_revision()
     orchestrator that reads snapshot, computes changes, emits events,
     writes new snapshot. Uses an injected adapter (load_snapshot,
     save_snapshot, insert_event) so the test runs DB-free.

A label_change event is tier-1 (FDA-published) → trust_score 0.95.
Boxed Warning / Contraindications / Warnings additions are
high-impact; Indications additions are medium; everything else is
low.
"""

from __future__ import annotations

from datetime import date
from dataclasses import dataclass
from typing import Any, Optional

import pytest

from services.spl_section_parser import SplSection


# ────────────────────────────────────────────────────────────────────
# Helper builders
# ────────────────────────────────────────────────────────────────────


def _section(loinc: str, text: str, display: str = "") -> SplSection:
    return SplSection(
        loinc_code=loinc,
        display_name=display or _DEFAULT_DISPLAY.get(loinc, loinc),
        title=display or loinc,
        text=text,
    )


_DEFAULT_DISPLAY = {
    "34066-1": "BOXED WARNING",
    "34067-9": "INDICATIONS AND USAGE",
    "34068-7": "DOSAGE AND ADMINISTRATION",
    "34070-3": "CONTRAINDICATIONS",
    "43685-7": "WARNINGS AND PRECAUTIONS",
    "34071-1": "ADVERSE REACTIONS",
    "34073-7": "DRUG INTERACTIONS",
}


# ────────────────────────────────────────────────────────────────────
# Cat 1 — compute_section_changes (pure)
# ────────────────────────────────────────────────────────────────────


class TestComputeSectionChanges:

    def test_module_imports(self):
        from services.spl_diff_service import compute_section_changes  # noqa: F401

    def test_no_changes_when_identical(self):
        from services.spl_diff_service import compute_section_changes
        prev = [_section("34066-1", "warning text")]
        fresh = [_section("34066-1", "warning text")]
        assert compute_section_changes(prev, fresh) == []

    def test_added_section(self):
        from services.spl_diff_service import compute_section_changes
        prev: list[SplSection] = []
        fresh = [_section("34066-1", "new boxed warning")]
        changes = compute_section_changes(prev, fresh)
        assert len(changes) == 1
        c = changes[0]
        assert c.kind == "added"
        assert c.loinc_code == "34066-1"
        assert c.new_text == "new boxed warning"
        assert c.prev_text is None

    def test_modified_section(self):
        from services.spl_diff_service import compute_section_changes
        prev = [_section("34071-1", "Most common: nausea (5%)")]
        fresh = [_section("34071-1", "Most common: nausea (12%), fatigue (8%)")]
        changes = compute_section_changes(prev, fresh)
        assert len(changes) == 1
        c = changes[0]
        assert c.kind == "modified"
        assert c.loinc_code == "34071-1"
        assert c.prev_text == "Most common: nausea (5%)"
        assert "fatigue" in c.new_text

    def test_removed_section(self):
        from services.spl_diff_service import compute_section_changes
        prev = [_section("34066-1", "old boxed warning")]
        fresh: list[SplSection] = []
        changes = compute_section_changes(prev, fresh)
        assert len(changes) == 1
        c = changes[0]
        assert c.kind == "removed"
        assert c.loinc_code == "34066-1"
        assert c.new_text is None

    def test_multiple_changes_in_order(self):
        from services.spl_diff_service import compute_section_changes
        prev = [
            _section("34067-9", "indicated for X"),
            _section("34071-1", "nausea common"),
        ]
        fresh = [
            _section("34066-1", "new boxed warning"),       # added
            _section("34067-9", "indicated for X and Y"),   # modified
            # 34071-1 removed
        ]
        changes = compute_section_changes(prev, fresh)
        kinds = sorted(c.kind for c in changes)
        assert kinds == ["added", "modified", "removed"]


# ────────────────────────────────────────────────────────────────────
# Cat 2 — Whitespace normalisation (don't emit on cosmetic only)
# ────────────────────────────────────────────────────────────────────


class TestWhitespaceNormalisation:

    def test_trailing_whitespace_does_not_trigger(self):
        from services.spl_diff_service import compute_section_changes
        prev = [_section("34071-1", "ADRs:\n nausea ")]
        fresh = [_section("34071-1", "ADRs: nausea")]
        # whitespace-only diff = no change emitted
        assert compute_section_changes(prev, fresh) == []

    def test_internal_whitespace_collapse_does_not_trigger(self):
        from services.spl_diff_service import compute_section_changes
        prev = [_section("34071-1", "headache  fatigue")]
        fresh = [_section("34071-1", "headache fatigue")]
        assert compute_section_changes(prev, fresh) == []


# ────────────────────────────────────────────────────────────────────
# Cat 3 — Event emitter
# ────────────────────────────────────────────────────────────────────


class TestEventEmitter:

    def test_module_imports(self):
        from services.event_emitters.label_change import build_event_row  # noqa: F401

    def test_added_boxed_warning_high_impact(self):
        from services.event_emitters.label_change import build_event_row
        from services.spl_diff_service import SectionChange
        change = SectionChange(
            loinc_code="34066-1",
            display_name="BOXED WARNING",
            kind="added",
            prev_text=None,
            new_text="WARNING: SERIOUS RISK",
        )
        row = build_event_row(
            change=change,
            drug_id="11111111-1111-1111-1111-111111111111",
            drug_name="Example Drug",
            company_id="22222222-2222-2222-2222-222222222222",
            setid="abc-123",
            source_document_id="33333333-3333-3333-3333-333333333333",
            disclosed_date=date(2026, 4, 15),
        )
        assert row["event_type"] == "label_change"
        assert row["primary_entity_type"] == "drug"
        assert row["primary_entity_id"] == \
               "11111111-1111-1111-1111-111111111111"
        assert row["impact_hint"] == "high"
        assert row["source_tier"] == "tier_1"  # FDA-published
        assert row["trust_score"] >= 0.9

    def test_modified_indications_medium_impact(self):
        from services.event_emitters.label_change import build_event_row
        from services.spl_diff_service import SectionChange
        change = SectionChange(
            loinc_code="34067-9",
            display_name="INDICATIONS AND USAGE",
            kind="modified",
            prev_text="indicated for X",
            new_text="indicated for X and Y",
        )
        row = build_event_row(
            change=change, drug_id="d", drug_name="Drug",
            company_id="c", setid="s",
            source_document_id="src", disclosed_date=date(2026, 1, 1),
        )
        assert row["impact_hint"] == "medium"

    def test_modified_other_section_low_impact(self):
        from services.event_emitters.label_change import build_event_row
        from services.spl_diff_service import SectionChange
        change = SectionChange(
            loinc_code="34073-7",  # DRUG INTERACTIONS
            display_name="DRUG INTERACTIONS",
            kind="modified",
            prev_text="A",
            new_text="A and B",
        )
        row = build_event_row(
            change=change, drug_id="d", drug_name="Drug",
            company_id="c", setid="s",
            source_document_id="src", disclosed_date=date(2026, 1, 1),
        )
        assert row["impact_hint"] == "low"

    def test_event_hash_deterministic(self):
        from services.event_emitters.label_change import build_event_row
        from services.spl_diff_service import SectionChange
        change = SectionChange(
            loinc_code="34066-1", display_name="BOXED WARNING",
            kind="added", prev_text=None, new_text="text",
        )
        kwargs = dict(
            change=change, drug_id="d", drug_name="Drug",
            company_id="c", setid="s",
            source_document_id="src", disclosed_date=date(2026, 1, 1),
        )
        r1 = build_event_row(**kwargs)
        r2 = build_event_row(**kwargs)
        assert r1["event_hash"] == r2["event_hash"]
        assert len(r1["event_hash"]) == 64

    def test_payload_includes_diff_text(self):
        from services.event_emitters.label_change import build_event_row
        from services.spl_diff_service import SectionChange
        change = SectionChange(
            loinc_code="34071-1", display_name="ADVERSE REACTIONS",
            kind="modified", prev_text="nausea",
            new_text="nausea, fatigue",
        )
        row = build_event_row(
            change=change, drug_id="d", drug_name="Drug",
            company_id="c", setid="s",
            source_document_id="src", disclosed_date=date(2026, 1, 1),
        )
        payload = row["payload"]
        assert payload["loinc_code"] == "34071-1"
        assert payload["change_kind"] == "modified"
        assert payload["prev_text"] == "nausea"
        assert payload["new_text"] == "nausea, fatigue"


# ────────────────────────────────────────────────────────────────────
# Cat 4 — Orchestrator (process_spl_revision)
# ────────────────────────────────────────────────────────────────────


class FakeSPLAdapter:
    """Stand-in for the persistence layer used by the orchestrator."""

    def __init__(
        self,
        snapshots: Optional[dict[str, list[SplSection]]] = None,
        drug_id: Optional[str] = "drug-uuid",
        company_id: Optional[str] = "company-uuid",
    ):
        self._snapshots = snapshots or {}
        self._drug_id = drug_id
        self._company_id = company_id
        self.events_inserted: list[dict] = []
        self.snapshots_saved: list[tuple[str, list[SplSection]]] = []

    def load_snapshot(self, *, setid: str) -> list[SplSection]:
        return list(self._snapshots.get(setid, []))

    def save_snapshot(self, *, setid: str,
                       sections: list[SplSection]) -> None:
        self._snapshots[setid] = list(sections)
        self.snapshots_saved.append((setid, list(sections)))

    def resolve_drug_for_setid(self, *, setid: str) -> Optional[str]:
        return self._drug_id

    def resolve_company_for_drug(self, *, drug_id: str) -> Optional[str]:
        return self._company_id

    def insert_event(self, *, row: dict) -> bool:
        self.events_inserted.append(row)
        return True


class TestOrchestrator:

    def test_module_imports(self):
        from services.spl_diff_service import process_spl_revision  # noqa: F401

    def test_first_observation_writes_snapshot_no_events(self):
        from services.spl_diff_service import process_spl_revision
        adapter = FakeSPLAdapter()
        fresh = [_section("34067-9", "indicated for X")]
        result = process_spl_revision(
            setid="abc",
            fresh_sections=fresh,
            adapter=adapter,
            disclosed_date=date(2026, 4, 15),
            source_document_id="src-1",
        )
        assert result.events_emitted == 0
        assert result.snapshot_initialised is True
        assert len(adapter.snapshots_saved) == 1

    def test_real_change_emits_event_and_updates_snapshot(self):
        from services.spl_diff_service import process_spl_revision
        adapter = FakeSPLAdapter(
            snapshots={"abc": [_section("34067-9", "indicated for X")]},
        )
        fresh = [_section("34067-9", "indicated for X and Y")]
        result = process_spl_revision(
            setid="abc",
            fresh_sections=fresh,
            adapter=adapter,
            disclosed_date=date(2026, 4, 15),
            source_document_id="src-2",
        )
        assert result.events_emitted == 1
        assert len(adapter.events_inserted) == 1
        assert adapter.events_inserted[0]["event_type"] == "label_change"
        assert len(adapter.snapshots_saved) == 1

    def test_no_change_no_event_no_snapshot_write(self):
        from services.spl_diff_service import process_spl_revision
        adapter = FakeSPLAdapter(
            snapshots={"abc": [_section("34067-9", "indicated for X")]},
        )
        fresh = [_section("34067-9", "indicated for X")]
        result = process_spl_revision(
            setid="abc",
            fresh_sections=fresh,
            adapter=adapter,
            disclosed_date=date(2026, 4, 15),
            source_document_id="src-3",
        )
        assert result.events_emitted == 0
        # Snapshot stays untouched (no rewrite needed when no change)
        assert len(adapter.snapshots_saved) == 0

    def test_unresolved_drug_skips(self):
        from services.spl_diff_service import process_spl_revision
        adapter = FakeSPLAdapter(drug_id=None,
                                 snapshots={"abc": [_section("34067-9", "x")]})
        fresh = [_section("34067-9", "y")]
        result = process_spl_revision(
            setid="abc",
            fresh_sections=fresh,
            adapter=adapter,
            disclosed_date=date(2026, 4, 15),
            source_document_id="src-4",
        )
        assert result.events_emitted == 0
        assert result.skipped_reason == "drug_not_resolved"
