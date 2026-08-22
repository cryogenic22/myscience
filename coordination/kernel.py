"""Pure Phase-1 contract validation for Market Zero work items.

GitHub will be the observation source, not a place where business rules are
hidden. This phase validates a protected graph and bootstrap fixture. It cannot
select work or publish live/review state until the bound adapter exists.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable

from .model import (
    ACCEPTANCE_ID_RE,
    GRAPH_SCHEMA,
    ID_RE,
    MAX_CLOCK_SKEW,
    MAX_SNAPSHOT_AGE,
    MIGRATION_RE,
    SNAPSHOT_SCHEMA,
    CoordinationViolation,
    ReadinessResult,
    Violation,
    WorkItem,
    is_https_url as _is_https_url,
    is_int as _is_int,
    is_nonempty_string as _is_nonempty_string,
    is_positive_int as _is_positive_int,
    is_sha as _is_sha,
    is_sha256 as _is_sha256,
    is_string_list as _is_string_list,
    load_protected_surface as _load_protected_surface,
    matches as _matches,
    parse_timestamp as _parse_timestamp,
    patterns_overlap as _patterns_overlap,
    strict_json_loads as _strict_json_loads,
    valid_path_pattern as _valid_path_pattern,
)
from .state import (
    ACTIVE_STATES,
    REVIEWABLE_STATES,
    REVIEW_EVIDENCE_STATES,
    REVIEW_VERDICTS,
    STATES,
    TERMINAL_PROOF_STATES,
    transition_violations,
)


_REVIEW_VERIFIER_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
_PROTECTED_SURFACE_PATH = "protected-surface.txt"
_CONTRACT_STATUSES = frozenset({"executable", "contract_pending"})


def _canonical_graph_sha256(graph: dict[str, Any]) -> str:
    """Hash canonical JSON, independent of checkout encoding and line endings."""

    canonical = json.dumps(
        graph,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


class CoordinationKernel:
    """Validate contracts; internal lifecycle predicates are non-authoritative."""

    def __init__(
        self,
        graph: dict[str, Any],
        snapshot: dict[str, Any],
        *,
        now: datetime | None = None,
        protected_patterns: Iterable[str] = (),
        repository_root: str | Path | None = None,
        graph_path: str | Path | None = None,
    ):
        self.graph = graph
        self.snapshot = snapshot
        self.repository_root = (
            Path(repository_root).resolve()
            if repository_root is not None
            else Path(__file__).resolve().parents[1]
        )
        self.graph_path = Path(graph_path).resolve() if graph_path is not None else None
        self._repository_setup_violations: list[Violation] = []
        repository_patterns: tuple[str, ...] = ()
        if isinstance(graph, dict):
            authority = graph.get("authority")
            protected_path = (
                authority.get("protected_surface_path")
                if isinstance(authority, dict)
                else None
            )
            if isinstance(protected_path, str) and protected_path:
                try:
                    repository_patterns = _load_protected_surface(
                        self.repository_root / protected_path
                    )
                except (OSError, ValueError) as exc:
                    self._repository_setup_violations.append(
                        Violation(
                            "INVALID_PROTECTED_SURFACE_SOURCE",
                            "graph",
                            str(exc),
                        )
                    )
        self.protected_patterns = tuple(
            dict.fromkeys((*protected_patterns, *repository_patterns))
        )
        if self.graph_path is None and isinstance(snapshot, dict) and snapshot.get(
            "synthetic"
        ) is False:
            self._repository_setup_violations.append(
                Violation(
                    "UNBOUND_GRAPH_SOURCE",
                    "graph",
                    "live-shaped input requires the canonical repository graph path",
                )
            )
        if self.graph_path is not None:
            try:
                self.graph_path.relative_to(self.repository_root)
                expected_graph_path = (
                    self.repository_root
                    / "coordination"
                    / "contracts"
                    / "work_graph.json"
                ).resolve()
                if self.graph_path != expected_graph_path:
                    raise ValueError(
                        "graph path must be coordination/contracts/work_graph.json"
                    )
                graph_bytes = self.graph_path.read_bytes()
                if _strict_json_loads(graph_bytes) != graph:
                    self._repository_setup_violations.append(
                        Violation(
                            "GRAPH_INPUT_MISMATCH",
                            "graph",
                            "loaded graph differs from the repository graph file",
                        )
                    )
                contract_digest = _canonical_graph_sha256(graph)
                if isinstance(snapshot, dict) and snapshot.get(
                    "graph_contract_sha256"
                ) != contract_digest:
                    self._repository_setup_violations.append(
                        Violation(
                            "GRAPH_CONTRACT_MISMATCH",
                            "snapshot",
                            "snapshot is not bound to canonical JSON for the protected graph",
                        )
                    )
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                self._repository_setup_violations.append(
                    Violation(
                        "INVALID_GRAPH_SOURCE",
                        "graph",
                        str(exc),
                    )
                )
        self.now = now or datetime.now(timezone.utc)
        if self.now.tzinfo is None:
            self.now = self.now.replace(tzinfo=timezone.utc)
        else:
            self.now = self.now.astimezone(timezone.utc)
        raw_items = graph.get("items", []) if isinstance(graph, dict) else []
        if not isinstance(raw_items, list):
            raw_items = []
        self.items = [
            WorkItem.from_dict(raw) for raw in raw_items if isinstance(raw, dict)
        ]
        self.item_by_id = {item.id: item for item in self.items}
        raw_observations = (
            snapshot.get("observations", []) if isinstance(snapshot, dict) else []
        )
        if not isinstance(raw_observations, list):
            raw_observations = []
        self.observations = [
            raw for raw in raw_observations if isinstance(raw, dict)
        ]
        self.observation_by_id = {
            raw["id"]: raw
            for raw in self.observations
            if isinstance(raw.get("id"), str)
        }

    @property
    def authority(self) -> dict[str, Any]:
        value = self.graph.get("authority", {}) if isinstance(self.graph, dict) else {}
        return value if isinstance(value, dict) else {}

    @property
    def lanes(self) -> dict[str, Any]:
        value = self.graph.get("lanes", {}) if isinstance(self.graph, dict) else {}
        return value if isinstance(value, dict) else {}

    def _global_denied(self) -> tuple[str, ...]:
        value = self.authority.get("global_forbidden_paths", [])
        declared = tuple(value) if isinstance(value, list) else ()
        return tuple(dict.fromkeys((*declared, *self.protected_patterns)))

    def effective_denied(self, item: WorkItem) -> tuple[str, ...]:
        return tuple(dict.fromkeys((*self._global_denied(), *item.denied_paths)))

    def _authorized_protected_pattern(self, item: WorkItem, pattern: str) -> bool:
        return (
            item.protected_status == "approved"
            and bool(item.protected_decision)
            and pattern in item.protected_scopes
        )

    def _path_denied(self, item: WorkItem, path: str) -> bool:
        if any(_matches(pattern, path) for pattern in item.denied_paths):
            return True
        for pattern in self._global_denied():
            if _matches(pattern, path) and path not in item.protected_scopes:
                return True
        return False

    def _reported_state(self, item_id: str) -> str:
        observation = self.observation_by_id.get(item_id)
        state = observation.get("state") if observation else "planned"
        return state if isinstance(state, str) else ""

    @staticmethod
    def transition_violations(
        item_id: str,
        from_state: str,
        to_state: str,
        *,
        actor_role: str,
        blocked_from_state: str | None = None,
    ) -> list[Violation]:
        return transition_violations(
            item_id,
            from_state,
            to_state,
            actor_role=actor_role,
            blocked_from_state=blocked_from_state,
        )

    def validate(self) -> list[Violation]:
        violations = self._validate_raw_types()
        if not isinstance(self.graph, dict) or not isinstance(self.snapshot, dict):
            return sorted(set(violations))
        if any(violation.code == "MALFORMED_FIELD" for violation in violations):
            return sorted(set(violations))
        violations.extend(self._validate_shapes())
        violations.extend(self._validate_repository_contract())
        violations.extend(self._validate_dependencies())
        violations.extend(self._validate_claims())
        if self.snapshot.get("synthetic") is True and self.observations:
            violations.append(
                Violation(
                    "SYNTHETIC_OBSERVATIONS_FORBIDDEN",
                    "snapshot",
                    "Phase 1 synthetic input validates contracts only, never work state",
                )
            )
        if self.snapshot.get("synthetic") is False:
            violations.append(
                Violation(
                    "LIVE_ADAPTER_REQUIRED",
                    "snapshot",
                    "live work state is rejected until the read-only GitHub adapter lands",
                )
            )
        for raw in self.observations:
            item_id = raw.get("id", "")
            item = self.item_by_id.get(item_id)
            if item is not None and item.contract_status != "executable" and raw.get(
                "state"
            ) != "planned":
                violations.append(
                    Violation(
                        "CONTRACT_NOT_EXECUTABLE",
                        item_id,
                        "contract-pending work cannot enter a lifecycle",
                    )
                )
            if raw.get("state") == "review_ready" and not self._review_readiness(item_id).ready:
                violations.append(Violation("UNTRUSTED_REPORTED_STATE", item_id, "review_ready was reported but exact-head readiness is false"))
            if raw.get("state") in {"approved", "changes_required"} and self._derived_state(item_id) != raw.get("state"):
                violations.append(Violation("UNTRUSTED_REPORTED_STATE", item_id, f"{raw.get('state')} was reported without a valid independent exact-head review"))
            if raw.get("state") in TERMINAL_PROOF_STATES:
                violations.extend(self._terminal_state_violations(item_id, raw))
        return sorted(set(violations))

    def _validate_repository_contract(self) -> list[Violation]:
        """Bind declared specs/tests to real files when trusted repo context exists."""

        out: list[Violation] = list(self._repository_setup_violations)

        def file_exists(
            item_id: str,
            value: str,
            *,
            kind: str,
            require_exists: bool = True,
        ) -> None:
            if not _valid_path_pattern(value) or value.endswith("/**"):
                out.append(
                    Violation(
                        "INVALID_VERIFIER_TARGET",
                        item_id,
                        f"{kind} target {value!r} is not one exact safe path",
                    )
                )
                return
            candidate = (self.repository_root / value).resolve()
            try:
                candidate.relative_to(self.repository_root)
            except ValueError:
                out.append(
                    Violation(
                        "INVALID_VERIFIER_TARGET",
                        item_id,
                        f"{kind} target {value!r} escapes repository root",
                    )
                )
                return
            if require_exists and not candidate.is_file():
                out.append(
                    Violation(
                        "MISSING_VERIFIER_TARGET",
                        item_id,
                        f"{kind} target {value!r} does not exist",
                    )
                )

        for item in self.items:
            file_exists(item.id, item.spec_path, kind="spec")
            item_has_test = False
            for criterion in item.acceptance:
                for verifier in criterion.verification:
                    if not isinstance(verifier, str):
                        out.append(
                            Violation(
                                "INVALID_VERIFIER_TARGET",
                                item.id,
                                "verifier must be a string",
                            )
                        )
                    elif verifier.startswith("test:"):
                        item_has_test = True
                        target = verifier.removeprefix("test:")
                        if not target.startswith("tests/") or not target.endswith(".py"):
                            out.append(
                                Violation(
                                    "INVALID_VERIFIER_TARGET",
                                    item.id,
                                    f"test verifier {verifier!r} must name one tests/*.py file",
                                )
                            )
                        else:
                            file_exists(
                                item.id,
                                target,
                                kind="test",
                                require_exists=item.contract_status == "executable",
                            )
                    elif verifier.startswith("review:"):
                        route = verifier.removeprefix("review:")
                        if _REVIEW_VERIFIER_RE.fullmatch(route) is None:
                            out.append(
                                Violation(
                                    "INVALID_VERIFIER_TARGET",
                                    item.id,
                                    f"review verifier {verifier!r} is malformed",
                                )
                            )
                    else:
                        out.append(
                            Violation(
                                "INVALID_VERIFIER_TARGET",
                                item.id,
                                f"unsupported verifier {verifier!r}",
                            )
                        )
            if not item_has_test:
                out.append(
                    Violation(
                        "NO_EXECUTABLE_VERIFIERS",
                        item.id,
                        "every work item must predeclare an executable test verifier",
                    )
                )
        if not any(item.contract_status == "executable" for item in self.items):
            out.append(
                Violation(
                    "NO_EXECUTABLE_VERIFIERS",
                    "graph",
                    "at least one work contract must be executable",
                )
            )
        return sorted(set(out))

    def test_verifiers(self) -> tuple[str, ...]:
        """Return the exact protected test set after repository validation."""

        self.require_valid()
        return tuple(
            sorted(
                {
                    verifier.removeprefix("test:")
                    for item in self.items
                    if item.contract_status == "executable"
                    for criterion in item.acceptance
                    for verifier in criterion.verification
                    if isinstance(verifier, str) and verifier.startswith("test:")
                }
            )
        )

    def _terminal_state_violations(
        self, item_id: str, raw: dict[str, Any]
    ) -> list[Violation]:
        item = self.item_by_id.get(item_id)
        if item is None:
            return [
                Violation(
                    "UNTRUSTED_TERMINAL_STATE",
                    item_id or "<missing>",
                    "terminal state has no protected work item",
                )
            ]

        reasons: list[str] = []
        review = raw.get("review") if isinstance(raw.get("review"), dict) else {}
        if review.get("verdict") != "APPROVE" or self._review_violations(
            item_id, require_live_baseline=False
        ):
            reasons.append("valid exact-head approval is absent")

        merge = raw.get("merge") if isinstance(raw.get("merge"), dict) else {}
        merged_at = _parse_timestamp(merge.get("merged_at"))
        review_at = _parse_timestamp(review.get("submitted_at"))
        snapshot_at = _parse_timestamp(self.snapshot.get("observed_at"))
        if (
            merge.get("head_sha") != raw.get("head_sha")
            or not _is_sha(merge.get("commit_sha"))
            or merge.get("ancestor_of_baseline") is not True
            or merged_at is None
            or not _is_https_url(merge.get("url"))
            or (review_at is not None and merged_at < review_at)
            or (snapshot_at is not None and merged_at > snapshot_at)
        ):
            reasons.append("externally bound merge evidence is absent or inconsistent")

        if raw.get("state") in {"observed", "closed"}:
            observation = (
                raw.get("post_merge")
                if isinstance(raw.get("post_merge"), dict)
                else {}
            )
            observed_at = _parse_timestamp(observation.get("observed_at"))
            if (
                observation.get("conclusion") != "success"
                or observation.get("commit_sha") != merge.get("commit_sha")
                or observed_at is None
                or not _is_https_url(observation.get("url"))
                or (merged_at is not None and observed_at < merged_at)
                or (snapshot_at is not None and observed_at > snapshot_at)
            ):
                reasons.append("post-merge observation proof is absent or inconsistent")

        if raw.get("state") == "closed":
            closed_at = _parse_timestamp(raw.get("closed_at"))
            post_merge = (
                raw.get("post_merge")
                if isinstance(raw.get("post_merge"), dict)
                else {}
            )
            post_merge_at = _parse_timestamp(post_merge.get("observed_at"))
            predecessors = [
                value
                for value in (review_at, merged_at, post_merge_at)
                if value is not None
            ]
            if (
                closed_at is None
                or (predecessors and closed_at < max(predecessors))
                or (snapshot_at is not None and closed_at > snapshot_at)
            ):
                reasons.append("closure timestamp is absent or inconsistent")

        if not reasons:
            return []
        return [
            Violation(
                "UNTRUSTED_TERMINAL_STATE",
                item_id,
                "; ".join(reasons),
            )
        ]

    def require_valid(self) -> None:
        violations = self.validate()
        if violations:
            raise CoordinationViolation(violations)

    def _validate_raw_types(self) -> list[Violation]:
        out: list[Violation] = []

        def malformed(item_id: str, field: str) -> None:
            out.append(Violation("MALFORMED_FIELD", item_id, field))

        if not isinstance(self.graph, dict):
            return [Violation("MALFORMED_FIELD", "graph", "root must be an object")]
        authority = self.graph.get("authority")
        if not isinstance(authority, dict):
            malformed("graph", "authority must be an object")
            authority = {}
        if not _is_string_list(authority.get("trusted_reviewers"), allow_empty=False):
            malformed("graph", "authority.trusted_reviewers must be a non-empty string array")
        if not _is_string_list(authority.get("global_forbidden_paths"), allow_empty=False):
            malformed("graph", "authority.global_forbidden_paths must be a non-empty string array")
        for field in (
            "repository",
            "baseline_ref",
            "coordination_board",
            "protected_surface_path",
        ):
            if not _is_nonempty_string(authority.get(field)):
                malformed("graph", f"authority.{field} must be a non-empty string")
        lanes = self.graph.get("lanes")
        if not isinstance(lanes, dict) or not lanes:
            malformed("graph", "lanes must be a non-empty object")
        else:
            for lane, config in lanes.items():
                if not isinstance(lane, str) or not lane or not isinstance(config, dict):
                    malformed("graph", "every lane needs a named object")
                elif not _is_int(config.get("max_active")) or config["max_active"] < 1:
                    malformed(lane, "max_active must be a positive integer")
        raw_items = self.graph.get("items")
        if not isinstance(raw_items, list) or not raw_items:
            malformed("graph", "items must be a non-empty array")
        else:
            for index, raw in enumerate(raw_items):
                candidate_id = raw.get("id") if isinstance(raw, dict) else None
                item_id = candidate_id if isinstance(candidate_id, str) else f"items[{index}]"
                if not isinstance(raw, dict):
                    malformed(item_id, "work item must be an object")
                    continue
                for field in ("id", "title", "lane", "risk", "contract_status"):
                    if not isinstance(raw.get(field), str) or not raw[field]:
                        malformed(item_id, f"{field} must be a non-empty string")
                if not _is_int(raw.get("priority")):
                    malformed(item_id, "priority must be an integer")
                if not _is_string_list(raw.get("depends_on")):
                    malformed(item_id, "depends_on must be a string array")
                spec = raw.get("spec")
                if not isinstance(spec, dict):
                    malformed(item_id, "spec must be an object")
                else:
                    if not isinstance(spec.get("path"), str) or not spec["path"]:
                        malformed(item_id, "spec.path must be a non-empty string")
                    acceptance = spec.get("acceptance")
                    if not isinstance(acceptance, dict) or not acceptance:
                        malformed(item_id, "spec.acceptance must be a non-empty object")
                    else:
                        for criterion_id, criterion in acceptance.items():
                            if not isinstance(criterion_id, str) or not criterion_id:
                                malformed(
                                    item_id,
                                    "every acceptance criterion needs a string id",
                                )
                            if not isinstance(criterion, dict):
                                malformed(
                                    item_id,
                                    f"acceptance {criterion_id!r} must be an object",
                                )
                                continue
                            if not _is_nonempty_string(criterion.get("statement")):
                                malformed(
                                    item_id,
                                    f"acceptance {criterion_id!r}.statement must be a non-empty string",
                                )
                            if not _is_string_list(
                                criterion.get("verification"), allow_empty=False
                            ):
                                malformed(
                                    item_id,
                                    f"acceptance {criterion_id!r}.verification must be a non-empty string array",
                                )
                paths = raw.get("paths")
                if not isinstance(paths, dict):
                    malformed(item_id, "paths must be an object")
                else:
                    if not _is_string_list(paths.get("allow"), allow_empty=False):
                        malformed(item_id, "paths.allow must be a non-empty string array")
                    if not _is_string_list(paths.get("deny")):
                        malformed(item_id, "paths.deny must be a string array")
                if raw.get("migration") is not None and not isinstance(raw.get("migration"), str):
                    malformed(item_id, "migration must be null or a string")
                if not _is_string_list(raw.get("required_checks"), allow_empty=False):
                    malformed(item_id, "required_checks must be a non-empty string array")
                protected = raw.get("protected_change")
                if protected is not None:
                    if not isinstance(protected, dict):
                        malformed(item_id, "protected_change must be an object")
                    else:
                        if protected.get("status") != "approved":
                            malformed(item_id, "protected_change.status must be approved")
                        if not isinstance(protected.get("owner_decision"), str) or not protected["owner_decision"]:
                            malformed(item_id, "protected_change.owner_decision is required")
                        if not _is_string_list(protected.get("scope"), allow_empty=False):
                            malformed(item_id, "protected_change.scope must be a non-empty string array")

        if not isinstance(self.snapshot, dict):
            return sorted(set((*out, Violation("MALFORMED_FIELD", "snapshot", "root must be an object"))))
        if type(self.snapshot.get("synthetic")) is not bool:
            malformed("snapshot", "synthetic must be a boolean")
        for field in (
            "source",
            "repository",
            "baseline_ref",
            "observed_at",
            "expires_at",
            "baseline_sha",
            "graph_contract_sha256",
        ):
            if not _is_nonempty_string(self.snapshot.get(field)):
                malformed("snapshot", f"{field} must be a non-empty string")
        observations = self.snapshot.get("observations")
        if not isinstance(observations, list):
            malformed("snapshot", "observations must be an array")
        else:
            for index, raw in enumerate(observations):
                candidate_id = raw.get("id") if isinstance(raw, dict) else None
                item_id = candidate_id if isinstance(candidate_id, str) else f"observations[{index}]"
                if not isinstance(raw, dict):
                    malformed(item_id, "observation must be an object")
                    continue
                if not isinstance(raw.get("id"), str) or not raw["id"]:
                    malformed(item_id, "observation.id must be a non-empty string")
                if not isinstance(raw.get("state"), str):
                    malformed(item_id, "observation.state must be a string")
                for field in ("changed_paths", "acceptance_ids", "unresolved_decisions"):
                    if field in raw and not _is_string_list(raw[field]):
                        malformed(item_id, f"observation.{field} must be a string array")
                if "checks" in raw:
                    checks = raw["checks"]
                    if not isinstance(checks, list) or not all(
                        isinstance(check, dict) for check in checks
                    ):
                        malformed(item_id, "observation.checks must be an object array")
                    elif isinstance(checks, list):
                        for check in checks:
                            for field in ("name", "sha", "conclusion", "url"):
                                if field in check and not _is_nonempty_string(
                                    check[field]
                                ):
                                    malformed(
                                        item_id,
                                        f"observation.checks.{field} must be a non-empty string",
                                    )
                            for field in ("collected", "executed", "skipped"):
                                if field in check and not _is_int(check[field]):
                                    malformed(
                                        item_id,
                                        f"observation.checks.{field} must be an integer",
                                    )
                for field in ("issue_number", "pr_number"):
                    if field in raw and not _is_positive_int(raw[field]):
                        malformed(item_id, f"observation.{field} must be a positive integer")
                for field in ("issue_url", "pr_url"):
                    if field in raw and not _is_https_url(raw[field]):
                        malformed(item_id, f"observation.{field} must be an HTTPS URL")
                if "evidence" in raw and not isinstance(raw["evidence"], dict):
                    malformed(item_id, "observation.evidence must be an object")
                elif isinstance(raw.get("evidence"), dict):
                    for phase in ("red", "green"):
                        evidence = raw["evidence"].get(phase)
                        if evidence is not None and not isinstance(evidence, dict):
                            malformed(item_id, f"observation.evidence.{phase} must be an object")
                        elif isinstance(evidence, dict):
                            for field in ("sha", "command", "conclusion", "url"):
                                if field in evidence and not _is_nonempty_string(
                                    evidence[field]
                                ):
                                    malformed(
                                        item_id,
                                        f"observation.evidence.{phase}.{field} must be a non-empty string",
                                    )
                            for field in ("collected", "executed", "skipped"):
                                if field in evidence and not _is_int(evidence[field]):
                                    malformed(
                                        item_id,
                                        f"observation.evidence.{phase}.{field} must be an integer",
                                    )
                            if (
                                phase == "red"
                                and "ancestor_of_head" in evidence
                                and type(evidence["ancestor_of_head"]) is not bool
                            ):
                                malformed(item_id, "observation.evidence.red.ancestor_of_head must be a boolean")
                            if (
                                phase == "red"
                                and "descendant_of_base" in evidence
                                and type(evidence["descendant_of_base"]) is not bool
                            ):
                                malformed(item_id, "observation.evidence.red.descendant_of_base must be a boolean")
                if "baseline_proof" in raw and not isinstance(
                    raw["baseline_proof"], dict
                ):
                    malformed(
                        item_id,
                        "observation.baseline_proof must be an object",
                    )
                elif isinstance(raw.get("baseline_proof"), dict):
                    for field in (
                        "repository",
                        "baseline_ref",
                        "base_sha",
                        "head_sha",
                        "graph_contract_sha256",
                        "observed_at",
                        "expires_at",
                        "url",
                    ):
                        if field in raw["baseline_proof"] and not _is_nonempty_string(
                            raw["baseline_proof"][field]
                        ):
                            malformed(
                                item_id,
                                f"observation.baseline_proof.{field} must be a non-empty string",
                            )
                if "review" in raw and raw["review"] is not None and not isinstance(raw["review"], dict):
                    malformed(item_id, "observation.review must be null or an object")
                elif isinstance(raw.get("review"), dict):
                    for field in ("reviewer", "verdict", "commit_id", "submitted_at"):
                        if field in raw["review"] and not _is_nonempty_string(raw["review"][field]):
                            malformed(item_id, f"observation.review.{field} must be a non-empty string")
                for object_name in ("merge", "post_merge"):
                    value = raw.get(object_name)
                    if value is not None and not isinstance(value, dict):
                        malformed(
                            item_id,
                            f"observation.{object_name} must be null or an object",
                        )
                if isinstance(raw.get("merge"), dict):
                    merge = raw["merge"]
                    for field in ("head_sha", "commit_sha", "merged_at", "url"):
                        if field in merge and not _is_nonempty_string(merge[field]):
                            malformed(
                                item_id,
                                f"observation.merge.{field} must be a non-empty string",
                            )
                    if (
                        "ancestor_of_baseline" in merge
                        and type(merge["ancestor_of_baseline"]) is not bool
                    ):
                        malformed(
                            item_id,
                            "observation.merge.ancestor_of_baseline must be a boolean",
                        )
                if isinstance(raw.get("post_merge"), dict):
                    for field in ("commit_sha", "conclusion", "observed_at", "url"):
                        if field in raw["post_merge"] and not _is_nonempty_string(
                            raw["post_merge"][field]
                        ):
                            malformed(
                                item_id,
                                f"observation.post_merge.{field} must be a non-empty string",
                            )
                if "closed_at" in raw and not _is_nonempty_string(raw["closed_at"]):
                    malformed(
                        item_id,
                        "observation.closed_at must be a non-empty string",
                    )
        return sorted(set(out))

    def _validate_shapes(self) -> list[Violation]:
        out: list[Violation] = []
        if self.graph.get("schema") != GRAPH_SCHEMA:
            out.append(Violation("INVALID_GRAPH_SCHEMA", "graph", "unknown schema"))
        if self.snapshot.get("schema") != SNAPSHOT_SCHEMA:
            out.append(Violation("INVALID_SNAPSHOT_SCHEMA", "snapshot", "unknown schema"))
        protected_surface_path = self.authority.get("protected_surface_path")
        if (
            not _valid_path_pattern(protected_surface_path)
            or protected_surface_path.endswith("/**")
            or protected_surface_path != _PROTECTED_SURFACE_PATH
        ):
            out.append(
                Violation(
                    "INVALID_PROTECTED_SURFACE_PATH",
                    "graph",
                    f"protected surface must be {_PROTECTED_SURFACE_PATH!r}",
                )
            )
        if not _is_sha(self.snapshot.get("baseline_sha")):
            out.append(Violation("INVALID_BASELINE_SHA", "snapshot", "baseline_sha must be 40-char lowercase hex"))
        if not _is_sha256(self.snapshot.get("graph_contract_sha256")):
            out.append(
                Violation(
                    "INVALID_GRAPH_CONTRACT_SHA256",
                    "snapshot",
                    "graph_contract_sha256 must bind canonical protected graph JSON",
                )
            )
        if self.snapshot.get("repository") != self.authority.get("repository"):
            out.append(Violation("REPOSITORY_MISMATCH", "snapshot", "snapshot repository differs from the protected authority"))
        if self.snapshot.get("baseline_ref") != self.authority.get("baseline_ref"):
            out.append(Violation("BASELINE_REF_MISMATCH", "snapshot", "snapshot baseline ref differs from the protected authority"))
        synthetic = self.snapshot.get("synthetic") is True
        expected_source = "fixture" if synthetic else "github"
        if self.snapshot.get("source") != expected_source:
            out.append(Violation("INVALID_SNAPSHOT_SOURCE", "snapshot", f"source must be {expected_source!r}"))
        observed_at = _parse_timestamp(self.snapshot.get("observed_at"))
        expires_at = _parse_timestamp(self.snapshot.get("expires_at"))
        if observed_at is None or expires_at is None:
            out.append(Violation("INVALID_SNAPSHOT_TIME", "snapshot", "snapshot timestamps must be timezone-aware ISO-8601"))
        elif expires_at <= observed_at or expires_at - observed_at > MAX_SNAPSHOT_AGE:
            out.append(Violation("INVALID_SNAPSHOT_WINDOW", "snapshot", "snapshot validity must be greater than zero and no more than five minutes"))
        elif not synthetic:
            if self.now > expires_at:
                out.append(Violation("STALE_SNAPSHOT", "snapshot", "live snapshot has expired"))
            if observed_at > self.now + MAX_CLOCK_SKEW:
                out.append(Violation("FUTURE_SNAPSHOT", "snapshot", "live snapshot is beyond permitted clock skew"))

        ids = [item.id for item in self.items]
        for duplicate in sorted({item_id for item_id in ids if ids.count(item_id) > 1}):
            out.append(Violation("DUPLICATE_ITEM", duplicate, "work-item id is not unique"))

        lane_names = set(self.lanes)
        migration_owners: dict[str, str] = {}
        for item in self.items:
            if item.contract_status not in _CONTRACT_STATUSES:
                out.append(
                    Violation(
                        "INVALID_CONTRACT_STATUS",
                        item.id,
                        "contract_status must be executable or contract_pending",
                    )
                )
            if not ID_RE.fullmatch(item.id):
                out.append(Violation("INVALID_ITEM_ID", item.id or "<missing>", "id must be a stable uppercase token"))
            if not item.title:
                out.append(Violation("MISSING_TITLE", item.id, "title is required"))
            if item.lane not in lane_names:
                out.append(Violation("UNKNOWN_LANE", item.id, f"unknown lane {item.lane!r}"))
            if not _is_int(item.priority) or item.priority < 0:
                out.append(Violation("INVALID_PRIORITY", item.id, "priority must be a non-negative integer"))
            if not item.spec_path or not _valid_path_pattern(item.spec_path) or item.spec_path.endswith("/**"):
                out.append(Violation("INVALID_SPEC_PATH", item.id, "spec path must be one exact repository path"))
            if not item.acceptance or len(set(item.acceptance_ids)) != len(item.acceptance_ids):
                out.append(Violation("INVALID_ACCEPTANCE_CONTRACT", item.id, "acceptance criteria must be non-empty and unique"))
            for criterion in item.acceptance:
                if (
                    not ACCEPTANCE_ID_RE.fullmatch(criterion.id)
                    or not _is_nonempty_string(criterion.statement)
                    or not _is_string_list(list(criterion.verification), allow_empty=False)
                ):
                    out.append(Violation("INVALID_ACCEPTANCE_CONTRACT", item.id, f"criterion {criterion.id!r} is malformed"))
            if not item.allowed_paths:
                out.append(Violation("EMPTY_PATH_CLAIM", item.id, "at least one allowed path is required"))
            for pattern in (*item.allowed_paths, *item.denied_paths, *self._global_denied()):
                if not _valid_path_pattern(pattern):
                    out.append(Violation("INVALID_PATH", item.id, f"unsupported or unsafe path pattern {pattern!r}"))
            if item.protected_scopes:
                if item.protected_status != "approved" or not item.protected_decision:
                    out.append(Violation("INVALID_PROTECTED_AUTHORIZATION", item.id, "protected scope needs an approved owner decision"))
                for scope in item.protected_scopes:
                    if not _valid_path_pattern(scope) or scope.endswith("/**"):
                        out.append(Violation("INVALID_PROTECTED_SCOPE", item.id, "protected scope must name exact files"))
            for allowed in item.allowed_paths:
                for denied in item.denied_paths:
                    if _valid_path_pattern(allowed) and _valid_path_pattern(denied) and _patterns_overlap(allowed, denied):
                        out.append(Violation("FORBIDDEN_PATH_CLAIM", item.id, f"{allowed!r} overlaps forbidden {denied!r}"))
                for denied in self._global_denied():
                    if (
                        item.contract_status == "executable"
                        and
                        _valid_path_pattern(allowed)
                        and _valid_path_pattern(denied)
                        and _patterns_overlap(allowed, denied)
                        and not self._authorized_protected_pattern(item, allowed)
                    ):
                        out.append(Violation("FORBIDDEN_PATH_CLAIM", item.id, f"{allowed!r} overlaps protected {denied!r} without exact owner authorization"))
            if not item.required_checks or len(set(item.required_checks)) != len(item.required_checks):
                out.append(Violation("INVALID_REQUIRED_CHECKS", item.id, "required checks must be non-empty and unique"))
            if item.migration is not None:
                if not isinstance(item.migration, str) or not MIGRATION_RE.fullmatch(item.migration):
                    out.append(Violation("INVALID_MIGRATION", item.id, "migration reservation must be a three-digit string"))
                elif item.migration in migration_owners:
                    out.append(Violation("DUPLICATE_MIGRATION", item.id, f"migration {item.migration} also belongs to {migration_owners[item.migration]}"))
                else:
                    migration_owners[item.migration] = item.id

        observation_ids = [
            raw["id"] for raw in self.observations if isinstance(raw.get("id"), str)
        ]
        for duplicate in sorted({item_id for item_id in observation_ids if observation_ids.count(item_id) > 1}):
            out.append(Violation("DUPLICATE_OBSERVATION", duplicate, "controller snapshot has duplicate observations"))
        for raw in self.observations:
            item_id = raw.get("id", "")
            if item_id not in self.item_by_id:
                out.append(Violation("UNKNOWN_OBSERVATION", item_id or "<missing>", "snapshot references no work contract"))
                continue
            state = raw.get("state")
            if not isinstance(state, str) or state not in STATES:
                out.append(Violation("INVALID_STATE", item_id, f"unknown state {state!r}"))
            if state in ACTIVE_STATES:
                if not _is_sha(raw.get("base_sha")):
                    out.append(Violation("INVALID_BASE_SHA", item_id, "active item needs an exact base SHA"))
                if not _is_sha(raw.get("head_sha")):
                    out.append(Violation("INVALID_HEAD_SHA", item_id, "active item needs an exact head SHA"))
        return out

    def _validate_dependencies(self) -> list[Violation]:
        out: list[Violation] = []
        ids = set(self.item_by_id)
        adjacency: dict[str, tuple[str, ...]] = {}
        for item in self.items:
            adjacency[item.id] = item.depends_on
            for dependency in item.depends_on:
                if dependency not in ids:
                    out.append(Violation("UNKNOWN_DEPENDENCY", item.id, f"dependency {dependency!r} does not exist"))
                if dependency == item.id:
                    out.append(Violation("DEPENDENCY_CYCLE", item.id, "item depends on itself"))

        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(item_id: str, trail: tuple[str, ...]) -> None:
            if item_id in visiting:
                cycle = " -> ".join((*trail, item_id))
                out.append(Violation("DEPENDENCY_CYCLE", item_id, cycle))
                return
            if item_id in visited:
                return
            visiting.add(item_id)
            for dependency in adjacency.get(item_id, ()):
                if dependency in adjacency:
                    visit(dependency, (*trail, item_id))
            visiting.remove(item_id)
            visited.add(item_id)

        for item_id in sorted(adjacency):
            visit(item_id, ())
        return out

    def _validate_claims(self) -> list[Violation]:
        out: list[Violation] = []
        active_by_lane: dict[str, list[WorkItem]] = {}
        active: list[WorkItem] = []
        for item in self.items:
            if self._reported_state(item.id) in ACTIVE_STATES:
                active.append(item)
                active_by_lane.setdefault(item.lane, []).append(item)

        for lane, items in active_by_lane.items():
            raw_limit = self.lanes.get(lane, {}).get("max_active", 1)
            limit = raw_limit if isinstance(raw_limit, int) and raw_limit >= 0 else 0
            if len(items) > limit:
                out.append(Violation("LANE_CAPACITY_EXCEEDED", lane, f"{len(items)} active items exceeds max_active={limit}"))

        for index, left in enumerate(active):
            for right in active[index + 1 :]:
                overlaps = [
                    f"{lp} <-> {rp}"
                    for lp in left.allowed_paths
                    for rp in right.allowed_paths
                    if _valid_path_pattern(lp) and _valid_path_pattern(rp) and _patterns_overlap(lp, rp)
                ]
                if overlaps:
                    out.append(Violation("ACTIVE_PATH_COLLISION", f"{left.id},{right.id}", ", ".join(overlaps)))
        return out

    def _readiness_violations(
        self,
        item: WorkItem,
        raw: dict[str, Any] | None,
        *,
        require_queue_state: bool = True,
        require_live_baseline: bool = True,
    ) -> list[Violation]:
        out: list[Violation] = []
        if raw is None:
            return [Violation("MISSING_OBSERVATION", item.id, "no controller observation")]
        permitted_states = REVIEWABLE_STATES if require_queue_state else REVIEW_EVIDENCE_STATES
        if raw.get("state") not in permitted_states:
            message = (
                "item must be in ci or review_ready"
                if require_queue_state
                else "review evidence is only valid for a review lifecycle state"
            )
            out.append(Violation("INVALID_REVIEW_STATE", item.id, message))
        head = raw.get("head_sha")
        if not _is_sha(head):
            out.append(Violation("INVALID_HEAD_SHA", item.id, "review requires an exact head SHA"))
        if not _is_positive_int(raw.get("issue_number")) or not _is_https_url(raw.get("issue_url")):
            out.append(Violation("MISSING_ISSUE", item.id, "review requires a linked issue"))
        if not _is_positive_int(raw.get("pr_number")) or not _is_https_url(raw.get("pr_url")):
            out.append(Violation("MISSING_PR", item.id, "review requires a linked PR"))
        if not isinstance(raw.get("author"), str) or not raw.get("author"):
            out.append(Violation("MISSING_AUTHOR", item.id, "author identity must come from the external PR"))
        if not isinstance(raw.get("branch"), str) or not raw.get("branch"):
            out.append(Violation("MISSING_BRANCH", item.id, "review requires the observed branch"))
        if not _is_sha(raw.get("base_sha")) or raw.get("base_sha") == head:
            out.append(Violation("INVALID_BASE_SHA", item.id, "base must be an exact SHA different from head"))
        if require_live_baseline and raw.get("base_sha") != self.snapshot.get("baseline_sha"):
            out.append(Violation("BASELINE_SHA_MISMATCH", item.id, "PR base is not the protected live baseline"))
        out.extend(
            self._baseline_proof_violations(
                item,
                raw,
                require_live_baseline=require_live_baseline,
            )
        )

        actual_acceptance = raw.get("acceptance_ids")
        if not _is_string_list(actual_acceptance) or sorted(actual_acceptance) != sorted(item.acceptance_ids):
            out.append(Violation("ACCEPTANCE_DRIFT", item.id, "observed acceptance ids differ from the protected work contract"))
        decisions = raw.get("unresolved_decisions")
        if not isinstance(decisions, list) or decisions:
            out.append(Violation("UNRESOLVED_DECISION", item.id, "all material decisions must be resolved"))

        changed = raw.get("changed_paths")
        if not isinstance(changed, list) or not changed:
            out.append(Violation("EMPTY_DIFF", item.id, "reviewable work must have a non-empty changed-path set"))
        else:
            for path in changed:
                if not _valid_path_pattern(path) or path.endswith("/**"):
                    out.append(Violation("INVALID_CHANGED_PATH", item.id, f"invalid changed path {path!r}"))
                    continue
                if not any(_matches(pattern, path) for pattern in item.allowed_paths):
                    out.append(Violation("OUT_OF_SCOPE_PATH", item.id, f"{path!r} is outside the claim"))
                if self._path_denied(item, path):
                    out.append(Violation("FORBIDDEN_PATH_CHANGED", item.id, f"{path!r} is forbidden"))

        evidence = raw.get("evidence") if isinstance(raw.get("evidence"), dict) else {}
        red = evidence.get("red") if isinstance(evidence.get("red"), dict) else {}
        green = evidence.get("green") if isinstance(evidence.get("green"), dict) else {}
        red_collected = red.get("collected")
        red_executed = red.get("executed")
        red_skipped = red.get("skipped", 0)
        if (
            red.get("conclusion") != "failure"
            or not _is_sha(red.get("sha"))
            or red.get("sha") == head
            or not _is_int(red_collected)
            or red_collected <= 0
            or not _is_int(red_executed)
            or red_executed <= 0
            or not _is_int(red_skipped)
            or red_skipped < 0
            or not _is_nonempty_string(red.get("command"))
            or not _is_https_url(red.get("url"))
        ):
            out.append(Violation("MISSING_RED", item.id, "RED must be non-vacuous, failing, linked, and pre-date final head"))
        if (
            red.get("sha") == raw.get("base_sha")
            or red.get("descendant_of_base") is not True
            or red.get("ancestor_of_head") is not True
        ):
            out.append(
                Violation(
                    "UNPROVEN_RED_LINEAGE",
                    item.id,
                    "external ancestry must prove base -> distinct RED -> final head",
                )
            )
        if _is_int(red_collected) and _is_int(red_executed) and _is_int(red_skipped) and red_collected != red_executed + red_skipped:
            out.append(Violation("EVIDENCE_COUNT_MISMATCH", item.id, "RED collected must equal executed + skipped"))
        green_collected = green.get("collected")
        green_executed = green.get("executed")
        green_skipped = green.get("skipped", 0)
        if _is_int(green_collected) and _is_int(green_executed) and (green_collected <= 0 or green_executed <= 0):
            out.append(Violation("ZERO_TESTS", item.id, "GREEN collected/executed zero tests"))
        if _is_int(green_collected) and _is_int(green_executed) and _is_int(green_skipped) and green_collected != green_executed + green_skipped:
            out.append(Violation("EVIDENCE_COUNT_MISMATCH", item.id, "GREEN collected must equal executed + skipped"))
        if green.get("sha") != head:
            out.append(Violation("STALE_GREEN_EVIDENCE", item.id, "final GREEN is not bound to head"))
        if (
            green.get("conclusion") != "success"
            or not _is_int(green_collected)
            or not _is_int(green_executed)
            or not _is_int(green_skipped)
            or green_skipped < 0
            or green_collected <= 0
            or green_executed <= 0
            or not _is_nonempty_string(green.get("command"))
            or not _is_https_url(green.get("url"))
        ):
            out.append(Violation("INVALID_GREEN", item.id, "GREEN must be a non-vacuous exact-head success"))

        checks = raw.get("checks") if isinstance(raw.get("checks"), list) else []
        by_name: dict[str, list[dict[str, Any]]] = {}
        for check in checks:
            if isinstance(check, dict) and isinstance(check.get("name"), str):
                by_name.setdefault(check["name"], []).append(check)
        for required in item.required_checks:
            matches = by_name.get(required, [])
            if len(matches) != 1:
                out.append(Violation("MISSING_REQUIRED_CHECK", item.id, f"{required!r} must appear exactly once"))
                continue
            check = matches[0]
            if check.get("sha") != head:
                out.append(Violation("STALE_CHECK", item.id, f"{required!r} is not bound to head"))
            if check.get("conclusion") != "success":
                out.append(Violation("FAILED_REQUIRED_CHECK", item.id, f"{required!r} is not successful"))
            collected = check.get("collected")
            executed = check.get("executed")
            skipped = check.get("skipped", 0)
            if not _is_int(collected) or not _is_int(executed) or not _is_int(skipped) or collected <= 0 or executed <= 0 or skipped < 0:
                out.append(Violation("VACUOUS_REQUIRED_CHECK", item.id, f"{required!r} proves no executed cases"))
            elif collected != executed + skipped:
                out.append(Violation("CHECK_COUNT_MISMATCH", item.id, f"{required!r} collected must equal executed + skipped"))
            if not _is_https_url(check.get("url")):
                out.append(Violation("UNLINKED_REQUIRED_CHECK", item.id, f"{required!r} lacks immutable evidence"))
        return sorted(set(out))

    def _baseline_proof_violations(
        self,
        item: WorkItem,
        raw: dict[str, Any],
        *,
        require_live_baseline: bool,
    ) -> list[Violation]:
        proof = raw.get("baseline_proof")
        if not isinstance(proof, dict):
            return [
                Violation(
                    "INVALID_BASELINE_PROOF",
                    item.id,
                    "review lifecycle needs a persisted live-baseline proof",
                )
            ]

        observed_at = _parse_timestamp(proof.get("observed_at"))
        expires_at = _parse_timestamp(proof.get("expires_at"))
        review = raw.get("review") if isinstance(raw.get("review"), dict) else {}
        reviewed_at = _parse_timestamp(review.get("submitted_at"))
        snapshot_at = _parse_timestamp(self.snapshot.get("observed_at"))
        invalid = (
            proof.get("repository") != self.authority.get("repository")
            or proof.get("baseline_ref") != self.authority.get("baseline_ref")
            or proof.get("base_sha") != raw.get("base_sha")
            or proof.get("head_sha") != raw.get("head_sha")
            or not _is_sha256(proof.get("graph_contract_sha256"))
            or not _is_https_url(proof.get("url"))
            or observed_at is None
            or expires_at is None
            or (
                observed_at is not None
                and expires_at is not None
                and (
                    expires_at <= observed_at
                    or expires_at - observed_at > MAX_SNAPSHOT_AGE
                )
            )
            or (
                reviewed_at is not None
                and observed_at is not None
                and expires_at is not None
                and not (observed_at <= reviewed_at <= expires_at)
            )
        )
        if require_live_baseline:
            invalid = invalid or (
                proof.get("base_sha") != self.snapshot.get("baseline_sha")
                or proof.get("graph_contract_sha256")
                != self.snapshot.get("graph_contract_sha256")
                or (
                    snapshot_at is not None
                    and observed_at is not None
                    and expires_at is not None
                    and not (observed_at <= snapshot_at <= expires_at)
                )
            )
        if not invalid:
            return []
        return [
            Violation(
                "INVALID_BASELINE_PROOF",
                item.id,
                "persisted baseline proof is missing, stale, or inconsistent",
            )
        ]

    def _review_readiness(self, item_id: str) -> ReadinessResult:
        item = self.item_by_id.get(item_id)
        if item is None:
            violations = (Violation("UNKNOWN_ITEM", item_id, "work item does not exist"),)
            return ReadinessResult(item_id, False, violations)
        violations = tuple(self._readiness_violations(item, self.observation_by_id.get(item_id)))
        return ReadinessResult(item_id, not violations, violations)

    def _review_violations(
        self,
        item_id: str,
        *,
        require_live_baseline: bool | None = None,
    ) -> list[Violation]:
        item = self.item_by_id.get(item_id)
        raw = self.observation_by_id.get(item_id)
        if item is None:
            return [Violation("UNKNOWN_ITEM", item_id, "work item does not exist")]
        if require_live_baseline is None:
            require_live_baseline = not (
                raw is not None and raw.get("state") in TERMINAL_PROOF_STATES
            )
        readiness = self._readiness_violations(
            item,
            raw,
            require_queue_state=False,
            require_live_baseline=require_live_baseline,
        )
        if raw is None:
            return readiness
        review = raw.get("review")
        if not isinstance(review, dict):
            return sorted(set((*readiness, Violation("REVIEW_MISSING", item.id, "no external review"))))
        verdict = review.get("verdict")
        if verdict not in REVIEW_VERDICTS:
            readiness.append(Violation("INVALID_VERDICT", item.id, f"unsupported verdict {verdict!r}"))
        reviewer = review.get("reviewer")
        if reviewer == raw.get("author"):
            readiness.append(Violation("REVIEWER_NOT_INDEPENDENT", item.id, "author cannot review own work"))
        trusted = self.authority.get("trusted_reviewers", [])
        if not isinstance(trusted, list) or reviewer not in trusted:
            readiness.append(Violation("UNTRUSTED_REVIEWER", item.id, "reviewer is not an externally trusted principal"))
        if review.get("commit_id") != raw.get("head_sha"):
            readiness.append(Violation("STALE_REVIEW", item.id, "review is not anchored to current head"))
        submitted_at = _parse_timestamp(review.get("submitted_at"))
        snapshot_at = _parse_timestamp(self.snapshot.get("observed_at"))
        if submitted_at is None:
            readiness.append(Violation("INVALID_REVIEW_TIME", item.id, "review timestamp is not valid timezone-aware ISO-8601"))
        elif snapshot_at is not None and submitted_at > snapshot_at:
            readiness.append(Violation("INVALID_REVIEW_TIME", item.id, "review timestamp is later than the external snapshot"))
        return sorted(set(readiness))

    def _derived_state(self, item_id: str) -> str:
        raw = self.observation_by_id.get(item_id)
        if raw is None:
            return "planned"
        if (
            raw.get("state") in TERMINAL_PROOF_STATES
            and not self._terminal_state_violations(item_id, raw)
        ):
            return raw["state"]
        review = raw.get("review") if isinstance(raw.get("review"), dict) else None
        if review:
            violations = self._review_violations(item_id)
            codes = {item.code for item in violations}
            if review.get("verdict") == "APPROVE" and not violations:
                return "approved"
            if review.get("verdict") == "CHANGES-REQUIRED" and not violations:
                return "changes_required"
            if "STALE_REVIEW" in codes:
                return "building"
        if self._review_readiness(item_id).ready:
            return "review_ready"
        if raw.get("state") in {"review_ready", "approved", "changes_required"}:
            return "ci"
        return raw.get("state", "planned")
