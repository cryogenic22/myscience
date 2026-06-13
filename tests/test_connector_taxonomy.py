"""DataHub L2 — connector-type taxonomy + onboarding lifecycle.

Lane-1, DB-free. Pure state-machine helpers are tested in isolation; DB-backed
functions run against a small stateful fake `db` (fetch_one/fetch_all/execute)
that mirrors the migration-096 tables. An anti-drift test pins the Python
taxonomy constant to the migration's seed so the two never silently diverge.
"""
from __future__ import annotations

import os
import re

import pytest

from services.connector_taxonomy import (
    CONNECTOR_TYPE_NAMES,
    ONBOARDING_STATUSES,
    InvalidTransition,
    OnboardingNotFound,
    UnknownConnectorType,
    advance_onboarding,
    get_connector_type,
    is_valid_transition,
    list_connector_types,
    set_source_connector_type,
    start_onboarding,
    validate_transition,
)

_MIGRATION = os.path.join(
    os.path.dirname(__file__), "..", "schema", "migrations",
    "096_connector_taxonomy_onboarding.sql",
)


# ── pure state machine ───────────────────────────────────────────────────────

class TestTransitions:
    def test_legal_forward_path(self):
        assert is_valid_transition("draft", "test")
        assert is_valid_transition("test", "staged")
        assert is_valid_transition("staged", "prod")
        assert is_valid_transition("prod", "paused")
        assert is_valid_transition("paused", "prod")

    def test_retire_from_any_live_state(self):
        for s in ("draft", "test", "staged", "prod", "paused"):
            assert is_valid_transition(s, "retired")

    def test_retired_is_terminal(self):
        for s in ONBOARDING_STATUSES:
            assert not is_valid_transition("retired", s)

    def test_illegal_skips_are_rejected(self):
        assert not is_valid_transition("draft", "prod")   # can't skip test+staged
        assert not is_valid_transition("draft", "staged")
        assert not is_valid_transition("test", "prod")

    def test_unknown_status_never_valid(self):
        assert not is_valid_transition("draft", "bogus")
        assert not is_valid_transition("bogus", "test")

    def test_validate_raises_with_helpful_message(self):
        with pytest.raises(InvalidTransition):
            validate_transition("draft", "prod")
        with pytest.raises(InvalidTransition):
            validate_transition("draft", "bogus")
        # legal transition does not raise
        validate_transition("draft", "test")


# ── anti-drift: Python constant vs migration seed ────────────────────────────

class TestTaxonomySync:
    def test_python_names_match_migration_seed(self):
        with open(_MIGRATION, "r", encoding="utf-8") as f:
            sql = f.read()
        block = sql.split("INSERT INTO connector_types", 1)[1].split(";", 1)[0]
        seeded = set(re.findall(r"\(\s*'([A-Z_]+)'", block))
        assert seeded == set(CONNECTOR_TYPE_NAMES), (
            f"taxonomy drift: migration seeds {seeded}, "
            f"code declares {set(CONNECTOR_TYPE_NAMES)}"
        )


# ── stateful fake db ─────────────────────────────────────────────────────────

