"""Loop C — pharma_source_contracts.yaml is an ENFORCEABLE contract, not docs.

Lane-1, DB-free. Fails closed if a connector is added without a contract, or a
contract declares a predicate the ledger doesn't route (no vacuous green).
"""
from __future__ import annotations

import os

import yaml

from connectors import CONNECTOR_REGISTRY
from services.dossier_kb import _PREDICATE_DOMAIN
from services.facts_ledger import FACT_CLASSES

_PACK = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "domain", "pharma", "packs", "pharma_source_contracts.yaml",
)


def _load():
    with open(_PACK, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _contracts():
    return _load()["source_contracts"]


def _active():
    return {k: v for k, v in _contracts().items() if v.get("status") == "active"}


def test_pack_parses_with_required_header():
    pack = _load()
    assert pack["pack"]["id"] == "pharma.source_contracts.v0_1"
    assert pack["trust_tiers"]


def test_every_registered_connector_has_an_active_contract():
    registered = {st.value for st in CONNECTOR_REGISTRY}
    governed = set(_active())
    missing = registered - governed
    assert not missing, f"connectors with no active source contract: {sorted(missing)}"


def test_no_orphan_active_contract():
    # an active contract must correspond to a real registered connector
    registered = {st.value for st in CONNECTOR_REGISTRY}
    orphans = set(_active()) - registered
    assert not orphans, f"active contracts with no connector: {sorted(orphans)}"


def test_active_contracts_only_emit_real_predicates():
    known = set(_PREDICATE_DOMAIN)
    for name, c in _active().items():
        for em in c.get("may_emit", []):
            assert em["predicate"] in known, (
                f"{name} declares unknown predicate {em['predicate']!r} "
                f"(not in _PREDICATE_DOMAIN)")


def test_active_contracts_have_required_shape():
    tiers = set(_load()["trust_tiers"])
    for name, c in _active().items():
        assert c.get("source_class"), f"{name}: missing source_class"
        assert c.get("trust_tier") in tiers, f"{name}: bad trust_tier"
        assert "must_capture" in c and c["must_capture"], f"{name}: empty must_capture"
        assert "may_emit" in c, f"{name}: missing may_emit"
        assert c.get("default_fact_class") in FACT_CLASSES, f"{name}: bad default_fact_class"
        for em in c.get("may_emit", []):
            assert em["fact_class"] in FACT_CLASSES, f"{name}: bad fact_class {em}"


def test_planned_contracts_state_demand_and_proposed_predicates():
    planned = {k: v for k, v in _contracts().items() if v.get("status") == "planned"}
    assert planned, "expected the payer/RWD roadmap as planned contracts"
    for name, c in planned.items():
        assert c.get("demand"), f"{name}: planned contract must state demand"
        assert c.get("proposed_predicates"), f"{name}: planned must list proposed_predicates"


def test_news_and_filing_discipline_encoded():
    # news → signal, never an approved clinical fact; filing → corporate claim
    c = _contracts()
    assert c["pharma_news"]["default_fact_class"] == "signal"
    assert c["sec_edgar"]["default_fact_class"] == "corporate"
    assert c["openfda_faers"]["default_fact_class"] == "signal"
