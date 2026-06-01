"""PB-H09 — Scenarios as first-class probabilistic objects grounded in the dossier.

Two layers:
  1. PURE: derivation from a DossierSnapshot, the prior heuristic, serialization
     to the frontend Scenario shape. No DB — the testable keystone.
  2. DB-backed: persist (archive prior batch + insert) + list round-trip over a
     fake db, mirroring the dossier_kb fake-db pattern.
"""
from __future__ import annotations

import pytest

from services import scenarios as sc
from services.scenarios import (
    Scenario,
    ScenarioEvidence,
    derive_scenarios,
)
from services.dossier_kb import DossierSnapshot, build_domains


def _snapshot_with(facts=None, signals=None, related=None) -> DossierSnapshot:
    domains, cov, cnt = build_domains(facts or [], signals, None, related)
    return DossierSnapshot(
        engagement_id="e1", focal_asset="drug:x", domains=domains,
        coverage_score=cov, fact_count=cnt, id="snap1",
    )


# ── Pure: derivation ───────────────────────────────────────────────


def test_derive_competitive_scenario_cites_fact():
    related = [{"id": "d2", "type": "drug", "name": "tirzepatide",
                "relation": "COMPETES_WITH", "edge_count": 4}]
    out = derive_scenarios(_snapshot_with(related=related))
    assert len(out) >= 1
    s = next(x for x in out if "tirzepatide" in x.name)
    assert s.evidence and s.evidence[0].fact_id == "d2"     # provenance
    assert s.evidence[0].predicate == "competitive_relation"
    assert 0.1 <= s.prior_prob <= 0.7


def test_derive_signal_scenario_from_critical_domain():
    # a pricing signal lands in pricing_and_access (critical) → a signal scenario
    signals = [{"signal_id": "s1", "headline": "Novo cuts WAC 5%",
                "kbq_tag": "pricing_access", "ts": None}]
    out = derive_scenarios(_snapshot_with(signals=signals))
    sig = next(s for s in out if "Novo cuts WAC" in s.name)
    assert sig.evidence[0].fact_id == "s1"
    assert sig.evidence[0].predicate == "signal"


def test_scenarios_capped_and_sorted_by_prior():
    related = [{"id": f"d{i}", "type": "drug", "name": f"rival{i}",
                "relation": "COMPETES_WITH", "edge_count": i} for i in range(8)]
    out = derive_scenarios(_snapshot_with(related=related))
    assert len(out) <= 6
    priors = [s.prior_prob for s in out]
    assert priors == sorted(priors, reverse=True)


def test_blocked_by_gaps_inherits_high_importance_gaps():
    # competitive fact present, but pricing_and_access (critical) is empty → a
    # high-importance gap that blocks confident scenario execution.
    related = [{"id": "d2", "type": "drug", "name": "tirzepatide",
                "relation": "COMPETES_WITH", "edge_count": 4}]
    out = derive_scenarios(_snapshot_with(related=related))
    assert out[0].blocked_by_gaps
    assert any("payer & access" in g for g in out[0].blocked_by_gaps)


def test_empty_dossier_yields_no_scenarios():
    out = derive_scenarios(_snapshot_with())
    assert out == []


# ── Pure: prior heuristic + serialization ──────────────────────────


def test_prior_heuristic_bounds_and_grounding():
    from services.scenarios import _prior_from_fact
    assert _prior_from_fact("x", "signal") == 0.3
    assert _prior_from_fact("x", "corporate") == 0.4               # +0.10 grounded
    assert _prior_from_fact("rival (4 edges)", "inferred") == pytest.approx(0.46)
    # grounded + 5-edge cap = 0.3 + 0.10 + 0.20, still within [0.1, 0.7]
    assert _prior_from_fact("rival (99 edges)", "corporate") == pytest.approx(0.6)


def test_to_dict_matches_frontend_shape():
    s = Scenario(name="X", trigger_event="ev", prior_prob=0.42,
                 evidence=[ScenarioEvidence(fact_id="f1", predicate="signal")])
    d = s.to_dict()
    assert d["name"] == "X"
    assert d["trigger"] == {"event": "ev", "date": None,
                            "evidence": [{"factId": "f1", "predicate": "signal"}]}
    assert d["probability"] == 0.42
    assert d["probabilityCurrent"] is None
    assert d["teamMoves"] == [] and d["decisionOptions"] == []
    assert d["blockedByGaps"] == []


def test_to_dict_decision_option_camelcase():
    from services.scenarios import DecisionOption
    s = Scenario(name="X", trigger_event="e", prior_prob=0.3, current_prob=0.55,
                 decision_options=[DecisionOption(id="o1", statement="hold",
                                                  rationale="why", npv_5y_dkk_bn=4.7,
                                                  recommended=True)])
    d = s.to_dict()
    assert d["probabilityCurrent"] == 0.55
    assert d["decisionOptions"][0] == {
        "id": "o1", "statement": "hold", "rationale": "why",
        "npv5yDkkBn": 4.7, "recommended": True,
    }


# ── DB-backed: fake db persist + list ──────────────────────────────


class _FakeScenarioDB:
    """Models scenarios insert / archive / list."""

    def __init__(self):
        self.rows: list[dict] = []
        self._idc = 0

    def execute(self, sql, params=None):
        if "UPDATE scenarios SET is_archived" in sql:
            eng = params[0]
            for r in self.rows:
                if r["engagement_id"] == eng:
                    r["is_archived"] = True

    def fetch_one(self, sql, params=None):
        if "INSERT INTO scenarios" in sql:
            self._idc += 1
            rid = f"sc-{self._idc}"
            row = dict(params)
            row["id"] = rid
            row["is_archived"] = False
            row["created_at"] = None
            self.rows.append(row)
            return {"id": rid, "created_at": None}
        return None

    def fetch_all(self, sql, params=None):
        if "FROM scenarios" in sql:
            eng = params[0]
            out = [r for r in self.rows
                   if r["engagement_id"] == eng and not r.get("is_archived")]
            out.sort(key=lambda r: r["prior_prob"], reverse=True)
            return out
        return []


def test_persist_and_list_round_trip():
    db = _FakeScenarioDB()
    related = [{"id": "d2", "type": "drug", "name": "tirzepatide",
                "relation": "COMPETES_WITH", "edge_count": 4}]
    derived = derive_scenarios(_snapshot_with(related=related))
    for s in derived:
        s.dossier_snapshot_id = "snap1"
    sc.persist_scenarios(db, "e1", derived)
    listed = sc.list_scenarios(db, "e1")
    assert len(listed) == len(derived)
    assert listed[0].name == derived[0].name
    assert listed[0].evidence[0].fact_id == "d2"        # JSONB round-trips
    assert listed[0].prior_prob == derived[0].prior_prob


def test_persist_archives_prior_batch():
    db = _FakeScenarioDB()
    snap = _snapshot_with(related=[{"id": "d2", "type": "drug", "name": "a",
                                    "relation": "COMPETES_WITH", "edge_count": 1}])
    sc.persist_scenarios(db, "e1", derive_scenarios(snap))
    first = sc.list_scenarios(db, "e1")
    sc.persist_scenarios(db, "e1", derive_scenarios(snap))   # re-assemble
    second = sc.list_scenarios(db, "e1")
    # prior batch archived → list shows only the fresh batch, not doubled
    assert len(second) == len(first)
