"""DI-4 — handler-wiring tests for the new playbooks.

Confirms the shared _run_domain_intelligence helper and the dossier handler run
the planner for the single-drug playbooks and fold the grounded matrix into the
answer. DB-free: facts come from a fake ledger; engine/LLM are stubbed.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import services.chat_handlers.handlers as handlers


class _FakeLedgerDB:
    def __init__(self, store):
        self.store = store

    def fetch_all(self, sql, params=None):
        params = params or []
        if len(params) >= 3 and params[0] == "drug":
            return list(self.store.get((params[1], params[2]), []))
        return []

    def fetch_one(self, sql, params=None):
        return None


def _fact(pred, desc):
    return {
        "id": f"{pred}-{abs(hash(desc)) % 9999}", "predicate": pred,
        "object_value": {"description": desc, "source_url": "https://x"},
        "fact_class": "corporate", "confidence": 0.9,
        "source_doc_id": None, "valid_from": None,
    }


# ── shared helper ──────────────────────────────────────────────────


class TestRunDomainIntelligence:
    def test_dossier_intent_builds_matrix(self):
        store = {
            ("sema", "mechanism_of_action"): [_fact("mechanism_of_action", "GLP-1 RA")],
            ("sema", "clinical_trial"): [_fact("clinical_trial", f"STEP {i}") for i in range(3)],
        }
        db = _FakeLedgerDB(store)
        out = handlers._run_domain_intelligence(
            "dossier",
            [{"entity_id": "sema", "entity_type": "drug", "label": "semaglutide"}],
            db,
        )
        assert out["matrix"] is not None
        assert out["matrix"].playbook_id == "dossier.drug"
        assert "Mechanism" in out["narrative"]
        assert "DECOMPOSITION MATRIX" in out["context"]

    def test_unknown_intent_returns_empty_bundle(self):
        out = handlers._run_domain_intelligence(
            "weather",
            [{"entity_id": "x", "entity_type": "drug", "label": "x"}],
            _FakeLedgerDB({}),
        )
        assert out["matrix"] is None
        assert out["narrative"] == ""

    def test_no_db_returns_empty_bundle(self):
        out = handlers._run_domain_intelligence(
            "dossier",
            [{"entity_id": "x", "entity_type": "drug", "label": "x"}],
            None,
        )
        assert out["matrix"] is None


# ── dossier handler wiring ─────────────────────────────────────────


def test_dossier_handler_feeds_matrix_to_llm_and_uses_grounded_fallback():
    store = {
        ("sema", "mechanism_of_action"): [_fact("mechanism_of_action", "GLP-1 receptor agonist")],
        ("sema", "label_indication"): [_fact("label_indication", "type 2 diabetes")],
        ("sema", "clinical_trial"): [_fact("clinical_trial", f"STEP {i}") for i in range(3)],
        ("sema", "adverse_event"): [_fact("adverse_event", f"AE {i}") for i in range(2)],
        # pricing/regulatory/competition left as honest gaps
    }
    db = _FakeLedgerDB(store)

    llm = MagicMock()
    llm.synthesize_dossier.return_value = "NARRATIVE"

    engine = MagicMock()
    engine.entity_dossier.return_value = MagicMock(
        evidence=[], graph_context={}, metrics_context={},
        entity_focus=[], provenance_summary={},
    )

    def fake_resolve(name, etype, _db):
        return {"entity_id": "sema", "entity_type": "drug",
                "label": "semaglutide", "match_score": 1.0}

    with patch.object(handlers, "resolve_entity", side_effect=fake_resolve), \
         patch.object(handlers, "_enrich_result", return_value={}), \
         patch.object(handlers, "_hydrate_dossier_ctx", return_value=None):
        out = handlers.handle_dossier({"entity_name": "semaglutide"}, db, engine, llm)

    assert out["intent"] == "dossier"
    # the LLM received the grounded decomposition matrix as context
    _, kwargs = llm.synthesize_dossier.call_args
    extra = kwargs.get("extra_context") or ""
    assert "DECOMPOSITION MATRIX" in extra
    assert "GLP-1 receptor agonist" in extra
    # and the fallback floor is the grounded per-dimension narrative (gaps stated)
    fallback = kwargs.get("fallback_narrative") or ""
    assert "Mechanism" in fallback
    assert "gap" in fallback.lower()
