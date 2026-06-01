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


def _snapshot_with(facts=None, signals=None, related=None, focal="drug:x") -> DossierSnapshot:
    domains, cov, cnt = build_domains(facts or [], signals, None, related)
    return DossierSnapshot(
        engagement_id="e1", focal_asset=focal, domains=domains,
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


def test_signal_scenarios_skip_wargame_specific():
    # PB-H07: a 'strategic' kbq signal lands in wargame_specific (the catch-all,
    # where routine recalls/shortages collect) and must NOT spawn a scenario; a
    # pricing signal (a substantive critical domain) does.
    signals = [
        {"signal_id": "s_noise", "headline": "Routine recall", "kbq_tag": "strategic", "ts": None},
        {"signal_id": "s_real", "headline": "Novo cuts WAC", "kbq_tag": "pricing_access", "ts": None},
    ]
    out = derive_scenarios(_snapshot_with(signals=signals))
    cited = {e.fact_id for s in out for e in s.evidence}
    assert "s_real" in cited          # pricing signal → scenario
    assert "s_noise" not in cited     # wargame_specific signal → suppressed


def test_scenarios_capped_and_sorted_by_prior():
    related = [{"id": f"d{i}", "type": "drug", "name": f"rival{i}",
                "relation": "COMPETES_WITH", "edge_count": i} for i in range(8)]
    out = derive_scenarios(_snapshot_with(related=related))
    assert len(out) <= 6
    priors = [s.prior_prob for s in out]
    assert priors == sorted(priors, reverse=True)


def test_scenario_not_blocked_by_unrelated_domain_gap():
    # PB-H10c: a competitive scenario draws evidence from the competitive domain.
    # An empty pricing_and_access (a high-importance gap) is a CONTEXT gap in a
    # different domain — it must NOT hard-block the competitive scenario (the
    # prior behaviour blocked ALL scenarios on every high gap → dead-end).
    related = [{"id": "d2", "type": "drug", "name": "tirzepatide",
                "relation": "COMPETES_WITH", "edge_count": 4}]
    out = derive_scenarios(_snapshot_with(related=related))
    comp = next(s for s in out if "tirzepatide" in s.name)
    assert comp.source_domains == ["competitive"]
    assert comp.blocked_by_gaps == []          # own-evidence → playable


def test_team_moves_carry_bounded_impact_vectors():
    # PB-H11: each team move carries an illustrative directional impact vector
    # keyed by team, bounded to [-1, 1], with the acting team positive.
    related = [{"id": "d2", "type": "drug", "name": "tirzepatide",
                "relation": "COMPETES_WITH", "edge_count": 4}]
    s = next(x for x in derive_scenarios(_snapshot_with(related=related))
             if "tirzepatide" in x.name)
    assert s.team_moves
    for m in s.team_moves:
        assert m.impact, f"move by {m.team} must carry an impact vector"
        assert all(-1.0 <= v <= 1.0 for v in m.impact.values())
        # the acting team is helped by its own move.
        assert m.impact.get(m.team, 0) > 0
    # round-trips to the frontend shape.
    d = s.to_dict()
    assert "impact" in d["teamMoves"][0]


def test_self_referential_competitor_is_suppressed():
    # PB-H10c: a "GLP-1 analogue - semaglutide" rival when the focal asset IS
    # semaglutide is a self-match and must not spawn a competitive scenario.
    related = [
        {"id": "self", "type": "drug", "name": "GLP-1 analogue - semaglutide",
         "relation": "COMPETES_WITH", "edge_count": 2},
        {"id": "real", "type": "drug", "name": "tirzepatide",
         "relation": "COMPETES_WITH", "edge_count": 3},
    ]
    out = derive_scenarios(_snapshot_with(related=related, focal="drug:semaglutide"))
    names = " ".join(s.name for s in out)
    assert "tirzepatide" in names              # real rival kept
    assert "semaglutide" not in names          # self-match suppressed


def test_empty_dossier_yields_no_scenarios():
    out = derive_scenarios(_snapshot_with())
    assert out == []


# ── Pure: team moves + decision options (PB-H10/H11) ────────────────


def test_competitive_scenario_has_grounded_team_moves():
    related = [{"id": "d2", "type": "drug", "name": "tirzepatide",
                "relation": "COMPETES_WITH", "edge_count": 4}]
    s = next(x for x in derive_scenarios(_snapshot_with(related=related))
             if "tirzepatide" in x.name)
    # three actors, each with a move + rationale.
    assert len(s.team_moves) == 3
    teams = {m.team for m in s.team_moves}
    assert "tirzepatide" in teams          # the rival, by name
    assert "x" in teams                    # the focal asset (drug:x → x)
    assert all(m.move and m.rationale for m in s.team_moves)
    # moves are scenario-specific, not generic boilerplate.
    assert any("tirzepatide" in m.move for m in s.team_moves)


def test_competitive_scenario_options_exactly_one_recommended_no_fabricated_npv():
    related = [{"id": "d2", "type": "drug", "name": "tirzepatide",
                "relation": "COMPETES_WITH", "edge_count": 4}]
    s = next(x for x in derive_scenarios(_snapshot_with(related=related))
             if "tirzepatide" in x.name)
    assert len(s.decision_options) == 3
    assert sum(1 for o in s.decision_options if o.recommended) == 1
    # honest: no fabricated NPV figures (value model is a later loop).
    assert all(o.npv_5y_dkk_bn is None for o in s.decision_options)
    # high prior (4 edges → 0.46) → defend, not margin-harvest.
    rec = next(o for o in s.decision_options if o.recommended)
    assert rec.id == "defend-differentiate"


def test_low_threat_competitive_recommends_segment_defend():
    related = [{"id": "d3", "type": "drug", "name": "minor", "relation": "COMPETES_WITH",
                "edge_count": 0}]  # prior 0.3 (< 0.4) → margin focus
    s = next(x for x in derive_scenarios(_snapshot_with(related=related))
             if "minor" in x.name)
    rec = next(o for o in s.decision_options if o.recommended)
    assert rec.id == "segment-defend"


def test_signal_scenario_has_moves_and_options():
    signals = [{"signal_id": "s1", "headline": "Novo cuts WAC 5%",
                "kbq_tag": "pricing_access", "ts": None}]
    s = next(x for x in derive_scenarios(_snapshot_with(signals=signals))
             if "Novo cuts WAC" in x.name)
    assert len(s.team_moves) == 3
    assert len(s.decision_options) == 3
    assert sum(1 for o in s.decision_options if o.recommended) == 1
    # the signal headline is woven into the rational-interest framing.
    assert any("Novo cuts WAC" in m.rationale for m in s.team_moves)


def test_team_moves_and_options_survive_to_dict_round_trip():
    related = [{"id": "d2", "type": "drug", "name": "tirzepatide",
                "relation": "COMPETES_WITH", "edge_count": 4}]
    d = next(x for x in derive_scenarios(_snapshot_with(related=related))
             if "tirzepatide" in x.name).to_dict()
    assert len(d["teamMoves"]) == 3 and len(d["decisionOptions"]) == 3
    assert set(d["teamMoves"][0]) == {"team", "move", "rationale", "impact"}
    assert set(d["decisionOptions"][0]) == {"id", "statement", "rationale", "npv5yDkkBn", "recommended"}


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
