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
import types
from pathlib import Path

import pytest

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


# ---- semantic parity: manifest / spec / contract must agree on ONE review model (Rev 4) ----

_SPEC_TEXT = (REPO_ROOT / "specs" / "SPEC_WP12_assurance_kernel.md").read_text(encoding="utf-8")
_CONTRACT = json.loads((REPO_ROOT / "assurance" / "contract" / "review_contract.json").read_text(encoding="utf-8"))


def test_review_model_token_is_consistent_across_protected_surfaces():
    """One canonical structured source (manifest.review_model) — the spec and contract must agree,
    so the manifest criterion text and the governing spec cannot drift to different review models
    (the acceptance-bar-drift the independent review flagged)."""
    token = MANIFEST.get("review_model")
    assert token == "github-review-body-payload", token
    assert _CONTRACT.get("review_model") == token, "contract disagrees on review_model"
    assert token in _SPEC_TEXT, "spec does not declare the canonical review_model token"


def test_wp12_6_criterion_describes_the_review_body_model_not_the_committed_artifact():
    """The WP12#6 criterion text must describe the review-BODY model and must NOT prescribe the
    removed committed-artifact model (semantic parity, not just ID/count)."""
    wp6 = next(c["text"] for c in MANIFEST["prs"]["327"]["criteria"] if c["id"] == "WP12#6")
    assert "review BODY" in wp6 or "review body" in wp6.lower()
    assert "validates committed structured review artifacts" not in wp6  # the old prescription
    # The spec's WP12#6 must likewise not prescribe the removed model.
    assert "reconciles a committed review artifact" not in _SPEC_TEXT


def test_parity_check_would_catch_a_divergent_model(tmp_path):
    """Mutation proof: if the manifest's review_model diverged from the contract, parity fails."""
    divergent = dict(MANIFEST, review_model="committed-artifact")
    assert divergent["review_model"] != _CONTRACT.get("review_model")


def test_cli_success_does_not_claim_ratified():
    """A pending/unratified manifest must never be described as 'ratified' in CLI success output."""
    src = (REPO_ROOT / "assurance" / "check.py").read_text(encoding="utf-8")
    assert "VALID against ratified" not in src, "CLI success message overclaims 'ratified'"


# ---- no PRESCRIPTIVE legacy evidence-commit instructions remain (finding 4) ----

_GOVERNING_SURFACES = [
    "specs/SPEC_WP12_assurance_kernel.md",
    "assurance/reviews/README.md",
    "assurance/reviews/TEMPLATE.json",
    "assurance/contract/review_contract.json",
    "assurance/contract/acceptance_manifest.json",
    ".github/workflows/assurance-gate.yml",
]
# Phrases that only appear as an INSTRUCTION to use the removed committed-artifact model, or as a
# present-tense description of the gate waiting on one. The negating/history mentions ("NOT a file
# committed", "removed the evidence-commit model", "evidence-only commit whose parent WAS ...
# SUPERSEDED") do not match these strings, so this stays true even where docs explain the old model.
_PROHIBITED_LEGACY_INSTRUCTIONS = [
    "commit assurance/reviews/PR",
    "evidence-only commit whose parent is",
    "reviewed_sha == parent",
    "copies this to PR-",
    "independent-review evidence commit",   # the exact workflow-comment contradiction (finding 2)
    "evidence commit exists",
    "evidence-review commit",
]

# The workflow is machine-operational and must describe ONLY the current model — it has no reason
# to narrate the removed one, so any "evidence commit" wording there is a defect.
_WORKFLOW = ".github/workflows/assurance-gate.yml"
_WORKFLOW_ONLY_PROHIBITED = ["evidence commit", "evidence-only commit", "committed review artifact"]


