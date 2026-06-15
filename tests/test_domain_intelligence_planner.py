"""DI-2 — Decomposition planner tests.

The planner is the core lift: select playbook → expand per-dimension
sub-questions per entity → route each dimension to its facts via facts_as_of by
predicate → assemble a structured matrix (entities × dimensions), each cell =
grounded facts + a coverage state (covered / thin / gap).

DB-free: a fake DB returns canned facts per (entity, predicate) so we can test
the matrix shape + coverage logic without prod. A separate live-DB gate
(scripts run in the report) proves it on real semaglutide vs tirzepatide.
"""

from __future__ import annotations

from services.domain_intelligence.planner import (
    DecompositionPlanner,
    DimensionCell,
    QuestionMatrix,
    coverage_state,
)
from services.domain_intelligence.playbook import PlaybookRegistry


# ── A fake ledger ──────────────────────────────────────────────────


class FakeDB:
    """Returns facts keyed by (subject_id, predicate). Mimics db.fetch_all for
    facts_as_of-shaped queries used by the planner."""

    def __init__(self, store: dict):
        # store: {(entity_id, predicate): [fact_dicts]}
        self.store = store

    def fetch_all(self, sql, params=None):
        # The planner calls facts_as_of(db, type, id, predicate=...). facts_as_of
        # issues a SELECT with subject_entity_type, subject_entity_id, predicate.
        params = params or []
        # params = [type, id, predicate] when predicate filtering
        if len(params) >= 3:
            _t, eid, pred = params[0], params[1], params[2]
            return list(self.store.get((eid, pred), []))
        if len(params) == 2:
            _t, eid = params
            out = []
            for (e, _p), facts in self.store.items():
                if e == eid:
                    out.extend(facts)
            return out
        return []

    def fetch_one(self, sql, params=None):
        return None


def _fact(predicate, desc, fc="reference", conf=0.9):
    # NOTE: fc must be a VALID_FACT_CLASS post-coercion. 'reference' is the
    # substantive (curated) class; 'corporate'/'signal'/'inferred' are weak
    # (news/derived). Anything else coerces to 'signal' (weak).
    return {
        "id": f"{predicate}-{abs(hash(desc)) % 99999}",
        "predicate": predicate,
        "object_value": {"description": desc, "source_url": "https://x/1"},
        "fact_class": fc,
        "confidence": conf,
        "source_doc_id": None,
        "valid_from": None,
    }


def _entity(eid, name):
    return {"entity_id": eid, "entity_type": "drug", "label": name}


# ── coverage_state (pure) ──────────────────────────────────────────


class TestCoverageState:
    def test_gap_when_no_facts(self):
        assert coverage_state([]) == "gap"

    def test_thin_when_one_fact(self):
        assert coverage_state([_fact("clinical_trial", "x")]) == "thin"

    def test_covered_when_multiple_substantive_facts(self):
        facts = [_fact("mechanism_of_action", f"m {i}", fc="reference") for i in range(3)]
        assert coverage_state(facts) == "covered"

    def test_weak_only_facts_are_thin_not_covered(self):
        # Coverage-QUALITY: news/signal/inferred facts are context, not hard
        # evidence — a cell backed only by them is 'thin', never 'covered'.
        for fc in ("corporate", "signal", "inferred"):
            facts = [_fact("clinical_trial", f"t{i}", fc=fc) for i in range(4)]
            assert coverage_state(facts) == "thin", f"{fc} facts must not be 'covered'"
        # one substantive (reference) fact among weak ones is still only 'thin' (<2 substantive)
        mixed = [_fact("x", "a", fc="reference")] + [_fact("y", f"n{i}", fc="signal") for i in range(3)]
        assert coverage_state(mixed) == "thin"


# ── matrix assembly ────────────────────────────────────────────────


