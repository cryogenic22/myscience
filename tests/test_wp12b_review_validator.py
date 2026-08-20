"""WP-12B — typed review-artifact validator (SPEC_WP12 §3 WP-12B), hardened across rounds.

The validator reconciles a structured review artifact against the WP-12A contract AND against
TrustedInputs — the real PR head SHA, commit time, the ratified criterion/gate set, the REAL
check conclusions, and the INDEPENDENT REVIEW (actor/state/commit_id/dismissed), all sourced
OUTSIDE the artifact from GitHub. It is the machine that would have caught the PRIV-001
escaped defect.

Independent-review binding (owner calibration): an APPROVE is believed ONLY when the review
is by the ONE trusted reviewer (codexindependentreviewer[bot]), state == APPROVED, not
dismissed, targets the EXACT live head, and the actor != the PR author. COMMENTED,
CHANGES_REQUESTED, wrong-actor, stale-SHA, dismissed, and missing all fail closed.
"""
from __future__ import annotations

import copy

from assurance.review_artifact import load_contract, validate_review, TrustedInputs, Violation

CONTRACT = load_contract()

_HEAD = "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678"
_OTHER = "ffffffffffffffffffffffffffffffffffffffff"
_FINAL_AT = "2026-08-14T10:00:00+00:00"
_NOW = "2026-08-14T12:00:00+00:00"
_BOT = "codexindependentreviewer[bot]"
_BOT_ID = 317626643
_AUTHOR = "the-builder"


def _ti(**over) -> TrustedInputs:
    """A fully-reconcilable TrustedInputs (approved by the trusted bot on the exact head),
    with keyword overrides for the axis under test."""
    base = dict(
        pr_head_sha=_HEAD,
        final_commit_committed_at=_FINAL_AT,
        required_criteria=("SPEC_X#1", "SPEC_X#2"),
        required_gates=("conservation-lane1",),
        na_allowed_criteria=("SPEC_X#2",),
        now=_NOW,
        gate_conclusions={"conservation-lane1": "success"},
        pr_author_login=_AUTHOR,
        trusted_reviewer_login=_BOT,
        trusted_reviewer_id=_BOT_ID,
        review_actor=_BOT,
        review_actor_id=_BOT_ID,
        review_actor_type="Bot",
        review_state="APPROVED",
        review_commit_id=_HEAD,
        review_dismissed=False,
        run_id="run-1234",
    )
    base.update(over)
    return TrustedInputs(**base)


_TRUSTED = _ti()

_GOOD_APPROVE = {
    "pr": "#999",
    "verdict": "APPROVE",
    "reviewer": _BOT,
    "reviewed_sha": _HEAD,
    "pr_head_sha": _HEAD,
    "final_commit_committed_at": _FINAL_AT,
    "spec_conformance": [
        {"criterion_id": "SPEC_X#1", "verdict": "met", "evidence_ref": "ev-tests"},
        {"criterion_id": "SPEC_X#2", "verdict": "n/a", "evidence_ref": "not applicable"},
    ],
    "findings": [{"id": "F1", "severity": "nit", "must_fix": False, "resolved": False}],
    "gates": [{"name": "conservation-lane1", "status": "pass"}],
    "evidence": [{"id": "ev-tests", "ref": "pytest -q", "produced_at": "2026-08-14T10:05:00+00:00"}],
}


def _mut(**over):
    d = copy.deepcopy(_GOOD_APPROVE)
    d.update(over)
    return d


def _codes(artifact, trusted=_TRUSTED) -> set[str]:
    return {v.code for v in validate_review(artifact, CONTRACT, trusted)}


# =========================================================================
# The escaped-defect replay — MUST be rejected.
# =========================================================================

