#!/usr/bin/env python3
"""WP-12B/WP-12A — executable review-artifact gate (the CI dogfood).

A Markdown review table is not a machine artifact, and a review artifact's own values are not
external truth. This CLI is the enforcement seam. It assembles ``TrustedInputs`` from sources
OUTSIDE any review artifact — git + the GitHub API for the head SHA, the reviewed-commit time,
the real check conclusions, and the reviewer/author identities; the owner-ratified acceptance
manifest for the criterion + required-gate set — then runs the WP-12B validator and exits
non-zero on any violation.

Modes:
    python -m assurance.check --self-test
        Prove the gate is NOT vacuous: a bundled fabricated APPROVE MUST be rejected and a
        bundled well-formed APPROVE MUST be accepted. Runs every CI invocation (principle #3).

    python -m assurance.check --merge-gate --pr <n> --repo <owner/repo> \
        --kernel-result <success|failure|...> --conservation-result <...> [--run-id <id>] \
        [--require-verdict APPROVE]
        Reconcile the independent-review artifact (assurance/reviews/PR-<n>.json) against the
        LIVE PR head. The review is an evidence-only commit whose PARENT is the reviewed code
        (reviewed_sha == parent); the head must change nothing outside assurance/reviews/.
        Gate conclusions come from the REAL job results (passed in from GitHub needs.*.result);
        the reviewer identity comes from `gh pr view`. Fails CLOSED if the PR cannot be
        resolved, if no artifact exists, or on any violation. There is NO local-HEAD fallback
        when --pr is supplied.

Exit codes: 0 = valid; 1 = violations / fail-closed; 2 = usage / IO error.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from assurance.review_artifact import (
    TrustedInputs,
    Violation,
    load_contract,
    validate_review,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "assurance" / "contract" / "acceptance_manifest.json"
REVIEWS_DIR = REPO_ROOT / "assurance" / "reviews"


# --------------------------------------------------------------------------- git/gh helpers
def _run(cmd: list[str]) -> str | None:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    return r.stdout.strip() or None


def resolve_head_sha(pr: str | None, explicit: str | None, repo: str | None) -> tuple[str | None, str]:
    """Return (sha, source). External truth only. When --pr is given and GitHub cannot resolve
    it, return (None, ...) — NEVER fall back to local HEAD (that would let a local checkout
    stand in for the real PR head)."""
    if explicit:
        return explicit, "--head-sha"
    env = os.environ.get("ASSURANCE_HEAD_SHA")
    if env:
        return env, "$ASSURANCE_HEAD_SHA"
    if pr:
        cmd = ["gh", "pr", "view", str(pr), "--json", "headRefOid", "-q", ".headRefOid"]
        if repo:
            cmd[3:3] = ["--repo", repo]
        sha = _run(cmd)
        return (sha, "gh pr view") if sha else (None, "gh-unresolved")
    sha = _run(["git", "rev-parse", "HEAD"])
    return (sha, "git rev-parse HEAD") if sha else (None, "unresolved")


def commit_time(sha: str | None) -> str | None:
    return _run(["git", "show", "-s", "--format=%cI", sha]) if sha else None


def artifact_commit_parent(path: Path) -> str | None:
    """Parent SHA of the commit that last introduced/changed the review artifact."""
    rel = path.relative_to(REPO_ROOT).as_posix()
    c = _run(["git", "log", "-1", "--format=%H", "--", rel])
    return _run(["git", "rev-parse", f"{c}^"]) if c else None


def head_is_evidence_only(reviewed_sha: str | None, head: str | None) -> bool | None:
    """True iff reviewed_sha..head touches ONLY assurance/reviews/ (no code changed after review)."""
    if not reviewed_sha or not head:
        return None
    out = _run(["git", "diff", "--name-only", f"{reviewed_sha}..{head}"])
    if out is None:
        return None
    files = [f for f in out.splitlines() if f.strip()]
    return all(f.startswith("assurance/reviews/") for f in files) if files else True


def pr_identities(pr: str, repo: str | None) -> tuple[str | None, str | None]:
    """(reviewer_login, pr_author_login) from GitHub — the independent reviewer and PR author."""
    base = ["gh", "pr", "view", str(pr)]
    if repo:
        base += ["--repo", repo]
    author = _run(base + ["--json", "author", "-q", ".author.login"])
    reviewer = _run(base + ["--json", "reviews", "-q",
                            '[.reviews[] | select(.author.login != null)] | last | .author.login'])
    return reviewer, author


def load_manifest(path: Path | None = None) -> dict:
    return json.loads((path or MANIFEST_PATH).read_text(encoding="utf-8"))


def build_trusted(pr: str, manifest: dict, *, head_sha: str, reviewed_sha: str,
                  gate_conclusions: dict[str, str], reviewer_login: str | None,
                  pr_author_login: str | None, artifact_parent: str | None,
                  evidence_only: bool | None, run_id: str | None, now: str | None = None) -> TrustedInputs:
    entry = manifest["prs"][str(pr)]
    return TrustedInputs(
        pr_head_sha=head_sha,
        final_commit_committed_at=commit_time(reviewed_sha),
        required_criteria=tuple(c["id"] for c in entry["criteria"]),
        required_gates=tuple(entry.get("required_gates", ())),
        na_allowed_criteria=tuple(entry.get("na_allowed", ())),
        now=now or datetime.now(timezone.utc).isoformat(),
        gate_conclusions=gate_conclusions,
        reviewer_login=reviewer_login,
        pr_author_login=pr_author_login,
        artifact_commit_parent=artifact_parent,
        head_is_evidence_only=evidence_only,
        run_id=run_id,
    )


# --------------------------------------------------------------------------- self-test (non-vacuous)
_SELFTEST_HEAD = "1234567890abcdef1234567890abcdef12345678"
_SELFTEST_TRUSTED = TrustedInputs(
    pr_head_sha=_SELFTEST_HEAD,
    final_commit_committed_at="2026-08-14T10:00:00+00:00",
    required_criteria=("C#1", "C#2"),
    required_gates=("gate-a",),
    na_allowed_criteria=("C#2",),
    now="2026-08-14T12:00:00+00:00",
    gate_conclusions={"gate-a": "success"},
    reviewer_login="independent-reviewer",
    pr_author_login="the-builder",
)
_SELFTEST_GOOD = {
    "verdict": "APPROVE",
    "reviewer": "independent-reviewer",
    "reviewed_sha": _SELFTEST_HEAD,
    "pr_head_sha": _SELFTEST_HEAD,
    "final_commit_committed_at": "2026-08-14T10:00:00+00:00",
    "spec_conformance": [
        {"criterion_id": "C#1", "verdict": "met", "evidence_ref": "ev1"},
        {"criterion_id": "C#2", "verdict": "n/a", "evidence_ref": "-"},
    ],
    "findings": [],
    "gates": [{"name": "gate-a", "status": "pass"}],
    "evidence": [{"id": "ev1", "ref": "pytest -q", "produced_at": "2026-08-14T10:05:00+00:00"}],
}
_SELFTEST_FABRICATED = {
    "verdict": "APPROVE",
    "reviewer": "the-builder",                 # the author reviewing their own PR
    "reviewed_sha": "0" * 40,
    "pr_head_sha": "0" * 40,
    "final_commit_committed_at": "2026-08-14T10:00:00+00:00",
    "spec_conformance": [{"criterion_id": "MADE#UP", "verdict": "met", "evidence_ref": "trust me"}],
    "findings": [],
    "gates": [{"name": "gate-a", "status": "pass"}],   # claims pass; real conclusion below differs
    "evidence": [],
}
_SELFTEST_FAB_TRUSTED = TrustedInputs(
    pr_head_sha=_SELFTEST_HEAD,
    required_criteria=("C#1", "C#2"),
    required_gates=("gate-a",),
    na_allowed_criteria=("C#2",),
    now="2026-08-14T12:00:00+00:00",
    gate_conclusions={"gate-a": "failure"},    # GitHub says the gate FAILED; artifact lied
    reviewer_login="the-builder",
    pr_author_login="the-builder",             # reviewer == author (not independent)
)


def self_test(contract: dict) -> list[str]:
    """Return a list of failures (empty == the gate has teeth)."""
    failures: list[str] = []
    good = validate_review(_SELFTEST_GOOD, contract, _SELFTEST_TRUSTED)
    if good:
        failures.append(f"VACUOUS: a well-formed APPROVE was rejected: {[v.code for v in good]}")
    fab = validate_review(_SELFTEST_FABRICATED, contract, _SELFTEST_FAB_TRUSTED)
    if not fab:
        failures.append("VACUOUS: a fabricated self-attested APPROVE was ACCEPTED (gate checks nothing)")
    return failures


# --------------------------------------------------------------------------- merge gate
def _print_violations(where: str, viols: list[Violation]) -> None:
    print(f"[assurance.check] {where}: {len(viols)} violation(s)")
    for v in viols:
        print(f"  - {v.code}: {v.message}")


def run_merge_gate(args) -> int:
    contract = load_contract()
    try:
        manifest = load_manifest(Path(args.manifest) if args.manifest else None)
    except (OSError, json.JSONDecodeError) as e:
        print(f"[assurance.check] cannot read manifest: {e}")
        return 2
    if str(args.pr) not in manifest["prs"]:
        print(f"[assurance.check] FAIL CLOSED: no ratified manifest entry for PR {args.pr}")
        return 1

    head, source = resolve_head_sha(args.pr, args.head_sha, args.repo)
    if not head:
        print(f"[assurance.check] FAIL CLOSED: could not resolve PR {args.pr} head externally "
              f"(source: {source}) — refusing to fall back to local HEAD.")
        return 1
    print(f"[assurance.check] trusted PR head = {head} (source: {source})")

    artifact_path = Path(args.artifact) if args.artifact else (REVIEWS_DIR / f"PR-{args.pr}.json")
    if not artifact_path.exists():
        print(f"[assurance.check] MERGE BLOCKED: no independent-review artifact at "
              f"{artifact_path.relative_to(REPO_ROOT).as_posix()} (fail closed).")
        return 1
    try:
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"[assurance.check] cannot parse artifact: {e}")
        return 2

    parent = artifact_commit_parent(artifact_path)
    reviewed_sha = parent or head
    evidence_only = head_is_evidence_only(reviewed_sha, head)
    reviewer, author = pr_identities(args.pr, args.repo)

    # Real gate conclusions from the CI job results (GitHub needs.*.result), never the artifact.
    gate_conclusions: dict[str, str] = {}
    if args.kernel_result:
        gate_conclusions["assurance-kernel"] = args.kernel_result
    if args.conservation_result:
        gate_conclusions["conservation-lane1"] = args.conservation_result

    trusted = build_trusted(
        args.pr, manifest, head_sha=head, reviewed_sha=reviewed_sha,
        gate_conclusions=gate_conclusions, reviewer_login=reviewer, pr_author_login=author,
        artifact_parent=parent, evidence_only=evidence_only, run_id=args.run_id,
    )
    print(f"[assurance.check] reviewed_sha(parent)={parent} evidence_only={evidence_only} "
          f"reviewer={reviewer!r} author={author!r} gate_conclusions={gate_conclusions}")

    viols = list(validate_review(artifact, contract, trusted))
    if args.require_verdict and artifact.get("verdict") != args.require_verdict:
        viols.append(Violation("VERDICT_NOT_REQUIRED",
                               f"verdict {artifact.get('verdict')!r} != required {args.require_verdict!r}"))
    if viols:
        _print_violations(artifact_path.name, viols)
        return 1
    print(f"[assurance.check] {artifact_path.name}: VALID against PR-{args.pr} ratified criteria "
          f"+ real check conclusions at head {head}.")
    return 0


# --------------------------------------------------------------------------- main
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="assurance.check", description=__doc__)
    ap.add_argument("--self-test", action="store_true", help="prove the gate is non-vacuous")
    ap.add_argument("--merge-gate", action="store_true", help="reconcile the PR's review artifact against live head")
    ap.add_argument("--pr", help="PR number (keys into the acceptance manifest)")
    ap.add_argument("--head-sha", help="trusted PR head SHA (overrides env/gh)")
    ap.add_argument("--repo", help="owner/repo for gh")
    ap.add_argument("--manifest", help="override acceptance manifest path")
    ap.add_argument("--artifact", help="override review artifact path")
    ap.add_argument("--kernel-result", help="real conclusion of the assurance-kernel job (needs.*.result)")
    ap.add_argument("--conservation-result", help="real conclusion of the conservation-lane1 job")
    ap.add_argument("--run-id", help="CI run id binding the conclusions to a concrete execution")
    ap.add_argument("--require-verdict", help="also require the artifact verdict == this (merge gate)")
    args = ap.parse_args(argv)

    contract = load_contract()

    if args.self_test:
        failures = self_test(contract)
        if failures:
            for f in failures:
                print(f"[assurance.check] {f}")
            return 1
        print("[assurance.check] self-test OK - reject fixture rejected, accept fixture accepted (non-vacuous).")
        if not args.merge_gate:
            return 0

    if args.merge_gate:
        if not args.pr:
            ap.error("--merge-gate requires --pr")
        return run_merge_gate(args)

    if not args.self_test:
        ap.error("nothing to do: pass --self-test or --merge-gate --pr <n>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
