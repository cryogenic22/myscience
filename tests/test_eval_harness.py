"""Track I — eval harness tests.

Covers:
  * pure scorers: system-vs-gold verdict + precision/recall per round type.
  * EvalHarness: load gold (joined to round payload) → compute the SYSTEM answer
    (planner dimensions / playbook routes / materiality ordering / cell
    groundedness) → score → aggregate accuracy/precision/recall/coverage →
    persist eval_runs / eval_results.
  * the /eval API end-to-end via create_app() TestClient (so a shadowed/dead
    route would be caught — the /entities greedy-route gotcha).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest


# ════════════════════════════════════════════════════════════════════
# Pure scorers
# ════════════════════════════════════════════════════════════════════

class TestScoreWhatMatters:
    def test_top_match_and_first_is_correct(self):
        from services.evaluation.scorers import score_what_matters, CORRECT
        s = score_what_matters(["efficacy", "safety"], ["efficacy", "safety", "mechanism"],
                               system_top="efficacy")
        assert s.verdict == CORRECT
        assert s.recall == 1.0
        assert s.covered is True

    def test_top_present_but_not_first_is_partial(self):
        from services.evaluation.scorers import score_what_matters, PARTIAL
        s = score_what_matters(["safety"], ["efficacy", "safety"], system_top="efficacy")
        assert s.verdict == PARTIAL

    def test_top_absent_is_miss(self):
        from services.evaluation.scorers import score_what_matters, MISS
        s = score_what_matters(["pricing_access"], ["efficacy", "safety"],
                               system_top="efficacy")
        assert s.verdict == MISS

    def test_no_system_dimensions_is_miss_uncovered(self):
        from services.evaluation.scorers import score_what_matters, MISS
        s = score_what_matters(["efficacy"], [])
        assert s.verdict == MISS
        assert s.covered is False


class TestScoreRouting:
    def test_exact_set_is_correct(self):
        from services.evaluation.scorers import score_routing, CORRECT
        gold = ["predicate:adverse_event", "predicate:safety_signal"]
        s = score_routing(gold, list(reversed(gold)))  # order-independent
        assert s.verdict == CORRECT
        assert s.precision == 1.0 and s.recall == 1.0

    def test_overlap_is_partial_with_pr(self):
        from services.evaluation.scorers import score_routing, PARTIAL
        s = score_routing(["predicate:adverse_event", "predicate:safety_signal"],
                          ["predicate:adverse_event"])
        assert s.verdict == PARTIAL
        assert s.recall == 0.5 and s.precision == 1.0

    def test_disjoint_is_miss(self):
        from services.evaluation.scorers import score_routing, MISS
        s = score_routing(["predicate:adverse_event"], ["predicate:wac_usd"])
        assert s.verdict == MISS
        assert s.recall == 0.0


class TestScoreSignalOrNoise:
    def test_ranked_first_is_correct(self):
        from services.evaluation.scorers import score_signal_or_noise, CORRECT
        s = score_signal_or_noise("sig-1", ["sig-1", "sig-2", "sig-3"])
        assert s.verdict == CORRECT

    def test_top_half_is_partial(self):
        from services.evaluation.scorers import score_signal_or_noise, PARTIAL
        # 4 candidates: ranks 1 (correct), 2 (top half → partial), 3-4 (miss)
        s = score_signal_or_noise("sig-2", ["sig-1", "sig-2", "sig-3", "sig-4"])
        assert s.verdict == PARTIAL

    def test_bottom_half_is_miss(self):
        from services.evaluation.scorers import score_signal_or_noise, MISS
        s = score_signal_or_noise("sig-3", ["sig-1", "sig-2", "sig-3"])
        assert s.verdict == MISS

    def test_not_in_ranking_is_miss(self):
        from services.evaluation.scorers import score_signal_or_noise, MISS
        s = score_signal_or_noise("sig-X", ["sig-1", "sig-2"])
        assert s.verdict == MISS


class TestScoreCritique:
    def test_correct_grade_grounded_is_correct(self):
        from services.evaluation.scorers import score_critique, CORRECT
        assert score_critique("correct", True).verdict == CORRECT

    def test_wrong_grade_grounded_is_miss(self):
        from services.evaluation.scorers import score_critique, MISS
        assert score_critique("wrong", True).verdict == MISS

    def test_wrong_grade_ungrounded_is_correct_self_correction(self):
        from services.evaluation.scorers import score_critique, CORRECT
        assert score_critique("wrong", False).verdict == CORRECT

    def test_partial_is_partial(self):
        from services.evaluation.scorers import score_critique, PARTIAL
        assert score_critique("partial", True).verdict == PARTIAL


# ════════════════════════════════════════════════════════════════════
# Fake DB simulating forge_eval_items + forge_rounds + eval_runs/_results
# ════════════════════════════════════════════════════════════════════

def _make_db(gold_items: list[dict]):
    """gold_items: list of {round_type, playbook_id, intent, answer, payload}.
    Returns (db, store). The DB serves the harness's joined gold read, the
    materiality config (defaults), facts groundedness, and the eval_runs/_results
    writes."""
    from services.auth import hash_password
    users = {
        "viewer@test.io": {"id": "uuid-viewer", "email": "viewer@test.io",
                           "password_hash": hash_password("demo"), "role": "viewer",
                           "is_active": True},
        "editor@test.io": {"id": "uuid-editor", "email": "editor@test.io",
                           "password_hash": hash_password("demo"), "role": "uploader",
                           "is_active": True},
    }
    # materialize gold rows with ids + timestamps
    gold = []
    for i, g in enumerate(gold_items):
        gold.append({
            "id": f"eval-{i}", "round_id": f"round-{i}",
            "session_id": "s1", "playbook_id": g["playbook_id"],
            "intent": g.get("intent", "compare"), "prompt": g.get("prompt", "q?"),
            "answer": g["answer"], "consensus_state": g.get("consensus_state", "labelled"),
            "round_type": g["round_type"], "payload": g.get("payload", {}),
            "created_at": datetime.now(timezone.utc),
        })
    grounded_facts = gold_items[0].get("_grounded_facts", set()) if gold_items else set()
    runs: list[dict] = []
    results: list[dict] = []
    seq = {"n": 0}

    def _coerce(v):
        return json.loads(v) if isinstance(v, str) else v

    def fetch_one(sql, params=None):
        s = (sql or "").lower()
        params = params or []
        if "from users" in s and params:
            if "lower(email)" in s or "where email" in s:
                return users.get(str(params[0]).lower())
            if "where id" in s:
                return next((u for u in users.values() if u["id"] == params[0]), None)
        # materiality active config → none (harness falls back to defaults)
        if "from materiality_weight_config" in s:
            return None
        # facts groundedness check (cell still asserted)
        if "from facts where id::text" in s and params:
            return {"x": 1} if str(params[0]) in grounded_facts else None
        # eval_runs insert
        if "insert into eval_runs" in s and "returning" in s:
            seq["n"] += 1
            row = {"id": f"run-{seq['n']}", "run_key": params[0],
                   "gold_count": params[1], "scored_count": params[2],
                   "metrics": _coerce(params[3]), "notes": params[4],
                   "created_by": params[5], "created_at": datetime.now(timezone.utc)}
            runs.append(row)
            return {"id": row["id"]}
        if "from eval_runs where run_key" in s and params:
            return next(({"id": r["id"]} for r in runs if r["run_key"] == params[0]), None)
        # latest summary
        if "from eval_runs order by created_at desc" in s:
            if not runs:
                return None
            r = runs[-1]
            return {"id": r["id"], "run_key": r["run_key"], "gold_count": r["gold_count"],
                    "scored_count": r["scored_count"], "metrics": r["metrics"],
                    "notes": r["notes"], "created_at": r["created_at"]}
        # flagged backlog count
        if "count(*) as n from forge_eval_items" in s and "flagged" in s and "group by" not in s:
            return {"n": sum(1 for g in gold if g["consensus_state"] == "flagged")}
        return None

    def fetch_all(sql, params=None):
        s = (sql or "").lower()
        params = params or []
        # the harness's joined gold read
        if "from forge_eval_items e" in s and "join forge_rounds r" in s:
            out = list(gold)
            if "e.playbook_id = %s" in s and params:
                out = [g for g in out if g["playbook_id"] == params[0]]
            return out
        # flagged backlog by playbook
        if "from forge_eval_items" in s and "flagged" in s and "group by" in s:
            from collections import Counter
            c = Counter(g["playbook_id"] for g in gold if g["consensus_state"] == "flagged")
            return [{"playbook_id": k, "n": v} for k, v in c.items()]
        return []

    def execute(sql, params=None):
        s = (sql or "").lower()
        params = params or []
        if "insert into eval_results" in s and params:
            results.append({"run_id": params[0], "eval_item_id": params[1],
                            "round_type": params[2], "playbook_id": params[3],
                            "verdict": params[4], "precision": params[5],
                            "recall": params[6], "detail": _coerce(params[7])})
        return None

    db = MagicMock()
    db.fetch_one.side_effect = fetch_one
    db.fetch_all.side_effect = fetch_all
    db.execute.side_effect = execute
    return db, {"runs": runs, "results": results, "gold": gold}


# ════════════════════════════════════════════════════════════════════
# EvalHarness — compute system answer + score + aggregate + persist
# ════════════════════════════════════════════════════════════════════

class TestHarness:
    def test_what_matters_scored_against_planner_dimensions(self):
        from services.evaluation import EvalHarness
        from services.domain_intelligence.playbook import get_playbook_registry
        # gold top = 'efficacy' (the compare playbook's highest-weight dim) →
        # the planner ranks efficacy first → CORRECT.
        gold = [{"round_type": "what_matters", "playbook_id": "compare.drug_x_drug",
                 "intent": "compare",
                 "answer": {"ranking": ["efficacy", "safety"]},
                 "payload": {"entities": [{"entity_type": "drug"}, {"entity_type": "drug"}]}}]
        db, store = _make_db(gold)
        h = EvalHarness(registry=get_playbook_registry())
        summary = h.run(db, persist=True)
        assert summary.scored_count == 1
        rt = summary.metrics["by_round_type"]["what_matters"]
        assert rt["correct"] == 1
        assert rt["accuracy"] == 1.0
        assert rt["coverage"] == 1.0
        # persisted
        assert len(store["runs"]) == 1
        assert len(store["results"]) == 1
        assert store["results"][0]["verdict"] == "correct"

    def test_routing_set_precision_recall(self):
        from services.evaluation import EvalHarness
        from services.domain_intelligence.playbook import get_playbook_registry
        # gold routes match the dossier.drug 'mechanism' routes exactly → correct.
        reg = get_playbook_registry()
        pb = reg.get("dossier.drug")
        mech = next(d for d in pb.dimensions if d.key == "mechanism")
        gold_routes = [f"{r.kind}:{r.value}" for r in mech.routes]
        gold = [{"round_type": "routing", "playbook_id": "dossier.drug", "intent": "dossier",
                 "answer": {"selected": gold_routes},
                 "payload": {"dimension": {"key": "mechanism"}}}]
        db, _ = _make_db(gold)
        h = EvalHarness(registry=reg)
        summary = h.run(db, persist=False)
        rt = summary.metrics["by_round_type"]["routing"]
        assert rt["correct"] == 1
        assert rt["precision"] == 1.0 and rt["recall"] == 1.0

    def test_signal_or_noise_ranked_by_materiality(self):
        from services.evaluation import EvalHarness
        # high-impact clinical signal should out-rank a low-impact financial one;
        # gold picks the clinical one → CORRECT.
        sigs = [
            {"signal_id": "sig-clin", "kbq_tags": ["clinical"], "impact_tier": "high"},
            {"signal_id": "sig-fin", "kbq_tags": ["financial"], "impact_tier": "low"},
            {"signal_id": "sig-prod", "kbq_tags": ["product"], "impact_tier": "low"},
        ]
        gold = [{"round_type": "signal_or_noise", "playbook_id": "materiality.signal_triage",
                 "intent": "materiality",
                 "answer": {"signal_id": "sig-clin", "reason": "clinical_readout"},
                 "payload": {"signals": sigs}}]
        db, _ = _make_db(gold)
        summary = EvalHarness().run(db, persist=False)
        rt = summary.metrics["by_round_type"]["signal_or_noise"]
        assert rt["correct"] == 1

    def test_critique_grounded_correct(self):
        from services.evaluation import EvalHarness
        # gold 'correct' on a cell whose fact still exists → CORRECT.
        gold = [{"round_type": "critique", "playbook_id": "critique.cell_accuracy",
                 "intent": "critique",
                 "answer": {"grade": "correct", "fact_id": "fact-1"},
                 "payload": {"cell": {"fact_id": "fact-1"}},
                 "_grounded_facts": {"fact-1"}}]
        db, _ = _make_db(gold)
        summary = EvalHarness().run(db, persist=False)
        rt = summary.metrics["by_round_type"]["critique"]
        assert rt["correct"] == 1

    def test_aggregates_overall_and_per_playbook(self):
        from services.evaluation import EvalHarness
        from services.domain_intelligence.playbook import get_playbook_registry
        gold = [
            {"round_type": "what_matters", "playbook_id": "compare.drug_x_drug",
             "intent": "compare", "answer": {"ranking": ["efficacy"]},
             "payload": {"entities": [{"entity_type": "drug"}, {"entity_type": "drug"}]}},
            {"round_type": "what_matters", "playbook_id": "compare.drug_x_drug",
             "intent": "compare", "answer": {"ranking": ["pricing_access"]},  # not top → partial
             "payload": {"entities": [{"entity_type": "drug"}, {"entity_type": "drug"}]}},
        ]
        db, _ = _make_db(gold)
        summary = EvalHarness(registry=get_playbook_registry()).run(db, persist=False)
        ov = summary.metrics["overall"]
        assert ov["n"] == 2
        assert ov["correct"] == 1 and ov["partial"] == 1
        assert ov["accuracy"] == 0.75  # (1.0 + 0.5) / 2
        assert "compare.drug_x_drug" in summary.metrics["by_playbook"]

    def test_empty_gold_set_is_graceful(self):
        from services.evaluation import EvalHarness
        db, store = _make_db([])
        summary = EvalHarness().run(db, persist=True)
        assert summary.gold_count == 0 and summary.scored_count == 0
        assert summary.metrics["overall"]["n"] == 0
        assert len(store["runs"]) == 1


# ════════════════════════════════════════════════════════════════════
# API — via create_app() TestClient (catches shadowed/dead routes)
# ════════════════════════════════════════════════════════════════════

def _client(db):
    from fastapi.testclient import TestClient
    from api.app import create_app
    from api.deps import get_db
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def _login(client, email):
    r = client.post("/auth/login", json={"email": email, "password": "demo"})
    return r.json().get("access_token", "") if r.status_code == 200 else ""


def _hdr(tok):
    return {"Authorization": f"Bearer {tok}"} if tok else {}


def test_routes_registered_not_shadowed():
    from api.app import create_app
    app = create_app()
    paths = {getattr(r, "path", "") for r in app.routes}
    assert "/eval/summary" in paths
    assert "/eval/run" in paths


def test_router_prefix_is_own():
    from api.routes import eval as r
    assert r.router.prefix == "/eval"


class TestApi:
    def test_summary_before_any_run(self):
        db, _ = _make_db([])
        c = _client(db)
        vw = _hdr(_login(c, "viewer@test.io"))
        r = c.get("/eval/summary", headers=vw)
        assert r.status_code == 200, r.text
        assert r.json()["has_run"] is False
        assert "flagged_backlog" in r.json()

    def test_run_then_summary(self):
        from services.domain_intelligence.playbook import get_playbook_registry
        gold = [{"round_type": "what_matters", "playbook_id": "compare.drug_x_drug",
                 "intent": "compare", "answer": {"ranking": ["efficacy"]},
                 "payload": {"entities": [{"entity_type": "drug"}, {"entity_type": "drug"}]}}]
        db, store = _make_db(gold)
        c = _client(db)
        ed = _hdr(_login(c, "editor@test.io"))
        r = c.post("/eval/run", headers=ed, json={})
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["scored_count"] == 1
        assert body["metrics"]["overall"]["n"] == 1
        # summary now reflects the run
        r = c.get("/eval/summary", headers=ed)
        assert r.status_code == 200
        assert r.json()["has_run"] is True

    def test_viewer_cannot_run(self):
        db, _ = _make_db([])
        c = _client(db)
        vw = _hdr(_login(c, "viewer@test.io"))
        r = c.post("/eval/run", headers=vw, json={})
        assert r.status_code == 403
