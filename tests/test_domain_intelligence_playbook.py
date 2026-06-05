"""DI-1 — Playbook data model + registry tests.

A Playbook is encoded domain expertise: a trigger (intent × entity-type
signature) + a list of routed dimensions + a synthesis shape. Playbooks are
DATA (YAML-seeded), not hardcoded dicts, and SME-editable later (DI-5).

These tests are DB-free: the registry loads from the seeded YAML pack.
"""

from __future__ import annotations

import pytest

from services.domain_intelligence.playbook import (
    Dimension,
    Playbook,
    PlaybookRegistry,
    Route,
    get_playbook_registry,
)


# ── Data model ─────────────────────────────────────────────────────


class TestDataModel:
    def test_route_parses_predicate_link_source(self):
        assert Route.parse("predicate:mechanism_of_action") == Route("predicate", "mechanism_of_action")
        assert Route.parse("link:COMPETES_WITH") == Route("link", "COMPETES_WITH")
        assert Route.parse("source:regulatory_milestones") == Route("source", "regulatory_milestones")

    def test_route_bare_string_defaults_to_predicate(self):
        assert Route.parse("trial_result") == Route("predicate", "trial_result")

    def test_dimension_has_routes_and_subquestion(self):
        d = Dimension(
            key="mechanism",
            label="Mechanism of action",
            sub_question="What is {entity}'s mechanism?",
            routes=[Route("predicate", "mechanism_of_action")],
            required=True,
            weight=0.9,
        )
        assert d.predicates() == ["mechanism_of_action"]
        assert "{entity}" in d.sub_question

    def test_dimension_fill_subquestion(self):
        d = Dimension(key="m", label="M", sub_question="What is {entity}'s mechanism?")
        assert d.fill("semaglutide") == "What is semaglutide's mechanism?"


# ── Registry / seeding ─────────────────────────────────────────────


class TestRegistrySeed:
    def test_registry_loads_compare_drug_x_drug(self):
        reg = PlaybookRegistry()
        pb = reg.get("compare.drug_x_drug")
        assert pb is not None
        assert pb.id == "compare.drug_x_drug"
        assert pb.pack == "pharma"

    def test_compare_playbook_lists_seven_routed_dimensions(self):
        """DI-1 gate: the drug-vs-drug playbook loads and lists 7 routed dimensions."""
        pb = PlaybookRegistry().get("compare.drug_x_drug")
        keys = [d.key for d in pb.dimensions]
        assert keys == [
            "mechanism", "efficacy", "safety", "dosing",
            "regulatory", "pricing_access", "competition",
        ]
        # every dimension is routed (has at least one route)
        for d in pb.dimensions:
            assert d.routes, f"dimension {d.key} has no routes"

    def test_dimensions_route_to_real_ledger_predicates(self):
        """Routes must reuse predicates the ledger actually emits / routes —
        i.e. predicates known to _PREDICATE_DOMAIN or _PREDICATE_KBQ."""
        from services.dossier_kb import _PREDICATE_DOMAIN, route_predicate_to_domain
        from services.kbq_views import _PREDICATE_KBQ

        known = set(_PREDICATE_DOMAIN) | set(_PREDICATE_KBQ)
        pb = PlaybookRegistry().get("compare.drug_x_drug")
        for d in pb.dimensions:
            for r in d.routes:
                if r.kind == "predicate":
                    # known exactly, or routable by the prefix router (not fallback)
                    routable = (
                        r.value in known
                        or route_predicate_to_domain(r.value) != "wargame_specific"
                    )
                    assert routable, f"{d.key} routes to unknown predicate {r.value}"

    def test_required_dimensions_marked(self):
        pb = PlaybookRegistry().get("compare.drug_x_drug")
        required = {d.key for d in pb.dimensions if d.required}
        assert {"mechanism", "efficacy", "safety"}.issubset(required)

    def test_synthesis_shape_is_matrix(self):
        pb = PlaybookRegistry().get("compare.drug_x_drug")
        assert pb.synthesis.get("shape") == "matrix"


# ── Trigger selection ──────────────────────────────────────────────


class TestTriggerSelection:
    def test_select_by_intent_and_entity_signature(self):
        reg = PlaybookRegistry()
        pb = reg.select(intent="compare", entity_types=["drug", "drug"])
        assert pb is not None
        assert pb.id == "compare.drug_x_drug"

    def test_select_single_drug_does_not_match_drug_x_drug(self):
        reg = PlaybookRegistry()
        pb = reg.select(intent="compare", entity_types=["drug"])
        # only one drug → drug_x_drug signature (drug × drug) should not match
        assert pb is None or pb.id != "compare.drug_x_drug"

    def test_select_unknown_intent_returns_none(self):
        reg = PlaybookRegistry()
        assert reg.select(intent="weather", entity_types=["drug", "drug"]) is None

    def test_module_singleton_caches(self):
        a = get_playbook_registry()
        b = get_playbook_registry()
        assert a is b
        assert a.get("compare.drug_x_drug") is not None


# ── DB-backed override (DI-5 forward-compat, additive) ─────────────


class TestDbBackedOverride:
    def test_db_playbook_overrides_seed(self):
        """When a DB row exists for an id, it overrides the YAML seed — the
        SME-editable path. Falls back to seed when the table is absent/empty."""
        from unittest.mock import MagicMock

        db = MagicMock()
        db.fetch_all.return_value = [{
            "id": "compare.drug_x_drug",
            "pack": "pharma",
            "trigger": {"intent": "compare", "entities": "drug × drug"},
            "dimensions": [
                {"key": "mechanism", "label": "Mechanism", "sub_question": "?",
                 "routes": ["predicate:mechanism_of_action"], "required": True, "weight": 0.9},
            ],
            "synthesis": {"shape": "matrix"},
        }]
        reg = PlaybookRegistry(db=db)
        pb = reg.get("compare.drug_x_drug")
        # DB version has 1 dimension (overrode the 7-dim seed)
        assert len(pb.dimensions) == 1

    def test_db_failure_falls_back_to_seed(self):
        from unittest.mock import MagicMock

        db = MagicMock()
        db.fetch_all.side_effect = Exception("no table")
        reg = PlaybookRegistry(db=db)
        pb = reg.get("compare.drug_x_drug")
        assert len(pb.dimensions) == 7
