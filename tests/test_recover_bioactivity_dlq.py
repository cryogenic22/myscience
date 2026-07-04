"""Recovery of the ChEMBL bioactivity molecule_chembl_id dead-letter backlog.

These pin the reconstruction + replay orchestration in
``scripts/recover_bioactivity_dlq.py``: a dead-lettered activity (whose only
stored state is raw_payload + external_id + provenance) must be rebuilt into the
RawRecord the connector emitted and replayed through the POST-#304 store so that
molecule_chembl_id — the field whose absent column crashed the original store —
actually lands, and the failed_record flips to 'recovered'. The store internals
(the molecule_chembl_id INSERT/UPDATE columns) are pinned separately in
test_bioactivity_molecule_chembl_id.py; here we pin the *recovery wiring*.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

from connectors.base import RecordType, SourceType
from domain.pharma.pack import get_pharma_pack
from integration.entity_resolver import ResolvedRecord
from integration.knowledge_store import KnowledgeStore
from integration.normalizer import Normalizer
from scripts.recover_bioactivity_dlq import (
    _PENDING_FILTER,
    _build_components,
    _parse_retrieved,
    _reconstruct,
    _replay_batch,
    _resolve_drug_ids,
)

_PAYLOAD = {
    "drug_name": "empagliflozin",
    "chembl_id": "CHEMBL2107830",          # the MOLECULE id — must survive to store
    "target_chembl_id": "CHEMBL3884",
    "target_name": "Sodium/glucose cotransporter 2",
    "target_organism": "Homo sapiens",
    "activity_type": "IC50",
    "activity_value": 42.0,
    "activity_units": "nM",
    "activity_relation": "=",
    "pchembl_value": 7.4,
    "assay_type": "B",
    "assay_description": "enzymatic",
}


def _failed_record(raw_payload=None, provenance=None, external_id="chembl_activity_26593977", fid="fr-1"):
    return {
        "id": fid,
        "external_id": external_id,
        "raw_payload": _PAYLOAD if raw_payload is None else raw_payload,
        "provenance": provenance if provenance is not None else {
            "source_type": "chembl",
            "api_endpoint": "https://www.ebi.ac.uk/chembl/api/data/activity.json",
            "retrieved_at": "2026-03-29T00:55:42.322164+00:00",
        },
    }


# ---- reconstruction (pure) ----

def test_reconstruct_maps_payload_identifiers_and_provenance():
    raw = _reconstruct(_failed_record())
    assert raw.record_type == RecordType.BIOACTIVITY
    assert raw.provenance.source_type == SourceType.CHEMBL
    assert raw.external_id == "chembl_activity_26593977"
    # the molecule id rides in data -> _store_bioactivity persists it as molecule_chembl_id
    assert raw.data["chembl_id"] == "CHEMBL2107830"
    # generic_name rebuilt from drug_name so the resolver can link the canonical drug
    assert raw.identifiers["generic_name"] == "empagliflozin"
    # external_id's connector prefix is stripped back to the bare activity id
    assert raw.identifiers["activity_id"] == "26593977"
    assert raw.identifiers["chembl_id"] == "CHEMBL2107830"


def test_reconstruct_accepts_json_string_columns():
    # psycopg2 may hand jsonb back as a str depending on the adapter
    fr = _failed_record(raw_payload=json.dumps(_PAYLOAD),
                        provenance=json.dumps({"source_type": "chembl"}))
    raw = _reconstruct(fr)
    assert raw.data["chembl_id"] == "CHEMBL2107830"
    assert raw.provenance.source_type == SourceType.CHEMBL


def test_reconstruct_handles_non_prefixed_external_id():
    raw = _reconstruct(_failed_record(external_id="26593977"))
    assert raw.identifiers["activity_id"] == "26593977"


def test_parse_retrieved_parses_iso_and_falls_back_tz_aware():
    got = _parse_retrieved({"retrieved_at": "2026-03-29T00:55:42.322164+00:00"})
    assert got == datetime(2026, 3, 29, 0, 55, 42, 322164, tzinfo=timezone.utc)
    # missing / unparseable must not crash and must stay tz-aware
    assert _parse_retrieved({}).tzinfo is not None
    assert _parse_retrieved({"retrieved_at": "not-a-date"}).tzinfo is not None


# ---- deterministic, non-creating resolution ----

def test_build_components_disables_autocreate_and_network():
    normalizer, resolver, store = _build_components(db=object())
    # a recovery must never mint new drug/target rows from an unresolved name
    assert resolver.auto_create_enabled is False
    # openai_client=None => no embedding/LLM strategy => deterministic, offline
    assert resolver.openai_client is None
    assert isinstance(normalizer, Normalizer)
    assert isinstance(store, KnowledgeStore)


# ---- filter scope (no sweeping other chembl DLQ causes) ----

def test_filter_scoped_to_molecule_chembl_id_only():
    assert "molecule_chembl_id" in _PENDING_FILTER
    assert "bioactivities" in _PENDING_FILTER
    assert "status = 'pending'" in _PENDING_FILTER
    # the distinct chembl DLQ causes (Loop 4+) must NOT be swept into this replay
    assert "target_type" not in _PENDING_FILTER
    assert "target_name" not in _PENDING_FILTER


# ---- end-to-end replay through the REAL store (DB-free) ----

class _FakeDB:
    """Captures writes; every existence check misses so the store INSERTs."""
    def __init__(self):
        self.executed: list[tuple[str, list]] = []
        self._pool = None

    @contextmanager
    def transaction(self):
        yield self

    def fetch_one(self, sql, params=None):
        return None     # no existing target, no existing bioactivity -> INSERT path

    def fetch_all(self, sql, params=None):
        return []

    def execute(self, sql, params=None):
        self.executed.append((sql, params or []))


class _CountingResolver:
    """Stands in for EntityResolver, counting resolve() calls and returning a drug
    link only for known names (so we can assert per-distinct-name caching)."""
    def __init__(self, by_name=None):
        self.calls = 0
        self._by_name = by_name or {}

    def resolve(self, normalized):
        self.calls += 1
        name = normalized.raw.identifiers.get("generic_name")
        drug_id = self._by_name.get(name)
        links = {"generic_name": SimpleNamespace(entity_id=drug_id)} if drug_id else {}
        return ResolvedRecord(normalized=normalized, resolved_links=links)


def _find(db, needle):
    return [e for e in db.executed if needle in e[0].lower()]


# ---- drug resolution is cached per distinct name (bounds the alias side effect) ----

def test_resolve_drug_ids_caches_per_distinct_name():
    normalizer = Normalizer(domain_pack=get_pharma_pack())
    resolver = _CountingResolver({"empagliflozin": "drug-empa"})
    rows = [
        _failed_record(external_id="chembl_activity_1", fid="a"),
        _failed_record(external_id="chembl_activity_2", fid="b"),  # same drug_name
    ]
    cache = _resolve_drug_ids(normalizer, resolver, rows)
    assert cache == {"empagliflozin": "drug-empa"}
    assert resolver.calls == 1   # resolved ONCE despite two rows -> no per-row alias writes


def test_resolve_drug_ids_unresolved_maps_to_none():
    normalizer = Normalizer(domain_pack=get_pharma_pack())
    resolver = _CountingResolver(by_name={})   # nothing resolves
    cache = _resolve_drug_ids(normalizer, resolver, [_failed_record()])
    assert cache == {"empagliflozin": None}


# ---- end-to-end batch replay through the REAL store (DB-free) ----

def test_replay_batch_persists_molecule_and_drug_and_marks_recovered():
    db = _FakeDB()
    normalizer = Normalizer(domain_pack=get_pharma_pack())
    store = KnowledgeStore(db)

    inserted, updated, skipped = _replay_batch(
        db, normalizer, store, [_failed_record()], {"empagliflozin": "drug-empa"}
    )
    assert (inserted, updated, skipped) == (1, 0, 0)

    ins = _find(db, "insert into bioactivities")
    assert len(ins) == 1
    sql, params = ins[0]
    assert "molecule_chembl_id" in sql.lower()
    # position-precise: (id, drug_id, target_id, molecule_chembl_id, chembl_activity_id, ...)
    assert params[1] == "drug-empa"          # cached canonical drug_id is linked
    assert params[3] == "CHEMBL2107830"      # molecule id (the dropped field) persisted
    assert params[4] == "chembl_activity_26593977"

    upd = _find(db, "update failed_records")
    assert len(upd) == 1
    assert "recovered" in upd[0][0].lower()
    assert upd[0][1] == ["fr-1"]


def test_replay_batch_unresolved_drug_leaves_drug_id_null_but_keeps_molecule():
    db = _FakeDB()
    normalizer = Normalizer(domain_pack=get_pharma_pack())
    store = KnowledgeStore(db)
    # empty drug_ids cache -> drug_id NULL, but molecule_chembl_id must still land
    _replay_batch(db, normalizer, store, [_failed_record()], {})
    sql, params = _find(db, "insert into bioactivities")[0]
    assert params[1] is None                 # no drug link
    assert params[3] == "CHEMBL2107830"      # molecule_chembl_id still set


def test_replay_batch_skips_payload_with_no_chembl_id_leaving_it_pending():
    """Conservation guard: a payload with no molecule id has nothing to recover —
    it must be LEFT 'pending' (counted), NOT stored + silently marked 'recovered'."""
    db = _FakeDB()
    normalizer = Normalizer(domain_pack=get_pharma_pack())
    store = KnowledgeStore(db)
    payload = dict(_PAYLOAD)
    payload.pop("chembl_id")
    inserted, updated, skipped = _replay_batch(
        db, normalizer, store, [_failed_record(raw_payload=payload)], {}
    )
    assert (inserted, updated, skipped) == (0, 0, 1)
    assert _find(db, "insert into bioactivities") == []     # nothing stored
    assert _find(db, "update failed_records") == []         # NOT flipped to recovered


def test_replay_batch_updates_when_activity_already_landed():
    """If the activity already exists (a later run stored it without the molecule
    id), the replay UPDATEs to backfill molecule_chembl_id, not duplicate."""
    class _ExistingDB(_FakeDB):
        def fetch_one(self, sql, params=None):
            if "from bioactivities" in sql.lower():
                return {"id": "existing-act"}
            return None

    db = _ExistingDB()
    normalizer = Normalizer(domain_pack=get_pharma_pack())
    store = KnowledgeStore(db)

    inserted, updated, skipped = _replay_batch(
        db, normalizer, store, [_failed_record()], {"empagliflozin": "drug-empa"}
    )
    assert (inserted, updated, skipped) == (0, 1, 0)
    upd = _find(db, "update bioactivities")
    assert len(upd) == 1
    assert "molecule_chembl_id" in upd[0][0].lower()


def test_apply_reconnects_and_retries_once_on_connection_drop():
    """The first batch transaction drops the connection; _apply must null _conn,
    reconnect, and retry the (idempotent) batch — not crash."""
    import psycopg2
    from scripts.recover_bioactivity_dlq import _apply

    class _FlakyDB(_FakeDB):
        def __init__(self):
            super().__init__()
            self._fail_next = True
            self.connects = 0

        @contextmanager
        def transaction(self):
            if self._fail_next:
                self._fail_next = False
                raise psycopg2.OperationalError("server closed the connection unexpectedly")
            yield self

        def connect(self):
            self.connects += 1
            self._conn = object()   # a fresh "connection"

    db = _FlakyDB()
    normalizer = Normalizer(domain_pack=get_pharma_pack())
    store = KnowledgeStore(db)
    resolver = _CountingResolver({"empagliflozin": "drug-empa"})

    inserted, updated, skipped, recovered = _apply(
        db, normalizer, resolver, store, [_failed_record()], batch_size=50
    )
    assert db.connects == 1                      # reconnected exactly once
    assert (inserted, recovered) == (1, 1)       # batch retried + stored after reconnect


def test_apply_refuses_pooled_database():
    """Atomicity guard: _apply must fail closed against a pooled Database."""
    import pytest
    from scripts.recover_bioactivity_dlq import _apply

    class _PooledDB(_FakeDB):
        def __init__(self):
            super().__init__()
            self._pool = object()     # pretend we're pooled

    db = _PooledDB()
    normalizer = Normalizer(domain_pack=get_pharma_pack())
    store = KnowledgeStore(db)
    with pytest.raises(AssertionError):
        _apply(db, normalizer, _CountingResolver(), store, [_failed_record()])
