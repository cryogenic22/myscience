"""WP-12A/B — the executable assurance gate (dogfood), hermetic.

Proves the enforcement seam is real and non-vacuous WITHOUT touching the network:
  1. assurance.check.self_test has teeth — a fabricated APPROVE is rejected AND a well-formed
     APPROVE is accepted (a gate that inverts either way is vacuous, principle #3).
  2. The acceptance manifest is well-formed and its PR-327 criteria match SPEC_WP12 §5.
  3. Every committed structured review artifact (assurance/reviews/PR-*.json) reconciles
     against its ratified manifest entry — the Markdown PR table is not the artifact of record.

Live-head reconciliation (reviewed_sha == the current PR head from git/GitHub) is the CLI's
job at merge time (assurance/check.py --artifact ... --pr ...); it is intentionally NOT run
here because a self-committed artifact is one commit behind its own head.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from assurance.check import self_test, load_manifest
from assurance.review_artifact import TrustedInputs, load_contract, validate_review

REPO_ROOT = Path(__file__).resolve().parents[1]
REVIEWS_DIR = REPO_ROOT / "assurance" / "reviews"
CONTRACT = load_contract()
MANIFEST = load_manifest()

# Far-future so the timestamp checks are gated only by the artifact's OWN internal
# consistency (evidence >= final_commit), never by a wall clock this test cannot control.
_FAR_FUTURE = "2100-01-01T00:00:00+00:00"


def test_selftest_is_non_vacuous():
    """The CLI self-test must report zero failures: reject fixture rejected, accept accepted."""
    assert self_test(CONTRACT) == []


def test_selftest_would_fail_if_gate_were_vacuous(monkeypatch):
    """Meta-proof: if the validator suddenly accepted everything, self_test must catch it."""
    import assurance.check as chk
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
    """The manifest's PR-327 criteria count matches the 7 acceptance criteria in SPEC_WP12 §5."""
    entry = MANIFEST["prs"]["327"]
    assert len(entry["criteria"]) == 7, entry["criteria"]
    spec = (REPO_ROOT / "specs" / "SPEC_WP12_assurance_kernel.md").read_text(encoding="utf-8")
    assert entry["spec"].split("#")[0] == "specs/SPEC_WP12_assurance_kernel.md"
    assert "## 5. Acceptance criteria" in spec


def _committed_reviews() -> list[Path]:
    return sorted(REVIEWS_DIR.glob("PR-*.json")) if REVIEWS_DIR.exists() else []


def test_at_least_one_committed_review_artifact_exists():
    """Dogfood: there is a structured artifact of record, not just a Markdown table."""
    assert _committed_reviews(), "no assurance/reviews/PR-*.json artifact committed"


@pytest.mark.parametrize("path", _committed_reviews(), ids=lambda p: p.name)
def test_committed_review_artifact_reconciles(path: Path):
    """Each committed artifact must reconcile against its ratified manifest entry: enumerate
    every criterion, pass every required gate, resolve every 'met' evidence_ref, valid verdict.
    (Structural + criteria + gate reconciliation; live-head equality is the merge-gate's job.)"""
    artifact = json.loads(path.read_text(encoding="utf-8"))
    pr = str(artifact["pr"]).lstrip("#")
    assert pr in MANIFEST["prs"], f"{path.name}: no manifest entry for PR {pr}"
    entry = MANIFEST["prs"][pr]
    trusted = TrustedInputs(
        pr_head_sha=artifact["reviewed_sha"],           # self-consistent (not live-head)
        final_commit_committed_at=None,                 # commit-time equality is the CLI's job
        required_criteria=tuple(c["id"] for c in entry["criteria"]),
        required_gates=tuple(entry.get("required_gates", ())),
        na_allowed_criteria=tuple(entry.get("na_allowed", ())),
        now=_FAR_FUTURE,
    )
    violations = validate_review(artifact, CONTRACT, trusted)
    assert violations == [], [f"{v.code}: {v.message}" for v in violations]
