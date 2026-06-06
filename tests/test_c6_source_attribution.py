"""C6 (learning loops) — source attribution closes the predictive-accuracy EWMA.

Two pieces:
  1. SourceRegistryService.seed_defaults — populate `sources` from the
     canonical connector set so attribution has a target (the registry
     shipped empty, so every decision skipped `no_source_attribution`).
  2. find_source_ids_for_decision — resolve a decision to its sources via the
     REAL provenance edge (signal → evidence_document_ids →
     evidence_records.source_id), not the non-existent `signals.source`
     column. Decision's own signal first, then the war-room's seed signal.

Fake-DB substring matching keys on stable, unambiguous SQL fragments.
"""

from __future__ import annotations


# ════════════════════════════════════════════════════════════════════
# seed_defaults
# ════════════════════════════════════════════════════════════════════

class _SeedFakeDB:
    """Captures register() inserts; reports which source_ids are 'in use'."""

    def __init__(self, in_use_source_ids):
        self._in_use = list(in_use_source_ids)
        self.registered: list[str] = []

    def fetch_all(self, sql, params=None):
        s = " ".join(sql.lower().split())
        if "distinct source_id from evidence_records" in s:
            return [{"source_id": sid} for sid in self._in_use]
        return []

    def fetch_one(self, sql, params=None):
        s = " ".join(sql.lower().split())
        # register() first checks for an existing row → None (always insert)
        if "from sources where source_id = %s" in s:
            return None
        # register() INSERT ... RETURNING
        if "insert into sources" in s and "returning" in s and params:
            sid = params[0]
            self.registered.append(sid)
            return {
                "source_id": sid, "display_name": params[1], "tier": params[2],
                "kind": params[3], "base_url": None, "description": None,
                "active": True, "license_status": "not_applicable",
                "license_renewal_at": None, "rate_limit_per_min": None,
                "usage_profile": {}, "latest_quality_id": None,
                "created_at": None, "updated_at": None,
            }
        return None

    def execute(self, sql, params=None):
        return None


def test_seed_defaults_only_seeds_in_use_sources():
    from services.source_registry import SourceRegistryService
    db = _SeedFakeDB(in_use_source_ids=["pubmed", "clinical_trials_gov", "not_a_connector"])
    seeded = SourceRegistryService.seed_defaults(db, only_in_use=True)
    # Both canonical ones seeded; the non-enum id is ignored (no invented names).
    assert set(seeded) == {"pubmed", "clinical_trials_gov"}
    assert "not_a_connector" not in db.registered


def test_seed_defaults_uses_canonical_display_names_and_tiers():
    from services.source_registry import SourceRegistryService, _SOURCE_SEED_META
    db = _SeedFakeDB(in_use_source_ids=["pubmed"])
    SourceRegistryService.seed_defaults(db, only_in_use=True)
    assert _SOURCE_SEED_META["pubmed"]["display_name"] == "PubMed"
    assert _SOURCE_SEED_META["clinical_trials_gov"]["tier"] == 1


def test_seed_defaults_all_when_not_restricted():
    from services.source_registry import SourceRegistryService
    from connectors.base import SourceType
    db = _SeedFakeDB(in_use_source_ids=[])
    seeded = SourceRegistryService.seed_defaults(db, only_in_use=False)
    assert set(seeded) == {st.value for st in SourceType}


# ════════════════════════════════════════════════════════════════════
# find_source_ids_for_decision (signal → evidence → source)
# ════════════════════════════════════════════════════════════════════

class _AttrFakeDB:
    """Resolves the signal→evidence_records.source_id chain and war_room
    seed-signal lookup. `signal_sources` maps signal_id → [source_id]."""

    def __init__(self, *, signal_sources=None, war_room_signal=None, snapshot_sources=None):
        self.signal_sources = signal_sources or {}
        self.war_room_signal = war_room_signal or {}
        self.snapshot_sources = snapshot_sources or {}

    def fetch_all(self, sql, params=None):
        s = " ".join(sql.lower().split())
        # Path 1: evidence_snapshot chain
        if "from evidence_snapshots es" in s and params:
            return [{"source_id": sid} for sid in self.snapshot_sources.get(str(params[0]), [])]
        # _sources_for_signal: signals s JOIN evidence_records er
        if "from signals s" in s and "join evidence_records er" in s and params:
            return [{"source_id": sid} for sid in self.signal_sources.get(str(params[0]), [])]
        return []

    def fetch_one(self, sql, params=None):
        s = " ".join(sql.lower().split())
        if "source_signal_id from war_rooms" in s and params:
            wr = str(params[0])
            return {"source_signal_id": self.war_room_signal.get(wr)}
        return None

    def execute(self, sql, params=None):
        return None


def test_attribution_via_decision_signal_evidence():
    from services.learning_service import find_source_ids_for_decision
    db = _AttrFakeDB(signal_sources={"sig-1": ["pubmed", "chembl"]})
    decision = {"id": "dec-1", "source_signal_id": "sig-1", "war_room_id": "wr-1"}
    sids, method = find_source_ids_for_decision(db, decision)
    assert method == "decision_signal_evidence"
    assert sids == ["pubmed", "chembl"]


def test_attribution_falls_back_to_war_room_signal():
    from services.learning_service import find_source_ids_for_decision
    db = _AttrFakeDB(
        signal_sources={"wr-sig": ["openfda_labels"]},
        war_room_signal={"wr-9": "wr-sig"},
    )
    # decision has NO source_signal_id → must use the war-room's seed signal.
    decision = {"id": "dec-2", "source_signal_id": None, "war_room_id": "wr-9"}
    sids, method = find_source_ids_for_decision(db, decision)
    assert method == "war_room_signal_evidence"
    assert sids == ["openfda_labels"]


def test_attribution_snapshot_chain_wins_when_present():
    from services.learning_service import find_source_ids_for_decision
    db = _AttrFakeDB(
        snapshot_sources={"dec-3": ["sec_edgar"]},
        signal_sources={"sig-x": ["pubmed"]},
    )
    decision = {"id": "dec-3", "source_signal_id": "sig-x", "war_room_id": "wr-3"}
    sids, method = find_source_ids_for_decision(db, decision)
    assert method == "evidence_snapshot_chain"
    assert sids == ["sec_edgar"]


def test_attribution_none_when_no_path():
    from services.learning_service import find_source_ids_for_decision
    db = _AttrFakeDB()
    decision = {"id": "dec-4", "source_signal_id": None, "war_room_id": None}
    sids, method = find_source_ids_for_decision(db, decision)
    assert sids == []
    assert method == "no_attribution_path"
