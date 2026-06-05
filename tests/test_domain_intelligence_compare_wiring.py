"""DI-3 — handle_compare wiring test.

Confirms the compare path runs the decomposition planner, hands the grounded
matrix context to the LLM, and attaches the structured matrix to the response.
DB-free: facts come from a fake ledger; resolve_entity + engine are stubbed.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import services.chat_handlers.handlers as handlers


class _FakeLedgerDB:
    """Serves facts_as_of-shaped queries from a canned store; everything else
    returns empty (the compare handler's incidental DB calls degrade safely)."""

    def __init__(self, store):
        self.store = store

    def fetch_all(self, sql, params=None):
        params = params or []
        if len(params) >= 3 and params[0] == "drug":
            return list(self.store.get((params[1], params[2]), []))
        return []

    def fetch_one(self, sql, params=None):
        return {"cnt": 0}


def _fact(pred, desc):
    return {
        "id": f"{pred}-{abs(hash(desc)) % 9999}", "predicate": pred,
        "object_value": {"description": desc, "source_url": "https://x"},
        "fact_class": "corporate", "confidence": 0.9,
        "source_doc_id": None, "valid_from": None,
    }


def _make_llm():
    llm = MagicMock()
    llm.synthesize_comparison.return_value = "SYNTH"
    return llm


def _make_engine():
    engine = MagicMock()
    engine.compare_entities.return_value = {
        "entities": [], "metrics_comparison": {},
        "shared_connections": [], "unique_connections": {},
    }
    return engine


def test_compare_attaches_decomposition_and_feeds_matrix_context():
    store = {
        ("sema", "mechanism_of_action"): [_fact("mechanism_of_action", "GLP-1 RA")],
        ("sema", "clinical_trial"): [_fact("clinical_trial", f"STEP {i}") for i in range(3)],
        ("tirze", "mechanism_of_action"): [_fact("mechanism_of_action", "dual GIP/GLP-1")],
        # tirze has NO clinical_trial / pricing → real gaps
    }
    db = _FakeLedgerDB(store)
    llm = _make_llm()
    engine = _make_engine()

    def fake_resolve(name, etype, _db):
        lname = name.strip().lower()
        if "sema" in lname:
            return {"entity_id": "sema", "entity_type": "drug", "label": "semaglutide"}
        if "tirze" in lname:
            return {"entity_id": "tirze", "entity_type": "drug", "label": "tirzepatide"}
        return None

    with patch.object(handlers, "resolve_entity", side_effect=fake_resolve):
        out = handlers.handle_compare(
            {"entities": ["semaglutide", "tirzepatide"]}, db, engine, llm,
        )

    # 1) the structured matrix is attached
    assert "decomposition" in out
    decomp = out["decomposition"]
    assert decomp["playbook_id"] == "compare.drug_x_drug"
    assert len(decomp["dimensions"]) == 7
    # 2) tirzepatide efficacy + pricing are honest gaps
    assert "efficacy" in decomp["gaps"]
    assert "pricing_access" in decomp["gaps"]
    # 3) the LLM received the grounded matrix as context (so it cannot invent)
    _, kwargs = llm.synthesize_comparison.call_args
    extra = kwargs.get("extra_context") or ""
    assert "DECOMPOSITION MATRIX" in extra
    assert "GLP-1 RA" in extra
    assert "GAP" in extra.upper()


def test_compare_falls_back_when_single_entity_unresolved():
    """No DI crash when fewer than two entities resolve."""
    db = _FakeLedgerDB({})
    llm = _make_llm()
    engine = _make_engine()
    engine.query.return_value = MagicMock(
        evidence=[], graph_context={}, metrics_context={}, entity_focus=[],
        provenance_summary={}, question="x",
    )

    def only_one(name, etype, _db):
        return {"entity_id": "sema", "entity_type": "drug", "label": "semaglutide"} \
            if "sema" in name.lower() else None

    with patch.object(handlers, "resolve_entity", side_effect=only_one):
        out = handlers.handle_compare(
            {"entities": ["semaglutide", "unknowndrug"]}, db, engine, llm,
        )
    # falls back to general query path; no decomposition, no crash
    assert "decomposition" not in out
