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


def test_etl_run_finalize_persists_skipped_and_failed():
    """`_finalize_etl_run` must persist records_skipped AND records_failed to
    etl_runs. The pipeline already COUNTS both (the #300 fail-closed skip for
    name-less ontology terms; a DLQ insert) on PipelineResult — but pre-098 the
    finalize UPDATE dropped them on the floor: etl_runs had no column for them.
    So a run that fail-closed-skipped 3,121 open_targets records still logged a
    clean SUCCESS with the skip count invisible to Lane-2 — which is *why* that
    backlog bled 18 days unseen. Static guard on the UPDATE select-list, no DB."""
    import inspect

    from integration import pipeline

    src = inspect.getsource(pipeline.IntegrationPipeline._finalize_etl_run).lower()
    assert "records_skipped" in src, (
        "_finalize_etl_run no longer persists records_skipped — fail-closed skips "
        "go invisible to Lane-2 again (the open_targets silent-bleed regression)"
    )
    assert "records_failed" in src, (
        "_finalize_etl_run no longer persists records_failed — DLQ inserts go "
        "invisible to Lane-2 again"
    )


def test_dlq_health_verdict_escalates_on_growth():
    """The DLQ backlog (fail-closed skips + failed_records) must be a first-class
    Lane-2 signal, not silent. A GROWING backlog (a real bleed) is RED; a
    quiescent non-zero backlog is AMBER (known debt awaiting replay, never
    silently GREEN); empty/draining is GREEN. Pure verdict, no DB."""
    from scripts.connector_health import score_dlq

    # a live bleed: many new pending records this window → RED
    assert score_dlq(pending_total=3000, pending_recent=500, skipped_recent=0) == "RED"
    # a fail-closed skip burst this window → RED (the open_targets signature,
    # which never even reaches the DLQ — it is a counted skip)
    assert score_dlq(pending_total=0, pending_recent=0, skipped_recent=500) == "RED"
    # quiescent known-debt backlog (old, not growing) → AMBER, not RED, so the
    # replay loops are not a permanent red — but it is never silently GREEN.
    assert score_dlq(pending_total=2612, pending_recent=0, skipped_recent=0) == "AMBER"
    # empty / fully drained → GREEN
    assert score_dlq(pending_total=0, pending_recent=0, skipped_recent=0) == "GREEN"


def test_connector_health_consults_dlq_verdict():
    """No vacuous green: the DLQ verdict must actually be wired into the health
    gate's output + exit path, not defined-and-ignored. A backlog verdict that
    gates nothing re-creates the silence it exists to kill."""
    import inspect

    from scripts import connector_health

    main_src = inspect.getsource(connector_health.main).lower()
    assert "dlq" in main_src, (
        "the DLQ verdict is never consulted by the health gate's main() — a "
        "backlog signal that gates nothing is a vacuous green"
    )


def test_lane1_suite_is_not_vacuous():
    """No vacuous green at the suite level: this conservation module must define
    real assertions, not be an empty shell that passes by checking nothing."""
    this = importlib.import_module(__name__)
    tests = [n for n in dir(this) if n.startswith("test_")]
    # 4 here + the cross-referenced suites; a single self-referential test would
    # be a smell.
    assert len(tests) >= 4, "conservation-gate suite collapsed to a near-empty shell"
