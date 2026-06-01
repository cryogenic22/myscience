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


def test_route_market_event_does_not_pollute_competitive():
    # PB-H07: the generic fallback predicate must NOT hit the "market" prefix
    # (which dumped 505 FDA-recall facts into the competitive domain). Real
    # competitive predicates still route to competitive.
    assert route_predicate_to_domain("market_event") == "wargame_specific"
    assert route_predicate_to_domain("market_share") == "competitive"
    assert route_predicate_to_domain("competitor_launch") == "competitive"


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


# ── B3 (PB-E02): signals from compose_dossier feed the domains ─────


def test_build_domains_merges_signals_into_domains():
    # A pricing-tagged signal must land in pricing_and_access alongside facts.
    signals = [
        {"signal_id": "s1", "headline": "Novo cuts WAC 5%", "kbq_tag": "pricing_access", "ts": "2026-05-01T00:00:00Z"},
        {"signal_id": "s2", "headline": "New P3 readout", "kbq_tag": "clinical", "ts": "2026-05-02T00:00:00Z"},
    ]
    domains, coverage, count = build_domains([], signals)
    by = {d.domain: d for d in domains}
    assert len(by["pricing_and_access"].facts) == 1
    assert by["pricing_and_access"].facts[0].fact_class == "signal"
    assert "Novo cuts WAC" in by["pricing_and_access"].facts[0].claim
    # count includes signals → composed dossier is richer than facts-only
    assert count == 2
    assert coverage > 0


def test_build_domains_signals_optional_back_compat():
    # Calling without signals (legacy) still works → no regression.
    d1, c1, n1 = build_domains([_fact("wac_usd_monthly", "corporate")])
    d2, c2, n2 = build_domains([_fact("wac_usd_monthly", "corporate")], None)
    assert (c1, n1) == (c2, n2)


def test_signals_widen_coverage_vs_facts_only():
    facts = [_fact("wac_usd_monthly", "corporate")]  # pricing only
    signals = [{"signal_id": "s1", "headline": "trial win", "kbq_tag": "clinical", "ts": None}]
    _, cov_facts_only, _ = build_domains(facts)
    _, cov_composed, _ = build_domains(facts, signals)
    # adding a clinical signal lights up a second domain
    assert cov_composed > cov_facts_only


# ── B4 (PB-E03): PharmaMetrics facts feed the domains ──────────────


def test_build_domains_merges_metric_facts():
    from services.dossier_kb import DossierFact
    metric_facts = [
        ("pipeline_and_macro", DossierFact(id="m1", claim="Pipeline score 12.5 (88th percentile)",
                                           fact_class="corporate", source_label="PharmaMetrics")),
        ("clinical_profile", DossierFact(id="m2", claim="Trial success rate 67%",
                                         fact_class="corporate", source_label="PharmaMetrics")),
    ]
    domains, coverage, count = build_domains([], None, metric_facts)
    by = {d.domain: d for d in domains}
    assert any("Pipeline score" in f.claim for f in by["pipeline_and_macro"].facts)
    assert any("success rate" in f.claim for f in by["clinical_profile"].facts)
    assert count == 2
    # corporate-class metric facts are "grounded"
    assert by["pipeline_and_macro"].facts[0].fact_class == "corporate"


def test_metric_facts_optional_back_compat():
    d1, c1, n1 = build_domains([_fact("ma_deal", "corporate")])
    d2, c2, n2 = build_domains([_fact("ma_deal", "corporate")], None, None)
    assert (c1, n1) == (c2, n2)


# ── B5 (PB-E04): competitive breadth from related entities ─────────


def test_build_domains_routes_related_to_competitive():
    related = [
        {"id": "d2", "type": "drug", "name": "tirzepatide", "relation": "TARGETS_MECHANISM", "edge_count": 4},
        {"id": "d3", "type": "drug", "name": "dulaglutide", "relation": "COMPETES_WITH", "edge_count": 2},
    ]
    domains, coverage, count = build_domains([], None, None, related)
    by = {d.domain: d for d in domains}
    comp = by["competitive"].facts
    assert len(comp) == 2
    assert any("tirzepatide" in f.claim for f in comp)
    # cited edge present
    assert any("edges" in f.claim for f in comp)
    assert comp[0].fact_class == "inferred"