class FakeDB:
    """Minimal stand-in for the Database: dispatches on SQL substrings against
    in-memory connector_types + source_onboarding + a sources.connector_type map."""

    def __init__(self, *, connector_types=None, onboarding=None):
        self.types = {
            n: {"name": n, "payload_formats": ["json"], "auth_kinds": ["none"],
                "description": f"{n} desc"}
            for n in (connector_types if connector_types is not None
                      else CONNECTOR_TYPE_NAMES)
        }
        self.onboarding: dict[str, dict] = dict(onboarding or {})
        self.source_connector_type: dict[str, str] = {}

    def fetch_one(self, sql, params=None):
        if "FROM connector_types WHERE name" in sql:
            return self.types.get(params[0])
        if "FROM source_onboarding WHERE source_id" in sql:
            return self.onboarding.get(params[0])
        if "INSERT INTO source_onboarding" in sql:
            source_id, status, owner, contact, go_live, esc = params
            rec = {"source_id": source_id, "status": status, "owner": owner,
                   "contact": contact, "go_live_date": go_live, "escalation": esc,
                   "created_at": None, "updated_at": None}
            self.onboarding[source_id] = rec
            return rec
        if "UPDATE source_onboarding SET status" in sql:
            status, source_id = params
            self.onboarding[source_id]["status"] = status
            return self.onboarding[source_id]
        raise AssertionError(f"unexpected fetch_one SQL: {sql!r}")

    def fetch_all(self, sql, params=None):
        if "FROM connector_types" in sql:
            return sorted(self.types.values(), key=lambda r: r["name"])
        if "FROM source_onboarding" in sql:
            rows = list(self.onboarding.values())
            if params:
                rows = [r for r in rows if r["status"] == params[0]]
            return rows
        raise AssertionError(f"unexpected fetch_all SQL: {sql!r}")

    def execute(self, sql, params=None):
        if "UPDATE sources SET connector_type" in sql:
            connector_type, source_id = params
            self.source_connector_type[source_id] = connector_type
            return
        raise AssertionError(f"unexpected execute SQL: {sql!r}")


# ── taxonomy queries ─────────────────────────────────────────────────────────

class TestTaxonomyQueries:
    def test_list_returns_all_seeded_types(self):
        db = FakeDB()
        types = list_connector_types(db)
        assert {t.name for t in types} == set(CONNECTOR_TYPE_NAMES)

    def test_get_known_and_unknown(self):
        db = FakeDB()
        assert get_connector_type(db, "API_REST").name == "API_REST"
        assert get_connector_type(db, "NOPE") is None

    def test_set_connector_type_validates(self):
        db = FakeDB()
        set_source_connector_type(db, "acme_api", "API_REST")
        assert db.source_connector_type["acme_api"] == "API_REST"

    def test_set_unknown_connector_type_raises(self):
        db = FakeDB()
        with pytest.raises(UnknownConnectorType):
            set_source_connector_type(db, "acme_api", "FTP")
        assert "acme_api" not in db.source_connector_type   # no write on reject


# ── onboarding lifecycle (the dynamic, string-keyed path) ────────────────────

class TestOnboarding:
    def test_start_creates_draft_for_a_dynamic_source(self):
        db = FakeDB()
        rec = start_onboarding(db, "acme_api", owner="data-team",
                               connector_type="API_REST")
        assert rec.status == "draft" and rec.source_id == "acme_api"
        assert db.source_connector_type["acme_api"] == "API_REST"

    def test_start_is_idempotent(self):
        db = FakeDB()
        first = start_onboarding(db, "acme_api")
        second = start_onboarding(db, "acme_api")
        assert second.status == first.status == "draft"
        assert len(db.onboarding) == 1   # not duplicated

    def test_start_with_unknown_type_raises_before_insert(self):
        db = FakeDB()
        with pytest.raises(UnknownConnectorType):
            start_onboarding(db, "acme_api", connector_type="FTP")
        assert "acme_api" not in db.onboarding   # no partial write

    def test_advance_through_legal_lifecycle(self):
        db = FakeDB()
        start_onboarding(db, "acme_api")
        for nxt in ("test", "staged", "prod", "paused", "prod", "retired"):
            rec = advance_onboarding(db, "acme_api", nxt)
            assert rec.status == nxt

    def test_advance_illegal_transition_raises(self):
        db = FakeDB()
        start_onboarding(db, "acme_api")
        with pytest.raises(InvalidTransition):
            advance_onboarding(db, "acme_api", "prod")   # can't skip from draft
        assert db.onboarding["acme_api"]["status"] == "draft"   # unchanged

    def test_advance_noop_returns_current(self):
        db = FakeDB()
        start_onboarding(db, "acme_api")
        rec = advance_onboarding(db, "acme_api", "draft")
        assert rec.status == "draft"

    def test_advance_without_start_raises(self):
        db = FakeDB()
        with pytest.raises(OnboardingNotFound):
            advance_onboarding(db, "ghost", "test")
