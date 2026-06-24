"""Data-quality / conservation: a name-less ontology term must FAIL CLOSED as a
recorded skip, not crash into the dead-letter queue.

Root cause of the #1 DLQ entry (3,121 'pending' records, still growing): the
open_targets connector emits target-disease association records that carry no
single ontology-term name, so `_store_ontology_term` ran
``INSERT INTO therapeutic_areas (name, ...) VALUES (NULL, ...)`` → a NOT NULL
violation → the whole record silently crash-lost to `failed_records`.

The fix: `_store_ontology_term` raises `RecordSkipped` (a recorded, counted skip)
when the name is blank; the pipeline counts it as `records_skipped` instead of
routing to `_dlq_insert`. Conservation: fail closed, record the drop, no crash.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from connectors.base import Provenance, RawRecord, RecordType, SourceType
from integration.embedder import EmbeddedRecord
from integration.entity_resolver import ResolvedRecord
from integration.knowledge_store import KnowledgeStore, RecordSkipped
from integration.normalizer import NormalizedRecord


class _FakeDB:
    def __init__(self, existing_row=None):
        self.executed: list[tuple[str, list]] = []
        self._existing = existing_row  # SELECT result (None => INSERT path)
        self._next_id = "ta-uuid-1"

    def fetch_one(self, sql, params=None):
        self.executed.append((sql, params or []))
        s = sql.lower()
        if "select id from" in s:
            return self._existing
        if "insert into" in s:
            return {"id": self._next_id}
        return None

    def fetch_all(self, sql, params=None):
        return []

    def execute(self, sql, params=None):
        self.executed.append((sql, params or []))


def _ontology_record(*, canonical_data: dict, source=SourceType.OPEN_TARGETS) -> EmbeddedRecord:
    prov = Provenance(
        source_type=source,
        api_endpoint="https://api.platform.opentargets.org",
        query_params={},
        retrieved_at=datetime(2026, 6, 24, tzinfo=timezone.utc),
        raw_response_hash="h",
    )
    raw = RawRecord(
        record_type=RecordType.ONTOLOGY_TERM,
        external_id="ot_drug_target_1",
        source_name="Open Targets Platform",
        provenance=prov,
        data=canonical_data,
        identifiers={},
    )
    norm = NormalizedRecord(raw=raw, canonical_data=canonical_data, identifiers={})
    resolved = ResolvedRecord(normalized=norm, resolved_links={})
    return EmbeddedRecord(resolved=resolved, embedding=None)


def _inserts(db):
    return [e for e in db.executed if "insert into" in e[0].lower()]


# ── store-level: the guard ───────────────────────────────────────────────────

def test_nameless_open_targets_term_is_skipped_not_inserted():
    # The exact prod shape: open_targets canonical_data carries target/disease
    # association fields but NO 'name'.
    db = _FakeDB()
    store = KnowledgeStore(db)
    rec = _ontology_record(canonical_data={
        "target_symbol": "GLP1R", "target_name": "Glucagon-like peptide 1 receptor",
        "disease_associations": [{"disease_id": "EFO_0001360", "disease_name": "type 2 diabetes"}],
    })
    with pytest.raises(RecordSkipped):
        store._store_ontology_term(rec, "run-1")
    # No NULL-name row ever reached the database.
    assert _inserts(db) == []


def test_blank_whitespace_name_is_also_skipped():
    db = _FakeDB()
    store = KnowledgeStore(db)
    rec = _ontology_record(canonical_data={"name": "   ", "mesh_id": "D000"})
    with pytest.raises(RecordSkipped):
        store._store_ontology_term(rec, "run-1")
    assert _inserts(db) == []


def test_named_term_still_inserts_with_its_name():
    # Regression: a legitimate named MeSH term (the happy path) is unaffected.
    db = _FakeDB(existing_row=None)
    store = KnowledgeStore(db)
    rec = _ontology_record(
        canonical_data={"name": "Type 2 Diabetes", "mesh_id": "D003924",
                        "term_type": "therapeutic_area"},
        source=SourceType.MESH_ONTOLOGY,
    )
    stored_id, was_insert = store._store_ontology_term(rec, "run-1")
    assert was_insert is True
    ins = _inserts(db)
    assert len(ins) == 1
    assert ins[0][1][0] == "Type 2 Diabetes"  # name is the first INSERT param


# ── pipeline-level: a skip is counted, NOT dead-lettered ─────────────────────

def _pipeline_with_skipping_store():
    from integration.pipeline import IntegrationPipeline

    p = IntegrationPipeline.__new__(IntegrationPipeline)
    p.db = MagicMock()
    p.normalizer = MagicMock()
    p.normalizer.normalize.return_value = MagicMock(canonical_data={})
    p.resolver = MagicMock()
    p.resolver.resolve.return_value = SimpleNamespace(resolved_links={})
    p.embedder = MagicMock()
    p.embedder.embed.return_value = MagicMock()
    p.store = MagicMock()
    p.store.store.side_effect = RecordSkipped("ontology term has no name")
    p.linker = MagicMock()
    p._record_type_to_entity = {"ontology_term": "therapeutic_area"}
    hooks = MagicMock()
    hooks.fire.return_value = []
    hooks.has_block.return_value = False
    p.hooks = hooks
    p._dlq_insert = MagicMock()
    return p


def test_pipeline_counts_skip_and_does_not_dead_letter():
    p = _pipeline_with_skipping_store()
    result = SimpleNamespace(
        records_skipped=0, records_unchanged=0, records_inserted=0,
        records_updated=0, records_failed=0, links_created=0, errors=[],
    )
    rec = _ontology_record(canonical_data={}).resolved.normalized.raw

    # Must NOT raise (the skip is handled, not propagated to the DLQ path).
    p._process_record(rec, "run-1", result)

    assert result.records_skipped == 1
    assert result.records_failed == 0
    p._dlq_insert.assert_not_called()