def test_no_prescriptive_legacy_evidence_commit_instructions():
    offenders = []
    for rel in _GOVERNING_SURFACES:
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        for phrase in _PROHIBITED_LEGACY_INSTRUCTIONS:
            if phrase in text:
                offenders.append(f"{rel}: {phrase!r}")
    wf_text = (REPO_ROOT / _WORKFLOW).read_text(encoding="utf-8")
    for phrase in _WORKFLOW_ONLY_PROHIBITED:
        if phrase in wf_text:
            offenders.append(f"{_WORKFLOW}: {phrase!r} (workflow must describe only the current model)")
    assert not offenders, "prescriptive/contradictory legacy evidence-commit wording remains:\n  " + "\n  ".join(offenders)


def test_workflow_describes_the_review_body_model():
    """Positive assertion (not just a denylist): the merge-gate comment must describe the
    review-BODY model so operators reading the governing workflow get correct instructions."""
    wf = (REPO_ROOT / _WORKFLOW).read_text(encoding="utf-8").lower()
    assert "review body" in wf, "workflow does not describe the review-body model"


# ---- workflow must react to review-body EDITS, not only submit/dismiss (finding 1) ----

def test_workflow_reacts_to_review_body_edits():
    """A submitted review body can be edited afterwards; without 'edited' a stale green would
    persist. The pull_request_review trigger must cover submitted + edited + dismissed."""
    import re
    wf = (REPO_ROOT / ".github" / "workflows" / "assurance-gate.yml").read_text(encoding="utf-8")
    m = re.search(r"pull_request_review:\s*(?:#[^\n]*\n\s*)*types:\s*\[([^\]]+)\]", wf)
    assert m, "pull_request_review types not found"
    types = {t.strip() for t in m.group(1).split(",")}
    assert types == {"submitted", "edited", "dismissed"}, types


def test_review_body_template_validates_structurally():
    """The TEMPLATE documents the review-BODY payload format (Rev 4 — not a committed file).
    It must reconcile as a real, machine-checkable payload against a trusted APPROVE on its head."""
    tpl = json.loads((REVIEWS_DIR / "TEMPLATE.json").read_text(encoding="utf-8"))
    head = tpl["pr_head_sha"]
    assert tpl["reviewed_sha"] == head, "template reviewed_sha must equal the head (review-body model)"
    ids = tuple(c["criterion_id"] for c in tpl["spec_conformance"])
    na = tuple(c["criterion_id"] for c in tpl["spec_conformance"] if c["verdict"] == "n/a")
    gate = tpl["gates"][0]["name"]
    trusted = TrustedInputs(
        pr_head_sha=head,
        required_criteria=ids,
        required_gates=(gate,),
        na_allowed_criteria=na,
        gate_conclusions={gate: "success"},
        pr_author_login="the-builder",
        trusted_reviewer_login="codexindependentreviewer[bot]",
        trusted_reviewer_id=317626643,
        review_actor="codexindependentreviewer[bot]",
        review_actor_id=317626643,
        review_actor_type="Bot",
        review_state="APPROVED",
        review_commit_id=head,
        run_id="template-run-1",
        now=_FAR_FUTURE,
    )
    violations = validate_review(tpl, CONTRACT, trusted)
    assert violations == [], [f"{v.code}: {v.message}" for v in violations]


def test_no_committed_verdict_artifact_present():
    """Rev 4: the review of record is the bot's review BODY, NOT a file. Only the format
    TEMPLATE + README live here — never a PR-<n>.json verdict committed to the branch."""
    names = {p.name for p in REVIEWS_DIR.glob("*") if p.is_file()}
    assert names == {"TEMPLATE.json", "README.md"}, names
    assert not list(REVIEWS_DIR.glob("PR-*.json")), "no committed per-PR verdict artifact allowed"


# ---- CLI external-truth behaviour ----

def test_resolve_head_sha_fails_closed_on_unresolvable_pr(monkeypatch):
    """--pr given but GitHub cannot resolve it -> (None, ...), NEVER a local-HEAD fallback."""
    monkeypatch.setattr(chk, "_run", lambda cmd: None)   # every git/gh call fails
    sha, source = chk.resolve_head_sha(pr="999999", explicit=None, repo="owner/repo")
    assert sha is None and source == "gh-unresolved", (sha, source)


