"""Open Targets disease recovery — emit per-disease NAMED ontology terms.

Root cause of the #1 *active* DLQ bleed (3,121 'pending', growing daily up to
PR #300): the open_targets connector emitted ONE ONTOLOGY_TERM per (drug,target)
carrying a `disease_associations` ARRAY but no single `name`, so every record
either crash-lost (pre-#300) or fail-closed-SKIPPED (post-#300) at
`_store_ontology_term` — the disease data never landed either way.

The fix models each associated disease as its own NAMED therapeutic-area
ontology term (name=disease_name, ontology_id=EFO/MONDO id), so the data lands
and re-runs dedupe idempotently on the stable ontology id (then name).
"""
from __future__ import annotations

from datetime import datetime, timezone

from connectors.base import Provenance, RawRecord, RecordType, SourceType
from connectors.open_targets import OpenTargetsConnector
from integration.embedder import EmbeddedRecord
from integration.entity_resolver import ResolvedRecord
from integration.knowledge_store import KnowledgeStore
from integration.normalizer import Normalizer, NormalizedRecord


# ── connector: one NAMED ontology term per disease ───────────────────────────

_TARGET = {
    "id": "ENSG00000112164",
    "approvedSymbol": "GLP1R",
    "approvedName": "glucagon like peptide 1 receptor",
    "associatedDiseases": {
        "count": 2,
        "rows": [
            {"disease": {"id": "MONDO_0005148", "name": "type 2 diabetes mellitus"},
             "score": 0.77, "datatypeScores": [{"id": "genetic_association", "score": 0.7}]},
            {"disease": {"id": "EFO_0001073", "name": "obesity"},
             "score": 0.72, "datatypeScores": []},
        ],
    },
}


def _connector():
    return OpenTargetsConnector(config=None)


def test_make_disease_records_emits_one_named_term_per_disease():
    recs = _connector()._make_disease_records("semaglutide", "CHEMBL123", _TARGET)
    assert len(recs) == 2
    for r in recs:
        assert r.record_type == RecordType.ONTOLOGY_TERM
        assert r.data["term_type"] == "therapeutic_area"
        assert r.data["name"]          # non-empty disease name
        assert r.data["ontology_id"]   # EFO/MONDO id
    assert {r.data["name"] for r in recs} == {"type 2 diabetes mellitus", "obesity"}
    assert {r.data["ontology_id"] for r in recs} == {"MONDO_0005148", "EFO_0001073"}


def test_make_disease_records_external_id_is_disease_stable():
    # external_id keyed on the disease (not drug/target) so the same disease
    # reached via different drugs dedupes to one therapeutic_area row.
    a = {r.data["ontology_id"]: r.external_id
         for r in _connector()._make_disease_records("semaglutide", "CHEMBL123", _TARGET)}
    b = {r.data["ontology_id"]: r.external_id
         for r in _connector()._make_disease_records("tirzepatide", "CHEMBL999", _TARGET)}
    assert a == b and len(a) == 2


def test_make_disease_records_skips_nameless_or_idless():
    target = {
        "id": "ENSG1", "approvedSymbol": "X",
        "associatedDiseases": {"rows": [
            {"disease": {"id": "EFO_1", "name": ""}, "score": 0.1},          # no name
            {"disease": {"id": "", "name": "ghost disease"}, "score": 0.1},  # no id
            {"disease": {"id": "EFO_2", "name": "real disease"}, "score": 0.1},
        ]},
    }
    recs = _connector()._make_disease_records("d", "id", target)
    assert [r.data["name"] for r in recs] == ["real disease"]


def test_make_disease_records_empty_associations_is_safe():
    assert _connector()._make_disease_records("d", "id", {"id": "ENSG1"}) == []
    assert _connector()._make_disease_records(
        "d", "id", {"associatedDiseases": {"rows": []}}) == []


# ── normalizer: the new fields survive into canonical_data ───────────────────

