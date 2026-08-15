"""WP-12B — typed review-artifact validator (SPEC_WP12 §3 WP-12B), hardened twice.

The validator reconciles a structured review artifact against the WP-12A contract AND against
TrustedInputs — the real PR head SHA, commit time, the ratified criterion/gate set, the REAL
check conclusions, and the reviewer/author identities, all sourced OUTSIDE the artifact. It is
the machine that would have caught the PRIV-001 escaped defect.

Round-2 hardening (independent review of 1b4be50): the artifact's self-declared gate 'pass'
and 'author' are not external truth; a review committed inside the branch cannot equal the
head; an APPROVE needs an independent reviewer and real 'success' gate conclusions.
"""
from __future__ import annotations

import copy

from assurance.review_artifact import load_contract, validate_review, TrustedInputs, Violation

CONTRACT = load_contract()

_HEAD = "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678"
_OTHER = "ffffffffffffffffffffffffffffffffffffffff"
_PARENT = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
_FINAL_AT = "2026-08-14T10:00:00+00:00"
_NOW = "2026-08-14T12:00:00+00:00"

# TrustedInputs matching the good APPROVE below — the external truth the review reconciles to.
_TRUSTED = TrustedInputs(
    pr_head_sha=_HEAD,
    final_commit_committed_at=_FINAL_AT,
    required_criteria=("SPEC_X#1", "SPEC_X#2"),
    required_gates=("conservation-lane1",),
    na_allowed_criteria=("SPEC_X#2",),
    now=_NOW,
    gate_conclusions={"conservation-lane1": "success"},
    reviewer_login="independent-reviewer",
    pr_author_login="the-builder",
)