_PRIV001_HEAD = "a66dbcba7337d9e28eef190823b90bb038a3856f"
PRIV001_LAND_WITH_NITS = {
    "pr": "#326",
    "verdict": "LAND-WITH-NITS",
    "reviewed_sha": _PRIV001_HEAD,
    "pr_head_sha": _PRIV001_HEAD,
    "final_commit_committed_at": "2026-08-13T10:00:00+00:00",
    "spec_conformance": [
        {"criterion_id": "SPEC_HANDOFF_001#H1.1.4", "verdict": "unmet",
         "evidence_ref": "extraction_llm.py:500 (Anthropic) + entity_resolver.py:620 still raw"},
        {"criterion_id": "SPEC_HANDOFF_001#H1.1.min-tests", "verdict": "unmet",
         "evidence_ref": "no static no-bypass test; no direct-vs-gateway parity test"},
    ],
    "findings": [{"id": "F1", "severity": "must", "must_fix": True, "resolved": False}],
    "gates": [{"name": "conservation-lane1", "status": "pass"}],
    "evidence": [{"id": "ev1", "ref": "pytest tests/test_llm_gateway.py",
                  "produced_at": "2026-08-13T11:00:00+00:00"}],
}
_PRIV001_TRUSTED = _ti(
    pr_head_sha=_PRIV001_HEAD,
    final_commit_committed_at="2026-08-13T10:00:00+00:00",
    required_criteria=("SPEC_HANDOFF_001#H1.1.4", "SPEC_HANDOFF_001#H1.1.min-tests"),
    na_allowed_criteria=(),
    review_commit_id=_PRIV001_HEAD,
)


def test_priv001_land_with_nits_is_rejected():
    codes = {v.code for v in validate_review(PRIV001_LAND_WITH_NITS, CONTRACT, _PRIV001_TRUSTED)}
    assert "UNKNOWN_VERDICT" in codes, codes


def test_priv001_even_as_approve_is_rejected_on_unmet_criterion():
    coerced = dict(PRIV001_LAND_WITH_NITS, verdict="APPROVE")
    codes = {v.code for v in validate_review(coerced, CONTRACT, _PRIV001_TRUSTED)}
    assert "APPROVE_WITH_UNMET_CRITERION" in codes, codes
    assert "APPROVE_WITH_OPEN_MUST" in codes, codes


# =========================================================================
# Positive cases
# =========================================================================

def test_good_approve_is_valid():
    assert validate_review(_GOOD_APPROVE, CONTRACT, _TRUSTED) == []


def test_review_of_record_is_the_body_payload_no_committed_artifact():
    """Rev 4: the review payload lives in the trusted bot's review BODY; reviewed_sha equals the
    live head directly (no self-referential evidence commit, no artifact_commit_parent). A payload
    that covers the exact head validates clean."""
    assert validate_review(_GOOD_APPROVE, CONTRACT, _TRUSTED) == []


def test_changes_required_with_open_items_is_valid():
    art = _mut(
        verdict="CHANGES-REQUIRED",
        spec_conformance=[{"criterion_id": "SPEC_X#1", "verdict": "unmet", "evidence_ref": "x"}],
        findings=[{"id": "F1", "severity": "must", "must_fix": True, "resolved": False}],
    )
    assert validate_review(art, CONTRACT, trusted=None) == []


# =========================================================================
# Independent-review binding — the owner-calibrated review-state / SHA matrix.
# Every non-APPROVED / wrong-actor / stale / dismissed / missing case fails closed.
# =========================================================================

def test_commented_review_is_rejected():
    assert "REVIEW_NOT_APPROVED" in _codes(_GOOD_APPROVE, _ti(review_state="COMMENTED"))


def test_changes_requested_review_is_rejected():
    assert "REVIEW_NOT_APPROVED" in _codes(_GOOD_APPROVE, _ti(review_state="CHANGES_REQUESTED"))


def test_approved_review_on_previous_sha_is_rejected():
    """An approval left on an older commit does not approve the current head (a push invalidates)."""
    assert "REVIEW_STALE_SHA" in _codes(_GOOD_APPROVE, _ti(review_commit_id=_OTHER))


def test_wrong_actor_review_is_rejected():
    assert "REVIEWER_NOT_TRUSTED" in _codes(_GOOD_APPROVE, _ti(review_actor="someone-else[bot]"))


def test_reviewer_equal_to_author_is_not_independent():
    """If the trusted-reviewer login somehow equals the PR author, it is not independent."""
    codes = _codes(_GOOD_APPROVE, _ti(review_actor=_AUTHOR, pr_author_login=_AUTHOR,
                                      trusted_reviewer_login=_AUTHOR))
    assert "REVIEWER_NOT_INDEPENDENT" in codes


