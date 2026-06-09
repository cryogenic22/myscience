"""DB-free tests for the ATC crosswalk loader (Loop L1b)."""

from __future__ import annotations

from services.crosswalk_loader import (
    build_atc_candidate,
    load_atc_seeds,
    seed_atc_mappings,
)
from services.ontology_crosswalk import classify, load_crosswalk_pack

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
    assert stats["would_write"] == 5 and stats["written"] == 0
    assert db.inserts == [] and db.updates == []


def test_apply_writes_record_and_backfills_atc():
    db = _MockDB(_drugs())
    stats = load_atc_seeds(db, _PACK, apply=True)
    assert stats["written"] == 5
    assert len(db.inserts) == 5 and len(db.updates) == 5
    # the crosswalk row carries the governed relation (related) + the ATC code
    sema_insert = next(p for p in db.inserts if p[0] == "d-sema")
    assert "A10BJ06" in sema_insert and "related" in sema_insert


def test_unresolved_drug_is_counted_not_dropped():
    db = _MockDB({"semaglutide": {"id": "d-sema", "generic_name": "semaglutide"}})
    stats = load_atc_seeds(db, _PACK, apply=True)
    assert stats["unresolved_drug"] == 4   # tirz/met/empa/dapa absent
    assert stats["written"] == 1           # only semaglutide written, none dropped silently


def test_backfill_update_is_guarded_against_duplicates():
    """The UPDATE only appends when the code is not already present (idempotent)."""
    db = _MockDB(_drugs())
    load_atc_seeds(db, _PACK, apply=True)
    sema_update = next(p for p in db.updates if p[1] == "d-sema")
    # params: [atc_code, drug_id, atc_code] — the WHERE NOT (... = ANY) guard
    assert sema_update[0] == "A10BJ06" and sema_update[2] == "A10BJ06"
