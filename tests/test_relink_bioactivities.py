"""ChEMBL bioactivity → drug-spine relink (pure-DB, API-free) + emitter activation.

Root cause the D3 loop fixed at *ingest* (connector carries ``generic_name`` →
``_store_bioactivity`` writes ``drug_id``): NEW activity rows now link. But two
gaps remained for a *robust, re-runnable* activation:

1. Rows ingested before D3 (and the residual off-spine rows) still carry
   ``drug_id = NULL`` and could only be relinked by re-hitting the ChEMBL API,
   because the bioactivities table never persisted the *molecule* identifier —
   only ``chembl_activity_id`` (the assay row id). There was no pure-DB key to
   resolve compound → drug.
2. No integration test pinned that, once ``drug_id`` is populated, the
   ``BioactivityEmitter`` actually emits ``target_activity`` facts idempotently
   via ``run_emitter``.

This module fixes both: it pins a DB-only ``relink_bioactivities`` that maps
``bioactivities.molecule_chembl_id → drugs.chembl_id → drug_id`` (additive, only
fills NULL, counts the unresolved — conservation #2: no silent drop), and a
MockDB integration test that the emitter emits + is idempotent once linked.
"""

from __future__ import annotations

from services.fact_emitters.base import run_emitter
from services.fact_emitters.mechanisms import BioactivityEmitter


# ── pure-DB relink (molecule_chembl_id → drugs.chembl_id → drug_id) ──────────

class _RelinkDB:
    """Minimal fake DB for the relink backfill.

    Seeds a drug spine (chembl_id → drug_id, excluding merged dups) and a set of
    NULL-drug_id bioactivity rows, then records the UPDATEs the backfill issues.
    """

    def __init__(self, drug_spine: list[dict], null_rows: list[dict]):
        self._drug_spine = drug_spine
        self._null_rows = null_rows
        self.updates: list[tuple[str, str]] = []  # (bioactivity_id, drug_id)

    def fetch_all(self, sql, params=None):
        s = sql.lower()
        if "from drugs" in s:
            return list(self._drug_spine)
        if "from bioactivities" in s:
            # backfill selects NULL-drug_id rows that still carry a molecule id
            return list(self._null_rows)
        return []

    def execute(self, sql, params=None):
        s = sql.lower()
        if "update bioactivities" in s and "set drug_id" in s:
            # params: [drug_id, bioactivity_id]
            self.updates.append((str(params[1]), str(params[0])))


def _spine():
    return [
        {"drug_id": "drug-sema", "chembl_id": "CHEMBL1201247"},
        {"drug_id": "drug-tirz", "chembl_id": "CHEMBL4297846"},
    ]


def test_relink_maps_molecule_chembl_id_to_drug():
    from scripts.relink_bioactivities import relink

    db = _RelinkDB(
        drug_spine=_spine(),
        null_rows=[
            {"id": "act-1", "molecule_chembl_id": "CHEMBL1201247"},  # → sema
            {"id": "act-2", "molecule_chembl_id": "CHEMBL4297846"},  # → tirz
        ],
    )
    stats = relink(db)
    assert stats["matched"] == 2
    assert stats["unresolved"] == 0
    assert ("act-1", "drug-sema") in db.updates
    assert ("act-2", "drug-tirz") in db.updates


def test_relink_counts_unresolved_and_does_not_drop():
    """Conservation #2: a molecule not in the drug spine must be COUNTED, never
    silently dropped — the row stays (drug_id NULL), no UPDATE issued for it."""
    from scripts.relink_bioactivities import relink

    db = _RelinkDB(
        drug_spine=_spine(),
        null_rows=[
            {"id": "act-1", "molecule_chembl_id": "CHEMBL1201247"},   # resolvable
            {"id": "act-x", "molecule_chembl_id": "CHEMBL_OFFSPINE"},  # not in spine
        ],
    )
    stats = relink(db)
    assert stats["matched"] == 1
    assert stats["unresolved"] == 1
    assert stats["candidates"] == 2
    # only the resolvable row was updated; the off-spine row is preserved
    assert [u[0] for u in db.updates] == ["act-1"]


def test_relink_dry_run_issues_no_updates():
    from scripts.relink_bioactivities import relink

    db = _RelinkDB(
        drug_spine=_spine(),
        null_rows=[{"id": "act-1", "molecule_chembl_id": "CHEMBL1201247"}],
    )
    stats = relink(db, dry_run=True)
    assert stats["matched"] == 1
    assert db.updates == []


# ── emitter activation once drug_id is populated (idempotent) ────────────────

def _linked_bioactivity_rows():
    """What BioactivityEmitter.fetch_rows returns AFTER the relink populates
    drug_id (the JOIN to drugs now yields rows)."""
    return [
        {
            "activity_id": "act-1", "drug_id": "drug-sema",
            "activity_type": "EC50", "activity_value": 0.5, "activity_units": "nM",
            "activity_relation": "=", "pchembl_value": 9.3,
            "assay_description": "Agonist activity at human GLP-1R.",
            "target_name": "GLP-1 receptor", "source_api": "chembl",
            "source_url": "https://www.ebi.ac.uk/chembl/",
        },
        {
            "activity_id": "act-2", "drug_id": "drug-tirz",
            "activity_type": "Ki", "activity_value": 1.2, "activity_units": "nM",
            "activity_relation": "=", "pchembl_value": 8.9,
            "assay_description": "Binding at GIP receptor.",
            "target_name": "GIP receptor", "source_api": "chembl",
            "source_url": "https://www.ebi.ac.uk/chembl/",
        },
    ]


class _EmitDB:
    """MockDB for run_emitter: first pass asserts everything, a re-run finds the
    facts already present and skips them (idempotency)."""

    def __init__(self, already_exists: bool = False):
        self._already_exists = already_exists

    def fetch_all(self, sql, params=None):
        s = sql.lower()
        if "from facts" in s:  # _fact_exists
            return [{"id": "f-existing"}] if self._already_exists else []
        return []

    def fetch_one(self, sql, params=None):
        s = sql.lower()
        if "from evidence_records" in s:   # evidence dedup → miss
            return None
        if "insert into evidence_records" in s:
            return {"evidence_id": "ev-1"}
        return {"id": "fact-new"}

    def execute(self, sql, params=None):
        pass


def test_emitter_emits_target_activity_facts_once_linked(monkeypatch):
    em = BioactivityEmitter()
    monkeypatch.setattr(em, "fetch_rows", lambda *a, **k: _linked_bioactivity_rows())
    stats = run_emitter(_EmitDB(already_exists=False), em)
    assert stats.scanned == 2
    assert stats.asserted == 2
    assert stats.evidence_written == 2


def test_emitter_rerun_is_idempotent(monkeypatch):
    em = BioactivityEmitter()
    monkeypatch.setattr(em, "fetch_rows", lambda *a, **k: _linked_bioactivity_rows())
    stats = run_emitter(_EmitDB(already_exists=True), em)
    assert stats.asserted == 0
    assert stats.skipped_existing == 2
