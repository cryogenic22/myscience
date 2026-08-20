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
        Reconcile the review of record — the typed JSON payload in the trusted bot's GitHub
        review BODY (NOT a file committed to the branch; that was self-referential) — against
        the LIVE PR head. The review's own commit_id (external) must equal the head, so the
        payload directly covers it. Gate conclusions come from the REAL job results (passed in
        from GitHub needs.*.result); reviewer/author identities come from the GitHub review API.
        Fails CLOSED if the PR head cannot be resolved externally (no local-HEAD fallback), if
        the trusted reviewer has no review, if the review body carries no parseable payload, or
        on any validation violation.

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


def pr_author(pr: str, repo: str | None) -> str | None:
    """PR author login from GitHub (external truth)."""
    base = ["gh", "pr", "view", str(pr)]
    if repo:
        base += ["--repo", repo]
    return _run(base + ["--json", "author", "-q", ".author.login"])


def independent_review(pr: str, repo: str | None, expected_reviewer: str) -> dict | None:
    """Externally-grounded review reconciliation (replaces the old pr_identities()).

    Fetch the review submitted by the ONE trusted reviewer identity via the GitHub reviews API
    and return {actor, state, commit_id, dismissed, body}. `body` carries the typed JSON review
    payload (the review of record — NOT a file committed to the branch). If the reviewer has
    multiple reviews, take the LATEST. Returns None if the trusted reviewer has no review — the
    caller then fails closed. Querying by the trusted actor means a COMMENTED/other-actor review
    can never be mistaken for the approval.
    """
    endpoint = f"repos/{repo}/pulls/{pr}/reviews" if repo else None
    if not endpoint:
        # No repo → cannot address the API deterministically; fail closed upstream.
        return None
    raw = _run(["gh", "api", "--paginate", endpoint])
    if raw is None:
        return None
    try:
        reviews = json.loads(raw)
    except json.JSONDecodeError:
        return None
    mine = [r for r in reviews if (r.get("user") or {}).get("login") == expected_reviewer]
    if not mine:
        return None
    r = mine[-1]  # latest review by the trusted reviewer
    state = r.get("state")
    user = r.get("user") or {}
    return {
        "actor": user.get("login"),
        # Numeric id + account type bind the reviewer to the pinned App bot, not just a login
        # string (a login is weaker; the id cannot be reassigned). Verified in the validator.
        "actor_id": user.get("id"),
        "actor_type": user.get("type"),
        "state": state,
        "commit_id": r.get("commit_id"),
        "dismissed": state == "DISMISSED",
        "body": r.get("body") or "",
    }


def _no_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    """object_pairs_hook that REJECTS duplicate keys. Default json.loads is last-wins, so
    {"verdict":"CHANGES-REQUIRED", ..., "verdict":"APPROVE"} silently becomes APPROVE — a
    contradictory payload must never parse to a single believed value."""
    seen: dict = {}
    for k, v in pairs:
        if k in seen:
            raise ValueError(f"duplicate key {k!r} in review payload (contradictory)")
        seen[k] = v
    return seen


def parse_review_payload(body: str) -> dict | None:
    """Extract the typed JSON review payload from a GitHub review body. Accepts a body that is
    pure JSON, or JSON inside a ```json … ``` (or bare ``` … ```) fenced block. Fails CLOSED
    (returns None) on: no parseable object, a payload with DUPLICATE KEYS, or AMBIGUITY — two or
    more DISTINCT JSON objects in the body (e.g. one CHANGES-REQUIRED block and one APPROVE
    block). Silently taking the first/last of contradictory payloads is exactly the bypass an
    edited review body could exploit; ambiguity is never resolved in the author's favour."""
    if not body:
        return None
    import re
    candidates = [body.strip()]
    for m in re.finditer(r"```(?:json)?\s*(.+?)```", body, re.DOTALL | re.IGNORECASE):
        candidates.append(m.group(1).strip())
    distinct: list[dict] = []
    for cand in candidates:
        try:
            obj = json.loads(cand, object_pairs_hook=_no_duplicate_keys)
        except json.JSONDecodeError:
            continue  # not JSON at all (prose, a non-JSON fence) — simply not a candidate
        except ValueError:
            # _no_duplicate_keys raised: a JSON-looking but CONTRADICTORY candidate (duplicate keys).
            # Silently discarding it while another valid block wins is the exact bypass an edited
            # review body could exploit — poison the WHOLE body (require ONE unambiguous payload).
            return None
        if isinstance(obj, dict) and not any(obj == d for d in distinct):
            distinct.append(obj)
    if len(distinct) != 1:
        return None  # 0 = no payload; >1 = ambiguous — both fail closed
    return distinct[0]


