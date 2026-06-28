"""Onboarding contract persistence (Connector Press Phase 1, migration 099).

DB-free tests over services/connector_taxonomy.py: the OnboardingRecord now
carries the full connector contract (config/mappings/record_type/trust_tier/
must_capture/license/cadence), `set_onboarding_contract` writes only the fields
you pass, `register_contract` orchestrates source-register → draft → contract, and
`list_runnable_sources` is what the scheduler reads to run prod dynamic sources.
"""
from __future__ import annotations

from services.connector_taxonomy import (
    OnboardingRecord,
    _row_to_onboarding,
    list_runnable_sources,
    register_contract,
    set_onboarding_contract,
)


def test_to_dict_includes_contract():
    rec = OnboardingRecord(
        source_id="s1", status="prod", config={"url": "u"},
        field_mappings=[{"source_field": "a", "target_field": "b"}],
        record_type="drug", trust_tier=2, must_capture=["generic_name"],
        license="pub", cadence={"hour": "*/6"},
    )
    d = rec.to_dict()
    assert d["config"] == {"url": "u"}
    assert d["record_type"] == "drug"
    assert d["trust_tier"] == 2
    assert d["must_capture"] == ["generic_name"]
    assert d["cadence"] == {"hour": "*/6"}


def test_row_to_onboarding_tolerates_pre_099_rows():
    # a row from a bare start_onboarding RETURNING has no contract columns
    rec = _row_to_onboarding({"source_id": "s1", "status": "draft"})
    assert rec.config == {} and rec.must_capture == [] and rec.record_type is None


class _CaptureDB:
    def __init__(self):
        self.execs: list = []

    def execute(self, sql, params=None):
        self.execs.append((" ".join(sql.split()), params))

    def fetch_one(self, sql, params=None):
        return {"source_id": "s1", "status": "draft"}  # for the get_onboarding re-fetch

    def fetch_all(self, sql, params=None):
        return []


def test_set_contract_writes_only_provided_fields():
    db = _CaptureDB()
    set_onboarding_contract(
        db, "s1", record_type="drug", config={"url": "u"},
        trust_tier=2, must_capture=["x"],
    )
    sql, params = db.execs[0]
    assert sql.startswith("UPDATE source_onboarding SET")
    assert "record_type = %s" in sql
    assert "config = %s::jsonb" in sql
    assert "trust_tier = %s" in sql
    assert "must_capture = %s" in sql
    # license/field_mappings/cadence were NOT passed → not written
    assert "license = %s" not in sql and "cadence = %s" not in sql
    assert '{"url": "u"}' in params and 2 in params and ["x"] in params


def test_set_contract_noop_when_empty():
    db = _CaptureDB()
    set_onboarding_contract(db, "s1")
    assert db.execs == []  # nothing to write → no UPDATE issued


def test_list_runnable_sources_filters_prod_runtime_types():
    captured: dict = {}

    class DB:
        def fetch_all(self, sql, params=None):
            captured["sql"] = " ".join(sql.split())
            captured["params"] = params
            return [{
                "source_id": "a", "source_name": "A", "connector_type": "API_REST",
                "record_type": "drug", "config": {"url": "u"}, "cadence": None, "trust_tier": 2,
            }]

    rows = list_runnable_sources(DB())
    assert rows[0]["source_id"] == "a"
    assert "o.status = 'prod'" in captured["sql"]
    assert captured["params"][0] == ["API_REST", "CSV_FILE", "RSS"]


class _FakeDB:
    """Simulates the sources + source_onboarding rows for the register_contract
    orchestration path (routes queries by keyword)."""

    def __init__(self):
        self.source = None
        self.onboarding = None
        self.execs: list = []

    def fetch_one(self, sql, params=None):
        s = " ".join(sql.split())
        if "FROM connector_types WHERE name" in s:
            return {"name": params[0], "payload_formats": [], "auth_kinds": [], "description": None}
        if "FROM sources WHERE source_id" in s:
            return dict(self.source) if self.source else None
        if s.startswith("INSERT INTO sources"):
            self.source = {
                "source_id": params[0], "display_name": params[1], "tier": params[2],
                "kind": params[3], "base_url": params[4], "description": params[5],
                "active": True, "license_status": params[6], "license_renewal_at": params[7],
                "rate_limit_per_min": params[8], "usage_profile": {}, "latest_quality_id": None,
                "created_at": None, "updated_at": None,
            }
            return dict(self.source)
        if "FROM source_onboarding WHERE source_id" in s:
            return dict(self.onboarding) if self.onboarding else None
        if s.startswith("INSERT INTO source_onboarding"):
            self.onboarding = {
                "source_id": params[0], "status": params[1], "owner": params[2],
                "contact": params[3], "go_live_date": params[4], "escalation": params[5],
            }
            return dict(self.onboarding)
        return None

    def fetch_all(self, sql, params=None):
        return []

    def execute(self, sql, params=None):
        s = " ".join(sql.split())
        self.execs.append((s, params))
        if "UPDATE sources SET connector_type" in s and self.source:
            self.source["connector_type"] = params[0]


def test_register_contract_orchestrates_writes():
    db = _FakeDB()
    rec = register_contract(
        db, "eu_x", source_name="EU X", connector_type="API_REST",
        record_type="drug",
        config={"url": "https://x", "external_id_field": "id"},
        trust_tier=2, must_capture=["generic_name"], license="pub",
    )
    # 1) source row created with the display name
    assert db.source and db.source["source_id"] == "eu_x" and db.source["display_name"] == "EU X"
    # 2) connector_type stamped onto the source
    assert any("UPDATE sources SET connector_type" in e[0] for e in db.execs)
    # 3) onboarding draft created
    assert db.onboarding and db.onboarding["status"] == "draft"
    # 4) the contract was actually persisted (conservation: not silently dropped)
    contract_updates = [e for e in db.execs if e[0].startswith("UPDATE source_onboarding SET")]
    assert contract_updates, "register_contract did not persist the contract"
    sql, params = contract_updates[0]
    assert "config = %s::jsonb" in sql and "record_type = %s" in sql and "trust_tier = %s" in sql
    assert "drug" in params and 2 in params and ["generic_name"] in params
    assert rec is not None
