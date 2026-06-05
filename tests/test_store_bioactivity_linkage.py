"""D3: bioactivity store linkage — drug_id + target_id are written.

Root cause of bioactivities.drug_id = 100% NULL and molecular_targets = 0:
_store_bioactivity never wrote drug_id/target_id, and the connector didn't carry
a generic_name identifier for the resolver to link a drug. These tests pin that
the store now (a) writes the resolved drug_id, and (b) upserts a target row and
writes target_id.
"""

from __future__ import annotations

from datetime import datetime, timezone

from connectors.base import Provenance, RawRecord, RecordType, SourceType
from integration.embedder import EmbeddedRecord
from integration.entity_resolver import ResolvedLink, ResolvedRecord
from integration.knowledge_store import KnowledgeStore
from integration.normalizer import NormalizedRecord


class _FakeDB:
    def __init__(self, existing_target_id=None, existing_activity=False):
        self.executed: list[tuple[str, list]] = []
        self._existing_target_id = existing_target_id
        self._existing_activity = existing_activity

    def fetch_one(self, sql, params=None):
        s = sql.lower()
        if "from molecular_targets" in s:
            return {"id": self._existing_target_id} if self._existing_target_id else None
        if "from bioactivities" in s:
            return {"id": "existing-act"} if self._existing_activity else None
        return None

    def execute(self, sql, params=None):
        self.executed.append((sql, params or []))


def _bioactivity_record(drug_id="drug-uuid-1"):
    prov = Provenance(
        source_type=SourceType.CHEMBL,
        api_endpoint="https://www.ebi.ac.uk/chembl/api/data/activity.json",
        query_params={},
        retrieved_at=datetime(2026, 6, 5, tzinfo=timezone.utc),
        raw_response_hash="h",
    )
    data = {
        "drug_name": "semaglutide",
        "chembl_id": "CHEMBL1",
        "target_chembl_id": "CHEMBL_TGT_GLP1R",
        "target_name": "Glucagon-like peptide 1 receptor",
        "activity_type": "EC50",
        "activity_value": 0.5,
        "activity_units": "nM",
        "pchembl_value": 9.3,
    }
    raw = RawRecord(
        record_type=RecordType.BIOACTIVITY,
        external_id="chembl_activity_999",
        source_name="ChEMBL",
        provenance=prov,
        data=data,
        identifiers={"chembl_id": "CHEMBL1", "generic_name": "semaglutide"},
    )
    norm = NormalizedRecord(raw=raw, canonical_data=data, identifiers=raw.identifiers)
    links = {}
    if drug_id:
        links["generic_name"] = ResolvedLink(
            entity_type="drug", entity_id=drug_id, matched_via="exact_id",
            confidence=1.0, matched_value="semaglutide",
        )
    resolved = ResolvedRecord(normalized=norm, resolved_links=links)
    return EmbeddedRecord(resolved=resolved, embedding=None)


def test_insert_writes_drug_id_and_target_id():
    db = _FakeDB(existing_target_id=None, existing_activity=False)
    store = KnowledgeStore(db)
    new_id, was_insert = store._store_bioactivity(_bioactivity_record(), "run-1")
    assert was_insert
    # A molecular_targets INSERT happened (target was new)
    target_inserts = [e for e in db.executed if "insert into molecular_targets" in e[0].lower()]
    assert len(target_inserts) == 1
    # The bioactivities INSERT carries a non-NULL drug_id and target_id
    act_inserts = [e for e in db.executed if "insert into bioactivities" in e[0].lower()]
    assert len(act_inserts) == 1
    params = act_inserts[0][1]
    # params order: id, drug_id, target_id, chembl_activity_id, ...
    assert params[1] == "drug-uuid-1"   # drug_id
    assert params[2] is not None         # target_id


def test_reuses_existing_target():
    db = _FakeDB(existing_target_id="tgt-existing", existing_activity=False)
    store = KnowledgeStore(db)
    store._store_bioactivity(_bioactivity_record(), "run-1")
    # No new target insert; existing reused
    assert not any("insert into molecular_targets" in e[0].lower() for e in db.executed)
    act_inserts = [e for e in db.executed if "insert into bioactivities" in e[0].lower()]
    assert act_inserts[0][1][2] == "tgt-existing"  # target_id


def test_unresolved_drug_leaves_drug_id_null_but_still_stores():
    db = _FakeDB(existing_target_id=None, existing_activity=False)
    store = KnowledgeStore(db)
    new_id, was_insert = store._store_bioactivity(_bioactivity_record(drug_id=None), "run-1")
    assert was_insert
    act_inserts = [e for e in db.executed if "insert into bioactivities" in e[0].lower()]
    assert act_inserts[0][1][1] is None   # drug_id NULL (no resolver link)
    assert act_inserts[0][1][2] is not None  # target still linked
