"""WP-12B — typed review-artifact validator (hardened).

Reconciles a structured review artifact against the WP-12A machine acceptance contract
(``assurance/contract/review_contract.json``) AND against ``TrustedInputs`` — facts sourced
OUTSIDE the artifact (git/GitHub for the real PR head SHA + final-commit timestamp; the
owner-ratified acceptance manifest for the canonical criterion set + required gates). Returns
a list of typed ``Violation``s; an empty list means the review satisfies the contract.

Why TrustedInputs exists (the defect an independent review found in the first pass): the
earlier validator compared ``reviewed_sha`` to ``pr_head_sha`` where BOTH came from the
artifact, and accepted any criterion IDs the artifact chose to list. A fabricated artifact —
equal fake SHAs, an invented criterion marked ``met``, empty evidence, a required gate marked
``skip`` — validated clean. Self-attestation is not verification. The binding facts now come
from external truth, and anything the validator cannot positively reconcile is a violation,
never a silent pass (**fail closed**).

This is the machine that would have rejected the PRIV-001 "LAND-WITH-NITS" review
(ESC-2026-08-13-priv001-spec-conformance).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CONTRACT_PATH = Path(__file__).resolve().parent / "contract" / "review_contract.json"

_SHA40 = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class Violation:
    code: str
    message: str


@dataclass(frozen=True)
class TrustedInputs:
    """Facts sourced OUTSIDE the review artifact. The validator believes the artifact's
    self-attested values (SHAs, gate ``status``, ``reviewer``) only insofar as they equal
    these. Nothing here is read from the artifact.

    - ``pr_head_sha``: the real PR head, from ``gh pr view`` / the GitHub event payload.
    - ``final_commit_committed_at``: committer date of the reviewed commit, from ``git show``.
    - ``required_criteria``: the canonical ratified acceptance-criterion IDs (from the
      owner-protected acceptance manifest) the review MUST enumerate — completely.
    - ``required_gates``: gate names that MUST have a real ``success`` conclusion for APPROVE.
    - ``na_allowed_criteria``: criteria the manifest explicitly permits to be ``n/a``.
    - ``now``: trusted current time (ISO-8601) for future-timestamp rejection.
    - ``gate_conclusions``: REAL check conclusions keyed by gate name (from GitHub check-runs /
      same-workflow ``needs.*.result``), e.g. ``{"assurance-kernel": "success"}``. The
      artifact's own ``gates[].status`` is NOT trusted — it is cross-checked against this.
    - ``pr_author_login``: the PR author's GitHub login (from ``gh pr view --json author``).
    - Independent-review binding (all sourced from GitHub's review API, NOT the artifact):
      ``trusted_reviewer_login`` = the ONE reviewer identity the contract accepts (the
      calibrated App bot, e.g. ``codexindependentreviewer[bot]``); ``review_actor`` = the login
      that actually submitted the review; ``review_state`` = APPROVED / CHANGES_REQUESTED /
      COMMENTED / DISMISSED; ``review_commit_id`` = the exact SHA the review targeted;
      ``review_dismissed`` = whether it was dismissed. An APPROVE is believed ONLY if the review
      is APPROVED, by the trusted reviewer, not the author, not dismissed, and targets the exact
      live head — anything else fails closed. (NOTE: this custom gate does NOT replace GitHub's
      native branch-protection approval; WP-12E still requires that separately.)
    - ``run_id``: the CI run id binding these conclusions to a concrete external execution.

    NOTE (Rev 4): the review of record is the typed JSON payload in the trusted bot's GitHub
    review BODY — NOT a file committed to the branch. That removes the self-reference of the
    old evidence-commit model (a committed artifact had to name the SHA of the commit that
    contained it). The reviewed SHA is the review's own ``commit_id`` (external truth from
    GitHub), which must equal the live head, so ``reviewed_sha`` in the payload is checked
    directly against ``pr_head_sha`` — there is no artifact-commit parent to bind.
    """
    pr_head_sha: str
    final_commit_committed_at: str | None = None
    required_criteria: tuple[str, ...] = ()
    required_gates: tuple[str, ...] = ()
    na_allowed_criteria: tuple[str, ...] = ()
    now: str | None = None
    gate_conclusions: dict[str, str] = field(default_factory=dict)
    pr_author_login: str | None = None
    # Independent-review binding (external truth from the GitHub review API):
    trusted_reviewer_login: str | None = None
    review_actor: str | None = None
    review_state: str | None = None
    review_commit_id: str | None = None
    review_dismissed: bool = False
    run_id: str | None = None


def load_contract(path: str | Path | None = None) -> dict:
    p = Path(path) if path else CONTRACT_PATH
    return json.loads(p.read_text(encoding="utf-8"))


def _parse_ts(value: Any) -> datetime | None:
    """Parse an ISO-8601 timestamp to an aware datetime (UTC if naive). None on failure."""
    if not isinstance(value, str):
        return None
    s = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def validate_review(
    artifact: Any,
    contract: dict,
    trusted: TrustedInputs | None = None,
) -> list[Violation]:
    """Validate a review artifact against the contract + trusted external inputs. [] == valid.

    Structural rules always run. Reconciliation rules (SHA == trusted head, criterion-set ==
    ratified set, required gates pass, n/a permitted, future-timestamp) run when ``trusted`` is
    provided. An APPROVE with no ``trusted`` cannot be reconciled and fails closed.
    """
    out: list[Violation] = []

    if not isinstance(artifact, dict):
        return [Violation("MALFORMED_ARTIFACT", f"review artifact must be an object, got {type(artifact).__name__}")]

    schema = contract["review_artifact_schema"]

    # 1. Required top-level fields present (fail closed on any absence).
    for f in schema["required_fields"]:
        if f not in artifact:
            out.append(Violation("MISSING_FIELD", f"required field '{f}' is absent"))

    verdict = artifact.get("verdict")

    # 2. Verdict is in the canonical closed set (rejects LAND-WITH-NITS / APPROVE-WITH-NITS).
    if verdict not in contract["valid_verdicts"]:
        out.append(Violation(
            "UNKNOWN_VERDICT",
            f"verdict {verdict!r} is not one of {contract['valid_verdicts']} "
            f"(interim per-slice dispositions are not valid final merge verdicts)",
        ))

    # 3. SHA fields must be well-formed 40-hex (reject fabricated short/non-hex SHAs).
    for f in ("reviewed_sha", "pr_head_sha"):
        v = artifact.get(f)
        if v is not None and not (isinstance(v, str) and _SHA40.match(v)):
            out.append(Violation("MALFORMED_SHA", f"{f} {v!r} is not a 40-hex lowercase git SHA"))

    # 4. spec-conformance matrix required, non-empty, well-formed; collect ids + dispositions.
    sc = artifact.get("spec_conformance")
    sc_item = schema["spec_conformance_item"]
    if contract["rules"].get("require_spec_conformance_matrix"):
        if not isinstance(sc, list) or not sc:
            out.append(Violation("MISSING_SPEC_CONFORMANCE",
                                 "a non-empty spec_conformance matrix is required"))
    criterion_dispositions: dict[str, str] = {}
    seen_ids: set[str] = set()
    unmet_criteria = 0
    if isinstance(sc, list):
        for i, item in enumerate(sc):
            if not isinstance(item, dict) or any(k not in item for k in sc_item["required_fields"]):
                out.append(Violation("MALFORMED_SPEC_ITEM",
                                     f"spec_conformance[{i}] missing required fields {sc_item['required_fields']}"))
                continue
            if item["verdict"] not in sc_item["allowed_verdicts"]:
                out.append(Violation("MALFORMED_SPEC_ITEM",
                                     f"spec_conformance[{i}].verdict {item['verdict']!r} not in {sc_item['allowed_verdicts']}"))
                continue
            cid = item["criterion_id"]
            if cid in seen_ids:
                out.append(Violation("DUPLICATE_CRITERION", f"criterion_id {cid!r} listed more than once"))
            seen_ids.add(cid)
            criterion_dispositions[cid] = item["verdict"]
            if item["verdict"] == "unmet":
                unmet_criteria += 1

    # 5. findings well-formed (incl. severity); count open MUSTs.
    findings = artifact.get("findings")
    f_item = schema["finding_item"]
    allowed_sev = set(f_item.get("allowed_severities", []))
    open_musts = 0
    if isinstance(findings, list):
        for i, item in enumerate(findings):
            if not isinstance(item, dict) or any(k not in item for k in f_item["required_fields"]):
                out.append(Violation("MALFORMED_FINDING",
                                     f"findings[{i}] missing required fields {f_item['required_fields']}"))
                continue
            if allowed_sev and item.get("severity") not in allowed_sev:
                out.append(Violation("MALFORMED_FINDING",
                                     f"findings[{i}].severity {item.get('severity')!r} not in {sorted(allowed_sev)}"))
            if item.get("must_fix") and not item.get("resolved"):
                open_musts += 1

    # 6. gates well-formed (incl. status); count failing; index by name.
    gates = artifact.get("gates")
    g_item = schema["gate_item"]
    allowed_status = set(g_item.get("allowed_status", []))
    gate_status: dict[str, str] = {}
    failing_gates = 0
    if isinstance(gates, list):
        for i, item in enumerate(gates):
            if not isinstance(item, dict) or any(k not in item for k in g_item["required_fields"]):
                out.append(Violation("MALFORMED_GATE",
                                     f"gates[{i}] missing required fields {g_item['required_fields']}"))
                continue
            if allowed_status and item["status"] not in allowed_status:
                out.append(Violation("MALFORMED_GATE",
                                     f"gates[{i}].status {item['status']!r} not in {sorted(allowed_status)}"))
                continue
            gate_status[item["name"]] = item["status"]
            if item["status"] == "fail":
                failing_gates += 1

    # 7. evidence: required non-empty; each item well-formed; build resolvable id set.
    evidence = artifact.get("evidence")
    ev_item = schema["evidence_item"]
    evidence_ids: set[str] = set()
    final_ts = _parse_ts(artifact.get("final_commit_committed_at"))
    now_ts = _parse_ts(trusted.now) if (trusted and trusted.now) else None
    if contract["rules"].get("evidence_required_nonempty") and (not isinstance(evidence, list) or not evidence):
        out.append(Violation("EMPTY_EVIDENCE", "a non-empty evidence list is required (no self-attestation without proof)"))
    if final_ts is None and "final_commit_committed_at" in artifact:
        out.append(Violation("MALFORMED_TIMESTAMP",
                             f"final_commit_committed_at is not ISO-8601: {artifact.get('final_commit_committed_at')!r}"))
    if now_ts is not None and final_ts is not None and final_ts > now_ts:
        out.append(Violation("FUTURE_FINAL_COMMIT",
                             f"final_commit_committed_at {artifact.get('final_commit_committed_at')} is in the future"))
    if isinstance(evidence, list):
        for i, item in enumerate(evidence):
            if not isinstance(item, dict) or any(k not in item for k in ev_item["required_fields"]):
                out.append(Violation("MALFORMED_EVIDENCE",
                                     f"evidence[{i}] missing required fields {ev_item['required_fields']}"))
                continue
            eid, eref = item["id"], item["ref"]
            if not (isinstance(eid, str) and eid.strip()) or not (isinstance(eref, str) and eref.strip()):
                out.append(Violation("MALFORMED_EVIDENCE",
                                     f"evidence[{i}] has an empty 'id' or 'ref' — a pointer with no content proves nothing"))
                continue
            evidence_ids.add(eid)
            ets = _parse_ts(item["produced_at"])
            if ets is None:
                out.append(Violation("MALFORMED_TIMESTAMP", f"evidence[{i}].produced_at not ISO-8601"))
                continue
            if final_ts is not None and ets < final_ts:
                out.append(Violation(
                    "STALE_EVIDENCE",
                    f"evidence[{i}] produced {item['produced_at']} predates final commit "
                    f"{artifact.get('final_commit_committed_at')} (pre-nit output cannot be final proof)",
                ))
            if now_ts is not None and ets > now_ts:
                out.append(Violation("FUTURE_EVIDENCE", f"evidence[{i}].produced_at {item['produced_at']} is in the future"))

    # 8. Every 'met' criterion must cite an evidence_ref that RESOLVES to an evidence id
    #    (an unresolved reference is a claim without proof).
    if contract["rules"].get("evidence_ref_must_resolve") and isinstance(sc, list):
        for i, item in enumerate(sc):
            if not isinstance(item, dict) or item.get("verdict") != "met":
                continue
            ref = item.get("evidence_ref")
            if not ref or ref not in evidence_ids:
                out.append(Violation(
                    "UNRESOLVED_EVIDENCE_REF",
                    f"spec_conformance[{i}] (criterion {item.get('criterion_id')!r}) is 'met' but its "
                    f"evidence_ref {ref!r} does not resolve to any evidence id {sorted(evidence_ids)}",
                ))

    # 9. Reconciliation against TrustedInputs (external truth). Fail closed if absent for APPROVE.
    if trusted is not None:
        # 9a. The review payload lives in the trusted bot's GitHub review BODY (not committed to
        #     the branch), so it directly covers the live head — reviewed_sha must equal it. The
        #     review's own commit_id (external) is separately checked to equal the head in
        #     _reconcile_independent_review (REVIEW_STALE_SHA), closing the loop without any
        #     self-referential committed artifact.
        if artifact.get("reviewed_sha") != trusted.pr_head_sha:
            out.append(Violation("STALE_REVIEW_SHA",
                                 f"reviewed_sha {artifact.get('reviewed_sha')!r} != trusted PR head "
                                 f"{trusted.pr_head_sha!r} (the review does not cover the current head)"))
        # 9b. The payload's self-reported pr_head_sha must equal the trusted head regardless.
        if artifact.get("pr_head_sha") != trusted.pr_head_sha:
            out.append(Violation("HEAD_MISMATCH",
                                 f"artifact pr_head_sha {artifact.get('pr_head_sha')!r} != trusted head "
                                 f"{trusted.pr_head_sha!r} (artifact self-reports a different head than git/GitHub)"))
        # 9c. committed-at must match the trusted value when supplied.
        if trusted.final_commit_committed_at is not None \
                and artifact.get("final_commit_committed_at") != trusted.final_commit_committed_at:
            out.append(Violation("COMMIT_TIME_MISMATCH",
                                 f"final_commit_committed_at {artifact.get('final_commit_committed_at')!r} != trusted "
                                 f"{trusted.final_commit_committed_at!r}"))
        # 9d. Criterion set must EQUAL the ratified set (no missing, no fabricated).
        if contract["rules"].get("criterion_set_must_equal_ratified") and trusted.required_criteria:
            required = set(trusted.required_criteria)
            listed = set(criterion_dispositions)
            for missing in sorted(required - listed):
                out.append(Violation("INCOMPLETE_SPEC_CONFORMANCE",
                                     f"ratified criterion {missing!r} is not enumerated in the review"))
            for extra in sorted(listed - required):
                out.append(Violation("UNKNOWN_CRITERION",
                                     f"criterion {extra!r} is not in the ratified acceptance set (fabricated/renamed)"))
            na_ok = set(trusted.na_allowed_criteria)
            for cid, disp in criterion_dispositions.items():
                if disp == "n/a" and cid not in na_ok:
                    out.append(Violation("NA_NOT_PERMITTED",
                                         f"criterion {cid!r} marked 'n/a' but the manifest does not permit n/a for it"))
        # 9e. A self-declared gate 'pass' that contradicts the REAL check conclusion is a lie.
        for name, st in gate_status.items():
            real = trusted.gate_conclusions.get(name)
            if st == "pass" and real is not None and real != "success":
                out.append(Violation("GATE_CONCLUSION_MISMATCH",
                                     f"gate {name!r} claims 'pass' but its real check conclusion is {real!r}"))
        # 9f. Declared reviewer (informational) must match the externally-observed actor.
        declared_reviewer = artifact.get("reviewer")
        if declared_reviewer and trusted.review_actor and declared_reviewer != trusted.review_actor:
            out.append(Violation("REVIEWER_MISMATCH",
                                 f"artifact reviewer {declared_reviewer!r} != externally-observed review actor "
                                 f"{trusted.review_actor!r}"))
    elif verdict == "APPROVE":
        out.append(Violation("UNVERIFIABLE_APPROVE",
                             "APPROVE requires TrustedInputs (external PR head + ratified criteria + real check "
                             "conclusions + an independent review) to reconcile; none supplied — fail closed"))

    # 10. APPROVE gating — the core reconciliation against ratified criteria + external truth.
    if verdict == "APPROVE":
        req = contract["approve_requires"]
        if open_musts > req["open_must_items"]:
            out.append(Violation("APPROVE_WITH_OPEN_MUST",
                                 f"APPROVE with {open_musts} open MUST finding(s); contract requires {req['open_must_items']}"))
        if failing_gates > req["failing_gates"]:
            out.append(Violation("APPROVE_WITH_FAILING_GATE",
                                 f"APPROVE with {failing_gates} failing gate(s); contract requires {req['failing_gates']}"))
        if unmet_criteria > req["unmet_spec_criteria"]:
            out.append(Violation("APPROVE_WITH_UNMET_CRITERION",
                                 f"APPROVE with {unmet_criteria} unmet ratified criterion/criteria; "
                                 f"contract requires {req['unmet_spec_criteria']} (the PRIV-001 escaped-defect class)"))
        if trusted is not None:
            # 10a. An empty ratified set means completeness/gate reconciliation was SKIPPED
            #      (§9d/§10b guard on non-empty). An APPROVE that reconciled against nothing is
            #      not verified — fail closed rather than silently pass.
            if not trusted.required_criteria:
                out.append(Violation("MISSING_RATIFIED_CRITERIA",
                                     "APPROVE cannot be reconciled: no ratified criterion set supplied "
                                     "(criterion-completeness was not checked) — fail closed"))
            # 10b. Required gates must have a REAL 'success' conclusion (not the artifact's word).
            if contract["rules"].get("required_gates_must_pass"):
                if not trusted.required_gates:
                    out.append(Violation("MISSING_RATIFIED_GATES",
                                         "APPROVE cannot be reconciled: no required-gate set supplied "
                                         "(no gate was actually required) — fail closed"))
                if not trusted.gate_conclusions:
                    out.append(Violation("APPROVE_UNVERIFIABLE_GATES",
                                         "APPROVE requires real check conclusions (trusted.gate_conclusions); none supplied"))
                for gname in trusted.required_gates:
                    real = trusted.gate_conclusions.get(gname)
                    if real != "success":
                        out.append(Violation("REQUIRED_GATE_NOT_PASSED",
                                             f"required gate {gname!r} real conclusion is {real or 'absent'!r}, not "
                                             f"'success' (skip/fail/absent/pending do not satisfy a required gate)"))
            # 10c. APPROVE requires a fully-reconciled independent review (external truth).
            out.extend(_reconcile_independent_review(trusted))

    return out


def _reconcile_independent_review(trusted: TrustedInputs) -> list[Violation]:
    """The independent-review gate. An APPROVE is believed ONLY if ALL hold; every failure is a
    typed violation, and any missing external fact fails closed (never a silent pass):
      - a review exists (state present)          else REVIEW_MISSING
      - actor == the ONE trusted reviewer login  else REVIEWER_NOT_TRUSTED
      - state == APPROVED                        else REVIEW_NOT_APPROVED   (COMMENTED/CHANGES_REQUESTED)
      - not dismissed (and state != DISMISSED)   else REVIEW_DISMISSED
      - commit_id == the exact live head SHA      else REVIEW_STALE_SHA      (a later push invalidates)
      - actor != the PR author                    else REVIEWER_NOT_INDEPENDENT
    """
    out: list[Violation] = []
    if not trusted.trusted_reviewer_login:
        out.append(Violation("MISSING_TRUSTED_REVIEWER",
                             "APPROVE cannot be reconciled: no trusted reviewer identity configured "
                             "(contract.trusted_independent_reviewer) — fail closed"))
        return out
    if not trusted.review_state:
        out.append(Violation("REVIEW_MISSING",
                             f"APPROVE requires an independent review by {trusted.trusted_reviewer_login!r}; "
                             "none found for this PR (fail closed)"))
        return out
    if trusted.review_actor != trusted.trusted_reviewer_login:
        out.append(Violation("REVIEWER_NOT_TRUSTED",
                             f"review actor {trusted.review_actor!r} is not the trusted reviewer "
                             f"{trusted.trusted_reviewer_login!r}"))
    if trusted.review_dismissed or trusted.review_state == "DISMISSED":
        out.append(Violation("REVIEW_DISMISSED",
                             "the independent review was dismissed — it no longer approves this head"))
    elif trusted.review_state != "APPROVED":
        out.append(Violation("REVIEW_NOT_APPROVED",
                             f"review state is {trusted.review_state!r}, not 'APPROVED' "
                             "(COMMENTED / CHANGES_REQUESTED do not approve)"))
    if trusted.review_commit_id != trusted.pr_head_sha:
        out.append(Violation("REVIEW_STALE_SHA",
                             f"review targeted commit {trusted.review_commit_id!r} != the live head "
                             f"{trusted.pr_head_sha!r} (a push after approval invalidates it — re-approve the new head)"))
    if trusted.pr_author_login and trusted.review_actor == trusted.pr_author_login:
        out.append(Violation("REVIEWER_NOT_INDEPENDENT",
                             f"review actor {trusted.review_actor!r} is the PR author — not an independent review"))
    return out


def is_valid(artifact: Any, contract: dict | None = None, trusted: TrustedInputs | None = None) -> bool:
    return not validate_review(artifact, contract or load_contract(), trusted)