def load_manifest(path: Path | None = None) -> dict:
    return json.loads((path or MANIFEST_PATH).read_text(encoding="utf-8"))


def build_trusted(pr: str, manifest: dict, contract: dict, *, head_sha: str,
                  gate_conclusions: dict[str, str], pr_author_login: str | None,
                  review: dict | None, run_id: str | None, committed_at: str | None = None,
                  now: str | None = None) -> TrustedInputs:
    entry = manifest["prs"][str(pr)]
    review = review or {}
    return TrustedInputs(
        pr_head_sha=head_sha,
        # committed-at of the head itself (the review targets the live head directly). Resolved
        # by the caller and passed in — the caller fails closed if it cannot be resolved, so this
        # is never a silent None that would skip the freshness check.
        final_commit_committed_at=committed_at if committed_at is not None else commit_time(head_sha),
        required_criteria=tuple(c["id"] for c in entry["criteria"]),
        required_gates=tuple(entry.get("required_gates", ())),
        na_allowed_criteria=tuple(entry.get("na_allowed", ())),
        now=now or datetime.now(timezone.utc).isoformat(),
        gate_conclusions=gate_conclusions,
        pr_author_login=pr_author_login,
        trusted_reviewer_login=contract.get("trusted_independent_reviewer"),
        trusted_reviewer_id=contract.get("trusted_independent_reviewer_id"),
        review_actor=review.get("actor"),
        review_actor_id=review.get("actor_id"),
        review_actor_type=review.get("actor_type"),
        review_state=review.get("state"),
        review_commit_id=review.get("commit_id"),
        review_dismissed=bool(review.get("dismissed")),
        run_id=run_id,
    )


