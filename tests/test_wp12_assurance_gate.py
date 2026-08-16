"""WP-12A/B — the executable assurance gate (dogfood), hermetic.

Proves the enforcement seam is real and non-vacuous WITHOUT the network:
  1. assurance.check.self_test has teeth — a fabricated APPROVE is rejected AND a well-formed
     APPROVE is accepted (a gate that inverts either way is vacuous, principle #3).
  2. The acceptance manifest is well-formed and its PR-327 criteria match SPEC_WP12 §5.
  3. The review-artifact TEMPLATE validates structurally (the format is real, not a Markdown table).
  4. resolve_head_sha fails CLOSED on an unresolvable --pr (no local-HEAD fallback), and the
     evidence-only-commit detector classifies diffs correctly — the round-2 review's blockers.
"""
from __future__ import annotations

import json
from pathlib import Path

import assurance.check as chk
from assurance.check import self_test, load_manifest
from assurance.review_artifact import TrustedInputs, load_contract, validate_review

REPO_ROOT = Path(__file__).resolve().parents[1]
REVIEWS_DIR = REPO_ROOT / "assurance" / "reviews"
CONTRACT = load_contract()
MANIFEST = load_manifest()
_FAR_FUTURE = "2100-01-01T00:00:00+00:00"


def test_selftest_is_non_vacuous():
    assert self_test(CONTRACT) == []


def test_selftest_would_fail_if_gate_were_vacuous(monkeypatch):
    monkeypatch.setattr(chk, "validate_review", lambda *a, **k: [])
    failures = chk.self_test(CONTRACT)
    assert any("VACUOUS" in f for f in failures), failures


def test_manifest_wellformed():
    assert MANIFEST["prs"], "manifest lists no PRs (fail-closed)"
    for pr, entry in MANIFEST["prs"].items():
        assert entry.get("criteria"), f"PR {pr} has no criteria"
        ids = [c["id"] for c in entry["criteria"]]
        assert len(ids) == len(set(ids)), f"PR {pr} has duplicate criterion ids"
        assert entry.get("required_gates"), f"PR {pr} declares no required gates (fail-closed)"


def test_pr327_manifest_matches_spec_section():
    entry = MANIFEST["prs"]["327"]
    assert len(entry["criteria"]) == 7, entry["criteria"]
    spec = (REPO_ROOT / "specs" / "SPEC_WP12_assurance_kernel.md").read_text(encoding="utf-8")
    assert entry["spec"].split("#")[0] == "specs/SPEC_WP12_assurance_kernel.md"
    assert "## 5. Acceptance criteria" in spec


def test_manifest_status_is_not_overclaimed():
    """Blocker 7: the manifest must not claim owner-ratified while the spec is DRAFT."""
    assert MANIFEST.get("status") == "owner-review-pending"
    assert "owner-ratified" not in MANIFEST["description"].lower()


def test_review_template_validates_structurally():
    """The evidence-only-commit TEMPLATE is a real, machine-checkable artifact (not a table)."""
    tpl = json.loads((REVIEWS_DIR / "TEMPLATE.json").read_text(encoding="utf-8"))
    ids = tuple(c["criterion_id"] for c in tpl["spec_conformance"])
    trusted = TrustedInputs(
        pr_head_sha=tpl["pr_head_sha"],
        required_criteria=ids,
        artifact_commit_parent=tpl["reviewed_sha"],   # evidence-commit parent == reviewed_sha
        head_is_evidence_only=True,
        now=_FAR_FUTURE,
    )
    violations = validate_review(tpl, CONTRACT, trusted)
    assert violations == [], [f"{v.code}: {v.message}" for v in violations]


def test_no_builder_authored_verdict_artifact_present():
    """The self-referential builder artifact is gone; only the TEMPLATE + README remain here.
    Real PR-<n>.json verdicts are added later by the independent reviewer in an evidence commit."""
    names = {p.name for p in REVIEWS_DIR.glob("*") if p.is_file()}
    assert names == {"TEMPLATE.json", "README.md"}, names


