"""DI-4 — new-playbook coverage tests.

DI-4 broadens the planner from drug-vs-drug compare to four more question
classes: single-drug dossier, asset-centric landscape, pricing/access, and
pipeline. These tests assert the new YAML seeds load, select on their
(intent × entity signature), route only to real ledger predicates / executed
link & source routes, and that the seed library is internally consistent.

DB-free: registry loads from the bundled seeds.
"""

from __future__ import annotations

import pytest

from services.domain_intelligence.playbook import PlaybookRegistry
from services.domain_intelligence.route_executors import SOURCE_ROUTES

NEW_PLAYBOOKS = {
    "dossier.drug": ("dossier", ["drug"]),
    "landscape.drug": ("landscape", ["drug"]),
    "pricing.drug": ("pricing", ["drug"]),
    "pipeline.drug": ("pipeline", ["drug"]),
}


@pytest.fixture(scope="module")
def reg():
    return PlaybookRegistry()


class TestNewPlaybooksLoad:
    @pytest.mark.parametrize("pid", sorted(NEW_PLAYBOOKS))
    def test_seed_loads(self, reg, pid):
        pb = reg.get(pid)
        assert pb is not None, f"{pid} did not load from seed"
        assert pb.pack == "pharma"
        assert pb.dimensions, f"{pid} has no dimensions"
        for d in pb.dimensions:
            assert d.routes, f"{pid}.{d.key} has no routes"

    @pytest.mark.parametrize("pid,trig", sorted(NEW_PLAYBOOKS.items()))
    def test_selects_on_trigger(self, reg, pid, trig):
        intent, sig = trig
        pb = reg.select(intent=intent, entity_types=sig)
        assert pb is not None and pb.id == pid

    def test_single_drug_compare_does_not_pick_a_drug_playbook(self, reg):
        # 'compare' + single drug must NOT silently fall into a single-drug
        # playbook (those trigger on dossier/landscape/pricing/pipeline).
        pb = reg.select(intent="compare", entity_types=["drug"])
        assert pb is None


class TestRoutesAreGrounded:
    """Every predicate route must hit a real ledger predicate; every link/source
    route must be one the executors can actually run."""

    def test_predicate_routes_are_real(self, reg):
        from services.dossier_kb import _PREDICATE_DOMAIN, route_predicate_to_domain
        from services.kbq_views import _PREDICATE_KBQ

        known = set(_PREDICATE_DOMAIN) | set(_PREDICATE_KBQ)
        for pid in NEW_PLAYBOOKS:
            pb = reg.get(pid)
            for d in pb.dimensions:
                for r in d.routes:
                    if r.kind == "predicate":
                        routable = (
                            r.value in known
                            or route_predicate_to_domain(r.value) != "wargame_specific"
                        )
                        assert routable, f"{pid}.{d.key} → unknown predicate {r.value}"

    def test_source_routes_are_whitelisted(self, reg):
        for pid in NEW_PLAYBOOKS:
            pb = reg.get(pid)
            for d in pb.dimensions:
                for r in d.routes:
                    if r.kind == "source":
                        assert r.value in SOURCE_ROUTES, (
                            f"{pid}.{d.key} uses non-executable source {r.value}"
                        )

    def test_link_routes_present_where_expected(self, reg):
        # landscape's competitive_set + dossier's competition lean on the now-
        # executed COMPETES_WITH link route.
        land = reg.get("landscape.drug")
        cset = next(d for d in land.dimensions if d.key == "competitive_set")
        assert "COMPETES_WITH" in cset.links()
        doss = reg.get("dossier.drug")
        comp = next(d for d in doss.dimensions if d.key == "competition")
        assert "COMPETES_WITH" in comp.links()


class TestRequiredDimensions:
    def test_dossier_requires_core_clinical_dimensions(self, reg):
        pb = reg.get("dossier.drug")
        required = {d.key for d in pb.dimensions if d.required}
        assert {"mechanism", "efficacy", "safety"}.issubset(required)

    def test_landscape_requires_competitive_set(self, reg):
        pb = reg.get("landscape.drug")
        required = {d.key for d in pb.dimensions if d.required}
        assert "competitive_set" in required
