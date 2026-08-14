#!/usr/bin/env python3
"""WP-12B/WP-12A — executable review-artifact gate (the CI dogfood).

A Markdown review table is not a machine artifact. This CLI is the enforcement seam: it
assembles ``TrustedInputs`` from sources OUTSIDE any review artifact (git / the GitHub event
for the head SHA + commit time; the owner-ratified acceptance manifest for the criterion +
required-gate set), then runs the WP-12B validator against a structured JSON review artifact
and exits non-zero on any violation.

Usage:
    python -m assurance.check --self-test
        Prove the gate is NOT vacuous: a bundled fabricated APPROVE MUST be rejected and a
        bundled well-formed APPROVE MUST be accepted. Exits non-zero if either inverts. Runs
        on every CI invocation so a gate that checks nothing fails closed (principle #3).

    python -m assurance.check --artifact assurance/reviews/PR-327.json --pr 327 \
        [--head-sha <40hex>] [--repo owner/repo] [--require-verdict APPROVE]
        Validate a real review artifact. Head SHA resolution order (first wins, source is
        printed): --head-sha  >  $ASSURANCE_HEAD_SHA  >  `gh pr view <pr> --json headRefOid`
        >  `git rev-parse HEAD`. Commit time comes from `git show -s --format=%cI`.

Exit codes: 0 = valid; 1 = violations / vacuous-gate failure; 2 = usage / IO error.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
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
    """Return (sha, source). External truth only — never the artifact."""
    import os
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
        if sha:
            return sha, "gh pr view"
    sha = _run(["git", "rev-parse", "HEAD"])
    return (sha, "git rev-parse HEAD") if sha else (None, "unresolved")


def commit_time(sha: str | None) -> str | None:
    if not sha:
        return None
    return _run(["git", "show", "-s", "--format=%cI", sha])


def load_manifest(path: Path | None = None) -> dict:
    return json.loads((path or MANIFEST_PATH).read_text(encoding="utf-8"))


def build_trusted(pr: str, head_sha: str | None, manifest: dict, now: str | None = None) -> TrustedInputs:
    entry = manifest["prs"][str(pr)]
    return TrustedInputs(
        pr_head_sha=head_sha or "",
        final_commit_committed_at=commit_time(head_sha),
        required_criteria=tuple(c["id"] for c in entry["criteria"]),
        required_gates=tuple(entry.get("required_gates", ())),
        na_allowed_criteria=tuple(entry.get("na_allowed", ())),
        now=now or datetime.now(timezone.utc).isoformat(),
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
)
_SELFTEST_GOOD = {
    "verdict": "APPROVE",
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
    "reviewed_sha": "0" * 40,
    "pr_head_sha": "0" * 40,
    "final_commit_committed_at": "2026-08-14T10:00:00+00:00",
    "spec_conformance": [{"criterion_id": "MADE#UP", "verdict": "met", "evidence_ref": "trust me"}],
    "findings": [],
    "gates": [{"name": "gate-a", "status": "skip"}],
    "evidence": [],
}


def self_test(contract: dict) -> list[str]:
    """Return a list of failures (empty == the gate has teeth)."""
    failures: list[str] = []
    good = validate_review(_SELFTEST_GOOD, contract, _SELFTEST_TRUSTED)
    if good:
        failures.append(f"VACUOUS: a well-formed APPROVE was rejected: {[v.code for v in good]}")
    fab = validate_review(_SELFTEST_FABRICATED, contract, _SELFTEST_TRUSTED)
    if not fab:
        failures.append("VACUOUS: a fabricated self-attested APPROVE was ACCEPTED (gate checks nothing)")
    return failures


# --------------------------------------------------------------------------- main
def _print_violations(where: str, viols: list[Violation]) -> None:
    print(f"[assurance.check] {where}: {len(viols)} violation(s)")
    for v in viols:
        print(f"  - {v.code}: {v.message}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="assurance.check", description=__doc__)
    ap.add_argument("--self-test", action="store_true", help="prove the gate is non-vacuous")
    ap.add_argument("--artifact", help="path to a structured JSON review artifact")
    ap.add_argument("--pr", help="PR number (keys into the acceptance manifest)")
    ap.add_argument("--head-sha", help="trusted PR head SHA (overrides env/gh/git)")
    ap.add_argument("--repo", help="owner/repo for `gh pr view`")
    ap.add_argument("--manifest", help="override acceptance manifest path")
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
        if not args.artifact:
            return 0

    if not args.artifact:
        ap.error("nothing to do: pass --artifact and --pr, or --self-test")

    if not args.pr:
        ap.error("--artifact requires --pr (to key the ratified manifest)")

    try:
        artifact = json.loads(Path(args.artifact).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"[assurance.check] cannot read artifact {args.artifact}: {e}")
        return 2

    try:
        manifest = load_manifest(Path(args.manifest) if args.manifest else None)
    except (OSError, json.JSONDecodeError) as e:
        print(f"[assurance.check] cannot read manifest: {e}")
        return 2
    if str(args.pr) not in manifest["prs"]:
        print(f"[assurance.check] no ratified manifest entry for PR {args.pr}")
        return 2

    head_sha, source = resolve_head_sha(args.pr, args.head_sha, args.repo)
    print(f"[assurance.check] trusted PR head = {head_sha} (source: {source})")
    if not head_sha:
        print("[assurance.check] FAIL CLOSED: could not resolve a trusted PR head SHA externally.")
        return 1

    trusted = build_trusted(args.pr, head_sha, manifest)
    viols = validate_review(artifact, contract, trusted)

    if args.require_verdict and artifact.get("verdict") != args.require_verdict:
        viols = list(viols) + [Violation("VERDICT_NOT_REQUIRED",
                                         f"verdict {artifact.get('verdict')!r} != required {args.require_verdict!r}")]

    if viols:
        _print_violations(args.artifact, viols)
        return 1
    print(f"[assurance.check] {args.artifact}: VALID against PR-{args.pr} ratified criteria at {head_sha}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