def test_dismissed_review_is_rejected():
    assert "REVIEW_DISMISSED" in _codes(_GOOD_APPROVE, _ti(review_dismissed=True))


def test_dismissed_state_is_rejected():
    assert "REVIEW_DISMISSED" in _codes(_GOOD_APPROVE, _ti(review_state="DISMISSED"))


def test_missing_review_is_rejected():
    """No review by the trusted reviewer at all → fail closed."""
    codes = _codes(_GOOD_APPROVE, _ti(review_state=None, review_actor=None, review_commit_id=None))
    assert "REVIEW_MISSING" in codes


def test_no_trusted_reviewer_configured_fails_closed():
    codes = _codes(_GOOD_APPROVE, _ti(trusted_reviewer_login=None))
    assert "MISSING_TRUSTED_REVIEWER" in codes


def test_declared_reviewer_mismatch_rejected():
    assert "REVIEWER_MISMATCH" in _codes(_mut(reviewer="someone-else"))


def test_approve_without_trusted_fails_closed():
    assert "UNVERIFIABLE_APPROVE" in _codes(_GOOD_APPROVE, trusted=None)


# =========================================================================
# External truth beats self-attestation (real gate conclusions).
# =========================================================================

def test_gate_pass_contradicting_real_conclusion_rejected():
    trusted = _ti(gate_conclusions={"conservation-lane1": "failure"})
    codes = {v.code for v in validate_review(_GOOD_APPROVE, CONTRACT, trusted)}
    assert "GATE_CONCLUSION_MISMATCH" in codes, codes
    assert "REQUIRED_GATE_NOT_PASSED" in codes, codes


def test_required_gate_real_conclusion_absent_rejected():
    trusted = _ti(gate_conclusions={"some-other-check": "success"})
    art = _mut(gates=[{"name": "conservation-lane1", "status": "skip"}])
    assert "REQUIRED_GATE_NOT_PASSED" in {v.code for v in validate_review(art, CONTRACT, trusted)}


def test_approve_with_no_real_conclusions_fails_closed():
    assert "APPROVE_UNVERIFIABLE_GATES" in _codes(_GOOD_APPROVE, _ti(gate_conclusions={}))


def test_approve_with_empty_ratified_criteria_fails_closed():
    assert "MISSING_RATIFIED_CRITERIA" in _codes(_GOOD_APPROVE, _ti(required_criteria=()))


def test_approve_with_empty_required_gates_fails_closed():
    assert "MISSING_RATIFIED_GATES" in _codes(_GOOD_APPROVE, _ti(required_gates=()))


# =========================================================================
# The fabricated self-attested APPROVE — rejected on every axis.
# =========================================================================

def test_fabricated_selfattested_approval_is_rejected():
    fabricated = {
        "pr": "#EVIL",
        "verdict": "APPROVE",
        "reviewer": "the-builder",
        "reviewed_sha": "0" * 40,
        "pr_head_sha": "0" * 40,
        "final_commit_committed_at": _FINAL_AT,
        "spec_conformance": [{"criterion_id": "TOTALLY#MADE#UP", "verdict": "met", "evidence_ref": "trust me"}],
        "findings": [],
        "gates": [{"name": "conservation-lane1", "status": "pass"}],
        "evidence": [],
    }
    trusted = _ti(
        gate_conclusions={"conservation-lane1": "failure"},
        review_actor="the-builder", review_state="COMMENTED", review_commit_id="0" * 40,
    )
    codes = {v.code for v in validate_review(fabricated, CONTRACT, trusted)}
    for expected in ("STALE_REVIEW_SHA", "HEAD_MISMATCH", "UNKNOWN_CRITERION",
                     "INCOMPLETE_SPEC_CONFORMANCE", "EMPTY_EVIDENCE", "UNRESOLVED_EVIDENCE_REF",
                     "GATE_CONCLUSION_MISMATCH", "REQUIRED_GATE_NOT_PASSED",
                     "REVIEWER_NOT_TRUSTED", "REVIEW_NOT_APPROVED", "REVIEW_STALE_SHA"):
        assert expected in codes, (expected, codes)