class TestPlannerMatrix:
    def _planner(self, store):
        reg = PlaybookRegistry()
        return DecompositionPlanner(FakeDB(store), registry=reg)

    def test_plan_returns_seven_dimension_matrix(self):
        # sema: covered on mechanism+efficacy+safety, gap elsewhere
        store = {
            ("sema", "mechanism_of_action"): [_fact("mechanism_of_action", "GLP-1 RA", "reference")],
            ("sema", "clinical_trial"): [_fact("clinical_trial", f"STEP {i}") for i in range(3)],
            ("sema", "adverse_event"): [_fact("adverse_event", f"AE {i}", "signal") for i in range(2)],
            ("tirze", "mechanism_of_action"): [_fact("mechanism_of_action", "GIP/GLP-1", "reference")],
            ("tirze", "clinical_trial"): [_fact("clinical_trial", f"SURMOUNT {i}") for i in range(3)],
        }
        planner = self._planner(store)
        matrix = planner.plan(
            intent="compare",
            entities=[_entity("sema", "semaglutide"), _entity("tirze", "tirzepatide")],
        )
        assert isinstance(matrix, QuestionMatrix)
        assert matrix.playbook_id == "compare.drug_x_drug"
        assert len(matrix.dimensions) == 7
        assert [e["label"] for e in matrix.entities] == ["semaglutide", "tirzepatide"]

    def test_cell_carries_facts_and_coverage(self):
        store = {
            ("sema", "clinical_trial"): [_fact("clinical_trial", f"STEP {i}") for i in range(3)],
        }
        planner = self._planner(store)
        matrix = planner.plan("compare", [_entity("sema", "semaglutide")] * 0 + [
            _entity("sema", "semaglutide"), _entity("tirze", "tirzepatide")])
        cell = matrix.cell("efficacy", "sema")
        assert isinstance(cell, DimensionCell)
        assert cell.coverage == "covered"
        assert len(cell.facts) == 3
        # tirze efficacy is a gap (no facts)
        assert matrix.cell("efficacy", "tirze").coverage == "gap"

    def test_uncovered_dimension_is_gap_not_invented(self):
        # No pricing facts for either → pricing_access cell must be a gap
        planner = self._planner({})
        matrix = planner.plan("compare", [_entity("sema", "semaglutide"), _entity("tirze", "tirzepatide")])
        assert matrix.cell("pricing_access", "sema").coverage == "gap"
        assert matrix.cell("pricing_access", "sema").facts == []

    def test_subquestion_filled_per_entity(self):
        planner = self._planner({})
        matrix = planner.plan("compare", [_entity("sema", "semaglutide"), _entity("tirze", "tirzepatide")])
        cell = matrix.cell("mechanism", "sema")
        assert "semaglutide" in cell.sub_question
        assert "{entity}" not in cell.sub_question

    def test_no_playbook_match_returns_none(self):
        planner = self._planner({})
        # single drug doesn't match the drug×drug signature
        matrix = planner.plan("compare", [_entity("sema", "semaglutide")])
        assert matrix is None

    def test_dimension_coverage_summary(self):
        store = {
            ("sema", "mechanism_of_action"): [_fact("mechanism_of_action", "GLP-1 RA")],
            ("sema", "clinical_trial"): [_fact("clinical_trial", f"t{i}") for i in range(3)],
            ("tirze", "clinical_trial"): [_fact("clinical_trial", f"s{i}") for i in range(3)],
        }
        planner = self._planner(store)
        matrix = planner.plan("compare", [_entity("sema", "semaglutide"), _entity("tirze", "tirzepatide")])
        summ = matrix.coverage_summary()
        # efficacy covered for both; pricing a gap for both
        assert summ["efficacy"] == "covered"
        assert summ["pricing_access"] == "gap"

    def test_compare_rollup_is_thin_when_only_one_entity_covered(self):
        # Honest compare rollup: covered for ONE drug but a gap for the other is
        # NOT 'covered' — it is 'thin' (partial). (Was 'covered if ANY'.)
        store = {
            ("sema", "clinical_trial"): [_fact("clinical_trial", f"t{i}", fc="reference") for i in range(3)],
            # tirze has no efficacy facts -> gap
        }
        planner = self._planner(store)
        matrix = planner.plan("compare", [_entity("sema", "semaglutide"), _entity("tirze", "tirzepatide")])
        summ = matrix.coverage_summary()
        assert summ["efficacy"] == "thin", "covered-for-one + gap-for-other must roll up to 'thin'"

    def test_facts_deduped_within_cell(self):
        # same description from two predicates routed to one dimension → 1 fact
        store = {
            ("sema", "adverse_event"): [_fact("adverse_event", "Nausea")],
            ("sema", "safety_signal"): [_fact("safety_signal", "Nausea")],
        }
        planner = self._planner(store)
        matrix = planner.plan("compare", [_entity("sema", "semaglutide"), _entity("tirze", "tirzepatide")])
        cell = matrix.cell("safety", "sema")
        # The same finding ("Nausea") surfaced via two predicates routed to the
        # safety dimension must appear exactly once in the cell.
        nausea = [f for f in cell.facts if "Nausea" in f["claim"]]
        assert len(nausea) == 1
