"""KB1 — Dossier Knowledge Base tests.

Two layers:
  1. PURE: predicate routing, domain-state scoring, coverage, fact rendering.
     No DB — the testable core of "what makes a good dossier".
  2. DB-backed: assemble (over a fake engagement + facts ledger), versioned
     persistence + supersession, latest/list reads. Fake-db pattern matches
     test_engagements_api.py.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from services import dossier_kb as kb
from services.dossier_kb import (
    DOSSIER_DOMAINS,
    DossierFact,
    EngagementNotFound,
    build_domains,
    route_predicate_to_domain,
    parse_asset_ref,
)


# ── Pure: routing ──────────────────────────────────────────────────


def test_route_known_predicate_exact():
    assert route_predicate_to_domain("wac_usd_monthly") == "pricing_and_access"
    assert route_predicate_to_domain("trial_result") == "clinical_profile"
    assert route_predicate_to_domain("ma_deal") == "competitive"
    assert route_predicate_to_domain("fda_approval_date") == "pipeline_and_macro"


def test_route_by_prefix():
    assert route_predicate_to_domain("payer_coverage_decision") == "pricing_and_access"
    assert route_predicate_to_domain("safety_signal_serious") == "clinical_profile"
    assert route_predicate_to_domain("regulatory_milestone") == "pipeline_and_macro"


def test_route_unknown_and_none_fall_back():
    assert route_predicate_to_domain("totally_novel_thing") == "wargame_specific"
    assert route_predicate_to_domain(None) == "wargame_specific"
    assert route_predicate_to_domain("") == "wargame_specific"


def test_parse_asset_ref():
    assert parse_asset_ref("drug:wegovy") == ("drug", "wegovy")
    assert parse_asset_ref("company:novo-nordisk") == ("company", "novo-nordisk")
    assert parse_asset_ref("wegovy") == ("drug", "wegovy")


# ── B2 (PB-E01): resolve_asset_to_subject ──────────────────────────


class _ResolveDB:
    """Fake DB for resolver tests. by_name maps lowercased slug → drug id;
    by_alias maps lowercased alias → (entity_type, id)."""

    def __init__(self, by_name=None, by_alias=None):
        self.by_name = by_name or {}
        self.by_alias = by_alias or {}

    def fetch_one(self, sql, params=None):
        s = (sql or "").lower()
        if "from drugs" in s:
            slug = str(params[0]).lower()
            hid = self.by_name.get(slug)
            return {"id": hid} if hid else None
        if "from entity_aliases" in s:
            alias = str(params[0]).lower()
            etype = params[1]
            hit = self.by_alias.get(alias)
            if hit and hit[0] == etype:
                return {"id": hit[1]}
            return None
        # other entity tables
        slug = str(params[0]).lower()
        hid = self.by_name.get(slug)
        return {"id": hid} if hid else None


def test_resolve_uuid_passes_through():
    uuid = "15b2232d-b931-4c1a-9aaa-000000000001"
    assert kb.resolve_asset_to_subject(_ResolveDB(), f"drug:{uuid}") == ("drug", uuid)


def test_resolve_by_generic_name():
    db = _ResolveDB(by_name={"semaglutide": "drug-uuid-1"})
    assert kb.resolve_asset_to_subject(db, "drug:semaglutide") == ("drug", "drug-uuid-1")


def test_resolve_by_brand_name_falls_through_to_drugs_query():
    # brand match handled inside the same drugs query (OR brand_name); fake maps the slug
    db = _ResolveDB(by_name={"wegovy": "drug-uuid-2"})
    assert kb.resolve_asset_to_subject(db, "drug:wegovy") == ("drug", "drug-uuid-2")


def test_resolve_via_alias_when_name_misses():
    db = _ResolveDB(by_name={}, by_alias={"ozempic": ("drug", "drug-uuid-3")})
    assert kb.resolve_asset_to_subject(db, "drug:ozempic") == ("drug", "drug-uuid-3")


def test_resolve_unresolved_falls_back_to_raw_slug():
    db = _ResolveDB(by_name={}, by_alias={})
    # graceful degradation: returns the slug, never raises
    assert kb.resolve_asset_to_subject(db, "drug:nonexistent") == ("drug", "nonexistent")


# ── Pure: build_domains ────────────────────────────────────────────


def test_build_domains_empty_is_all_gaps():
    domains, coverage, count = build_domains([])
    assert len(domains) == len(DOSSIER_DOMAINS)
    assert {d.domain for d in domains} == set(DOSSIER_DOMAINS)
    assert all(d.state == "gap" for d in domains)
    assert coverage == 0.0
    assert count == 0


def _fact(predicate, fact_class="signal", value="x", fid=None):
    return {
        "id": fid or f"f-{predicate}-{fact_class}",
        "predicate": predicate,
        "object_value": {"value": value},
        "fact_class": fact_class,
        "created_by": "data_automaton",
        "confidence": 0.9,
        "valid_from": None, "valid_to": None, "superseded_by": None,
    }


def test_build_domains_routes_and_counts():
    facts = [
        _fact("wac_usd_monthly", "corporate", "675", "p1"),
        _fact("pricing_intent", "signal", "cut", "p2"),
        _fact("trial_result", "reference", "positive", "c1"),
    ]
    domains, coverage, count = build_domains(facts)
    by = {d.domain: d for d in domains}
    assert len(by["pricing_and_access"].facts) == 2
    assert len(by["clinical_profile"].facts) == 1
    assert count == 3
    # 2 of 8 domains have facts → coverage 0.25
    assert coverage == pytest.approx(2 / 8)


def test_domain_state_complete_requires_three_and_grounded():
    # 3 facts but all 'signal' (ungrounded) → in_progress, not complete.
    ungrounded = [_fact("market_share", "signal", str(i), f"m{i}") for i in range(3)]
    domains, _, _ = build_domains(ungrounded)
    by = {d.domain: d for d in domains}
    assert by["competitive"].state == "in_progress"

    # 3 facts with one 'corporate' → complete.
    grounded = ungrounded + [_fact("ma_deal", "corporate", "acq", "deal1")]
    domains2, _, _ = build_domains(grounded)
    by2 = {d.domain: d for d in domains2}
    assert by2["competitive"].state == "complete"


def test_domain_state_in_progress_for_one_or_two():
    domains, _, _ = build_domains([_fact("wac_usd_monthly", "corporate", "675")])
    by = {d.domain: d for d in domains}
    assert by["pricing_and_access"].state == "in_progress"


# ── Pure: fact rendering + serialization ───────────────────────────


def test_fact_to_dict_is_camelcase():
    f = DossierFact(id="x", claim="c", fact_class="reference", source_label="s")
    assert f.to_dict() == {
        "id": "x", "claim": "c", "factClass": "reference", "sourceLabel": "s",
    }


def test_fact_class_coerced_to_valid():
    domains, _, _ = build_domains([_fact("wac_usd_monthly", "bogus_class")])
    by = {d.domain: d for d in domains}
    assert by["pricing_and_access"].facts[0].fact_class == "signal"


def test_claim_renders_predicate_and_value():
    domains, _, _ = build_domains([_fact("wac_usd_monthly", "corporate", "675")])
    by = {d.domain: d for d in domains}
    claim = by["pricing_and_access"].facts[0].claim
    assert "Wac usd monthly" in claim
    assert "675" in claim


def test_snapshot_gaps_lists_empty_domains_with_priority():
    domains, coverage, count = build_domains([_fact("wac_usd_monthly", "corporate")])
    snapshot = kb.DossierSnapshot(
        engagement_id="e1", focal_asset="drug:x", domains=domains,
        coverage_score=coverage, fact_count=count,
    )
    gaps = snapshot.gaps()
    gap_domains = {g["domain"] for g in gaps}
    # pricing has a fact, so it's NOT a gap; competitive is.
    assert "pricing_and_access" not in gap_domains
    assert "competitive" in gap_domains
    assert all("priority" in g for g in gaps)


# ── DB-backed: fake db ─────────────────────────────────────────────


class _FakeDB:
    """Models engagements (read), facts (read), dossier_snapshots (read+write)."""

    def __init__(self, engagement=None, facts=None):
        self._engagement = engagement
        self._facts = facts or []
        self.snapshots: list[dict] = []
        self._seq = 0
        self.supersede_calls: list[list] = []

    # engagement.get_engagement + facts_as_of both use fetch_all/fetch_one.
    def fetch_one(self, sql, params=None):
        s = (sql or "").lower()
        if "from engagements" in s:
            return self._engagement
        if "coalesce(max(version)" in s:
            eid = params[0]
            versions = [r["version"] for r in self.snapshots if r["engagement_id"] == eid]
            return {"v": max(versions) if versions else 0}
        if "insert into dossier_snapshots" in s:
            self._seq += 1
            new_id = f"snap-{self._seq}"
            row = {
                "id": new_id,
                "engagement_id": params["engagement_id"],
                "focal_asset": params["focal_asset"],
                "version": params["version"],
                "domains": params["domains"],
                "coverage_score": params["coverage_score"],
                "fact_count": params["fact_count"],
                "assembled_by": params["assembled_by"],
                "assembled_at": datetime(2026, 5, 31, tzinfo=timezone.utc),
                "superseded_by": None,
            }
            self.snapshots.append(row)
            return {"id": new_id, "assembled_at": row["assembled_at"]}
        if "from dossier_snapshots" in s and "superseded_by is null" in s:
            eid = params[0]
            heads = [r for r in self.snapshots
                     if r["engagement_id"] == eid and r["superseded_by"] is None]
            heads.sort(key=lambda r: r["version"], reverse=True)
            return heads[0] if heads else None
        return None

    def fetch_all(self, sql, params=None):
        s = (sql or "").lower()
        if "from facts" in s:
            return self._facts
        if "from dossier_snapshots" in s:
            eid = params[0]
            rows = [r for r in self.snapshots if r["engagement_id"] == eid]
            rows.sort(key=lambda r: r["version"], reverse=True)
            return rows
        return []

    def execute(self, sql, params=None):
        s = (sql or "").lower()
        if "set superseded_by" in s:
            new_id, eid, exclude_id = params
            self.supersede_calls.append(params)
            for r in self.snapshots:
                if (r["engagement_id"] == eid and r["id"] != exclude_id
                        and r["superseded_by"] is None):
                    r["superseded_by"] = new_id


class _Engagement:
    def __init__(self, asset="drug:wegovy", situation="defense"):
        self.asset = asset
        self.situation = situation


def _engagement_row(eid="e1", asset="drug:wegovy"):
    now = datetime(2026, 5, 31, tzinfo=timezone.utc)
    return {
        "id": eid, "name": "Test", "asset": asset, "sponsor": None,
        "situation": "defense", "workshop_date": None,
        "stage": "dossier", "status": "active",
        "scope": json.dumps({}), "created_by": "u",
        "created_at": now, "updated_at": now, "tenant_scope": None,
    }


def test_assemble_missing_engagement_raises():
    db = _FakeDB(engagement=None)
    with pytest.raises(EngagementNotFound):
        kb.assemble_dossier(db, "nope")


def test_assemble_builds_snapshot_from_facts():
    db = _FakeDB(
        engagement=_engagement_row(asset="drug:wegovy"),
        facts=[_fact("wac_usd_monthly", "corporate", "675"),
               _fact("trial_result", "reference", "win")],
    )
    snap = kb.assemble_dossier(db, "e1", assembled_by="analyst")
    assert snap.focal_asset == "drug:wegovy"
    assert snap.fact_count == 2
    assert snap.assembled_by == "analyst"
    assert snap.version is None  # not persisted yet
    assert 0 < snap.coverage_score < 1


def test_persist_assigns_version_and_supersedes():
    db = _FakeDB(engagement=_engagement_row(), facts=[_fact("wac_usd_monthly", "corporate")])

    snap1 = kb.assemble_and_persist(db, "e1", assembled_by="a1")
    assert snap1.version == 1
    assert snap1.id is not None

    snap2 = kb.assemble_and_persist(db, "e1", assembled_by="a2")
    assert snap2.version == 2
    # the v1 head must now be superseded by v2
    assert db.supersede_calls, "supersede should have been called"
    v1_row = next(r for r in db.snapshots if r["version"] == 1)
    assert v1_row["superseded_by"] == snap2.id


def test_get_latest_returns_head():
    db = _FakeDB(engagement=_engagement_row(), facts=[_fact("ma_deal", "corporate")])
    kb.assemble_and_persist(db, "e1")
    kb.assemble_and_persist(db, "e1")
    latest = kb.get_latest_snapshot(db, "e1")
    assert latest is not None
    assert latest.version == 2
    assert len(latest.domains) == len(DOSSIER_DOMAINS)


def test_list_versions_descending():
    db = _FakeDB(engagement=_engagement_row(), facts=[_fact("ma_deal", "corporate")])
    kb.assemble_and_persist(db, "e1")
    kb.assemble_and_persist(db, "e1")
    kb.assemble_and_persist(db, "e1")
    versions = kb.list_snapshot_versions(db, "e1")
    assert [v["version"] for v in versions] == [3, 2, 1]
    assert all("coverage_score" in v for v in versions)


def test_persisted_domains_roundtrip_through_json():
    """The stored domains JSONB must round-trip back into DomainView objects
    (the API serves get_latest, so this is the real read path)."""
    db = _FakeDB(
        engagement=_engagement_row(),
        facts=[_fact("wac_usd_monthly", "corporate", "675")],
    )
    kb.assemble_and_persist(db, "e1")
    # Simulate the JSONB being returned as a string (as a real driver might).
    db.snapshots[0]["domains"] = json.dumps(db.snapshots[0]["domains"]) \
        if not isinstance(db.snapshots[0]["domains"], str) else db.snapshots[0]["domains"]
    latest = kb.get_latest_snapshot(db, "e1")
    pricing = next(d for d in latest.domains if d.domain == "pricing_and_access")
    assert pricing.facts[0].fact_class == "corporate"
    assert "675" in pricing.facts[0].claim
