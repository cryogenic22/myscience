"""D2: _store_event must stamp the primary_entity_* spine columns at ingest.

Root cause of the 28.9% NULL primary_entity_id share: the event writer set
drug_id but never the primary_entity_* columns, so drug-grounded events landed
uncited by the dossier. These tests pin that ingest now mirrors the resolved
drug (preferred) or company into primary_entity_id/type/name, matching the
established prod convention (primary_entity_id == drug_id::text for drugs).
"""
from __future__ import annotations

from datetime import datetime, timezone

from connectors.base import Provenance, RawRecord, RecordType, SourceType
from integration.embedder import EmbeddedRecord
from integration.entity_resolver import ResolvedLink, ResolvedRecord
from integration.knowledge_store import KnowledgeStore
from integration.normalizer import NormalizedRecord


class _FakeDB:
    def __init__(self):
        self.executed: list[tuple[str, list]] = []
        self._next_id = "evt-uuid-1"

    def fetch_one(self, sql, params=None):
        s = sql.lower()
        if "insert into market_events" in s:
            self.executed.append((sql, params or []))
            return {"id": self._next_id}
        return None

    def execute(self, sql, params=None):
        self.executed.append((sql, params or []))


def _event_record(*, drug_id=None, company_id=None, generic_name="semaglutide",
                  company_name="Novo Nordisk"):
    prov = Provenance(
        source_type=SourceType.FDA_SHORTAGES,
        api_endpoint="https://api.fda.gov/drug/enforcement.json",
        query_params={},
        retrieved_at=datetime(2026, 6, 5, tzinfo=timezone.utc),
        raw_response_hash="h",
    )
    data = {
        "event_type": "RECALL_CLASS_I",
        "description": "Class II Ongoing: CGMP Deviations",
        "event_date": "2026-06-01",
        "impact_score": 0.5,
        "generic_name": generic_name,
        "company_name": company_name,
    }
    raw = RawRecord(
        record_type=RecordType.EVENT,
        external_id="recall_999",
        source_name="FDA",
        provenance=prov,
        data=data,
        identifiers={},
    )
    norm = NormalizedRecord(raw=raw, canonical_data=data, identifiers={})
    links = {}
    if drug_id:
        links["generic_name"] = ResolvedLink(
            entity_type="drug", entity_id=drug_id, matched_via="fuzzy",
            confidence=0.9, matched_value=generic_name,
        )
    if company_id:
        links["company_name"] = ResolvedLink(
            entity_type="company", entity_id=company_id, matched_via="fuzzy",
            confidence=0.9, matched_value=company_name,
        )
    resolved = ResolvedRecord(normalized=norm, resolved_links=links)
    return EmbeddedRecord(resolved=resolved, embedding=None)


def _event_insert_params(db):
    ins = [e for e in db.executed if "insert into market_events" in e[0].lower()]
    assert len(ins) == 1
    return ins[0][1]


def test_drug_link_sets_primary_entity_to_drug():
    db = _FakeDB()
    store = KnowledgeStore(db)
    store._store_event(_event_record(drug_id="drug-1"), "run-1")
    p = _event_insert_params(db)
    # last three params: primary_entity_id, primary_entity_type, primary_entity_name
    assert p[-3] == "drug-1"          # primary_entity_id == drug_id
    assert p[-2] == "drug"
    assert p[-1] == "semaglutide"
    # drug_id is param[0]
    assert p[0] == "drug-1"


def test_company_link_grounds_when_no_drug():
    db = _FakeDB()
    store = KnowledgeStore(db)
    store._store_event(_event_record(drug_id=None, company_id="co-1"), "run-1")
    p = _event_insert_params(db)
    assert p[-3] == "co-1"
    assert p[-2] == "company"
    assert p[-1] == "Novo Nordisk"
    assert p[0] is None               # no drug_id


def test_drug_wins_over_company():
    db = _FakeDB()
    store = KnowledgeStore(db)
    store._store_event(_event_record(drug_id="drug-1", company_id="co-1"), "run-1")
    p = _event_insert_params(db)
    assert p[-3] == "drug-1"
    assert p[-2] == "drug"


def test_unresolved_event_leaves_primary_null_but_stores():
    db = _FakeDB()
    store = KnowledgeStore(db)
    new_id, was_insert = store._store_event(
        _event_record(drug_id=None, company_id=None), "run-1")
    assert was_insert
    p = _event_insert_params(db)
    assert p[-3] is None and p[-2] is None and p[-1] is None