def test_related_optional_back_compat():
    d1, c1, n1 = build_domains([_fact("ma_deal", "corporate")])
    d2, c2, n2 = build_domains([_fact("ma_deal", "corporate")], None, None, None)
    assert (c1, n1) == (c2, n2)


def test_related_fact_cites_relation_and_edges():
    from services.dossier_kb import _related_to_dossier_fact
    f = _related_to_dossier_fact(
        {"id": "x", "type": "drug", "name": "semaglutide", "relation": "COMPETES_WITH", "edge_count": 7})
    assert "semaglutide" in f.claim
    assert "competes_with" in f.claim
    assert "7 edges" in f.claim
    assert "entity_graph" in f.source_label


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


def test_fact_carries_source_url_for_drillthrough():
    # PB-E05: market_event facts surface their source_url for drill-through.
    from services.dossier_kb import _fact_to_dossier_fact
    fact = {"id": "f1", "predicate": "market_event", "fact_class": "signal",
            "created_by": "data_automaton",
            "object_value": {"description": "Recall X",
                             "source_url": "https://api.fda.gov/x", "event_id": "e1"}}
    df = _fact_to_dossier_fact(fact)
    assert df.source_url == "https://api.fda.gov/x"
    assert df.to_dict()["sourceUrl"] == "https://api.fda.gov/x"


def test_fact_to_dict_omits_source_url_when_absent():
    f = DossierFact(id="x", claim="c", fact_class="reference", source_label="s")
    assert "sourceUrl" not in f.to_dict()      # additive: absent unless present


def test_row_to_snapshot_round_trips_source_url():
    from services.dossier_kb import _row_to_snapshot
    row = {"id": "s1", "engagement_id": "e1", "focal_asset": "drug:x", "version": 1,
           "coverage_score": 0.1, "fact_count": 1, "assembled_by": "system",
           "assembled_at": None,
           "domains": [{"domain": "clinical_profile", "priority": "high",
                        "state": "in_progress", "readiness": 0.3,
                        "facts": [{"id": "f1", "claim": "c", "factClass": "signal",
                                   "sourceLabel": "s", "sourceUrl": "https://u"}]}]}
    snap = _row_to_snapshot(row)
    assert snap.domains[0].facts[0].source_url == "https://u"


def test_render_value_prefers_description_for_event_facts():
    # market_event facts carry human text in `description`; without it they
    # rendered as raw JSON that leaked into scenario names (caught on real DB).
    from services.dossier_kb import _render_value
    ov = {"event_type": "approval", "description": "FDA approved drug X",
          "event_id": "e1", "source_url": "u"}
    out = _render_value(ov)
    assert out == "FDA approved drug X"
    assert "event_id" not in out          # no raw-JSON leak


def test_render_value_skips_empty_description():
    from services.dossier_kb import _render_value
    # None description falls through to the next usable key
    assert _render_value({"description": None, "summary": "the summary"}) == "the summary"
    # nothing usable → compact JSON (still a non-empty string, never "None")
    out = _render_value({"description": "", "event_id": "x"})
    assert out and out != "None"


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


# ── H05: per-domain readiness + overall (priority-weighted) readiness ──


def test_domain_readiness_zero_for_empty():
    from services.dossier_kb import _domain_readiness
    assert _domain_readiness([]) == 0.0


def test_domain_readiness_rewards_count_and_grounding():
    from services.dossier_kb import _domain_readiness
    one_signal = [DossierFact(id="1", claim="c", fact_class="signal", source_label="s")]
    three_grounded = [
        DossierFact(id=str(i), claim="c", fact_class="corporate", source_label="s")
        for i in range(3)
    ]
    assert 0.0 < _domain_readiness(one_signal) < _domain_readiness(three_grounded) <= 1.0
    # grounding alone lifts a single fact above its ungrounded equivalent
    one_grounded = [DossierFact(id="1", claim="c", fact_class="reference", source_label="s")]
    assert _domain_readiness(one_grounded) > _domain_readiness(one_signal)


