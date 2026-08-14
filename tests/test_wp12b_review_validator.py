"""WP-12B — typed review-artifact validator (SPEC_WP12 §3 WP-12B), hardened.

The validator reconciles a structured review artifact against the WP-12A machine acceptance
contract (assurance/contract/review_contract.json) AND against TrustedInputs — the real PR
head SHA, the final-commit timestamp, and the ratified criterion/gate set, all sourced OUTSIDE
the artifact. It is the machine that would have caught the PRIV-001 escaped defect: a live
LLM-egress bypass classified as a review "nit" under the non-canonical verdict
"LAND-WITH-NITS" (ESC-2026-08-13-priv001-spec-conformance).

This file also pins the hardening an independent review found missing in the first pass:
self-attested equal SHAs, fabricated criteria, empty evidence, and a required gate marked
'skip' must ALL be rejected, and an APPROVE with no external truth fails closed.

RED→GREEN: the validator is exercised against fixtures that were accepted before hardening.
"""
from __future__ import annotations

import copy

from assurance.review_artifact import load_contract, validate_review, TrustedInputs, Violation

CONTRACT = load_contract()

# 40-hex placeholder SHAs (the format the hardened validator requires).
_HEAD = "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678"
_OTHER = "ffffffffffffffffffffffffffffffffffffffff"
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
)

# --- Base well-formed APPROVE (all ratified criteria enumerated, evidence resolves) ---
_GOOD_APPROVE = {
    "pr": "#999",
    "verdict": "APPROVE",
    "reviewed_sha": _HEAD,
    "pr_head_sha": _HEAD,
    "final_commit_committed_at": _FINAL_AT,
    "spec_conformance": [
        {"criterion_id": "SPEC_X#1", "verdict": "met", "evidence_ref": "ev-tests"},
        {"criterion_id": "SPEC_X#2", "verdict": "n/a", "evidence_ref": "not applicable"},
    ],
    "findings": [
        {"id": "F1", "severity": "nit", "must_fix": False, "resolved": False},
    ],
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
# The escaped-defect replay — MUST be rejected (this is the whole point).
# =========================================================================

# Exactly what the PRIV-001 review produced: a non-canonical verdict on a slice that left
# ratified criterion H1.1.4 UNMET, with an open MUST for a live raw-Anthropic bypass.
# NOTE: reviewed_sha is #326's REAL head (gh pr view 326 -> a66dbcba...), corrected from the
# earlier fixture's 5bc8806 (which was actually the later priv-001b WIP branch tip).
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
    "findings": [
        {"id": "F1", "severity": "must", "must_fix": True, "resolved": False},
    ],
    "gates": [{"name": "conservation-lane1", "status": "pass"}],
    "evidence": [{"id": "ev1", "ref": "pytest tests/test_llm_gateway.py",
                  "produced_at": "2026-08-13T11:00:00+00:00"}],
}
_PRIV001_TRUSTED = TrustedInputs(
    pr_head_sha=_PRIV001_HEAD,
    final_commit_committed_at="2026-08-13T10:00:00+00:00",
    required_criteria=("SPEC_HANDOFF_001#H1.1.4", "SPEC_HANDOFF_001#H1.1.min-tests"),
)


def test_priv001_land_with_nits_is_rejected():
    """The exact escaped incident: 'LAND-WITH-NITS' is not a canonical verdict."""
    codes = {v.code for v in validate_review(PRIV001_LAND_WITH_NITS, CONTRACT, _PRIV001_TRUSTED)}
    assert "UNKNOWN_VERDICT" in codes, codes


def test_priv001_even_as_approve_is_rejected_on_unmet_criterion():
    """Even a valid verdict cannot APPROVE over an unmet ratified criterion or an open MUST."""
    coerced = dict(PRIV001_LAND_WITH_NITS, verdict="APPROVE")
    codes = {v.code for v in validate_review(coerced, CONTRACT, _PRIV001_TRUSTED)}
    assert "APPROVE_WITH_UNMET_CRITERION" in codes, codes
    assert "APPROVE_WITH_OPEN_MUST" in codes, codes


# =========================================================================
# Positive cases
# =========================================================================

def test_good_approve_is_valid():
    assert validate_review(_GOOD_APPROVE, CONTRACT, _TRUSTED) == []


def test_changes_required_with_open_items_is_valid():
    """CHANGES-REQUIRED may carry unmet criteria + open MUSTs — that's its job. It does not
    merge anything, so it does not require TrustedInputs to reconcile."""
    art = _mut(
        verdict="CHANGES-REQUIRED",
        spec_conformance=[{"criterion_id": "SPEC_X#1", "verdict": "unmet", "evidence_ref": "x"}],
        findings=[{"id": "F1", "severity": "must", "must_fix": True, "resolved": False}],
    )
    assert validate_review(art, CONTRACT, trusted=None) == []


