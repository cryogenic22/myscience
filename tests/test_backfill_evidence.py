"""D5 — evidence completeness backfill (SPEC_DATA_001 §D5).

Pure shaping tests + a recording-fake-DB test for the additive/idempotent
link path (writes an evidence_record, sets facts.source_doc_id only where NULL).
"""

from __future__ import annotations

from scripts.backfill_evidence import _fact_to_evidence, run


def test_shape_uses_description_as_evidence_text():
    row = {
        "id": "f1", "predicate": "market_event", "confidence": 0.5,
        "object_value": {"description": "Class II recall: impurity",
                         "source_url": "https://fda.gov/x",
                         "source_feed": "fda_shortages"},
    }
    ef = _fact_to_evidence(row)
    assert ef.evidence_text == "Class II recall: impurity"
    assert ef.source_url == "https://fda.gov/x"
    assert ef.source_id == "fda_shortages"
    assert ef.source_row_id == "f1"


def test_shape_falls_back_to_url_when_no_description():
    row = {"id": "f2", "predicate": "ma_deal", "confidence": 0.7,
           "object_value": {"source_url": "https://sec.gov/y"}}
    ef = _fact_to_evidence(row)
    assert ef.evidence_text == "https://sec.gov/y"


def test_shape_returns_none_when_no_text_or_url():
    row = {"id": "f3", "predicate": "market_event", "confidence": 0.5,
           "object_value": {"event_type": "macro"}}
    assert _fact_to_evidence(row) is None


class _FakeDB:
    def __init__(self, rows, evidence_id="ev-1"):
        self.rows = rows
        self.executed: list[tuple[str, list]] = []
        self._evidence_id = evidence_id

    def fetch_all(self, sql, params=None):
        if "from facts" in sql.lower() and "source_doc_id is null" in sql.lower():
            return self.rows
        return []

    def fetch_one(self, sql, params=None):
        s = sql.lower()
        if "filter (where source_doc_id is null)" in s:
            return {"n": 0, "t": 1}
        # _write_evidence idempotency probe: no existing record → insert path
        if "from evidence_records" in s and "source_content_hash" in s:
            return None
        if "insert into evidence_records" in s:
            return {"evidence_id": self._evidence_id}
        return None

    def execute(self, sql, params=None):
        self.executed.append((sql, params))


def test_run_links_fact_to_new_evidence():
    rows = [{
        "id": "f1", "predicate": "market_event", "confidence": 0.5,
        "object_value": {"description": "recall", "source_url": "u",
                         "source_feed": "fda"},
    }]
    db = _FakeDB(rows)
    stats = run(db)
    assert stats["linked"] == 1
    upd = [(s, p) for s, p in db.executed
           if "update facts set source_doc_id" in s.lower()]
    assert upd and upd[0][1] == ["ev-1", "f1"]
    # only updates where still NULL (idempotent)
    assert "source_doc_id is null" in upd[0][0].lower()


def test_run_dry_run_writes_nothing():
    rows = [{
        "id": "f1", "predicate": "market_event", "confidence": 0.5,
        "object_value": {"description": "recall", "source_url": "u"},
    }]
    db = _FakeDB(rows)
    stats = run(db, dry_run=True)
    assert stats["linked"] == 1
    assert db.executed == []