def test_build_domains_sets_readiness():
    domains, _, _ = build_domains([_fact("wac_usd_monthly", "corporate", "675")])
    by = {d.domain: d for d in domains}
    assert by["pricing_and_access"].readiness > 0.0      # has a fact
    assert by["competitive"].readiness == 0.0            # empty


def test_domainview_to_dict_carries_readiness():
    domains, _, _ = build_domains([_fact("wac_usd_monthly", "corporate")])
    by = {d.domain: d.to_dict() for d in domains}
    assert "readiness" in by["pricing_and_access"]
    assert by["competitive"]["readiness"] == 0.0


def test_overall_readiness_priority_weighted():
    from services.dossier_kb import overall_readiness
    # a strong CRITICAL domain (competitive) lifts overall more than a strong
    # MEDIUM domain (disease_and_patient) with identical evidence.
    crit_domains = build_domains(
        [_fact("ma_deal", "corporate", str(i), f"c{i}") for i in range(5)])[0]
    med_domains = build_domains(
        [_fact("prevalence", "corporate", str(i), f"d{i}") for i in range(5)])[0]
    assert overall_readiness(crit_domains) > overall_readiness(med_domains)


def test_snapshot_to_dict_has_readiness():
    domains, cov, cnt = build_domains([_fact("wac_usd_monthly", "corporate")])
    snap = kb.DossierSnapshot(engagement_id="e", focal_asset="drug:x",
                              domains=domains, coverage_score=cov, fact_count=cnt)
    d = snap.to_dict()
    assert "readiness" in d
    assert 0.0 <= d["readiness"] <= 1.0


# ── H04: actionable gaps (text + fill method + importance) ─────────


def test_gaps_enriched_with_text_method_importance():
    domains, cov, cnt = build_domains([_fact("wac_usd_monthly", "corporate")])
    snap = kb.DossierSnapshot(engagement_id="e", focal_asset="drug:x",
                              domains=domains, coverage_score=cov, fact_count=cnt)
    comp = next(g for g in snap.gaps() if g["domain"] == "competitive")
    assert comp["text"]                      # human-readable: what's missing
    assert comp["method"]                    # how to fill it
    assert comp["importance"] == "high"      # competitive is a critical domain
    assert comp["thin"] is False


def test_gaps_default_excludes_thin_but_include_thin_surfaces_it():
    # pricing has 1 corporate fact → in_progress (thin), not an empty gap.
    domains, cov, cnt = build_domains([_fact("wac_usd_monthly", "corporate")])
    snap = kb.DossierSnapshot(engagement_id="e", focal_asset="drug:x",
                              domains=domains, coverage_score=cov, fact_count=cnt)
    assert "pricing_and_access" not in {g["domain"] for g in snap.gaps()}  # back-compat
    thin = snap.gaps(include_thin=True)
    thin_gap = next(g for g in thin if g["domain"] == "pricing_and_access")
    assert thin_gap["thin"] is True
    assert "Thin coverage" in thin_gap["text"]


def test_row_to_snapshot_recomputes_missing_readiness():
    # Pre-H05 snapshot JSON carried no per-domain readiness — recompute on read.
    from services.dossier_kb import _row_to_snapshot
    row = {
        "id": "snap1", "engagement_id": "e1", "focal_asset": "drug:x", "version": 1,
        "coverage_score": 0.25, "fact_count": 1, "assembled_by": "system",
        "assembled_at": None,
        "domains": [
            {"domain": "pricing_and_access", "priority": "critical", "state": "in_progress",
             "facts": [{"id": "f1", "claim": "c", "factClass": "corporate", "sourceLabel": "s"}]},
        ],
    }
    snap = _row_to_snapshot(row)
    by = {d.domain: d for d in snap.domains}
    assert by["pricing_and_access"].readiness > 0.0   # recomputed, not defaulted to 0


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
