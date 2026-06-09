"""DB-free tests for the ATC crosswalk loader (Loop L1b)."""

from __future__ import annotations

import services.crosswalk_loader as loader_mod
from services.crosswalk_loader import (
    _review_status_for,
    _should_backfill_spine,
    build_atc_candidate,
    load_atc_seeds,
    seed_atc_mappings,
)
from services.ontology_crosswalk import CrosswalkRecord, classify, load_crosswalk_pack

_PACK = load_crosswalk_pack()


class _MockDB:
    """Routes the loader's two statements; records writes for assertions."""

    def __init__(self, drug_rows: dict):
        self._drugs = drug_rows           # name(lower) -> {id, generic_name}
        self.inserts: list = []
        self.updates: list = []

    def connect(self):
        pass

    def fetch_one(self, sql, params=None):
        if "from drugs" in sql.lower():
            return self._drugs.get((params[0] or "").lower())
        return None

    def execute(self, sql, params=None):
        if "insert into crosswalk_records" in sql.lower():
            self.inserts.append(params)
        elif "update drugs set atc_codes" in sql.lower():
            self.updates.append(params)


# ============================================================
# Pure helpers
# ============================================================

def test_seed_mappings_from_pack():
    seeds = seed_atc_mappings(_PACK)
    names = {s["drug_name"] for s in seeds}
    assert {"semaglutide", "tirzepatide", "metformin"} <= names
    sema = next(s for s in seeds if s["drug_name"] == "semaglutide")
    assert sema["atc_l5"] == "A10BJ06"


def test_atc_candidate_is_governed_as_related_substance():
    """An ATC L5 seed maps to a molecule as RELATED at substance level — never
    exact identity (the SME invariant)."""
    rec = classify(build_atc_candidate("A10BJ06"), _PACK)
    assert rec.relation == "related"
    assert rec.scope == "substance_level"
    assert rec.relation != "exact"


# ============================================================
# Loader behaviour (MockDB)
# ============================================================

def _drugs():
    return {
        "semaglutide": {"id": "d-sema", "generic_name": "semaglutide"},
        "tirzepatide": {"id": "d-tirz", "generic_name": "tirzepatide"},
        "metformin": {"id": "d-met", "generic_name": "metformin"},
        "empagliflozin": {"id": "d-empa", "generic_name": "empagliflozin"},
        "dapagliflozin": {"id": "d-dapa", "generic_name": "dapagliflozin"},
    }


def test_dry_run_writes_nothing():
    db = _MockDB(_drugs())
    stats = load_atc_seeds(db, _PACK, apply=False)
    assert stats["would_write"] == 5 and stats["records_written"] == 0
    assert db.inserts == [] and db.updates == []


def test_apply_writes_record_and_backfills_atc():
    db = _MockDB(_drugs())
    stats = load_atc_seeds(db, _PACK, apply=True)
    assert stats["records_written"] == 5 and stats["spine_backfilled"] == 5
    assert len(db.inserts) == 5 and len(db.updates) == 5
    sema_insert = next(p for p in db.inserts if p[0] == "d-sema")
    assert "A10BJ06" in sema_insert and "related" in sema_insert


def test_unresolved_drug_is_counted_not_dropped():
    db = _MockDB({"semaglutide": {"id": "d-sema", "generic_name": "semaglutide"}})
    stats = load_atc_seeds(db, _PACK, apply=True)
    assert stats["unresolved_drug"] == 4   # tirz/met/empa/dapa absent
    assert stats["records_written"] == 1   # only semaglutide written, none dropped silently


# ============================================================
# Governance gate — a non-accepted verdict must NEVER touch the spine
# (the hole an independent review found). Monkeypatch classify().
# ============================================================

def _patch_classify(monkeypatch, record: CrosswalkRecord):
    monkeypatch.setattr(loader_mod, "classify", lambda cand, pack=None: record)


def test_rejected_verdict_records_but_does_not_backfill_spine(monkeypatch):
    _patch_classify(monkeypatch, CrosswalkRecord(
        relation="rejected", scope=None, confidence=0.0, confidence_breakdown={},
        flags=["ATC_TOO_BROAD_FOR_EXACT_MATCH"], action="rejected_or_quarantined",
        reason="rejected"))
    db = _MockDB(_drugs())
    stats = load_atc_seeds(db, _PACK, apply=True)
    assert len(db.inserts) == 5            # decision recorded (auditable, not dropped)
    assert db.updates == []                # NO spine backfill
    assert stats["spine_backfilled"] == 0
    # persisted review_status reflects the rejection
    assert db.inserts[0][-2] == "rejected"  # review_status param


def test_review_required_verdict_does_not_backfill_spine(monkeypatch):
    _patch_classify(monkeypatch, CrosswalkRecord(
        relation="related", scope="substance_level", confidence=0.6, confidence_breakdown={},
        flags=[], action="review_required", reason="review"))
    db = _MockDB(_drugs())
    stats = load_atc_seeds(db, _PACK, apply=True)
    assert db.updates == [] and stats["spine_backfilled"] == 0
    assert db.inserts[0][-2] == "pending_review"


def test_review_status_and_gate_helpers():
    assert _review_status_for("approved_auto") == "approved"
    assert _review_status_for("review_required") == "pending_review"
    assert _review_status_for("rejected_or_quarantined") == "rejected"
    approved = CrosswalkRecord("related", "substance_level", 0.9, {}, [], "approved_with_audit", "")
    rejected = CrosswalkRecord("rejected", None, 0.0, {}, [], "rejected_or_quarantined", "")
    review = CrosswalkRecord("related", "substance_level", 0.6, {}, [], "review_required", "")
    assert _should_backfill_spine(approved) is True
    assert _should_backfill_spine(rejected) is False
    assert _should_backfill_spine(review) is False


def test_backfill_update_is_guarded_against_duplicates():
    """The UPDATE only appends when the code is not already present (idempotent)."""
    db = _MockDB(_drugs())
    load_atc_seeds(db, _PACK, apply=True)
    sema_update = next(p for p in db.updates if p[1] == "d-sema")
    # params: [atc_code, drug_id, atc_code] — the WHERE NOT (... = ANY) guard
    assert sema_update[0] == "A10BJ06" and sema_update[2] == "A10BJ06"