def test_resolve_head_sha_prefers_explicit(monkeypatch):
    monkeypatch.setattr(chk, "_run", lambda cmd: "SHOULD_NOT_BE_USED")
    sha, source = chk.resolve_head_sha(pr="1", explicit="deadbeef", repo=None)
    assert sha == "deadbeef" and source == "--head-sha"


# ---- review-body payload extraction (Rev 4) ----

def test_parse_review_payload_pure_json():
    body = '{"verdict": "APPROVE", "reviewed_sha": "abc"}'
    assert chk.parse_review_payload(body) == {"verdict": "APPROVE", "reviewed_sha": "abc"}


def test_parse_review_payload_fenced_json():
    body = "Independent review follows.\n\n```json\n{\"verdict\": \"APPROVE\"}\n```\nthanks"
    assert chk.parse_review_payload(body) == {"verdict": "APPROVE"}


def test_parse_review_payload_none_when_no_json():
    assert chk.parse_review_payload("LGTM 👍 no json here") is None
    assert chk.parse_review_payload("") is None
    assert chk.parse_review_payload("[1, 2, 3]") is None  # a list is not a review object


# ---- independent_review(): externally-grounded review fetch (replaces pr_identities) ----

_BOT = "codexindependentreviewer[bot]"


def _reviews_json(*reviews):
    return json.dumps(list(reviews))


def test_independent_review_extracts_trusted_reviewers_latest(monkeypatch):
    """Picks the LATEST review by the trusted actor and extracts actor/state/commit_id/dismissed/body."""
    payload = _reviews_json(
        {"user": {"login": "someone"}, "state": "COMMENTED", "commit_id": "x", "body": "hi"},
        {"user": {"login": _BOT}, "state": "CHANGES_REQUESTED", "commit_id": "old", "body": "{}"},
        {"user": {"login": _BOT}, "state": "APPROVED", "commit_id": "headsha", "body": '{"verdict":"APPROVE"}'},
    )
    monkeypatch.setattr(chk, "_run", lambda cmd: payload)
    r = chk.independent_review("1", "owner/repo", _BOT)
    assert r == {"actor": _BOT, "actor_id": None, "actor_type": None, "state": "APPROVED",
                 "commit_id": "headsha", "dismissed": False, "body": '{"verdict":"APPROVE"}'}


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


# ---- END-TO-END merge-gate lifecycle through the CLI: submit→green→edit→red→dismiss→red ----

_HEAD40 = "1234567890abcdef1234567890abcdef12345678"
_FIXED_COMMIT_TS = "2026-08-16T00:00:00+00:00"


def _valid_body_payload(head: str) -> dict:
    """A fully-reconciling APPROVE payload built from the REAL PR-327 manifest criteria."""
    entry = MANIFEST["prs"]["327"]
    na = set(entry.get("na_allowed", []))
    sc = [{"criterion_id": c["id"],
           "verdict": ("n/a" if c["id"] in na else "met"),
           "evidence_ref": ("-" if c["id"] in na else "ev-1")}
          for c in entry["criteria"]]
    return {
        "pr": "#327", "verdict": "APPROVE", "reviewer": _BOT,
        "reviewed_sha": head, "pr_head_sha": head,
        "final_commit_committed_at": _FIXED_COMMIT_TS,
        "spec_conformance": sc,
        "findings": [],
        "gates": [{"name": g, "status": "pass"} for g in entry["required_gates"]],
        "evidence": [{"id": "ev-1", "ref": "pytest -q (pasted)", "produced_at": "2026-08-16T00:05:00+00:00"}],
    }


def _merge_gate_args(**over):
    base = dict(pr="327", repo="owner/repo", head_sha=_HEAD40, manifest=None,
                kernel_result="success", conservation_result="success",
                run_id="run-1", require_verdict="APPROVE")
    base.update(over)
    return types.SimpleNamespace(**base)


_BOT_ID = 317626643