# ---- CLI external-truth behaviour (blocker 3 + the evidence-only detector) ----

def test_resolve_head_sha_fails_closed_on_unresolvable_pr(monkeypatch):
    """--pr given but GitHub cannot resolve it -> (None, ...), NEVER a local-HEAD fallback."""
    monkeypatch.setattr(chk, "_run", lambda cmd: None)   # every git/gh call fails
    sha, source = chk.resolve_head_sha(pr="999999", explicit=None, repo="owner/repo")
    assert sha is None and source == "gh-unresolved", (sha, source)


def test_resolve_head_sha_prefers_explicit(monkeypatch):
    monkeypatch.setattr(chk, "_run", lambda cmd: "SHOULD_NOT_BE_USED")
    sha, source = chk.resolve_head_sha(pr="1", explicit="deadbeef", repo=None)
    assert sha == "deadbeef" and source == "--head-sha"


def test_head_is_evidence_only_true_for_reviews_only_diff(monkeypatch):
    monkeypatch.setattr(chk, "_run", lambda cmd: "assurance/reviews/PR-1.json")
    assert chk.head_is_evidence_only("aaa", "bbb") is True


def test_head_is_evidence_only_false_when_code_changed(monkeypatch):
    monkeypatch.setattr(chk, "_run", lambda cmd: "assurance/reviews/PR-1.json\nservices/llm.py")
    assert chk.head_is_evidence_only("aaa", "bbb") is False


def test_head_is_evidence_only_true_for_empty_diff(monkeypatch):
    monkeypatch.setattr(chk, "_run", lambda cmd: "")
    assert chk.head_is_evidence_only("aaa", "aaa") is True


# ---- independent_review(): externally-grounded review fetch (replaces pr_identities) ----

_BOT = "codexindependentreviewer[bot]"


def _reviews_json(*reviews):
    return json.dumps(list(reviews))


def test_independent_review_extracts_trusted_reviewers_latest(monkeypatch):
    """Picks the LATEST review by the trusted actor and extracts actor/state/commit_id/dismissed."""
    payload = _reviews_json(
        {"user": {"login": "someone"}, "state": "COMMENTED", "commit_id": "x"},
        {"user": {"login": _BOT}, "state": "CHANGES_REQUESTED", "commit_id": "old"},
        {"user": {"login": _BOT}, "state": "APPROVED", "commit_id": "headsha"},
    )
    monkeypatch.setattr(chk, "_run", lambda cmd: payload)
    r = chk.independent_review("1", "owner/repo", _BOT)
    assert r == {"actor": _BOT, "state": "APPROVED", "commit_id": "headsha", "dismissed": False}


def test_independent_review_flags_dismissed(monkeypatch):
    payload = _reviews_json({"user": {"login": _BOT}, "state": "DISMISSED", "commit_id": "h"})
    monkeypatch.setattr(chk, "_run", lambda cmd: payload)
    r = chk.independent_review("1", "owner/repo", _BOT)
    assert r["state"] == "DISMISSED" and r["dismissed"] is True


def test_independent_review_ignores_other_actors(monkeypatch):
    """A COMMENTED/APPROVED review by a NON-trusted actor is never returned as the approval."""
    payload = _reviews_json({"user": {"login": "attacker"}, "state": "APPROVED", "commit_id": "h"})
    monkeypatch.setattr(chk, "_run", lambda cmd: payload)
    assert chk.independent_review("1", "owner/repo", _BOT) is None


def test_independent_review_none_when_no_reviews(monkeypatch):
    monkeypatch.setattr(chk, "_run", lambda cmd: "[]")
    assert chk.independent_review("1", "owner/repo", _BOT) is None


def test_independent_review_fails_closed_without_repo(monkeypatch):
    """No repo → cannot address the reviews API deterministically → None (caller fails closed)."""
    monkeypatch.setattr(chk, "_run", lambda cmd: (_ for _ in ()).throw(AssertionError("must not call gh")))
    assert chk.independent_review("1", None, _BOT) is None
