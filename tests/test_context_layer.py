"""A2a — tests for the Context Layer skeleton + FillState type invariants.

The keystone behaviour: a Section cannot construct as silently empty. The
dataclass enforces this in __post_init__ — there is no convention here, only
a type. See specs/SPEC_A2a_context_layer.md.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

import pytest

from services.context_layer import (
    ContextLayer,
    ContextContractError,
    FillState,
    Section,
    Entity360,
    EntityNotFound,
)

NOW = datetime(2026, 5, 30, tzinfo=timezone.utc)
FUTURE = datetime(2027, 1, 1, tzinfo=timezone.utc)


# ── FillState / Section invariants (no DB needed) ─────────────────

class TestSectionInvariants:
    def test_populated_section_requires_data(self):
        with pytest.raises(ContextContractError):
            Section(key="identity", fill=FillState.POPULATED, as_of=NOW, data=None)

    def test_unavailable_section_requires_reason(self):
        with pytest.raises(ContextContractError):
            Section(key="clinical", fill=FillState.UNAVAILABLE_NO_DATA,
                    as_of=NOW, data=None, reason="")

    def test_unavailable_section_with_reason_constructs(self):
        s = Section(key="clinical", fill=FillState.UNAVAILABLE_NO_DATA,
                    as_of=NOW, reason="no facts in window")
        assert s.reason
        assert s.data is None

    def test_populated_with_data_constructs(self):
        s = Section(key="identity", fill=FillState.POPULATED,
                    as_of=NOW, data={"name": "wegovy-demo"})
        assert s.data["name"] == "wegovy-demo"

    def test_error_state_requires_reason(self):
        with pytest.raises(ContextContractError):
            Section(key="x", fill=FillState.UNAVAILABLE_ERROR, as_of=NOW)
        # but with a reason it constructs
        s = Section(key="x", fill=FillState.UNAVAILABLE_ERROR, as_of=NOW,
                    reason="upstream timeout")
        assert s.reason == "upstream timeout"


# ── get_entity_360 ────────────────────────────────────────────────

class TestGetEntity360:
    def _layer(self, fact_rows=None):
        db = MagicMock()
        db.fetch_all.return_value = fact_rows or []
        return ContextLayer(db=db)

    def test_returns_entity_360_with_identity_section(self):
        cl = self._layer()
        e360 = cl.get_entity_360("drug:wegovy-demo")
        assert isinstance(e360, Entity360)
        assert "identity" in e360.sections
        assert e360.sections["identity"].fill in (
            FillState.POPULATED, FillState.UNAVAILABLE_NO_DATA
        )

    def test_as_of_propagates_to_facts_query(self):
        cl = self._layer()
        e360 = cl.get_entity_360("drug:wegovy-demo", as_of=FUTURE)
        assert e360.as_of == FUTURE
        # All sections share the same as_of
        for sec in e360.sections.values():
            assert sec.as_of == FUTURE

    def test_section_query_failure_becomes_unavailable_error_not_swallowed(self):
        # When a section builder raises, the section should be returned as
        # UNAVAILABLE_ERROR with the exception in reason — NEVER as [] or None.
        db = MagicMock()
        db.fetch_all.side_effect = RuntimeError("connection refused")
        cl = ContextLayer(db=db)
        e360 = cl.get_entity_360("drug:wegovy-demo")
        # At least one section should reflect the error
        error_sections = [
            s for s in e360.sections.values()
            if s.fill is FillState.UNAVAILABLE_ERROR
        ]
        assert len(error_sections) >= 1, "errors must surface as UNAVAILABLE_ERROR"
        for s in error_sections:
            assert s.reason  # never empty

    def test_projection_filters_sections(self):
        cl = self._layer()
        e360 = cl.get_entity_360("drug:wegovy-demo", projection=["identity"])
        assert set(e360.sections.keys()) == {"identity"}

    def test_malformed_entity_ref_raises_entity_not_found(self):
        cl = self._layer()
        with pytest.raises(EntityNotFound):
            cl.get_entity_360("not-a-valid-ref")


# ── query_facts (proxies facts_ledger) ─────────────────────────────

class TestQueryFacts:
    def test_returns_list(self):
        db = MagicMock()
        db.fetch_all.return_value = []
        cl = ContextLayer(db=db)
        facts = cl.query_facts({"subject_entity_type": "drug",
                                "subject_entity_id": "wegovy-demo"})
        assert isinstance(facts, list)

    def test_min_confidence_filter(self):
        # Two facts in store, one above, one below the floor
        rows = [
            {"id": "f1", "subject_entity_type": "drug", "subject_entity_id": "x",
             "predicate": "p", "confidence": 0.9, "object_value": {},
             "valid_from": None, "valid_to": None, "superseded_by": None,
             "kind": "point", "asserted_at": NOW, "source_doc_id": None},
            {"id": "f2", "subject_entity_type": "drug", "subject_entity_id": "x",
             "predicate": "p", "confidence": 0.5, "object_value": {},
             "valid_from": None, "valid_to": None, "superseded_by": None,
             "kind": "point", "asserted_at": NOW, "source_doc_id": None},
        ]
        db = MagicMock()
        db.fetch_all.return_value = rows
        cl = ContextLayer(db=db)
        facts = cl.query_facts({"subject_entity_type": "drug", "subject_entity_id": "x"},
                               min_confidence=0.7)
        ids = {f["id"] for f in facts}
        assert "f1" in ids
        assert "f2" not in ids


# ── stub ops are typed-clean (no crashing) ─────────────────────────

class TestStubOps:
    def test_traverse_returns_empty_subgraph_when_stubbed(self):
        cl = ContextLayer(db=MagicMock())
        sg = cl.traverse("drug:x", edge_types=["competes_with"])
        # Either implemented (returns SubGraph) or stubbed (returns empty
        # but typed — never None, never crash).
        assert sg is not None
        assert hasattr(sg, "nodes") or isinstance(sg, dict)

    def test_emit_event_returns_event_id(self):
        cl = ContextLayer(db=MagicMock())
        eid = cl.emit_event("test:event", {"k": "v"})
        assert eid  # non-empty string


# ── Provenance on returned facts ───────────────────────────────────

class TestProvenance:
    def test_query_facts_attaches_provenance(self):
        rows = [{
            "id": "f1", "subject_entity_type": "drug", "subject_entity_id": "x",
            "predicate": "p", "confidence": 0.9, "object_value": {},
            "valid_from": None, "valid_to": None, "superseded_by": None,
            "kind": "point", "asserted_at": NOW,
            "source_doc_id": "doc-123",
        }]
        db = MagicMock()
        db.fetch_all.return_value = rows
        cl = ContextLayer(db=db)
        facts = cl.query_facts({"subject_entity_type": "drug", "subject_entity_id": "x"})
        assert facts[0]["source_doc_id"] == "doc-123"