# =========================================================================
# Structural rules (unchanged) still reject their violation.
# =========================================================================

def test_empty_evidence_rejected():
    assert "EMPTY_EVIDENCE" in _codes(_mut(evidence=[]))


def test_all_na_criteria_rejected_when_not_permitted():
    art = _mut(spec_conformance=[
        {"criterion_id": "SPEC_X#1", "verdict": "n/a", "evidence_ref": "-"},
        {"criterion_id": "SPEC_X#2", "verdict": "n/a", "evidence_ref": "-"},
    ])
    assert "NA_NOT_PERMITTED" in _codes(art)


def test_unknown_criterion_rejected():
    art = _mut(spec_conformance=[
        {"criterion_id": "SPEC_X#1", "verdict": "met", "evidence_ref": "ev-tests"},
        {"criterion_id": "SPEC_X#2", "verdict": "n/a", "evidence_ref": "-"},
        {"criterion_id": "PADDING#99", "verdict": "met", "evidence_ref": "ev-tests"},
    ])
    assert "UNKNOWN_CRITERION" in _codes(art)


def test_incomplete_criterion_set_rejected():
    art = _mut(spec_conformance=[{"criterion_id": "SPEC_X#1", "verdict": "met", "evidence_ref": "ev-tests"}])
    assert "INCOMPLETE_SPEC_CONFORMANCE" in _codes(art)


def test_duplicate_criterion_rejected():
    art = _mut(spec_conformance=[
        {"criterion_id": "SPEC_X#1", "verdict": "met", "evidence_ref": "ev-tests"},
        {"criterion_id": "SPEC_X#1", "verdict": "met", "evidence_ref": "ev-tests"},
        {"criterion_id": "SPEC_X#2", "verdict": "n/a", "evidence_ref": "-"},
    ])
    assert "DUPLICATE_CRITERION" in _codes(art)


def test_malformed_sha_rejected():
    assert "MALFORMED_SHA" in _codes(_mut(reviewed_sha="abc1234"))


def test_stale_review_sha_rejected():
    assert "STALE_REVIEW_SHA" in _codes(_mut(reviewed_sha=_OTHER))


def test_head_mismatch_rejected():
    assert "HEAD_MISMATCH" in _codes(_mut(pr_head_sha=_OTHER))


def test_unresolved_evidence_ref_rejected():
    art = _mut(spec_conformance=[
        {"criterion_id": "SPEC_X#1", "verdict": "met", "evidence_ref": "does-not-exist"},
        {"criterion_id": "SPEC_X#2", "verdict": "n/a", "evidence_ref": "-"},
    ])
    assert "UNRESOLVED_EVIDENCE_REF" in _codes(art)


def test_empty_evidence_ref_rejected():
    art = _mut(
        spec_conformance=[
            {"criterion_id": "SPEC_X#1", "verdict": "met", "evidence_ref": "ev-tests"},
            {"criterion_id": "SPEC_X#2", "verdict": "n/a", "evidence_ref": "-"},
        ],
        evidence=[{"id": "ev-tests", "ref": "   ", "produced_at": "2026-08-14T10:05:00+00:00"}],
    )
    codes = _codes(art)
    assert "MALFORMED_EVIDENCE" in codes and "UNRESOLVED_EVIDENCE_REF" in codes


def test_future_evidence_rejected():
    art = _mut(evidence=[{"id": "ev-tests", "ref": "x", "produced_at": "2027-01-01T00:00:00+00:00"}])
    assert "FUTURE_EVIDENCE" in _codes(art)


def test_evidence_before_final_commit_rejected():
    art = _mut(evidence=[{"id": "ev-tests", "ref": "old run", "produced_at": "2026-08-14T09:00:00+00:00"}])
    assert "STALE_EVIDENCE" in _codes(art)


def test_malformed_gate_status_rejected():
    assert "MALFORMED_GATE" in _codes(_mut(gates=[{"name": "g", "status": "greenish"}]))


def test_malformed_finding_severity_rejected():
    art = _mut(findings=[{"id": "F1", "severity": "meh", "must_fix": False, "resolved": False}])
    assert "MALFORMED_FINDING" in _codes(art)


import pytest


