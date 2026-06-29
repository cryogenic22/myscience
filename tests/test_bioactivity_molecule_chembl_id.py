"""Conservation: persist the molecule's ChEMBL id on bioactivities.

`bioactivities.molecule_chembl_id` exists (migration 089) but the INSERT/UPDATE
in `_store_bioactivity` never referenced it — so `data['chembl_id']` (the
molecule id, present in every ChEMBL activity payload) was dropped on 100% of
rows (prod: 746/746 NULL), and 25% of rows (190/746) have neither `drug_id` NOR
`molecule_chembl_id` — no molecule link at all.

These tests pin that both store paths persist molecule_chembl_id from the
payload's chembl_id (and tolerate its absence).
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from connectors.base import Provenance, RawRecord, RecordType, SourceType
from integration.embedder import EmbeddedRecord
from integration.entity_resolver import ResolvedRecord
from integration.knowledge_store import KnowledgeStore
from integration.normalizer import NormalizedRecord


class _FakeDB:
    """Target already exists; bioactivity row presence is configurable."""
    def __init__(self, existing_activity=False):
        self.executed: list[tuple[str, list]] = []
        self._existing_activity = existing_activity

    def fetch_one(self, sql, params=None):
        s = sql.lower()
        if "from molecular_targets" in s:
            return {"id": "tgt-uuid"}
        if "from bioactivities" in s:
            return {"id": "act-uuid"} if self._existing_activity else None
        return None

    def fetch_all(self, sql, params=None):
        return []

    def execute(self, sql, params=None):
        self.executed.append((sql, params or []))


def _bioactivity(chembl_id="CHEMBL1487", drug_linked=True) -> EmbeddedRecord:
    data = {
        "chembl_id": chembl_id,                # the molecule id — must be persisted
        "chembl_activity_id": "ACT_5678",
        "target_chembl_id": "CHEMBL_TGT",
        "activity_type": "IC50", "activity_value": 42.0, "activity_units": "nM",
        "assay_type": "B", "pchembl_value": 7.4, "assay_description": "enzymatic",
    }
    if chembl_id is None:
        data.pop("chembl_id")
    prov = Provenance(
        source_type=SourceType.CHEMBL, api_endpoint="https://www.ebi.ac.uk/chembl",
        query_params={}, retrieved_at=datetime(2026, 6, 24, tzinfo=timezone.utc),
        raw_response_hash="h",
    )
    raw = RawRecord(record_type=RecordType.BIOACTIVITY, external_id="ACT_5678",
                    source_name="ChEMBL", provenance=prov, data=data, identifiers={})
    norm = NormalizedRecord(raw=raw, canonical_data=data, identifiers={})
    links = {"generic_name": SimpleNamespace(entity_id="drug-uuid")} if drug_linked else {}
    return EmbeddedRecord(resolved=ResolvedRecord(normalized=norm, resolved_links=links),
                          embedding=None)


def _inserts(db):
    return [e for e in db.executed if "insert into bioactivities" in e[0].lower()]


def _updates(db):
    return [e for e in db.executed if "update bioactivities" in e[0].lower()]


def test_insert_persists_molecule_chembl_id():
    db = _FakeDB(existing_activity=False)
    KnowledgeStore(db)._store_bioactivity(_bioactivity("CHEMBL1487"), "run-1")
    ins = _inserts(db)
    assert len(ins) == 1
    sql, params = ins[0]
    assert "molecule_chembl_id" in sql.lower()
    # position-precise: molecule_chembl_id is INSERT param index 3
    # (id, drug_id, target_id, molecule_chembl_id, chembl_activity_id, ...)
    assert params[3] == "CHEMBL1487"       # the molecule id is persisted, not dropped


def test_update_persists_molecule_chembl_id():
    db = _FakeDB(existing_activity=True)
    KnowledgeStore(db)._store_bioactivity(_bioactivity("CHEMBL1487"), "run-1")
    ups = _updates(db)
    assert len(ups) == 1
    sql, params = ups[0]
    assert "molecule_chembl_id" in sql.lower()
    # position-precise: molecule_chembl_id is UPDATE param index 2
    # (drug_id, target_id, molecule_chembl_id, activity_type, ...)
    assert params[2] == "CHEMBL1487"


def test_missing_chembl_id_is_null_not_crash():
    db = _FakeDB(existing_activity=False)
    KnowledgeStore(db)._store_bioactivity(_bioactivity(chembl_id=None), "run-1")
    ins = _inserts(db)
    assert len(ins) == 1
    assert ins[0][1][3] is None             # molecule_chembl_id param (idx 3) is NULL; INSERT still happens
