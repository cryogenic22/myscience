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
from services.entity_linker import LinkResult


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

    def fetch_all(self, sql, params=None):
        return []

    def execute(self, sql, params=None):
        self.executed.append((sql, params or []))


class _StubLinker:
    """Returns a fixed LinkResult when `needle` is in the text; counts calls so
    a test can assert the headline linker is NOT consulted on structured hits."""
    def __init__(self, needle, result):
        self.needle = needle
        self.result = result
        self.calls = 0

    def link(self, text):
        self.calls += 1
        return self.result if text and self.needle in text.lower() else None


def _event_record(*, drug_id=None, company_id=None, generic_name="semaglutide",
                  company_name="Novo Nordisk",
                  description="Class II Ongoing: CGMP Deviations"):
    prov = Provenance(
        source_type=SourceType.FDA_SHORTAGES,
        api_endpoint="https://api.fda.gov/drug/enforcement.json",
        query_params={},
        retrieved_at=datetime(2026, 6, 5, tzinfo=timezone.utc),
        raw_response_hash="h",
    )
    data = {
        "event_type": "RECALL_CLASS_I",
        "description": description,
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


# ── headline entity-linkage fallback (news events with no structured link) ──

def test_unresolved_event_links_known_entity_via_description():
    # A news event the resolver couldn't structure-link, but whose headline
    # names a known company, now grounds via the gazetteer (precision-safe).
    db = _FakeDB()
    store = KnowledgeStore(db)
    store._event_linker = _StubLinker(
        "astrazeneca", LinkResult("company", "co-az", "AstraZeneca", 0.9, "astrazeneca"))
    store._store_event(
        _event_record(drug_id=None, company_id=None,
                      description="AstraZeneca stock falls after FDA panel vote"), "run-1")
    p = _event_insert_params(db)
    assert p[-3] == "co-az"
    assert p[-2] == "company"
    assert p[-1] == "AstraZeneca"


def test_headline_link_respects_precision_floor():
    # A weak (auto-alias) headline match must NOT ground the event — stays NULL.
    db = _FakeDB()
    store = KnowledgeStore(db)
    store._event_linker = _StubLinker(
        "summit", LinkResult("company", "co-summit", "Summit", 0.72, "summit"))
    store._store_event(
        _event_record(drug_id=None, company_id=None,
                      description="reached the summit of approval"), "run-1")
    p = _event_insert_params(db)
    assert p[-3] is None and p[-2] is None and p[-1] is None


def test_structured_link_skips_headline_linker():
    # When the resolver already produced a drug link, the gazetteer is never
    # consulted — the structured spine entity wins.
    db = _FakeDB()
    store = KnowledgeStore(db)
    stub = _StubLinker("novo", LinkResult("company", "co-novo", "Novo Nordisk", 0.9, "novo"))
    store._event_linker = stub
    store._store_event(
        _event_record(drug_id="drug-1", company_id=None,
                      description="Novo Nordisk weekly insulin wins FDA nod"), "run-1")
    p = _event_insert_params(db)
    assert p[-3] == "drug-1" and p[-2] == "drug"
    assert stub.calls == 0  # structured hit short-circuits before the linker


def test_linker_build_failure_degrades_to_null_not_crash(monkeypatch):
    # The central ingest-safety claim: if the gazetteer can't be built, the
    # store falls back to a never-linking sentinel (cached, no retry storm) and
    # still writes the event with NULL primary — ingest must not break.
    import services.entity_linker as el
    from integration.knowledge_store import _NULL_LINKER

    class _Boom:
        def __init__(self, db):
            pass

        def load(self, **k):
            raise RuntimeError("gazetteer unavailable")

    monkeypatch.setattr(el, "EntityLinker", _Boom)
    db = _FakeDB()
    store = KnowledgeStore(db)
    new_id, was_insert = store._store_event(
        _event_record(drug_id=None, company_id=None,
                      description="AstraZeneca stock falls after FDA panel vote"), "run-1")
    assert was_insert
    p = _event_insert_params(db)
    assert p[-3] is None and p[-2] is None and p[-1] is None
    assert store._event_linker is _NULL_LINKER  # cached sentinel — no rebuild


def test_headline_link_accepts_at_floor_inclusive():
    # 0.85 (a hand-vetted priority alias) is inclusive — pins the boundary so a
    # regression to a strict > comparison is caught.
    db = _FakeDB()
    store = KnowledgeStore(db)
    store._event_linker = _StubLinker(
        "bms", LinkResult("company", "co-bms", "Bristol Myers Squibb", 0.85, "bms"))
    store._store_event(
        _event_record(drug_id=None, company_id=None,
                      description="bms acquires obesity biotech"), "run-1")
    p = _event_insert_params(db)
    assert p[-3] == "co-bms"


def test_relink_null_primary_events_grounds_existing_via_headline():
    db = _FakeDB()
    rows = [{"id": "e1", "description": "AstraZeneca stock falls after FDA panel vote"},
            {"id": "e2", "description": "Generic market update with no named entity"}]
    db.fetch_all = lambda sql, p=None: (
        rows if "primary_entity_id is null" in sql.lower() else [])
    store = KnowledgeStore(db)
    store._event_linker = _StubLinker(
        "astrazeneca", LinkResult("company", "co-az", "AstraZeneca", 0.9, "astrazeneca"))
    res = store.relink_null_primary_events()
    assert res["scanned"] == 2 and res["relinked"] == 1  # only the AstraZeneca one
    upd = [e for e in db.executed if "update market_events" in e[0].lower()]
    assert upd and "co-az" in upd[0][1]