_GOOD_APPROVE = {
    "pr": "#999",
    "verdict": "APPROVE",
    "reviewer": "independent-reviewer",
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
_PRIV001_TRUSTED = TrustedInputs(
    pr_head_sha=_PRIV001_HEAD,
    final_commit_committed_at="2026-08-13T10:00:00+00:00",
    required_criteria=("SPEC_HANDOFF_001#H1.1.4", "SPEC_HANDOFF_001#H1.1.min-tests"),
    gate_conclusions={"conservation-lane1": "success"},
    reviewer_login="independent-reviewer",
    pr_author_login="the-builder",
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


def test_good_approve_in_evidence_commit_mode_is_valid():
    """Evidence-only-commit model: reviewed_sha == the review commit's parent; head is the
    evidence commit; nothing outside assurance/reviews/ changed."""
    art = _mut(reviewed_sha=_PARENT, pr_head_sha=_HEAD)
    trusted = TrustedInputs(
        pr_head_sha=_HEAD, final_commit_committed_at=_FINAL_AT,
        required_criteria=("SPEC_X#1", "SPEC_X#2"), required_gates=("conservation-lane1",),
        na_allowed_criteria=("SPEC_X#2",), now=_NOW,
        gate_conclusions={"conservation-lane1": "success"},
        reviewer_login="independent-reviewer", pr_author_login="the-builder",
        artifact_commit_parent=_PARENT, head_is_evidence_only=True,
    )
    assert validate_review(art, CONTRACT, trusted) == []


def test_changes_required_with_open_items_is_valid():
    art = _mut(
        verdict="CHANGES-REQUIRED",
        spec_conformance=[{"criterion_id": "SPEC_X#1", "verdict": "unmet", "evidence_ref": "x"}],
        findings=[{"id": "F1", "severity": "must", "must_fix": True, "resolved": False}],
    )
    assert validate_review(art, CONTRACT, trusted=None) == []


# =========================================================================
# Round-2 hardening: external truth beats self-attestation.
# =========================================================================

def test_gate_pass_contradicting_real_conclusion_rejected():
    """A self-declared gate 'pass' whose REAL conclusion is failure is a lie."""
    trusted = TrustedInputs(
        pr_head_sha=_HEAD, final_commit_committed_at=_FINAL_AT,
        required_criteria=("SPEC_X#1", "SPEC_X#2"), required_gates=("conservation-lane1",),
        na_allowed_criteria=("SPEC_X#2",), now=_NOW,
        gate_conclusions={"conservation-lane1": "failure"},
        reviewer_login="independent-reviewer", pr_author_login="the-builder",
    )
    codes = {v.code for v in validate_review(_GOOD_APPROVE, CONTRACT, trusted)}
    assert "GATE_CONCLUSION_MISMATCH" in codes, codes
    assert "REQUIRED_GATE_NOT_PASSED" in codes, codes


def test_required_gate_real_conclusion_absent_rejected():
    trusted = TrustedInputs(
        pr_head_sha=_HEAD, final_commit_committed_at=_FINAL_AT,
        required_criteria=("SPEC_X#1", "SPEC_X#2"), required_gates=("conservation-lane1",),
        na_allowed_criteria=("SPEC_X#2",), now=_NOW,
        gate_conclusions={"some-other-check": "success"},
        reviewer_login="independent-reviewer", pr_author_login="the-builder",
    )
    art = _mut(gates=[{"name": "conservation-lane1", "status": "skip"}])
    assert "REQUIRED_GATE_NOT_PASSED" in {v.code for v in validate_review(art, CONTRACT, trusted)}


def test_approve_with_no_real_conclusions_fails_closed():
    trusted = TrustedInputs(
        pr_head_sha=_HEAD, final_commit_committed_at=_FINAL_AT,
        required_criteria=("SPEC_X#1", "SPEC_X#2"), required_gates=("conservation-lane1",),
        na_allowed_criteria=("SPEC_X#2",), now=_NOW,
        gate_conclusions={}, reviewer_login="independent-reviewer", pr_author_login="the-builder",
    )
    assert "APPROVE_UNVERIFIABLE_GATES" in {v.code for v in validate_review(_GOOD_APPROVE, CONTRACT, trusted)}


def test_reviewer_equals_author_is_not_independent():
    trusted = TrustedInputs(
        pr_head_sha=_HEAD, final_commit_committed_at=_FINAL_AT,
        required_criteria=("SPEC_X#1", "SPEC_X#2"), required_gates=("conservation-lane1",),
        na_allowed_criteria=("SPEC_X#2",), now=_NOW,
        gate_conclusions={"conservation-lane1": "success"},
        reviewer_login="the-builder", pr_author_login="the-builder",
    )
    art = _mut(reviewer="the-builder")
    assert "REVIEWER_NOT_INDEPENDENT" in {v.code for v in validate_review(art, CONTRACT, trusted)}


def test_declared_reviewer_mismatch_rejected():
    assert "REVIEWER_MISMATCH" in _codes(_mut(reviewer="someone-else"))


def test_approve_without_reviewer_identity_rejected():
    trusted = TrustedInputs(
        pr_head_sha=_HEAD, final_commit_committed_at=_FINAL_AT,
        required_criteria=("SPEC_X#1", "SPEC_X#2"), required_gates=("conservation-lane1",),
        na_allowed_criteria=("SPEC_X#2",), now=_NOW,
        gate_conclusions={"conservation-lane1": "success"},
        reviewer_login=None, pr_author_login="the-builder",
    )
    assert "MISSING_REVIEWER" in {v.code for v in validate_review(_GOOD_APPROVE, CONTRACT, trusted)}


def test_evidence_commit_unbound_rejected():
    """reviewed_sha must equal the review commit's parent in evidence-commit mode."""
    trusted = TrustedInputs(
        pr_head_sha=_HEAD, final_commit_committed_at=_FINAL_AT,
        required_criteria=("SPEC_X#1", "SPEC_X#2"), required_gates=("conservation-lane1",),
        na_allowed_criteria=("SPEC_X#2",), now=_NOW,
        gate_conclusions={"conservation-lane1": "success"},
        reviewer_login="independent-reviewer", pr_author_login="the-builder",
        artifact_commit_parent=_OTHER, head_is_evidence_only=True,   # parent != reviewed_sha
    )
    art = _mut(reviewed_sha=_PARENT, pr_head_sha=_HEAD)
    assert "EVIDENCE_COMMIT_UNBOUND" in {v.code for v in validate_review(art, CONTRACT, trusted)}


def test_code_changed_after_review_rejected():
    trusted = TrustedInputs(
        pr_head_sha=_HEAD, final_commit_committed_at=_FINAL_AT,
        required_criteria=("SPEC_X#1", "SPEC_X#2"), required_gates=("conservation-lane1",),
        na_allowed_criteria=("SPEC_X#2",), now=_NOW,
        gate_conclusions={"conservation-lane1": "success"},
        reviewer_login="independent-reviewer", pr_author_login="the-builder",
        artifact_commit_parent=_PARENT, head_is_evidence_only=False,  # code changed after review
    )
    art = _mut(reviewed_sha=_PARENT, pr_head_sha=_HEAD)
    assert "CODE_CHANGED_AFTER_REVIEW" in {v.code for v in validate_review(art, CONTRACT, trusted)}


def test_fabricated_selfattested_approval_is_rejected():
    """The round-1 headline defect, now also with lying gate + non-independent reviewer."""
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
    trusted = TrustedInputs(
        pr_head_sha=_HEAD, final_commit_committed_at=_FINAL_AT,
        required_criteria=("SPEC_X#1", "SPEC_X#2"), required_gates=("conservation-lane1",),
        na_allowed_criteria=("SPEC_X#2",), now=_NOW,
        gate_conclusions={"conservation-lane1": "failure"},
        reviewer_login="the-builder", pr_author_login="the-builder",
    )
    codes = {v.code for v in validate_review(fabricated, CONTRACT, trusted)}
    for expected in ("STALE_REVIEW_SHA", "HEAD_MISMATCH", "UNKNOWN_CRITERION",
                     "INCOMPLETE_SPEC_CONFORMANCE", "EMPTY_EVIDENCE", "UNRESOLVED_EVIDENCE_REF",
                     "GATE_CONCLUSION_MISMATCH", "REQUIRED_GATE_NOT_PASSED", "REVIEWER_NOT_INDEPENDENT"):
        assert expected in codes, (expected, codes)


# =========================================================================
# Structural rules (unchanged) still reject their violation
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


def test_future_evidence_rejected():
    art = _mut(evidence=[{"id": "ev-tests", "ref": "x", "produced_at": "2027-01-01T00:00:00+00:00"}])
    assert "FUTURE_EVIDENCE" in _codes(art)


def test_approve_without_trusted_fails_closed():
    assert "UNVERIFIABLE_APPROVE" in _codes(_GOOD_APPROVE, trusted=None)


def test_evidence_before_final_commit_rejected():
    art = _mut(evidence=[{"id": "ev-tests", "ref": "old run", "produced_at": "2026-08-14T09:00:00+00:00"}])
    assert "STALE_EVIDENCE" in _codes(art)


def test_malformed_gate_status_rejected():
    assert "MALFORMED_GATE" in _codes(_mut(gates=[{"name": "g", "status": "greenish"}]))


def test_malformed_finding_severity_rejected():
    art = _mut(findings=[{"id": "F1", "severity": "meh", "must_fix": False, "resolved": False}])
    assert "MALFORMED_FINDING" in _codes(art)


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
# Contract ↔ review-gate.md must not drift
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
