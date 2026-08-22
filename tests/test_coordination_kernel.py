"""Deterministic tests for the TIV2 coordination kernel.

Phase 1 deliberately validates protected contracts only. Live state and queue
selection remain unavailable until an externally bound GitHub adapter exists.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from coordination.kernel import (
    CoordinationKernel,
    CoordinationViolation,
    _canonical_graph_sha256,
)
from coordination.model import strict_json_loads


SHA_A = "a" * 40
SHA_B = "b" * 40
SHA_C = "c" * 40
SHA_D = "d" * 40
SHA256_C = "c" * 64
SHA256_D = "d" * 64
ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 8, 22, 12, 1, tzinfo=timezone.utc)


def _item(
    item_id: str,
    lane: str,
    *,
    priority: int,
    depends_on: list[str] | None = None,
    allow: list[str] | None = None,
    migration: str | None = None,
) -> dict:
    return {
        "id": item_id,
        "title": f"Work {item_id}",
        "lane": lane,
        "priority": priority,
        "contract_status": "executable",
        "depends_on": depends_on or [],
        "spec": {
            "path": "specs/governance/TIV2_COORDINATION_KERNEL.md",
            "acceptance": {
                f"{item_id}#1": {
                    "statement": f"The bounded outcome for {item_id} is independently verifiable.",
                    "verification": ["test:tests/test_coordination_kernel.py"],
                }
            },
        },
        "paths": {
            "allow": allow or [f"sandbox/{item_id}/**"],
            "deny": ["docs/COORDINATION.md", ".github/**"],
        },
        "migration": migration,
        "required_checks": ["targeted-tests", "coordination-gate"],
        "risk": "R1",
    }


@pytest.fixture
def graph() -> dict:
    return {
        "schema": "market-zero-work-graph/v1",
        "authority": {
            "repository": "cryogenic22/myscience",
            "baseline_ref": "main",
            "coordination_board": "docs/COORDINATION.md",
            "protected_surface_path": "protected-surface.txt",
            "trusted_reviewers": ["codexindependentreviewer[bot]"],
            "global_forbidden_paths": [
                "docs/COORDINATION.md",
                "protected-surface.txt",
                ".github/**",
            ],
        },
        "lanes": {
            "core": {"max_active": 1},
            "data": {"max_active": 1},
        },
        "items": [
            _item("V2-A-000", "core", priority=10),
            _item("V2-A-001", "core", priority=20, depends_on=["V2-A-000"]),
            _item("V2-B-000", "data", priority=10),
            _item("V2-B-001", "data", priority=20, depends_on=["V2-B-000"]),
        ],
    }


def _observation(
    item_id: str,
    state: str,
    *,
    head: str = SHA_B,
    changed_paths: list[str] | None = None,
) -> dict:
    return {
        "id": item_id,
        "state": state,
        "issue_number": 101,
        "issue_url": "https://github.example/issues/101",
        "pr_number": 201,
        "pr_url": "https://github.example/pulls/201",
        "author": "claude-builder",
        "branch": f"claude/{item_id.lower()}",
        "base_sha": SHA_A,
        "head_sha": head,
        "baseline_proof": {
            "repository": "cryogenic22/myscience",
            "baseline_ref": "main",
            "base_sha": SHA_A,
            "head_sha": head,
            "graph_contract_sha256": SHA256_C,
            "observed_at": "2026-08-22T11:57:00Z",
            "expires_at": "2026-08-22T12:02:00Z",
            "url": "https://github.example/baselines/main",
        },
        "changed_paths": changed_paths or [f"sandbox/{item_id}/module.py"],
        "acceptance_ids": [f"{item_id}#1"],
        "unresolved_decisions": [],
        "evidence": {
            "red": {
                "sha": SHA_D,
                "descendant_of_base": True,
                "ancestor_of_head": True,
                "command": "python -m pytest tests/test_feature.py -q",
                "conclusion": "failure",
                "collected": 1,
                "executed": 1,
                "url": "https://github.example/runs/red",
            },
            "green": {
                "sha": head,
                "command": "python -m pytest tests/test_feature.py -q",
                "conclusion": "success",
                "collected": 1,
                "executed": 1,
                "skipped": 0,
                "url": "https://github.example/runs/green",
            },
        },
        "checks": [
            {
                "name": "targeted-tests",
                "sha": head,
                "conclusion": "success",
                "collected": 1,
                "executed": 1,
                "skipped": 0,
                "url": "https://github.example/checks/targeted",
            },
            {
                "name": "coordination-gate",
                "sha": head,
                "conclusion": "success",
                "collected": 12,
                "executed": 12,
                "skipped": 0,
                "url": "https://github.example/checks/coordination",
            },
        ],
        "review": None,
    }


def _snapshot(
    *observations: dict,
    baseline: str = SHA_A,
    synthetic: bool = True,
) -> dict:
    return {
        "schema": "market-zero-controller-snapshot/v1",
        "synthetic": synthetic,
        "source": "fixture" if synthetic else "github",
        "repository": "cryogenic22/myscience",
        "baseline_ref": "main",
        "observed_at": "2026-08-22T12:00:00Z",
        "expires_at": "2026-08-22T12:05:00Z",
        "baseline_sha": baseline,
        "graph_contract_sha256": SHA256_C,
        "observations": list(observations),
    }


def _terminal_observation(state: str) -> dict:
    observation = _observation("V2-A-000", state)
    observation["review"] = {
        "reviewer": "codexindependentreviewer[bot]",
        "verdict": "APPROVE",
        "commit_id": SHA_B,
        "submitted_at": "2026-08-22T11:58:00Z",
    }
    observation["merge"] = {
        "head_sha": SHA_B,
        "commit_sha": SHA_C,
        "ancestor_of_baseline": True,
        "merged_at": "2026-08-22T11:59:00Z",
        "url": "https://github.example/pulls/201",
    }
    if state in {"observed", "closed"}:
        observation["post_merge"] = {
            "commit_sha": SHA_C,
            "conclusion": "success",
            "observed_at": "2026-08-22T11:59:30Z",
            "url": "https://github.example/runs/post-merge",
        }
    if state == "closed":
        observation["closed_at"] = "2026-08-22T11:59:45Z"
    return observation


def _codes(exc: pytest.ExceptionInfo[CoordinationViolation]) -> set[str]:
    return {item.code for item in exc.value.violations}


def test_graph_is_a_dag_and_dependencies_are_structural(graph):
    completed = _terminal_observation("observed")
    snapshot = _snapshot(
        completed,
        _observation("V2-B-000", "building"),
        baseline=SHA_C,
        synthetic=False,
    )
    kernel = CoordinationKernel(
        graph,
        snapshot,
        now=NOW,
        repository_root=ROOT,
    )

    assert kernel._validate_dependencies() == []
    assert graph["items"][1]["depends_on"] == ["V2-A-000"]
    assert graph["items"][3]["depends_on"] == ["V2-B-000"]


def test_phase1_exposes_no_actionable_state_or_queue_methods(graph):
    kernel = CoordinationKernel(graph, _snapshot())

    for name in (
        "next_item",
        "review_queue",
        "review_readiness",
        "review_violations",
        "derived_state",
        "state_of",
    ):
        assert not hasattr(kernel, name)


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (lambda g: g["items"][1]["depends_on"].append("MISSING"), "UNKNOWN_DEPENDENCY"),
        (lambda g: g["items"][0]["depends_on"].append("V2-A-001"), "DEPENDENCY_CYCLE"),
        (lambda g: g["items"][1].update({"migration": "101"}), "DUPLICATE_MIGRATION"),
        (lambda g: g["items"][0]["paths"]["allow"].append("../escape.py"), "INVALID_PATH"),
        (lambda g: g["items"][0]["paths"]["allow"].append(".github/workflows/x.yml"), "FORBIDDEN_PATH_CLAIM"),
    ],
)
def test_graph_mutations_fail_closed(graph, mutation, code):
    if code == "DUPLICATE_MIGRATION":
        graph["items"][0]["migration"] = "101"
    mutation(graph)

    with pytest.raises(CoordinationViolation) as caught:
        CoordinationKernel(graph, _snapshot()).require_valid()

    assert code in _codes(caught)


def test_two_active_items_cannot_claim_overlapping_paths(graph):
    graph["items"][0]["paths"]["allow"] = ["trusted-platform/**"]
    graph["items"][2]["paths"]["allow"] = ["trusted-platform/src/marketzero/**"]
    snapshot = _snapshot(
        _observation("V2-A-000", "building", changed_paths=["trusted-platform/a.py"]),
        _observation("V2-B-000", "red", changed_paths=["trusted-platform/src/marketzero/b.py"]),
    )

    with pytest.raises(CoordinationViolation) as caught:
        CoordinationKernel(graph, snapshot).require_valid()

    assert "ACTIVE_PATH_COLLISION" in _codes(caught)


def test_merged_waits_for_successful_post_merge_observation(graph):
    merged = _terminal_observation("merged")
    kernel = CoordinationKernel(
        graph,
        _snapshot(merged, baseline=SHA_C, synthetic=False),
        now=NOW,
        repository_root=ROOT,
    )

    assert kernel._terminal_state_violations("V2-A-000", merged) == []
    assert kernel._derived_state("V2-A-000") == "merged"


def test_closed_time_must_follow_review_merge_and_observation(graph):
    closed = _terminal_observation("closed")
    closed["closed_at"] = "2026-08-22T11:57:00Z"
    kernel = CoordinationKernel(
        graph,
        _snapshot(closed, baseline=SHA_C),
        repository_root=ROOT,
    )

    with pytest.raises(CoordinationViolation) as caught:
        kernel.require_valid()

    assert "UNTRUSTED_TERMINAL_STATE" in _codes(caught)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda o: o["merge"].update({"ancestor_of_baseline": False}),
        lambda o: o["merge"].update({"head_sha": SHA_D}),
        lambda o: o["merge"].update({"merged_at": "2026-08-22T11:57:00Z"}),
        lambda o: o["post_merge"].update({"conclusion": "failure"}),
        lambda o: o["post_merge"].update({"commit_sha": SHA_D}),
        lambda o: o["post_merge"].update({"observed_at": "2026-08-22T11:57:00Z"}),
    ],
)
def test_terminal_proof_mutations_fail_closed(graph, mutate):
    observed = _terminal_observation("observed")
    mutate(observed)

    with pytest.raises(CoordinationViolation) as caught:
        CoordinationKernel(
            graph,
            _snapshot(observed, baseline=SHA_C),
        ).require_valid()

    assert "UNTRUSTED_TERMINAL_STATE" in _codes(caught)


def test_valid_closed_state_is_derived_from_ordered_external_evidence(graph):
    closed = _terminal_observation("closed")
    kernel = CoordinationKernel(graph, _snapshot(closed, baseline=SHA_C))

    assert kernel._terminal_state_violations("V2-A-000", closed) == []
    assert kernel._derived_state("V2-A-000") == "closed"


def test_terminal_state_without_review_and_merge_proof_cannot_unlock_dependency(graph):
    forged = {"id": "V2-A-000", "state": "closed"}
    kernel = CoordinationKernel(graph, _snapshot(forged))

    with pytest.raises(CoordinationViolation) as caught:
        kernel.require_valid()

    assert "UNTRUSTED_TERMINAL_STATE" in _codes(caught)


def test_terminal_state_retains_the_review_ready_live_baseline_proof(graph):
    observed = _terminal_observation("observed")
    observed["base_sha"] = SHA_D
    kernel = CoordinationKernel(graph, _snapshot(observed, baseline=SHA_C))

    with pytest.raises(CoordinationViolation) as caught:
        kernel.require_valid()

    assert "UNTRUSTED_TERMINAL_STATE" in _codes(caught)


def test_protected_path_needs_exact_owner_authorization(graph):
    item = graph["items"][0]
    item["paths"]["allow"] = [".github/workflows/coordination-gate.yml"]
    item["paths"]["deny"] = ["docs/COORDINATION.md"]

    with pytest.raises(CoordinationViolation) as caught:
        CoordinationKernel(graph, _snapshot()).require_valid()
    assert "FORBIDDEN_PATH_CLAIM" in _codes(caught)

    item["protected_change"] = {
        "status": "approved",
        "owner_decision": "OWNER-2026-08-22-TIV2-COORD",
        "scope": [".github/workflows/coordination-gate.yml"],
    }
    CoordinationKernel(graph, _snapshot()).require_valid()


def test_protected_authorization_cannot_be_a_directory_wildcard(graph):
    item = graph["items"][0]
    item["paths"]["allow"] = [".github/**"]
    item["protected_change"] = {
        "status": "approved",
        "owner_decision": "OWNER-2026-08-22-TIV2-COORD",
        "scope": [".github/**"],
    }

    with pytest.raises(CoordinationViolation) as caught:
        CoordinationKernel(graph, _snapshot()).require_valid()
    assert "INVALID_PROTECTED_SCOPE" in _codes(caught)


def test_one_active_item_per_lane_is_structural(graph):
    snapshot = _snapshot(
        _observation("V2-A-000", "building"),
        _observation("V2-A-001", "blocked"),
    )

    with pytest.raises(CoordinationViolation) as caught:
        CoordinationKernel(graph, snapshot).require_valid()

    assert "LANE_CAPACITY_EXCEEDED" in _codes(caught)


def test_internal_readiness_requires_exact_head_nonvacuous_evidence(graph):
    obs = _observation("V2-A-000", "ci")
    snapshot = _snapshot(obs, synthetic=False)
    kernel = CoordinationKernel(
        graph,
        snapshot,
        now=NOW,
        repository_root=ROOT,
    )

    assert kernel._review_readiness("V2-A-000").ready is True

    obs["checks"][0]["sha"] = SHA_C
    assert CoordinationKernel(
        graph,
        snapshot,
        now=NOW,
        repository_root=ROOT,
    )._review_readiness("V2-A-000").ready is False


def test_self_reported_review_ready_is_downgraded_when_evidence_is_missing(graph):
    obs = _observation("V2-A-000", "review_ready")
    obs["checks"] = []
    kernel = CoordinationKernel(graph, _snapshot(obs))

    assert kernel._derived_state("V2-A-000") == "ci"
    with pytest.raises(CoordinationViolation) as caught:
        kernel.require_valid()
    assert "UNTRUSTED_REPORTED_STATE" in _codes(caught)


@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        (lambda o: o["evidence"]["green"].update({"collected": 0, "executed": 0}), "ZERO_TESTS"),
        (lambda o: o["evidence"]["green"].update({"collected": 2, "executed": 1}), "EVIDENCE_COUNT_MISMATCH"),
        (lambda o: o["checks"][0].update({"collected": True}), "VACUOUS_REQUIRED_CHECK"),
        (lambda o: o["checks"][0].update({"collected": 2, "executed": 1}), "CHECK_COUNT_MISMATCH"),
        (lambda o: o["evidence"]["green"].update({"sha": SHA_C}), "STALE_GREEN_EVIDENCE"),
        (lambda o: o["evidence"]["red"].update({"conclusion": "success"}), "MISSING_RED"),
        (lambda o: o["checks"].pop(), "MISSING_REQUIRED_CHECK"),
        (lambda o: o["unresolved_decisions"].append("tenant model"), "UNRESOLVED_DECISION"),
        (lambda o: o.update({"author": ""}), "MISSING_AUTHOR"),
        (lambda o: o.update({"branch": ""}), "MISSING_BRANCH"),
        (lambda o: o.update({"base_sha": o["head_sha"]}), "INVALID_BASE_SHA"),
        (lambda o: o.update({"base_sha": SHA_C}), "BASELINE_SHA_MISMATCH"),
        (lambda o: o["baseline_proof"].update({"base_sha": SHA_C}), "INVALID_BASELINE_PROOF"),
        (lambda o: o["baseline_proof"].update({"head_sha": SHA_C}), "INVALID_BASELINE_PROOF"),
        (
            lambda o: o["baseline_proof"].update(
                {"graph_contract_sha256": SHA256_D}
            ),
            "INVALID_BASELINE_PROOF",
        ),
        (lambda o: o["evidence"]["red"].update({"sha": SHA_A}), "UNPROVEN_RED_LINEAGE"),
        (lambda o: o["evidence"]["red"].update({"descendant_of_base": False}), "UNPROVEN_RED_LINEAGE"),
        (lambda o: o["evidence"]["red"].update({"ancestor_of_head": False}), "UNPROVEN_RED_LINEAGE"),
        (lambda o: o["changed_paths"].append("docs/COORDINATION.md"), "FORBIDDEN_PATH_CHANGED"),
        (lambda o: o.update({"acceptance_ids": ["invented"]}), "ACCEPTANCE_DRIFT"),
    ],
)
def test_review_readiness_mutations_are_rejected(graph, mutate, reason):
    obs = _observation("V2-A-000", "ci")
    mutate(obs)

    result = CoordinationKernel(graph, _snapshot(obs))._review_readiness("V2-A-000")

    assert not result.ready
    assert reason in {v.code for v in result.violations}


def test_exact_head_independent_approve_is_accepted(graph):
    obs = _observation("V2-A-000", "review_ready")
    obs["review"] = {
        "reviewer": "codexindependentreviewer[bot]",
        "verdict": "APPROVE",
        "commit_id": SHA_B,
        "submitted_at": "2026-08-22T11:58:00Z",
    }
    kernel = CoordinationKernel(graph, _snapshot(obs))

    assert kernel._derived_state("V2-A-000") == "approved"


@pytest.mark.parametrize(
    ("review_mutation", "code"),
    [
        (lambda r: r.update({"reviewer": "claude-builder"}), "REVIEWER_NOT_INDEPENDENT"),
        (lambda r: r.update({"reviewer": "unknown[bot]"}), "UNTRUSTED_REVIEWER"),
        (lambda r: r.update({"verdict": "LAND-WITH-NITS"}), "INVALID_VERDICT"),
        (lambda r: r.update({"commit_id": SHA_C}), "STALE_REVIEW"),
        (lambda r: r.update({"submitted_at": "nonsense"}), "INVALID_REVIEW_TIME"),
    ],
)
def test_review_mutations_never_approve(graph, review_mutation, code):
    obs = _observation("V2-A-000", "review_ready")
    review = {
        "reviewer": "codexindependentreviewer[bot]",
        "verdict": "APPROVE",
        "commit_id": SHA_B,
        "submitted_at": "2026-08-22T11:58:00Z",
    }
    review_mutation(review)
    obs["review"] = review
    kernel = CoordinationKernel(graph, _snapshot(obs))

    assert kernel._derived_state("V2-A-000") != "approved"
    assert code in {v.code for v in kernel._review_violations("V2-A-000")}


def test_push_after_approval_invalidates_it(graph):
    obs = _observation("V2-A-000", "review_ready", head=SHA_C)
    obs["review"] = {
        "reviewer": "codexindependentreviewer[bot]",
        "verdict": "APPROVE",
        "commit_id": SHA_B,
        "submitted_at": "2026-08-22T11:58:00Z",
    }

    kernel = CoordinationKernel(graph, _snapshot(obs))

    assert kernel._derived_state("V2-A-000") == "building"
    assert "STALE_REVIEW" in {v.code for v in kernel._review_violations("V2-A-000")}


def test_changes_required_needs_the_same_trusted_exact_head_review(graph):
    obs = _observation("V2-A-000", "review_ready")
    obs["review"] = {
        "reviewer": "unknown[bot]",
        "verdict": "CHANGES-REQUIRED",
        "commit_id": SHA_B,
        "submitted_at": "2026-08-22T11:58:00Z",
    }
    kernel = CoordinationKernel(graph, _snapshot(obs))

    assert kernel._derived_state("V2-A-000") != "changes_required"
    assert "UNTRUSTED_REVIEWER" in {
        violation.code for violation in kernel._review_violations("V2-A-000")
    }

    obs["review"]["reviewer"] = "codexindependentreviewer[bot]"
    assert CoordinationKernel(graph, _snapshot(obs))._derived_state(
        "V2-A-000"
    ) == "changes_required"


def test_self_reported_changes_required_needs_valid_review_evidence(graph):
    obs = _observation("V2-A-000", "changes_required")
    obs["review"] = {
        "reviewer": "unknown[bot]",
        "verdict": "CHANGES-REQUIRED",
        "commit_id": SHA_B,
        "submitted_at": "2026-08-22T11:58:00Z",
    }

    with pytest.raises(CoordinationViolation) as caught:
        CoordinationKernel(graph, _snapshot(obs)).require_valid()

    assert "UNTRUSTED_REPORTED_STATE" in _codes(caught)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda o: o.update({"acceptance_ids": [{}]}),
        lambda o: o.update({"changed_paths": [{}]}),
        lambda o: o.update({"checks": ["not-an-object"]}),
        lambda o: o.update({"issue_number": True}),
        lambda o: o["evidence"]["green"].update({"url": {}}),
        lambda o: o["checks"][0].update({"name": {}}),
        lambda o: o["checks"][0].update({"collected": {}}),
        lambda o: o["evidence"]["red"].update({"collected": {}}),
        lambda o: o["evidence"]["red"].update({"conclusion": 7}),
        lambda o: o["review"].update({"submitted_at": []}),
    ],
)
def test_nested_type_mutations_fail_closed_without_crashing(graph, mutate):
    obs = _observation("V2-A-000", "review_ready")
    obs["review"] = {
        "reviewer": "codexindependentreviewer[bot]",
        "verdict": "APPROVE",
        "commit_id": SHA_B,
        "submitted_at": "2026-08-22T11:58:00Z",
    }
    mutate(obs)
    kernel = CoordinationKernel(graph, _snapshot(obs))

    with pytest.raises(CoordinationViolation) as caught:
        kernel.require_valid()

    assert "MALFORMED_FIELD" in _codes(caught)


@pytest.mark.parametrize(
    ("from_state", "to_state"),
    [
        ("planned", "claimed"),
        ("claimed", "red"),
        ("red", "building"),
        ("building", "green_local"),
        ("green_local", "ci"),
        ("ci", "review_ready"),
        ("review_ready", "changes_required"),
        ("changes_required", "building"),
        ("review_ready", "approved"),
        ("approved", "merged"),
        ("merged", "observed"),
        ("observed", "closed"),
    ],
)
def test_normal_controller_transitions_are_closed_and_explicit(from_state, to_state):
    assert CoordinationKernel.transition_violations(
        "V2-A-000", from_state, to_state, actor_role="controller"
    ) == []


def test_builder_cannot_assert_a_state_transition():
    violations = CoordinationKernel.transition_violations(
        "V2-A-000", "building", "green_local", actor_role="builder"
    )
    assert {item.code for item in violations} == {"UNTRUSTED_STATE_ACTOR"}


def test_skipped_state_and_unrecorded_resume_fail_closed():
    skipped = CoordinationKernel.transition_violations(
        "V2-A-000", "planned", "review_ready", actor_role="controller"
    )
    resumed = CoordinationKernel.transition_violations(
        "V2-A-000", "blocked", "building", actor_role="controller"
    )

    assert "INVALID_TRANSITION" in {item.code for item in skipped}
    assert "INVALID_RESUME_STATE" in {item.code for item in resumed}


def test_blocked_item_only_resumes_to_recorded_state():
    assert CoordinationKernel.transition_violations(
        "V2-A-000",
        "blocked",
        "building",
        actor_role="controller",
        blocked_from_state="building",
    ) == []
    violations = CoordinationKernel.transition_violations(
        "V2-A-000",
        "blocked",
        "red",
        actor_role="controller",
        blocked_from_state="building",
    )
    assert "INVALID_TRANSITION" in {item.code for item in violations}


def test_cancel_is_owner_controller_only():
    denied = CoordinationKernel.transition_violations(
        "V2-A-000", "building", "cancelled", actor_role="controller"
    )
    allowed = CoordinationKernel.transition_violations(
        "V2-A-000", "building", "cancelled", actor_role="controller-owner"
    )

    assert "OWNER_ONLY_CANCELLATION" in {item.code for item in denied}
    assert allowed == []


def test_cli_contract_fixture_is_valid():
    graph_path = ROOT / "coordination" / "contracts" / "work_graph.json"
    graph = json.loads(graph_path.read_text())
    snapshot = json.loads(
        (ROOT / "coordination" / "contracts" / "example_snapshot.json").read_text()
    )

    assert CoordinationKernel(
        graph,
        snapshot,
        repository_root=ROOT,
        graph_path=graph_path,
    ).validate() == []


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (
            lambda graph, snapshot: snapshot.update(
                {"graph_contract_sha256": SHA256_D}
            ),
            "GRAPH_CONTRACT_MISMATCH",
        ),
        (lambda graph, snapshot: graph["items"][0].update({"title": "mutated"}), "GRAPH_INPUT_MISMATCH"),
    ],
)
def test_repository_graph_input_and_canonical_contract_are_bound(mutate, code):
    graph_path = ROOT / "coordination" / "contracts" / "work_graph.json"
    graph = json.loads(graph_path.read_text())
    snapshot = json.loads(
        (ROOT / "coordination" / "contracts" / "example_snapshot.json").read_text()
    )
    mutate(graph, snapshot)

    with pytest.raises(CoordinationViolation) as caught:
        CoordinationKernel(
            graph,
            snapshot,
            repository_root=ROOT,
            graph_path=graph_path,
        ).require_valid()

    assert code in _codes(caught)


def test_canonical_graph_digest_is_identical_for_lf_and_crlf_json():
    graph_path = ROOT / "coordination" / "contracts" / "work_graph.json"
    lf = graph_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    crlf = lf.replace("\n", "\r\n")

    assert _canonical_graph_sha256(json.loads(lf)) == _canonical_graph_sha256(
        json.loads(crlf)
    )


@pytest.mark.parametrize(
    "payload",
    [
        '{"schema":"shadow","schema":"market-zero-work-graph/v1"}',
        '{"outer":{"state":"planned","state":"closed"}}',
        '{"value":NaN}',
        '{"value":Infinity}',
        '{"value":1e999}',
        '{"value":-1e999}',
    ],
)
def test_strict_json_parser_rejects_ambiguous_or_nonstandard_input(payload):
    with pytest.raises(ValueError):
        strict_json_loads(payload)


@pytest.mark.parametrize("value", [float("inf"), float("-inf"), float("nan")])
def test_canonical_graph_digest_rejects_non_finite_in_memory_values(value):
    with pytest.raises(ValueError):
        _canonical_graph_sha256({"value": value})


def test_kernel_rejects_non_finite_graph_even_if_supplied_as_a_python_object():
    graph_path = ROOT / "coordination" / "contracts" / "work_graph.json"
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    snapshot = json.loads(
        (ROOT / "coordination" / "contracts" / "example_snapshot.json").read_text(
            encoding="utf-8"
        )
    )
    graph["ignored_overflow"] = float("inf")

    with pytest.raises(CoordinationViolation) as caught:
        CoordinationKernel(
            graph,
            snapshot,
            repository_root=ROOT,
            graph_path=graph_path,
        ).require_valid()

    assert "INVALID_GRAPH_SOURCE" in _codes(caught)


def test_core_and_data_are_blocked_behind_the_complete_governance_rollout():
    graph = json.loads(
        (ROOT / "coordination" / "contracts" / "work_graph.json").read_text()
    )
    by_id = {item["id"]: item for item in graph["items"]}
    rollout = [f"V2-GOV-{number:03d}" for number in range(1, 8)]

    for previous, current in zip(rollout, rollout[1:]):
        assert by_id[current]["depends_on"] == [previous]
    assert by_id[rollout[0]]["contract_status"] == "executable"
    assert {
        by_id[item_id]["contract_status"] for item_id in rollout[1:]
    } == {"contract_pending"}
    assert by_id["V2-A-000"]["depends_on"] == [rollout[-1]]
    assert by_id["V2-B-000"]["depends_on"] == [rollout[-1]]
    assert by_id["V2-A-000"]["contract_status"] == "contract_pending"
    assert by_id["V2-B-000"]["contract_status"] == "contract_pending"


def test_contract_pending_item_cannot_activate_without_its_predeclared_test():
    graph_path = ROOT / "coordination" / "contracts" / "work_graph.json"
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    snapshot = json.loads(
        (ROOT / "coordination" / "contracts" / "example_snapshot.json").read_text(
            encoding="utf-8"
        )
    )
    graph["items"][1]["contract_status"] = "executable"

    with pytest.raises(CoordinationViolation) as caught:
        CoordinationKernel(graph, snapshot, repository_root=ROOT).require_valid()

    assert "MISSING_VERIFIER_TARGET" in _codes(caught)


def test_contract_pending_gov2_cannot_be_fabricated_review_ready():
    graph = json.loads(
        (ROOT / "coordination" / "contracts" / "work_graph.json").read_text(
            encoding="utf-8"
        )
    )
    observation = _observation(
        "V2-GOV-002",
        "review_ready",
        changed_paths=["coordination/github_adapter.py"],
    )
    observation["acceptance_ids"] = ["GOV2#1"]
    observation["checks"] = [
        {
            "name": "coordination-kernel",
            "sha": SHA_B,
            "conclusion": "success",
            "collected": 1,
            "executed": 1,
            "skipped": 0,
            "url": "https://github.example/checks/coordination",
        }
    ]

    with pytest.raises(CoordinationViolation) as caught:
        CoordinationKernel(graph, _snapshot(observation)).require_valid()

    assert {
        "CONTRACT_NOT_EXECUTABLE",
        "SYNTHETIC_OBSERVATIONS_FORBIDDEN",
    }.issubset(_codes(caught))


def test_missing_test_verifier_target_fails_repository_contract(graph):
    graph["items"][0]["spec"]["acceptance"]["V2-A-000#1"]["verification"] = [
        "test:tests/DOES_NOT_EXIST.py"
    ]

    with pytest.raises(CoordinationViolation) as caught:
        CoordinationKernel(graph, _snapshot()).require_valid()

    assert "MISSING_VERIFIER_TARGET" in _codes(caught)


@pytest.mark.parametrize(
    "verifier",
    ["test:coordination-kernel", "test:../escape.py", "shell:pytest -q"],
)
def test_unsafe_or_unknown_verifier_syntax_fails_closed(graph, verifier):
    graph["items"][0]["spec"]["acceptance"]["V2-A-000#1"]["verification"] = [
        verifier
    ]

    with pytest.raises(CoordinationViolation) as caught:
        CoordinationKernel(graph, _snapshot(), repository_root=ROOT).require_valid()

    assert "INVALID_VERIFIER_TARGET" in _codes(caught)


def test_graph_cannot_remove_every_executable_verifier(graph):
    for item in graph["items"]:
        for criterion in item["spec"]["acceptance"].values():
            criterion["verification"] = ["review:architecture-and-integrity"]

    with pytest.raises(CoordinationViolation) as caught:
        CoordinationKernel(graph, _snapshot(), repository_root=ROOT).require_valid()

    assert "NO_EXECUTABLE_VERIFIERS" in _codes(caught)


def test_live_shaped_input_requires_adapter_and_bound_graph(graph):
    with pytest.raises(CoordinationViolation) as caught:
        CoordinationKernel(graph, _snapshot(synthetic=False), now=NOW).require_valid()

    assert {"LIVE_ADAPTER_REQUIRED", "UNBOUND_GRAPH_SOURCE"}.issubset(_codes(caught))


def test_self_asserted_historical_terminal_proof_is_never_authoritative(graph):
    terminal = _terminal_observation("observed")
    terminal["base_sha"] = SHA_D
    terminal["baseline_proof"].update(
        {
            "base_sha": SHA_D,
            "graph_contract_sha256": SHA256_D,
        }
    )
    snapshot = _snapshot(terminal, baseline=SHA_C, synthetic=False)

    with pytest.raises(CoordinationViolation) as caught:
        CoordinationKernel(graph, snapshot, now=NOW).require_valid()

    assert "LIVE_ADAPTER_REQUIRED" in _codes(caught)


def test_synthetic_observations_cannot_drive_any_lifecycle(graph):
    snapshot = _snapshot(_observation("V2-A-000", "review_ready"))

    with pytest.raises(CoordinationViolation) as caught:
        CoordinationKernel(graph, snapshot).require_valid()

    assert "SYNTHETIC_OBSERVATIONS_FORBIDDEN" in _codes(caught)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda g, s: g.update({"items": {}}),
        lambda g, s: g.update({"lanes": []}),
        lambda g, s: g["authority"].update({"trusted_reviewers": {}}),
        lambda g, s: g["authority"].update({"global_forbidden_paths": None}),
        lambda g, s: g["items"][0].update({"depends_on": {}}),
        lambda g, s: g["items"][0]["spec"].update({"acceptance": "A"}),
        lambda g, s: next(
            iter(g["items"][0]["spec"]["acceptance"].values())
        ).update({"verification": [{}]}),
        lambda g, s: g["items"][0]["paths"].update({"allow": {}}),
        lambda g, s: g["items"][0].update({"required_checks": None}),
        lambda g, s: s.update({"observations": {}}),
        lambda g, s: g.update({"items": None}),
        lambda g, s: g.update({"items": 0}),
        lambda g, s: g.update({"items": True}),
        lambda g, s: s.update({"observations": None}),
        lambda g, s: s.update({"observations": 0}),
        lambda g, s: s.update({"observations": True}),
    ],
)
def test_required_collection_type_mutations_fail_closed(graph, mutate):
    snapshot = _snapshot()
    mutate(graph, snapshot)

    with pytest.raises(CoordinationViolation) as caught:
        CoordinationKernel(graph, snapshot).require_valid()

    assert "MALFORMED_FIELD" in _codes(caught)


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (
            lambda acceptance: next(iter(acceptance.values())).update(
                {"statement": ""}
            ),
            "MALFORMED_FIELD",
        ),
        (
            lambda acceptance: next(iter(acceptance.values())).update(
                {"verification": []}
            ),
            "MALFORMED_FIELD",
        ),
        (
            lambda acceptance: acceptance.update(
                {"BAD": {"statement": "x", "verification": ["test:x"]}}
            ),
            "INVALID_ACCEPTANCE_CONTRACT",
        ),
    ],
)
def test_acceptance_contract_is_typed_and_canonical(graph, mutate, code):
    acceptance = graph["items"][0]["spec"]["acceptance"]
    mutate(acceptance)

    with pytest.raises(CoordinationViolation) as caught:
        CoordinationKernel(graph, _snapshot()).require_valid()

    assert code in _codes(caught)


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (lambda s: s.update({"expires_at": "2026-08-22T11:59:00Z"}), "INVALID_SNAPSHOT_WINDOW"),
        (lambda s: s.update({"expires_at": "2026-08-22T12:06:00Z"}), "INVALID_SNAPSHOT_WINDOW"),
        (lambda s: s.update({"baseline_ref": "claude/stale"}), "BASELINE_REF_MISMATCH"),
        (lambda s: s.update({"repository": "someone/else"}), "REPOSITORY_MISMATCH"),
    ],
)
def test_snapshot_scope_and_window_are_fixed(graph, mutation, code):
    graph["authority"]["repository"] = "cryogenic22/myscience"
    snapshot = _snapshot()
    mutation(snapshot)

    with pytest.raises(CoordinationViolation) as caught:
        CoordinationKernel(
            graph,
            snapshot,
            now=datetime(2026, 8, 22, 12, 1, tzinfo=timezone.utc),
        ).require_valid()

    assert code in _codes(caught)


def test_expired_live_snapshot_fails_closed(graph):
    graph["authority"]["repository"] = "cryogenic22/myscience"
    snapshot = _snapshot()
    snapshot["synthetic"] = False
    snapshot["source"] = "github"

    with pytest.raises(CoordinationViolation) as caught:
        CoordinationKernel(
            graph,
            snapshot,
            now=datetime(2026, 8, 22, 12, 6, tzinfo=timezone.utc),
        ).require_valid()

    assert "STALE_SNAPSHOT" in _codes(caught)


def test_repository_protected_surface_is_enforced_even_if_graph_omits_path(graph):
    graph["items"][0]["paths"]["allow"] = ["requirements.txt"]
    graph["items"][0]["paths"]["deny"] = []
    root = Path(__file__).resolve().parents[1]

    with pytest.raises(CoordinationViolation) as caught:
        CoordinationKernel(
            graph,
            _snapshot(),
            repository_root=root,
        ).require_valid()

    assert "FORBIDDEN_PATH_CLAIM" in _codes(caught)


@pytest.mark.parametrize(
    ("graph_value", "snapshot_value"),
    [
        ([], _snapshot()),
        (0, _snapshot()),
        ({"schema": "market-zero-work-graph/v1", "items": [{"id": {}}]}, _snapshot()),
        (None, [{"id": "V2-A-000"}]),
    ],
)
def test_malformed_roots_and_nested_map_keys_fail_closed_without_crashing(
    graph, graph_value, snapshot_value
):
    candidate_graph = graph if graph_value is None else graph_value
    candidate_snapshot = _snapshot() if snapshot_value is None else snapshot_value

    with pytest.raises(CoordinationViolation) as caught:
        CoordinationKernel(candidate_graph, candidate_snapshot).require_valid()

    assert "MALFORMED_FIELD" in _codes(caught)


@pytest.mark.parametrize("bad", [None, {}, [], 7, True])
@pytest.mark.parametrize(
    "mutate",
    [
        lambda o, bad: o["checks"][0].update({"name": bad}),
        lambda o, bad: o["checks"][0].update({"conclusion": bad}),
        lambda o, bad: o["evidence"]["red"].update({"sha": bad}),
        lambda o, bad: o["evidence"]["red"].update({"conclusion": bad}),
    ],
)
def test_nested_string_evidence_fields_reject_every_non_string_type(
    graph, mutate, bad
):
    obs = _observation("V2-A-000", "review_ready")
    mutate(obs, bad)

    with pytest.raises(CoordinationViolation) as caught:
        CoordinationKernel(graph, _snapshot(obs)).require_valid()

    assert "MALFORMED_FIELD" in _codes(caught)


@pytest.mark.parametrize("bad", [None, {}, [], "1", 1.5, True])
@pytest.mark.parametrize(
    "mutate",
    [
        lambda o, bad: o["checks"][0].update({"collected": bad}),
        lambda o, bad: o["checks"][0].update({"executed": bad}),
        lambda o, bad: o["evidence"]["red"].update({"collected": bad}),
        lambda o, bad: o["evidence"]["green"].update({"skipped": bad}),
    ],
)
def test_nested_integer_evidence_fields_reject_every_non_integer_type(
    graph, mutate, bad
):
    obs = _observation("V2-A-000", "review_ready")
    mutate(obs, bad)

    with pytest.raises(CoordinationViolation) as caught:
        CoordinationKernel(graph, _snapshot(obs)).require_valid()

    assert "MALFORMED_FIELD" in _codes(caught)