def _raw_disease(name="obesity", ontology_id="EFO_0001073"):
    return RawRecord(
        record_type=RecordType.ONTOLOGY_TERM,
        external_id=f"ot_disease_{ontology_id}",
        source_name="Open Targets Platform",
        provenance=Provenance(
            source_type=SourceType.OPEN_TARGETS,
            api_endpoint="https://api.platform.opentargets.org",
            query_params={}, retrieved_at=datetime(2026, 6, 24, tzinfo=timezone.utc),
            raw_response_hash="h",
        ),
        data={"name": name, "ontology_id": ontology_id, "term_type": "therapeutic_area"},
        identifiers={},
    )


def test_normalizer_keeps_name_ontology_id_term_type():
    cd = Normalizer().normalize(_raw_disease()).canonical_data
    assert cd["name"] == "obesity"
    assert cd["ontology_id"] == "EFO_0001073"
    assert cd["term_type"] == "therapeutic_area"


# ── store: persist ontology_id + three-tier dedup (mesh_id → ontology_id → name)

class _FakeDB:
    """Matches `SELECT id FROM <t> WHERE <col> = <val>` against seeded rows."""
    def __init__(self, by_mesh=None, by_ontology=None, by_name=None):
        self.executed: list[tuple[str, list]] = []
        self._by = {"mesh_id": by_mesh or {}, "ontology_id": by_ontology or {},
                    "name": by_name or {}}
        self._next_id = "ta-new"

    def fetch_one(self, sql, params=None):
        self.executed.append((sql, params or []))
        s = sql.lower()
        if "select id from" in s:
            for col in ("mesh_id", "ontology_id", "name"):
                if f"where {col} =" in s:
                    val = (params or [None])[0]
                    hit = self._by[col].get(val)
                    return {"id": hit} if hit else None
            return None
        if "insert into" in s:
            return {"id": self._next_id}
        return None

    def fetch_all(self, sql, params=None):
        return []

    def execute(self, sql, params=None):
        self.executed.append((sql, params or []))


def _embedded(name="obesity", ontology_id="EFO_0001073", mesh_id=None):
    cd = {"name": name, "ontology_id": ontology_id, "term_type": "therapeutic_area"}
    if mesh_id:
        cd["mesh_id"] = mesh_id
    norm = NormalizedRecord(raw=_raw_disease(name=name, ontology_id=ontology_id),
                            canonical_data=cd, identifiers={})
    return EmbeddedRecord(resolved=ResolvedRecord(normalized=norm, resolved_links={}),
                          embedding=None)


def _inserts(db):
    return [e for e in db.executed if "insert into" in e[0].lower()]


def test_insert_persists_ontology_id():
    db = _FakeDB()  # nothing seeded → INSERT path
    _, was_insert = KnowledgeStore(db)._store_ontology_term(_embedded(), "run-1")
    assert was_insert is True
    ins = _inserts(db)
    assert len(ins) == 1
    sql, params = ins[0]
    assert "ontology_id" in sql.lower()
    assert "EFO_0001073" in params  # the ontology id is persisted, not dropped


def test_dedup_by_ontology_id_updates_not_inserts():
    db = _FakeDB(by_ontology={"EFO_0001073": "existing-ta"})
    sid, was_insert = KnowledgeStore(db)._store_ontology_term(_embedded(), "run-1")
    assert was_insert is False
    assert sid == "existing-ta"
    assert _inserts(db) == []


def test_dedup_falls_back_to_name_when_no_id_match():
    # No mesh_id, ontology_id unseen, but the NAME already exists → UPDATE,
    # never a 2nd INSERT (which would crash the UNIQUE name constraint → DLQ).
    db = _FakeDB(by_name={"obesity": "existing-by-name"})
    sid, was_insert = KnowledgeStore(db)._store_ontology_term(_embedded(), "run-1")
    assert was_insert is False
    assert sid == "existing-by-name"
    assert _inserts(db) == []


def test_mesh_id_dedup_still_takes_precedence():
    db = _FakeDB(by_mesh={"D003924": "existing-mesh"})
    sid, was_insert = KnowledgeStore(db)._store_ontology_term(
        _embedded(mesh_id="D003924"), "run-1")
    assert was_insert is False
    assert sid == "existing-mesh"
    assert _inserts(db) == []
