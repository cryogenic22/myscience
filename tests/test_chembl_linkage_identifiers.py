"""D3 — ChEMBL connector must carry drug + target linkage identifiers.

Root cause of bioactivities.drug_id = 100% NULL / molecular_targets = 0: the
activity and mechanism records reached the resolver/store with no drug name and
no target ChEMBL id, so nothing could be linked. These tests pin that the
connector now emits ``generic_name`` (→ drug_id) and ``target_chembl_id`` /
``target_name`` (→ molecular_targets) on every activity/mechanism record, the
identifiers _store_bioactivity / _upsert_target_by_chembl rely on.
"""
from __future__ import annotations

from connectors.base import RecordType
from connectors.chembl import ChEMBLConnector


class _Resp:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def _connector_with_fake_http(monkeypatch, payload_for):
    c = ChEMBLConnector()

    def fake_fetch(url, params=None, max_retries=3):
        for key, payload in payload_for.items():
            if key in url:
                return _Resp(payload)
        return _Resp({})

    monkeypatch.setattr(c, "_fetch_with_retry", fake_fetch)
    return c


def test_activities_carry_drug_and_target_identifiers(monkeypatch):
    c = _connector_with_fake_http(monkeypatch, {
        "activity.json": {"activities": [{
            "activity_id": 999,
            "target_chembl_id": "CHEMBL_GLP1R",
            "target_pref_name": "Glucagon-like peptide 1 receptor",
            "target_organism": "Homo sapiens",
            "standard_type": "EC50", "standard_value": "0.5",
            "standard_units": "nM", "pchembl_value": "9.3",
        }]},
    })
    recs = c._fetch_activities("CHEMBL_SEMA", "semaglutide")
    assert len(recs) == 1
    r = recs[0]
    assert r.record_type == RecordType.BIOACTIVITY
    # drug linkage for the resolver
    assert r.identifiers.get("generic_name") == "semaglutide"
    # target linkage for _upsert_target_by_chembl
    assert r.data.get("target_chembl_id") == "CHEMBL_GLP1R"
    assert r.data.get("target_name") == "Glucagon-like peptide 1 receptor"


def test_mechanisms_carry_drug_and_target_identifiers(monkeypatch):
    c = _connector_with_fake_http(monkeypatch, {
        "mechanism.json": {"mechanisms": [{
            "mechanism_of_action": "GLP-1 receptor agonist",
            "target_chembl_id": "CHEMBL_GLP1R",
            "action_type": "AGONIST",
        }]},
    })
    recs = c._fetch_mechanisms("CHEMBL_SEMA", "semaglutide")
    assert recs, "mechanism record expected"
    r = recs[0]
    assert r.identifiers.get("generic_name") == "semaglutide"
    assert r.data.get("target_chembl_id") == "CHEMBL_GLP1R"