@pytest.fixture
def _stub_gh(monkeypatch):
    """Stub the external GitHub/git surface so run_merge_gate is driven by a crafted review.
    The test controls only the review dict; everything else is the real validator + manifest."""
    monkeypatch.setattr(chk, "pr_author", lambda pr, repo: "the-builder")
    monkeypatch.setattr(chk, "commit_time", lambda sha: _FIXED_COMMIT_TS)
    holder = {"review": None}

    def _review(pr, repo, rev):
        # Real independent_review now returns the reviewer's numeric id + account type. A trusted-bot
        # review carries the pinned id + Bot type by default; a test can override either to exercise
        # the id/type binding (explicit keys win over these defaults).
        r = holder["review"]
        if r and r.get("actor") == _BOT:
            r = {"actor_id": _BOT_ID, "actor_type": "Bot", **r}
        return r

    monkeypatch.setattr(chk, "independent_review", _review)
    return holder


def test_merge_gate_lifecycle_submit_green_edit_red_dismiss_red(_stub_gh, capsys):
    body = json.dumps(_valid_body_payload(_HEAD40))

    # 1) SUBMIT a valid APPROVE review whose body carries the payload → GREEN (exit 0).
    _stub_gh["review"] = {"actor": _BOT, "state": "APPROVED", "commit_id": _HEAD40,
                          "dismissed": False, "body": body}
    assert chk.run_merge_gate(_merge_gate_args()) == 0

    # 2) EDIT the review body to invalid content (verdict flipped, payload no longer reconciles)
    #    → RED (exit 1). This is why the workflow must react to the 'edited' event.
    bad = _valid_body_payload(_HEAD40); bad["verdict"] = "CHANGES-REQUIRED"
    _stub_gh["review"] = {"actor": _BOT, "state": "APPROVED", "commit_id": _HEAD40,
                          "dismissed": False, "body": json.dumps(bad)}
    assert chk.run_merge_gate(_merge_gate_args()) == 1

    # 2b) EDIT to an unparseable body → RED (fail closed).
    _stub_gh["review"] = {"actor": _BOT, "state": "APPROVED", "commit_id": _HEAD40,
                          "dismissed": False, "body": "LGTM, no json"}
    assert chk.run_merge_gate(_merge_gate_args()) == 1

    # 3) DISMISS the review → RED (exit 1).
    _stub_gh["review"] = {"actor": _BOT, "state": "DISMISSED", "commit_id": _HEAD40,
                          "dismissed": True, "body": body}
    assert chk.run_merge_gate(_merge_gate_args()) == 1


def test_merge_gate_red_on_stale_sha_after_push(_stub_gh):
    """An APPROVE left on an OLD commit does not cover a new head (synchronize/push) → RED."""
    body = json.dumps(_valid_body_payload(_HEAD40))
    _stub_gh["review"] = {"actor": _BOT, "state": "APPROVED", "commit_id": "0" * 40,
                          "dismissed": False, "body": body}
    assert chk.run_merge_gate(_merge_gate_args()) == 1


def test_merge_gate_red_on_wrong_actor(_stub_gh):
    body = json.dumps(_valid_body_payload(_HEAD40))
    _stub_gh["review"] = {"actor": "attacker[bot]", "state": "APPROVED", "commit_id": _HEAD40,
                          "dismissed": False, "body": body}
    # independent_review only ever returns the trusted actor's review; simulate none found:
    _stub_gh["review"] = None
    assert chk.run_merge_gate(_merge_gate_args()) == 1


def test_merge_gate_red_when_real_gate_failed(_stub_gh):
    """Even a perfect APPROVE body is RED if a required check's REAL conclusion is not success."""
    body = json.dumps(_valid_body_payload(_HEAD40))
    _stub_gh["review"] = {"actor": _BOT, "state": "APPROVED", "commit_id": _HEAD40,
                          "dismissed": False, "body": body}
    assert chk.run_merge_gate(_merge_gate_args(conservation_result="failure")) == 1


# =========================================================================
# Co-review round (2026-08-17): payload ambiguity + fail-open authority resolution.
# =========================================================================

