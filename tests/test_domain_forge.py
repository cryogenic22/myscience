"""DF-1 + DF-2 — Domain Forge tests.

Covers:
  * prompt generation FROM real (here: injected) DB entities — never fabricates.
  * the round engine: create round → submit constrained answer → a dimension is
    promoted into a playbook version (via the reused PlaybookAuthoringService)
    AND a gold eval item is persisted (DF-1).
  * DF-2: 2 agreeing SMEs promote a dimension; a lone / dissenting answer is
    FLAGGED (not applied); the score is gated on validation + consensus.
  * the /forge API end-to-end via create_app() TestClient (so a shadowed/dead
    route would be caught — the /entities greedy-route gotcha).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest


# ════════════════════════════════════════════════════════════════════
# Prompt generation
# ════════════════════════════════════════════════════════════════════

_TWO_DRUGS = [
    {"entity_id": "d-sema", "entity_type": "drug", "label": "semaglutide"},
    {"entity_id": "d-tirz", "entity_type": "drug", "label": "tirzepatide"},
]


class TestPromptGeneration:
    def test_round_grounded_in_supplied_entities(self):
        from services.domain_forge.prompts import generate_what_matters_round
        spec = generate_what_matters_round(MagicMock(), entities=_TWO_DRUGS)
        assert spec["round_type"] == "what_matters"
        assert "semaglutide" in spec["prompt"] and "tirzepatide" in spec["prompt"]
        keys = {o["key"] for o in spec["payload"]["options"]}
        assert "mechanism" in keys and "efficacy" in keys
        # every option carries a routable route (no free text)
        for o in spec["payload"]["options"]:
            assert o["routes"]

    def test_too_few_entities_raises_not_fabricates(self):
        from services.domain_forge.prompts import generate_what_matters_round
        with pytest.raises(ValueError):
            generate_what_matters_round(MagicMock(), entities=_TWO_DRUGS[:1])

    def test_options_map_to_validatable_predicates(self):
        # Every option's predicate route must validate against the live ledger
        # vocabulary (reuse) — so an SME pick is always plannable.
        from services.domain_forge.prompts import DIMENSION_OPTIONS
        from services.domain_intelligence.playbook import Route
        from services.domain_intelligence.validation import validate_route
        for o in DIMENSION_OPTIONS:
            for spec in o["routes"]:
                assert validate_route(Route.parse(spec)) is None, (o["key"], spec)


# ════════════════════════════════════════════════════════════════════
# Fake DB simulating forge_* + playbooks + users
# ════════════════════════════════════════════════════════════════════

def _make_db():
    from services.auth import hash_password
    users = {
        "viewer@test.io": {"id": "uuid-viewer", "email": "viewer@test.io",
                           "password_hash": hash_password("demo"), "role": "viewer",
                           "is_active": True},
        "editor@test.io": {"id": "uuid-editor", "email": "editor@test.io",
                           "password_hash": hash_password("demo"), "role": "uploader",
                           "is_active": True},
    }
    rounds: dict[str, dict] = {}
    evals: list[dict] = []
    scores: dict[str, dict] = {}        # keyed by eval_item_id (unique)
    playbooks: dict[str, dict] = {}
    versions: list[dict] = []
    seq = {"n": 0}

    def _nid(prefix):
        seq["n"] += 1
        return f"{prefix}-{seq['n']}"

    def _coerce(v):
        return json.loads(v) if isinstance(v, str) else v

    def fetch_one(sql, params=None):
        s = (sql or "").lower()
        params = params or []
        # users (auth)
        if "from users" in s and params:
            if "lower(email)" in s or "where email" in s:
                return users.get(str(params[0]).lower())
            if "where id" in s:
                return next((u for u in users.values() if u["id"] == params[0]), None)
        # rich drugs for prompt gen — return two fixed drugs
        if "from drugs" in s and "count(f.id)" in s:
            return None  # this path uses fetch_all
        # critique cell (DF-5 ④): a real machine-generated fact
        if "from facts f" in s and "object_value" in s and params:
            return {
                "fact_id": "fact-1", "predicate": params[0],
                "object_value": {"emitter": "mechanisms", "mechanism": "GLP-1 receptor agonist"},
                "fact_class": "reference", "entity_id": "d-sema",
                "entity_label": "semaglutide",
            }
        # forge_rounds insert
        if "insert into forge_rounds" in s and "returning" in s:
            rid = _nid("round")
            row = {
                "id": rid, "session_id": params[0], "round_type": params[1],
                "playbook_id": params[2], "intent": params[3], "prompt": params[4],
                "payload": _coerce(params[5]), "status": "open",
                "created_by": params[6], "created_at": datetime.now(timezone.utc),
                "answered_at": None,
            }
            rounds[rid] = row
            return dict(row)
        if "from forge_rounds where id" in s and params:
            return rounds.get(params[0])
        # forge_eval_items insert
        if "insert into forge_eval_items" in s and "returning" in s:
            eid = _nid("eval")
            row = {
                "id": eid, "round_id": params[0], "session_id": params[1],
                "playbook_id": params[2], "intent": params[3], "prompt": params[4],
                "answer": _coerce(params[5]), "sme_id": params[6],
                "validation": _coerce(params[7]), "consensus_state": params[8],
                "promoted_version": params[9], "created_at": datetime.now(timezone.utc),
            }
            evals.append(row)
            return dict(row)
        # forge_scores insert
        if "insert into forge_scores" in s and "returning" in s:
            ev_id = params[0]
            if ev_id in scores:
                return None  # ON CONFLICT DO NOTHING
            row = {
                "id": _nid("score"), "eval_item_id": ev_id, "session_id": params[1],
                "sme_id": params[2], "points": params[3], "reason": params[4],
                "created_at": datetime.now(timezone.utc),
            }
            scores[ev_id] = row
            return dict(row)
        if "from forge_scores where eval_item_id" in s and params:
            return scores.get(params[0])
        # session summary
        if "from forge_rounds where session_id" in s and "count(*)" in s:
            sid = params[0]
            rs = [r for r in rounds.values() if r["session_id"] == sid]
            return {"n": len(rs), "answered": sum(1 for r in rs if r["status"] == "answered")}
        if "from forge_eval_items where session_id" in s and "count(*)" in s:
            sid = params[0]
            es = [e for e in evals if e["session_id"] == sid]
            return {"n": len(es), "promoted": sum(1 for e in es if e["consensus_state"] == "promoted")}
        if "sum(points)" in s and params:
            sid = params[0]
            return {"total": sum(sc["points"] for sc in scores.values() if sc["session_id"] == sid)}
        # playbooks (authoring reuse)
        if "from playbooks where id" in s and params:
            return playbooks.get(params[0])
        if "insert into playbooks" in s and "returning" in s and params:
            row = {
                "id": params[0], "pack": params[1], "trigger": _coerce(params[2]),
                "dimensions": _coerce(params[3]), "synthesis": _coerce(params[4]),
                "active": True, "version": 1, "author": params[5], "tenant_scope": None,
                "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc),
            }
            playbooks[params[0]] = row
            return dict(row)
        if "update playbooks set" in s and "returning" in s and params:
            pid = params[-1]
            row = playbooks.get(pid)
            if not row:
                return None
            row["pack"] = params[0]; row["trigger"] = _coerce(params[1])
            row["dimensions"] = _coerce(params[2]); row["synthesis"] = _coerce(params[3])
            row["version"] = params[4]; row["author"] = params[5]
            row["updated_at"] = datetime.now(timezone.utc)
            return dict(row)
        if "from playbook_versions where playbook_id" in s and "and version" in s and params:
            return next(({"snapshot": v["snapshot"]} for v in versions
                         if v["playbook_id"] == params[0] and v["version"] == params[1]), None)
        return None

    def fetch_all(sql, params=None):
        s = (sql or "").lower()
        params = params or []
        if "from drugs" in s and "count(f.id)" in s:
            return [
                {"entity_id": "d-sema", "label": "semaglutide", "nf": 1023},
                {"entity_id": "d-tirz", "label": "tirzepatide", "nf": 431},
            ]
        # candidate signals for signal_or_noise (DF-5 ②)
        if "from signals" in s and "headline" in s and "impact_tier" in s:
            return [
                {"signal_id": "sig-1", "headline": "Phase 3 primary endpoint missed",
                 "summary": "REDEFINE-2 missed", "primary_entity_name": "CagriSema",
                 "primary_entity_type": "drug", "kbq_tags": ["clinical"],
                 "impact_tier": "high", "confidence_tier": "high",
                 "created_at": datetime.now(timezone.utc)},
                {"signal_id": "sig-2", "headline": "Boxed warning added",
                 "summary": "Thyroid C-cell tumors", "primary_entity_name": "liraglutide",
                 "primary_entity_type": "drug", "kbq_tags": ["clinical"],
                 "impact_tier": "high", "confidence_tier": "med",
                 "created_at": datetime.now(timezone.utc)},
                {"signal_id": "sig-3", "headline": "Quarterly IR call scheduled",
                 "summary": "Routine", "primary_entity_name": "Novo Nordisk",
                 "primary_entity_type": "company", "kbq_tags": ["financial"],
                 "impact_tier": "low", "confidence_tier": "low",
                 "created_at": datetime.now(timezone.utc)},
            ]
        # routing consensus (DF-5 ③): distinct SMEs by stored consensus_key
        if "distinct sme_id from forge_eval_items" in s and "consensus_key" in s:
            pid, ckey = params[0], params[1]
            return [{"sme_id": e["sme_id"]} for e in evals
                    if e["playbook_id"] == pid
                    and e["answer"].get("consensus_key") == ckey]
        if "distinct sme_id from forge_eval_items" in s and "ranking" in s and "->'ranking'->>0" in s:
            pid, key = params[0], params[1]
            return [{"sme_id": e["sme_id"]} for e in evals
                    if e["playbook_id"] == pid
                    and (e["answer"].get("ranking") or [None])[0] == key]
        if "distinct sme_id from forge_eval_items" in s and "selected" in s:
            pid, key = params[0], params[1]
            return [{"sme_id": e["sme_id"]} for e in evals
                    if e["playbook_id"] == pid and not e["answer"].get("ranking")
                    and (e["answer"].get("selected") or [None])[0] == key]
        if "from forge_eval_items" in s:
            out = list(evals)
            # crude filters
            if "playbook_id = %s" in s and "session_id = %s" in s:
                out = [e for e in out if e["playbook_id"] == params[0] and e["session_id"] == params[1]]
            elif "playbook_id = %s" in s:
                out = [e for e in out if e["playbook_id"] == params[0]]
            elif "session_id = %s" in s:
                out = [e for e in out if e["session_id"] == params[0]]
            return sorted(out, key=lambda e: e["created_at"], reverse=True)
        if "from playbooks order by id" in s:
            return sorted(playbooks.values(), key=lambda r: r["id"])
        if "from playbooks where active" in s:
            return [r for r in playbooks.values() if r.get("active", True)]
        if "from playbook_versions where playbook_id" in s and params:
            out = [v for v in versions if v["playbook_id"] == params[0]]
            out.sort(key=lambda v: v["version"], reverse=True)
            return out
        return []

    def execute(sql, params=None):
        s = (sql or "").lower()
        params = params or []
        if "insert into playbook_versions" in s and params:
            versions.append({
                "playbook_id": params[0], "version": params[1], "action": params[2],
                "snapshot": _coerce(params[3]), "diff": _coerce(params[4]),
                "author": params[5], "note": params[6], "rolled_back_from": params[7],
                "created_at": datetime.now(timezone.utc),
            })
        elif "update forge_rounds set status='answered'" in s and params:
            r = rounds.get(params[0])
            if r:
                r["status"] = "answered"; r["answered_at"] = datetime.now(timezone.utc)
        elif "delete from playbooks where id" in s and params:
            playbooks.pop(params[0], None)
        return None

    db = MagicMock()
    db.fetch_one.side_effect = fetch_one
    db.fetch_all.side_effect = fetch_all
    db.execute.side_effect = execute
    return db, {"rounds": rounds, "evals": evals, "scores": scores,
                "playbooks": playbooks, "versions": versions}


# ════════════════════════════════════════════════════════════════════
# DF-1: round engine — create → answer → dimension + eval item persist
# ════════════════════════════════════════════════════════════════════

class TestRoundEngineDF1:
    def test_create_round_persists_grounded_prompt(self):
        from services.domain_forge import ForgeEngine
        db, store = _make_db()
        rnd = ForgeEngine().create_round(db, session_id="s1")
        assert rnd["status"] == "open"
        assert "semaglutide" in rnd["prompt"]
        assert store["rounds"][rnd["id"]]["round_type"] == "what_matters"

    def test_answer_persists_eval_item_and_score(self):
        from services.domain_forge import ForgeEngine
        db, store = _make_db()
        eng = ForgeEngine()
        rnd = eng.create_round(db, session_id="s1")
        res = eng.submit_answer(db, rnd["id"], {"ranking": ["mechanism"], "selected": ["mechanism"]},
                                sme_id="sme-alice")
        # a gold eval item persisted
        assert len(store["evals"]) == 1
        assert store["evals"][0]["prompt"] == rnd["prompt"]
        assert res["validation"]["valid"] is True
        # a score row persisted
        assert len(store["scores"]) == 1
        assert res["score"]["points"] >= 3
        # round is now answered (one play)
        assert store["rounds"][rnd["id"]]["status"] == "answered"

    def test_resubmit_blocked(self):
        from services.domain_forge import ForgeEngine, RoundAlreadyAnswered
        db, _ = _make_db()
        eng = ForgeEngine()
        rnd = eng.create_round(db, session_id="s1")
        eng.submit_answer(db, rnd["id"], {"ranking": ["mechanism"]}, sme_id="a")
        with pytest.raises(RoundAlreadyAnswered):
            eng.submit_answer(db, rnd["id"], {"ranking": ["mechanism"]}, sme_id="b")

    def test_answer_outside_option_set_rejected(self):
        from services.domain_forge import ForgeEngine, InvalidAnswer
        db, _ = _make_db()
        eng = ForgeEngine()
        rnd = eng.create_round(db, session_id="s1")
        with pytest.raises(InvalidAnswer):
            eng.submit_answer(db, rnd["id"], {"ranking": ["not_a_real_dim"]}, sme_id="a")

    def test_empty_answer_rejected(self):
        from services.domain_forge import ForgeEngine, InvalidAnswer
        db, _ = _make_db()
        eng = ForgeEngine()
        rnd = eng.create_round(db, session_id="s1")
        with pytest.raises(InvalidAnswer):
            eng.submit_answer(db, rnd["id"], {"ranking": [], "selected": []}, sme_id="a")


# ════════════════════════════════════════════════════════════════════
# DF-2: validation + consensus + scoring
# ════════════════════════════════════════════════════════════════════

class TestConsensusDF2:
    def test_lone_answer_flagged_not_applied(self):
        from services.domain_forge import ForgeEngine
        db, store = _make_db()
        eng = ForgeEngine(consensus_threshold=2)
        rnd = eng.create_round(db, session_id="s1")
        res = eng.submit_answer(db, rnd["id"], {"ranking": ["safety"]}, sme_id="sme-1")
        assert res["consensus"]["state"] == "flagged"
        assert res["playbook_version"] is None
        # NOT applied to a playbook
        assert "compare.drug_x_drug" not in store["playbooks"]
        # valid gold label → small reward, not the promotion reward
        assert res["score"]["points"] == 3

    def test_two_agreeing_smes_promote_dimension(self):
        from services.domain_forge import ForgeEngine
        db, store = _make_db()
        eng = ForgeEngine(consensus_threshold=2)
        # SME 1 picks safety (flagged, lone)
        r1 = eng.create_round(db, session_id="s1")
        res1 = eng.submit_answer(db, r1["id"], {"ranking": ["safety"]}, sme_id="sme-1")
        assert res1["consensus"]["state"] == "flagged"
        # SME 2 independently picks safety → consensus → promoted
        r2 = eng.create_round(db, session_id="s2")
        res2 = eng.submit_answer(db, r2["id"], {"ranking": ["safety"]}, sme_id="sme-2")
        assert res2["consensus"]["state"] == "promoted"
        assert res2["consensus"]["agree_count"] >= 2
        # a playbook version now carries the dimension (via authoring reuse)
        assert res2["playbook_version"] is not None
        pb = store["playbooks"].get("compare.drug_x_drug")
        assert pb is not None
        assert any(d["key"] == "safety" for d in pb["dimensions"])
        # promotion earns the full reward
        assert res2["score"]["points"] == 10

    def test_same_sme_twice_does_not_manufacture_consensus(self):
        from services.domain_forge import ForgeEngine
        db, store = _make_db()
        eng = ForgeEngine(consensus_threshold=2)
        r1 = eng.create_round(db, session_id="s1")
        eng.submit_answer(db, r1["id"], {"ranking": ["dosing"]}, sme_id="sme-1")
        r2 = eng.create_round(db, session_id="s1")
        res2 = eng.submit_answer(db, r2["id"], {"ranking": ["dosing"]}, sme_id="sme-1")
        # distinct-by-sme → still only ONE voice → flagged, not promoted
        assert res2["consensus"]["state"] == "flagged"
        assert "compare.drug_x_drug" not in store["playbooks"]

    def test_session_summary_counts(self):
        from services.domain_forge import ForgeEngine
        db, _ = _make_db()
        eng = ForgeEngine(consensus_threshold=2)
        r1 = eng.create_round(db, session_id="s1")
        eng.submit_answer(db, r1["id"], {"ranking": ["mechanism"]}, sme_id="sme-1")
        summ = eng.session_summary(db, "s1")
        assert summ["rounds"] == 1 and summ["rounds_answered"] == 1
        assert summ["eval_items"] == 1
        assert summ["score"] >= 3


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
    assert "/forge/rounds" in paths
    assert "/forge/rounds/{round_id}" in paths
    assert "/forge/rounds/{round_id}/answer" in paths
    assert "/forge/sessions/{session_id}" in paths
    assert "/forge/eval-items" in paths


def test_router_prefix_is_own():
    from api.routes import forge as r
    assert r.router.prefix == "/forge"


class TestApiRoundTrip:
    def test_play_a_round_end_to_end(self):
        db, store = _make_db()
        c = _client(db)
        ed = _hdr(_login(c, "editor@test.io"))

        # create a round
        r = c.post("/forge/rounds", headers=ed, json={"session_id": "api-s1"})
        assert r.status_code == 201, r.text
        rid = r.json()["id"]
        assert "semaglutide" in r.json()["prompt"]

        # read it back
        r = c.get(f"/forge/rounds/{rid}", headers=ed)
        assert r.status_code == 200

        # submit an answer → eval item + score persist
        r = c.post(f"/forge/rounds/{rid}/answer", headers=ed,
                   json={"ranking": ["mechanism"], "selected": ["mechanism"], "sme_id": "sme-x"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["validation"]["valid"] is True
        assert body["eval_item"]["prompt"]
        assert body["score"]["points"] >= 3

        # gold eval items are listable for the harness
        r = c.get("/forge/eval-items", headers=ed, params={"session_id": "api-s1"})
        assert r.status_code == 200
        assert len(r.json()["eval_items"]) == 1

        # session summary
        r = c.get("/forge/sessions/api-s1", headers=ed)
        assert r.status_code == 200
        assert r.json()["rounds_answered"] == 1

    def test_viewer_cannot_create_round(self):
        db, _ = _make_db()
        c = _client(db)
        vw = _hdr(_login(c, "viewer@test.io"))
        r = c.post("/forge/rounds", headers=vw, json={"session_id": "s"})
        assert r.status_code == 403

    def test_viewer_can_read_eval_items(self):
        db, _ = _make_db()
        c = _client(db)
        vw = _hdr(_login(c, "viewer@test.io"))
        r = c.get("/forge/eval-items", headers=vw)
        assert r.status_code == 200
        assert "eval_items" in r.json()

    def test_answer_outside_option_set_returns_400(self):
        db, _ = _make_db()
        c = _client(db)
        ed = _hdr(_login(c, "editor@test.io"))
        rid = c.post("/forge/rounds", headers=ed, json={"session_id": "s"}).json()["id"]
        r = c.post(f"/forge/rounds/{rid}/answer", headers=ed, json={"ranking": ["bogus"]})
        assert r.status_code == 400

    def test_resubmit_returns_409(self):
        db, _ = _make_db()
        c = _client(db)
        ed = _hdr(_login(c, "editor@test.io"))
        rid = c.post("/forge/rounds", headers=ed, json={"session_id": "s"}).json()["id"]
        c.post(f"/forge/rounds/{rid}/answer", headers=ed, json={"ranking": ["mechanism"]})
        r = c.post(f"/forge/rounds/{rid}/answer", headers=ed, json={"ranking": ["mechanism"]})
        assert r.status_code == 409


# ════════════════════════════════════════════════════════════════════
# DF-5 — more round types: prompt generation (grounded, never fabricates)
# ════════════════════════════════════════════════════════════════════

class TestDF5PromptGeneration:
    _SIGNALS = [
        {"signal_id": "s1", "headline": "Phase 3 missed", "entity_name": "X"},
        {"signal_id": "s2", "headline": "Boxed warning", "entity_name": "Y"},
        {"signal_id": "s3", "headline": "IR call", "entity_name": "Z"},
    ]

    def test_signal_or_noise_grounded(self):
        from services.domain_forge.prompts import generate_signal_or_noise_round
        spec = generate_signal_or_noise_round(MagicMock(), signals=self._SIGNALS)
        assert spec["round_type"] == "signal_or_noise"
        assert len(spec["payload"]["signals"]) == 3
        assert {r["key"] for r in spec["payload"]["reasons"]}  # constrained reasons

    def test_signal_or_noise_too_few_raises(self):
        from services.domain_forge.prompts import generate_signal_or_noise_round
        with pytest.raises(ValueError):
            generate_signal_or_noise_round(MagicMock(), signals=self._SIGNALS[:2])

    def test_routing_round_grounded_and_routable(self):
        from services.domain_forge.prompts import generate_routing_round
        from services.domain_intelligence.playbook import Route
        from services.domain_intelligence.validation import validate_route
        spec = generate_routing_round(
            MagicMock(), dimension_key="safety", entities=_TWO_DRUGS[:1])
        assert spec["round_type"] == "routing"
        assert spec["payload"]["dimension"]["key"] == "safety"
        # every offered route must validate against the live ledger vocabulary
        for o in spec["payload"]["options"]:
            assert validate_route(Route.parse(o["key"])) is None, o["key"]

    def test_routing_unknown_dimension_raises(self):
        from services.domain_forge.prompts import generate_routing_round
        with pytest.raises(ValueError):
            generate_routing_round(MagicMock(), dimension_key="not_a_dim",
                                   entities=_TWO_DRUGS[:1])

    def test_critique_round_grounded_in_real_fact(self):
        from services.domain_forge.prompts import generate_critique_round
        db, _ = _make_db()
        spec = generate_critique_round(db, predicate="mechanism_of_action")
        assert spec["round_type"] == "critique"
        assert spec["payload"]["cell"]["fact_id"]
        assert "semaglutide" in spec["prompt"]
        assert {g["key"] for g in spec["payload"]["grades"]} == {"correct", "partial", "wrong"}


# ════════════════════════════════════════════════════════════════════
# DF-5 ② — Signal or noise? (materiality label)
# ════════════════════════════════════════════════════════════════════

class TestDF5SignalOrNoise:
    def test_persists_materiality_label_and_score(self):
        from services.domain_forge import ForgeEngine
        db, store = _make_db()
        eng = ForgeEngine()
        rnd = eng.create_round(db, session_id="s1", round_type="signal_or_noise")
        res = eng.submit_answer(
            db, rnd["id"],
            {"signal_id": "sig-1", "reason": "clinical_readout"}, sme_id="sme-1")
        assert res["validation"]["valid"] is True
        assert res["label"]["signal_id"] == "sig-1"
        assert res["consensus"]["state"] == "labelled"
        assert res["playbook_version"] is None  # no pack edit
        # a gold eval item + a labelling score persist
        assert len(store["evals"]) == 1
        assert store["evals"][0]["consensus_state"] == "labelled"
        assert res["score"]["points"] == 5

    def test_signal_outside_candidate_set_rejected(self):
        from services.domain_forge import ForgeEngine, InvalidAnswer
        db, _ = _make_db()
        eng = ForgeEngine()
        rnd = eng.create_round(db, session_id="s1", round_type="signal_or_noise")
        with pytest.raises(InvalidAnswer):
            eng.submit_answer(db, rnd["id"],
                              {"signal_id": "ghost", "reason": "clinical_readout"})

    def test_invalid_reason_rejected(self):
        from services.domain_forge import ForgeEngine, InvalidAnswer
        db, _ = _make_db()
        eng = ForgeEngine()
        rnd = eng.create_round(db, session_id="s1", round_type="signal_or_noise")
        with pytest.raises(InvalidAnswer):
            eng.submit_answer(db, rnd["id"],
                              {"signal_id": "sig-1", "reason": "vibes"})


# ════════════════════════════════════════════════════════════════════
# DF-5 ③ — Where does the answer live? (routing → pack edit, consensus)
# ════════════════════════════════════════════════════════════════════

class TestDF5Routing:
    def test_lone_routing_answer_flagged_not_applied(self):
        from services.domain_forge import ForgeEngine
        db, store = _make_db()
        eng = ForgeEngine(consensus_threshold=2)
        rnd = eng.create_round(db, session_id="s1", round_type="routing",
                               dimension_key="safety")
        res = eng.submit_answer(
            db, rnd["id"],
            {"selected": ["predicate:adverse_event", "predicate:safety_signal"]},
            sme_id="sme-1")
        assert res["validation"]["valid"] is True
        assert res["consensus"]["state"] == "flagged"
        assert res["playbook_version"] is None
        assert "dossier.drug" not in store["playbooks"]
        assert res["score"]["points"] == 3  # valid pending

    def test_two_smes_same_routes_promote_dimension(self):
        from services.domain_forge import ForgeEngine
        db, store = _make_db()
        eng = ForgeEngine(consensus_threshold=2)
        routes = ["predicate:adverse_event", "predicate:safety_signal"]
        r1 = eng.create_round(db, session_id="s1", round_type="routing",
                              dimension_key="safety")
        eng.submit_answer(db, r1["id"], {"selected": routes}, sme_id="sme-1")
        # SME 2 picks the SAME route set (order-independent) → consensus → promote
        r2 = eng.create_round(db, session_id="s2", round_type="routing",
                              dimension_key="safety")
        res2 = eng.submit_answer(db, r2["id"],
                                 {"selected": list(reversed(routes))}, sme_id="sme-2")
        assert res2["consensus"]["state"] == "promoted"
        assert res2["playbook_version"] is not None
        pb = store["playbooks"].get("dossier.drug")
        assert pb is not None
        safety = next(d for d in pb["dimensions"] if d["key"] == "safety")
        assert set(safety["routes"]) == set(routes)
        assert res2["score"]["points"] == 10

    def test_unroutable_selection_outside_options_rejected(self):
        from services.domain_forge import ForgeEngine, InvalidAnswer
        db, _ = _make_db()
        eng = ForgeEngine()
        rnd = eng.create_round(db, session_id="s1", round_type="routing",
                               dimension_key="safety")
        with pytest.raises(InvalidAnswer):
            eng.submit_answer(db, rnd["id"],
                              {"selected": ["predicate:totally_made_up"]}, sme_id="a")

    def test_empty_routing_selection_rejected(self):
        from services.domain_forge import ForgeEngine, InvalidAnswer
        db, _ = _make_db()
        eng = ForgeEngine()
        rnd = eng.create_round(db, session_id="s1", round_type="routing",
                               dimension_key="safety")
        with pytest.raises(InvalidAnswer):
            eng.submit_answer(db, rnd["id"], {"selected": []}, sme_id="a")


# ════════════════════════════════════════════════════════════════════
# DF-5 ④ — Grade the machine (accuracy label)
# ════════════════════════════════════════════════════════════════════

class TestDF5Critique:
    def test_grade_persists_accuracy_label_and_score(self):
        from services.domain_forge import ForgeEngine
        db, store = _make_db()
        eng = ForgeEngine()
        rnd = eng.create_round(db, session_id="s1", round_type="critique")
        res = eng.submit_answer(
            db, rnd["id"], {"grade": "partial", "correction": "dual GIP/GLP-1"},
            sme_id="sme-1")
        assert res["validation"]["valid"] is True
        assert res["label"]["grade"] == "partial"
        assert res["label"]["fact_id"] == "fact-1"
        assert res["consensus"]["state"] == "labelled"
        assert len(store["evals"]) == 1
        assert res["score"]["points"] == 5

    def test_invalid_grade_rejected(self):
        from services.domain_forge import ForgeEngine, InvalidAnswer
        db, _ = _make_db()
        eng = ForgeEngine()
        rnd = eng.create_round(db, session_id="s1", round_type="critique")
        with pytest.raises(InvalidAnswer):
            eng.submit_answer(db, rnd["id"], {"grade": "meh"}, sme_id="a")


# ════════════════════════════════════════════════════════════════════
# DF-5 — engine dispatch + API for the new round types
# ════════════════════════════════════════════════════════════════════

class TestDF5Dispatch:
    def test_unknown_round_type_raises(self):
        from services.domain_forge import ForgeEngine
        db, _ = _make_db()
        with pytest.raises(ValueError):
            ForgeEngine().create_round(db, session_id="s1", round_type="bogus")

    def test_api_play_signal_or_noise_end_to_end(self):
        db, _ = _make_db()
        c = _client(db)
        ed = _hdr(_login(c, "editor@test.io"))
        r = c.post("/forge/rounds", headers=ed,
                   json={"session_id": "api-sn", "round_type": "signal_or_noise"})
        assert r.status_code == 201, r.text
        rid = r.json()["id"]
        r = c.post(f"/forge/rounds/{rid}/answer", headers=ed,
                   json={"signal_id": "sig-1", "reason": "clinical_readout",
                         "sme_id": "sme-x"})
        assert r.status_code == 200, r.text
        assert r.json()["eval_item"]["consensus_state"] == "labelled"
        assert r.json()["score"]["points"] == 5

    def test_api_play_routing_end_to_end(self):
        db, _ = _make_db()
        c = _client(db)
        ed = _hdr(_login(c, "editor@test.io"))
        r = c.post("/forge/rounds", headers=ed,
                   json={"session_id": "api-rt", "round_type": "routing",
                         "dimension_key": "safety"})
        assert r.status_code == 201, r.text
        rid = r.json()["id"]
        r = c.post(f"/forge/rounds/{rid}/answer", headers=ed,
                   json={"selected": ["predicate:adverse_event"], "sme_id": "sme-x"})
        assert r.status_code == 200, r.text
        assert r.json()["validation"]["valid"] is True

    def test_api_play_critique_end_to_end(self):
        db, _ = _make_db()
        c = _client(db)
        ed = _hdr(_login(c, "editor@test.io"))
        r = c.post("/forge/rounds", headers=ed,
                   json={"session_id": "api-cr", "round_type": "critique"})
        assert r.status_code == 201, r.text
        rid = r.json()["id"]
        r = c.post(f"/forge/rounds/{rid}/answer", headers=ed,
                   json={"grade": "correct", "sme_id": "sme-x"})
        assert r.status_code == 200, r.text
        assert r.json()["label"]["grade"] == "correct"