# --------------------------------------------------------------------------- self-test (non-vacuous)
_SELFTEST_HEAD = "1234567890abcdef1234567890abcdef12345678"
_SELFTEST_BOT = "codexindependentreviewer[bot]"
_SELFTEST_BOT_ID = 317626643
_SELFTEST_TRUSTED = TrustedInputs(
    pr_head_sha=_SELFTEST_HEAD,
    final_commit_committed_at="2026-08-14T10:00:00+00:00",
    required_criteria=("C#1", "C#2"),
    required_gates=("gate-a",),
    na_allowed_criteria=("C#2",),
    now="2026-08-14T12:00:00+00:00",
    gate_conclusions={"gate-a": "success"},
    pr_author_login="the-builder",
    trusted_reviewer_login=_SELFTEST_BOT,
    trusted_reviewer_id=_SELFTEST_BOT_ID,
    review_actor=_SELFTEST_BOT,                 # trusted reviewer
    review_actor_id=_SELFTEST_BOT_ID,           # pinned numeric id (not just the login)
    review_actor_type="Bot",                    # a GitHub App bot
    review_state="APPROVED",                    # APPROVED
    review_commit_id=_SELFTEST_HEAD,            # targets the exact head
    review_dismissed=False,
    run_id="selftest-run-1",                    # conclusions bound to a concrete run
)
_SELFTEST_GOOD = {
    "verdict": "APPROVE",
    "reviewer": _SELFTEST_BOT,
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
    pr_author_login="the-builder",
    trusted_reviewer_login=_SELFTEST_BOT,
    review_actor="the-builder",                 # wrong actor AND == author
    review_state="COMMENTED",                   # not APPROVED
    review_commit_id="0" * 40,                   # stale vs head
    review_dismissed=False,
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

    # Author + commit time are authority facts (reviewer-independence and evidence freshness
    # depend on them). If GitHub/git cannot resolve them, FAIL CLOSED — passing None here would
    # make the validator SKIP those checks (§9c / REVIEWER_NOT_INDEPENDENT), a silent fail-open.
    author = pr_author(args.pr, args.repo)
    if not author:
        print(f"[assurance.check] MERGE BLOCKED: could not resolve the author of PR {args.pr} "
              f"externally (gh pr view) — reviewer independence cannot be verified (fail closed).")
        return 1
    committed_at = commit_time(head)
    if not committed_at:
        print(f"[assurance.check] MERGE BLOCKED: could not resolve the committed-at time of head "
              f"{head} externally (git show) — evidence freshness cannot be verified (fail closed).")
        return 1

    expected_reviewer = contract.get("trusted_independent_reviewer")
    if not expected_reviewer:
        print("[assurance.check] FAIL CLOSED: contract has no trusted_independent_reviewer.")
        return 1
    review = independent_review(args.pr, args.repo, expected_reviewer)

    # The review of record is the typed JSON payload in the trusted bot's review BODY — not a
    # file committed to the branch (that would be self-referential). No review → fail closed.
    if not review:
        print(f"[assurance.check] MERGE BLOCKED: no review by {expected_reviewer!r} on PR "
              f"{args.pr} (fail closed).")
        return 1
    payload = parse_review_payload(review.get("body", ""))
    if payload is None:
        print(f"[assurance.check] MERGE BLOCKED: the {expected_reviewer!r} review body carries no "
              f"parseable typed JSON review payload (fail closed).")
        return 1

    # Real gate conclusions from the CI job results (GitHub needs.*.result), never the payload.
    gate_conclusions: dict[str, str] = {}
    if args.kernel_result:
        gate_conclusions["assurance-kernel"] = args.kernel_result
    if args.conservation_result:
        gate_conclusions["conservation-lane1"] = args.conservation_result

    trusted = build_trusted(
        args.pr, manifest, contract, head_sha=head,
        gate_conclusions=gate_conclusions, pr_author_login=author,
        review=review, run_id=args.run_id, committed_at=committed_at,
    )
    review_meta = {k: review.get(k) for k in ("actor", "actor_id", "actor_type", "state", "commit_id", "dismissed")}
    print(f"[assurance.check] author={author!r} expected_reviewer={expected_reviewer!r} "
          f"review={review_meta} gate_conclusions={gate_conclusions}")

    viols = list(validate_review(payload, contract, trusted))
    if args.require_verdict and payload.get("verdict") != args.require_verdict:
        viols.append(Violation("VERDICT_NOT_REQUIRED",
                               f"verdict {payload.get('verdict')!r} != required {args.require_verdict!r}"))
    if viols:
        _print_violations(f"PR-{args.pr} review body", viols)
        return 1
    # Do NOT claim "ratified": the manifest status may still be owner-review-pending (the bar is
    # not owner-ratified until the protected-surface change is approved). Report status honestly.
    manifest_status = manifest.get("status", "unknown")
    print(f"[assurance.check] PR-{args.pr} review-body payload: VALID against the acceptance "
          f"criteria (manifest status: {manifest_status}) + real check conclusions + independent "
          f"APPROVE at head {head}.")
    return 0


# --------------------------------------------------------------------------- main
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="assurance.check", description=__doc__)
    ap.add_argument("--self-test", action="store_true", help="prove the gate is non-vacuous")
    ap.add_argument("--merge-gate", action="store_true",
                    help="reconcile the trusted bot's review-body payload against the live head")
    ap.add_argument("--pr", help="PR number (keys into the acceptance manifest)")
    ap.add_argument("--head-sha", help="trusted PR head SHA (overrides env/gh)")
    ap.add_argument("--repo", help="owner/repo for gh")
    ap.add_argument("--manifest", help="override acceptance manifest path")
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