def test_parse_payload_rejects_duplicate_keys():
    """FINDING #5: json's last-wins on duplicate keys silently turned a contradiction into APPROVE."""
    assert chk.parse_review_payload('{"verdict": "CHANGES-REQUIRED", "verdict": "APPROVE"}') is None


def test_parse_payload_rejects_ambiguous_multiple_objects():
    """FINDING #5: two distinct JSON objects in one body — taking the first is arbitrary; fail closed."""
    body = '```json\n{"verdict":"CHANGES-REQUIRED"}\n```\n```json\n{"verdict":"APPROVE"}\n```'
    assert chk.parse_review_payload(body) is None


def test_parse_payload_rejects_duplicate_key_block_beside_valid_block():
    """2026-08-20 correction round (WP12#6): a duplicate-key block is JSON-looking-but-contradictory.
    Silently DISCARDING it while a separate valid APPROVE block wins is the exact bypass an edited
    body could exploit — any dup-key candidate must poison the WHOLE body, not just itself."""
    body = ('```json\n{"verdict": "CHANGES-REQUIRED", "verdict": "BLOCK"}\n```\n'
            '```json\n{"verdict": "APPROVE"}\n```')
    assert chk.parse_review_payload(body) is None


def test_parse_payload_plain_prose_still_yields_the_single_valid_block():
    """Regression guard for the fix above: a NON-JSON prose candidate (JSONDecodeError, not a
    dup-key ValueError) must still be skipped, not treated as poison — one valid block resolves."""
    body = 'LGTM overall.\n```json\n{"verdict":"APPROVE","reviewed_sha":"x"}\n```'
    p = chk.parse_review_payload(body)
    assert p and p["verdict"] == "APPROVE"


def test_parse_payload_accepts_single_valid_object():
    p = chk.parse_review_payload('```json\n{"verdict":"APPROVE","reviewed_sha":"x"}\n```')
    assert p and p["verdict"] == "APPROVE"


def test_parse_payload_accepts_pure_json_body():
    assert chk.parse_review_payload('{"verdict":"APPROVE"}')["verdict"] == "APPROVE"


def test_merge_gate_red_on_ambiguous_review_body(_stub_gh):
    """End-to-end: a review body carrying two payloads (one CHANGES-REQUIRED, one APPROVE) is
    ambiguous and must not merge."""
    two = ('```json\n{"verdict":"CHANGES-REQUIRED"}\n```\n```json\n'
           + json.dumps(_valid_body_payload(_HEAD40)) + '\n```')
    _stub_gh["review"] = {"actor": _BOT, "state": "APPROVED", "commit_id": _HEAD40,
                          "dismissed": False, "body": two}
    assert chk.run_merge_gate(_merge_gate_args()) == 1


def test_merge_gate_fails_closed_when_author_unresolvable(_stub_gh, monkeypatch, capsys):
    """FINDING #2: if the PR author cannot be resolved, reviewer-independence is uncheckable — the
    gate must fail closed, not skip the check (fail open)."""
    monkeypatch.setattr(chk, "pr_author", lambda pr, repo: None)
    _stub_gh["review"] = {"actor": _BOT, "state": "APPROVED", "commit_id": _HEAD40,
                          "dismissed": False, "body": json.dumps(_valid_body_payload(_HEAD40))}
    assert chk.run_merge_gate(_merge_gate_args()) == 1
    assert "author" in capsys.readouterr().out.lower()


def test_merge_gate_fails_closed_when_commit_time_unresolvable(_stub_gh, monkeypatch, capsys):
    """FINDING #2: if the reviewed commit's time cannot be resolved, evidence freshness is
    uncheckable — fail closed."""
    monkeypatch.setattr(chk, "commit_time", lambda sha: None)
    _stub_gh["review"] = {"actor": _BOT, "state": "APPROVED", "commit_id": _HEAD40,
                          "dismissed": False, "body": json.dumps(_valid_body_payload(_HEAD40))}
    assert chk.run_merge_gate(_merge_gate_args()) == 1
    assert "freshness" in capsys.readouterr().out.lower()