@pytest.mark.parametrize("badval", [{}, None, "x", 5, 3.14, True])
def test_non_list_findings_rejected(badval):
    """A present-but-non-list 'findings' must fail closed — else the isinstance(list) guard
    silently skips open-MUST accounting (the review's malformed-collection false-green)."""
    assert "MALFORMED_FINDING" in _codes(_mut(findings=badval)), badval


@pytest.mark.parametrize("badval", [{}, None, "x", 5, 3.14, True])
def test_non_list_gates_rejected(badval):
    """Same fail-closed rule for 'gates' — a non-list bypasses the declared-gate structural checks."""
    assert "MALFORMED_GATE" in _codes(_mut(gates=badval)), badval


def test_unknown_verdict_rejected():
    assert "UNKNOWN_VERDICT" in _codes(_mut(verdict="APPROVE-WITH-NITS"))


def test_approve_with_failing_gate_rejected():
    art = _mut(gates=[{"name": "conservation-lane1", "status": "fail"}])
    assert "APPROVE_WITH_FAILING_GATE" in _codes(art)


def test_missing_spec_conformance_matrix_rejected():
    assert "MISSING_SPEC_CONFORMANCE" in _codes(_mut(spec_conformance=[]))


def test_missing_required_field_rejected():
    art = _mut()
    del art["gates"]
    assert "MISSING_FIELD" in _codes(art)


def test_malformed_spec_item_rejected():
    art = _mut(spec_conformance=[{"criterion_id": "X", "verdict": "probably", "evidence_ref": "y"}])
    assert "MALFORMED_SPEC_ITEM" in _codes(art)


def test_violations_are_typed():
    for v in validate_review(PRIV001_LAND_WITH_NITS, CONTRACT, _PRIV001_TRUSTED):
        assert isinstance(v, Violation)
        assert v.code and v.message


# =========================================================================
# Contract ↔ review-gate.md must not drift; trusted reviewer is pinned.
# =========================================================================

def test_valid_verdicts_match_review_gate_command():
    from pathlib import Path
    import re
    root = Path(__file__).resolve().parents[1]
    text = (root / ".claude" / "commands" / "review-gate.md").read_text(encoding="utf-8")
    m = re.search(r"\*\*([A-Z][A-Z-]+(?:\s*/\s*[A-Z][A-Z-]+)+)\*\*", text)
    assert m, "could not find the verdict set in review-gate.md"
    gate_verdicts = {v.strip() for v in m.group(1).split("/")}
    assert gate_verdicts == set(CONTRACT["valid_verdicts"]), (
        f"drift: review-gate.md={gate_verdicts} contract={set(CONTRACT['valid_verdicts'])}"
    )


def test_contract_pins_the_trusted_independent_reviewer():
    assert CONTRACT.get("trusted_independent_reviewer") == "codexindependentreviewer[bot]"


# =========================================================================
# Co-review round (2026-08-17) — blocker/MUST accounting and reviewer/run binding.
# Each reproduces a confirmed finding that validated clean before the fix.
# =========================================================================

def test_approve_with_unresolved_blocker_regardless_of_must_fix_flag():
    """FINDING #1: an unresolved 'blocker' severity finding must count as an open MUST even when
    must_fix is false/omitted. Before the fix this APPROVE validated clean."""
    art = _mut(findings=[{"id": "B1", "severity": "blocker", "must_fix": False, "resolved": False}])
    codes = _codes(art)
    assert "APPROVE_WITH_OPEN_MUST" in codes, codes
    assert "CONTRADICTORY_FINDING" in codes, codes  # blocker + must_fix:false is itself contradictory


def test_unresolved_must_severity_counts_as_open_must():
    art = _mut(findings=[{"id": "M1", "severity": "must", "must_fix": False, "resolved": False}])
    assert "APPROVE_WITH_OPEN_MUST" in _codes(art)


def test_non_boolean_must_fix_is_malformed():
    art = _mut(findings=[{"id": "F1", "severity": "should", "must_fix": "no", "resolved": False}])
    assert "MALFORMED_FINDING" in _codes(art)