# =========================================================================
# Hardening: the fabricated-approval classes an independent review found accepted.
# =========================================================================

def test_fabricated_selfattested_approval_is_rejected():
    """The review's headline defect: fake equal SHAs + invented criterion 'met' + empty
    evidence + a required gate 'skip' validated CLEAN. It must now fail on every axis."""
    fabricated = {
        "pr": "#EVIL",
        "verdict": "APPROVE",
        "reviewed_sha": "0" * 40,          # equals pr_head_sha but NOT the trusted head
        "pr_head_sha": "0" * 40,
        "final_commit_committed_at": _FINAL_AT,
        "spec_conformance": [{"criterion_id": "TOTALLY#MADE#UP", "verdict": "met", "evidence_ref": "trust me"}],
        "findings": [],
        "gates": [{"name": "conservation-lane1", "status": "skip"}],
        "evidence": [],
    }
    codes = _codes(fabricated)
    assert "STALE_REVIEW_SHA" in codes, codes            # reviewed_sha != trusted head
    assert "HEAD_MISMATCH" in codes, codes               # self-reported head != trusted head
    assert "UNKNOWN_CRITERION" in codes, codes           # invented criterion
    assert "INCOMPLETE_SPEC_CONFORMANCE" in codes, codes # ratified criteria not enumerated
    assert "EMPTY_EVIDENCE" in codes, codes              # no proof
    assert "REQUIRED_GATE_NOT_PASSED" in codes, codes    # required gate skipped
    assert "UNRESOLVED_EVIDENCE_REF" in codes, codes     # 'met' cites nothing real


def test_empty_evidence_rejected():
    assert "EMPTY_EVIDENCE" in _codes(_mut(evidence=[]))


def test_required_gate_skip_does_not_satisfy():
    assert "REQUIRED_GATE_NOT_PASSED" in _codes(_mut(gates=[{"name": "conservation-lane1", "status": "skip"}]))


def test_required_gate_absent_rejected():
    assert "REQUIRED_GATE_NOT_PASSED" in _codes(_mut(gates=[{"name": "unrelated", "status": "pass"}]))


def test_all_na_criteria_rejected_when_not_permitted():
    art = _mut(spec_conformance=[
        {"criterion_id": "SPEC_X#1", "verdict": "n/a", "evidence_ref": "-"},
        {"criterion_id": "SPEC_X#2", "verdict": "n/a", "evidence_ref": "-"},
    ])
    assert "NA_NOT_PERMITTED" in _codes(art)   # SPEC_X#1 is not in na_allowed


def test_unknown_criterion_rejected():
    art = _mut(spec_conformance=[
        {"criterion_id": "SPEC_X#1", "verdict": "met", "evidence_ref": "ev-tests"},
        {"criterion_id": "SPEC_X#2", "verdict": "n/a", "evidence_ref": "-"},
        {"criterion_id": "PADDING#99", "verdict": "met", "evidence_ref": "ev-tests"},
    ])
    assert "UNKNOWN_CRITERION" in _codes(art)


def test_incomplete_criterion_set_rejected():
    art = _mut(spec_conformance=[{"criterion_id": "SPEC_X#1", "verdict": "met", "evidence_ref": "ev-tests"}])
    assert "INCOMPLETE_SPEC_CONFORMANCE" in _codes(art)   # SPEC_X#2 missing


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
    """A well-formed SHA that is not the trusted head is stale."""
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
    """An APPROVE that cannot be reconciled against external truth is not believed."""
    assert "UNVERIFIABLE_APPROVE" in _codes(_GOOD_APPROVE, trusted=None)


def test_evidence_before_final_commit_rejected():
    art = _mut(evidence=[{"id": "ev-tests", "ref": "old run", "produced_at": "2026-08-14T09:00:00+00:00"}])
    assert "STALE_EVIDENCE" in _codes(art)


def test_malformed_gate_status_rejected():
    assert "MALFORMED_GATE" in _codes(_mut(gates=[{"name": "g", "status": "greenish"}]))


def test_malformed_finding_severity_rejected():
    art = _mut(findings=[{"id": "F1", "severity": "meh", "must_fix": False, "resolved": False}])
    assert "MALFORMED_FINDING" in _codes(art)


# =========================================================================
# Each original contract rule still rejects its violation
# =========================================================================

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
