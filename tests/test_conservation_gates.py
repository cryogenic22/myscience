"""Conservation gates — Lane 1 (deterministic, PR-hard, DB-free).

These encode the *logic* that makes silent data degradation illegal — the
class of bug this project keeps re-discovering reactively ("the dossier feels
hardcoded"). Each test is a regression net for a REAL failure that shipped
green:

  * fact_class disappearance — `facts_as_of` once didn't SELECT `fact_class`,
    so EVERY ledger fact rendered as a generic `signal` in the dossier. The
    select-list must carry fact_class.
  * resolver picking a 0-fact duplicate — covered by
    test_dossier_kb.test_resolve_ranks_duplicate_drug_rows_by_richness (the
    "Mounjaro feels identical to semaglutide" bug). Asserted here as a
    cross-reference so the Lane-1 suite documents the full conservation set.
  * predicate invisibility (a fact exists but routes nowhere / is missing from
    the KBQ surface) — covered by tests/test_schema_completeness.py pure
    invariants, which run in the same Lane-1 gate.

Lane 2 (population-level NULL%/freshness against the live DB) lives in
test_schema_completeness.py behind DATABASE_URL and runs on the scheduled
operational-health gate, NOT on PRs (a live source being down must never
red a PR). See .claude/rules/conservation-gates.md.

Principle 2 (Conservation before correctness): freshness / linkage / no-silent-
loss invariants make the cheap degradation path fail closed.
"""
from __future__ import annotations

import importlib


def test_facts_as_of_select_carries_fact_class():
    """`facts_as_of` must SELECT fact_class. Without it, every fact silently
    renders as `signal` in the dossier (the DR-1 bug). This is a static guard on
    the canonical select-list — no DB required."""
    from services import facts_ledger

    sql = facts_ledger._SELECT_SUBJECT_SQL.lower()
    assert "fact_class" in sql, (
        "facts_as_of select-list dropped fact_class — every fact will render as "
        "a generic 'signal' in the dossier (DR-1 regression)"
    )


def test_resolver_richness_guard_exists():
    """The 'pick the richest duplicate, never a 0-fact dup' guard must remain a
    live test. Cross-references the canonical resolver test so removing it trips
    this gate."""
    mod = importlib.import_module("tests.test_dossier_kb")
    assert hasattr(mod, "test_resolve_ranks_duplicate_drug_rows_by_richness"), (
        "the resolver-richness regression test was removed — the 'Mounjaro feels "
        "hardcoded' (0-fact duplicate selected) bug is no longer gated"
    )


def test_schema_completeness_pure_invariants_present():
    """The double-mapping invariant (a fact can exist and still be invisible)
    must remain in the Lane-1 suite."""
    mod = importlib.import_module("tests.test_schema_completeness")
    for name in (
        "test_predicate_routes_to_specific_domain",
        "test_predicate_mapped_in_kbq",
        "test_every_scheduled_source_has_an_sla",
    ):
        assert hasattr(mod, name), f"Lane-1 invariant {name} is missing"


def test_lane1_suite_is_not_vacuous():
    """No vacuous green at the suite level: this conservation module must define
    real assertions, not be an empty shell that passes by checking nothing."""
    this = importlib.import_module(__name__)
    tests = [n for n in dir(this) if n.startswith("test_")]
    # 4 here + the cross-referenced suites; a single self-referential test would
    # be a smell.
    assert len(tests) >= 4, "conservation-gate suite collapsed to a near-empty shell"