def test_non_boolean_resolved_does_not_clear_a_blocker():
    """A truthy non-bool 'resolved' must not silently clear a blocker (it is malformed AND still open)."""
    art = _mut(findings=[{"id": "B1", "severity": "blocker", "must_fix": True, "resolved": "yes"}])
    codes = _codes(art)
    assert "MALFORMED_FINDING" in codes and "APPROVE_WITH_OPEN_MUST" in codes


def test_reviewer_id_mismatch_rejected():
    """FINDING #3: the right login with the WRONG numeric id must fail (a login can be spoofed)."""
    assert "REVIEWER_ID_MISMATCH" in _codes(_GOOD_APPROVE, _ti(review_actor_id=999999))


def test_reviewer_id_unverified_fails_closed():
    assert "REVIEWER_ID_UNVERIFIED" in _codes(_GOOD_APPROVE, _ti(review_actor_id=None))


def test_reviewer_not_bot_rejected():
    assert "REVIEWER_NOT_BOT" in _codes(_GOOD_APPROVE, _ti(review_actor_type="User"))


def test_approve_without_run_binding_fails_closed():
    """FINDING #3: an APPROVE not bound to a concrete CI run has no auditable conclusions."""
    assert "MISSING_RUN_BINDING" in _codes(_GOOD_APPROVE, _ti(run_id=None))


def test_contract_pins_the_reviewer_numeric_id():
    assert CONTRACT.get("trusted_independent_reviewer_id") == 317626643


# =========================================================================
# 2026-08-20 correction round — two independent reviews found adjacent fail-open
# cases: the payload gate set was decorative, and reviewer identity was still
# partially fail-open. Each mutation validated CLEAN before these fixes.
# =========================================================================

# WP12#2 — the review-of-record payload must HONESTLY enumerate every required gate exactly once
# with status 'pass'. Understating a required gate (omit / skip / fail / duplicate / unknown) is a
# vacuous-green signal even though trusted.gate_conclusions remains the real authority.

def test_approve_payload_omitting_required_gate_rejected():
    assert "REQUIRED_GATE_ABSENT_IN_PAYLOAD" in _codes(_mut(gates=[]))


def test_approve_payload_required_gate_marked_skip_rejected():
    art = _mut(gates=[{"name": "conservation-lane1", "status": "skip"}])
    assert "REQUIRED_GATE_NOT_PASS_IN_PAYLOAD" in _codes(art)


def test_approve_payload_duplicate_required_gate_rejected():
    art = _mut(gates=[{"name": "conservation-lane1", "status": "pass"},
                      {"name": "conservation-lane1", "status": "pass"}])
    assert "DUPLICATE_GATE_IN_PAYLOAD" in _codes(art)


def test_approve_payload_unknown_gate_rejected():
    art = _mut(gates=[{"name": "conservation-lane1", "status": "pass"},
                      {"name": "not-a-required-gate", "status": "pass"}])
    assert "UNKNOWN_GATE_IN_PAYLOAD" in _codes(art)


def test_good_approve_with_exact_required_gate_set_still_valid():
    """The honest payload (every required gate exactly once, all pass) must stay clean."""
    assert validate_review(_GOOD_APPROVE, CONTRACT, _TRUSTED) == []


# WP12#7 — reviewer identity must fail closed on a MISSING account type (not only a wrong type).
# (A GitHub App-id pin was considered and REMOVED by owner ruling 2026-08-20 — GitHub's pull-review
# API does not expose performed_via_github_app, so it was an unenforceable control; identity is
# bound by login + the immutable bot-account id (317626643) + account type == 'Bot'.)

def test_reviewer_type_missing_fails_closed():
    """A pinned reviewer id with NO account type from the review API must fail closed — a None
    actor_type slipped past the `is not None` guard before (fail-open)."""
    assert "REVIEWER_TYPE_UNVERIFIED" in _codes(_GOOD_APPROVE, _ti(review_actor_type=None))


def test_no_app_id_field_on_trusted_inputs():
    """The removed App-id pin leaves no trace: constructing TrustedInputs with an app-id kwarg is a
    TypeError, and a good APPROVE still validates on login + account-id + type alone."""
    import pytest as _pytest
    with _pytest.raises(TypeError):
        _ti(trusted_reviewer_app_id=4614805)
    assert validate_review(_GOOD_APPROVE, CONTRACT, _TRUSTED) == []
